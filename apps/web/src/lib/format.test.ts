import { describe, expect, it } from "vitest";

import { formatDelta, formatMetric, titleCase } from "./format";

describe("formatMetric", () => {
  it("renders empty values as an em dash", () => {
    expect(formatMetric(null, "count")).toBe("—");
    expect(formatMetric(Number.NaN, "percent")).toBe("—");
  });

  it("formats rates as percents and counts with grouping", () => {
    expect(formatMetric(0.084, "percent")).toBe("8.40%");
    expect(formatMetric(1600, "count")).toBe("1,600");
  });
});

describe("formatDelta", () => {
  it("expresses rate moves in percentage points", () => {
    expect(formatDelta(0.12, 0.1, "percent")).toEqual({ text: "+2.00 pp", sign: 1 });
  });

  it("expresses everything else as relative percent", () => {
    expect(formatDelta(110, 100, "count")).toEqual({ text: "+10.0%", sign: 1 });
    expect(formatDelta(90, 100, "currency")).toEqual({ text: "-10.0%", sign: -1 });
  });

  it("returns null when a side is missing or the baseline is zero", () => {
    expect(formatDelta(1, null, "count")).toBeNull();
    expect(formatDelta(1, 0, "count")).toBeNull();
  });
});

describe("titleCase", () => {
  it("turns snake_case status keys into labels", () => {
    expect(titleCase("in_progress")).toBe("In Progress");
  });
});
