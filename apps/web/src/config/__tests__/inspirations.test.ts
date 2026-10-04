import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("inspirationsConfig", () => {
  it.each([undefined, "", "false", "0", "off", "invalid"])(
    "keeps the optional library disabled for %s",
    async (value) => {
      vi.stubEnv("VITE_INSPIRATIONS_ENABLED", value);
      vi.resetModules();
      const { inspirationsConfig } = await import("../inspirations");
      expect(inspirationsConfig.enabled).toBe(false);
      const { DASHBOARD_FIRST_RUN_TOUR } = await import("../productTours/dashboardFirstRun");
      expect(DASHBOARD_FIRST_RUN_TOUR.steps.map((step) => step.id)).not.toContain("inspirations_link");
      expect(DASHBOARD_FIRST_RUN_TOUR.steps.find((step) => step.id === "inspiration_input")?.defaultDescription).not.toContain("下方推荐");
    },
  );

  it.each(["true", " TRUE\n", "1", "yes", "on"])(
    "explicitly enables the library for %s",
    async (value) => {
      vi.stubEnv("VITE_INSPIRATIONS_ENABLED", value);
      vi.resetModules();
      const { inspirationsConfig } = await import("../inspirations");
      expect(inspirationsConfig.enabled).toBe(true);
      const { DASHBOARD_FIRST_RUN_TOUR } = await import("../productTours/dashboardFirstRun");
      expect(DASHBOARD_FIRST_RUN_TOUR.steps.map((step) => step.id)).toContain("inspirations_link");
    },
  );
});
