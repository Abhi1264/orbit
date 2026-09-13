"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";
import { useExperiments } from "@/lib/api/experiments";
import { type ReleaseCreate, useReleaseMutations, useSops } from "@/lib/api/ops";
import { releaseHref } from "@/lib/links";
import { useRange } from "@/lib/range";

const AREAS = [
  "checkout",
  "payments",
  "search",
  "discovery",
  "product_page",
  "cart",
  "wishlist",
  "account",
  "delivery",
];

export function NewReleaseDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open ? <NewReleaseForm onClose={() => onOpenChange(false)} /> : null}
    </Dialog>
  );
}

function NewReleaseForm({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const range = useRange();
  const sops = useSops();
  const experiments = useExperiments("all");
  const { create } = useReleaseMutations();
  const [form, setForm] = useState<ReleaseCreate>({
    version: "",
    name: "",
    description: "",
    platform: "android",
    release_date: range.meta?.data_end ?? new Date().toISOString().slice(0, 10),
    affected_areas: [],
    experiment_id: null,
    sop_id: null,
  });
  const patch = (p: Partial<ReleaseCreate>) => setForm((f) => ({ ...f, ...p }));
  const toggleArea = (a: string) =>
    patch({
      affected_areas: form.affected_areas?.includes(a)
        ? form.affected_areas.filter((x) => x !== a)
        : [...(form.affected_areas ?? []), a],
    });

  return (
    <DialogContent
      title="New release"
      description="Log what is shipping, where, and which launch checklist applies. Anomalies detected after the release date will list it as a candidate cause."
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(form, {
            onSuccess: (rel) => {
              onClose();
              router.push(releaseHref(rel.id));
            },
          });
        }}
      >
        <div className="grid grid-cols-[1fr_9rem] gap-3">
          <Field label="Name" htmlFor="rel-name">
            <Input
              id="rel-name"
              required
              minLength={3}
              value={form.name}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="Android 8.5.0 — cart redesign"
            />
          </Field>
          <Field label="Version" htmlFor="rel-version">
            <Input
              id="rel-version"
              required
              value={form.version}
              onChange={(e) => patch({ version: e.target.value })}
              placeholder="8.5.0"
              className="font-mono"
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Platform" htmlFor="rel-platform">
            <Select
              id="rel-platform"
              value={form.platform}
              onChange={(e) => patch({ platform: e.target.value as ReleaseCreate["platform"] })}
            >
              <option value="android">Android</option>
              <option value="ios">iOS</option>
              <option value="web">Web</option>
              <option value="all">All platforms</option>
            </Select>
          </Field>
          <Field label="Release date" htmlFor="rel-date">
            <Input
              id="rel-date"
              type="date"
              required
              value={form.release_date}
              onChange={(e) => patch({ release_date: e.target.value })}
            />
          </Field>
        </div>
        <Field label="What changes" htmlFor="rel-desc">
          <Textarea
            id="rel-desc"
            value={form.description ?? ""}
            onChange={(e) => patch({ description: e.target.value })}
            placeholder="One paragraph a PM can read six weeks from now when this shows up as a root-cause candidate."
          />
        </Field>
        <Field label="Affected areas" hint="Used to pick the extra metrics in the post-launch read.">
          <div className="flex flex-wrap gap-1.5">
            {AREAS.map((a) => {
              const on = form.affected_areas?.includes(a);
              return (
                <button
                  key={a}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleArea(a)}
                  className={
                    on
                      ? "border-accent bg-accent-soft text-accent rounded-sm border px-2 py-0.5 text-xs"
                      : "border-border text-fg-muted hover:text-fg rounded-sm border px-2 py-0.5 text-xs"
                  }
                >
                  {a.replace(/_/g, " ")}
                </button>
              );
            })}
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Launch checklist (SOP)" htmlFor="rel-sop">
            <Select
              id="rel-sop"
              value={form.sop_id ?? ""}
              onChange={(e) => patch({ sop_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">None</option>
              {(sops.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Ships an experiment" htmlFor="rel-exp">
            <Select
              id="rel-exp"
              value={form.experiment_id ?? ""}
              onChange={(e) => patch({ experiment_id: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">None</option>
              {(experiments.data ?? []).map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {create.isError ? <ErrorState error={create.error} className="py-3" /> : null}
        <DialogFooter>
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={create.isPending}>
            Create release
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
