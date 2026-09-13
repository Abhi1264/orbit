"use client";

import { isLowVolume, SERIES_COLORS } from "@/components/charts/trend-chart";
import { Badge } from "@/components/ui/badge";
import { DeltaText } from "@/components/ui/delta";
import type { MetricQueryResult } from "@/lib/api/analytics";
import { formatCompactCount, formatMetric, type MetricFormat } from "@/lib/format";
import { cn } from "@/lib/utils";

export function BreakdownTable({
  result,
  onSelect,
  selected,
}: {
  result: MetricQueryResult;
  onSelect?: (key: string) => void;
  selected?: string | null;
}) {
  const format = result.metric.format as MetricFormat;
  const isRatio = result.metric.is_proportion || result.metric.key === "aov";
  const maxValue = Math.max(...result.series.map((s) => s.total.value ?? 0), 0);
  const hasCompare = result.series.some((s) => s.compare_total);
  const volumeLabel = isRatio ? "Denominator" : null;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th className="w-1/3">{result.interpretation.breakdown as string}</th>
          <th className="w-1/3" aria-label="Relative value" />
          <th className="num">{result.metric.label}</th>
          {hasCompare ? <th className="num">Change</th> : null}
          {volumeLabel ? <th className="num">{volumeLabel}</th> : null}
        </tr>
      </thead>
      <tbody>
        {result.series.map((s, i) => {
          const value = s.total.value ?? 0;
          const width = maxValue > 0 ? Math.max(2, (value / maxValue) * 100) : 0;
          return (
            <tr
              key={s.key}
              className={cn(onSelect && "cursor-pointer", selected === s.key && "bg-accent-soft")}
              onClick={onSelect ? () => onSelect(s.key) : undefined}
            >
              <td>
                <span className="flex items-center gap-2">
                  <span className="inline-block size-2 rounded-full" style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }} />
                  <span className="truncate">{s.label}</span>
                  {isLowVolume(s, result.series) ? <Badge>low volume</Badge> : null}
                </span>
              </td>
              <td>
                <div className="h-1.5 w-full rounded-full bg-surface-2">
                  <div className="h-1.5 rounded-full" style={{ width: `${width}%`, background: SERIES_COLORS[i % SERIES_COLORS.length] }} />
                </div>
              </td>
              <td className="num font-medium">{formatMetric(s.total.value, format)}</td>
              {hasCompare ? (
                <td className="num">
                  <DeltaText
                    current={s.total.value}
                    previous={s.compare_total?.value ?? null}
                    format={format}
                    higherIsBetter={result.metric.higher_is_better}
                  />
                </td>
              ) : null}
              {volumeLabel ? <td className="num text-fg-subtle">{formatCompactCount(s.total.denominator ?? 0)}</td> : null}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
