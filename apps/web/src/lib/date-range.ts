"use client";

import { addDays, differenceInCalendarDays, format, parseISO, subDays } from "date-fns";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";

export type Comparison = "previous_period" | "previous_week" | "previous_month" | "none";

export interface DateRange {
  from: string;
  to: string;
  comparison: Comparison;
  /** Comparison window derived from the primary window. */
  compareFrom: string | null;
  compareTo: string | null;
  days: number;
}

export const DEFAULT_WINDOW_DAYS = 28;

export function isoDate(d: Date) {
  return format(d, "yyyy-MM-dd");
}

export function computeComparison(from: string, to: string, comparison: Comparison) {
  if (comparison === "none") return { compareFrom: null, compareTo: null };
  const f = parseISO(from);
  const t = parseISO(to);
  const len = differenceInCalendarDays(t, f) + 1;
  const shift = comparison === "previous_period" ? len : comparison === "previous_week" ? 7 : 30;
  return { compareFrom: isoDate(subDays(f, shift)), compareTo: isoDate(subDays(t, shift)) };
}

/**
 * Global date range lives in the URL so any view is shareable. When no range is
 * set, callers pass the dataset's last available day so defaults follow the data
 * rather than the wall clock.
 */
export function useDateRange(dataEnd?: string): DateRange & {
  set: (next: Partial<Pick<DateRange, "from" | "to" | "comparison">>) => void;
} {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const anchor = dataEnd ? parseISO(dataEnd) : new Date();
  const to = params.get("to") ?? isoDate(anchor);
  const from = params.get("from") ?? isoDate(subDays(parseISO(to), DEFAULT_WINDOW_DAYS - 1));
  const comparison = (params.get("compare") as Comparison | null) ?? "previous_period";

  const set = useCallback(
    (next: Partial<Pick<DateRange, "from" | "to" | "comparison">>) => {
      const sp = new URLSearchParams(params.toString());
      if (next.from) sp.set("from", next.from);
      if (next.to) sp.set("to", next.to);
      if (next.comparison) sp.set("compare", next.comparison);
      router.replace(`${pathname}?${sp.toString()}` as "/");
    },
    [params, pathname, router],
  );

  return useMemo(() => {
    const cmp = computeComparison(from, to, comparison);
    return {
      from,
      to,
      comparison,
      ...cmp,
      days: differenceInCalendarDays(parseISO(to), parseISO(from)) + 1,
      set,
    };
  }, [from, to, comparison, set]);
}

export function shiftRange(range: { from: string; to: string }, days: number) {
  return {
    from: isoDate(addDays(parseISO(range.from), days)),
    to: isoDate(addDays(parseISO(range.to), days)),
  };
}
