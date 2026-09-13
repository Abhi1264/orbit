"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { FilterBuilder } from "@/components/analytics/filter-builder";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import type { Filter } from "@/lib/api/analytics";
import {
  type AnomalyOut,
  type InvestigationCreate,
  useInvestigationMutations,
} from "@/lib/api/investigations";
import { formatMetric, type MetricFormat } from "@/lib/format";
import { useRange } from "@/lib/range";

export interface InvestigationSeed {
  title?: string;
  metric_key?: string;
  filters?: Filter[];
  period_start?: string;
  period_end?: string;
  baseline_start?: string;
  baseline_end?: string;
  observation?: string;
  anomaly?: AnomalyOut;
}

function addDays(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Default baseline: the four weeks ending the day before the period starts. */
function defaultBaseline(periodStart: string) {
  return { baseline_start: addDays(periodStart, -28), baseline_end: addDays(periodStart, -1) };
}

function anomalyTitle(a: AnomalyOut) {
  const verb = a.direction === "up" ? "up" : "down";
  const scope = a.filter_labels.length ? ` for ${a.filter_labels.join(", ")}` : "";
  return `${a.metric_label} ${verb}${scope}`;
}

function anomalyObservation(a: AnomalyOut) {
  const fmt = a.metric_format as MetricFormat;
  return (
    `${a.metric_label} ${a.direction === "up" ? "rose" : "fell"} to ${formatMetric(a.actual, fmt)} ` +
    `against an expected ${formatMetric(a.expected, fmt)} between ${a.period_start} and ${a.period_end}` +
    `${a.ongoing ? " and is still off baseline" : ""}` +
    `${a.filter_labels.length ? ` (${a.filter_labels.join(", ")})` : ""}.`
  );
}

export function NewInvestigationDialog({
  open,
  onClose,
  seed,
}: {
  open: boolean;
  onClose: () => void;
  seed?: InvestigationSeed;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      {open ? (
        <NewInvestigationForm key={seed?.anomaly?.id ?? "blank"} seed={seed} onClose={onClose} />
      ) : null}
    </Dialog>
  );
}

function NewInvestigationForm({ seed, onClose }: { seed?: InvestigationSeed; onClose: () => void }) {
  const range = useRange();
  const router = useRouter();
  const { create } = useInvestigationMutations();
  const a = seed?.anomaly;

  const periodStart = seed?.period_start ?? a?.period_start ?? range.from;
  const periodEnd = seed?.period_end ?? a?.period_end ?? range.to;
  const [form, setForm] = useState<InvestigationCreate>(() => ({
    title: seed?.title ?? (a ? anomalyTitle(a) : ""),
    metric_key: seed?.metric_key ?? a?.metric_key ?? "conversion",
    filters: seed?.filters ?? a?.filters ?? [],
    period_start: periodStart,
    period_end: periodEnd,
    ...(seed?.baseline_start && seed.baseline_end
      ? { baseline_start: seed.baseline_start, baseline_end: seed.baseline_end }
      : defaultBaseline(periodStart)),
    observation: seed?.observation ?? (a ? anomalyObservation(a) : ""),
    anomaly_id: a?.id ?? null,
  }));
  const [baselineTouched, setBaselineTouched] = useState(Boolean(seed?.baseline_start));

  const patch = (p: Partial<InvestigationCreate>) => setForm((f) => ({ ...f, ...p }));
  const setPeriodStart = (v: string) =>
    setForm((f) => ({ ...f, period_start: v, ...(baselineTouched || !v ? {} : defaultBaseline(v)) }));

  return (
    <DialogContent
      title={a ? "Investigate anomaly" : "New investigation"}
      description="An investigation pins a metric, a scope and two windows: the period that looks wrong and the baseline it is judged against. Everything else is evidence you add."
      wide
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(form, {
            onSuccess: (inv) => {
              onClose();
              router.push(`/investigations/${inv.id}`);
            },
          });
        }}
      >
        <Field label="Title" htmlFor="inv-title">
          <Input
            id="inv-title"
            value={form.title}
            onChange={(e) => patch({ title: e.target.value })}
            required
            autoFocus
            maxLength={200}
          />
        </Field>
        <div className="grid gap-3 md:grid-cols-[220px_1fr]">
          <Field label="Metric" htmlFor="inv-metric">
            <Select
              id="inv-metric"
              value={form.metric_key}
              onChange={(e) => patch({ metric_key: e.target.value })}
            >
              {(range.meta?.metrics ?? []).map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Scope" hint="Leave empty for store-wide.">
            <FilterBuilder
              filters={form.filters ?? []}
              onChange={(filters) => patch({ filters })}
              dimensions={range.meta?.dimensions ?? []}
              compact
            />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <fieldset className="border-border bg-surface rounded-sm border p-3">
            <legend className="text-fg px-1 text-xs font-medium">Period under investigation</legend>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From" htmlFor="inv-ps">
                <Input
                  id="inv-ps"
                  type="date"
                  value={form.period_start}
                  onChange={(e) => setPeriodStart(e.target.value)}
                  required
                />
              </Field>
              <Field label="To" htmlFor="inv-pe">
                <Input
                  id="inv-pe"
                  type="date"
                  value={form.period_end}
                  onChange={(e) => patch({ period_end: e.target.value })}
                  required
                />
              </Field>
            </div>
          </fieldset>
          <fieldset className="border-border bg-surface rounded-sm border p-3">
            <legend className="text-fg px-1 text-xs font-medium">Baseline</legend>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From" htmlFor="inv-bs">
                <Input
                  id="inv-bs"
                  type="date"
                  value={form.baseline_start}
                  onChange={(e) => {
                    setBaselineTouched(true);
                    patch({ baseline_start: e.target.value });
                  }}
                  required
                />
              </Field>
              <Field label="To" htmlFor="inv-be">
                <Input
                  id="inv-be"
                  type="date"
                  value={form.baseline_end}
                  onChange={(e) => {
                    setBaselineTouched(true);
                    patch({ baseline_end: e.target.value });
                  }}
                  required
                />
              </Field>
            </div>
          </fieldset>
        </div>
        <Field
          label="Observation"
          htmlFor="inv-obs"
          hint="What you saw, in plain numbers. Hypotheses come later."
        >
          <Textarea
            id="inv-obs"
            value={form.observation ?? ""}
            onChange={(e) => patch({ observation: e.target.value })}
            className="min-h-16"
          />
        </Field>
        {create.isError ? <ErrorState error={create.error} className="py-2" /> : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={create.isPending}>
            {a ? "Open investigation" : "Create investigation"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
