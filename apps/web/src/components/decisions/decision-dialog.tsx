"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { useExperiments } from "@/lib/api/experiments";
import { useInvestigations } from "@/lib/api/investigations";
import { type DecisionCreate, type DecisionOut, useDecisionMutations, useReleases } from "@/lib/api/ops";

export type DecisionPrefill = Partial<DecisionCreate>;

/**
 * Create or edit a decision. `prefill` lets other pages (experiment readout, investigation)
 * open the dialog with the evidence already written in.
 */
export function DecisionDialog({
  open,
  existing,
  prefill,
  onClose,
  onSaved,
}: {
  open: boolean;
  existing: DecisionOut | null;
  prefill?: DecisionPrefill;
  onClose: () => void;
  onSaved?: (id: number) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      {open ? (
        <DecisionForm existing={existing} prefill={prefill} onClose={onClose} onSaved={onSaved} />
      ) : null}
    </Dialog>
  );
}

function DecisionForm({
  existing,
  prefill,
  onClose,
  onSaved,
}: {
  existing: DecisionOut | null;
  prefill?: DecisionPrefill;
  onClose: () => void;
  onSaved?: (id: number) => void;
}) {
  const { create, update } = useDecisionMutations();
  const investigations = useInvestigations();
  const experiments = useExperiments("all");
  const releases = useReleases();
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState<DecisionCreate>({
    title: existing?.title ?? prefill?.title ?? "",
    context: existing?.context ?? prefill?.context ?? "",
    evidence: existing?.evidence ?? prefill?.evidence ?? "",
    alternatives: existing?.alternatives ?? prefill?.alternatives ?? "",
    decision: existing?.decision ?? prefill?.decision ?? "",
    expected_impact: existing?.expected_impact ?? prefill?.expected_impact ?? "",
    status: existing?.status ?? prefill?.status ?? "decided",
    decided_on: existing?.decided_on ?? prefill?.decided_on ?? today,
    follow_up_date: existing?.follow_up_date ?? prefill?.follow_up_date ?? null,
    investigation_id: existing?.investigation_id ?? prefill?.investigation_id ?? null,
    experiment_id: existing?.experiment_id ?? prefill?.experiment_id ?? null,
    release_id: existing?.release_id ?? prefill?.release_id ?? null,
  });
  const patch = (p: Partial<DecisionCreate>) => setForm((f) => ({ ...f, ...p }));
  const mutation = existing ? update : create;

  return (
    <DialogContent
      title={existing ? "Edit decision" : "Record a decision"}
      description="Context → evidence → alternatives → decision → expected impact. Future you will read this when the follow-up comes due."
      wide
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          const body = { ...form, follow_up_date: form.follow_up_date || null };
          if (existing) {
            update.mutate({ id: existing.id, body }, { onSuccess: (d) => (onClose(), onSaved?.(d.id)) });
          } else {
            create.mutate(body, { onSuccess: (d) => (onClose(), onSaved?.(d.id)) });
          }
        }}
      >
        <Field label="Title" htmlFor="dec-title">
          <Input
            id="dec-title"
            required
            minLength={3}
            value={form.title}
            onChange={(e) => patch({ title: e.target.value })}
            placeholder="Ship the sticky CTA to 100%"
          />
        </Field>
        <Field label="Decision" htmlFor="dec-decision" hint="One or two sentences. What are we doing?">
          <Textarea
            id="dec-decision"
            required
            minLength={3}
            value={form.decision}
            onChange={(e) => patch({ decision: e.target.value })}
            className="min-h-16"
          />
        </Field>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Context" htmlFor="dec-context">
            <Textarea
              id="dec-context"
              value={form.context ?? ""}
              onChange={(e) => patch({ context: e.target.value })}
              className="min-h-20"
            />
          </Field>
          <Field label="Evidence" htmlFor="dec-evidence">
            <Textarea
              id="dec-evidence"
              value={form.evidence ?? ""}
              onChange={(e) => patch({ evidence: e.target.value })}
              className="min-h-20"
            />
          </Field>
          <Field label="Alternatives considered" htmlFor="dec-alt">
            <Textarea
              id="dec-alt"
              value={form.alternatives ?? ""}
              onChange={(e) => patch({ alternatives: e.target.value })}
              className="min-h-20"
            />
          </Field>
          <Field
            label="Expected impact"
            htmlFor="dec-impact"
            hint="Something checkable on the follow-up date."
          >
            <Textarea
              id="dec-impact"
              value={form.expected_impact ?? ""}
              onChange={(e) => patch({ expected_impact: e.target.value })}
              className="min-h-20"
            />
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Status" htmlFor="dec-status">
            <Select
              id="dec-status"
              value={form.status ?? "decided"}
              onChange={(e) => patch({ status: e.target.value as DecisionCreate["status"] })}
            >
              <option value="proposed">Proposed</option>
              <option value="decided">Decided</option>
              <option value="superseded">Superseded</option>
            </Select>
          </Field>
          <Field label="Decided on" htmlFor="dec-date">
            <Input
              id="dec-date"
              type="date"
              value={form.decided_on ?? today}
              onChange={(e) => patch({ decided_on: e.target.value })}
            />
          </Field>
          <Field label="Follow-up" htmlFor="dec-follow">
            <Input
              id="dec-follow"
              type="date"
              value={form.follow_up_date ?? ""}
              onChange={(e) => patch({ follow_up_date: e.target.value || null })}
            />
          </Field>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Investigation" htmlFor="dec-inv">
            <Select
              id="dec-inv"
              value={form.investigation_id ?? ""}
              onChange={(e) => patch({ investigation_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">—</option>
              {(investigations.data ?? []).map((i) => (
                <option key={i.id} value={i.id}>
                  {i.title}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Experiment" htmlFor="dec-exp">
            <Select
              id="dec-exp"
              value={form.experiment_id ?? ""}
              onChange={(e) => patch({ experiment_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">—</option>
              {(experiments.data ?? []).map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Release" htmlFor="dec-rel">
            <Select
              id="dec-rel"
              value={form.release_id ?? ""}
              onChange={(e) => patch({ release_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">—</option>
              {(releases.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.version} · {r.platform}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {mutation.isError ? <ErrorState error={mutation.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={mutation.isPending}>
            {existing ? "Save" : "Record decision"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
