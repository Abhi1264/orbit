import { describe, expect, it } from "vitest";

import {
  deliveryBadge,
  exportSummary,
  integrationBadge,
  propertyPairs,
  showAnalyticsDebugger,
} from "./integrations";

describe("integrationBadge", () => {
  it("only calls a live, accepted connection connected", () => {
    expect(integrationBadge("connected")).toEqual({ label: "Connected", tone: "success" });
    expect(integrationBadge("not_configured").label).toBe("Not configured");
    expect(integrationBadge("invalid_key").tone).toBe("danger");
    expect(integrationBadge("unreachable").tone).toBe("danger");
    expect(integrationBadge("needs_setup").tone).toBe("warning");
  });
});

describe("deliveryBadge", () => {
  it("marks only confirmed deliveries with a check", () => {
    expect(deliveryBadge("delivered").label).toContain("✓");
    for (const state of ["failed", "pending", "not_configured", "unknown"] as const) {
      expect(deliveryBadge(state).label).not.toContain("✓");
    }
  });
});

describe("showAnalyticsDebugger", () => {
  it("never shows outside next dev, whatever the API says", () => {
    expect(showAnalyticsDebugger("production", true)).toBe(false);
    expect(showAnalyticsDebugger("test", true)).toBe(false);
    expect(showAnalyticsDebugger(undefined, true)).toBe(false);
  });

  it("needs the API to allow it too", () => {
    expect(showAnalyticsDebugger("development", false)).toBe(false);
    expect(showAnalyticsDebugger("development", undefined)).toBe(false);
    expect(showAnalyticsDebugger("development", true)).toBe(true);
  });
});

describe("exportSummary", () => {
  it("lists failures and deferrals only when there are some", () => {
    expect(exportSummary({ sent: 1200, delivered: 1200, failed: 0, unconfirmed: 0, deferred: 0 })).toBe(
      "1,200 sent · 1,200 delivered",
    );
    expect(exportSummary({ sent: 10, delivered: 7, failed: 2, unconfirmed: 1, deferred: 4 })).toBe(
      "10 sent · 7 delivered · 2 failed · 1 unconfirmed · 4 deferred (future-dated)",
    );
  });
});

describe("propertyPairs", () => {
  it("renders lists and nested objects on one line", () => {
    expect(
      propertyPairs({ product_ids: ["1", "2"], price: 499, $set: { city_tier: "tier1" }, query: "shoes" }),
    ).toEqual([
      ["product_ids", "1, 2"],
      ["price", "499"],
      ["$set", '{"city_tier":"tier1"}'],
      ["query", "shoes"],
    ]);
  });
});
