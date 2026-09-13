"use client";

import type { CohortResult } from "@/lib/api/analytics";
import { formatCompactCount, formatDate, formatMetric } from "@/lib/format";

/**
 * Sequential single-hue scale; intensity is relative to the largest cell in
 * the matrix so the eye reads structure, not absolute magnitude.
 */
function cellStyle(value: number | null, max: number) {
  if (value === null) return { background: "transparent" };
  const t = max > 0 ? Math.min(1, value / max) : 0;
  const alpha = 0.08 + t * 0.82;
  return { background: `rgb(47 95 214 / ${alpha.toFixed(2)})`, color: t > 0.55 ? "#fff" : "var(--color-fg)" };
}

export function CohortHeatmap({ result }: { result: CohortResult }) {
  const isCurrency = result.measure === "revenue_per_user";
  const max = Math.max(...result.rows.flatMap((r) => r.values.filter((v): v is number => v !== null)), 0);
  return (
    <div className="overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Cohort week</th>
            <th className="num">Users</th>
            {Array.from({ length: result.weeks }).map((_, k) => (
              <th key={k} className="num">
                W{k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row) => (
            <tr key={row.cohort}>
              <td className="whitespace-nowrap">{formatDate(row.cohort, { month: "short", day: "numeric" })}</td>
              <td className="num text-fg-subtle">{formatCompactCount(row.size)}</td>
              {row.values.map((v, k) => (
                <td key={k} className="num p-0">
                  <div className="px-2 py-1.5 text-xs" style={cellStyle(v, max)}>
                    {v === null ? "" : isCurrency ? formatMetric(v, "currency", true) : formatMetric(v, "percent")}
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
