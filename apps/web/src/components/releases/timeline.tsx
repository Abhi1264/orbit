import { Flag, MessageSquare, Percent, Link as LinkIcon } from "lucide-react";

import type { ReleaseEventOut } from "@/lib/api/ops";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const KIND_ICON = {
  status_change: Flag,
  rollout: Percent,
  note: MessageSquare,
  link: LinkIcon,
} as const;

export function ReleaseTimeline({ events }: { events: ReleaseEventOut[] }) {
  if (events.length === 0) return <p className="text-fg-faint text-xs">No events yet.</p>;
  const ordered = [...events].sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
  return (
    <ol className="relative space-y-3 text-[13px]">
      <span className="bg-border absolute top-1 bottom-1 left-1.75 w-px" aria-hidden />
      {ordered.map((e) => {
        const Icon = KIND_ICON[e.kind as keyof typeof KIND_ICON] ?? MessageSquare;
        const rolledBack = e.kind === "status_change" && /rolled back/i.test(e.note);
        return (
          <li key={e.id} className="relative flex gap-3 pl-6">
            <span
              className={cn(
                "bg-bg absolute top-0.5 left-0 flex size-3.75 items-center justify-center rounded-full border",
                rolledBack
                  ? "border-danger text-danger"
                  : e.kind === "rollout"
                    ? "border-info text-info"
                    : "border-border text-fg-subtle",
              )}
            >
              <Icon className="size-2.5" strokeWidth={2.5} />
            </span>
            <div className="min-w-0">
              <div className="text-fg leading-5">{e.note}</div>
              <div className="text-fg-subtle text-2xs">
                {formatDateTime(e.occurred_at)}
                {e.actor ? ` · ${e.actor.name}` : ""}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
