"use client";

import { ArrowUpRight, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { Suspense, useState } from "react";

import { describeFilter, FilterBuilder } from "@/components/analytics/filter-builder";
import { Button } from "@/components/ui/button";
import { DeltaText } from "@/components/ui/delta";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { type Filter, type SegmentOut, useSegmentMutations, useSegmentPreview, useSegments } from "@/lib/api/analytics";
import { useMe } from "@/lib/api/hooks";
import { formatMetric, type MetricFormat } from "@/lib/format";
import { useRange } from "@/lib/range";

function SegmentEditor({
  initial,
  onClose,
}: {
  initial: SegmentOut | null;
  onClose: () => void;
}) {
  const range = useRange();
  const { create, update } = useSegmentMutations();
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [conditions, setConditions] = useState<Filter[]>(initial?.conditions ?? []);
  const preview = useSegmentPreview(
    range.ready && conditions.length
      ? { conditions, date_from: range.from, date_to: range.to, compare_from: range.compareFrom, compare_to: range.compareTo }
      : null,
  );
  const pending = create.isPending || update.isPending;

  return (
    <DialogContent
      title={initial ? "Edit segment" : "New segment"}
      description="Segments are saved filter sets. Their metrics are computed live against the current date range."
      wide
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const body = { name, description, conditions };
          if (initial) update.mutate({ id: initial.id, body }, { onSuccess: onClose });
          else create.mutate(body, { onSuccess: onClose });
        }}
        className="grid gap-4 md:grid-cols-[1fr_320px]"
      >
        <div className="space-y-3">
          <Field label="Name" htmlFor="seg-name">
            <Input id="seg-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          </Field>
          <Field label="Description" htmlFor="seg-desc">
            <Textarea id="seg-desc" value={description} onChange={(e) => setDescription(e.target.value)} className="min-h-14" />
          </Field>
          <Field label="Conditions" hint="All conditions must match (AND).">
            <FilterBuilder filters={conditions} onChange={setConditions} dimensions={range.meta?.dimensions ?? []} />
          </Field>
        </div>
        <div className="rounded-sm border border-border bg-surface p-3">
          <div className="mb-2 text-xs font-medium text-fg">Preview · {range.from} → {range.to}</div>
          {!conditions.length ? (
            <p className="text-xs text-fg-subtle">Add a condition to preview.</p>
          ) : preview.isPending ? (
            <TableSkeleton rows={6} cols={2} />
          ) : preview.isError ? (
            <ErrorState error={preview.error} />
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-2xs text-fg-subtle uppercase">
                  <th className="pb-1 text-left font-medium">Metric</th>
                  <th className="pb-1 text-right font-medium">Segment</th>
                  <th className="pb-1 text-right font-medium">All</th>
                </tr>
              </thead>
              <tbody>
                {preview.data?.metrics.map((m) => (
                  <tr key={m.key} className="border-t border-border">
                    <td className="py-1 text-fg-muted">{m.label}</td>
                    <td className="tabular py-1 text-right font-medium">{formatMetric(m.value, m.format as MetricFormat, true)}</td>
                    <td className="tabular py-1 text-right text-fg-subtle">{formatMetric(m.baseline_value, m.format as MetricFormat, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={pending} disabled={!name || !conditions.length}>
            {initial ? "Save changes" : "Create segment"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

function SegmentRow({ segment, onEdit }: { segment: SegmentOut; onEdit: () => void }) {
  const range = useRange();
  const me = useMe();
  const { remove } = useSegmentMutations();
  const preview = useSegmentPreview(
    range.ready
      ? { conditions: segment.conditions, date_from: range.from, date_to: range.to, compare_from: range.compareFrom, compare_to: range.compareTo }
      : null,
  );
  const dims = range.meta?.dimensions ?? [];
  const canEdit = me.data && (me.data.id === segment.owner.id || me.data.role === "admin" || me.data.role === "pm");
  const shown = ["sessions", "conversion", "payment_success_rate", "return_rate"];
  const exploreHref = `/analytics?metric=conversion&f=${encodeURIComponent(JSON.stringify(segment.conditions))}`;

  return (
    <tr>
      <td>
        <div className="font-medium">{segment.name}</div>
        <div className="mt-0.5 flex flex-wrap gap-1">
          {segment.conditions.map((c, i) => (
            <span key={i} className="rounded-sm border border-border bg-surface px-1 py-px font-mono text-2xs text-fg-muted">
              {describeFilter(c, dims)}
            </span>
          ))}
        </div>
      </td>
      {shown.map((key) => {
        const m = preview.data?.metrics.find((x) => x.key === key);
        return (
          <td key={key} className="num">
            {m ? (
              <div>
                <div className="font-medium">{formatMetric(m.value, m.format as MetricFormat, true)}</div>
                <DeltaText current={m.value} previous={m.compare_value} format={m.format as MetricFormat} higherIsBetter={key !== "return_rate"} className="text-2xs" />
              </div>
            ) : (
              <span className="text-fg-faint">…</span>
            )}
          </td>
        );
      })}
      <td className="text-fg-subtle">{segment.owner.name}</td>
      <td>
        <div className="flex justify-end gap-1">
          <Link href={exploreHref as "/"} className="inline-flex h-7 w-7 items-center justify-center rounded-sm text-fg-subtle hover:bg-surface-2 hover:text-fg" aria-label="Explore segment">
            <ArrowUpRight className="size-3.5" />
          </Link>
          <Button variant="ghost" size="icon" aria-label="Edit segment" onClick={onEdit} disabled={!canEdit}>
            <Pencil className="size-3.5" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Delete segment" onClick={() => remove.mutate(segment.id)} disabled={!canEdit}>
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function Segments() {
  const segments = useSegments();
  const [editing, setEditing] = useState<SegmentOut | null | "new">(null);

  return (
    <>
      <PageHeader
        title="Segments"
        description="Reusable user and session filters. Metrics are computed live for the selected period and compared with the previous period."
        actions={
          <Button variant="primary" size="sm" onClick={() => setEditing("new")}>
            New segment
          </Button>
        }
      />
      <Panel>
        <PanelHeader title={`${segments.data?.length ?? 0} segments`} />
        {segments.isPending ? (
          <TableSkeleton />
        ) : segments.isError ? (
          <ErrorState error={segments.error} onRetry={() => segments.refetch()} />
        ) : segments.data?.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Segment</th>
                <th className="num">Sessions</th>
                <th className="num">Conversion</th>
                <th className="num">Payment success</th>
                <th className="num">Return rate</th>
                <th>Owner</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {segments.data.map((s) => (
                <SegmentRow key={s.id} segment={s} onEdit={() => setEditing(s)} />
              ))}
            </tbody>
          </table>
        ) : (
          <PanelBody>
            <EmptyState title="No segments yet" action={<Button onClick={() => setEditing("new")}>Create one</Button>} />
          </PanelBody>
        )}
      </Panel>
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        {editing !== null ? <SegmentEditor initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}
      </Dialog>
    </>
  );
}

export default function SegmentsPage() {
  return (
    <Suspense>
      <Segments />
    </Suspense>
  );
}
