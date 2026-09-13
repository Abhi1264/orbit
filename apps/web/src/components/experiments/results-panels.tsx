"use client";

import { AlertTriangle, Check as CheckIcon, RefreshCw } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { SERIES_COLORS } from "@/components/charts/trend-chart";
import { Badge, type BadgeTone, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KeyValue, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Tooltip } from "@/components/ui/menu";
import type {
  Check,
  ExperimentOut,
  ExperimentResults,
  MetricReadout,
  Recommendation,
  SegmentReadout,
  VariantComparison,
} from "@/lib/api/experiments";
import { formatDate, formatMetric, formatRelative, type MetricFormat, niceDomain } from "@/lib/format";
import { cn } from "@/lib/utils";

const DIRECTION_TONE: Record<VariantComparison["direction"], BadgeTone> = {
  better: "success",
  worse: "danger",
  flat: "neutral",
};

function pValue(p: number) {
  if (p < 0.001) return "<0.001";
  return p.toFixed(3);
}

/**
 * A 95% interval on the relative lift drawn against a shared zero line. Colour
 * follows business direction, not sign, so a falling return rate reads green.
 */
function IntervalBar({
  c,
  higherIsBetter,
  scale,
}: {
  c: VariantComparison;
  higherIsBetter: boolean;
  scale: number;
}) {
  if (c.rel_ci_low == null || c.rel_ci_high == null || c.rel_diff == null) return null;
  const W = 160;
  const H = 14;
  const x = (v: number) => W / 2 + (v / scale) * (W / 2 - 4);
  const good = c.direction === "flat" ? null : c.direction === "better";
  const color =
    good === null ? "var(--color-fg-faint)" : good ? "var(--color-success)" : "var(--color-danger)";
  void higherIsBetter;
  return (
    <svg width={W} height={H} className="block" aria-hidden>
      <line x1={W / 2} x2={W / 2} y1={0} y2={H} stroke="var(--color-border-strong)" strokeDasharray="2 2" />
      <line
        x1={x(Math.max(c.rel_ci_low, -scale))}
        x2={x(Math.min(c.rel_ci_high, scale))}
        y1={H / 2}
        y2={H / 2}
        stroke={color}
        strokeWidth={3}
        strokeLinecap="round"
        opacity={0.55}
      />
      <circle cx={x(Math.max(-scale, Math.min(scale, c.rel_diff)))} cy={H / 2} r={3} fill={color} />
    </svg>
  );
}

