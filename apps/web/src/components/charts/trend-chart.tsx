"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";

import type { MetricQueryResult } from "@/lib/api/analytics";
import { formatDate, formatMetric, type MetricFormat, niceDomain } from "@/lib/format";

export const SERIES_COLORS = [
  "var(--color-series-1)",
  "var(--color-series-2)",
  "var(--color-series-3)",
  "var(--color-series-4)",
  "var(--color-series-5)",
  "var(--color-series-6)",
  "#64748b",
  "#a16207",
];

type Row = Record<string, string | number | null>;

/**
 * Series whose denominator is under 2% of the largest are too noisy to plot as
 * a line; they stay in the table flagged as low volume.
 */
export function isLowVolume(s: MetricQueryResult["series"][number], all: MetricQueryResult["series"]) {
  const vol = (x: MetricQueryResult["series"][number]) => x.total.denominator ?? x.total.numerator;
  const max = Math.max(...all.map(vol));
  return all.length > 1 && max > 0 && vol(s) < max * 0.02;
}

export interface Marker {
  bucket: string;
  label: string;
  tone?: "neutral" | "danger" | "info";
}

function pivot(result: MetricQueryResult, granularity: string | null | undefined) {
  const rows = new Map<string, Row>();
  const ensure = (bucket: string) => {
    let r = rows.get(bucket);
    if (!r) {
      r = { bucket };
      rows.set(bucket, r);
    }
    return r;
  };
  result.series.forEach((s) => {
    (s.points ?? []).forEach((p) => {
      ensure(p.bucket)[s.key] = p.value;
    });
  });
  // Compare series is aligned by index so it overlays the primary period.
  const primary = result.series[0];
  if (primary?.compare_points?.length) {
    const buckets = (primary.points ?? []).map((p) => p.bucket);
    primary.compare_points.forEach((p, i) => {
      if (buckets[i]) ensure(buckets[i])[`${primary.key}__compare`] = p.value;
    });
  }
  const sorted = [...rows.values()].sort((a, b) => String(a.bucket).localeCompare(String(b.bucket)));
  void granularity;
  return sorted;
}

function tick(bucket: string, granularity: string | null | undefined) {
  if (granularity === "hour") {
    const d = new Date(bucket);
    return `${formatDate(d)} ${String(d.getHours()).padStart(2, "0")}h`;
  }
  return formatDate(bucket);
}

export function TrendChart({
  result,
  granularity,
  height = 260,
  markers = [],
  showCompare = true,
  variant = "line",
}: {
  result: MetricQueryResult;
  granularity: string | null | undefined;
  height?: number;
  markers?: Marker[];
  showCompare?: boolean;
  variant?: "line" | "bar";
}) {
  const format = result.metric.format as MetricFormat;
  const data = pivot(result, granularity);
  const primary = result.series[0];
  const hasCompare = showCompare && !!primary?.compare_points?.length && result.series.length === 1;
  const Chart = variant === "bar" ? BarChart : LineChart;
  const plotted = result.series.filter((s) => !isLowVolume(s, result.series));
  const tight = variant === "line" && (format === "percent" || result.metric.key === "aov" || format === "days");
  const axis = tight
    ? niceDomain(
        [
          ...plotted.flatMap((s) => (s.points ?? []).map((p) => p.value ?? NaN)),
          ...(hasCompare ? primary.compare_points!.map((p) => p.value ?? NaN) : []),
        ],
        format === "percent",
      )
    : null;

  return (
    <Chart
      responsive
      data={data}
      margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
      style={{ width: "100%", height }}
      accessibilityLayer
    >
      <CartesianGrid vertical={false} strokeDasharray="0" />
      <XAxis
        dataKey="bucket"
        tickFormatter={(v) => tick(String(v), granularity)}
        tickLine={false}
        axisLine={{ stroke: "var(--color-border)" }}
        minTickGap={24}
        tickMargin={8}
      />
      <YAxis
        tickFormatter={(v) => formatMetric(Number(v), format, true)}
        tickLine={false}
        axisLine={false}
        width={56}
        domain={axis ? axis.domain : [0, "auto"]}
        ticks={axis?.ticks}
        allowDecimals
      />
      <Tooltip
        cursor={{ stroke: "var(--color-border-strong)" }}
        content={({ active, payload, label }) => {
          if (!active || !payload?.length) return null;
          return (
            <div className="rounded-sm border border-border bg-bg px-2.5 py-2 text-xs shadow-sm">
              <div className="mb-1 text-fg-subtle">{tick(String(label), granularity)}</div>
              {payload.map((p) => {
                const key = String(p.dataKey);
                const isCompare = key.endsWith("__compare");
                const series = result.series.find((s) => s.key === key.replace("__compare", ""));
                return (
                  <div key={key} className="flex items-center justify-between gap-4">
                    <span className="flex items-center gap-1.5 text-fg-muted">
                      <span
                        className="inline-block h-0.5 w-3"
                        style={{
                          background: String(p.color),
                          borderTop: isCompare ? "2px dashed" : undefined,
                          borderColor: String(p.color),
                          height: isCompare ? 0 : undefined,
                        }}
                      />
                      {isCompare ? "Previous period" : series?.label ?? key}
                    </span>
                    <span className="tabular font-medium text-fg">
                      {formatMetric(p.value as number | null, format)}
                    </span>
                  </div>
                );
              })}
            </div>
          );
        }}
      />
      {markers.map((m) => (
        <ReferenceLine
          key={`${m.bucket}-${m.label}`}
          x={m.bucket}
          stroke={m.tone === "danger" ? "var(--color-danger)" : m.tone === "info" ? "var(--color-info)" : "var(--color-fg-faint)"}
          strokeDasharray="3 3"
          label={{ value: m.label, position: "insideTopLeft", fontSize: 10, fill: "var(--color-fg-subtle)" }}
        />
      ))}
      {hasCompare ? (
        <Line
          type="monotone"
          dataKey={`${primary.key}__compare`}
          stroke="var(--color-fg-faint)"
          strokeDasharray="4 3"
          strokeWidth={1.25}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
      ) : null}
      {plotted.map((s, i) =>
        variant === "bar" ? (
          <Bar
            key={s.key}
            dataKey={s.key}
            stackId="a"
            fill={SERIES_COLORS[i % SERIES_COLORS.length]}
            isAnimationActive={false}
            maxBarSize={28}
          />
        ) : (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
            connectNulls
          />
        ),
      )}
    </Chart>
  );
}
