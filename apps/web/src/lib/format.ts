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
// Currency keeps Indian grouping (₹1.6Cr) because Threadline reports in INR;
// counts use K/M so non-Indian readers are not tripped up by lakh notation.
const count = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const countCompact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 0 });

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

/**
 * A tight, "nice" axis domain for rate metrics: lines fill the plot instead of
 * hugging a zero baseline, and ticks land on round percentages.
 */
export function niceDomain(values: number[], isPercent: boolean): { domain: [number, number]; ticks: number[] } {
  const finite = values.filter((v) => Number.isFinite(v));
  if (!finite.length) return { domain: [0, 1], ticks: [0, 0.5, 1] };
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (min === max) {
    min = min * 0.9;
    max = max * 1.1 || 1;
  }
  const span = max - min;
  const rawStep = span / 4;
  const pow = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= rawStep) ?? pow * 10;
  let lo = Math.floor((min - span * 0.15) / step) * step;
  let hi = Math.ceil((max + span * 0.15) / step) * step;
  if (lo < 0) lo = 0;
  if (isPercent && hi > 1) hi = 1;
  const ticks: number[] = [];
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Number(t.toFixed(10)));
  return { domain: [lo, hi], ticks };
}
