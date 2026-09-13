"use client";

import { Fragment } from "react";

import { SERIES_COLORS } from "@/components/charts/trend-chart";
import type { FunnelResult } from "@/lib/api/analytics";
import { formatCompactCount, formatMetric } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Side-by-side funnel bars. Each step shows sessions as a bar scaled to the
 * first step of its own series, so segments with different volumes compare
 * on shape rather than size.
 */
export function FunnelChart({ result }: { result: FunnelResult }) {
  const steps = result.steps;
  const series = result.series;
  if (!series.length) return null;

  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-160 gap-x-3"
        style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}
      >
        {steps.map((_, i) => {
          const label = series[0].steps[i]?.label ?? steps[i];
          return (
            <div key={steps[i]} className="min-w-0">
              <div className="border-border mb-2 flex items-baseline justify-between gap-2 border-b pb-1.5">
                <span className="text-fg truncate text-xs font-medium">{label}</span>
                <span className="text-2xs text-fg-subtle">step {i + 1}</span>
              </div>
              <div className="flex h-36 items-end gap-1.5">
                {series.map((s, si) => {
                  const step = s.steps[i];
                  const first = s.steps[0]?.sessions ?? 0;
                  const pct = first ? step.sessions / first : 0;
                  return (
                    <div
                      key={s.key}
                      className="flex h-full flex-1 flex-col justify-end"
                      title={`${s.label}: ${step.sessions} sessions`}
                    >
                      <div
                        className="w-full rounded-t-sm"
                        style={{
                          height: `${Math.max(1, pct * 100)}%`,
                          background: SERIES_COLORS[si % SERIES_COLORS.length],
                        }}
                      />
                    </div>
                  );
                })}
              </div>
              <div className="mt-2 space-y-1">
                {series.map((s, si) => {
                  const step = s.steps[i];
                  return (
                    <div key={s.key} className="flex items-baseline justify-between gap-2 text-xs">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span
                          className="inline-block size-1.5 shrink-0 rounded-full"
                          style={{ background: SERIES_COLORS[si % SERIES_COLORS.length] }}
                        />
                        <span className="tabular font-medium">{formatCompactCount(step.sessions)}</span>
                      </span>
                      <span
                        className={cn(
                          "tabular text-fg-subtle",
                          i > 0 &&
                            step.step_conversion !== null &&
                            step.step_conversion !== undefined &&
                            step.step_conversion < 0.5 &&
                            "text-warning",
                        )}
                      >
                        {i === 0 ? "" : formatMetric(step.step_conversion ?? null, "percent")}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FunnelTable({ result }: { result: FunnelResult }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Step</th>
          {result.series.map((s) => (
            <th key={s.key} className="num" colSpan={3}>
              {s.label}
            </th>
          ))}
        </tr>
        <tr>
          <th />
          {result.series.map((s) => (
            <Fragment key={s.key}>
              <th className="num">Sessions</th>
              <th className="num">Step conv.</th>
              <th className="num">Overall</th>
            </Fragment>
          ))}
        </tr>
      </thead>
      <tbody>
        {result.steps.map((ev, i) => (
          <tr key={ev}>
            <td>{result.series[0]?.steps[i]?.label ?? ev}</td>
            {result.series.map((s) => {
              const step = s.steps[i];
              return (
                <Fragment key={s.key}>
                  <td className="num">{formatMetric(step.sessions, "count")}</td>
                  <td className="num">
                    {i === 0 ? "—" : formatMetric(step.step_conversion ?? null, "percent")}
                  </td>
                  <td className="num text-fg-subtle">
                    {formatMetric(step.overall_conversion ?? null, "percent")}
                  </td>
                </Fragment>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