function MetricReadoutTable({
  m,
  control,
  spec,
}: {
  m: MetricReadout;
  control: string;
  spec: ExperimentOut;
}) {
  const fmt = m.format as MetricFormat;
  const bounds = m.comparisons.flatMap((c) => [Math.abs(c.rel_ci_low ?? 0), Math.abs(c.rel_ci_high ?? 0)]);
  const scale = Math.max(spec.min_relative_effect * 2, ...bounds, 0.02) * 1.1;
  const variantName = (key: string) => spec.variants.find((v) => v.key === key)?.name ?? key;
  return (
    <div className="border-border overflow-hidden rounded-sm border">
      <div className="border-border bg-surface flex items-center justify-between gap-3 border-b px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span className="text-fg text-[13px] font-medium">{m.label}</span>
          <Badge tone={m.role === "primary" ? "accent" : "neutral"}>{m.role}</Badge>
          <span className="text-fg-subtle text-xs">
            {m.higher_is_better ? "higher is better" : "lower is better"}
          </span>
        </div>
        {m.role === "primary" ? (
          <span className="text-fg-subtle text-xs">
            target lift ±{formatRelative(spec.min_relative_effect, 0).replace("+", "")}
          </span>
        ) : null}
      </div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
            <th className="px-3 py-1.5 text-left font-medium">Variant</th>
            <th className="px-3 py-1.5 text-right font-medium">Users</th>
            <th className="px-3 py-1.5 text-right font-medium">Value</th>
            <th className="px-3 py-1.5 text-right font-medium">Lift</th>
            <th className="px-3 py-1.5 text-left font-medium">95% interval on lift</th>
            <th className="px-3 py-1.5 text-right font-medium">p</th>
          </tr>
        </thead>
        <tbody>
          {m.variants.map((v, i) => {
            const c = m.comparisons.find((x) => x.variant === v.key);
            const isControl = v.key === control;
            return (
              <tr key={v.key} className="border-border border-b last:border-b-0">
                <td className="px-3 py-2">
                  <span className="flex items-center gap-2 whitespace-nowrap">
                    <span
                      className="inline-block size-2 shrink-0 rounded-full"
                      style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }}
                      aria-hidden
                    />
                    <span className="text-fg">{variantName(v.key)}</span>
                    {isControl ? <Badge>control</Badge> : null}
                  </span>
                </td>
                <td className="tabular px-3 py-2 text-right">{v.users.toLocaleString("en-US")}</td>
                <td className="tabular px-3 py-2 text-right whitespace-nowrap">
                  <span className="text-fg font-medium">{formatMetric(v.value, fmt)}</span>
                  {v.ci_low != null && v.ci_high != null ? (
                    <span className="text-fg-faint block text-xs">
                      {formatMetric(v.ci_low, fmt)} – {formatMetric(v.ci_high, fmt)}
                    </span>
                  ) : null}
                </td>
                {isControl || !c ? (
                  <td colSpan={3} className="text-fg-faint px-3 py-2 text-xs">
                    {isControl ? "baseline" : "—"}
                  </td>
                ) : (
                  <>
                    <td className="tabular px-3 py-2 text-right whitespace-nowrap">
                      <span
                        className={cn(
                          "font-medium",
                          c.direction === "better"
                            ? "text-success"
                            : c.direction === "worse"
                              ? "text-danger"
                              : "text-fg",
                        )}
                      >
                        {c.rel_diff != null ? formatRelative(c.rel_diff) : "—"}
                      </span>
                      {fmt === "percent" ? (
                        <span className="text-fg-faint block text-xs">
                          {c.abs_diff > 0 ? "+" : ""}
                          {(c.abs_diff * 100).toFixed(2)} pp
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <IntervalBar c={c} higherIsBetter={m.higher_is_better} scale={scale} />
                        <span className="tabular text-fg-subtle text-xs whitespace-nowrap">
                          {c.rel_ci_low != null ? formatRelative(c.rel_ci_low) : "?"} to{" "}
                          {c.rel_ci_high != null ? formatRelative(c.rel_ci_high) : "?"}
                        </span>
                      </div>
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      <span className="text-fg">{pValue(c.p_value)}</span>
                      <Badge tone={DIRECTION_TONE[c.direction]} className="mt-0.5 ml-auto block w-fit">
                        {c.direction === "flat" ? "n.s." : c.direction}
                      </Badge>
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ReadoutPanel({
  exp,
  results,
  isFetching,
  onRefresh,
}: {
  exp: ExperimentOut;
  results: ExperimentResults;
  isFetching: boolean;
  onRefresh: () => void;
}) {
  return (
    <Panel>
      <PanelHeader
        title="Readout"
        description={`Users are analysed under their first exposure; outcomes counted through ${formatDate(results.as_of)}. Intervals are 95%, at the user level.`}
        actions={
          <Tooltip content="Recompute">
            <Button
              size="icon"
              variant="ghost"
              aria-label="Recompute"
              onClick={onRefresh}
              loading={isFetching}
            >
              <RefreshCw className="size-3.5" />
            </Button>
          </Tooltip>
        }
      />
      <PanelBody className="space-y-3">
        {results.metrics.map((m) => (
          <MetricReadoutTable key={m.metric_key} m={m} control={results.control} spec={exp} />
        ))}
        {results.notes.length ? (
          <ul className="text-fg-subtle space-y-0.5 text-xs">
            {results.notes.map((n) => (
              <li key={n}>· {n}</li>
            ))}
          </ul>
        ) : null}
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- recommendation

function CheckRow({ c }: { c: Check }) {
  return (
    <li className="flex gap-2 text-xs">
      {c.passed ? (
        <CheckIcon className="text-success mt-0.5 size-3.5 shrink-0" aria-label="Passed" />
      ) : (
        <AlertTriangle className="text-warning mt-0.5 size-3.5 shrink-0" aria-label="Failed" />
      )}
      <span>
        <span className="text-fg font-medium">{c.name}</span>
        <span className="text-fg-muted"> — {c.detail}</span>
      </span>
    </li>
  );
}

export function RecommendationPanel({
  rec,
  recorded,
  actions,
}: {
  rec: Recommendation;
  recorded: { decision: string; reason: string; by: string | null; at: string | null } | null;
  actions?: React.ReactNode;
}) {
  const failed = rec.checks.filter((c) => !c.passed).length;
  return (
    <Panel>
      <PanelHeader
        title="Recommendation"
        description="Rule-based, from the checks below. It is input to the decision, not the decision."
        actions={actions}
      />
      <PanelBody className="space-y-3">
        <div className="flex items-start gap-3">
          <StatusBadge status={rec.decision} className="mt-0.5 px-2 py-0.5 text-xs" />
          <div className="min-w-0">
            <p className="text-fg text-[13px] font-medium">{rec.headline}</p>
            <p className="text-fg-subtle mt-0.5 text-xs">
              {rec.confidence} confidence · {rec.checks.length - failed}/{rec.checks.length} checks passed
            </p>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <h3 className="text-2xs text-fg-subtle mb-1 font-medium uppercase">Why</h3>
            <ul className="text-fg-muted space-y-1 text-xs">
              {rec.reasons.map((r) => (
                <li key={r}>· {r}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-2xs text-fg-subtle mb-1 font-medium uppercase">Risks</h3>
            {rec.risks.length ? (
              <ul className="text-fg-muted space-y-1 text-xs">
                {rec.risks.map((r) => (
                  <li key={r}>· {r}</li>
                ))}
              </ul>
            ) : (
              <p className="text-fg-faint text-xs">None flagged.</p>
            )}
          </div>
        </div>
        <div>
          <h3 className="text-2xs text-fg-subtle mb-1 font-medium uppercase">Validity checks</h3>
          <ul className="space-y-1">
            {rec.checks.map((c) => (
              <CheckRow key={c.name} c={c} />
            ))}
          </ul>
        </div>
        {recorded ? (
          <div className="border-border bg-surface rounded-sm border px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-2xs text-fg-subtle font-medium uppercase">Recorded decision</span>
              <StatusBadge status={recorded.decision} />
              {recorded.decision !== rec.decision ? (
                <Badge tone="warning">differs from recommendation</Badge>
              ) : null}
            </div>
            <p className="text-fg mt-1 text-[13px]">{recorded.reason}</p>
            {recorded.by ? (
              <p className="text-fg-subtle mt-0.5 text-xs">
                {recorded.by}
                {recorded.at ? ` · ${formatDate(recorded.at)}` : ""}
              </p>
            ) : null}
          </div>
        ) : null}
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- exposure & power

export function ExposurePanel({ exp, results }: { exp: ExperimentOut; results: ExperimentResults }) {
  const ex = results.exposure;
  const p = results.power;
  const variantName = (key: string) => exp.variants.find((v) => v.key === key)?.name ?? key;
  return (
    <Panel>
      <PanelHeader title="Exposure and power" />
      <PanelBody className="space-y-3">
        <div>
          <div className="text-fg tabular text-lg font-semibold">
            {ex.total_users.toLocaleString("en-US")}
          </div>
          <div className="text-fg-subtle text-xs">
            users exposed over {ex.days_running} days
            {ex.first_exposure ? ` · ${formatDate(ex.first_exposure)}` : ""}
            {ex.last_exposure ? ` – ${formatDate(ex.last_exposure)}` : ""}
          </div>
        </div>
        <div className="space-y-1">
          {Object.entries(ex.by_variant).map(([key, n], i) => {
            const share = ex.total_users ? n / ex.total_users : 0;
            const expected = ex.srm?.expected[key];
            return (
              <div key={key} className="text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-fg flex min-w-0 items-center gap-1.5">
                    <span
                      className="inline-block size-2 shrink-0 rounded-full"
                      style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }}
                      aria-hidden
                    />
                    <span className="truncate">{variantName(key)}</span>
                  </span>
                  <span className="tabular text-fg-muted whitespace-nowrap">
                    {n.toLocaleString("en-US")} · {(share * 100).toFixed(1)}%
                    {expected != null ? (
                      <span className="text-fg-faint">
                        {" "}
                        / {((expected / ex.total_users) * 100).toFixed(0)}%
                      </span>
                    ) : null}
                  </span>
                </div>
                <div className="bg-surface-2 mt-0.5 h-1 overflow-hidden rounded-sm">
                  <div
                    className="h-full"
                    style={{ width: `${share * 100}%`, background: SERIES_COLORS[i % SERIES_COLORS.length] }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <KeyValue
          items={[
            {
              label: "Sample ratio",
              value: ex.srm ? (
                <span className={cn("tabular", ex.srm.mismatch ? "text-danger font-medium" : "")}>
                  {ex.srm.mismatch ? "Mismatch" : "OK"} · χ² p = {pValue(ex.srm.p_value)}
                </span>
              ) : (
                "—"
              ),
            },
            {
              label: "Cross-exposed",
              value: <span className="tabular">{ex.contaminated_users.toLocaleString("en-US")} users</span>,
            },
            {
              label: "Detectable now",
              value:
                p.detectable_effect_now != null ? (
                  <span className="tabular">
                    ±{(p.detectable_effect_now * 100).toFixed(1)}% relative
                    <span className="text-fg-subtle">
                      {" "}
                      (target ±{(exp.min_relative_effect * 100).toFixed(0)}%)
                    </span>
                  </span>
                ) : (
                  "—"
                ),
            },
            {
              label: "Needed / variant",
              value:
                p.required_n_per_variant != null ? (
                  <span className="tabular">
                    {p.required_n_per_variant.toLocaleString("en-US")}
                    <span className="text-fg-subtle">
                      {" "}
                      · have {p.smallest_variant_n.toLocaleString("en-US")}
                    </span>
                  </span>
                ) : (
                  "—"
                ),
            },
            ...(p.projected_days_to_power != null
              ? [
                  {
                    label: "Time to power",
                    value: (
                      <span className="tabular">
                        ~{p.projected_days_to_power} more days at current traffic
                      </span>
                    ),
                  },
                ]
              : []),
          ]}
        />
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- timeline

export function TimelinePanel({ exp, results }: { exp: ExperimentOut; results: ExperimentResults }) {
  const primary = results.metrics[0];
  const fmt = primary.format as MetricFormat;
  const variants = exp.variants.map((v) => v.key);
  const data = results.timeline.map((t) => ({
    day: t.day,
    ...Object.fromEntries(variants.map((v) => [v, t.cumulative[v] ?? null])),
    ...Object.fromEntries(variants.map((v) => [`${v}__n`, t.users[v] ?? 0])),
  }));
  const values = results.timeline.flatMap((t) => variants.map((v) => t.cumulative[v] ?? NaN));
  const axis = niceDomain(values, fmt === "percent");
  const variantName = (key: string) => exp.variants.find((v) => v.key === key)?.name ?? key;
  return (
    <Panel>
      <PanelHeader
        title={`${primary.label} over time`}
        description="Cumulative value per variant since the first exposure. Early days swing; a result that only appears at the end deserves suspicion."
      />
      <PanelBody>
        {data.length < 2 ? (
          <p className="text-fg-subtle py-6 text-center text-xs">Not enough days to chart yet.</p>
        ) : (
          <LineChart
            responsive
            data={data}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
            style={{ width: "100%", height: 220 }}
            accessibilityLayer
          >
            <CartesianGrid vertical={false} strokeDasharray="0" />
            <XAxis
              dataKey="day"
              tickFormatter={(v) => formatDate(String(v))}
              tickLine={false}
              axisLine={{ stroke: "var(--color-border)" }}
              minTickGap={24}
              tickMargin={8}
            />
            <YAxis
              tickFormatter={(v) => formatMetric(Number(v), fmt, true)}
              tickLine={false}
              axisLine={false}
              width={56}
              domain={axis.domain}
              ticks={axis.ticks}
            />
            {exp.end_date && exp.end_date !== results.as_of ? (
              <ReferenceLine
                x={exp.end_date}
                stroke="var(--color-fg-faint)"
                strokeDasharray="3 3"
                label={{
                  value: "ended",
                  position: "insideTopLeft",
                  fontSize: 10,
                  fill: "var(--color-fg-subtle)",
                }}
              />
            ) : null}
            <ChartTooltip
              cursor={{ stroke: "var(--color-border-strong)" }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0]?.payload as Record<string, number | string | null>;
                return (
                  <div className="border-border bg-bg rounded-sm border px-2.5 py-2 text-xs shadow-sm">
                    <div className="text-fg-subtle mb-1">{formatDate(String(label))}</div>
                    {variants.map((v, i) => (
                      <div key={v} className="flex items-center justify-between gap-4">
                        <span className="text-fg-muted flex items-center gap-1.5">
                          <span
                            className="inline-block h-0.5 w-3"
                            style={{ background: SERIES_COLORS[i % SERIES_COLORS.length] }}
                          />
                          {variantName(v)}
                        </span>
                        <span className="tabular text-fg font-medium">
                          {formatMetric(row[v] as number | null, fmt)}
                          <span className="text-fg-faint">
                            {" "}
                            · n={Number(row[`${v}__n`] ?? 0).toLocaleString("en-US")}
                          </span>
                        </span>
                      </div>
                    ))}
                  </div>
                );
              }}
            />
            {variants.map((v, i) => (
              <Line
                key={v}
                type="monotone"
                dataKey={v}
                stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        )}
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- segments

export function SegmentsPanel({ segments, primary }: { segments: SegmentReadout[]; primary: MetricReadout }) {
  const fmt = primary.format as MetricFormat;
  return (
    <Panel>
      <PanelHeader
        title="Segments"
        description="Primary metric by the user's attribute at first exposure. Exploratory: with several segments some will look significant by chance."
      />
      {segments.map((s) => (
        <table key={s.dimension} className="w-full text-[13px]">
          <thead>
            <tr className="text-2xs text-fg-subtle border-border bg-surface border-y uppercase">
              <th className="px-4 py-1.5 text-left font-medium">{s.label}</th>
              <th className="px-3 py-1.5 text-right font-medium">Users</th>
              <th className="px-3 py-1.5 text-right font-medium">Control</th>
              <th className="px-3 py-1.5 text-right font-medium">Treatment</th>
              <th className="px-3 py-1.5 text-right font-medium">Lift</th>
              <th className="px-4 py-1.5 text-right font-medium">p</th>
            </tr>
          </thead>
          <tbody>
            {s.rows.map((r) => {
              const good =
                r.rel_diff == null || !r.significant
                  ? null
                  : primary.higher_is_better
                    ? r.rel_diff > 0
                    : r.rel_diff < 0;
              return (
                <tr key={r.segment} className="border-border border-b last:border-b-0">
                  <td className="text-fg px-4 py-1.5">{r.segment}</td>
                  <td className="tabular px-3 py-1.5 text-right">{r.users.toLocaleString("en-US")}</td>
                  <td className="tabular px-3 py-1.5 text-right">{formatMetric(r.control, fmt)}</td>
                  <td className="tabular px-3 py-1.5 text-right">{formatMetric(r.treatment, fmt)}</td>
                  <td
                    className={cn(
                      "tabular px-3 py-1.5 text-right",
                      good === null ? "text-fg-muted" : good ? "text-success" : "text-danger",
                    )}
                  >
                    {r.rel_diff != null ? formatRelative(r.rel_diff) : "—"}
                  </td>
                  <td className="tabular text-fg-muted px-4 py-1.5 text-right">
                    {r.p_value != null ? pValue(r.p_value) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ))}
    </Panel>
  );
}
