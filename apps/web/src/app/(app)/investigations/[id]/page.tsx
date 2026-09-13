"use client";

import { ArrowUpRight, ChevronLeft, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AskAnalystButton } from "@/components/analyst/ask-analyst-button";
import { CommentThread } from "@/components/comments/comment-thread";
import { DecisionDialog } from "@/components/decisions/decision-dialog";
import { TrendChart, type Band, type Marker } from "@/components/charts/trend-chart";
import { SeverityBadge } from "@/components/investigations/anomaly-inbox";
import { FindingsPanel } from "@/components/investigations/findings-panel";
import { RootCausePanel } from "@/components/investigations/root-cause-panel";
import { ActionsPanel, StakeholdersPanel } from "@/components/investigations/side-panels";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeltaText } from "@/components/ui/delta";
import { Select, Textarea } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menu";
import { KeyValue, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ChartSkeleton, ErrorState, Skeleton } from "@/components/ui/states";
import { useAnalyticsMeta, useMetricQuery } from "@/lib/api/analytics";
import { useMe, usePermission } from "@/lib/api/hooks";
import {
  type InvestigationOut,
  type InvestigationStatus,
  useInvestigation,
  useInvestigationMutations,
  useRootCause,
} from "@/lib/api/investigations";
import { formatDate, formatDateTime, formatMetric, type MetricFormat } from "@/lib/format";
import { useDecisions, useReleases } from "@/lib/api/ops";
import { analystHref, decisionHref, exploreHref, releaseHref } from "@/lib/links";

const STATUSES: { value: InvestigationStatus; label: string; help: string }[] = [
  { value: "open", label: "Open", help: "Observed, nobody digging yet" },
  { value: "investigating", label: "Investigating", help: "Gathering evidence and hypotheses" },
  { value: "validating", label: "Validating", help: "Fix or experiment in flight; watching the metric" },
  { value: "resolved", label: "Resolved", help: "Cause understood and decision recorded" },
  {
    value: "closed",
    label: "Closed",
    help: "Closed without resolution (expected behaviour, duplicate, etc.)",
  },
];

