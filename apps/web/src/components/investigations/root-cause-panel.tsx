"use client";

import { ArrowUpRight, ChevronDown, Lightbulb, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeltaText } from "@/components/ui/delta";
import { Tooltip } from "@/components/ui/menu";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState, Skeleton } from "@/components/ui/states";
import type { Filter } from "@/lib/api/analytics";
import {
  type Contribution,
  type InvestigationOut,
  type RootCauseAnalysis,
  type RootCauseCandidate,
  useInvestigationMutations,
  useRootCause,
} from "@/lib/api/investigations";
import {
  formatCompactCount,
  formatDate,
  formatMetric,
  formatRelative,
  type MetricFormat,
} from "@/lib/format";
import { exploreHref } from "@/lib/links";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<RootCauseCandidate["kind"], string> = {
  segment: "Segment",
  release: "Release",
  experiment: "Experiment",
  mix_shift: "Mix shift",
};

const CONFIDENCE_TONE = { high: "success", medium: "warning", low: "neutral" } as const;

function pct(v: number | null | undefined, digits = 0) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

/** Share of the overall change accounted for; clipped so a 240% over-explanation still reads sensibly. */
function ExplainedBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-fg-faint text-xs">n/a</span>;
  const clipped = Math.max(0, Math.min(1, value));
  return (
    <Tooltip content={`Explains ${pct(value)} of the overall change`}>
      <span className="inline-flex items-center gap-2">
        <span className="bg-surface-2 relative h-1.5 w-20 overflow-hidden rounded-full">
          <span
            className={cn("absolute inset-y-0 left-0 rounded-full", value < 0 ? "bg-fg-faint" : "bg-accent")}
            style={{ width: `${clipped * 100}%` }}
          />
        </span>
        <span className="tabular text-fg-muted w-10 text-right text-xs">{pct(value)}</span>
      </span>
    </Tooltip>
  );
}

