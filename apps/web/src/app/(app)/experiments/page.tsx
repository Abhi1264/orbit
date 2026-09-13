"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { NewExperimentDialog } from "@/components/experiments/new-experiment-dialog";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { SegmentedControl } from "@/components/ui/tabs";
import { type ExperimentStatus, type ExperimentSummary, useExperiments } from "@/lib/api/experiments";
import { usePermission } from "@/lib/api/hooks";
import { formatDate } from "@/lib/format";
import { experimentHref } from "@/lib/links";
import { useUrlState } from "@/lib/url-state";

type ListFilter = ExperimentStatus | "all";

function ExperimentRow({ exp }: { exp: ExperimentSummary }) {
  return (
    <tr className="border-border hover:bg-surface border-b last:border-b-0">
      <td className="px-4 py-2.5">
        <Link href={experimentHref(exp.id)} className="text-fg hover:text-accent font-medium">
          {exp.name}
        </Link>
        <div className="text-fg-subtle mt-0.5 font-mono text-xs">{exp.key}</div>
      </td>
      <td className="px-3 py-2.5">
        <StatusBadge status={exp.status} />
      </td>
      <td className="px-3 py-2.5">
        <span className="text-fg">{exp.primary_metric_label}</span>
        {exp.guardrail_metrics.length ? (
          <span className="text-fg-subtle text-xs"> · {exp.guardrail_metrics.length} guardrails</span>
        ) : null}
      </td>
      <td className="tabular px-3 py-2.5 whitespace-nowrap">
        {formatDate(exp.start_date)} – {exp.end_date ? formatDate(exp.end_date) : "ongoing"}
      </td>
      <td className="tabular text-fg-muted px-3 py-2.5 text-right">
        {exp.variant_count} · {exp.traffic_percent}%
      </td>
      <td className="px-3 py-2.5">
        {exp.decision ? <StatusBadge status={exp.decision} /> : <span className="text-fg-faint">—</span>}
      </td>
      <td className="text-fg-muted px-4 py-2.5">{exp.owner.name}</td>
    </tr>
  );
}

function ExperimentsPage() {
  const url = useUrlState();
  const filter = (url.get("status") as ListFilter | null) ?? "all";
  const experiments = useExperiments(filter);
  const canManage = usePermission("manage_experiments");
  const [creating, setCreating] = useState(false);
  const rows = experiments.data ?? [];

  return (
    <>
      <PageHeader
        title="Experiments"
        description="Hypothesize → experiment → decide. Every experiment names one primary metric and the guardrails it must not hurt; results are read at the user level with the decision rules written down up front."
        actions={
          canManage ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" />
              New experiment
            </Button>
          ) : null
        }
      />
      <Panel>
        <PanelHeader
          title="All experiments"
          actions={
            <SegmentedControl<ListFilter>
              label="Experiment status"
              value={filter}
              onChange={(v) => url.set({ status: v === "all" ? null : v })}
              options={[
                { value: "all", label: "All" },
                { value: "running", label: "Running" },
                { value: "completed", label: "Completed" },
                { value: "stopped", label: "Stopped" },
                { value: "draft", label: "Draft" },
              ]}
            />
          }
        />
        {experiments.isPending ? (
          <PanelBody>
            <TableSkeleton rows={4} cols={6} />
          </PanelBody>
        ) : experiments.isError ? (
          <ErrorState error={experiments.error} onRetry={() => experiments.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No experiments"
            description="Turn a hypothesis from an investigation into a test with a primary metric, guardrails and decision rules."
          />
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-2xs text-fg-subtle border-border border-b uppercase">
                <th className="px-4 py-2 text-left font-medium">Experiment</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Primary metric</th>
                <th className="px-3 py-2 text-left font-medium">Window</th>
                <th className="px-3 py-2 text-right font-medium">Variants · traffic</th>
                <th className="px-3 py-2 text-left font-medium">Decision</th>
                <th className="px-4 py-2 text-left font-medium">Owner</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((exp) => (
                <ExperimentRow key={exp.id} exp={exp} />
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <NewExperimentDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

export default function Page() {
  return <ExperimentsPage />;
}
