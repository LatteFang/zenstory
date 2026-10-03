import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  classifyHttpStatus,
  createReleaseManifest,
  npmPublicationDecision,
  selectCiProof,
  validatePackageEntries,
  validateReleaseMetadata,
  validateRunStability,
  validateNpmVersion,
  verifyPublicationSource,
  verifyReleaseManifest,
} from "./cli-release.mjs";

test("CLI dry-run accepts an explicit Unreleased candidate without publication", () => {
  assert.deepEqual(
    validateReleaseMetadata({
      packageVersion: "0.2.0",
      changelog: "## [Unreleased]\n\nCandidate: 0.2.0\n",
    }),
    { version: "0.2.0", tag: null, publishing: false },
  );
  assert.throws(
    () => validateReleaseMetadata({ packageVersion: "0.2.0", changelog: "## [Unreleased]\n" }),
    /candidate marker/,
  );
});

test("CLI publication requires cli-v namespace, matching version, and a dated heading", () => {
  const changelog = "## [Unreleased]\n\n## [0.2.0] - 2026-10-03\n";
  assert.deepEqual(
    validateReleaseMetadata({ tag: "cli-v0.2.0", packageVersion: "0.2.0", changelog, publishing: true }),
    { version: "0.2.0", tag: "cli-v0.2.0", publishing: true },
  );
  for (const tag of ["v0.2.0", "cli-v0.2", "cli-v0.2.0-rc.1", "cli-v00.2.0"]) {
    assert.throws(
      () => validateReleaseMetadata({ tag, packageVersion: "0.2.0", changelog, publishing: true }),
      /stable CLI release tag/,
    );
  }
  assert.throws(
    () => validateReleaseMetadata({
      tag: "cli-v0.2.0",
      packageVersion: "0.2.0",
      changelog: "## [Unreleased]\nCandidate: 0.2.0\n",
      publishing: true,
    }),
    /dated CLI changelog heading/,
  );
});

test("CLI tarball inventory includes the binary, skill, README, and no local state", () => {
  assert.doesNotThrow(() => validatePackageEntries([
    "package/package.json",
    "package/dist/cli.js",
    "package/skill/zenstory/SKILL.md",
    "package/README.md",
  ]));
  assert.throws(
    () => validatePackageEntries(["package/package.json", "package/dist/cli.js", "package/README.md"]),
    /missing package\/skill\/zenstory\/SKILL.md/,
  );
  assert.throws(
    () => validatePackageEntries([
      "package/package.json",
      "package/dist/cli.js",
      "package/skill/zenstory/SKILL.md",
      "package/README.md",
      "package/.env",
    ]),
    /forbidden npm package entry/,
  );
});

test("CLI proof selects the newest exact-SHA main push and requires summary plus CLI", () => {
  const sourceSha = "a".repeat(40);
  const requiredJobs = ["ci-summary", "cli-test"];
  const base = {
    repository: "zenstory-ai/zenstory",
    sourceSha,
    workflowId: 123,
    workflowPath: ".github/workflows/ci.yml",
    runs: [{
      id: 91,
      run_attempt: 2,
      head_sha: sourceSha,
      head_branch: "main",
      event: "push",
      status: "completed",
      conclusion: "success",
      workflow_id: 123,
      path: ".github/workflows/ci.yml",
      check_suite_id: 45,
      repository: { full_name: "zenstory-ai/zenstory" },
      head_repository: { full_name: "zenstory-ai/zenstory" },
    }],
    jobs: requiredJobs.map((name) => ({ name, status: "completed", conclusion: "success" })),
    checkSuite: {
      id: 45,
      head_sha: sourceSha,
      status: "completed",
      conclusion: "success",
      app: { id: 15368 },
    },
    requiredJobs,
  };
  assert.equal(selectCiProof(base).runAttempt, 2);
  assert.throws(() => selectCiProof({ ...base, jobs: base.jobs.slice(1) }), /missing required CI job/);
  assert.throws(
    () => selectCiProof({ ...base, checkSuite: { ...base.checkSuite, app: { id: 1 } } }),
    /unexpected check-suite app/,
  );
  assert.throws(
    () => selectCiProof({ ...base, checkSuite: { ...base.checkSuite, head_sha: "b".repeat(40) } }),
    /check-suite source SHA mismatch/,
  );
  assert.throws(
    () => selectCiProof({ ...base, runs: [{ ...base.runs[0], head_repository: { full_name: "fork/zenstory" } }] }),
    /head repository mismatch/,
  );
  assert.throws(
    () => selectCiProof({
      ...base,
      runs: [...base.runs, { ...base.runs[0], id: 92, run_attempt: 3, conclusion: "failure" }],
    }),
    /newest exact-SHA CI run did not succeed/,
  );
});

test("CLI manifest binds source and exact npm integrity", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "zenstory-cli-release-test-"));
  const tarball = path.join(directory, "zenstory-0.2.0.tgz");
  await writeFile(tarball, "package bytes");
  const manifest = await createReleaseManifest({ tarball, sourceSha: "b".repeat(40), version: "0.2.0" });
  assert.equal(manifest.package, "zenstory");
  assert.equal(manifest.tag, "cli-v0.2.0");
  assert.match(manifest.files[0].integrity, /^sha512-/);
  await verifyReleaseManifest({ manifest, directory, expectedSourceSha: "b".repeat(40) });
  await assert.rejects(
    verifyReleaseManifest({ manifest, directory, expectedSourceSha: "c".repeat(40) }),
    /source SHA mismatch/,
  );
});

