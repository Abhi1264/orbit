"use client";

import { ArrowUpRight, ChevronDown } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AnalystAnswer, AskResponse, ToolCallRecord } from "@/lib/api/ai";
import { cn } from "@/lib/utils";

const CONF_TONE: Record<string, BadgeTone> = { high: "success", medium: "info", low: "neutral" };
const PRIORITY_LABEL: Record<string, string> = { now: "Now", next: "Next", later: "Later" };
const PRIORITY_TONE: Record<string, BadgeTone> = { now: "danger", next: "warning", later: "neutral" };
const KIND_LABEL: Record<string, string> = {
  segment: "Segment",
  release: "Release",
  experiment: "Experiment",
  mix_shift: "Mix shift",
};

/** Small inline chip that points at the tool call which produced a number. */
export function Cite({
  id,
  active,
  onClick,
}: {
  id: string;
  active?: boolean;
  onClick?: (id: string) => void;
}) {
  const className = cn(
    "text-2xs inline-flex h-4 items-center rounded-sm border px-1 align-middle font-mono leading-none transition-colors",
    active
      ? "border-accent bg-accent text-white"
      : "border-border bg-surface-2 text-fg-subtle hover:border-accent hover:text-accent",
  );
  // Without a handler it is a label (e.g. inside the evidence row, which is itself a button).
  if (!onClick) return <span className={className}>{id}</span>;
  return (
    <button type="button" onClick={() => onClick(id)} title={`Evidence ${id}`} className={className}>
      {id}
    </button>
  );
}

function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h3 className="text-fg-subtle mb-2 flex items-baseline gap-1.5 text-[11px] font-medium tracking-wide uppercase">
      {children}
      {count !== undefined ? <span className="tabular text-fg-faint normal-case">{count}</span> : null}
    </h3>
  );
}

