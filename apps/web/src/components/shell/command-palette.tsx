"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import {
  Activity,
  BookOpen,
  CornerDownLeft,
  FlaskConical,
  Gauge,
  LayoutList,
  Lightbulb,
  MessageSquareText,
  Rocket,
  Ruler,
  Search,
  SearchCheck,
  Sparkles,
  Tag,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "@/components/ui/badge";
import { type SearchHit, useSearch } from "@/lib/api/ops";
import { analystHref, entityHref } from "@/lib/links";
import { cn } from "@/lib/utils";

const TYPE_META: Record<string, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  investigation: { label: "Investigations", icon: SearchCheck },
  experiment: { label: "Experiments", icon: FlaskConical },
  release: { label: "Releases", icon: Rocket },
  decision: { label: "Decisions", icon: LayoutList },
  sop: { label: "SOPs", icon: BookOpen },
  knowledge: { label: "Knowledge", icon: Lightbulb },
  feedback: { label: "Feedback", icon: MessageSquareText },
  saved: { label: "Saved analyses", icon: Activity },
  metric: { label: "Metrics", icon: Gauge },
  dimension: { label: "Dimensions", icon: Ruler },
};
const TYPE_ORDER = Object.keys(TYPE_META);

const PAGES: { label: string; href: string; hint: string }[] = [
  { label: "Overview", href: "/", hint: "KPIs and what needs attention" },
  { label: "Analytics", href: "/analytics", hint: "Explore any metric" },
  { label: "Funnels", href: "/funnels", hint: "Step conversion" },
  { label: "Cohorts", href: "/cohorts", hint: "Retention by signup week" },
  { label: "Segments", href: "/segments", hint: "Saved audiences" },
  { label: "Investigations", href: "/investigations", hint: "Anomaly inbox and root cause" },
  { label: "Experiments", href: "/experiments", hint: "A/B tests and readouts" },
  { label: "Analyst", href: "/analyst", hint: "Ask a product question" },
  { label: "Product Ops", href: "/ops", hint: "SOPs, knowledge, feedback" },
  { label: "Releases", href: "/releases", hint: "What shipped when" },
  { label: "Decisions", href: "/decisions", hint: "Decision log" },
];

