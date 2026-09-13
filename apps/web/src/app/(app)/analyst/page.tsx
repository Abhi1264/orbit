"use client";

import { CornerDownLeft, Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AnswerView, EvidenceList } from "@/components/analyst/answer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ErrorState, Skeleton } from "@/components/ui/states";
import {
  type AskContext,
  type AskResponse,
  useAnalystStatus,
  useAsk,
  useRun,
  useRuns,
  useSuggestions,
} from "@/lib/api/ai";
import type { Filter } from "@/lib/api/analytics";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function parseFilters(raw: string | null): Filter[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? (v as Filter[]) : [];
  } catch {
    return [];
  }
}

function AnswerSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Analysing">
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-5 w-2/3" />
      <div className="grid gap-6 pt-2 lg:grid-cols-2">
        <div className="space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      </div>
    </div>
  );
}

export default function AnalystPage() {
  const params = useSearchParams();
  const status = useAnalystStatus();
  const ask = useAsk();
  const runs = useRuns(12);

  // Where the user came from: the analyst defaults to the page's metric, scope and window.
  const context: AskContext = useMemo(
    () => ({
      metric: params.get("metric"),
      date_from: params.get("from"),
      date_to: params.get("to"),
      filters: parseFilters(params.get("f")),
      experiment_id: params.get("experiment_id") ? Number(params.get("experiment_id")) : null,
      investigation_id: params.get("investigation_id") ? Number(params.get("investigation_id")) : null,
    }),
    [params],
  );
  const suggestions = useSuggestions({
    metric: context.metric,
    experiment_id: context.experiment_id ?? undefined,
    investigation_id: context.investigation_id ?? undefined,
  });

  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [current, setCurrent] = useState<AskResponse | null>(null);
  const [selectedRun, setSelectedRun] = useState<number | null>(null);
  const [activeCall, setActiveCall] = useState<string | null>(null);
  const replay = useRun(selectedRun);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = useCallback(
    (q: string) => {
      const text = q.trim();
      if (text.length < 3 || ask.isPending) return;
      setQuestion(text);
      setSelectedRun(null);
      setActiveCall(null);
      ask.mutate({ question: text, context }, { onSuccess: (r) => setCurrent(r) });
    },
    [ask, context],
  );

  // Deep link: /analyst?q=... asks immediately.
  const autoAsked = useRef(false);
  useEffect(() => {
    const q = params.get("q");
    if (q && !autoAsked.current) {
      autoAsked.current = true;
      submit(q);
    }
  }, [params, submit]);

  const onCite = (id: string) => {
    setActiveCall((prev) => (prev === id ? null : id));
    document.getElementById(`evidence-${id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  // A selected history item is shown in place of the live answer while it loads/renders.
  const shown = selectedRun !== null ? (replay.data ?? null) : current;
  const isReplay = selectedRun !== null && shown?.run_id === selectedRun;

  return (
    <>
      <PageHeader
        title="Analyst"
        description="Ask a product question. The analyst runs the same queries you would, then separates what the data says from what it thinks."
        actions={
          status.data ? (
            <Badge tone={status.data.llm_enabled ? "accent" : "neutral"} className="h-6 px-2">
              <Sparkles className="size-3" />
              {status.data.llm_enabled ? `LLM · ${status.data.model}` : "Demo mode · deterministic playbooks"}
            </Badge>
          ) : null
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <Panel>
            <PanelBody className="p-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  submit(question);
                }}
              >
                <label htmlFor="question" className="sr-only">
                  Question
                </label>
                <div className="border-border focus-within:border-accent flex items-end gap-2 rounded-md border px-3 py-2 transition-colors">
                  <textarea
                    id="question"
                    ref={textareaRef}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        submit(question);
                      }
                    }}
                    rows={2}
                    placeholder="Why did conversion fall last week on Android?"
                    className="text-fg placeholder:text-fg-faint min-h-11 flex-1 resize-none bg-transparent text-[14px] leading-snug outline-none"
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    loading={ask.isPending}
                    disabled={question.trim().length < 3}
                  >
                    Ask <CornerDownLeft className="size-3 opacity-70" />
                  </Button>
                </div>
              </form>
              {context.metric || context.experiment_id || context.investigation_id ? (
                <p className="text-fg-subtle mt-2 text-xs">
                  Context:{" "}
                  {[
                    context.metric && `metric ${context.metric}`,
                    context.date_from && context.date_to && `${context.date_from} → ${context.date_to}`,
                    context.filters?.length ? `${context.filters.length} filter(s)` : null,
                    context.experiment_id && `experiment #${context.experiment_id}`,
                    context.investigation_id && `investigation #${context.investigation_id}`,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              ) : null}
              {suggestions.data?.length ? (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {suggestions.data.map((s) => (
                    <button
                      key={s.text}
                      type="button"
                      onClick={() => submit(s.text)}
                      className="border-border text-fg-muted hover:border-accent hover:text-accent rounded-full border px-2.5 py-0.5 text-xs transition-colors"
                    >
                      {s.text}
                    </button>
                  ))}
                </div>
              ) : null}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title={shown ? shown.question : "Answer"}
              description={
                shown ? (
                  <span className="inline-flex flex-wrap items-center gap-2">
                    <span>
                      {shown.mode === "llm" ? `LLM · ${shown.model}` : "Deterministic playbook"} ·{" "}
                      {shown.tool_calls.length} tool call{shown.tool_calls.length === 1 ? "" : "s"} ·{" "}
                      {(shown.latency_ms / 1000).toFixed(1)}s
                    </span>
                    {isReplay ? <Badge>Replayed from history</Badge> : null}
                  </span>
                ) : (
                  "Facts cite the tool call that produced them; inferences carry a confidence."
                )
              }
            />
            <PanelBody className="py-4">
              {ask.isPending || (selectedRun !== null && replay.isPending) ? (
                <AnswerSkeleton />
              ) : ask.isError ? (
                <ErrorState
                  error={ask.error}
                  onRetry={() => submit(question)}
                  title="The analyst could not answer"
                />
              ) : shown ? (
                <AnswerView response={shown} activeCall={activeCall} onCite={onCite} onFollowUp={submit} />
              ) : (
                <div className="text-fg-subtle py-6 text-center text-[13px]">
                  <p>Ask about a metric move, a funnel, an experiment, or what needs attention.</p>
                  <p className="text-fg-faint mt-1 text-xs">
                    Every number in the answer comes from a query you can inspect on the right.
                  </p>
                </div>
              )}
            </PanelBody>
          </Panel>
        </div>

        <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <Panel>
            <PanelHeader
              title="Evidence"
              description={shown ? "Tool calls in the order they ran." : "Appears once a question is asked."}
            />
            <div className="max-h-[60vh] overflow-y-auto">
              {shown ? (
                <EvidenceList calls={shown.tool_calls} active={activeCall} onSelect={setActiveCall} />
              ) : null}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Recent questions" />
            {runs.isPending ? (
              <div className="space-y-2 p-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : runs.data?.length ? (
              <ul className="divide-border divide-y">
                {runs.data.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedRun(r.id);
                        setQuestion(r.question);
                        setActiveCall(null);
                      }}
                      className={cn(
                        "hover:bg-surface flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left",
                        shown?.run_id === r.id && "bg-surface",
                      )}
                    >
                      <span className="text-fg line-clamp-1 text-[13px]">{r.question}</span>
                      <span className="text-fg-faint text-[11px]">
                        {formatDateTime(r.created_at)} · {r.tool_count} tools ·{" "}
                        {(r.latency_ms / 1000).toFixed(1)}s{r.error ? " · fell back" : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-fg-faint px-3 py-4 text-xs">Nothing asked yet.</p>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
