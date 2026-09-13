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
