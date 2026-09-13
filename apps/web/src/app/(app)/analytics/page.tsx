"use client";

import { Bookmark, Trash2 } from "lucide-react";
import { Suspense, useState } from "react";

import { FilterBuilder } from "@/components/analytics/filter-builder";
import { BreakdownTable } from "@/components/charts/breakdown-table";
import { TrendChart } from "@/components/charts/trend-chart";
import { Button } from "@/components/ui/button";
import { DeltaText } from "@/components/ui/delta";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/menu";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ChartSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { SegmentedControl } from "@/components/ui/tabs";
import {
  type Filter,
  type MetricQuery,
  useMetricQuery,
  useSavedAnalyses,
  useSavedAnalysisMutations,
} from "@/lib/api/analytics";
import { usePermission } from "@/lib/api/hooks";
import { formatMetric, type MetricFormat } from "@/lib/format";
import { useRange } from "@/lib/range";
import { useUrlState } from "@/lib/url-state";

type Granularity = "hour" | "day" | "week";
type Viz = "line" | "bar";

const METRIC_GROUPS: { label: string; keys: string[] }[] = [
  { label: "Traffic", keys: ["users", "sessions", "bounce_rate", "product_views", "searches"] },
  {
    label: "Conversion",
    keys: ["conversion", "checkout_conversion", "add_to_cart_rate", "search_to_product_view_rate"],
  },
  { label: "Commerce", keys: ["orders", "revenue", "aov"] },
  {
    label: "Payments",
    keys: ["payment_success_rate", "payment_failure_rate", "payment_attempts", "payment_failures"],
  },
  { label: "Post-purchase", keys: ["return_rate", "returns", "avg_delivery_days"] },
];

