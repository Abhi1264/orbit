"use client";

import { ArrowUpRight, ChevronLeft, ListChecks, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { AskAnalystButton } from "@/components/analyst/ask-analyst-button";
import { TrendChart } from "@/components/charts/trend-chart";
import { CommentThread } from "@/components/comments/comment-thread";
import { ChecklistPanel } from "@/components/releases/checklist-panel";
import { ReleaseTimeline } from "@/components/releases/timeline";
import { Badge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menu";
import { KeyValue, PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ChartSkeleton, EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useAnalyticsMeta, useMetricQuery } from "@/lib/api/analytics";
import { usePermission } from "@/lib/api/hooks";
import {
  type ReleaseOut,
  type ReleaseStatus,
  useRelease,
  useReleaseImpact,
  useReleaseMutations,
  useSops,
} from "@/lib/api/ops";
import { formatDate } from "@/lib/format";
import { analystHref, entityHref, exploreHref } from "@/lib/links";
import { cn } from "@/lib/utils";

const STATUSES: { value: ReleaseStatus; label: string }[] = [
  { value: "planned", label: "Planned" },
  { value: "in_progress", label: "In progress" },
  { value: "rolling_out", label: "Rolling out" },
  { value: "completed", label: "Completed" },
  { value: "rolled_back", label: "Rolled back" },
];

function shiftIso(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// --------------------------------------------------------------------------- impact

const TONE_CLASS = {
  good: "text-success",
  bad: "text-danger",
  neutral: "text-fg-muted",
  unknown: "text-fg-faint",
} as const;

function ImpactPanel({ rel }: { rel: ReleaseOut }) {
  const impact = useReleaseImpact(rel.id, rel.status !== "planned");
  const meta = useAnalyticsMeta();
  const [metric, setMetric] = useState<string>(
    rel.affected_areas.some((a) => /payment|checkout/.test(a)) ? "payment_success_rate" : "conversion",
  );
  const dataEnd = meta.data?.data_end ?? rel.release_date;
  const from = shiftIso(rel.release_date, -14);
  const to = shiftIso(rel.release_date, 14) < dataEnd ? shiftIso(rel.release_date, 14) : dataEnd;
  const filters =
    rel.platform === "all" ? [] : [{ dimension: "platform", operator: "eq" as const, value: rel.platform }];
  const q = useMetricQuery(
    meta.isSuccess && rel.status !== "planned"
      ? { metric, date_from: from, date_to: to, filters, granularity: "day", limit: 5 }
      : null,
  );

  if (rel.status === "planned") {
    return (
      <Panel>
        <PanelHeader title="Post-launch read" />
        <EmptyState
          title="Not shipped yet"
          description="Once the release is rolling out, this panel compares the week after against the week before on the release's platform."
        />
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHeader
        title="Post-launch read"
        description={impact.data?.note}
        actions={
          <Tooltip content="Open in Analytics">
            <Link
              href={exploreHref({ metric, filters, from, to, breakdown: "app_version" })}
              className="text-fg-subtle hover:bg-surface-2 hover:text-fg rounded-sm p-1"
              aria-label="Open in Analytics"
            >
              <ArrowUpRight className="size-4" />
            </Link>
          </Tooltip>
        }
      />
      {impact.isPending ? (
        <div className="space-y-2 p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : impact.isError ? (
        <PanelBody>
          <ErrorState error={impact.error} onRetry={() => impact.refetch()} />
        </PanelBody>
      ) : (
        <>
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-fg-subtle text-2xs border-border border-b text-left tracking-wide uppercase">
                <th className="px-4 py-2 font-medium">Metric</th>
                <th className="tabular px-3 py-2 text-right font-medium">Before</th>
                <th className="tabular px-3 py-2 text-right font-medium">After</th>
                <th className="tabular px-4 py-2 text-right font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {impact.data.metrics.map((m) => (
                <tr
                  key={m.metric_key}
                  className={cn(
                    "border-border hover:bg-surface cursor-pointer border-b last:border-b-0",
                    m.metric_key === metric && "bg-surface",
                  )}
                  onClick={() => setMetric(m.metric_key)}
                >
                  <td className="text-fg px-4 py-2">{m.label}</td>
                  <td className="tabular text-fg-muted px-3 py-2 text-right">{m.formatted_before}</td>
                  <td className="tabular text-fg px-3 py-2 text-right font-medium">{m.formatted_after}</td>
                  <td className={cn("tabular px-4 py-2 text-right font-medium", TONE_CLASS[m.tone])}>
                    {m.formatted_change}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <PanelBody className="border-border border-t">
            {q.isPending || !meta.isSuccess ? (
              <ChartSkeleton height={200} />
            ) : q.isError ? (
              <ErrorState error={q.error} />
            ) : (
              <TrendChart
                result={q.data}
                granularity="day"
                height={200}
                markers={[
                  { bucket: rel.release_date, label: `${rel.version} ships`, tone: "info" },
                  ...rel.timeline
                    .filter((e) => e.kind === "rollout" && /100%/.test(e.note))
                    .slice(0, 1)
                    .map((e) => ({
                      bucket: e.occurred_at.slice(0, 10),
                      label: "100%",
                      tone: "neutral" as const,
                    })),
                ]}
                bands={[
                  {
                    from: impact.data.before_start,
                    to: impact.data.before_end,
                    label: "Before",
                    tone: "neutral",
                  },
                  { from: impact.data.after_start, to: impact.data.after_end, label: "After", tone: "info" },
                ]}
              />
            )}
          </PanelBody>
        </>
      )}
    </Panel>
  );
}

// --------------------------------------------------------------------------- page

export default function ReleaseDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const router = useRouter();
  const release = useRelease(id);
  const sops = useSops();
  const { update, addNote, runSop, remove } = useReleaseMutations(id);
  const canManage = usePermission("manage_releases");
  const [rollout, setRollout] = useState<string>("");
  const [note, setNote] = useState("");

  if (release.isPending) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-96" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (release.isError) return <ErrorState error={release.error} onRetry={() => release.refetch()} />;
  const data = release.data;
  const rolloutValue = rollout === "" ? String(data.rollout_percent) : rollout;
  const platformLabel = data.platform === "all" ? "All platforms" : data.platform;
  const unusedSops = (sops.data ?? []).filter((s) => !data.checklists.some((c) => c.sop_id === s.id));

  return (
    <>
      <PageHeader
        breadcrumb={
          <Link href="/releases" className="hover:text-fg inline-flex items-center gap-0.5">
            <ChevronLeft className="size-3" />
            Releases
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-2">
            {data.name}
            <StatusBadge status={data.status} className="px-2 py-0.5 text-xs" />
          </span>
        }
        description={
          <>
            <span className="font-mono">{data.version}</span> ·{" "}
            <span className="capitalize">{platformLabel}</span> ·{" "}
            {formatDate(data.release_date, { day: "numeric", month: "short", year: "numeric" })} ·{" "}
            {data.owner.name}
          </>
        }
        actions={
          <>
            {data.status !== "planned" ? (
              <AskAnalystButton
                href={analystHref({
                  q: `What changed after ${data.platform === "all" ? "" : data.platform + " "}${data.version} shipped?`,
                  metric: data.affected_areas.some((a) => /payment|checkout/.test(a))
                    ? "payment_success_rate"
                    : "conversion",
                  filters:
                    data.platform === "all"
                      ? []
                      : [{ dimension: "platform", operator: "eq", value: data.platform }],
                  from: shiftIso(data.release_date, -7),
                  to: shiftIso(data.release_date, 7),
                })}
              />
            ) : null}
            {canManage ? (
              <>
                <Select
                  aria-label="Status"
                  value={data.status}
                  onChange={(e) => update.mutate({ status: e.target.value as ReleaseStatus })}
                  className="w-36"
                >
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
                {data.status === "planned" ? (
                  <Tooltip content="Delete planned release">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Delete release"
                      loading={remove.isPending}
                      onClick={() => {
                        if (window.confirm(`Delete "${data.name}"?`))
                          remove.mutate(undefined, { onSuccess: () => router.push("/releases") });
                      }}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </Tooltip>
                ) : null}
              </>
            ) : null}
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Panel>
            <PanelHeader title="What shipped" />
            <PanelBody className="space-y-3">
              <p className="text-fg text-[13px] leading-6">{data.description || "No description."}</p>
              <KeyValue
                items={[
                  {
                    label: "Areas",
                    value: data.affected_areas.length ? (
                      <span className="flex flex-wrap gap-1">
                        {data.affected_areas.map((a) => (
                          <Badge key={a}>{a}</Badge>
                        ))}
                      </span>
                    ) : (
                      "—"
                    ),
                  },
                  {
                    label: "Rollout",
                    value:
                      canManage && data.status !== "planned" ? (
                        <form
                          className="flex items-center gap-2"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const pct = Math.max(0, Math.min(100, Number(rolloutValue)));
                            if (pct !== data.rollout_percent) update.mutate({ rollout_percent: pct });
                            setRollout("");
                          }}
                        >
                          <Input
                            type="number"
                            min={0}
                            max={100}
                            value={rolloutValue}
                            onChange={(e) => setRollout(e.target.value)}
                            className="tabular h-7 w-20"
                            aria-label="Rollout percent"
                          />
                          <span className="text-fg-subtle text-xs">%</span>
                          {rollout !== "" && Number(rollout) !== data.rollout_percent ? (
                            <Button size="sm" type="submit" loading={update.isPending}>
                              Update
                            </Button>
                          ) : null}
                        </form>
                      ) : (
                        `${data.rollout_percent}%`
                      ),
                  },
                  {
                    label: "Experiment",
                    value: data.experiment ? (
                      <Link
                        href={entityHref("experiment", data.experiment.id)}
                        className="text-accent hover:underline"
                      >
                        {data.experiment.title}
                      </Link>
                    ) : (
                      "—"
                    ),
                  },
                ]}
              />
            </PanelBody>
          </Panel>

          <ImpactPanel rel={data} />

          {data.checklists.length ? (
            data.checklists.map((c) => <ChecklistPanel key={c.id} checklist={c} canEdit={canManage} />)
          ) : (
            <Panel>
              <PanelHeader
                title="Launch checklist"
                actions={
                  canManage && unusedSops.length ? (
                    <Select
                      aria-label="Run SOP"
                      value=""
                      onChange={(e) => e.target.value && runSop.mutate(Number(e.target.value))}
                      className="w-56"
                    >
                      <option value="">Run an SOP…</option>
                      {unusedSops.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.title}
                        </option>
                      ))}
                    </Select>
                  ) : null
                }
              />
              <EmptyState
                title="No checklist attached"
                description="Run the relevant SOP to create a checklist for this release; every item is tracked with who ticked it and when."
              />
            </Panel>
          )}
          {data.checklists.length && canManage && unusedSops.length ? (
            <div className="flex items-center justify-end gap-2 text-xs">
              <ListChecks className="text-fg-subtle size-3.5" />
              <Select
                aria-label="Run another SOP"
                value=""
                onChange={(e) => e.target.value && runSop.mutate(Number(e.target.value))}
                className="h-7 w-56 text-xs"
              >
                <option value="">Run another SOP…</option>
                {unusedSops.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </Select>
            </div>
          ) : null}

          <CommentThread entityType="release" entityId={data.id} />
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader title="Timeline" />
            <PanelBody>
              <ReleaseTimeline events={data.timeline} />
              {canManage ? (
                <form
                  className="mt-3 flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (note.trim()) addNote.mutate(note.trim(), { onSuccess: () => setNote("") });
                  }}
                >
                  <Input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Add a note to the timeline"
                    aria-label="Timeline note"
                    className="h-7 text-xs"
                  />
                  <Button size="sm" type="submit" disabled={!note.trim()} loading={addNote.isPending}>
                    Add
                  </Button>
                </form>
              ) : null}
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader title="Linked" />
            <PanelBody className="space-y-3 text-[13px]">
              <LinkedList
                label="Investigations"
                items={data.investigations}
                empty="No investigation names this release as a cause."
              />
              <LinkedList
                label="Decisions"
                items={data.decisions}
                empty="No decisions reference this release."
              />
            </PanelBody>
          </Panel>
        </div>
      </div>
    </>
  );
}

function LinkedList({
  label,
  items,
  empty,
}: {
  label: string;
  items: ReleaseOut["investigations"];
  empty: string;
}) {
  return (
    <div>
      <div className="text-fg-subtle text-2xs mb-1 tracking-wide uppercase">{label}</div>
      {items.length === 0 ? (
        <p className="text-fg-faint text-xs">{empty}</p>
      ) : (
        <ul className="space-y-1">
          {items.map((it) => (
            <li key={`${it.type}-${it.id}`} className="flex items-center justify-between gap-2">
              <Link href={entityHref(it.type, it.id)} className="text-fg hover:text-accent truncate">
                {it.title}
              </Link>
              {it.status ? <StatusBadge status={it.status} /> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
