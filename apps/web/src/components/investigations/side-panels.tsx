"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { useUsers } from "@/lib/api/hooks";
import { type InvestigationOut, useInvestigationMutations, useStakeholders } from "@/lib/api/investigations";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

// --------------------------------------------------------------------------- actions

export function ActionsPanel({ inv, canEdit }: { inv: InvestigationOut; canEdit: boolean }) {
  const { addAction, updateAction, deleteAction } = useInvestigationMutations(inv.id);
  const users = useUsers();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [ownerId, setOwnerId] = useState<string>("");
  const [due, setDue] = useState("");
  const open = inv.actions.filter((a) => a.status !== "done");
  const done = inv.actions.filter((a) => a.status === "done");

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            Actions
            {inv.actions.length ? (
              <span className="text-fg-subtle text-xs font-normal">
                {done.length}/{inv.actions.length} done
              </span>
            ) : null}
          </span>
        }
        actions={
          canEdit && !adding ? (
            <Button size="icon" variant="ghost" aria-label="Add action" onClick={() => setAdding(true)}>
              <Plus className="size-3.5" />
            </Button>
          ) : null
        }
      />
      <PanelBody className="space-y-2">
        {adding ? (
          <form
            className="border-border bg-surface space-y-2 rounded-md border p-2"
            onSubmit={(e) => {
              e.preventDefault();
              addAction.mutate(
                { title, owner_id: ownerId ? Number(ownerId) : null, due_date: due || null },
                {
                  onSuccess: () => {
                    setAdding(false);
                    setTitle("");
                    setOwnerId("");
                    setDue("");
                  },
                },
              );
            }}
          >
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What needs to happen"
              required
              autoFocus
              aria-label="Action title"
            />
            <div className="grid grid-cols-2 gap-2">
              <Select value={ownerId} onChange={(e) => setOwnerId(e.target.value)} aria-label="Owner">
                <option value="">Unassigned</option>
                {(users.data ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </Select>
              <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label="Due date" />
            </div>
            <div className="flex justify-end gap-1.5">
              <Button type="button" size="sm" variant="ghost" onClick={() => setAdding(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" variant="primary" loading={addAction.isPending}>
                Add action
              </Button>
            </div>
          </form>
        ) : null}
        {inv.actions.length === 0 && !adding ? (
          <p className="text-fg-faint text-xs">
            No actions yet. Add one when a recommendation turns into work.
          </p>
        ) : null}
        <ul className="space-y-1">
          {[...open, ...done].map((a) => (
            <li key={a.id} className="group flex items-start gap-2 text-[13px]">
              <input
                type="checkbox"
                className="accent-accent mt-1"
                checked={a.status === "done"}
                disabled={!canEdit}
                aria-label={`Mark "${a.title}" ${a.status === "done" ? "not done" : "done"}`}
                onChange={(e) =>
                  updateAction.mutate({
                    action_id: a.id,
                    body: { status: e.target.checked ? "done" : "todo" },
                  })
                }
              />
              <div className="min-w-0 flex-1">
                <div className={cn("text-fg", a.status === "done" && "text-fg-subtle line-through")}>
                  {a.title}
                </div>
                <div className="text-fg-subtle text-2xs">
                  {a.owner?.name ?? "Unassigned"}
                  {a.due_date ? <> · due {formatDate(a.due_date)}</> : null}
                  {a.status === "in_progress" ? <> · in progress</> : null}
                </div>
              </div>
              {canEdit ? (
                <button
                  type="button"
                  aria-label="Delete action"
                  onClick={() => deleteAction.mutate(a.id)}
                  className="text-fg-subtle hover:text-danger mt-0.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <Trash2 className="size-3" />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </PanelBody>
    </Panel>
  );
}

// --------------------------------------------------------------------------- stakeholders

const ROLES = ["informed", "consulted", "owner", "approver"];

export function StakeholdersPanel({ inv, canEdit }: { inv: InvestigationOut; canEdit: boolean }) {
  const all = useStakeholders();
  const { setStakeholders } = useInvestigationMutations(inv.id);
  const [pick, setPick] = useState("");
  const [role, setRole] = useState(ROLES[0]!);
  const current = inv.stakeholders.map((s) => ({ stakeholder_id: s.stakeholder.id, role: s.role }));
  const available = (all.data ?? []).filter((s) => !current.some((c) => c.stakeholder_id === s.id));

  return (
    <Panel>
      <PanelHeader title="Stakeholders" description="Who needs to know, and in what capacity." />
      <PanelBody className="space-y-2">
        {inv.stakeholders.length ? (
          <ul className="space-y-1.5">
            {inv.stakeholders.map((s) => (
              <li key={s.stakeholder.id} className="group flex items-start justify-between gap-2 text-[13px]">
                <div className="min-w-0">
                  <div className="text-fg">{s.stakeholder.name}</div>
                  <div className="text-fg-subtle text-2xs">
                    {s.stakeholder.title} · {s.stakeholder.team}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Badge tone="neutral">{s.role}</Badge>
                  {canEdit ? (
                    <button
                      type="button"
                      aria-label={`Remove ${s.stakeholder.name}`}
                      onClick={() =>
                        setStakeholders.mutate(current.filter((c) => c.stakeholder_id !== s.stakeholder.id))
                      }
                      className="text-fg-subtle hover:text-danger opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-fg-faint text-xs">Nobody assigned.</p>
        )}
        {canEdit && available.length ? (
          <form
            className="flex items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              if (!pick) return;
              setStakeholders.mutate([...current, { stakeholder_id: Number(pick), role }], {
                onSuccess: () => setPick(""),
              });
            }}
          >
            <Select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              aria-label="Stakeholder"
              className="min-w-0 flex-1"
            >
              <option value="">Add stakeholder…</option>
              {available.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} — {s.team}
                </option>
              ))}
            </Select>
            <Select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" className="w-28">
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
            <Button
              type="submit"
              size="icon"
              variant="ghost"
              aria-label="Add"
              disabled={!pick}
              loading={setStakeholders.isPending}
            >
              <Plus className="size-3.5" />
            </Button>
          </form>
        ) : null}
      </PanelBody>
    </Panel>
  );
}
