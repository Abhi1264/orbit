"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/states";
import { useMe } from "@/lib/api/hooks";
import { type EntityType, useCommentMutations, useComments } from "@/lib/api/investigations";
import { formatDateTime } from "@/lib/format";

export function CommentThread({ entityType, entityId }: { entityType: EntityType; entityId: number }) {
  const me = useMe();
  const comments = useComments(entityType, entityId);
  const { add, remove } = useCommentMutations(entityType, entityId);
  const [draft, setDraft] = useState("");
  const isAdmin = me.data?.role === "admin";

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            Discussion
            {comments.data?.length ? (
              <span className="text-fg-subtle text-xs font-normal">{comments.data.length}</span>
            ) : null}
          </span>
        }
      />
      <PanelBody className="space-y-3">
        {comments.isPending ? (
          <Skeleton className="h-12" />
        ) : comments.data?.length ? (
          <ul className="space-y-3">
            {comments.data.map((c) => (
              <li key={c.id} className="group text-[13px]">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-fg font-medium">{c.author.name}</span>
                  <span className="text-fg-subtle text-2xs flex items-center gap-1">
                    {formatDateTime(c.created_at)}
                    {isAdmin || c.author.id === me.data?.id ? (
                      <button
                        type="button"
                        aria-label="Delete comment"
                        onClick={() => remove.mutate(c.id)}
                        className="text-fg-subtle hover:text-danger opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        <Trash2 className="size-3" />
                      </button>
                    ) : null}
                  </span>
                </div>
                <p className="text-fg-muted mt-0.5 text-xs leading-5 whitespace-pre-line">{c.body}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-fg-faint text-xs">No comments yet.</p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!draft.trim()) return;
            add.mutate(draft.trim(), { onSuccess: () => setDraft("") });
          }}
          className="space-y-2"
        >
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a comment…"
            aria-label="Comment"
            className="min-h-14"
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") e.currentTarget.form?.requestSubmit();
            }}
          />
          <div className="flex items-center justify-between">
            <span className="text-fg-faint text-2xs">⌘↵ to post</span>
            <Button type="submit" size="sm" loading={add.isPending} disabled={!draft.trim()}>
              Comment
            </Button>
          </div>
        </form>
      </PanelBody>
    </Panel>
  );
}
