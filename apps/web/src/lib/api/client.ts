import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./schema";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public requestId?: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const unauthorizedRedirect: Middleware = {
  async onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined") {
      const next = window.location.pathname + window.location.search;
      if (window.location.pathname !== "/login") {
        // A hard navigation on session expiry intentionally drops all client cache.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.assign(`/login?next=${encodeURIComponent(next)}`);
      }
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });
api.use(unauthorizedRedirect);

type ErrorBody = { detail?: string | { msg: string }[]; error?: string } | undefined;

export function toApiError(response: Response, body: ErrorBody): ApiError {
  let detail = response.statusText || "Request failed";
  if (body?.detail) {
    detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
  }
  if (body?.error) detail = `${detail}: ${body.error}`;
  return new ApiError(response.status, detail, response.headers.get("x-request-id") ?? undefined);
}

/** Unwrap an openapi-fetch result into data or a thrown ApiError, for use in query functions. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result.response, result.error as ErrorBody);
  }
  return result.data;
}