function Explorer() {
  const range = useRange();
  const url = useUrlState();
  const canSave = usePermission("run_analytics");

  const metric = url.get("metric") ?? "conversion";
  const breakdown = url.get("breakdown");
  const granularity = (url.get("granularity") as Granularity | null) ?? (range.days > 60 ? "week" : "day");
  const viz = (url.get("viz") as Viz | null) ?? "line";
  const filters = url.getJson<Filter[]>("f", []);
  const setFilters = (next: Filter[]) => url.set({ f: next.length ? JSON.stringify(next) : null });

  const query: MetricQuery | null = range.ready
    ? {
        metric,
        date_from: range.from,
        date_to: range.to,
        filters,
        breakdown: breakdown || null,
        granularity,
        compare_from: range.compareFrom,
        compare_to: range.compareTo,
        limit: 8,
      }
    : null;
  const result = useMetricQuery(query);
  const meta = range.meta;
  const metricInfo = meta?.metrics.find((m) => m.key === metric);
  const dims = meta?.dimensions ?? [];
  const primary = result.data?.series[0];

  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const saved = useSavedAnalyses();
  const { create, remove } = useSavedAnalysisMutations();

  const loadSaved = (config: Record<string, unknown>) => {
    url.set({
      metric: String(config.metric ?? "conversion"),
      breakdown: config.breakdown ? String(config.breakdown) : null,
      granularity: config.granularity ? String(config.granularity) : null,
      f: Array.isArray(config.filters) && config.filters.length ? JSON.stringify(config.filters) : null,
    });
  };

  const breakdownLabel = breakdown ? (dims.find((d) => d.key === breakdown)?.label ?? breakdown) : null;
  const trendTitle = breakdownLabel
    ? `${metricInfo?.label ?? metric} by ${breakdownLabel}`
    : (metricInfo?.label ?? metric);

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Pick a metric, slice it, and compare against the previous period. Every view is a shareable URL."
        actions={
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm">
                  <Bookmark className="size-3.5" /> Saved
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-72">
                <DropdownMenuLabel>Saved analyses</DropdownMenuLabel>
                {(saved.data ?? []).filter((s) => s.kind === "analysis").length === 0 ? (
                  <div className="text-fg-subtle px-2 py-1.5 text-xs">Nothing saved yet.</div>
                ) : null}
                {(saved.data ?? [])
                  .filter((s) => s.kind === "analysis")
                  .map((s) => (
                    <DropdownMenuItem
                      key={s.id}
                      onSelect={() => loadSaved(s.config as Record<string, unknown>)}
                    >
                      <span className="flex-1 truncate">{s.name}</span>
                      <button
                        type="button"
                        aria-label={`Delete ${s.name}`}
                        className="text-fg-faint hover:text-danger rounded-sm p-0.5"
                        onClick={(e) => {
                          e.stopPropagation();
                          remove.mutate(s.id);
                        }}
                      >
                        <Trash2 className="size-3" />
                      </button>
                    </DropdownMenuItem>
                  ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button size="sm" variant="primary" onClick={() => setSaveOpen(true)} disabled={!canSave}>
              Save analysis
            </Button>
          </>
        }
      />

      <Panel className="mb-4">
        <PanelBody className="flex flex-wrap items-end gap-3">
          <Field label="Metric" htmlFor="metric">
            <Select
              id="metric"
              value={metric}
              onChange={(e) => url.set({ metric: e.target.value })}
              className="w-56"
            >
              {METRIC_GROUPS.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.keys.map((k) => (
                    <option key={k} value={k}>
                      {meta?.metrics.find((m) => m.key === k)?.label ?? k}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Break down by" htmlFor="breakdown">
            <Select
              id="breakdown"
              value={breakdown ?? ""}
              onChange={(e) => url.set({ breakdown: e.target.value || null })}
              className="w-44"
            >
              <option value="">None</option>
              {dims.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Granularity">
            <SegmentedControl<Granularity>
              label="Granularity"
              value={granularity}
              onChange={(v) => url.set({ granularity: v })}
              options={[
                { value: "hour", label: "Hour" },
                { value: "day", label: "Day" },
                { value: "week", label: "Week" },
              ]}
            />
          </Field>
          <Field label="Chart">
            <SegmentedControl<Viz>
              label="Chart type"
              value={viz}
              onChange={(v) => url.set({ viz: v })}
              options={[
                { value: "line", label: "Line" },
                { value: "bar", label: "Bar" },
              ]}
            />
          </Field>
          <Field label="Filters" className="min-w-0 flex-1">
            <FilterBuilder filters={filters} onChange={setFilters} dimensions={dims} />
          </Field>
        </PanelBody>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <Panel>
          <PanelHeader title={trendTitle} description={metricInfo?.description} />
          <PanelBody>
            {result.isPending ? (
              <ChartSkeleton />
            ) : result.isError ? (
              <ErrorState error={result.error} onRetry={() => result.refetch()} />
            ) : result.data && result.data.series.length ? (
              <TrendChart result={result.data} granularity={granularity} variant={viz} />
            ) : (
              <EmptyState
                title="No data for this selection"
                description="Try widening the date range or removing a filter."
              />
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader title="Period summary" />
          <PanelBody>
            {primary && metricInfo ? (
              <div>
                <div className="tabular text-2xl font-semibold tracking-tight">
                  {formatMetric(primary.total.value, metricInfo.format as MetricFormat)}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs">
                  <DeltaText
                    current={primary.total.value}
                    previous={primary.compare_total?.value}
                    format={metricInfo.format as MetricFormat}
                    higherIsBetter={metricInfo.higher_is_better}
                  />
                  {primary.compare_total ? (
                    <span className="text-fg-subtle">
                      vs {formatMetric(primary.compare_total.value, metricInfo.format as MetricFormat)}
                    </span>
                  ) : null}
                </div>
                {breakdown ? (
                  <p className="text-fg-subtle mt-2 text-xs">
                    Summary shows the largest segment ({primary.label}). See the table for all.
                  </p>
                ) : null}
                {metricInfo.is_proportion ? (
                  <dl className="border-border mt-3 grid grid-cols-2 gap-x-3 gap-y-1 border-t pt-3 text-xs">
                    <dt className="text-fg-subtle">Numerator</dt>
                    <dd className="tabular text-right">{formatMetric(primary.total.numerator, "count")}</dd>
                    <dt className="text-fg-subtle">Denominator</dt>
                    <dd className="tabular text-right">{formatMetric(primary.total.denominator, "count")}</dd>
                  </dl>
                ) : null}
                <div className="border-border text-fg-subtle mt-3 border-t pt-3 text-xs">
                  {range.from} → {range.to}
                  {range.compareFrom ? (
                    <>
                      <br />
                      vs {range.compareFrom} → {range.compareTo}
                    </>
                  ) : null}
                </div>
              </div>
            ) : (
              <ChartSkeleton height={80} />
            )}
          </PanelBody>
        </Panel>
      </div>

      {breakdown && result.data ? (
        <Panel className="mt-4">
          <PanelHeader
            title={`Top ${result.data.series.length} by ${breakdownLabel}`}
            description="Ranked by volume in the period."
          />
          <BreakdownTable result={result.data} />
        </Panel>
      ) : null}

      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent
          title="Save analysis"
          description="Saved analyses store the metric, breakdown, granularity and filters; the date range follows the global selector."
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate(
                {
                  name: saveName || trendTitle,
                  description: "",
                  kind: "analysis",
                  config: { metric, breakdown: breakdown || null, granularity, filters },
                },
                {
                  onSuccess: () => {
                    setSaveOpen(false);
                    setSaveName("");
                  },
                },
              );
            }}
          >
            <Field label="Name" htmlFor="save-name">
              <Input
                id="save-name"
                value={saveName}
                placeholder={trendTitle}
                onChange={(e) => setSaveName(e.target.value)}
                autoFocus
              />
            </Field>
            <DialogFooter>
              <Button type="button" onClick={() => setSaveOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={create.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense>
      <Explorer />
    </Suspense>
  );
}
