import { beforeEach, describe, expect, it, vi } from "vitest";

import { getEntitlementMetricDefinitions } from "../subscriptionEntitlements";

const inspirationFeature = vi.hoisted(() => ({ enabled: true }));

vi.mock("../../config/inspirations", () => ({
  inspirationsConfig: inspirationFeature,
}));

const t = (_key: string, fallback: string) => fallback;

describe("getEntitlementMetricDefinitions", () => {
  beforeEach(() => {
    inspirationFeature.enabled = true;
  });

  it("includes inspiration copy entitlements when enabled", () => {
    expect(getEntitlementMetricDefinitions(t, "zh-CN").map((metric) => metric.key))
      .toContain("inspiration_copies_monthly");
  });

  it("omits inspiration copy entitlements when disabled", () => {
    inspirationFeature.enabled = false;

    expect(getEntitlementMetricDefinitions(t, "zh-CN").map((metric) => metric.key))
      .not.toContain("inspiration_copies_monthly");
  });
});
