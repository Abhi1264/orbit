"use client";

import { Check } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/ui/badge";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { type ChecklistOut, useOpsMutations } from "@/lib/api/ops";
import { formatDateTime } from "@/lib/format";
import { releaseHref } from "@/lib/links";
import { cn } from "@/lib/utils";

export function ChecklistPanel({
  checklist,
  canEdit,
  showRelease,
}: {
  checklist: ChecklistOut;
  canEdit: boolean;
  showRelease?: boolean;
}) {
  const { toggleItem } = useOpsMutations();
  const pct = checklist.total_count ? Math.round((checklist.done_count / checklist.total_count) * 100) : 0;

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            {showRelease && checklist.release_id ? (
              <Link href={releaseHref(checklist.release_id)} className="hover:text-accent">
                {checklist.title}
              </Link>
            ) : (
              checklist.title
            )}
            <StatusBadge status={checklist.status} />
          </span>
        }
        description={`${checklist.done_count} of ${checklist.total_count} done · owner ${checklist.owner.name}`}
        actions={
          <span className="bg-surface-2 h-1.5 w-24 overflow-hidden rounded-full" aria-hidden>
            <span
              className={cn("block h-full", pct === 100 ? "bg-success" : "bg-accent")}
              style={{ width: `${pct}%` }}
            />
          </span>
        }
      />
      <PanelBody className="p-0">
        <ul>
          {checklist.items.map((item) => {
            const pending = toggleItem.isPending && toggleItem.variables?.key === item.key;
            return (
              <li
                key={item.key}
                className="border-border flex items-start gap-3 border-b px-4 py-2 last:border-b-0"
              >
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={item.done}
                  aria-label={item.label}
                  disabled={!canEdit || pending}
                  onClick={() =>
                    toggleItem.mutate({ checklistId: checklist.id, key: item.key, done: !item.done })
                  }
                  className={cn(
                    "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-sm border transition-colors",
                    item.done ? "border-success bg-success text-white" : "border-border bg-bg",
                    canEdit ? "hover:border-accent" : "cursor-default",
                    pending && "opacity-50",
                  )}
                >
                  {item.done ? <Check className="size-3" strokeWidth={3} /> : null}
                </button>
                <div className="min-w-0 flex-1">
                  <div className={cn("text-[13px]", item.done ? "text-fg-muted line-through" : "text-fg")}>
                    {item.label}
                  </div>
                  <div className="text-fg-subtle text-2xs mt-0.5 flex gap-2">
                    {item.owner_role ? <span className="uppercase">{item.owner_role}</span> : null}
                    {item.done && item.done_at ? <span>done {formatDateTime(item.done_at)}</span> : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </PanelBody>
    </Panel>
  );
}
