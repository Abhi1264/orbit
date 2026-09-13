"use client";

import { Check, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menu";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import {
  type FindingKind,
  type FindingOut,
  type InvestigationOut,
  useInvestigationMutations,
} from "@/lib/api/investigations";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const KINDS: { kind: FindingKind; label: string; plural: string; help: string }[] = [
  {
    kind: "observation",
    label: "Observation",
    plural: "Observations",
    help: "What the data shows. No interpretation.",
  },
  {
    kind: "evidence",
    label: "Evidence",
    plural: "Evidence",
    help: "A fact that supports or refutes a hypothesis.",
  },
  {
    kind: "hypothesis",
    label: "Hypothesis",
    plural: "Hypotheses",
    help: "A testable explanation. Mark it supported or refuted as evidence lands.",
  },
  {
    kind: "recommendation",
    label: "Recommendation",
    plural: "Recommendations",
    help: "What to do about it, and why.",
  },
];

const STATE_TONE = { proposed: "neutral", supported: "success", refuted: "danger" } as const;
const CONFIDENCE_TONE = { high: "success", medium: "warning", low: "neutral" } as const;

function FindingRow({ f, invId, canEdit }: { f: FindingOut; invId: number; canEdit: boolean }) {
  const { updateFinding, deleteFinding } = useInvestigationMutations(invId);
  const isHypothesis = f.kind === "hypothesis";
  const setState = (state: "proposed" | "supported" | "refuted") =>
    updateFinding.mutate({ finding_id: f.id, body: { state } });

  return (
    <li
      className={cn(
        "border-border group rounded-md border px-3 py-2.5",
        f.state === "refuted" && "opacity-70",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={cn("text-fg text-[13px] font-medium", f.state === "refuted" && "line-through")}>
              {f.title}
            </span>
            {f.state ? <Badge tone={STATE_TONE[f.state]}>{f.state}</Badge> : null}
            {f.confidence ? <Badge tone={CONFIDENCE_TONE[f.confidence]}>{f.confidence}</Badge> : null}
            {f.source === "analyst" ? (
              <Badge tone="accent">AI analyst</Badge>
            ) : f.source === "system" ? (
              <Badge tone="neutral">auto</Badge>
            ) : null}
          </div>
          {f.body ? (
            <p className="text-fg-muted mt-1 text-xs leading-5 whitespace-pre-line">{f.body}</p>
          ) : null}
          <p className="text-fg-subtle text-2xs mt-1">
            {f.author?.name ?? "System"} · {formatDateTime(f.created_at)}
          </p>
        </div>
        {canEdit ? (
          <div className="flex shrink-0 items-center gap-0.5">
            {isHypothesis && f.state !== "supported" ? (
              <Tooltip content="Mark supported">
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Mark supported"
                  onClick={() => setState("supported")}
                >
                  <Check className="text-success size-3.5" />
                </Button>
              </Tooltip>
            ) : null}
            {isHypothesis && f.state !== "refuted" ? (
              <Tooltip content="Mark refuted">
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label="Mark refuted"
                  onClick={() => setState("refuted")}
                >
                  <X className="text-danger size-3.5" />
                </Button>
              </Tooltip>
            ) : null}
            {isHypothesis && f.state !== "proposed" ? (
              <Button size="sm" variant="ghost" onClick={() => setState("proposed")}>
                Reopen
              </Button>
            ) : null}
            <Tooltip content="Delete">
              <Button
                size="icon"
                variant="ghost"
                aria-label="Delete finding"
                className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                onClick={() => deleteFinding.mutate(f.id)}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </Tooltip>
          </div>
        ) : null}
      </div>
    </li>
  );
}

function AddFindingForm({
  invId,
  defaultKind,
  onClose,
}: {
  invId: number;
  defaultKind: FindingKind;
  onClose: () => void;
}) {
  const { addFinding } = useInvestigationMutations(invId);
  const [kind, setKind] = useState<FindingKind>(defaultKind);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [confidence, setConfidence] = useState<"" | "low" | "medium" | "high">("");
  const help = KINDS.find((k) => k.kind === kind)?.help;

  return (
    <form
      className="border-border bg-surface space-y-3 rounded-md border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        addFinding.mutate({ kind, title, body, confidence: confidence || null }, { onSuccess: onClose });
      }}
    >
      <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
        <Field label="Kind" htmlFor="finding-kind" hint={help}>
          <Select id="finding-kind" value={kind} onChange={(e) => setKind(e.target.value as FindingKind)}>
            {KINDS.map((k) => (
              <option key={k.kind} value={k.kind}>
                {k.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Title" htmlFor="finding-title">
          <Input
            id="finding-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus
            maxLength={200}
          />
        </Field>
      </div>
      <Field label="Detail" htmlFor="finding-body">
        <Textarea
          id="finding-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="min-h-16"
        />
      </Field>
      {kind === "hypothesis" || kind === "recommendation" ? (
        <Field label="Confidence" htmlFor="finding-confidence" className="w-40">
          <Select
            id="finding-confidence"
            value={confidence}
            onChange={(e) => setConfidence(e.target.value as typeof confidence)}
          >
            <option value="">Unstated</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </Select>
        </Field>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" size="sm" loading={addFinding.isPending}>
          Add {kind}
        </Button>
      </div>
    </form>
  );
}

export function FindingsPanel({ inv, canEdit }: { inv: InvestigationOut; canEdit: boolean }) {
  const [adding, setAdding] = useState<FindingKind | null>(null);
  const grouped = KINDS.map((k) => ({ ...k, items: inv.findings.filter((f) => f.kind === k.kind) }));
  const hypotheses = grouped.find((g) => g.kind === "hypothesis")?.items ?? [];
  const supported = hypotheses.filter((h) => h.state === "supported").length;
  const refuted = hypotheses.filter((h) => h.state === "refuted").length;

  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            Findings
            {hypotheses.length ? (
              <span className="text-fg-subtle text-xs font-normal">
                {hypotheses.length} hypotheses · {supported} supported · {refuted} refuted
              </span>
            ) : null}
          </span>
        }
        description="Kept separate on purpose: what we saw, what we can prove, what we think, and what we should do."
        actions={
          canEdit && adding === null ? (
            <Button size="sm" onClick={() => setAdding("evidence")}>
              <Plus className="size-3.5" />
              Add finding
            </Button>
          ) : null
        }
      />
      <PanelBody className="space-y-4">
        {adding !== null ? (
          <AddFindingForm invId={inv.id} defaultKind={adding} onClose={() => setAdding(null)} />
        ) : null}
        {grouped.map((g) =>
          g.items.length || g.kind === "hypothesis" ? (
            <section key={g.kind}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <h3 className="text-2xs text-fg-subtle uppercase">{g.plural}</h3>
                {canEdit && adding === null ? (
                  <button
                    type="button"
                    onClick={() => setAdding(g.kind)}
                    className="text-fg-subtle hover:text-fg text-2xs"
                  >
                    + {g.label.toLowerCase()}
                  </button>
                ) : null}
              </div>
              {g.items.length ? (
                <ul className="space-y-1.5">
                  {g.items.map((f) => (
                    <FindingRow key={f.id} f={f} invId={inv.id} canEdit={canEdit} />
                  ))}
                </ul>
              ) : (
                <p className="text-fg-faint text-xs">
                  No hypotheses yet. Promote a root-cause candidate above, or write your own.
                </p>
              )}
            </section>
          ) : null,
        )}
      </PanelBody>
    </Panel>
  );
}
