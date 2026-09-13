"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AnomalyInbox } from "@/components/investigations/anomaly-inbox";
import { NewInvestigationDialog } from "@/components/investigations/new-investigation-dialog";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { SegmentedControl } from "@/components/ui/tabs";
import { usePermission } from "@/lib/api/hooks";
import {
  type InvestigationStatus,
  type InvestigationSummary,
  useInvestigations,
} from "@/lib/api/investigations";
import { formatDate, formatDateTime } from "@/lib/format";
import { investigationHref } from "@/lib/links";
import { useUrlState } from "@/lib/url-state";

type ListFilter = "active" | InvestigationStatus | "all";

const ACTIVE: InvestigationStatus[] = ["open", "investigating", "validating"];

function FindingCounts({ counts }: { counts: Record<string, number> }) {
  const items: [string, string][] = [
    ["evidence", "ev"],
    ["hypothesis", "hyp"],
    ["recommendation", "rec"],
  ];
  const present = items.filter(([k]) => (counts[k] ?? 0) > 0);
  if (!present.length) return <span className="text-fg-faint">—</span>;
  return (
    <span className="tabular text-fg-muted inline-flex gap-2 text-xs">
      {present.map(([k, short]) => (
        <span key={k}>
          {counts[k]} {short}
        </span>
      ))}
    </span>
  );
}

function InvestigationRow({ inv }: { inv: InvestigationSummary }) {
  return (
    <tr className="border-border hover:bg-surface border-b last:border-b-0">
      <td className="px-4 py-2.5">
        <Link href={investigationHref(inv.id)} className="text-fg hover:text-accent font-medium">
          {inv.title}
        </Link>
        <div className="text-fg-subtle mt-0.5 text-xs">
          {inv.metric_label}
          {inv.filter_labels.length ? <> · {inv.filter_labels.join(", ")}</> : null}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <StatusBadge status={inv.status} />
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap">
        {formatDate(inv.period_start)} – {formatDate(inv.period_end)}
      </td>
      <td className="px-3 py-2.5">
        <FindingCounts counts={inv.finding_counts} />
      </td>
      <td className="tabular px-3 py-2.5 text-right">
        {inv.open_actions > 0 ? inv.open_actions : <span className="text-fg-faint">—</span>}
      </td>
      <td className="text-fg-muted px-3 py-2.5">{inv.owner.name}</td>
      <td className="text-fg-subtle px-4 py-2.5 text-right whitespace-nowrap">
        {formatDateTime(inv.updated_at)}
      </td>
    </tr>
  );
}

function InvestigationsList() {
  const url = useUrlState();
  const filter = (url.get("status") as ListFilter | null) ?? "active";
  const investigations = useInvestigations(filter === "active" ? "all" : filter);
  const rows = (investigations.data ?? []).filter((i) => filter !== "active" || ACTIVE.includes(i.status));

  return (
    <Panel>
      <PanelHeader
        title="Investigations"
        description="Each investigation tracks one metric movement from observation through hypotheses to a decision."
        actions={
          <SegmentedControl<ListFilter>
            label="Investigation status"
            value={filter}
            onChange={(v) => url.set({ status: v === "active" ? null : v })}
            options={[
              { value: "active", label: "Active" },
              { value: "validating", label: "Validating" },
              { value: "resolved", label: "Resolved" },
              { value: "closed", label: "Closed" },
              { value: "all", label: "All" },
            ]}
          />
        }
      />
      {investigations.isPending ? (
        <PanelBody>
          <TableSkeleton rows={4} cols={6} />
        </PanelBody>
      ) : investigations.isError ? (
        <ErrorState error={investigations.error} onRetry={() => investigations.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No investigations"
          description="Start one from an anomaly above, or create a blank investigation for something you noticed in Analytics."
        />
      ) : (
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
              <th className="px-4 py-2 text-left font-medium">Investigation</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-left font-medium">Period</th>
              <th className="px-3 py-2 text-left font-medium">Findings</th>
              <th className="px-3 py-2 text-right font-medium">Open actions</th>
              <th className="px-3 py-2 text-left font-medium">Owner</th>
              <th className="px-4 py-2 text-right font-medium">Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((inv) => (
              <InvestigationRow key={inv.id} inv={inv} />
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function InvestigationsPage() {
  const canManage = usePermission("manage_investigations");
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader
        title="Investigations"
        description="Observe → investigate → hypothesize. Anomalies land in the inbox; anything worth explaining becomes an investigation with evidence, hypotheses and a decision."
        actions={
          canManage ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" />
              New investigation
            </Button>
          ) : null
        }
      />
      <div className="space-y-5">
        <AnomalyInbox />
        <InvestigationsList />
      </div>
      <NewInvestigationDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

// No page-level Suspense on purpose: the layout already provides the boundary
// `useSearchParams` needs, and a nested one hydrates later than the shell, by
// which point `useMe` has resolved and permission-gated buttons mismatch the
// server HTML.
export default function Page() {
  return <InvestigationsPage />;
}
