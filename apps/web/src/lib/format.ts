export type MetricFormat = "count" | "currency" | "percent" | "ratio" | "number" | "days";

const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const inrCompact = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});
const count = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const countCompact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const decimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 0 });

export function formatMetric(value: number | null | undefined, format: MetricFormat, compact = false) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  switch (format) {
    case "currency":
      return compact ? inrCompact.format(value) : inr.format(value);
    case "percent":
      return `${(value * 100).toFixed(value * 100 < 10 ? 2 : 1)}%`;
    case "ratio":
      return decimal.format(value);
    case "days":
      return `${decimal.format(value)} d`;
    case "count":
      return compact ? countCompact.format(value) : count.format(value);
    default:
      return decimal.format(value);
  }
}

/**
 * Period-over-period change, expressed the way an analyst would read it: rates move
 * in percentage points, everything else in relative percent.
 */
export function formatDelta(current: number | null, previous: number | null, format: MetricFormat) {
  if (current === null || previous === null) return null;
  if (format === "percent") {
    const pp = (current - previous) * 100;
    return { text: `${pp > 0 ? "+" : ""}${pp.toFixed(2)} pp`, sign: Math.sign(pp) };
  }
  if (previous === 0) return null;
  const rel = ((current - previous) / previous) * 100;
  return { text: `${rel > 0 ? "+" : ""}${rel.toFixed(1)}%`, sign: Math.sign(rel) };
}

export function formatRelative(value: number, digits = 1) {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

export function formatPp(value: number, digits = 2) {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(digits)} pp`;
}

export function formatCompactCount(value: number) {
  return countCompact.format(value);
}

export function formatDate(
  iso: string | Date,
  opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" },
) {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleDateString("en-IN", opts);
}

export function formatDateTime(iso: string | Date) {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return d.toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function titleCase(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
