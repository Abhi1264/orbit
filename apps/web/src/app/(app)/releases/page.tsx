"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { NewReleaseDialog } from "@/components/releases/new-release-dialog";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { SegmentedControl } from "@/components/ui/tabs";
import { usePermission } from "@/lib/api/hooks";
import { type ReleaseSummary, useReleases } from "@/lib/api/ops";
import { formatDate } from "@/lib/format";
import { releaseHref } from "@/lib/links";
import { useUrlState } from "@/lib/url-state";

type PlatformFilter = "all" | "android" | "ios" | "web";

function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <span className="inline-flex items-center gap-2">
      <span className="bg-surface-2 h-1.5 w-16 overflow-hidden rounded-full">
        <span
          className={pct === 100 ? "bg-success block h-full" : "bg-accent block h-full"}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="tabular text-fg-muted text-xs">
        {done}/{total}
      </span>
    </span>
  );
}

function ReleaseRow({ rel }: { rel: ReleaseSummary }) {
  return (
    <tr className="border-border hover:bg-surface border-b last:border-b-0">
      <td className="px-4 py-2.5">
        <Link href={releaseHref(rel.id)} className="text-fg hover:text-accent font-medium">
          {rel.name}
        </Link>
        <div className="text-fg-subtle mt-0.5 flex items-center gap-1.5 text-xs">
          <span className="font-mono">{rel.version}</span>
          <span>·</span>
          <span className="capitalize">{rel.platform === "all" ? "all platforms" : rel.platform}</span>
        </div>
      </td>
      <td className="px-3 py-2.5">
        <StatusBadge status={rel.status} />
      </td>
      <td className="tabular px-3 py-2.5 whitespace-nowrap">{formatDate(rel.release_date)}</td>
      <td className="tabular px-3 py-2.5">
        {rel.status === "planned" ? <span className="text-fg-faint">—</span> : `${rel.rollout_percent}%`}
      </td>
      <td className="px-3 py-2.5">
        {rel.checklist_progress ? (
          <Progress done={rel.checklist_progress.done} total={rel.checklist_progress.total} />
        ) : (
          <span className="text-fg-faint text-xs">No checklist</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap gap-1">
          {rel.affected_areas.map((a) => (
            <Badge key={a}>{a}</Badge>
          ))}
        </div>
      </td>
      <td className="px-3 py-2.5">
        {rel.open_investigations ? (
          <Badge tone="warning">
            {rel.open_investigations} open investigation{rel.open_investigations > 1 ? "s" : ""}
          </Badge>
        ) : (
          <span className="text-fg-faint">—</span>
        )}
      </td>
      <td className="text-fg-muted px-4 py-2.5">{rel.owner.name}</td>
    </tr>
  );
}

export default function ReleasesPage() {
  const url = useUrlState();
  const platform = (url.get("platform") as PlatformFilter | null) ?? "all";
  const releases = useReleases(platform === "all" ? {} : { platform });
  const canManage = usePermission("manage_releases");
  const [creating, setCreating] = useState(false);
  const rows = releases.data ?? [];
  const upcoming = rows.filter((r) => r.status === "planned" || r.status === "in_progress");
  const shipped = rows.filter((r) => !upcoming.includes(r));

  return (
    <>
      <PageHeader
        title="Releases"
        description="Every release is a candidate cause. Ship with the launch checklist attached, then read the week after against the week before; root-cause analysis correlates anomalies back to what shipped here."
        actions={
          canManage ? (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus className="size-3.5" />
              New release
            </Button>
          ) : null
        }
      />
      <Panel>
        <PanelHeader
          title="All releases"
          actions={
            <SegmentedControl<PlatformFilter>
              label="Platform"
              value={platform}
              onChange={(v) => url.set({ platform: v === "all" ? null : v })}
              options={[
                { value: "all", label: "All" },
                { value: "android", label: "Android" },
                { value: "ios", label: "iOS" },
                { value: "web", label: "Web" },
              ]}
            />
          }
        />
        {releases.isPending ? (
          <TableSkeleton rows={5} cols={6} />
        ) : releases.isError ? (
          <PanelBody>
            <ErrorState error={releases.error} onRetry={() => releases.refetch()} />
          </PanelBody>
        ) : rows.length === 0 ? (
          <EmptyState title="No releases" description="Nothing has shipped for this platform yet." />
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-fg-subtle text-2xs border-border border-b text-left tracking-wide uppercase">
                <th className="px-4 py-2 font-medium">Release</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Rollout</th>
                <th className="px-3 py-2 font-medium">Checklist</th>
                <th className="px-3 py-2 font-medium">Areas</th>
                <th className="px-3 py-2 font-medium">Signals</th>
                <th className="px-4 py-2 font-medium">Owner</th>
              </tr>
            </thead>
            <tbody>
              {[...upcoming, ...shipped].map((r) => (
                <ReleaseRow key={r.id} rel={r} />
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <NewReleaseDialog open={creating} onOpenChange={setCreating} />
    </>
  );
}
