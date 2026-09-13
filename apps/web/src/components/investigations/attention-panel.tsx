"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { SeverityDot } from "@/components/investigations/anomaly-inbox";
import { Badge } from "@/components/ui/badge";
import { DeltaText } from "@/components/ui/delta";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useAnomalies } from "@/lib/api/investigations";
import { formatDate, formatMetric, type MetricFormat } from "@/lib/format";
import { investigationHref } from "@/lib/links";

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 } as const;

/** Compact "what's wrong right now" list for the Overview: open + investigating anomalies. */
export function AttentionPanel({ limit = 6 }: { limit?: number }) {
  const anomalies = useAnomalies("all");
  const rows = (anomalies.data ?? [])
    .filter((a) => a.status === "open" || a.status === "investigating")
    .sort(
      (a, b) =>
        (SEVERITY_ORDER[a.severity as keyof typeof SEVERITY_ORDER] ?? 3) -
          (SEVERITY_ORDER[b.severity as keyof typeof SEVERITY_ORDER] ?? 3) ||
        Math.abs(b.zscore) - Math.abs(a.zscore),
    );
  const openCount = rows.filter((a) => a.status === "open").length;

  return (
    <Panel>
      <PanelHeader
        title="Needs attention"
        description="Metric windows the detector flagged and nobody has acted on."
        actions={
          <>
            {anomalies.data ? <Badge tone={openCount ? "warning" : "neutral"}>{openCount} open</Badge> : null}
            <Link
              href="/investigations"
              className="text-accent inline-flex items-center gap-0.5 text-xs hover:underline"
            >
              Inbox
              <ArrowRight className="size-3" />
            </Link>
          </>
        }
      />
      {anomalies.isPending ? (
        <PanelBody>
          <Skeleton className="h-24 w-full" />
        </PanelBody>
      ) : anomalies.isError ? (
        <ErrorState error={anomalies.error} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="Nothing flagged"
          description="Every detected window has been acknowledged or resolved."
          className="py-6"
        />
      ) : (
        <ul className="divide-border divide-y">
          {rows.slice(0, limit).map((a) => {
            const fmt = a.metric_format as MetricFormat;
            const inner = (
              <>
                <SeverityDot severity={a.severity} className="mt-1.5" />
                <div className="min-w-0 flex-1">
                  <div className="text-fg truncate text-[13px]">
                    {a.metric_label} {a.direction === "up" ? "↑" : "↓"}
                    {a.filter_labels.length ? (
                      <span className="text-fg-subtle"> · {a.filter_labels.join(", ")}</span>
                    ) : null}
                  </div>
                  <div className="text-fg-subtle text-xs">
                    since {formatDate(a.period_start)}
                    {a.ongoing ? " · ongoing" : ` · to ${formatDate(a.period_end)}`}
                    {a.status === "investigating" ? " · under investigation" : ""}
                  </div>
                </div>
                <div className="tabular shrink-0 text-right text-xs">
                  <div className="text-fg">{formatMetric(a.actual, fmt)}</div>
                  <DeltaText
                    current={a.actual}
                    previous={a.expected}
                    format={fmt}
                    higherIsBetter={a.higher_is_better}
                  />
                </div>
              </>
            );
            const cls = "flex items-start gap-2.5 px-4 py-2 hover:bg-surface";
            return (
              <li key={a.id}>
                {a.investigation_id ? (
                  <Link href={investigationHref(a.investigation_id)} className={cls}>
                    {inner}
                  </Link>
                ) : (
                  <Link href="/investigations" className={cls}>
                    {inner}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
