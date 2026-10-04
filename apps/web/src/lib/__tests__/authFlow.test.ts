import { describe, expect, it } from "vitest";
import { consumeOAuthPlanIntent, normalizePlanIntent, saveOAuthPlanIntent } from "../authFlow";

describe("normalizePlanIntent", () => {
  it("returns normalized value for known plans", () => {
    expect(normalizePlanIntent("PRO")).toBe("pro");
    expect(normalizePlanIntent(" free ")).toBe("free");
  });

  it("returns null for unknown plan values", () => {
    expect(normalizePlanIntent("enterprise")).toBeNull();
    expect(normalizePlanIntent("studio")).toBeNull();
    expect(normalizePlanIntent("")).toBeNull();
    expect(normalizePlanIntent(null)).toBeNull();
    expect(normalizePlanIntent(undefined)).toBeNull();
  });
});

describe("OAuth plan intent", () => {
  it("normalizes and consumes the intent once", () => {
    sessionStorage.clear();
    saveOAuthPlanIntent(" PRO ");
    expect(consumeOAuthPlanIntent()).toBe("pro");
    expect(consumeOAuthPlanIntent()).toBeNull();
  });

  it("does not persist unknown intent", () => {
    sessionStorage.clear();
    saveOAuthPlanIntent("enterprise");
    expect(consumeOAuthPlanIntent()).toBeNull();
  });
});
