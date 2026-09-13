"use client";

import { useAnalyticsMeta } from "@/lib/api/analytics";
import { useDateRange } from "@/lib/date-range";

/** Global date range anchored to the dataset's last day. */
export function useRange() {
  const meta = useAnalyticsMeta();
  const range = useDateRange(meta.data?.data_end ?? undefined);
  return { ...range, ready: meta.isSuccess, meta: meta.data, dataEnd: meta.data?.data_end ?? undefined };
}
