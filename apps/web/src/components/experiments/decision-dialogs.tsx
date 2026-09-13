"use client";

import { Check, Copy, Download } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Select, Textarea } from "@/components/ui/input";
import { ErrorState, Skeleton } from "@/components/ui/states";
import {
  type ExperimentDecision,
  type ExperimentOut,
  type Recommendation,
  useExperimentMemo,
  useExperimentMutations,
} from "@/lib/api/experiments";

const DECISIONS: { value: ExperimentDecision; label: string; help: string }[] = [
  { value: "ship", label: "Ship", help: "Roll the winning variant out to everyone." },
  {
    value: "iterate",
    label: "Iterate",
    help: "The idea has legs but this version does not ship; design a follow-up.",
  },
  { value: "stop", label: "Stop", help: "Abandon the change; record what was learned." },
  { value: "continue", label: "Keep running", help: "Not enough evidence yet; revisit on a set date." },
];

export function DecisionDialog({
  exp,
  rec,
  open,
  onClose,
}: {
  exp: ExperimentOut;
  rec: Recommendation | undefined;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      {open ? <DecisionForm exp={exp} rec={rec} onClose={onClose} /> : null}
    </Dialog>
  );
}

function DecisionForm({
  exp,
  rec,
  onClose,
}: {
  exp: ExperimentOut;
  rec: Recommendation | undefined;
  onClose: () => void;
}) {
  const { decide } = useExperimentMutations(exp.id);
  const [decision, setDecision] = useState<ExperimentDecision>(exp.decision ?? rec?.decision ?? "continue");
  const [reason, setReason] = useState(
    exp.decision_reason || (rec ? [rec.headline + ".", ...rec.reasons].join("\n") : ""),
  );
  const [log, setLog] = useState(true);
  const differs = rec && decision !== rec.decision;

  return (
    <DialogContent
      title="Record decision"
      description="The decision is yours, not the rule engine's. If you overrule the recommendation, say why: the decision log is read months later by people without the context."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          decide.mutate({ decision, reason, log }, { onSuccess: onClose });
        }}
      >
        <Field
          label="Decision"
          htmlFor="dec-decision"
          hint={DECISIONS.find((d) => d.value === decision)?.help}
        >
          <Select
            id="dec-decision"
            value={decision}
            onChange={(e) => setDecision(e.target.value as ExperimentDecision)}
          >
            {DECISIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
                {rec?.decision === d.value ? " (recommended)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        {differs ? (
          <p className="border-warning/30 bg-warning-soft text-warning rounded-sm border px-2.5 py-1.5 text-xs">
            This overrules the rule-based recommendation ({rec.decision}). The memo will show both.
          </p>
        ) : null}
        <Field
          label="Rationale"
          htmlFor="dec-reason"
          hint="Plain language. Numbers are in the readout; this is the judgement."
        >
          <Textarea
            id="dec-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            className="min-h-28"
          />
        </Field>
        <label className="text-fg-muted flex items-center gap-2 text-xs">
          <input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} />
          Add an entry to the decision log
        </label>
        {decide.isError ? <ErrorState error={decide.error} className="py-2" /> : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={decide.isPending}>
            Record decision
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

// --------------------------------------------------------------------------- memo

export function MemoDialog({
  exp,
  open,
  onClose,
}: {
  exp: ExperimentOut;
  open: boolean;
  onClose: () => void;
}) {
  const memo = useExperimentMemo(exp.id, open);
  const [copied, setCopied] = useState(false);
  const md = memo.data?.markdown ?? "";

  const copy = async () => {
    await navigator.clipboard.writeText(md);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const download = () => {
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${exp.key}-decision-memo.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      <DialogContent
        title="Decision memo"
        description="Generated from the readout; every number traces to a query. Paste it into the decision doc as-is, or edit it there."
        wide
      >
        {memo.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : memo.isError ? (
          <ErrorState error={memo.error} onRetry={() => memo.refetch()} />
        ) : (
          <div className="memo border-border bg-surface max-h-[60vh] overflow-y-auto rounded-sm border px-4 py-3">
            <Markdown remarkPlugins={[remarkGfm]}>{md}</Markdown>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={download} disabled={!md}>
            <Download className="size-3.5" />
            Download .md
          </Button>
          <Button type="button" variant="secondary" onClick={copy} disabled={!md}>
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
            {copied ? "Copied" : "Copy markdown"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
