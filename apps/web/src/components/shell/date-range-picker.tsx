"use client";

import { differenceInCalendarDays, parseISO, subDays } from "date-fns";
import { CalendarDays } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/menu";
import { type Comparison, isoDate, useDateRange } from "@/lib/date-range";
import { formatDate } from "@/lib/format";

const PRESETS = [7, 14, 28, 56];

const COMPARISONS: { value: Comparison; label: string }[] = [
  { value: "previous_period", label: "Previous period" },
  { value: "previous_week", label: "Previous week" },
  { value: "previous_month", label: "Previous month" },
  { value: "none", label: "No comparison" },
];

export function DateRangePicker({ dataStart, dataEnd }: { dataStart?: string; dataEnd?: string }) {
  const range = useDateRange(dataEnd);
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);

  const days = differenceInCalendarDays(parseISO(range.to), parseISO(range.from)) + 1;
  const activePreset = PRESETS.find((p) => p === days && range.to === (dataEnd ?? range.to));

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setFrom(range.from);
          setTo(range.to);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button size="sm" aria-label="Change date range">
          <CalendarDays className="text-fg-subtle size-3.5" aria-hidden />
          <span className="tabular">
            {formatDate(range.from)} –{" "}
            {formatDate(range.to, { month: "short", day: "numeric", year: "numeric" })}
          </span>
          <span className="text-fg-subtle">· {days}d</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" align="end">
        <div className="mb-3 flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <Button
              key={p}
              size="sm"
              variant={activePreset === p ? "primary" : "secondary"}
              onClick={() => {
                const end = dataEnd ? parseISO(dataEnd) : new Date();
                range.set({ from: isoDate(subDays(end, p - 1)), to: isoDate(end) });
                setOpen(false);
              }}
            >
              Last {p} days
            </Button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Field label="From" htmlFor="range-from">
            <Input
              id="range-from"
              type="date"
              value={from}
              min={dataStart}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
            />
          </Field>
          <Field label="To" htmlFor="range-to">
            <Input
              id="range-to"
              type="date"
              value={to}
              min={from}
              max={dataEnd}
              onChange={(e) => setTo(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Compare to" htmlFor="range-compare" className="mt-2">
          <Select
            id="range-compare"
            value={range.comparison}
            onChange={(e) => range.set({ comparison: e.target.value as Comparison })}
          >
            {COMPARISONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>
        {dataStart && dataEnd ? (
          <p className="text-2xs text-fg-subtle mt-2">
            Data available {formatDate(dataStart)} –{" "}
            {formatDate(dataEnd, { month: "short", day: "numeric", year: "numeric" })}
          </p>
        ) : null}
        <div className="mt-3 flex justify-end">
          <Button
            size="sm"
            variant="primary"
            disabled={!from || !to || from > to}
            onClick={() => {
              range.set({ from, to });
              setOpen(false);
            }}
          >
            Apply
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
