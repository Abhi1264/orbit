import type { Filter } from "@/lib/api/analytics";

/** Deep link into the Analytics explorer with a metric, scope and window preselected. */
export function exploreHref(opts: {
  metric: string;
  filters?: Filter[];
  from?: string;
  to?: string;
  breakdown?: string | null;
  compareFrom?: string;
  compareTo?: string;
}): `/analytics?${string}` {
  const sp = new URLSearchParams({ metric: opts.metric });
  if (opts.filters?.length) sp.set("f", JSON.stringify(opts.filters));
  if (opts.from) sp.set("from", opts.from);
  if (opts.to) sp.set("to", opts.to);
  if (opts.breakdown) sp.set("breakdown", opts.breakdown);
  return `/analytics?${sp.toString()}`;
}

export function investigationHref(id: number): `/investigations/${number}` {
  return `/investigations/${id}`;
}

export function experimentHref(id: number): `/experiments/${number}` {
  return `/experiments/${id}`;
}

/** Open the analyst with the current page as context; `q` is asked immediately. */
export function analystHref(opts: {
  q?: string;
  metric?: string | null;
  filters?: Filter[];
  from?: string;
  to?: string;
  experimentId?: number;
  investigationId?: number;
}): `/analyst?${string}` {
  const sp = new URLSearchParams();
  if (opts.q) sp.set("q", opts.q);
  if (opts.metric) sp.set("metric", opts.metric);
  if (opts.filters?.length) sp.set("f", JSON.stringify(opts.filters));
  if (opts.from) sp.set("from", opts.from);
  if (opts.to) sp.set("to", opts.to);
  if (opts.experimentId) sp.set("experiment_id", String(opts.experimentId));
  if (opts.investigationId) sp.set("investigation_id", String(opts.investigationId));
  return `/analyst?${sp.toString()}`;
}

export function releaseHref(id: number): `/releases/${number}` {
  return `/releases/${id}`;
}

export function decisionHref(id: number): `/decisions?id=${number}` {
  return `/decisions?id=${id}`;
}

export function opsHref(tab: "sops" | "knowledge" | "feedback", opts: { doc?: number; sop?: number } = {}) {
  const sp = new URLSearchParams({ tab });
  if (opts.doc) sp.set("doc", String(opts.doc));
  if (opts.sop) sp.set("sop", String(opts.sop));
  return `/ops?${sp.toString()}` as `/ops?${string}`;
}

/** Route to any object the API references by (type, id). */
export function entityHref(type: string, id: number, extra: Record<string, string> = {}) {
  switch (type) {
    case "investigation":
      return investigationHref(id);
    case "experiment":
      return experimentHref(id);
    case "release":
      return releaseHref(id);
    case "decision":
      return decisionHref(id);
    case "sop":
      return opsHref("sops", { sop: id });
    case "knowledge":
      return opsHref("knowledge", { doc: id });
    case "feedback":
      return opsHref("feedback");
    case "saved":
      return extra.kind === "funnel"
        ? ("/funnels" as const)
        : extra.kind === "cohort"
          ? ("/cohorts" as const)
          : ("/analytics" as const);
    case "metric":
      return exploreHref({ metric: extra.key ?? "conversion" });
    case "dimension":
      return exploreHref({ metric: "conversion", breakdown: extra.key });
    default:
      return "/" as const;
  }
}
