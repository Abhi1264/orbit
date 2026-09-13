"use client";

import { CornerDownLeft, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { type PlanResponse, usePlan } from "@/lib/api/ai";
import type { Filter } from "@/lib/api/analytics";
import { usePermission } from "@/lib/api/hooks";
import { analystHref } from "@/lib/links";

/**
 * "Describe the query" input above the explorer controls. The planner is deterministic
 * (no LLM call), so this is instant and works in demo mode. The explanation shows the
 * user exactly how their words were read before the view changes.
 */
export function NlQueryBar({
  context,
  onApply,
}: {
  context: { metric: string; filters: Filter[]; from: string; to: string };
  onApply: (q: PlanResponse["query"]) => void;
}) {
  const [text, setText] = useState("");
  const [last, setLast] = useState<PlanResponse | null>(null);
  const plan = usePlan();
  const canAsk = usePermission("use_analyst");
  if (!canAsk) return null;

  const submit = () => {
    const t = text.trim();
    if (t.length < 2 || plan.isPending) return;
    plan.mutate(
      {
        text: t,
        context: {
          metric: context.metric,
          filters: context.filters,
          date_from: context.from,
          date_to: context.to,
        },
      },
      {
        onSuccess: (r) => {
          setLast(r);
          onApply(r.query);
        },
      },
    );
  };

  return (
    <div className="mb-3">
      <form
        className="border-border bg-bg focus-within:border-accent flex items-center gap-2 rounded-md border px-3 py-1.5 transition-colors"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Sparkles className="text-fg-faint size-3.5 shrink-0" aria-hidden />
        <label htmlFor="nl-query" className="sr-only">
          Describe a query
        </label>
        <input
          id="nl-query"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe it instead: “payment success rate on android by payment method last 30 days”"
          className="text-fg placeholder:text-fg-faint h-6 flex-1 bg-transparent text-[13px] outline-none"
        />
        <Button
          type="submit"
          size="sm"
          variant="ghost"
          loading={plan.isPending}
          disabled={text.trim().length < 2}
        >
          Apply <CornerDownLeft className="size-3 opacity-60" />
        </Button>
      </form>
      {last ? (
        <p className="text-fg-subtle mt-1 flex flex-wrap items-center gap-x-2 px-1 text-xs">
          <span>
            Read as <span className="text-fg">{last.explanation}</span>
          </span>
          {last.unresolved?.length ? (
            <span className="text-warning">Ignored: {last.unresolved.join(", ")}</span>
          ) : null}
          <Link
            href={analystHref({
              q: `Why did ${last.query.metric.replace(/_/g, " ")} change?`,
              metric: last.query.metric,
              filters: last.query.filters,
              from: last.query.date_from,
              to: last.query.date_to,
            })}
            className="text-accent hover:underline"
          >
            Ask the analyst why →
          </Link>
        </p>
      ) : null}
    </div>
  );
}
