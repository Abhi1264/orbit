"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { FilterBuilder } from "@/components/analytics/filter-builder";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { type ExperimentCreate, useExperimentMutations, type VariantIn } from "@/lib/api/experiments";
import { experimentHref } from "@/lib/links";
import { useRange } from "@/lib/range";

const DEFAULT_VARIANTS: VariantIn[] = [
  { key: "control", name: "Control", description: "", weight: 50, is_control: true },
  { key: "treatment", name: "Treatment", description: "", weight: 50, is_control: false },
];

function slug(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
}

export function NewExperimentDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? null : onClose())}>
      {open ? <NewExperimentForm onClose={onClose} /> : null}
    </Dialog>
  );
}

function NewExperimentForm({ onClose }: { onClose: () => void }) {
  const range = useRange();
  const router = useRouter();
  const { create } = useExperimentMutations();
  const metrics = range.meta?.metrics ?? [];
  const [form, setForm] = useState<ExperimentCreate>({
    name: "",
    hypothesis: "",
    description: "",
    primary_metric: "conversion",
    guardrail_metrics: ["return_rate"],
    audience_filters: [],
    traffic_percent: 100,
    min_sample_per_variant: 2000,
    min_relative_effect: 0.03,
    min_duration_days: 7,
    start_date: range.meta?.data_end ?? null,
    end_date: null,
    variants: DEFAULT_VARIANTS,
  });
  const patch = (p: Partial<ExperimentCreate>) => setForm((f) => ({ ...f, ...p }));
  const setVariant = (i: number, p: Partial<VariantIn>) =>
    setForm((f) => ({ ...f, variants: f.variants.map((v, j) => (j === i ? { ...v, ...p } : v)) }));
  const weightTotal = form.variants.reduce((s, v) => s + v.weight, 0);
  const guardrailOptions = metrics.filter((m) => m.key !== form.primary_metric);

  return (
    <DialogContent
      title="New experiment"
      description="Pin the hypothesis, the one metric it should move, and the metrics it must not hurt, before anyone sees a result. The design is frozen once the experiment starts."
      wide
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(
            { ...form, key: slug(form.name) || null, end_date: form.end_date || null },
            {
              onSuccess: (exp) => {
                onClose();
                router.push(experimentHref(exp.id));
              },
            },
          );
        }}
      >
        <Field label="Name" htmlFor="exp-name">
          <Input
            id="exp-name"
            value={form.name}
            onChange={(e) => patch({ name: e.target.value })}
            required
            autoFocus
            maxLength={200}
            placeholder="e.g. One-page mobile checkout"
          />
        </Field>
        <Field
          label="Hypothesis"
          htmlFor="exp-hyp"
          hint="If we [change], then [metric] will [move] because [mechanism]."
        >
          <Textarea
            id="exp-hyp"
            value={form.hypothesis}
            onChange={(e) => patch({ hypothesis: e.target.value })}
            required
            className="min-h-16"
          />
        </Field>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Primary metric" htmlFor="exp-primary" hint="The one number the decision hinges on.">
            <Select
              id="exp-primary"
              value={form.primary_metric}
              onChange={(e) =>
                patch({
                  primary_metric: e.target.value,
                  guardrail_metrics: form.guardrail_metrics?.filter((g) => g !== e.target.value) ?? [],
                })
              }
            >
              {metrics.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Guardrails" hint="Must not get significantly worse. Pick up to three.">
            <div className="flex flex-wrap gap-1.5">
              {guardrailOptions.map((m) => {
                const on = form.guardrail_metrics?.includes(m.key) ?? false;
                return (
                  <button
                    key={m.key}
                    type="button"
                    aria-pressed={on}
                    onClick={() => {
                      const cur = form.guardrail_metrics ?? [];
                      patch({
                        guardrail_metrics: on
                          ? cur.filter((g) => g !== m.key)
                          : cur.length < 3
                            ? [...cur, m.key]
                            : cur,
                      });
                    }}
                    className={
                      on
                        ? "border-accent/30 bg-accent-soft text-accent rounded-sm border px-1.5 py-px text-xs"
                        : "border-border text-fg-muted hover:text-fg rounded-sm border px-1.5 py-px text-xs"
                    }
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          </Field>
        </div>

        <fieldset className="border-border bg-surface rounded-sm border p-3">
          <legend className="text-fg px-1 text-xs font-medium">Variants</legend>
          <div className="space-y-2">
            {form.variants.map((v, i) => (
              <div key={i} className="grid grid-cols-[1fr_1.4fr_72px_auto_auto] items-end gap-2">
                <Field label={i === 0 ? "Key" : ""} htmlFor={`v-key-${i}`}>
                  <Input
                    id={`v-key-${i}`}
                    value={v.key}
                    pattern="[a-z0-9_]+"
                    onChange={(e) => setVariant(i, { key: slug(e.target.value) })}
                    required
                    className="font-mono"
                  />
                </Field>
                <Field label={i === 0 ? "Name" : ""} htmlFor={`v-name-${i}`}>
                  <Input
                    id={`v-name-${i}`}
                    value={v.name}
                    onChange={(e) => setVariant(i, { name: e.target.value })}
                    required
                  />
                </Field>
                <Field label={i === 0 ? "Weight" : ""} htmlFor={`v-w-${i}`}>
                  <Input
                    id={`v-w-${i}`}
                    type="number"
                    min={1}
                    max={100}
                    value={v.weight}
                    onChange={(e) => setVariant(i, { weight: Number(e.target.value) })}
                    className="tabular"
                  />
                </Field>
                <label className="text-fg-muted flex h-8 items-center gap-1.5 text-xs">
                  <input
                    type="radio"
                    name="control"
                    checked={v.is_control}
                    onChange={() =>
                      setForm((f) => ({
                        ...f,
                        variants: f.variants.map((x, j) => ({ ...x, is_control: j === i })),
                      }))
                    }
                  />
                  control
                </label>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="Remove variant"
                  disabled={form.variants.length <= 2}
                  onClick={() => setForm((f) => ({ ...f, variants: f.variants.filter((_, j) => j !== i) }))}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="text-fg-subtle text-xs">
              Weights are relative;{" "}
              {form.variants.map((v) => Math.round((v.weight / weightTotal) * 100)).join(" / ")}% split of{" "}
              {form.traffic_percent}% traffic.
            </span>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={form.variants.length >= 5}
              onClick={() =>
                setForm((f) => ({
                  ...f,
                  variants: [
                    ...f.variants,
                    {
                      key: `variant_${f.variants.length}`,
                      name: `Variant ${f.variants.length}`,
                      description: "",
                      weight: 50,
                      is_control: false,
                    },
                  ],
                }))
              }
            >
              <Plus className="size-3.5" />
              Add variant
            </Button>
          </div>
        </fieldset>

        <div className="grid gap-3 md:grid-cols-[1fr_120px_140px]">
          <Field label="Audience" hint="Who is eligible. Leave empty for everyone.">
            <FilterBuilder
              filters={form.audience_filters ?? []}
              onChange={(audience_filters) => patch({ audience_filters })}
              dimensions={(range.meta?.dimensions ?? []).filter((d) => d.scope === "session")}
              compact
            />
          </Field>
          <Field label="Traffic %" htmlFor="exp-traffic">
            <Input
              id="exp-traffic"
              type="number"
              min={1}
              max={100}
              value={form.traffic_percent}
              onChange={(e) => patch({ traffic_percent: Number(e.target.value) })}
              className="tabular"
            />
          </Field>
          <Field label="Start" htmlFor="exp-start">
            <Input
              id="exp-start"
              type="date"
              value={form.start_date ?? ""}
              onChange={(e) => patch({ start_date: e.target.value || null })}
            />
          </Field>
        </div>

        <fieldset className="border-border bg-surface rounded-sm border p-3">
          <legend className="text-fg px-1 text-xs font-medium">Decision rules</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field
              label="Min. detectable lift"
              htmlFor="exp-mde"
              hint="Smallest relative change worth shipping."
            >
              <div className="flex items-center gap-1.5">
                <Input
                  id="exp-mde"
                  type="number"
                  min={0.5}
                  max={100}
                  step={0.5}
                  value={Math.round(form.min_relative_effect! * 1000) / 10}
                  onChange={(e) => patch({ min_relative_effect: Number(e.target.value) / 100 })}
                  className="tabular"
                />
                <span className="text-fg-subtle text-xs">%</span>
              </div>
            </Field>
            <Field label="Min. users per variant" htmlFor="exp-n">
              <Input
                id="exp-n"
                type="number"
                min={100}
                step={100}
                value={form.min_sample_per_variant}
                onChange={(e) => patch({ min_sample_per_variant: Number(e.target.value) })}
                className="tabular"
              />
            </Field>
            <Field
              label="Min. duration (days)"
              htmlFor="exp-days"
              hint="At least a week covers weekday effects."
            >
              <Input
                id="exp-days"
                type="number"
                min={1}
                max={90}
                value={form.min_duration_days}
                onChange={(e) => patch({ min_duration_days: Number(e.target.value) })}
                className="tabular"
              />
            </Field>
          </div>
        </fieldset>

        {create.isError ? <ErrorState error={create.error} className="py-2" /> : null}
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={create.isPending}>
            Create draft
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