type Row =
  | { kind: "page"; key: string; label: string; hint: string; href: string }
  | { kind: "hit"; key: string; hit: SearchHit; href: string }
  | { kind: "ask"; key: string; label: string; href: string };

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQState] = useState("");
  const [cursor, setCursor] = useState(0);
  const setQ = (v: string) => {
    setQState(v);
    setCursor(0);
  };
  const router = useRouter();
  const search = useSearch(q, open);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const rows = useMemo<Row[]>(() => {
    const needle = q.trim().toLowerCase();
    if (needle.length < 2) {
      return PAGES.filter((p) => !needle || p.label.toLowerCase().includes(needle)).map((p) => ({
        kind: "page",
        key: `page-${p.href}`,
        ...p,
      }));
    }
    const out: Row[] = [];
    const groups = search.data?.groups ?? {};
    for (const type of TYPE_ORDER) {
      for (const hit of groups[type] ?? []) {
        out.push({
          kind: "hit",
          key: `${type}-${hit.id}-${hit.title}`,
          hit,
          href: entityHref(
            type,
            hit.id,
            Object.fromEntries(Object.entries(hit.extra ?? {}).map(([k, v]) => [k, String(v)])),
          ),
        });
      }
    }
    for (const p of PAGES) {
      if (p.label.toLowerCase().includes(needle)) out.push({ kind: "page", key: `page-${p.href}`, ...p });
    }
    out.push({
      kind: "ask",
      key: "ask",
      label: `Ask the analyst: “${q.trim()}”`,
      href: analystHref({ q: q.trim() }),
    });
    return out;
  }, [q, search.data]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>("[data-active=true]");
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  const go = (row: Row) => {
    setOpen(false);
    setQ("");
    router.push(row.href as "/");
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(rows.length - 1, c + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (e.key === "Enter" && rows[cursor]) {
      e.preventDefault();
      go(rows[cursor]);
    }
  };

  let lastType = "";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="border-border bg-surface text-fg-subtle hover:border-fg-faint hover:text-fg-muted hidden h-7 w-56 items-center gap-2 rounded-sm border px-2 text-xs transition-colors md:flex"
        aria-label="Search (⌘K)"
      >
        <Search className="size-3.5" />
        <span className="flex-1 text-left">Search…</span>
        <kbd className="text-2xs font-mono">⌘K</kbd>
      </button>
      <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="bg-fg/30 fixed inset-0 z-40" />
          <DialogPrimitive.Content
            className="border-border bg-bg fixed top-[12vh] left-1/2 z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-md border shadow-md focus:outline-none"
            onOpenAutoFocus={(e) => {
              e.preventDefault();
              inputRef.current?.focus();
            }}
          >
            <DialogPrimitive.Title className="sr-only">Search</DialogPrimitive.Title>
            <DialogPrimitive.Description className="sr-only">
              Search investigations, experiments, releases, decisions, SOPs, knowledge and feedback
            </DialogPrimitive.Description>
            <div className="border-border flex items-center gap-2 border-b px-3">
              <Search className="text-fg-faint size-4 shrink-0" aria-hidden />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Search everything, or jump to a page"
                className="text-fg placeholder:text-fg-faint h-11 flex-1 bg-transparent text-sm outline-none"
                role="combobox"
                aria-expanded
                aria-controls="palette-list"
                aria-activedescendant={rows[cursor] ? `palette-${rows[cursor].key}` : undefined}
                aria-autocomplete="list"
              />
              {search.isFetching ? <span className="text-fg-faint text-xs">searching…</span> : null}
            </div>
            <div ref={listRef} id="palette-list" role="listbox" className="max-h-[60vh] overflow-y-auto py-1">
              {rows.length === 0 ? (
                <p className="text-fg-subtle px-3 py-6 text-center text-xs">
                  {search.isPending && q.trim().length >= 2 ? "Searching…" : "No matches."}
                </p>
              ) : (
                rows.map((row, i) => {
                  const active = i === cursor;
                  let header: React.ReactNode = null;
                  const type = row.kind === "hit" ? row.hit.type : row.kind;
                  if (type !== lastType) {
                    lastType = type;
                    const label =
                      row.kind === "hit"
                        ? TYPE_META[row.hit.type]?.label
                        : row.kind === "page"
                          ? "Pages"
                          : "";
                    header = label ? (
                      <div className="text-fg-faint text-2xs mt-1 px-3 pt-1.5 pb-0.5 tracking-wide uppercase">
                        {label}
                      </div>
                    ) : null;
                  }
                  const Icon =
                    row.kind === "hit"
                      ? (TYPE_META[row.hit.type]?.icon ?? Tag)
                      : row.kind === "ask"
                        ? Sparkles
                        : CornerDownLeft;
                  return (
                    <div key={row.key}>
                      {header}
                      <button
                        type="button"
                        id={`palette-${row.key}`}
                        role="option"
                        aria-selected={active}
                        data-active={active}
                        onMouseEnter={() => setCursor(i)}
                        onClick={() => go(row)}
                        className={cn(
                          "flex w-full items-center gap-3 px-3 py-1.5 text-left text-[13px]",
                          active ? "bg-surface-2 text-fg" : "text-fg-muted",
                        )}
                      >
                        <Icon className={cn("size-3.5 shrink-0", active ? "text-fg" : "text-fg-faint")} />
                        {row.kind === "hit" ? (
                          <>
                            <span className="min-w-0 flex-1">
                              <span className="text-fg block truncate">{row.hit.title}</span>
                              {row.hit.subtitle ? (
                                <span className="text-fg-subtle block truncate text-xs">
                                  {row.hit.subtitle}
                                </span>
                              ) : null}
                            </span>
                            {row.hit.extra?.version ? (
                              <span className="text-fg-subtle font-mono text-xs">
                                {String(row.hit.extra?.version)}
                              </span>
                            ) : null}
                            {row.hit.status ? <StatusBadge status={row.hit.status} /> : null}
                          </>
                        ) : row.kind === "page" ? (
                          <>
                            <span className="text-fg flex-1">{row.label}</span>
                            <span className="text-fg-subtle text-xs">{row.hint}</span>
                          </>
                        ) : (
                          <span className="text-fg flex-1 truncate">{row.label}</span>
                        )}
                      </button>
                    </div>
                  );
                })
              )}
            </div>
            <div className="border-border text-fg-faint text-2xs flex items-center gap-3 border-t px-3 py-1.5">
              <span>↑↓ navigate</span>
              <span>↵ open</span>
              <span>esc close</span>
            </div>
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </>
  );
}
