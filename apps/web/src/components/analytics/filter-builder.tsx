"use client";

import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import type { DimensionInfo, Filter } from "@/lib/api/analytics";

export function describeFilter(f: Filter, dims: DimensionInfo[]) {
  const label = dims.find((d) => d.key === f.dimension)?.label ?? f.dimension;
  const op = f.operator === "neq" ? "≠" : f.operator === "in" ? "in" : f.operator === "not_in" ? "not in" : "=";
  const value = f.values ? f.values.join(", ") : String(f.value ?? "");
  return `${label} ${op} ${value}`;
}

export function FilterBuilder({
  filters,
  onChange,
  dimensions,
  compact,
}: {
  filters: Filter[];
  onChange: (next: Filter[]) => void;
  dimensions: DimensionInfo[];
  compact?: boolean;
}) {
  const update = (i: number, patch: Partial<Filter>) => {
    const next = filters.map((f, idx) => (idx === i ? { ...f, ...patch } : f));
    onChange(next);
  };
  const remove = (i: number) => onChange(filters.filter((_, idx) => idx !== i));
  const add = () => {
    const dim = dimensions[0];
    onChange([...filters, { dimension: dim.key, operator: "eq", value: dim.values[0] ?? "" }]);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {filters.map((f, i) => {
        const dim = dimensions.find((d) => d.key === f.dimension);
        const values = dim?.values ?? [];
        return (
          <div key={i} className="flex items-center gap-1 rounded-sm border border-border bg-surface p-1">
            <Select
              aria-label="Dimension"
              className="h-6 w-auto border-0 bg-transparent py-0 pl-1 text-xs"
              value={f.dimension}
              onChange={(e) => {
                const d = dimensions.find((x) => x.key === e.target.value)!;
                update(i, { dimension: d.key, value: d.values[0] ?? "" });
              }}
            >
              {dimensions.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.label}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Operator"
              className="h-6 w-auto border-0 bg-transparent py-0 pl-1 text-xs"
              value={f.operator ?? "eq"}
              onChange={(e) => update(i, { operator: e.target.value as Filter["operator"] })}
            >
              <option value="eq">=</option>
              <option value="neq">≠</option>
            </Select>
            {values.length > 0 ? (
              <Select
                aria-label="Value"
                className="h-6 w-auto max-w-48 border-0 bg-transparent py-0 pl-1 text-xs"
                value={String(f.value ?? "")}
                onChange={(e) => update(i, { value: e.target.value })}
              >
                {values.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                aria-label="Value"
                className="h-6 w-28 border-0 bg-transparent text-xs"
                value={String(f.value ?? "")}
                onChange={(e) => update(i, { value: e.target.value })}
              />
            )}
            <button
              type="button"
              aria-label="Remove filter"
              className="rounded-sm p-0.5 text-fg-subtle hover:bg-surface-2 hover:text-fg"
              onClick={() => remove(i)}
            >
              <X className="size-3" />
            </button>
          </div>
        );
      })}
      <Button variant="ghost" size="sm" onClick={add} disabled={!dimensions.length}>
        <Plus className="size-3.5" />
        {compact && filters.length ? null : "Filter"}
      </Button>
    </div>
  );
}
