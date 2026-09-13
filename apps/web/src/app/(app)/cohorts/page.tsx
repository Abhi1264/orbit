"use client";

import { subDays } from "date-fns";
import { Suspense } from "react";

import { CohortHeatmap } from "@/components/charts/cohort-heatmap";
import { Field, Select } from "@/components/ui/input";
import { PageHeader, Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/states";
import { type CohortQuery, useCohort } from "@/lib/api/analytics";
import { isoDate } from "@/lib/date-range";
import { useRange } from "@/lib/range";
import { useUrlState } from "@/lib/url-state";

type CohortType = CohortQuery["cohort_type"];
type Measure = CohortQuery["measure"];

const COHORT_FILTERS: { key: string; label: string; dim: string }[] = [
  { key: "platform", label: "Platform", dim: "platform" },
  { key: "traffic_source", label: "Acquisition source", dim: "traffic_source" },
  { key: "city_tier", label: "City tier", dim: "city_tier" },
  { key: "country", label: "Country", dim: "country" },
];

function Cohorts() {
  const range = useRange();
  const url = useUrlState();
  const cohortType = (url.get("type") as CohortType | null) ?? "signup";
  const measure = (url.get("measure") as Measure | null) ?? "retention";
  const weeks = Number(url.get("weeks") ?? 8);
  const filterDim = url.get("fd");
  const filterValue = url.get("fv");

  // Cohorts need history: look back at least `weeks` weeks even when the global range is short.
  const lookback = isoDate(subDays(new Date(range.to), weeks * 7 + 6));
  const dateFrom = range.from < lookback ? range.from : lookback;
  const query: CohortQuery | null = range.ready
    ? {
        cohort_type: cohortType,
        measure,
        date_from: dateFrom,
        date_to: range.to,
        weeks,
        filters: filterDim && filterValue ? [{ dimension: filterDim, value: filterValue }] : [],
      }
    : null;
  const result = useCohort(query);
  const dims = range.meta?.dimensions ?? [];
  const values = dims.find((d) => d.key === filterDim)?.values ?? [];

  return (
    <>
      <PageHeader
        title="Cohorts"
        description="Weekly cohorts by signup or first purchase. Week 0 is the cohort week itself; cells that have not had time to happen are blank."
      />
      <Panel className="mb-4">
        <PanelBody className="flex flex-wrap items-end gap-3">
          <Field label="Cohort by" htmlFor="cohort-type">
            <Select
              id="cohort-type"
              value={cohortType}
              onChange={(e) => url.set({ type: e.target.value })}
              className="w-40"
            >
              <option value="signup">Signup week</option>
              <option value="first_purchase">First purchase week</option>
            </Select>
          </Field>
          <Field label="Measure" htmlFor="cohort-measure">
            <Select
              id="cohort-measure"
              value={measure}
              onChange={(e) => url.set({ measure: e.target.value })}
              className="w-44"
            >
              <option value="retention">Retention (any session)</option>
              <option value="repeat_purchase">Repeat purchase</option>
              <option value="revenue_per_user">Revenue per user</option>
            </Select>
          </Field>
          <Field label="Weeks" htmlFor="cohort-weeks">
            <Select
              id="cohort-weeks"
              value={String(weeks)}
              onChange={(e) => url.set({ weeks: e.target.value })}
              className="w-20"
            >
              {[4, 6, 8, 10, 12].map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Filter users by" htmlFor="cohort-fd">
            <div className="flex gap-1.5">
              <Select
                id="cohort-fd"
                value={filterDim ?? ""}
                onChange={(e) => {
                  const dim = e.target.value || null;
                  const first = dims.find((d) => d.key === dim)?.values[0] ?? null;
                  url.set({ fd: dim, fv: dim ? first : null });
                }}
                className="w-40"
              >
                <option value="">None</option>
                {COHORT_FILTERS.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.label}
                  </option>
                ))}
              </Select>
              {filterDim ? (
                <Select
                  aria-label="Filter value"
                  value={filterValue ?? ""}
                  onChange={(e) => url.set({ fv: e.target.value })}
                  className="w-32"
                >
                  {values.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </Select>
              ) : null}
            </div>
          </Field>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader
          title={
            result.data
              ? `${result.data.interpretation.cohort as string} · ${measure.replace(/_/g, " ")}`
              : "Cohorts"
          }
          description={
            result.data
              ? `${result.data.measure_definition}. Cohorts from ${dateFrom} to ${range.to}.`
              : undefined
          }
        />
        {result.isPending ? (
          <TableSkeleton rows={8} cols={10} />
        ) : result.isError ? (
          <ErrorState error={result.error} onRetry={() => result.refetch()} />
        ) : result.data && result.data.rows.length ? (
          <CohortHeatmap result={result.data} />
        ) : (
          <EmptyState
            title="No cohorts in range"
            description="Widen the date range to include more cohort weeks."
          />
        )}
      </Panel>
    </>
  );
}

export default function CohortsPage() {
  return (
    <Suspense>
      <Cohorts />
    </Suspense>
  );
}
