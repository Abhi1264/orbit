"use client";

import { Link2, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge, type BadgeTone, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/states";
import { SegmentedControl } from "@/components/ui/tabs";
import { useExperiments } from "@/lib/api/experiments";
import { usePermission } from "@/lib/api/hooks";
import { useInvestigations } from "@/lib/api/investigations";
import {
  type FeedbackCreate,
  type FeedbackOut,
  type FeedbackSentiment,
  type FeedbackSource,
  type FeedbackStatus,
  useFeedback,
  useFeedbackThemes,
  useOpsMutations,
  useReleases,
  useStakeholders,
} from "@/lib/api/ops";
import { formatDate, titleCase } from "@/lib/format";
import { entityHref } from "@/lib/links";
import { cn } from "@/lib/utils";
import { useUrlState } from "@/lib/url-state";

const SENTIMENT_TONE: Record<FeedbackSentiment, BadgeTone> = {
  negative: "danger",
  neutral: "neutral",
  positive: "success",
};
const SOURCE_LABEL: Record<FeedbackSource, string> = {
  support: "Support",
  interview: "Interview",
  survey: "Survey",
  sales: "Sales",
  app_review: "App review",
  internal: "Internal",
};
const STATUSES: FeedbackStatus[] = ["new", "triaged", "planned", "addressed", "dismissed"];

type View = "open" | "all";

export function FeedbackTab() {
  const url = useUrlState();
  const view = (url.get("view") as View | null) ?? "open";
  const theme = url.get("theme") ?? undefined;
  const themes = useFeedbackThemes();
  const items = useFeedback({ open_only: view === "open", theme });
  const canManage = usePermission("manage_ops");
  const [creating, setCreating] = useState(false);
  const [linking, setLinking] = useState<FeedbackOut | null>(null);
  const { updateFeedback } = useOpsMutations();

  return (
    <div className="grid gap-4 xl:grid-cols-[18rem_minmax(0,1fr)]">
      <Panel className="self-start">
        <PanelHeader title="Themes" description="What keeps coming up. Sorted by open items." />
        {themes.isPending ? (
          <TableSkeleton rows={5} cols={2} />
        ) : themes.isError ? (
          <PanelBody>
            <ErrorState error={themes.error} />
          </PanelBody>
        ) : (
          <ul>
            <li>
              <button
                type="button"
                onClick={() => url.set({ theme: null })}
                className={cn(
                  "border-border hover:bg-surface flex w-full items-center justify-between border-b px-4 py-2 text-left text-[13px]",
                  !theme && "bg-surface",
                )}
              >
                <span className="text-fg">All themes</span>
                <span className="tabular text-fg-subtle text-xs">
                  {themes.data.reduce((s, t) => s + t.open, 0)} open
                </span>
              </button>
            </li>
            {themes.data.map((t) => (
              <li key={t.theme}>
                <button
                  type="button"
                  onClick={() => url.set({ theme: t.theme })}
                  className={cn(
                    "border-border hover:bg-surface flex w-full items-center justify-between gap-2 border-b px-4 py-2 text-left text-[13px] last:border-b-0",
                    theme === t.theme && "bg-surface",
                  )}
                >
                  <span className="min-w-0">
                    <span className="text-fg block">{titleCase(t.theme)}</span>
                    <span className="text-fg-faint text-2xs">last {formatDate(t.last_received)}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {t.negative ? (
                      <span className="text-danger tabular text-xs" title="negative">
                        {t.negative}−
                      </span>
                    ) : null}
                    <span className="tabular text-fg-subtle text-xs">
                      {t.open}/{t.total}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title={theme ? titleCase(theme) : "All feedback"}
          description="Stakeholder and customer signals, each tied to the work that answers it."
          actions={
            <>
              <SegmentedControl<View>
                label="Feedback view"
                value={view}
                onChange={(v) => url.set({ view: v === "open" ? null : v })}
                options={[
                  { value: "open", label: "Open" },
                  { value: "all", label: "All" },
                ]}
              />
              {canManage ? (
                <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
                  <Plus className="size-3.5" /> Log feedback
                </Button>
              ) : null}
            </>
          }
        />
        {items.isPending ? (
          <PanelBody className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </PanelBody>
        ) : items.isError ? (
          <PanelBody>
            <ErrorState error={items.error} />
          </PanelBody>
        ) : items.data.length === 0 ? (
          <EmptyState
            title="Nothing here"
            description={
              view === "open" ? "No open feedback for this theme." : "No feedback logged for this theme."
            }
          />
        ) : (
          <ul>
            {items.data.map((f) => (
              <li key={f.id} className="border-border border-b px-4 py-3 last:border-b-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs">
                      <Badge tone={SENTIMENT_TONE[f.sentiment]}>{f.sentiment}</Badge>
                      <Badge>{SOURCE_LABEL[f.source]}</Badge>
                      {f.platform ? <Badge tone="info">{f.platform}</Badge> : null}
                      {!theme ? <span className="text-fg-subtle">{titleCase(f.theme)}</span> : null}
                      <span className="text-fg-faint">· {formatDate(f.received_on)}</span>
                    </div>
                    <p className="text-fg text-[13px] leading-6">{f.body}</p>
                    <div className="text-fg-subtle mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                      <span>
                        {f.stakeholder
                          ? `${f.stakeholder.name}, ${f.stakeholder.team}`
                          : `via ${f.submitted_by.name}`}
                      </span>
                      {f.linked ? (
                        <Link
                          href={entityHref(f.linked.type, f.linked.id)}
                          className="text-accent inline-flex items-center gap-1 hover:underline"
                        >
                          <Link2 className="size-3" />
                          {f.linked.type}: {f.linked.title}
                        </Link>
                      ) : canManage ? (
                        <button
                          type="button"
                          onClick={() => setLinking(f)}
                          className="hover:text-fg inline-flex items-center gap-1"
                        >
                          <Link2 className="size-3" /> Link to work
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="shrink-0">
                    {canManage ? (
                      <Select
                        aria-label="Status"
                        value={f.status}
                        onChange={(e) =>
                          updateFeedback.mutate({
                            id: f.id,
                            body: { status: e.target.value as FeedbackStatus },
                          })
                        }
                        className="h-7 w-32 text-xs"
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {titleCase(s)}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <StatusBadge status={f.status} />
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Dialog open={creating} onOpenChange={setCreating}>
        {creating ? <NewFeedbackForm onClose={() => setCreating(false)} defaultTheme={theme} /> : null}
      </Dialog>
      <Dialog open={linking !== null} onOpenChange={(o) => (o ? null : setLinking(null))}>
        {linking ? <LinkForm item={linking} onClose={() => setLinking(null)} /> : null}
      </Dialog>
    </div>
  );
}

function LinkPicker({
  value,
  onChange,
}: {
  value: { type: string | null; id: number | null };
  onChange: (v: { type: string | null; id: number | null }) => void;
}) {
  const investigations = useInvestigations();
  const experiments = useExperiments("all");
  const releases = useReleases();
  const options =
    value.type === "investigation"
      ? (investigations.data ?? []).map((i) => ({ id: i.id, label: i.title }))
      : value.type === "experiment"
        ? (experiments.data ?? []).map((e) => ({ id: e.id, label: e.name }))
        : value.type === "release"
          ? (releases.data ?? []).map((r) => ({
              id: r.id,
              label: `${r.version} · ${r.platform} · ${r.name}`,
            }))
          : [];
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2">
      <Select
        aria-label="Link type"
        value={value.type ?? ""}
        onChange={(e) => onChange({ type: e.target.value || null, id: null })}
      >
        <option value="">No link</option>
        <option value="investigation">Investigation</option>
        <option value="experiment">Experiment</option>
        <option value="release">Release</option>
      </Select>
      <Select
        aria-label="Linked item"
        value={value.id ?? ""}
        disabled={!value.type}
        onChange={(e) => onChange({ ...value, id: e.target.value ? Number(e.target.value) : null })}
      >
        <option value="">Choose…</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.label}
          </option>
        ))}
      </Select>
    </div>
  );
}

function LinkForm({ item, onClose }: { item: FeedbackOut; onClose: () => void }) {
  const { updateFeedback } = useOpsMutations();
  const [link, setLink] = useState<{ type: string | null; id: number | null }>({ type: null, id: null });
  return (
    <DialogContent
      title="Link feedback to work"
      description="Point this item at the investigation, experiment or release that answers it."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!link.type || !link.id) return;
          updateFeedback.mutate(
            {
              id: item.id,
              body: {
                linked_entity_type: link.type,
                linked_entity_id: link.id,
                status: item.status === "new" ? "triaged" : undefined,
              },
            },
            { onSuccess: onClose },
          );
        }}
      >
        <p className="text-fg-muted text-xs leading-5">{item.body}</p>
        <LinkPicker value={link} onChange={setLink} />
        {updateFeedback.isError ? <ErrorState error={updateFeedback.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!link.type || !link.id}
            loading={updateFeedback.isPending}
          >
            Link
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

function NewFeedbackForm({ onClose, defaultTheme }: { onClose: () => void; defaultTheme?: string }) {
  const { createFeedback } = useOpsMutations();
  const stakeholders = useStakeholders();
  const themes = useFeedbackThemes();
  const [form, setForm] = useState<FeedbackCreate>({
    source: "support",
    theme: defaultTheme ?? "",
    body: "",
    sentiment: "neutral",
    platform: null,
    received_on: null,
    stakeholder_id: null,
    linked_entity_type: null,
    linked_entity_id: null,
  });
  const patch = (p: Partial<FeedbackCreate>) => setForm((f) => ({ ...f, ...p }));

  return (
    <DialogContent
      title="Log feedback"
      description="One item per signal. Themes group them; links tie them to the work."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          createFeedback.mutate(form, { onSuccess: onClose });
        }}
      >
        <Field label="What was said" htmlFor="fb-body">
          <Textarea
            id="fb-body"
            required
            minLength={3}
            value={form.body}
            onChange={(e) => patch({ body: e.target.value })}
          />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Source" htmlFor="fb-source">
            <Select
              id="fb-source"
              value={form.source}
              onChange={(e) => patch({ source: e.target.value as FeedbackSource })}
            >
              {(Object.keys(SOURCE_LABEL) as FeedbackSource[]).map((s) => (
                <option key={s} value={s}>
                  {SOURCE_LABEL[s]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Sentiment" htmlFor="fb-sent">
            <Select
              id="fb-sent"
              value={form.sentiment ?? "neutral"}
              onChange={(e) => patch({ sentiment: e.target.value as FeedbackSentiment })}
            >
              <option value="negative">Negative</option>
              <option value="neutral">Neutral</option>
              <option value="positive">Positive</option>
            </Select>
          </Field>
          <Field label="Platform" htmlFor="fb-platform">
            <Select
              id="fb-platform"
              value={form.platform ?? ""}
              onChange={(e) => patch({ platform: e.target.value || null })}
            >
              <option value="">Any</option>
              <option value="android">Android</option>
              <option value="ios">iOS</option>
              <option value="web">Web</option>
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Theme" htmlFor="fb-theme" hint="Reuse an existing theme where possible.">
            <Input
              id="fb-theme"
              required
              list="fb-themes"
              value={form.theme}
              onChange={(e) => patch({ theme: e.target.value })}
              placeholder="payments"
            />
            <datalist id="fb-themes">
              {(themes.data ?? []).map((t) => (
                <option key={t.theme} value={t.theme} />
              ))}
            </datalist>
          </Field>
          <Field label="Stakeholder" htmlFor="fb-stk">
            <Select
              id="fb-stk"
              value={form.stakeholder_id ?? ""}
              onChange={(e) => patch({ stakeholder_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">Customer / anonymous</option>
              {(stakeholders.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.team}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Link to work">
          <LinkPicker
            value={{ type: form.linked_entity_type ?? null, id: form.linked_entity_id ?? null }}
            onChange={(v) => patch({ linked_entity_type: v.type, linked_entity_id: v.id })}
          />
        </Field>
        {createFeedback.isError ? <ErrorState error={createFeedback.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={createFeedback.isPending}>
            Log feedback
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
