import { formatDelta, type MetricFormat } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Period-over-period change. Colour encodes whether the move is good for the
 * business (not merely up or down), so a falling return rate reads green.
 */
export function DeltaText({
  current,
  previous,
  format,
  higherIsBetter = true,
  className,
}: {
  current: number | null | undefined;
  previous: number | null | undefined;
  format: MetricFormat;
  higherIsBetter?: boolean;
  className?: string;
}) {
  const delta = formatDelta(current ?? null, previous ?? null, format);
  if (!delta) return <span className={cn("text-fg-faint", className)}>—</span>;
  const good = delta.sign === 0 ? null : higherIsBetter ? delta.sign > 0 : delta.sign < 0;
  return (
    <span
      className={cn(
        "tabular",
        good === null ? "text-fg-subtle" : good ? "text-success" : "text-danger",
        className,
      )}
    >
      {delta.text}
    </span>
  );
}
