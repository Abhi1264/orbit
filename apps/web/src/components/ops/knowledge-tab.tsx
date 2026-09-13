"use client";

import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import { usePermission } from "@/lib/api/hooks";
import {
  type KnowledgeCreate,
  type KnowledgeOut,
  useKnowledge,
  useKnowledgeDoc,
  useOpsMutations,
} from "@/lib/api/ops";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/url-state";

export function SimpleMarkdown({ body }: { body: string }) {
  const blocks = body.split(/\n{2,}/);
  return (
    <div className="space-y-3 text-[13px] leading-6">
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim());
        if (lines.length === 0) return null;
        if (/^###\s/.test(lines[0])) {
          return (
            <h4 key={i} className="text-fg mt-2 text-[13px] font-semibold">
              {lines[0].replace(/^###\s/, "")}
            </h4>
          );
        }
        if (/^##\s/.test(lines[0])) {
          return (
            <div key={i}>
              <h3 className="text-fg mt-3 text-sm font-semibold">{lines[0].replace(/^##\s/, "")}</h3>
              {lines.slice(1).length ? <p className="text-fg mt-1">{lines.slice(1).join(" ")}</p> : null}
            </div>
          );
        }
        if (lines.every((l) => /^[-*]\s/.test(l))) {
          return (
            <ul key={i} className="text-fg list-disc space-y-0.5 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{l.replace(/^[-*]\s/, "")}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="text-fg">
            {lines.join(" ")}
          </p>
        );
      })}
    </div>
  );
}

export function KnowledgeTab() {
  const url = useUrlState();
  const [q, setQ] = useState("");
  const tag = url.get("tag") ?? undefined;
  const docs = useKnowledge({ tag, q: q.trim().length >= 2 ? q.trim() : undefined });
  const docId = url.get("doc") ? Number(url.get("doc")) : null;
  const selectedId = docId ?? docs.data?.[0]?.id ?? null;
  const doc = useKnowledgeDoc(selectedId);
  const canManage = usePermission("manage_ops");
  const { removeDoc } = useOpsMutations();
  const [editing, setEditing] = useState<KnowledgeOut | "new" | null>(null);
  const allTags = Array.from(new Set((docs.data ?? []).flatMap((d) => d.tags))).sort();

  return (
    <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
      <Panel className="self-start">
        <PanelHeader
          title="Documents"
          actions={
            canManage ? (
              <Button size="sm" onClick={() => setEditing("new")}>
                <Plus className="size-3.5" /> New
              </Button>
            ) : null
          }
        />
        <div className="border-border border-b px-3 py-2">
          <div className="relative">
            <Search className="text-fg-faint absolute top-1/2 left-2 size-3.5 -translate-y-1/2" aria-hidden />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search the knowledge base"
              aria-label="Search knowledge"
              className="h-7 pl-7 text-xs"
            />
          </div>
          {allTags.length ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {allTags.map((t) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={tag === t}
                  onClick={() => url.set({ tag: tag === t ? null : t, doc: null })}
                  className={cn(
                    "rounded-sm border px-1.5 py-px text-[11px]",
                    tag === t
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-border text-fg-muted hover:text-fg",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        {docs.isPending ? (
          <TableSkeleton rows={4} cols={1} />
        ) : docs.isError ? (
          <PanelBody>
            <ErrorState error={docs.error} />
          </PanelBody>
        ) : docs.data.length === 0 ? (
          <EmptyState title="Nothing matches" description="Try fewer words, or clear the tag filter." />
        ) : (
          <ul>
            {docs.data.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  onClick={() => url.set({ doc: String(d.id) })}
                  className={cn(
                    "border-border hover:bg-surface flex w-full flex-col items-start gap-0.5 border-b px-4 py-2.5 text-left last:border-b-0",
                    selectedId === d.id && "bg-surface",
                  )}
                >
                  <span className="text-fg text-[13px] font-medium">{d.title}</span>
                  <span className="text-fg-subtle line-clamp-2 text-xs">{d.excerpt}</span>
                  <span className="text-fg-faint text-2xs">
                    {d.author.name} · {formatDate(d.updated_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel className="self-start">
        {doc.isPending && selectedId !== null ? (
          <PanelBody className="space-y-2">
            <Skeleton className="h-5 w-64" />
            <Skeleton className="h-32 w-full" />
          </PanelBody>
        ) : doc.data ? (
          <>
            <PanelHeader
              title={doc.data.title}
              description={
                <>
                  {doc.data.author.name} · updated{" "}
                  {formatDate(doc.data.updated_at, { day: "numeric", month: "short", year: "numeric" })}
                </>
              }
              actions={
                <>
                  {doc.data.tags.map((t) => (
                    <Badge key={t}>{t}</Badge>
                  ))}
                  {canManage ? (
                    <>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Edit document"
                        onClick={() => setEditing(doc.data!)}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label="Delete document"
                        loading={removeDoc.isPending}
                        onClick={() => {
                          if (window.confirm(`Delete "${doc.data!.title}"?`))
                            removeDoc.mutate(doc.data!.id, { onSuccess: () => url.set({ doc: null }) });
                        }}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </>
                  ) : null}
                </>
              }
            />
            <PanelBody className="max-w-3xl">
              <SimpleMarkdown body={doc.data.body} />
            </PanelBody>
          </>
        ) : (
          <EmptyState title="Select a document" />
        )}
      </Panel>

      <Dialog open={editing !== null} onOpenChange={(o) => (o ? null : setEditing(null))}>
        {editing !== null ? (
          <DocForm existing={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
        ) : null}
      </Dialog>
    </div>
  );
}

function DocForm({ existing, onClose }: { existing: KnowledgeOut | null; onClose: () => void }) {
  const url = useUrlState();
  const { createDoc, updateDoc } = useOpsMutations();
  const [form, setForm] = useState<KnowledgeCreate>({
    title: existing?.title ?? "",
    body: existing?.body ?? "",
    tags: existing?.tags ?? [],
  });
  const [tagsText, setTagsText] = useState((existing?.tags ?? []).join(", "));
  const mutation = existing ? updateDoc : createDoc;

  return (
    <DialogContent title={existing ? "Edit document" : "New document"} wide>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          const tags = tagsText
            .split(",")
            .map((t) => t.trim().toLowerCase())
            .filter(Boolean);
          const body = { ...form, tags };
          if (existing) {
            updateDoc.mutate({ id: existing.id, body }, { onSuccess: onClose });
          } else {
            createDoc.mutate(body, {
              onSuccess: (d) => {
                onClose();
                url.set({ doc: String(d.id) });
              },
            });
          }
        }}
      >
        <div className="grid grid-cols-[1fr_14rem] gap-3">
          <Field label="Title" htmlFor="doc-title">
            <Input
              id="doc-title"
              required
              minLength={3}
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </Field>
          <Field label="Tags" htmlFor="doc-tags" hint="Comma-separated">
            <Input
              id="doc-tags"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              placeholder="metrics, definitions"
            />
          </Field>
        </div>
        <Field label="Body" htmlFor="doc-body" hint="Supports ## headings, paragraphs and - lists.">
          <Textarea
            id="doc-body"
            required
            value={form.body}
            onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
            className="min-h-64 font-mono text-xs leading-5"
          />
        </Field>
        {mutation.isError ? <ErrorState error={mutation.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {existing ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
