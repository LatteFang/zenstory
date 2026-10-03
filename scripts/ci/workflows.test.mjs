import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);

test("changed workflows and composite actions pin every external action to a full SHA", async () => {
  for (const file of [
    ".github/workflows/ci.yml",
    ".github/workflows/e2e.yml",
    ".github/workflows/cli-release.yml",
    ".github/workflows/zenstory-online-smoke.yml",
    ".github/actions/setup-backend/action.yml",
    ".github/actions/setup-frontend/action.yml",
  ]) {
    const source = await readFile(file, "utf8");
    for (const match of source.matchAll(/^\s*- uses:\s*([^\s#]+)/gm)) {
      if (match[1].startsWith("./")) continue;
      assert.match(match[1], /@[a-f0-9]{40}$/i, `${file}: ${match[1]} is not full-SHA pinned`);
    }
  }
});

test("CI summary and E2E summary consume detector result and validated scope", async () => {
  const ci = await readFile(".github/workflows/ci.yml", "utf8");
  assert.match(ci, /DETECT_CHANGES_RESULT: \$\{\{ needs\['detect-changes'\]\.result \}\}/);
  assert.match(ci, /node scripts\/ci\/check-workflow-results\.mjs ci/);
  assert.match(ci, /cancel-in-progress: \$\{\{ github\.event_name == 'pull_request' \|\| github\.ref != 'refs\/heads\/main' \}\}/);

  const e2e = await readFile(".github/workflows/e2e.yml", "utf8");
  assert.match(e2e, /github\.event_name == 'schedule' \|\| github\.event_name == 'workflow_dispatch'/);
  assert.match(e2e, /node scripts\/ci\/check-workflow-results\.mjs e2e/);
  assert.match(e2e, /Malformed paths-filter output/);
});

test("online smoke is read-only, source-bound, canonical-origin only, and not a provider gate claim", async () => {
  const workflow = await readFile(".github/workflows/zenstory-online-smoke.yml", "utf8");
  assert.match(workflow, /source_sha:/);
  assert.match(workflow, /ci_run_id:/);
  assert.match(workflow, /providerSourceBinding: 'NOT_VERIFIED'/);
  assert.match(workflow, /providerGate: 'NOT_VERIFIED'/);
  assert.doesNotMatch(workflow, /VERCEL_TOKEN|RAILWAY_TOKEN|vercel deploy|railway (up|deploy)|secrets\./i);

  await assert.rejects(
    execFileAsync("bash", ["scripts/ci/zenstory-online-smoke.sh"], {
      env: {
        ...process.env,
        ZENSTORY_BACKEND_URL: "https://example.invalid",
        ZENSTORY_FRONTEND_URL: "https://app.zenstory.ai",
      },
    }),
    /Refusing noncanonical backend origin/,
  );
  await assert.rejects(
    execFileAsync("bash", ["scripts/ci/zenstory-online-smoke.sh"], {
      env: {
        ...process.env,
        ZENSTORY_BACKEND_URL: "https://api.zenstory.ai",
        ZENSTORY_FRONTEND_URL: "https://example.invalid",
      },
    }),
    /Refusing noncanonical frontend origin/,
  );
});

test("regression controls are required CI and npm version comes from the npm executable", async () => {
  const workflow = await readFile(".github/workflows/cli-release.yml", "utf8");
  assert.doesNotMatch(workflow, /process\.versions\.npm/);
  assert.match(workflow, /node scripts\/cli-release\.mjs npm-version/);
  const ci = await readFile(".github/workflows/ci.yml", "utf8");
  assert.match(ci, /node --test scripts\/ci\/\*\.test\.mjs/);
  assert.match(ci, /node --test scripts\/cli-release\.test\.mjs/);
  assert.match(ci, /'scripts\/cli-release\*\.mjs'/);
});
