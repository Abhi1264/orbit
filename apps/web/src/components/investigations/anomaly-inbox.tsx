"use client";

import { ArrowRight, ArrowUpRight, Check, EyeOff, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { NewInvestigationDialog } from "@/components/investigations/new-investigation-dialog";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeltaText } from "@/components/ui/delta";
import { SegmentedControl } from "@/components/ui/tabs";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { Tooltip } from "@/components/ui/menu";
import { usePermission } from "@/lib/api/hooks";
import {
  type AnomalyOut,
  type AnomalyStatus,
  useAnomalies,
  useAnomalyMutations,
} from "@/lib/api/investigations";
import { formatDate, formatMetric, type MetricFormat } from "@/lib/format";
import { exploreHref, investigationHref } from "@/lib/links";
import { cn } from "@/lib/utils";

type InboxFilter = "open" | "acknowledged" | "investigating" | "resolved" | "all";

function windowLabel(a: AnomalyOut) {
  const start = formatDate(a.period_start);
  if (a.period_start === a.period_end) return start;
  return `${start} – ${formatDate(a.period_end)}`;
}

function daysBetween(a: string, b: string) {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000) + 1;
}

export function AnomalyInbox({ compact = false }: { compact?: boolean }) {
  const [filter, setFilter] = useState<InboxFilter>("open");
  const anomalies = useAnomalies(filter === "all" ? "all" : (filter as AnomalyStatus));
  const { setStatus, detect } = useAnomalyMutations();
  const canManage = usePermission("manage_investigations");
  const [investigating, setInvestigating] = useState<AnomalyOut | null>(null);

  const rows = anomalies.data ?? [];
  const ongoing = rows.filter((a) => a.ongoing).length;

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            Anomaly inbox
            {anomalies.data ? (
              <span className="text-fg-subtle text-xs font-normal">
                {rows.length} {filter === "all" ? "" : filter} · {ongoing} ongoing
              </span>
            ) : null}
          </span>
        }
        description="Daily series compared with a trailing 28-day baseline (robust z-score, weekday-adjusted). A window stays open until someone acknowledges it or the investigation resolves."
        actions={
          <>
            <SegmentedControl<InboxFilter>
              label="Anomaly status"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "open", label: "Open" },
                { value: "acknowledged", label: "Acknowledged" },
                { value: "investigating", label: "Investigating" },
                { value: "resolved", label: "Resolved" },
                { value: "all", label: "All" },
              ]}
            />
            {canManage ? (
              <Tooltip content="Re-run detection against the dataset's last day">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => detect.mutate()}
                  loading={detect.isPending}
                  aria-label="Run detection"
                >
                  <RefreshCw className="size-3.5" />
                  Detect
                </Button>
              </Tooltip>
            ) : null}
          </>
        }
      />
      {anomalies.isPending ? (
        <PanelBody>
          <TableSkeleton rows={6} cols={6} />
        </PanelBody>
      ) : anomalies.isError ? (
        <ErrorState error={anomalies.error} onRetry={() => anomalies.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={filter === "open" ? "Nothing open" : "No anomalies here"}
          description={
            filter === "open"
              ? "Every detected window has been acknowledged or is under investigation."
              : "Try a different status filter."
          }
        />
      ) : (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
              <th className="px-4 py-2 text-left font-medium">Signal</th>
              <th className="px-3 py-2 text-left font-medium">Window</th>
              <th className="px-3 py-2 text-right font-medium">Expected</th>
              <th className="px-3 py-2 text-right font-medium">Actual</th>
              <th className="px-3 py-2 text-right font-medium">Change</th>
              <th className="px-3 py-2 text-right font-medium">z</th>
              {compact ? null : <th className="px-3 py-2 text-left font-medium">Status</th>}
              <th className="px-4 py-2 text-right font-medium">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const fmt = a.metric_format as MetricFormat;
              const days = daysBetween(a.period_start, a.period_end);
              return (
                <tr key={a.id} className="border-border hover:bg-surface border-b last:border-b-0">
                  <td className="px-4 py-2.5">
                    <div className="flex items-start gap-2">
                      <SeverityDot severity={a.severity} />
                      <div className="min-w-0">
                        <div className="text-fg font-medium">
                          {a.metric_label}{" "}
                          <span className="text-fg-subtle font-normal">
                            {a.direction === "up" ? "↑" : "↓"}
                          </span>
                        </div>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {a.filter_labels.length ? (
                            a.filter_labels.map((l) => (
                              <span
                                key={l}
                                className="text-2xs text-fg-muted bg-surface-2 rounded-sm px-1 font-mono"
                              >
                                {l}
                              </span>
                            ))
                          ) : (
                            <span className="text-2xs text-fg-subtle">store-wide</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <div className="text-fg">{windowLabel(a)}</div>
                    <div className="text-fg-subtle text-xs">
                      {days} day{days === 1 ? "" : "s"}
                      {a.ongoing ? (
                        <>
                          {" · "}
                          <span className="text-warning font-medium">ongoing</span>
                        </>
                      ) : null}
                    </div>
                  </td>
                  <td className="tabular text-fg-muted px-3 py-2.5 text-right">
                    {formatMetric(a.expected, fmt)}
                  </td>
                  <td className="tabular text-fg px-3 py-2.5 text-right font-medium">
                    {formatMetric(a.actual, fmt)}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <DeltaText
                      current={a.actual}
                      previous={a.expected}
                      format={fmt}
                      higherIsBetter={a.higher_is_better}
                    />
                  </td>
                  <td className="tabular text-fg-muted px-3 py-2.5 text-right">
                    {a.zscore > 0 ? "+" : ""}
                    {a.zscore.toFixed(1)}
                  </td>
                  {compact ? null : (
                    <td className="px-3 py-2.5">
                      <StatusBadge status={a.status} />
                    </td>
                  )}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center justify-end gap-1">
                      <Tooltip content="Explore in Analytics">
                        <Link
                          href={exploreHref({
                            metric: a.metric_key,
                            filters: a.filters,
                            from: shiftIso(a.period_start, -28),
                            to: a.period_end,
                          })}
                          className="text-fg-subtle hover:bg-surface-2 hover:text-fg rounded-sm p-1"
                          aria-label="Explore in Analytics"
                        >
                          <ArrowUpRight className="size-3.5" />
                        </Link>
                      </Tooltip>
                      {a.investigation_id ? (
                        <Link
                          href={investigationHref(a.investigation_id)}
                          className="text-accent hover:bg-accent-soft inline-flex h-7 items-center gap-1 rounded-sm px-2 text-xs font-medium"
                        >
                          Investigation
                          <ArrowRight className="size-3" />
                        </Link>
                      ) : canManage ? (
                        <>
                          {a.status === "open" ? (
                            <Tooltip content="Acknowledge: seen, not acting yet">
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label="Acknowledge"
                                onClick={() => setStatus.mutate({ id: a.id, status: "acknowledged" })}
                              >
                                <Check className="size-3.5" />
                              </Button>
                            </Tooltip>
                          ) : null}
                          {a.status !== "resolved" ? (
                            <Tooltip content="Dismiss as expected behaviour">
                              <Button
                                size="icon"
                                variant="ghost"
                                aria-label="Dismiss"
                                onClick={() => setStatus.mutate({ id: a.id, status: "resolved" })}
                              >
                                <EyeOff className="size-3.5" />
                              </Button>
                            </Tooltip>
                          ) : null}
                          <Button size="sm" onClick={() => setInvestigating(a)}>
                            Investigate
                          </Button>
                        </>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <NewInvestigationDialog
        open={investigating !== null}
        onClose={() => setInvestigating(null)}
        seed={investigating ? { anomaly: investigating } : undefined}
      />
    </Panel>
  );
}

function shiftIso(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function SeverityDot({ severity, className }: { severity: string; className?: string }) {
  return (
    <Tooltip content={`${severity} severity`}>
      <span
        aria-label={`${severity} severity`}
        className={cn(
          "mt-1.5 inline-block size-2 shrink-0 rounded-full",
          severity === "high" ? "bg-danger" : severity === "medium" ? "bg-warning" : "bg-fg-faint",
          className,
        )}
      />
    </Tooltip>
  );
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge tone={severity === "high" ? "danger" : severity === "medium" ? "warning" : "neutral"}>
      {severity}
    </Badge>
  );
}
