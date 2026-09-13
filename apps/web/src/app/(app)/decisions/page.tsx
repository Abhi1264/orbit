"use client";

import { CalendarClock, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { CommentThread } from "@/components/comments/comment-thread";
import { DecisionDialog } from "@/components/decisions/decision-dialog";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { KeyValue, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import { SegmentedControl } from "@/components/ui/tabs";
import { usePermission } from "@/lib/api/hooks";
import {
  type DecisionOut,
  type DecisionStatus,
  useDecision,
  useDecisionMutations,
  useDecisions,
} from "@/lib/api/ops";
import { formatDate } from "@/lib/format";
import { entityHref } from "@/lib/links";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/url-state";

type View = "all" | "due" | "proposed";

const STATUS_HELP: Record<DecisionStatus, string> = {
  proposed: "Written up, not yet agreed",
  decided: "Agreed and in effect",
  superseded: "Replaced by a later decision",
};

function Section({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <div>
      <div className="text-fg-subtle text-2xs mb-1 tracking-wide uppercase">{label}</div>
      <p className="text-fg text-[13px] leading-6 whitespace-pre-line">{text}</p>
    </div>
  );
}

function DecisionDetail({ id, onEdit }: { id: number; onEdit: (d: DecisionOut) => void }) {
  const decision = useDecision(id);
  const canManage = usePermission("manage_decisions");
  const { update } = useDecisionMutations();

  if (decision.isPending) {
    return (
      <Panel>
        <PanelBody className="space-y-2">
          <Skeleton className="h-5 w-72" />
          <Skeleton className="h-24 w-full" />
        </PanelBody>
      </Panel>
    );
  }
  if (decision.isError) return <ErrorState error={decision.error} onRetry={() => decision.refetch()} />;
  const d = decision.data;

  return (
    <div className="space-y-4">
      <Panel>
        <PanelHeader
          title={
            <span className="flex flex-wrap items-center gap-2">
              {d.title}
              <StatusBadge status={d.status} />
              {d.follow_up_due ? <Badge tone="warning">Follow-up due</Badge> : null}
            </span>
          }
          description={
            <>
              Decided {formatDate(d.decided_on, { day: "numeric", month: "short", year: "numeric" })} by{" "}
              {d.owner.name}
              {d.follow_up_date ? (
                <>
                  {" "}
                  · review {formatDate(d.follow_up_date, { day: "numeric", month: "short", year: "numeric" })}
                </>
              ) : null}
            </>
          }
          actions={
            canManage ? (
              <>
                <Select
                  aria-label="Status"
                  value={d.status}
                  onChange={(e) =>
                    update.mutate({ id: d.id, body: { status: e.target.value as DecisionStatus } })
                  }
                  className="h-7 w-32 text-xs"
                  title={STATUS_HELP[d.status]}
                >
                  <option value="proposed">Proposed</option>
                  <option value="decided">Decided</option>
                  <option value="superseded">Superseded</option>
                </Select>
                <Button size="sm" onClick={() => onEdit(d)}>
                  Edit
                </Button>
              </>
            ) : null
          }
        />
        <PanelBody className="space-y-4">
          <div className="border-accent bg-accent-soft/40 rounded-sm border-l-2 px-3 py-2">
            <div className="text-accent text-2xs mb-0.5 tracking-wide uppercase">Decision</div>
            <p className="text-fg text-[13px] leading-6">{d.decision}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Section label="Context" text={d.context} />
            <Section label="Evidence" text={d.evidence} />
            <Section label="Alternatives considered" text={d.alternatives} />
            <Section label="Expected impact" text={d.expected_impact} />
          </div>
          {d.linked.length ? (
            <KeyValue
              items={[
                {
                  label: "Based on",
                  value: (
                    <span className="flex flex-wrap gap-x-3 gap-y-1">
                      {d.linked.map((l) => (
                        <Link
                          key={`${l.type}-${l.id}`}
                          href={entityHref(l.type, l.id)}
                          className="text-accent hover:underline"
                        >
                          {l.type}: {l.title}
                        </Link>
                      ))}
                    </span>
                  ),
                },
              ]}
            />
          ) : null}
        </PanelBody>
      </Panel>
      <CommentThread entityType="decision" entityId={d.id} />
    </div>
  );
}

export default function DecisionsPage() {
  const url = useUrlState();
  const view = (url.get("view") as View | null) ?? "all";
  const decisions = useDecisions(
    view === "due" ? { due_only: true } : view === "proposed" ? { status: "proposed" } : {},
  );
  const canManage = usePermission("manage_decisions");
  const [editing, setEditing] = useState<DecisionOut | "new" | null>(null);
  const rows = decisions.data ?? [];
  const selectedId = url.get("id") ? Number(url.get("id")) : (rows[0]?.id ?? null);
  const dueCount = rows.filter((r) => r.follow_up_due).length;

  return (
    <>
      <PageHeader
        title="Decision log"
        description="What we decided, on what evidence, and what we expected to happen. Every entry links back to the investigation, experiment or release it came from, with a follow-up date to check the expectation against reality."
        actions={
          canManage ? (
            <Button variant="primary" onClick={() => setEditing("new")}>
              <Plus className="size-3.5" />
              Record decision
            </Button>
          ) : null
        }
      />
      <div className="grid gap-4 xl:grid-cols-[24rem_minmax(0,1fr)]">
        <Panel className="self-start">
          <PanelHeader
            title="Decisions"
            actions={
              <SegmentedControl<View>
                label="Decision view"
                value={view}
                onChange={(v) => url.set({ view: v === "all" ? null : v, id: null })}
                options={[
                  { value: "all", label: "All" },
                  { value: "due", label: dueCount ? `Due ${dueCount}` : "Due" },
                  { value: "proposed", label: "Proposed" },
                ]}
              />
            }
          />
          {decisions.isPending ? (
            <TableSkeleton rows={4} cols={1} />
          ) : decisions.isError ? (
            <PanelBody>
              <ErrorState error={decisions.error} />
            </PanelBody>
          ) : rows.length === 0 ? (
            <EmptyState
              title="No decisions"
              description={
                view === "due"
                  ? "Nothing is due for review."
                  : "Record the first one from an experiment or investigation."
              }
            />
          ) : (
            <ul>
              {rows.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => url.set({ id: String(d.id) })}
                    className={cn(
                      "border-border hover:bg-surface flex w-full flex-col items-start gap-1 border-b px-4 py-2.5 text-left last:border-b-0",
                      selectedId === d.id && "bg-surface",
                    )}
                  >
                    <span className="flex w-full items-start justify-between gap-2">
                      <span className="text-fg text-[13px] font-medium">{d.title}</span>
                      <StatusBadge status={d.status} />
                    </span>
                    <span className="text-fg-subtle line-clamp-2 text-xs">{d.decision}</span>
                    <span className="text-fg-faint text-2xs flex items-center gap-2">
                      <span>{formatDate(d.decided_on)}</span>
                      <span>·</span>
                      <span>{d.owner.name}</span>
                      {d.follow_up_due ? (
                        <span className="text-warning inline-flex items-center gap-0.5">
                          <CalendarClock className="size-3" /> review due
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <div>
          {selectedId !== null ? (
            <DecisionDetail id={selectedId} onEdit={(d) => setEditing(d)} />
          ) : decisions.isSuccess ? (
            <Panel>
              <EmptyState title="Select a decision" />
            </Panel>
          ) : null}
        </div>
      </div>
      <DecisionDialog
        open={editing !== null}
        existing={editing === "new" ? null : editing}
        onClose={() => setEditing(null)}
        onSaved={(id) => url.set({ id: String(id) })}
      />
    </>
  );
}
