"use client";

import { ChevronLeft, FileText, Gavel, Play, Square, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { CommentThread } from "@/components/comments/comment-thread";
import { DecisionDialog, MemoDialog } from "@/components/experiments/decision-dialogs";
import {
  ExposurePanel,
  ReadoutPanel,
  RecommendationPanel,
  SegmentsPanel,
  TimelinePanel,
} from "@/components/experiments/results-panels";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/menu";
import { KeyValue, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ChartSkeleton, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import {
  type ExperimentOut,
  useExperiment,
  useExperimentMutations,
  useExperimentResults,
} from "@/lib/api/experiments";
import { useMe, usePermission } from "@/lib/api/hooks";
import { formatDate, formatDateTime } from "@/lib/format";

function DesignPanel({ exp }: { exp: ExperimentOut }) {
  const guardrails = exp.guardrail_metrics;
  return (
    <Panel>
      <PanelHeader
        title="Design"
        description="Frozen at start. Changing it mid-flight would be a new experiment."
      />
      <PanelBody>
        <KeyValue
          items={[
            { label: "Owner", value: exp.owner.name },
            { label: "Primary", value: exp.primary_metric_label },
            {
              label: "Guardrails",
              value: guardrails.length ? (
                <span className="flex flex-wrap gap-1">
                  {guardrails.map((g) => (
                    <span key={g} className="text-2xs bg-surface-2 text-fg-muted rounded-sm px-1 font-mono">
                      {g}
                    </span>
                  ))}
                </span>
              ) : (
                <span className="text-fg-subtle">None</span>
              ),
            },
            {
              label: "Audience",
              value: exp.filter_labels.length ? (
                <span className="flex flex-wrap gap-1">
                  {exp.filter_labels.map((l) => (
                    <span key={l} className="text-2xs bg-surface-2 text-fg-muted rounded-sm px-1 font-mono">
                      {l}
                    </span>
                  ))}
                </span>
              ) : (
                <span className="text-fg-subtle">Everyone</span>
              ),
            },
            { label: "Traffic", value: `${exp.traffic_percent}%` },
            {
              label: "Variants",
              value: (
                <ul className="space-y-0.5">
                  {exp.variants.map((v) => (
                    <li key={v.key} className="flex items-baseline gap-1.5">
                      <span className="text-fg">{v.name}</span>
                      <span className="text-fg-faint font-mono text-xs">{v.key}</span>
                      <span className="tabular text-fg-subtle text-xs">{v.weight}</span>
                      {v.is_control ? <Badge>control</Badge> : null}
                    </li>
                  ))}
                </ul>
              ),
            },
            {
              label: "Window",
              value: `${formatDate(exp.start_date)} – ${exp.end_date ? formatDate(exp.end_date) : "ongoing"}`,
            },
            {
              label: "Rules",
              value: (
                <span className="text-fg-muted text-xs">
                  detect ±{(exp.min_relative_effect * 100).toFixed(0)}% · ≥
                  {exp.min_sample_per_variant.toLocaleString("en-US")} users/variant · ≥
                  {exp.min_duration_days} days
                </span>
              ),
            },
            {
              label: "Assignment",
              value: (
                <span className="text-fg-muted text-xs">
                  {exp.has_exposure_events
                    ? "Exposure events in the stream"
                    : "Deterministic hash (retroactive)"}
                </span>
              ),
            },
            { label: "Created", value: formatDateTime(exp.created_at) },
          ]}
        />
      </PanelBody>
    </Panel>
  );
}

function ExperimentDetail({ id }: { id: number }) {
  const router = useRouter();
  const me = useMe();
  const canManage = usePermission("manage_experiments");
  const canDecide = usePermission("decide_experiments");
  const exp = useExperiment(id);
  const started = exp.data ? exp.data.status !== "draft" : false;
  const results = useExperimentResults(id, started);
  const { update, remove } = useExperimentMutations(id);
  const [deciding, setDeciding] = useState(false);
  const [memoOpen, setMemoOpen] = useState(false);

  if (exp.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-4 w-2/3" />
        <ChartSkeleton />
      </div>
    );
  }
  if (exp.isError) return <ErrorState error={exp.error} onRetry={() => exp.refetch()} />;
  const data = exp.data;
  const role = me.data?.role;
  const canEdit = canManage && (role === "admin" || role === "pm" || me.data?.id === data.owner.id);

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link href="/experiments" className="hover:text-fg inline-flex items-center gap-0.5">
            <ChevronLeft className="size-3" />
            Experiments
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {data.name}
            <StatusBadge status={data.status} className="px-2 py-0.5 text-xs" />
            {data.decision ? <StatusBadge status={data.decision} className="px-2 py-0.5 text-xs" /> : null}
          </span>
        }
        description={data.hypothesis}
        actions={
          <>
            {started ? (
              <Button variant="secondary" onClick={() => setMemoOpen(true)}>
                <FileText className="size-3.5" />
                Decision memo
              </Button>
            ) : null}
            {canEdit && data.status === "draft" ? (
              <>
                <Tooltip content="Only drafts can be deleted">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="Delete experiment"
                    onClick={() => {
                      if (confirm("Delete this draft experiment?"))
                        remove.mutate(undefined, { onSuccess: () => router.push("/experiments") });
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </Tooltip>
                <Button
                  variant="primary"
                  onClick={() => update.mutate({ status: "running" })}
                  loading={update.isPending}
                >
                  <Play className="size-3.5" />
                  Start
                </Button>
              </>
            ) : null}
            {canEdit && data.status === "running" ? (
              <Button
                variant="secondary"
                onClick={() => update.mutate({ status: "completed" })}
                loading={update.isPending}
              >
                <Square className="size-3.5" />
                End
              </Button>
            ) : null}
            {canDecide && started ? (
              <Button variant="primary" onClick={() => setDeciding(true)}>
                <Gavel className="size-3.5" />
                {data.decision ? "Revise decision" : "Record decision"}
              </Button>
            ) : null}
          </>
        }
      />
      {update.isError ? <ErrorState error={update.error} className="py-2" /> : null}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-5">
          {!started ? (
            <Panel>
              <PanelBody className="text-fg-subtle py-10 text-center text-xs">
                This experiment is a draft. Start it to begin assigning users and reading results.
              </PanelBody>
            </Panel>
          ) : results.isPending ? (
            <>
              <Panel>
                <PanelBody>
                  <TableSkeleton rows={3} cols={5} />
                </PanelBody>
              </Panel>
              <ChartSkeleton />
            </>
          ) : results.isError ? (
            <ErrorState error={results.error} onRetry={() => results.refetch()} />
          ) : (
            <>
              <RecommendationPanel
                rec={results.data.recommendation}
                recorded={
                  data.decision
                    ? {
                        decision: data.decision,
                        reason: data.decision_reason,
                        by: data.decided_by?.name ?? null,
                        at: data.decided_at ?? null,
                      }
                    : null
                }
              />
              <ReadoutPanel
                exp={data}
                results={results.data}
                isFetching={results.isFetching}
                onRefresh={() => results.refetch()}
              />
              <TimelinePanel exp={data} results={results.data} />
              {results.data.segments.length ? (
                <SegmentsPanel segments={results.data.segments} primary={results.data.metrics[0]} />
              ) : null}
            </>
          )}
        </div>
        <div className="space-y-5">
          {started && results.data ? <ExposurePanel exp={data} results={results.data} /> : null}
          <DesignPanel exp={data} />
          <CommentThread entityType="experiment" entityId={data.id} />
        </div>
      </div>
      <DecisionDialog
        exp={data}
        rec={results.data?.recommendation}
        open={deciding}
        onClose={() => setDeciding(false)}
      />
      <MemoDialog exp={data} open={memoOpen} onClose={() => setMemoOpen(false)} />
    </>
  );
}

export default function Page() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  if (!Number.isFinite(id)) return <ErrorState error={new Error("Invalid experiment id")} />;
  return <ExperimentDetail id={id} />;
}