test("registry absence is distinct from auth, throttling, network, and byte mismatch", () => {
  assert.equal(classifyHttpStatus(404), "missing");
  assert.equal(npmPublicationDecision({ status: 404, localIntegrity: "sha512-a" }), "publish");
  assert.equal(
    npmPublicationDecision({ status: 200, remoteIntegrity: "sha512-a", localIntegrity: "sha512-a" }),
    "skip-exact",
  );
  for (const status of [401, 403, 429, 500]) {
    assert.throws(
      () => npmPublicationDecision({ status, remoteIntegrity: null, localIntegrity: "sha512-a" }),
      /registry lookup failed/,
    );
  }
  assert.throws(
    () => npmPublicationDecision({ status: 200, remoteIntegrity: "sha512-b", localIntegrity: "sha512-a" }),
    /different bytes/,
  );
});

test("CLI release workflow is immutable, least-privilege, and fail-closed", async () => {
  const { readFile } = await import("node:fs/promises");
  const workflow = await readFile(".github/workflows/cli-release.yml", "utf8");
  for (const match of workflow.matchAll(/^\s*- uses:\s*([^\s#]+)/gm)) {
    assert.match(match[1], /@[a-f0-9]{40}$/i, `${match[1]} is not full-SHA pinned`);
  }
  assert.match(workflow, /tags: \["cli-v\*"\]/);
  assert.match(workflow, /CLI_NPM_PUBLISH_ENABLED/);
  assert.match(workflow, /github-release:[\s\S]*contents: write/);
  assert.match(workflow, /npm:[\s\S]*id-token: write/);
  assert.match(workflow, /artifact-ids: \$\{\{ needs\.verify\.outputs\.artifact-id \}\}/);
  assert.match(workflow, /manifest-sha256: \$\{\{ steps\.digests\.outputs\.manifest-sha256 \}\}/);
  assert.match(workflow, /EXPECTED_PROMOTION_PROOF_SHA256/);
  assert.match(workflow, /EXPECTED_CI_PROOF_SHA256/);
  assert.match(workflow, /npm-publish[\s\S]*--repository "\$GITHUB_REPOSITORY"[\s\S]*--tag "\$GITHUB_REF_NAME"/);
  assert.doesNotMatch(workflow, /--clobber|NPM_TOKEN|NODE_AUTH_TOKEN: \$\{\{ secrets/);
});

test("packed CLI installation uses a local tarball rather than GitHub shorthand", async () => {
  const { readFile } = await import("node:fs/promises");
  const workflow = await readFile(".github/workflows/cli-release.yml", "utf8");
  assert.match(workflow, /npm install[^\n]*--package-lock=false "\.\/\$tarball"/);
});


test("CI proof rejects a concurrent rerun or selected-run identity change", () => {
  const before = { id: 9, run_attempt: 1, head_sha: "a".repeat(40), check_suite_id: 10, status: "completed", conclusion: "success" };
  assert.doesNotThrow(() => validateRunStability(before, { ...before }));
  assert.throws(() => validateRunStability(before, { ...before, run_attempt: 2 }), /rerun during proof collection/);
  assert.throws(() => validateRunStability(before, { ...before, head_sha: "b".repeat(40) }), /source changed/);
  assert.throws(() => validateRunStability(before, { ...before, conclusion: "failure" }), /run changed/);
});

test("npm Trusted Publishing validates the actual CLI version at or above 11.5.1", () => {
  for (const version of ["11.5.1", "11.6.0", "12.0.0"]) assert.equal(validateNpmVersion(version), version);
  for (const version of ["10.9.0", "11.4.9", "11.5.0", "undefined", "11.5.1-rc.1"]) {
    assert.throws(() => validateNpmVersion(version), /Trusted Publishing/);
  }
});

test("the live publication gate validates CI/main then resolves the tag last", async () => {
  const order = [];
  const deps = {
    ciProof: async () => {order.push("ci");},
    compare: async () => {order.push("main"); return {status: "ahead"};},
    tagSha: async () => {order.push("tag"); return "b".repeat(40);},
  };
  await assert.rejects(verifyPublicationSource({repository: "zenstory-ai/zenstory", sourceSha: "a".repeat(40), tag: "cli-v0.2.0"}, deps), /tag moved/);
  assert.deepEqual(order, ["ci", "main", "tag"]);
  await assert.doesNotReject(verifyPublicationSource({repository: "zenstory-ai/zenstory", sourceSha: "a".repeat(40), tag: "cli-v0.2.0"}, {...deps, tagSha: async () => "a".repeat(40)}));
});

test("a prepared dated CLI version remains nonpublishing in PR and manual verification", () => {
  assert.equal(validateReleaseMetadata({packageVersion: "0.2.0", changelog: "## [Unreleased]\n\n## [0.2.0] - 2026-10-03\n"}).publishing, false);
  assert.throws(() => validateReleaseMetadata({packageVersion: "0.2.0", changelog: "## [Unreleased]\n\n## [0.1.0] - 2026-10-03\nCandidate: 0.2.0\n"}), /candidate|dated/);
});