export function AnswerView({
  response,
  activeCall,
  onCite,
  onFollowUp,
}: {
  response: AskResponse;
  activeCall: string | null;
  onCite: (id: string) => void;
  onFollowUp: (q: string) => void;
}) {
  // Pydantic default_factory fields are optional in the generated types; fill them in once.
  const raw: AnalystAnswer = response.answer;
  const a = {
    summary: raw.summary,
    facts: raw.facts ?? [],
    inferences: (raw.inferences ?? []).map((i) => ({ ...i, basis: i.basis ?? [] })),
    candidates: raw.candidates ?? [],
    recommendations: raw.recommendations ?? [],
    follow_ups: raw.follow_ups ?? [],
    links: raw.links ?? [],
    caveats: raw.caveats ?? [],
  };
  const groups = ["now", "next", "later"] as const;
  return (
    <div className="space-y-6">
      <p className="text-fg max-w-3xl text-[15px] leading-relaxed">{a.summary}</p>

      {a.candidates.length ? (
        <section>
          <SectionTitle count={a.candidates.length}>Root-cause candidates</SectionTitle>
          <ol className="divide-border border-border divide-y rounded-md border">
            {a.candidates.map((c, i) => (
              <li key={i} className="flex gap-3 px-3 py-2.5">
                <span className="tabular text-fg-faint w-4 shrink-0 pt-px text-xs">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {c.href ? (
                      <Link
                        href={c.href as "/"}
                        className="text-fg hover:text-accent text-[13px] font-medium underline-offset-2 hover:underline"
                      >
                        {c.title}
                      </Link>
                    ) : (
                      <span className="text-fg text-[13px] font-medium">{c.title}</span>
                    )}
                    <Badge tone={CONF_TONE[c.confidence]}>{c.confidence}</Badge>
                    <Badge>{KIND_LABEL[c.kind] ?? c.kind}</Badge>
                  </div>
                  <p className="text-fg-muted mt-0.5 text-xs leading-relaxed">{c.evidence}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <SectionTitle count={a.facts.length}>Facts</SectionTitle>
          {a.facts.length ? (
            <ul className="space-y-1.5">
              {a.facts.map((f, i) => (
                <li key={i} className="text-fg flex gap-2 text-[13px] leading-snug">
                  <span className="min-w-0 flex-1">
                    {f.text} <Cite id={f.source} active={activeCall === f.source} onClick={onCite} />
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-fg-faint text-xs">No facts were returned.</p>
          )}
        </section>
        <section>
          <SectionTitle count={a.inferences.length}>Inferences</SectionTitle>
          {a.inferences.length ? (
            <ul className="space-y-2">
              {a.inferences.map((inf, i) => (
                <li key={i} className="text-[13px] leading-snug">
                  <span className="text-fg">{inf.text}</span>{" "}
                  <span className="inline-flex flex-wrap items-center gap-1 align-middle">
                    <Badge tone={CONF_TONE[inf.confidence]}>{inf.confidence}</Badge>
                    {inf.basis.map((b) => (
                      <Cite key={b} id={b} active={activeCall === b} onClick={onCite} />
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-fg-faint text-xs">No interpretation beyond the facts.</p>
          )}
        </section>
      </div>

      {a.recommendations.length ? (
        <section>
          <SectionTitle count={a.recommendations.length}>Recommendations</SectionTitle>
          <ul className="space-y-1.5">
            {groups.flatMap((g) =>
              a.recommendations
                .filter((r) => r.priority === g)
                .map((r, i) => (
                  <li key={`${g}-${i}`} className="flex items-start gap-2 text-[13px] leading-snug">
                    <Badge tone={PRIORITY_TONE[g]} className="mt-px w-10 shrink-0 justify-center">
                      {PRIORITY_LABEL[g]}
                    </Badge>
                    <span className="text-fg">{r.text}</span>
                  </li>
                )),
            )}
          </ul>
        </section>
      ) : null}

      {a.links.length ? (
        <div className="flex flex-wrap gap-2">
          {a.links.map((l, i) => (
            <Link
              key={i}
              href={l.href as "/"}
              className="border-border bg-bg text-fg hover:bg-surface-2 inline-flex h-7 items-center gap-1 rounded-sm border px-2 text-xs"
            >
              {l.label} <ArrowUpRight className="size-3 opacity-60" />
            </Link>
          ))}
        </div>
      ) : null}

      {a.caveats.length ? (
        <section className="border-border bg-surface rounded-md border px-3 py-2">
          <SectionTitle>Caveats</SectionTitle>
          <ul className="text-fg-muted list-disc space-y-1 pl-4 text-xs leading-snug">
            {a.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {a.follow_ups.length ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-fg-subtle mr-1 text-xs">Ask next:</span>
          {a.follow_ups.map((q) => (
            <Button
              key={q}
              size="sm"
              variant="ghost"
              className="border-border border"
              onClick={() => onFollowUp(q)}
            >
              {q}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ evidence drawer

function fmtArgs(args: Record<string, unknown>) {
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
    .join("  ");
}

type CellFormat = "pct" | "num" | "money" | "p" | "text";

function DataTable({
  rows,
  columns,
  formats = {},
}: {
  rows: Record<string, unknown>[];
  columns: [string, string][];
  formats?: Record<string, CellFormat | ((row: Record<string, unknown>) => CellFormat)>;
}) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-fg-subtle text-left">
          {columns.map(([k, label]) => (
            <th key={k} className="py-1 pr-3 font-medium">
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="tabular">
        {rows.map((r, i) => (
          <tr key={i} className="border-border border-t">
            {columns.map(([k]) => (
              <td key={k} className="py-1 pr-3 whitespace-nowrap">
                {fmtCell(r[k], typeof formats[k] === "function" ? formats[k](r) : formats[k])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function fmtCell(v: unknown, fmt: CellFormat = "text"): string {
  if (v === null || v === undefined) return "—";
  if (typeof v !== "number") return String(v);
  switch (fmt) {
    case "pct":
      return `${(v * 100).toFixed(1)}%`;
    case "money":
      return `₹${Math.round(v).toLocaleString("en-IN")}`;
    case "p":
      return v < 0.001 ? v.toExponential(2) : v.toFixed(3);
    case "num":
      return Number.isInteger(v) ? v.toLocaleString("en-IN") : v.toFixed(2);
    default:
      return Number.isInteger(v) ? v.toLocaleString("en-IN") : v.toFixed(2);
  }
}

/** Metric values follow the metric's own format; the tool payload carries it. */
function metricFormat(d: Record<string, unknown>): CellFormat {
  const f = String(d.format ?? "");
  if (f === "percent") return "pct";
  if (f === "currency") return "money";
  return "num";
}

function ToolData({ call }: { call: ToolCallRecord }) {
  const d = (call.data ?? {}) as Record<string, unknown>;
  if (call.name === "breakdown_metric" && Array.isArray(d.rows)) {
    return (
      <DataTable
        rows={d.rows as Record<string, unknown>[]}
        columns={[
          ["segment", String(d.dimension_label ?? "Segment")],
          ["value", "Value"],
          ["previous", "Previous"],
          ["rel_change", "Change"],
          ["share", "Share"],
        ]}
        formats={{ value: metricFormat(d), previous: metricFormat(d), rel_change: "pct", share: "pct" }}
      />
    );
  }
  if (call.name === "root_cause" && Array.isArray(d.candidates)) {
    return (
      <DataTable
        rows={d.candidates as Record<string, unknown>[]}
        columns={[
          ["rank", "#"],
          ["title", "Candidate"],
          ["kind", "Kind"],
          ["confidence", "Confidence"],
          ["explained", "Explained"],
        ]}
        formats={{ explained: "pct" }}
      />
    );
  }
  if (call.name === "list_anomalies" && Array.isArray(d.anomalies)) {
    return (
      <DataTable
        rows={d.anomalies as Record<string, unknown>[]}
        columns={[
          ["label", "Metric"],
          ["scope", "Scope"],
          ["actual", "Actual"],
          ["expected", "Expected"],
          ["zscore", "z"],
          ["severity", "Severity"],
          ["status", "Status"],
        ]}
        formats={{ zscore: "num" }}
      />
    );
  }
  if (call.name === "list_releases" && Array.isArray(d.releases)) {
    return (
      <DataTable
        rows={d.releases as Record<string, unknown>[]}
        columns={[
          ["release_date", "Date"],
          ["platform", "Platform"],
          ["version", "Version"],
          ["name", "Name"],
          ["status", "Status"],
        ]}
      />
    );
  }
  if (call.name === "experiment_results" && Array.isArray(d.metrics)) {
    return (
      <DataTable
        rows={d.metrics as Record<string, unknown>[]}
        columns={[
          ["label", "Metric"],
          ["role", "Role"],
          ["control", "Control"],
          ["treatment", "Treatment"],
          ["rel_diff", "Lift"],
          ["p_value", "p"],
          ["direction", "Read"],
        ]}
        formats={{ rel_diff: "pct", p_value: "p", control: metricFormat, treatment: metricFormat }}
      />
    );
  }
  if (call.name === "get_metric_summary" && Array.isArray(d.daily)) {
    const daily = d.daily as [string, number | null][];
    return (
      <DataTable
        rows={daily.map(([b, v]) => ({ day: b.slice(0, 10), value: v }))}
        columns={[
          ["day", "Day"],
          ["value", "Value"],
        ]}
        formats={{ value: metricFormat(d) }}
      />
    );
  }
  return (
    <pre className="text-fg-muted max-h-72 overflow-auto font-mono text-[11px] leading-snug">
      {JSON.stringify(d, null, 2)}
    </pre>
  );
}

export function EvidenceList({
  calls,
  active,
  onSelect,
}: {
  calls: ToolCallRecord[];
  active: string | null;
  onSelect: (id: string | null) => void;
}) {
  if (!calls.length) {
    return <p className="text-fg-faint px-4 py-6 text-center text-xs">No tools were called.</p>;
  }
  return (
    <ol className="divide-border divide-y">
      {calls.map((c) => {
        const open = active === c.id;
        return (
          <li key={c.id} id={`evidence-${c.id}`} className={cn(open && "bg-surface")}>
            <button
              type="button"
              onClick={() => onSelect(open ? null : c.id)}
              aria-expanded={open}
              className="flex w-full items-start gap-2 px-3 py-2 text-left"
            >
              <Cite id={c.id} active={open} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-fg font-mono text-xs">{c.name}</span>
                  <span className="tabular text-fg-faint ml-auto shrink-0 text-[11px]">{c.ms} ms</span>
                  <ChevronDown
                    className={cn("text-fg-faint size-3 shrink-0 transition-transform", open && "rotate-180")}
                  />
                </div>
                <div className="text-fg-subtle mt-0.5 truncate font-mono text-[11px]">{fmtArgs(c.args)}</div>
                {c.error ? (
                  <div className="text-danger mt-1 text-xs">{c.error}</div>
                ) : (
                  <div className={cn("text-fg-muted mt-1 text-xs leading-snug", !open && "line-clamp-2")}>
                    {c.summary}
                  </div>
                )}
              </div>
            </button>
            {open && c.data ? (
              <div className="border-border border-t px-3 py-2">
                <ToolData call={c} />
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
