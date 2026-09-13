"use client";

import { Line, LineChart } from "recharts";

export function Sparkline({
  points,
  compare,
  height = 32,
  color = "var(--color-accent)",
}: {
  points: { bucket: string; value: number | null }[];
  compare?: { bucket: string; value: number | null }[];
  height?: number;
  color?: string;
}) {
  const data = points.map((p, i) => ({ i, v: p.value, c: compare?.[i]?.value ?? null }));
  return (
    <LineChart responsive data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }} style={{ width: "100%", height }}>
      {compare?.length ? (
        <Line type="monotone" dataKey="c" stroke="var(--color-border-strong)" strokeWidth={1} dot={false} isAnimationActive={false} connectNulls />
      ) : null}
      <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
    </LineChart>
  );
}
