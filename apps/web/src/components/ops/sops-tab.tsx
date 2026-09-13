"use client";

import { Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ChecklistPanel } from "@/components/releases/checklist-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import { usePermission } from "@/lib/api/hooks";
import {
  type SopCreate,
  type SopItem,
  type SopOut,
  useChecklists,
  useOpsMutations,
  useReleases,
  useSops,
} from "@/lib/api/ops";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/url-state";

export function SopsTab() {
  const url = useUrlState();
  const sops = useSops();
  const checklists = useChecklists();
  const canManage = usePermission("manage_ops");
  const selectedId = url.get("sop") ? Number(url.get("sop")) : null;
  const selected = sops.data?.find((s) => s.id === selectedId) ?? sops.data?.[0] ?? null;
  const [creating, setCreating] = useState(false);
  const [running, setRunning] = useState<SopOut | null>(null);
  const open = (checklists.data ?? []).filter((c) => c.status !== "complete");
  const done = (checklists.data ?? []).filter((c) => c.status === "complete");

  return (
    <div className="grid gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
      <Panel className="self-start">
        <PanelHeader
          title="Procedures"
          description="Reusable checklists. Running one against a release creates a tracked copy."
          actions={
            canManage ? (
              <Button size="sm" onClick={() => setCreating(true)}>
                <Plus className="size-3.5" /> New
              </Button>
            ) : null
          }
        />
        {sops.isPending ? (
          <TableSkeleton rows={3} cols={1} />
        ) : sops.isError ? (
          <PanelBody>
            <ErrorState error={sops.error} />
          </PanelBody>
        ) : (
          <ul>
            {(sops.data ?? []).map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => url.set({ sop: String(s.id) })}
                  className={cn(
                    "border-border hover:bg-surface flex w-full flex-col items-start gap-0.5 border-b px-4 py-2.5 text-left last:border-b-0",
                    selected?.id === s.id && "bg-surface",
                  )}
                >
                  <span className="text-fg text-[13px] font-medium">{s.title}</span>
                  <span className="text-fg-subtle text-xs">
                    {s.category} · {s.items.length} steps · run {s.run_count}×
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="space-y-4">
        {selected ? (
          <Panel>
            <PanelHeader
              title={selected.title}
              description={selected.description}
              actions={
                <>
                  <Badge>{selected.category}</Badge>
                  {canManage ? (
                    <Button size="sm" variant="primary" onClick={() => setRunning(selected)}>
                      <Play className="size-3.5" /> Run
                    </Button>
                  ) : null}
                </>
              }
            />
            <PanelBody className="p-0">
              <ol className="text-[13px]">
                {selected.items.map((item, i) => (
                  <li
                    key={item.key}
                    className="border-border flex items-baseline gap-3 border-b px-4 py-2 last:border-b-0"
                  >
                    <span className="tabular text-fg-faint w-5 shrink-0 text-right text-xs">{i + 1}</span>
                    <span className="text-fg flex-1">{item.label}</span>
                    {item.owner_role ? (
                      <span className="text-fg-subtle text-2xs uppercase">{item.owner_role}</span>
                    ) : null}
                  </li>
                ))}
              </ol>
            </PanelBody>
          </Panel>
        ) : sops.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : null}

        <div>
          <h3 className="text-fg mb-2 text-[13px] font-medium">
            Active checklists{" "}
            <span className="text-fg-subtle font-normal">
              {open.length} open · {done.length} complete
            </span>
          </h3>
          {checklists.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : open.length === 0 && done.length === 0 ? (
            <Panel>
              <EmptyState
                title="No checklists yet"
                description="Run an SOP against a release to start one."
              />
            </Panel>
          ) : (
            <div className="space-y-3">
              {[...open, ...done].map((c) => (
                <ChecklistPanel key={c.id} checklist={c} canEdit={canManage} showRelease />
              ))}
            </div>
          )}
        </div>
      </div>

      <Dialog open={creating} onOpenChange={setCreating}>
        {creating ? <NewSopForm onClose={() => setCreating(false)} /> : null}
      </Dialog>
      <Dialog open={running !== null} onOpenChange={(o) => (o ? null : setRunning(null))}>
        {running ? <RunSopForm sop={running} onClose={() => setRunning(null)} /> : null}
      </Dialog>
    </div>
  );
}

function slug(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40);
}

function NewSopForm({ onClose }: { onClose: () => void }) {
  const { createSop } = useOpsMutations();
  const url = useUrlState();
  const [form, setForm] = useState<SopCreate>({
    title: "",
    description: "",
    category: "launch",
    items: [{ key: "", label: "", owner_role: "pm" }],
  });
  const patch = (p: Partial<SopCreate>) => setForm((f) => ({ ...f, ...p }));
  const setItem = (i: number, p: Partial<SopItem>) =>
    patch({ items: form.items.map((it, j) => (j === i ? { ...it, ...p } : it)) });

  return (
    <DialogContent
      title="New SOP"
      description="Write the steps once; every run gets its own checklist with who ticked what and when."
      wide
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          const items = form.items
            .filter((it) => it.label.trim())
            .map((it, i) => ({ ...it, key: it.key || slug(it.label) || `step_${i + 1}` }));
          createSop.mutate(
            { ...form, items },
            {
              onSuccess: (sop) => {
                onClose();
                url.set({ sop: String(sop.id) });
              },
            },
          );
        }}
      >
        <div className="grid grid-cols-[1fr_10rem] gap-3">
          <Field label="Title" htmlFor="sop-title">
            <Input
              id="sop-title"
              required
              minLength={3}
              value={form.title}
              onChange={(e) => patch({ title: e.target.value })}
            />
          </Field>
          <Field label="Category" htmlFor="sop-cat">
            <Input
              id="sop-cat"
              required
              value={form.category}
              onChange={(e) => patch({ category: e.target.value })}
            />
          </Field>
        </div>
        <Field label="When it applies" htmlFor="sop-desc">
          <Textarea
            id="sop-desc"
            value={form.description ?? ""}
            onChange={(e) => patch({ description: e.target.value })}
            className="min-h-14"
          />
        </Field>
        <Field label="Steps">
          <div className="space-y-1.5">
            {form.items.map((it, i) => (
              <div key={i} className="grid grid-cols-[1fr_7rem_1.75rem] gap-2">
                <Input
                  aria-label={`Step ${i + 1}`}
                  value={it.label}
                  onChange={(e) => setItem(i, { label: e.target.value })}
                  placeholder={`Step ${i + 1}`}
                />
                <Select
                  aria-label="Owner role"
                  value={it.owner_role ?? ""}
                  onChange={(e) => setItem(i, { owner_role: e.target.value || null })}
                >
                  <option value="">Anyone</option>
                  <option value="pm">PM</option>
                  <option value="eng">Eng</option>
                  <option value="qa">QA</option>
                  <option value="analyst">Analyst</option>
                  <option value="design">Design</option>
                </Select>
                <Button
                  size="icon"
                  variant="ghost"
                  type="button"
                  aria-label="Remove step"
                  disabled={form.items.length === 1}
                  onClick={() => patch({ items: form.items.filter((_, j) => j !== i) })}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
            <Button
              size="sm"
              type="button"
              onClick={() => patch({ items: [...form.items, { key: "", label: "", owner_role: null }] })}
            >
              <Plus className="size-3.5" /> Add step
            </Button>
          </div>
        </Field>
        {createSop.isError ? <ErrorState error={createSop.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={createSop.isPending}>
            Create SOP
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

function RunSopForm({ sop, onClose }: { sop: SopOut; onClose: () => void }) {
  const releases = useReleases();
  const { startChecklist } = useOpsMutations();
  const [releaseId, setReleaseId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const candidates = (releases.data ?? []).filter((r) => r.status !== "rolled_back");

  return (
    <DialogContent
      title={`Run “${sop.title}”`}
      description="Creates a checklist from the SOP steps. Attach it to a release so it shows up on the release page."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          startChecklist.mutate(
            { sop_id: sop.id, release_id: releaseId, title: title.trim() || null },
            { onSuccess: onClose },
          );
        }}
      >
        <Field label="Release" htmlFor="run-release" hint="Optional. Leave empty for a standalone checklist.">
          <Select
            id="run-release"
            value={releaseId ?? ""}
            onChange={(e) => setReleaseId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">No release</option>
            {candidates.map((r) => (
              <option key={r.id} value={r.id}>
                {r.version} · {r.platform} · {r.name} ({formatDate(r.release_date)})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Checklist title" htmlFor="run-title">
          <Input
            id="run-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Defaults to release + SOP name"
          />
        </Field>
        {startChecklist.isError ? <ErrorState error={startChecklist.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={startChecklist.isPending}>
            Start checklist
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
