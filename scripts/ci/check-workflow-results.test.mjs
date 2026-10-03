import assert from "node:assert/strict";
import test from "node:test";

import { validateCiSummary, validateE2eSummary } from "./check-workflow-results.mjs";

const irrelevantJobs = {
  "frontend-lint": "skipped",
  "ci-lint": "skipped",
  "backend-test": "skipped",
  "prefect-compatibility": "skipped",
  "production-images": "skipped",
  "frontend-test": "skipped",
  "frontend-build": "skipped",
  "cli-test": "skipped",
  "vercel-build": "skipped",
};

test("CI permits skipped jobs only when their validated scope is irrelevant", () => {
  assert.deepEqual(
    validateCiSummary({
      detector: "success",
      outputs: { backend: "false", frontend: "true", cli: "false", ci: "false" },
      jobs: {
        ...irrelevantJobs,
        "frontend-lint": "success",
        "frontend-test": "success",
        "frontend-build": "success",
        "vercel-build": "success",
      },
    }).scopes,
    { backend: false, frontend: true, cli: false, ci: false },
  );
});

test("CI fails closed on detector failure even when every downstream job skipped", () => {
  assert.throws(
    () => validateCiSummary({
      detector: "failure",
      outputs: { backend: "", frontend: "", cli: "", ci: "" },
      jobs: irrelevantJobs,
    }),
    /detect-changes did not succeed/,
  );
});

test("CI rejects malformed scope outputs and a skipped relevant job", () => {
  assert.throws(
    () => validateCiSummary({
      detector: "success",
      outputs: { backend: "", frontend: "false", cli: "false", ci: "false" },
      jobs: irrelevantJobs,
    }),
    /backend output must be true or false/,
  );
  assert.throws(
    () => validateCiSummary({
      detector: "success",
      outputs: { backend: "false", frontend: "true", cli: "false", ci: "false" },
      jobs: irrelevantJobs,
    }),
    /frontend-lint was required but finished as skipped/,
  );
});

test("CI workflow changes require every conditional gate", () => {
  const successJobs = Object.fromEntries(Object.keys(irrelevantJobs).map((name) => [name, "success"]));
  assert.doesNotThrow(() => validateCiSummary({
    detector: "success",
    outputs: { backend: "false", frontend: "false", cli: "false", ci: "true" },
    jobs: successJobs,
  }));
  assert.throws(
    () => validateCiSummary({
      detector: "success",
      outputs: { backend: "false", frontend: "false", cli: "false", ci: "true" },
      jobs: { ...successJobs, "cli-test": "cancelled" },
    }),
    /cli-test was required but finished as cancelled/,
  );
});

test("scheduled and manual E2E runs are forced regardless of changed paths", () => {
  for (const eventName of ["schedule", "workflow_dispatch"]) {
    assert.equal(validateE2eSummary({
      detector: "success",
      outputs: { backend: "false", frontend: "false", ci: "false" },
      eventName,
      jobResult: "success",
    }).forced, true);
    assert.throws(
      () => validateE2eSummary({
        detector: "success",
        outputs: { backend: "false", frontend: "false", ci: "false" },
        eventName,
        jobResult: "skipped",
      }),
      /e2e-test was required but finished as skipped/,
    );
  }
});

test("push E2E permits skip only when every validated scope is false", () => {
  assert.doesNotThrow(() => validateE2eSummary({
    detector: "success",
    outputs: { backend: "false", frontend: "false", ci: "false" },
    eventName: "push",
    jobResult: "skipped",
  }));
  assert.throws(
    () => validateE2eSummary({
      detector: "success",
      outputs: { backend: "true", frontend: "false", ci: "false" },
      eventName: "push",
      jobResult: "failure",
    }),
    /e2e-test was required but finished as failure/,
  );
});
