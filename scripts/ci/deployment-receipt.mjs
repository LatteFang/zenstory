#!/usr/bin/env node

import { writeFile } from "node:fs/promises";

const shaPattern = /^[a-f0-9]{40}$/;
const githubActionsAppId = 15368;

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

function normalizeWorkflowPath(value) {
  return String(value ?? "").replace(/^\//, "");
}

export function validateDeploymentCiProof({ repository, sourceSha, requestedRunId, workflow, run, jobs, checkSuite }) {
  invariant(repository === "zenstory-ai/zenstory", `unexpected repository: ${repository}`);
  invariant(shaPattern.test(sourceSha), `invalid source SHA: ${sourceSha}`);
  invariant(/^\d+$/.test(String(requestedRunId)), `invalid CI run ID: ${requestedRunId}`);
  invariant(normalizeWorkflowPath(workflow?.path) === ".github/workflows/ci.yml", "CI workflow path mismatch");
  invariant(Number(run?.id) === Number(requestedRunId), "CI run ID mismatch");
  invariant(Number(run?.workflow_id) === Number(workflow.id), "CI workflow ID mismatch");
  invariant(normalizeWorkflowPath(run?.path) === ".github/workflows/ci.yml", "CI run path mismatch");
  invariant(run?.head_sha === sourceSha, "CI run source SHA mismatch");
  invariant(run?.head_branch === "main" && run?.event === "push", "CI proof must be a main push run");
  invariant(run?.status === "completed" && run?.conclusion === "success", "CI run did not succeed");
  invariant(Number(checkSuite?.app?.id) === githubActionsAppId, "CI check suite is not GitHub Actions");
  const summaries = jobs.filter((job) => job.name === "ci-summary");
  invariant(summaries.length === 1, "missing or ambiguous ci-summary job");
  invariant(
    summaries[0].status === "completed" && summaries[0].conclusion === "success",
    `ci-summary did not succeed: ${summaries[0].status}/${summaries[0].conclusion}`,
  );
  return {
    schemaVersion: 1,
    repository,
    sourceSha,
    workflowId: Number(workflow.id),
    workflowPath: ".github/workflows/ci.yml",
    runId: Number(run.id),
    runAttempt: Number(run.run_attempt),
    checkSuiteId: Number(run.check_suite_id),
    checkSuiteAppId: githubActionsAppId,
    requiredJobs: ["ci-summary"],
  };
}

async function githubJson(url, token) {
  let response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "User-Agent": "zenstory-deployment-receipt",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    });
  } catch (error) {
    throw new Error(`GitHub request failed before an HTTP response: ${error.message}`, { cause: error });
  }
  const text = await response.text();
  if (!response.ok) throw new Error(`GitHub request failed with HTTP ${response.status}: ${text.slice(0, 200)}`);
  return JSON.parse(text);
}

async function collectJobs(repository, runId, attempt, token) {
  const jobs = [];
  for (let page = 1; page <= 10; page += 1) {
    const body = await githubJson(
      `https://api.github.com/repos/${repository}/actions/runs/${runId}/attempts/${attempt}/jobs?per_page=100&page=${page}`,
      token,
    );
    invariant(Array.isArray(body.jobs), "unexpected jobs response");
    jobs.push(...body.jobs);
    if (body.jobs.length < 100) break;
  }
  return jobs;
}

async function main() {
  const [repository, sourceSha, requestedRunId, output] = process.argv.slice(2);
  const token = process.env.GITHUB_TOKEN;
  invariant(token, "GITHUB_TOKEN is required");
  invariant(output, "usage: deployment-receipt.mjs REPOSITORY SOURCE_SHA RUN_ID OUTPUT");
  const base = `https://api.github.com/repos/${repository}`;
  const workflow = await githubJson(`${base}/actions/workflows/ci.yml`, token);
  const run = await githubJson(`${base}/actions/runs/${requestedRunId}`, token);
  const jobs = await collectJobs(repository, requestedRunId, run.run_attempt, token);
  const checkSuite = await githubJson(`${base}/check-suites/${run.check_suite_id}`, token);
  const proof = validateDeploymentCiProof({ repository, sourceSha, requestedRunId, workflow, run, jobs, checkSuite });
  await writeFile(output, `${JSON.stringify(proof, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(proof)}\n`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    process.stderr.write(`deployment-receipt: ${error.message}\n`);
    process.exitCode = 1;
  });
}