function shiftIso(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function minIso(a: string, b: string) {
  return a < b ? a : b;
}

// --------------------------------------------------------------------------- metric panel

function MetricPanel({ inv }: { inv: InvestigationOut }) {
  const meta = useAnalyticsMeta();
  const rc = useRootCause(inv.id);
  const dataEnd = meta.data?.data_end ?? inv.period_end;
  // Show a bit of run-up before the baseline and a week after the period (when the data has it),
  // so the anomaly reads in context rather than filling the whole frame.
  const from = shiftIso(inv.baseline_start, -7);
  const to = minIso(shiftIso(inv.period_end, 7), dataEnd);
  const q = useMetricQuery(
    meta.isSuccess
      ? {
          metric: inv.metric_key,
          date_from: from,
          date_to: to,
          filters: inv.filters,
          granularity: "day",
          limit: 10,
        }
      : null,
  );
  const bands: Band[] = [
    { from: inv.baseline_start, to: inv.baseline_end, label: "Baseline", tone: "neutral" },
    { from: inv.period_start, to: inv.period_end, label: "Period", tone: "danger" },
  ];
  const markers: Marker[] = (rc.data?.releases ?? [])
    .filter((r) => r.release_date >= from && r.release_date <= to)
    .map((r) => ({
      bucket: r.release_date,
      label: `${r.platform} ${r.version}`,
      tone: r.relevance === "strong" ? "danger" : "info",
    }));
  const overall = rc.data?.overall;
  const format =
    (rc.data?.metric.format as MetricFormat | undefined) ??
    (q.data?.metric.format as MetricFormat | undefined) ??
    "number";
  const higherIsBetter = Boolean(rc.data?.metric.higher_is_better ?? q.data?.metric.higher_is_better ?? true);

  return (
    <Panel>
      <PanelHeader
        title={inv.metric_label}
        description={inv.filter_labels.length ? inv.filter_labels.join(" · ") : "Store-wide"}
        actions={
          <>
            {overall ? (
              <div className="tabular flex items-baseline gap-3 text-[13px]">
                <span className="text-fg-muted">{formatMetric(overall.baseline, format)}</span>
                <span className="text-fg-faint">→</span>
                <span className="text-fg font-medium">{formatMetric(overall.period, format)}</span>
                <DeltaText
                  current={overall.period}
                  previous={overall.baseline}
                  format={format}
                  higherIsBetter={higherIsBetter}
                  className="font-medium"
                />
              </div>
            ) : null}
            <Tooltip content="Open in Analytics">
              <Link
                href={exploreHref({ metric: inv.metric_key, filters: inv.filters, from, to })}
                className="text-fg-subtle hover:bg-surface-2 hover:text-fg rounded-sm p-1"
                aria-label="Open in Analytics"
              >
                <ArrowUpRight className="size-4" />
              </Link>
            </Tooltip>
          </>
        }
      />
      <PanelBody>
        {q.isPending || !meta.isSuccess ? (
          <ChartSkeleton height={220} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : (
          <TrendChart
            result={q.data}
            granularity="day"
            height={220}
            bands={bands}
            markers={markers}
            showCompare={false}
          />
        )}
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- decision

function DecisionPanel({ inv, canEdit }: { inv: InvestigationOut; canEdit: boolean }) {
  const { update } = useInvestigationMutations(inv.id);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(inv.decision);
  const [resolve, setResolve] = useState(inv.status !== "resolved" && inv.status !== "closed");
  const supported = inv.findings.filter((f) => f.kind === "hypothesis" && f.state === "supported");
  const recommendations = inv.findings.filter((f) => f.kind === "recommendation");
  const evidence = inv.findings.filter((f) => f.kind === "evidence");
  const canLog = usePermission("manage_decisions");
  const logged = useDecisions({ investigation_id: inv.id });
  const [logging, setLogging] = useState(false);

  if (!editing) {
    return (
      <Panel>
        <PanelHeader
          title="Decision"
          description={
            inv.resolved_at
              ? `Recorded ${formatDateTime(inv.resolved_at)}`
              : "What we concluded and what we are doing about it."
          }
          actions={
            <>
              {inv.decision && canLog && logged.isSuccess && logged.data.length === 0 ? (
                <Button size="sm" onClick={() => setLogging(true)}>
                  Add to decision log
                </Button>
              ) : null}
              {logged.data?.length ? (
                <Link href={decisionHref(logged.data[0].id)} className="text-accent text-xs hover:underline">
                  In decision log →
                </Link>
              ) : null}
              {canEdit ? (
                <Button size="sm" onClick={() => setEditing(true)}>
                  {inv.decision ? "Edit" : "Write decision"}
                </Button>
              ) : null}
            </>
          }
        />
        <DecisionDialog
          open={logging}
          existing={null}
          onClose={() => setLogging(false)}
          prefill={{
            title: inv.title,
            context: inv.observation,
            evidence: [
              ...supported.map((h) => `Supported: ${h.title}`),
              ...evidence.map((e) => e.title),
            ].join("\n"),
            decision: inv.decision,
            expected_impact: recommendations.map((r) => r.title).join("\n"),
            investigation_id: inv.id,
            release_id: inv.release?.id ?? null,
          }}
        />
        <PanelBody>
          {inv.decision ? (
            <p className="text-fg text-[13px] leading-6 whitespace-pre-line">{inv.decision}</p>
          ) : (
            <p className="text-fg-subtle text-xs">
              No decision yet.
              {supported.length === 0 ? " No hypothesis is marked supported; the cause is still open." : ""}
              {supported.length > 0 && recommendations.length === 0
                ? " A hypothesis is supported but nothing is recommended yet."
                : ""}
            </p>
          )}
        </PanelBody>
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHeader
        title="Decision"
        description="Say what was true, what caused it, and what happens next. This is what people read in six months."
      />
      <PanelBody>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            update.mutate(
              { decision: draft, ...(resolve ? { status: "resolved" as const } : {}) },
              { onSuccess: () => setEditing(false) },
            );
          }}
        >
          {supported.length || recommendations.length ? (
            <div className="text-fg-subtle bg-surface rounded-md px-3 py-2 text-xs">
              {supported.length ? <p>Supported: {supported.map((h) => h.title).join("; ")}</p> : null}
              {recommendations.length ? (
                <p>Recommended: {recommendations.map((r) => r.title).join("; ")}</p>
              ) : null}
            </div>
          ) : null}
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="min-h-32"
            autoFocus
            aria-label="Decision"
          />
          <div className="flex items-center justify-between gap-3">
            {inv.status !== "resolved" && inv.status !== "closed" ? (
              <label className="text-fg-muted flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  className="accent-accent"
                  checked={resolve}
                  onChange={(e) => setResolve(e.target.checked)}
                />
                Mark investigation resolved and close linked anomaly
              </label>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="sm"
                loading={update.isPending}
                disabled={!draft.trim()}
              >
                Save decision
              </Button>
            </div>
          </div>
        </form>
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- details

function DetailsPanel({ inv, canManage }: { inv: InvestigationOut; canManage: boolean }) {
  const releases = useReleases();
  const { update } = useInvestigationMutations(inv.id);
  const items: { label: string; value: React.ReactNode }[] = [
    { label: "Owner", value: inv.owner.name },
    { label: "Metric", value: inv.metric_label },
    {
      label: "Scope",
      value: inv.filter_labels.length ? (
        <span className="flex flex-wrap gap-1">
          {inv.filter_labels.map((l) => (
            <span key={l} className="text-2xs bg-surface-2 text-fg-muted rounded-sm px-1 font-mono">
              {l}
            </span>
          ))}
        </span>
      ) : (
        <span className="text-fg-subtle">Store-wide</span>
      ),
    },
    { label: "Period", value: `${formatDate(inv.period_start)} – ${formatDate(inv.period_end)}` },
    { label: "Baseline", value: `${formatDate(inv.baseline_start)} – ${formatDate(inv.baseline_end)}` },
    { label: "Opened", value: formatDateTime(inv.created_at) },
  ];
  if (inv.anomaly) {
    items.push({
      label: "Anomaly",
      value: (
        <span className="flex flex-wrap items-center gap-1.5">
          <SeverityBadge severity={inv.anomaly.severity} />
          <span className="tabular text-fg-muted text-xs">
            z {inv.anomaly.zscore > 0 ? "+" : ""}
            {inv.anomaly.zscore.toFixed(1)}
          </span>
          {inv.anomaly.ongoing ? <Badge tone="warning">ongoing</Badge> : null}
        </span>
      ),
    });
  }
  // Releases are candidate causes; linking one records the call so the release page shows it.
  const nearby = (releases.data ?? []).filter(
    (r) => r.release_date <= inv.period_end && r.release_date >= shiftIso(inv.baseline_start, -14),
  );
  items.push({
    label: "Release",
    value: canManage ? (
      <Select
        aria-label="Linked release"
        value={inv.release?.id ?? ""}
        onChange={(e) => update.mutate({ release_id: e.target.value ? Number(e.target.value) : null })}
        className="h-7 w-full max-w-64 text-xs"
      >
        <option value="">Not attributed to a release</option>
        {[
          ...nearby,
          ...(inv.release && !nearby.some((r) => r.id === inv.release?.id) ? [inv.release] : []),
        ].map((r) => (
          <option key={r.id} value={r.id}>
            {r.platform} {r.version} · {formatDate(r.release_date)}
          </option>
        ))}
      </Select>
    ) : inv.release ? (
      <Link href={releaseHref(inv.release.id)} className="text-accent hover:underline">
        {inv.release.platform} {inv.release.version} · {formatDate(inv.release.release_date)}
      </Link>
    ) : (
      <span className="text-fg-subtle">—</span>
    ),
  });
  if (inv.release && canManage) {
    items.push({
      label: "",
      value: (
        <Link href={releaseHref(inv.release.id)} className="text-accent text-xs hover:underline">
          Open {inv.release.version} →
        </Link>
      ),
    });
  }
  if (inv.experiment) {
    items.push({ label: "Experiment", value: `${inv.experiment.name} (${inv.experiment.status})` });
  }
  return (
    <Panel>
      <PanelHeader title="Details" />
      <PanelBody>
        <KeyValue items={items} />
        {inv.observation ? (
          <div className="border-border mt-3 border-t pt-3">
            <h3 className="text-2xs text-fg-subtle mb-1 uppercase">Observation</h3>
            <p className="text-fg-muted text-xs leading-5 whitespace-pre-line">{inv.observation}</p>
          </div>
        ) : null}
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- page

function InvestigationDetail({ id }: { id: number }) {
  const router = useRouter();
  const me = useMe();
  const canManage = usePermission("manage_investigations");
  const inv = useInvestigation(id);
  const { update, remove } = useInvestigationMutations(id);

  if (inv.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16" />
        <Skeleton className="h-64" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (inv.isError) return <ErrorState error={inv.error} onRetry={() => inv.refetch()} />;
  const data = inv.data;
  // Mirrors the API's rule: admins and PMs edit anything; analysts and owners edit theirs.
  const role = me.data?.role;
  const privileged = role === "admin" || role === "pm";
  const canEdit = privileged || (canManage && (role === "analyst" || me.data?.id === data.owner.id));
  const canDelete = privileged || me.data?.id === data.owner.id;

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link href="/investigations" className="hover:text-fg inline-flex items-center gap-0.5">
            <ChevronLeft className="size-3" />
            Investigations
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {data.title}
            <StatusBadge status={data.status} />
          </span>
        }
        description={
          <>
            {data.metric_label}
            {data.filter_labels.length ? <> · {data.filter_labels.join(" · ")}</> : null}
            {" · "}
            {formatDate(data.period_start)} – {formatDate(data.period_end)} vs{" "}
            {formatDate(data.baseline_start)} – {formatDate(data.baseline_end)}
          </>
        }
        actions={
          <>
            <AskAnalystButton
              href={analystHref({
                investigationId: data.id,
                metric: data.metric_key,
                filters: data.filters,
                from: data.period_start,
                to: data.period_end,
                q: `Why did ${data.metric_label.toLowerCase()} change?`,
              })}
            />
            {canEdit ? (
              <>
                <Tooltip content={STATUSES.find((s) => s.value === data.status)?.help ?? ""}>
                  <Select
                    aria-label="Status"
                    value={data.status}
                    onChange={(e) => update.mutate({ status: e.target.value as InvestigationStatus })}
                    className="w-36"
                  >
                    {STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </Select>
                </Tooltip>
                {canDelete ? (
                  <Tooltip content="Delete investigation">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Delete investigation"
                      loading={remove.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete "${data.title}"? Findings and actions go with it; the anomaly returns to the inbox.`,
                          )
                        ) {
                          remove.mutate(data.id, { onSuccess: () => router.push("/investigations") });
                        }
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </Tooltip>
                ) : null}
              </>
            ) : null}
          </>
        }
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-5">
          <MetricPanel inv={data} />
          <RootCausePanel inv={data} canEdit={canEdit} />
          <FindingsPanel inv={data} canEdit={canEdit} />
          <DecisionPanel inv={data} canEdit={canEdit} />
        </div>
        <div className="space-y-5">
          <DetailsPanel inv={data} canManage={canManage} />
          <ActionsPanel inv={data} canEdit={canEdit} />
          <StakeholdersPanel inv={data} canEdit={canEdit} />
          <CommentThread entityType="investigation" entityId={data.id} />
        </div>
      </div>
    </>
  );
}

export default function Page() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  if (!Number.isFinite(id)) return <ErrorState error={new Error("Invalid investigation id")} />;
  return <InvestigationDetail id={id} />;
}
