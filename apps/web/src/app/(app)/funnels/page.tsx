"use client";

import { Plus, X } from "lucide-react";
import { Suspense } from "react";

import { FilterBuilder } from "@/components/analytics/filter-builder";
import { FunnelChart, FunnelTable } from "@/components/charts/funnel-chart";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ChartSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { type Filter, type FunnelQuery, useFunnel } from "@/lib/api/analytics";
import { useRange } from "@/lib/range";
import { useUrlState } from "@/lib/url-state";

const DEFAULT_STEPS = [
  "home_view",
  "product_view",
  "add_to_cart",
  "checkout_started",
  "payment_started",
  "order_completed",
];

interface Segment {
  label: string;
  filters: Filter[];
}

function Funnels() {
  const range = useRange();
  const url = useUrlState();
  const steps = url.getJson<string[]>("steps", DEFAULT_STEPS);
  const segments = url.getJson<Segment[]>("segments", [{ label: "All sessions", filters: [] }]);
  const breakdown = url.get("breakdown");
  const setSteps = (next: string[]) => url.set({ steps: JSON.stringify(next) });
  const setSegments = (next: Segment[]) => url.set({ segments: JSON.stringify(next) });

  const query: FunnelQuery | null =
    range.ready && steps.length >= 2
      ? {
          steps,
          date_from: range.from,
          date_to: range.to,
          segments: breakdown ? [segments[0]] : segments,
          breakdown: breakdown || null,
          limit: 6,
        }
      : null;
  const result = useFunnel(query);
  const meta = range.meta;
  const events = meta?.funnel_events ?? {};
  const sessionDims = (meta?.dimensions ?? []).filter((d) => d.scope === "session");

  return (
    <>
      <PageHeader
        title="Funnels"
        description="Ordered step conversion within a session (24h window). Compare segments side by side or break a funnel down by a session attribute."
      />

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <div className="space-y-4">
          <Panel>
            <PanelHeader title="Steps" description="Events must occur in this order." />
            <PanelBody className="space-y-2">
              {steps.map((s, i) => (
                <div key={`${s}-${i}`} className="flex items-center gap-1.5">
                  <span className="text-2xs text-fg-subtle w-4 text-right">{i + 1}</span>
                  <Select
                    aria-label={`Step ${i + 1}`}
                    value={s}
                    onChange={(e) => setSteps(steps.map((x, idx) => (idx === i ? e.target.value : x)))}
                  >
                    {Object.entries(events).map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </Select>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Remove step"
                    disabled={steps.length <= 2}
                    onClick={() => setSteps(steps.filter((_, idx) => idx !== i))}
                  >
                    <X className="size-3.5" />
                  </Button>
                </div>
              ))}
              <Button
                variant="ghost"
                size="sm"
                disabled={steps.length >= 8}
                onClick={() => setSteps([...steps, "order_completed"])}
              >
                <Plus className="size-3.5" /> Add step
              </Button>
            </PanelBody>
          </Panel>

          <Panel>
            <PanelHeader
              title="Compare"
              description="Add segments to compare, or break down by a session attribute."
            />
            <PanelBody className="space-y-3">
              <Field label="Break down by" htmlFor="funnel-breakdown">
                <Select
                  id="funnel-breakdown"
                  value={breakdown ?? ""}
                  onChange={(e) => url.set({ breakdown: e.target.value || null })}
                >
                  <option value="">None (use segments)</option>
                  {sessionDims.map((d) => (
                    <option key={d.key} value={d.key}>
                      {d.label}
                    </option>
                  ))}
                </Select>
              </Field>
              {!breakdown ? (
                <div className="space-y-3">
                  {segments.map((seg, i) => (
                    <div key={i} className="border-border rounded-sm border p-2">
                      <div className="mb-2 flex items-center gap-1.5">
                        <Input
                          aria-label={`Segment ${i + 1} name`}
                          className="h-7 text-xs"
                          value={seg.label}
                          onChange={(e) =>
                            setSegments(
                              segments.map((x, idx) => (idx === i ? { ...x, label: e.target.value } : x)),
                            )
                          }
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Remove segment"
                          disabled={segments.length <= 1}
                          onClick={() => setSegments(segments.filter((_, idx) => idx !== i))}
                        >
                          <X className="size-3.5" />
                        </Button>
                      </div>
                      <FilterBuilder
                        compact
                        filters={seg.filters}
                        onChange={(f) =>
                          setSegments(segments.map((x, idx) => (idx === i ? { ...x, filters: f } : x)))
                        }
                        dimensions={meta?.dimensions ?? []}
                      />
                    </div>
                  ))}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={segments.length >= 4}
                    onClick={() =>
                      setSegments([...segments, { label: `Segment ${segments.length + 1}`, filters: [] }])
                    }
                  >
                    <Plus className="size-3.5" /> Add segment
                  </Button>
                </div>
              ) : (
                <FilterBuilder
                  filters={segments[0]?.filters ?? []}
                  onChange={(f) => setSegments([{ label: segments[0]?.label ?? "All sessions", filters: f }])}
                  dimensions={meta?.dimensions ?? []}
                />
              )}
            </PanelBody>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader
              title="Funnel"
              description={`${range.from} → ${range.to}. Bars are scaled to each series' first step.`}
            />
            <PanelBody>
              {result.isPending ? (
                <ChartSkeleton height={220} />
              ) : result.isError ? (
                <ErrorState error={result.error} onRetry={() => result.refetch()} />
              ) : result.data && result.data.series.length ? (
                <FunnelChart result={result.data} />
              ) : (
                <EmptyState title="No sessions match" />
              )}
            </PanelBody>
          </Panel>
          {result.data && result.data.series.length ? (
            <Panel>
              <PanelHeader title="Step detail" />
              <div className="overflow-x-auto">
                <FunnelTable result={result.data} />
              </div>
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}

export default function FunnelsPage() {
  return (
    <Suspense>
      <Funnels />
    </Suspense>
  );
}
