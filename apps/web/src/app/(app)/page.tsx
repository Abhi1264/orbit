"use client";

import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { FunnelChart } from "@/components/charts/funnel-chart";
import { Sparkline } from "@/components/charts/sparkline";
import { TrendChart } from "@/components/charts/trend-chart";
import { Badge } from "@/components/ui/badge";
import { DeltaText } from "@/components/ui/delta";
import { AttentionPanel } from "@/components/investigations/attention-panel";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { ChartSkeleton, EmptyState, ErrorState, Skeleton } from "@/components/ui/states";
import { useFunnel, useInventoryRisk, useMetricQuery, useOverview } from "@/lib/api/analytics";
import { formatCompactCount, formatMetric, type MetricFormat } from "@/lib/format";
import { useRange } from "@/lib/range";

function KpiStrip() {
  const range = useRange();
  const overview = useOverview(
    range.ready
      ? {
          date_from: range.from,
          date_to: range.to,
          compare_from: range.compareFrom,
          compare_to: range.compareTo,
        }
      : null,
  );
  if (overview.isError) return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {(overview.data?.kpis ?? Array.from({ length: 6 })).map((kpi, i) =>
        kpi ? (
          <Link
            key={kpi.metric.key}
            href={`/analytics?metric=${kpi.metric.key}` as "/"}
            className="group border-border bg-bg hover:border-border-strong rounded-md border p-3 transition-colors"
          >
            <div className="text-fg-subtle flex items-center justify-between text-xs">
              {kpi.metric.label}
              <ArrowUpRight className="size-3 opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
            <div className="tabular mt-1 text-xl font-semibold tracking-tight">
              {formatMetric(
                kpi.current.value,
                kpi.metric.format as MetricFormat,
                kpi.metric.format === "currency",
              )}
            </div>
            <div className="mt-0.5 text-xs">
              <DeltaText
                current={kpi.current.value}
                previous={kpi.previous?.value}
                format={kpi.metric.format as MetricFormat}
                higherIsBetter={kpi.metric.higher_is_better}
              />
              <span className="text-fg-faint"> vs prev.</span>
            </div>
            <div className="mt-2">
              <Sparkline points={kpi.points ?? []} compare={kpi.compare_points ?? []} />
            </div>
          </Link>
        ) : (
          <div key={i} className="border-border rounded-md border p-3">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-2 h-6 w-24" />
            <Skeleton className="mt-3 h-8 w-full" />
          </div>
        ),
      )}
    </div>
  );
}

function ConversionPanel() {
  const range = useRange();
  const q = useMetricQuery(
    range.ready
      ? {
          metric: "checkout_conversion",
          date_from: range.from,
          date_to: range.to,
          granularity: range.days > 60 ? "week" : "day",
          compare_from: range.compareFrom,
          compare_to: range.compareTo,
          filters: [],
          breakdown: null,
          limit: 8,
        }
      : null,
  );
  return (
    <Panel>
      <PanelHeader
        title="Checkout conversion"
        description="Orders ÷ sessions that started checkout. Dashed line is the comparison period."
        actions={
          <Link
            href={"/analytics?metric=checkout_conversion&breakdown=platform" as "/"}
            className="text-accent text-xs hover:underline"
          >
            Break down
          </Link>
        }
      />
      <PanelBody>
        {q.isPending ? (
          <ChartSkeleton height={220} />
        ) : q.isError ? (
          <ErrorState error={q.error} />
        ) : q.data ? (
          <TrendChart result={q.data} granularity={range.days > 60 ? "week" : "day"} height={220} />
        ) : null}
      </PanelBody>
    </Panel>
  );
}

function FunnelPanel() {
  const range = useRange();
  const q = useFunnel(
    range.ready
      ? {
          steps: ["product_view", "add_to_cart", "checkout_started", "payment_started", "order_completed"],
          date_from: range.from,
          date_to: range.to,
          segments: [{ label: "All sessions", filters: [] }],
          breakdown: null,
          limit: 6,
        }
      : null,
  );
  return (
    <Panel>
      <PanelHeader
        title="Purchase funnel"
        description="Sessions reaching each step, in order."
        actions={
          <Link href={"/funnels" as "/"} className="text-accent text-xs hover:underline">
            Open funnels
          </Link>
        }
      />
      <PanelBody>
        {q.isPending ? (
          <ChartSkeleton height={200} />
        ) : q.isError ? (
          <ErrorState error={q.error} />
        ) : q.data ? (
          <FunnelChart result={q.data} />
        ) : null}
      </PanelBody>
    </Panel>
  );
}

function InventoryPanel() {
  const range = useRange();
  const q = useInventoryRisk(range.ready ? range.to : undefined);
  return (
    <Panel>
      <PanelHeader
        title="Stock-out risk"
        description="Stock covers < 7 days of trailing 14-day sales."
        actions={
          q.data ? (
            <Badge tone={q.data.items.length ? "warning" : "neutral"}>{q.data.items.length} products</Badge>
          ) : null
        }
      />
      {q.isPending ? (
        <PanelBody>
          <Skeleton className="h-24 w-full" />
        </PanelBody>
      ) : q.isError ? (
        <ErrorState error={q.error} />
      ) : q.data?.items.length ? (
        <table className="data-table">
          <thead>
            <tr>
              <th>Product</th>
              <th className="num">Stock</th>
              <th className="num">14d sold</th>
              <th className="num">Cover</th>
            </tr>
          </thead>
          <tbody>
            {q.data.items.slice(0, 6).map((i) => (
              <tr key={i.product_id}>
                <td>
                  <div className="truncate">{i.name}</div>
                  <div className="text-2xs text-fg-subtle font-mono">{i.sku}</div>
                </td>
                <td className="num">{i.stock_units}</td>
                <td className="num">{formatCompactCount(i.units_sold_14d)}</td>
                <td className="num">
                  <span
                    className={
                      i.days_of_cover !== null && i.days_of_cover !== undefined && i.days_of_cover < 3
                        ? "text-danger"
                        : "text-warning"
                    }
                  >
                    {i.days_of_cover?.toFixed(1)} d
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState title="No products at risk" className="py-6" />
      )}
    </Panel>
  );
}

function Overview() {
  const range = useRange();
  return (
    <>
      <PageHeader
        title="Overview"
        description={
          range.ready
            ? `Threadline · ${range.from} → ${range.to}, compared with ${range.compareFrom ?? "—"} → ${range.compareTo ?? "—"}`
            : undefined
        }
      />
      <div className="space-y-4">
        <KpiStrip />
        <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
          <ConversionPanel />
          <AttentionPanel />
        </div>
        <div className="grid gap-4 xl:grid-cols-[3fr_2fr]">
          <FunnelPanel />
          <InventoryPanel />
        </div>
      </div>
    </>
  );
}

export default function OverviewPage() {
  return (
    <Suspense>
      <Overview />
    </Suspense>
  );
}
