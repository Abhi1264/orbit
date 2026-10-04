import type { BadgeTone } from "@/components/ui/badge";

export type IntegrationState = "connected" | "not_configured" | "needs_setup" | "invalid_key" | "unreachable";

export type AmplitudeDelivery = "delivered" | "failed" | "pending" | "not_configured" | "unknown";

const STATE: Record<IntegrationState, { label: string; tone: BadgeTone }> = {
  connected: { label: "Connected", tone: "success" },
  not_configured: { label: "Not configured", tone: "neutral" },
  needs_setup: { label: "Needs setup", tone: "warning" },
  invalid_key: { label: "Key rejected", tone: "danger" },
  unreachable: { label: "Unreachable", tone: "danger" },
};

const DELIVERY: Record<AmplitudeDelivery, { label: string; tone: BadgeTone }> = {
  delivered: { label: "✓ Delivered", tone: "success" },
  failed: { label: "✗ Failed", tone: "danger" },
  pending: { label: "Pending", tone: "warning" },
  not_configured: { label: "Not configured", tone: "neutral" },
  unknown: { label: "Not tracked", tone: "neutral" },
};

export function integrationBadge(state: IntegrationState) {
  return STATE[state];
}

export function deliveryBadge(delivery: AmplitudeDelivery) {
  return DELIVERY[delivery];
}

export function showAnalyticsDebugger(nodeEnv: string | undefined, apiAllows: boolean | undefined) {
  return nodeEnv === "development" && apiAllows === true;
}

export function exportSummary(e: {
  sent: number;
  delivered: number;
  failed: number;
  unconfirmed: number;
  deferred: number;
}) {
  const n = (v: number) => v.toLocaleString("en-IN");
  const parts = [`${n(e.sent)} sent`, `${n(e.delivered)} delivered`];
  if (e.failed) parts.push(`${n(e.failed)} failed`);
  if (e.unconfirmed) parts.push(`${n(e.unconfirmed)} unconfirmed`);
  if (e.deferred) parts.push(`${n(e.deferred)} deferred (future-dated)`);
  return parts.join(" · ");
}

export function propertyPairs(properties: Record<string, unknown>): [string, string][] {
  return Object.entries(properties).map(([key, value]) => [
    key,
    Array.isArray(value)
      ? value.join(", ")
      : typeof value === "object" && value !== null
        ? JSON.stringify(value)
        : String(value),
  ]);
}
