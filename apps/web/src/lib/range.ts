"use client";

import { useAnalyticsMeta } from "@/lib/api/analytics";
import { useDateRange } from "@/lib/date-range";

export function useRange() {
  const meta = useAnalyticsMeta();
  const range = useDateRange(meta.data?.data_end ?? undefined);
  return { ...range, ready: meta.isSuccess, meta: meta.data, dataEnd: meta.data?.data_end ?? undefined };
}