function ContributionTable({
  rows,
  format,
  higherIsBetter,
  additive = true,
}: {
  rows: Contribution[];
  format: MetricFormat;
  higherIsBetter: boolean;
  additive?: boolean;
}) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
          <th className="py-1.5 pr-3 text-left font-medium">Segment</th>
          <th className="py-1.5 pr-3 text-right font-medium">Baseline</th>
          <th className="py-1.5 pr-3 text-right font-medium">Period</th>
          <th className="py-1.5 pr-3 text-right font-medium">Change</th>
          <th className="py-1.5 pr-3 text-right font-medium">Share</th>
          {additive ? <th className="py-1.5 text-right font-medium">Explains</th> : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.key} className="border-border border-b last:border-b-0">
            <td className="py-1.5 pr-3">
              <span className="text-fg">{c.label}</span>
              {c.is_new ? (
                <Badge tone="info" className="ml-1.5">
                  new
                </Badge>
              ) : null}
            </td>
            <td className="tabular text-fg-muted py-1.5 pr-3 text-right">
              {formatMetric(c.baseline, format)}
            </td>
            <td className="tabular text-fg py-1.5 pr-3 text-right">{formatMetric(c.period, format)}</td>
            <td className="py-1.5 pr-3 text-right">
              <DeltaText
                current={c.period}
                previous={c.baseline}
                format={format}
                higherIsBetter={higherIsBetter}
              />
            </td>
            <td className="tabular text-fg-muted py-1.5 pr-3 text-right whitespace-nowrap">
              {pct(c.share_baseline)}
              {Math.abs(c.share_period - c.share_baseline) >= 0.005 ? <> → {pct(c.share_period)}</> : null}
            </td>
            {additive ? (
              <td className="py-1.5 text-right">
                <span className="tabular text-fg-muted">{pct(c.explained)}</span>
              </td>
            ) : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CandidateCard({
  c,
  analysis,
  inv,
  existing,
  canEdit,
}: {
  c: RootCauseCandidate;
  analysis: RootCauseAnalysis;
  inv: InvestigationOut;
  existing: Set<string>;
  canEdit: boolean;
}) {
  const [open, setOpen] = useState(false);
  const { addFinding } = useInvestigationMutations(inv.id);
  const format = analysis.metric.format as MetricFormat;
  const higherIsBetter = Boolean(analysis.metric.higher_is_better);
  const filters = [...inv.filters, ...(c.filters ?? [])] as Filter[];
  const added = existing.has(c.title.toLowerCase());

  return (
    <li className="border-border rounded-md border">
      <div className="flex items-start gap-3 px-3 py-2.5">
        <span className="tabular text-fg-subtle mt-0.5 w-4 shrink-0 text-right text-xs">{c.rank}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-fg text-[13px] font-medium">{c.title}</span>
            <Badge tone="neutral">{KIND_LABEL[c.kind]}</Badge>
            <Badge tone={CONFIDENCE_TONE[c.confidence]}>{c.confidence} confidence</Badge>
          </div>
          <p className="text-fg-muted mt-1 text-xs leading-5">{c.summary}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            {c.kind !== "release" && c.kind !== "experiment" ? <ExplainedBar value={c.explained} /> : null}
            {c.filters?.length ? (
              <Link
                href={exploreHref({
                  metric: inv.metric_key,
                  filters,
                  from: inv.baseline_start,
                  to: inv.period_end,
                  breakdown: c.drill_dimension,
                })}
                className="text-accent inline-flex items-center gap-0.5 text-xs hover:underline"
              >
                Explore
                <ArrowUpRight className="size-3" />
              </Link>
            ) : null}
            {c.drill?.length ? (
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                aria-expanded={open}
                className="text-fg-muted hover:text-fg inline-flex items-center gap-0.5 text-xs"
              >
                <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
                {open ? "Hide" : "Show"} breakdown by {c.drill_dimension?.replace(/_/g, " ")}
              </button>
            ) : null}
          </div>
        </div>
        {canEdit ? (
          <Tooltip content={added ? "Already tracked as a hypothesis" : "Add as a hypothesis to test"}>
            <Button
              size="sm"
              variant={added ? "ghost" : "secondary"}
              disabled={added}
              loading={addFinding.isPending}
              onClick={() =>
                addFinding.mutate({
                  kind: "hypothesis",
                  title: c.title,
                  body: c.summary,
                  confidence: c.confidence,
                  state: "proposed",
                  data: { candidate: c, source: "root_cause" },
                })
              }
            >
              <Lightbulb className="size-3.5" />
              {added ? "Hypothesis added" : "Add hypothesis"}
            </Button>
          </Tooltip>
        ) : null}
      </div>
      {open && c.drill?.length ? (
        <div className="border-border bg-surface border-t px-3 py-2">
          <ContributionTable rows={c.drill} format={format} higherIsBetter={higherIsBetter} />
        </div>
      ) : null}
    </li>
  );
}

function OverallChange({ analysis }: { analysis: RootCauseAnalysis }) {
  const o = analysis.overall;
  const format = analysis.metric.format as MetricFormat;
  const higherIsBetter = Boolean(analysis.metric.higher_is_better);
  const denom = (v: number | null) => (v === null ? null : formatCompactCount(v));
  return (
    <dl className="grid grid-cols-3 gap-4 text-[13px]">
      <div>
        <dt className="text-2xs text-fg-subtle uppercase">
          Baseline · {formatDate(analysis.baseline.start)} – {formatDate(analysis.baseline.end)}
        </dt>
        <dd className="tabular text-fg mt-0.5 text-base font-medium">{formatMetric(o.baseline, format)}</dd>
        <dd className="text-fg-subtle text-xs">
          {formatCompactCount(o.baseline_numerator)}
          {o.baseline_denominator !== null ? ` / ${denom(o.baseline_denominator)}` : ""}
        </dd>
      </div>
      <div>
        <dt className="text-2xs text-fg-subtle uppercase">
          Period · {formatDate(analysis.period.start)} – {formatDate(analysis.period.end)}
        </dt>
        <dd className="tabular text-fg mt-0.5 text-base font-medium">{formatMetric(o.period, format)}</dd>
        <dd className="text-fg-subtle text-xs">
          {formatCompactCount(o.period_numerator)}
          {o.period_denominator !== null ? ` / ${denom(o.period_denominator)}` : ""}
        </dd>
      </div>
      <div>
        <dt className="text-2xs text-fg-subtle uppercase">Change</dt>
        <dd className="mt-0.5 text-base font-medium">
          <DeltaText
            current={o.period}
            previous={o.baseline}
            format={format}
            higherIsBetter={higherIsBetter}
          />
        </dd>
        <dd className="text-fg-subtle text-xs">
          {o.rel_change !== null ? `${formatRelative(o.rel_change)} relative` : "no baseline"}
        </dd>
      </div>
    </dl>
  );
}

function SupportingTable({ s }: { s: RootCauseAnalysis["supporting"][number] }) {
  type Row = {
    key: string;
    label: string;
    baseline_count: number;
    period_count: number;
    baseline_share: number;
    period_share: number;
  };
  const rows = s.rows as unknown as Row[];
  return (
    <div>
      <h4 className="text-fg mb-1.5 text-xs font-medium">{s.title}</h4>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
            <th className="py-1 pr-3 text-left font-medium">Reason</th>
            <th className="py-1 pr-3 text-right font-medium">Baseline</th>
            <th className="py-1 pr-3 text-right font-medium">Period</th>
            <th className="py-1 text-right font-medium">Share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const shift = r.period_share - r.baseline_share;
            return (
              <tr key={r.key} className="border-border border-b last:border-b-0">
                <td className="text-fg py-1 pr-3">{r.label}</td>
                <td className="tabular text-fg-muted py-1 pr-3 text-right">
                  {formatCompactCount(r.baseline_count)}
                </td>
                <td className="tabular text-fg py-1 pr-3 text-right">{formatCompactCount(r.period_count)}</td>
                <td className="tabular py-1 text-right whitespace-nowrap">
                  <span className="text-fg-muted">{pct(r.baseline_share)} → </span>
                  <span className={cn(shift > 0.05 ? "text-danger font-medium" : "text-fg")}>
                    {pct(r.period_share)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function RootCausePanel({ inv, canEdit }: { inv: InvestigationOut; canEdit: boolean }) {
  const rc = useRootCause(inv.id);
  const [showDims, setShowDims] = useState(false);
  const existing = new Set(
    inv.findings.filter((f) => f.kind === "hypothesis").map((f) => f.title.toLowerCase()),
  );

  return (
    <Panel>
      <PanelHeader
        title="Root-cause analysis"
        description="Deterministic decomposition of the change: which segments moved (rate effect), which grew or shrank (mix effect), and what shipped or was running at the time. Candidates are evidence to test, not conclusions."
        actions={
          <Tooltip content="Recompute">
            <Button
              size="icon"
              variant="ghost"
              aria-label="Recompute"
              onClick={() => rc.refetch()}
              loading={rc.isFetching}
            >
              <RefreshCw className="size-3.5" />
            </Button>
          </Tooltip>
        }
      />
      {rc.isPending ? (
        <PanelBody className="space-y-3">
          <Skeleton className="h-14" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </PanelBody>
      ) : rc.isError ? (
        <ErrorState error={rc.error} onRetry={() => rc.refetch()} />
      ) : (
        <>
          <PanelBody className="border-border border-b">
            <OverallChange analysis={rc.data} />
          </PanelBody>
          <PanelBody className="space-y-4">
            <section>
              <h3 className="text-2xs text-fg-subtle mb-2 uppercase">
                Candidates{" "}
                <span className="text-fg-faint normal-case">
                  · ranked by how much of the change they account for
                </span>
              </h3>
              {rc.data.candidates.length ? (
                <ol className="space-y-2">
                  {rc.data.candidates.map((c) => (
                    <CandidateCard
                      key={`${c.kind}-${c.rank}`}
                      c={c}
                      analysis={rc.data}
                      inv={inv}
                      existing={existing}
                      canEdit={canEdit}
                    />
                  ))}
                </ol>
              ) : (
                <p className="text-fg-subtle text-xs">
                  No segment stands out; the movement looks broad-based.
                </p>
              )}
            </section>

            {rc.data.notes.length ? (
              <ul className="text-fg-subtle space-y-0.5 text-xs">
                {rc.data.notes.map((n) => (
                  <li key={n}>· {n}</li>
                ))}
              </ul>
            ) : null}

            {rc.data.supporting.length ? (
              <section className="grid gap-4 md:grid-cols-2">
                {rc.data.supporting.map((s) => (
                  <SupportingTable key={s.title} s={s} />
                ))}
              </section>
            ) : null}

            {rc.data.dimensions.length ? (
              <section>
                <button
                  type="button"
                  onClick={() => setShowDims((v) => !v)}
                  aria-expanded={showDims}
                  className="text-fg-muted hover:text-fg inline-flex items-center gap-1 text-xs font-medium"
                >
                  <ChevronDown className={cn("size-3.5 transition-transform", showDims && "rotate-180")} />
                  All dimension breakdowns ({rc.data.dimensions.length})
                </button>
                {showDims ? (
                  <div className="mt-3 space-y-4">
                    {rc.data.dimensions.map((d) => (
                      <div key={d.dimension}>
                        <div className="mb-1.5 flex items-baseline justify-between">
                          <h4 className="text-fg text-xs font-medium">{d.label}</h4>
                          <span className="text-fg-subtle text-2xs">
                            {d.additive
                              ? `concentration ${pct(d.concentration)}`
                              : "event-level dimension; rates only"}
                          </span>
                        </div>
                        <ContributionTable
                          rows={d.contributions}
                          format={rc.data.metric.format as MetricFormat}
                          higherIsBetter={Boolean(rc.data.metric.higher_is_better)}
                          additive={d.additive}
                        />
                      </div>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}
          </PanelBody>
        </>
      )}
    </Panel>
  );
}
