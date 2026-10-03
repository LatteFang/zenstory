#!/usr/bin/env node
/* global Buffer, fetch, process, setTimeout */

import { createHash } from "node:crypto";
import { execFile, spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const stableTag = /^cli-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const shaPattern = /^[a-f0-9]{40}$/;
const githubActionsAppId = 15368;

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

export function validateNpmVersion(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  invariant(match, `npm ${version} lacks supported Trusted Publishing`);
  const [major, minor, patch] = match.slice(1).map(Number);
  invariant(major > 11 || (major === 11 && (minor > 5 || (minor === 5 && patch >= 1))),
    `npm ${version} lacks Trusted Publishing support; require >=11.5.1`);
  return version;
}

async function commandNpmVersion() {
  const { stdout } = await execFileAsync("npm", ["--version"]);
  process.stdout.write(`${validateNpmVersion(stdout.trim())}\n`);
}

export function validateReleaseMetadata({ tag, packageVersion, changelog, publishing = false }) {
  invariant(/^\d+\.\d+\.\d+$/.test(packageVersion), `invalid package version: ${packageVersion}`);
  const releasedVersions = [...changelog.matchAll(/^## \[([^\]]+)\] - \d{4}-\d{2}-\d{2}$/gm)]
    .map((match) => match[1]);
  if (!publishing) {
    invariant(!tag, "dry-run metadata validation must not receive a tag");
    invariant(/^## \[Unreleased\]$/m.test(changelog), "missing Unreleased CLI changelog heading");
    const unreleased = changelog.split(/^## \[Unreleased\]$/m)[1].split(/^## /m)[0];
    const candidates = [...unreleased.matchAll(/^Candidate: (\d+\.\d+\.\d+)$/gm)].map((match) => match[1]);
    invariant(
      candidates.includes(packageVersion) || releasedVersions.includes(packageVersion),
      `missing Unreleased candidate marker or dated heading for ${packageVersion}`,
    );
    return { version: packageVersion, tag: null, publishing: false };
  }
  const match = stableTag.exec(tag);
  invariant(match, `expected stable CLI release tag cli-vX.Y.Z, received ${tag}`);
  const version = tag.slice("cli-v".length);
  invariant(version === packageVersion, `tag/package version mismatch: ${version} != ${packageVersion}`);
  invariant(releasedVersions.includes(version), `missing dated CLI changelog heading for ${version}`);
  return { version, tag, publishing: true };
}

export function validatePackageEntries(entries) {
  const normalized = entries.map((entry) => entry.replace(/^\.\//, "").replace(/\/$/, ""));
  for (const required of [
    "package/package.json",
    "package/dist/cli.js",
    "package/skill/zenstory/SKILL.md",
    "package/README.md",
  ]) {
    invariant(normalized.includes(required), `npm package is missing ${required}`);
  }
  for (const entry of normalized) {
    invariant(!entry.includes(".."), `unsafe npm package entry: ${entry}`);
    invariant(!/(^|\/)(node_modules|coverage|\.env|\.git)(\/|$)/.test(entry), `forbidden npm package entry: ${entry}`);
  }
  return normalized;
}

export function classifyHttpStatus(status) {
  if (status === 404) return "missing";
  if (status >= 200 && status < 300) return "ok";
  return "error";
}

export function npmPublicationDecision({ status, remoteIntegrity, localIntegrity }) {
  const state = classifyHttpStatus(status);
  if (state === "missing") return "publish";
  invariant(state === "ok", `npm registry lookup failed with HTTP ${status}`);
  invariant(remoteIntegrity, "published npm metadata has no dist.integrity");
  invariant(
    remoteIntegrity === localIntegrity,
    `npm version already exists with different bytes: ${remoteIntegrity} != ${localIntegrity}`,
  );
  return "skip-exact";
}

function normalizeWorkflowPath(value) {
  return String(value ?? "").replace(/^\//, "");
}

export function validateRunStability(before, after) {
  invariant(Number(after?.id) === Number(before?.id), "CI run ID changed during proof collection");
  invariant(Number(after?.run_attempt) === Number(before?.run_attempt), "CI run was rerun during proof collection");
  invariant(after?.head_sha === before?.head_sha, "CI run source changed during proof collection");
  invariant(Number(after?.check_suite_id) === Number(before?.check_suite_id), "CI check suite changed during proof collection");
  invariant(after?.status === before?.status && after?.conclusion === before?.conclusion, "CI run changed during proof collection");
}

export function selectCiProof({
  repository = "zenstory-ai/zenstory",
  sourceSha,
  workflowId,
  workflowPath,
  runs,
  jobs,
  checkSuite,
  requiredJobs,
}) {
  const exactRuns = runs
    .filter(
      (run) =>
        run.head_sha === sourceSha &&
        run.head_branch === "main" &&
        run.event === "push" &&
        Number(run.workflow_id) === Number(workflowId) &&
        normalizeWorkflowPath(run.path) === normalizeWorkflowPath(workflowPath),
    )
    .sort((left, right) => Number(right.id) - Number(left.id));
  invariant(exactRuns.length > 0, `no exact-SHA main-push CI run found for ${sourceSha}`);
  const run = exactRuns[0];
  invariant(run.repository?.full_name === repository, `CI run repository mismatch: ${run.repository?.full_name ?? "missing"}`);
  invariant(run.head_repository?.full_name === repository, `CI run head repository mismatch: ${run.head_repository?.full_name ?? "missing"}`);
  invariant(
    run.status === "completed" && run.conclusion === "success",
    `newest exact-SHA CI run did not succeed: run ${run.id} is ${run.status}/${run.conclusion}`,
  );
  invariant(Number(checkSuite?.id) === Number(run.check_suite_id), "check-suite ID mismatch");
  invariant(checkSuite?.head_sha === sourceSha, "check-suite source SHA mismatch");
  invariant(
    checkSuite?.status === "completed" && checkSuite?.conclusion === "success",
    `check suite did not succeed: ${checkSuite?.status ?? "missing"}/${checkSuite?.conclusion ?? "missing"}`,
  );
  invariant(
    Number(checkSuite?.app?.id) === githubActionsAppId,
    `unexpected check-suite app: expected ${githubActionsAppId}, received ${checkSuite?.app?.id ?? "missing"}`,
  );
  for (const requiredName of requiredJobs) {
    const matches = jobs.filter((job) => job.name === requiredName);
    invariant(matches.length === 1, `missing required CI job or ambiguous name: ${requiredName}`);
    invariant(
      matches[0].status === "completed" && matches[0].conclusion === "success",
      `required CI job did not succeed: ${requiredName} is ${matches[0].status}/${matches[0].conclusion}`,
    );
  }
  return {
    schemaVersion: 1,
    repository,
    sourceSha,
    workflowId: Number(workflowId),
    workflowPath: normalizeWorkflowPath(workflowPath),
    runId: Number(run.id),
    runAttempt: Number(run.run_attempt),
    checkSuiteId: Number(run.check_suite_id),
    checkSuiteAppId: githubActionsAppId,
    requiredJobs,
  };
}

async function digestFile(file) {
  const bytes = await readFile(file);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const sha512 = createHash("sha512").update(bytes).digest("base64");
  return { size: bytes.length, sha256, integrity: `sha512-${sha512}` };
}

export async function createReleaseManifest({ tarball, sourceSha, version }) {
  invariant(shaPattern.test(sourceSha), `invalid source SHA: ${sourceSha}`);
  const file = await digestFile(tarball);
  return {
    schemaVersion: 1,
    package: "zenstory",
    version,
    tag: `cli-v${version}`,
    sourceSha,
    tools: {
      node: "20",
      packageManager: "pnpm@10.29.3",
    },
    files: [{ name: path.basename(tarball), ...file }],
  };
}

export async function verifyReleaseManifest({ manifest, directory, expectedSourceSha }) {
  invariant(manifest?.schemaVersion === 1, "unsupported release manifest schema");
  invariant(manifest.sourceSha === expectedSourceSha, "release manifest source SHA mismatch");
  invariant(manifest.tag === `cli-v${manifest.version}`, "release manifest tag/version mismatch");
  invariant(manifest.package === "zenstory", "release manifest package mismatch");
  invariant(Array.isArray(manifest.files) && manifest.files.length === 1, "release manifest must contain one tarball");
  const entry = manifest.files[0];
  invariant(entry.name === `zenstory-${manifest.version}.tgz`, `unexpected tarball name: ${entry.name}`);
  invariant(path.basename(entry.name) === entry.name, "manifest file name must not contain a path");
  const actual = await digestFile(path.join(directory, entry.name));
  invariant(actual.sha256 === entry.sha256, `SHA-256 mismatch for ${entry.name}`);
  invariant(actual.integrity === entry.integrity, `SHA-512 integrity mismatch for ${entry.name}`);
  invariant(actual.size === entry.size, `size mismatch for ${entry.name}`);
  return actual;
}

export function verifyPromotionProof({ proof, manifestSha256, sourceSha, runId, runAttempt, artifactName }) {
  invariant(proof?.schemaVersion === 1, "unsupported promotion proof schema");
  invariant(proof.sourceSha === sourceSha, "promotion proof source SHA mismatch");
  invariant(proof.manifestSha256 === manifestSha256, "promotion proof manifest digest mismatch");
  invariant(String(proof.runId) === String(runId), "promotion proof run ID mismatch");
  invariant(String(proof.runAttempt) === String(runAttempt), "promotion proof run attempt mismatch");
  invariant(proof.artifactName === artifactName, "promotion proof artifact name mismatch");
}

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const args = {};
  for (let index = 0; index < rest.length; index += 1) {
    const token = rest[index];
    invariant(token.startsWith("--"), `unexpected argument: ${token}`);
    const key = token.slice(2);
    const value = rest[index + 1];
    invariant(value && !value.startsWith("--"), `missing value for --${key}`);
    args[key] = value;
    index += 1;
  }
  return { command, args };
}

async function loadJson(file) {
  return JSON.parse(await readFile(file, "utf8"));
}

async function githubRequest(url, { token, method = "GET", body, accept = "application/vnd.github+json" } = {}) {
  const headers = {
    Accept: accept,
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "zenstory-cli-release",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (error) {
    throw new Error(`GitHub request failed before an HTTP response: ${error.message}`, { cause: error });
  }
  return response;
}

async function githubJson(url, options = {}) {
  const response = await githubRequest(url, options);
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { message: text.slice(0, 300) };
    }
  }
  if (!response.ok) {
    const error = new Error(`GitHub API ${options.method ?? "GET"} ${url} failed with HTTP ${response.status}: ${body?.message ?? "unknown error"}`);
    error.status = response.status;
    throw error;
  }
  return body;
}

async function collectPages(url, token) {
  const items = [];
  for (let page = 1; page <= 10; page += 1) {
    const separator = url.includes("?") ? "&" : "?";
    const body = await githubJson(`${url}${separator}per_page=100&page=${page}`, { token });
    const pageItems = body.workflow_runs ?? body.jobs ?? body;
    invariant(Array.isArray(pageItems), "unexpected paginated GitHub API response");
    items.push(...pageItems);
    if (pageItems.length < 100) break;
  }
  return items;
}

async function commandCheck(args) {
  const plugin = JSON.parse(await readFile("apps/cli/package.json", "utf8"));
  const changelog = await readFile("apps/cli/CHANGELOG.md", "utf8");
  const publishing = args.publishing === "true";
  const result = validateReleaseMetadata({
    tag: args.tag,
    packageVersion: plugin.version,
    changelog,
    publishing,
  });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

async function git(args) {
  const { stdout } = await execFileAsync("git", args, { encoding: "utf8" });
  return stdout.trim();
}

async function assertRepositoryPolicy(repository, token) {
  invariant(repository === "zenstory-ai/zenstory", `unexpected repository: ${repository}`);
  const base = `https://api.github.com/repos/${repository}`;
  const metadata = await githubJson(base, { token });
  invariant(metadata.full_name === repository && metadata.private === false, "release repository must be canonical and public");
  invariant(metadata.default_branch === "main", `expected default branch main, received ${metadata.default_branch}`);
  const branch = await githubJson(`${base}/branches/main`, { token });
  invariant(branch.protected === true, "main branch is not protected");
}

async function fetchLiveCiProof({ repository, sourceSha, token }) {
  await assertRepositoryPolicy(repository, token);
  const base = `https://api.github.com/repos/${repository}`;
  const workflow = await githubJson(`${base}/actions/workflows/ci.yml`, { token });
  invariant(Number.isInteger(Number(workflow.id)), "CI workflow has no numeric ID");
  invariant(normalizeWorkflowPath(workflow.path) === ".github/workflows/ci.yml", "CI workflow path mismatch");
  const runs = await collectPages(`${base}/actions/workflows/${workflow.id}/runs?branch=main&event=push&head_sha=${sourceSha}`, token);
  const candidates = runs
    .filter((run) => run.head_sha === sourceSha && run.head_branch === "main" && run.event === "push")
    .sort((left, right) => Number(right.id) - Number(left.id));
  invariant(candidates.length > 0, `no exact-SHA main-push CI run found for ${sourceSha}`);
  const selected = candidates[0];
  const freshBefore = await githubJson(`${base}/actions/runs/${selected.id}`, { token });
  invariant(Number(freshBefore.run_attempt) === Number(selected.run_attempt), "selected CI run changed before job inspection");
  const jobs = await collectPages(`${base}/actions/runs/${selected.id}/attempts/${freshBefore.run_attempt}/jobs`, token);
  const checkSuite = await githubJson(`${base}/check-suites/${freshBefore.check_suite_id}`, { token });
  const freshAfter = await githubJson(`${base}/actions/runs/${selected.id}`, { token });
  validateRunStability(freshBefore, freshAfter);
  return selectCiProof({
    repository,
    sourceSha,
    workflowId: workflow.id,
    workflowPath: workflow.path,
    runs: [freshAfter],
    jobs,
    checkSuite,
    requiredJobs: ["ci-summary", "cli-test"],
  });
}

export async function verifyPublicationSource({ repository, sourceSha, tag, token },
  { ciProof = fetchLiveCiProof, compare = githubJson, tagSha = resolveRemoteTag } = {}) {
  invariant(repository === "zenstory-ai/zenstory", "unexpected publication repository");
  await ciProof({ repository, sourceSha, token });
  const main = await compare(`https://api.github.com/repos/${repository}/compare/${sourceSha}...main`, { token });
  invariant(main.status === "identical" || main.status === "ahead", "publication source is not on main");
  const resolved = await tagSha(repository, tag, token);
  invariant(resolved === sourceSha, "remote CLI tag moved before publication");
  return resolved;
}

async function commandCiProof(args) {
  const token = process.env.GITHUB_TOKEN;
  invariant(token, "GITHUB_TOKEN is required for CI proof");
  const repository = args.repository;
  const sourceSha = args.sha;
  invariant(repository && sourceSha, "--repository and --sha are required");
  invariant(await git(["rev-parse", "HEAD"]) === sourceSha, "checked-out HEAD does not match requested source SHA");
  await execFileAsync("git", ["fetch", "--no-tags", "origin", "main"]);
  await execFileAsync("git", ["merge-base", "--is-ancestor", sourceSha, "origin/main"]);
  if (args.tag) {
    invariant((await git(["rev-parse", `${args.tag}^{commit}`])) === sourceSha, `tag ${args.tag} does not resolve to ${sourceSha}`);
  }
  const proof = await fetchLiveCiProof({ repository, sourceSha, token });
  if (args.output) await writeFile(args.output, `${JSON.stringify(proof, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify(proof)}\n`);
}

async function commandInspectPackage(args) {
  invariant(args.tarball, "--tarball is required");
  const { stdout } = await execFileAsync("tar", ["-tzf", args.tarball], { encoding: "utf8" });
  const entries = validatePackageEntries(stdout.split("\n").filter(Boolean));
  process.stdout.write(`${JSON.stringify({ verified: true, entries: entries.length })}\n`);
}

async function commandManifest(args) {
  const manifest = await createReleaseManifest({
    tarball: args.tarball,
    sourceSha: args.sha,
    version: args.version,
  });
  invariant(/^\d+$/.test(String(args["run-id"])), `invalid run ID: ${args["run-id"]}`);
  invariant(/^\d+$/.test(String(args["run-attempt"])), `invalid run attempt: ${args["run-attempt"]}`);
  invariant(Boolean(args["artifact-name"]), "artifact name is required");
  await mkdir(path.dirname(args.output), { recursive: true });
  await writeFile(args.output, `${JSON.stringify(manifest, null, 2)}\n`);
  const promotionProof = {
    schemaVersion: 1,
    sourceSha: manifest.sourceSha,
    manifestSha256: (await digestFile(args.output)).sha256,
    runId: Number(args["run-id"]),
    runAttempt: Number(args["run-attempt"]),
    artifactName: args["artifact-name"],
  };
  await writeFile(
    path.join(path.dirname(args.output), "PROMOTION-PROOF.json"),
    `${JSON.stringify(promotionProof, null, 2)}\n`,
  );
  await writeFile(
    path.join(path.dirname(args.output), "SHA256SUMS"),
    `${manifest.files[0].sha256}  ${manifest.files[0].name}\n`,
  );
  process.stdout.write(`${JSON.stringify(manifest)}\n`);
}

async function commandVerifyManifest(args) {
  const manifest = await loadJson(args.manifest);
  await verifyReleaseManifest({ manifest, directory: args.directory, expectedSourceSha: args.sha });
  const promotionProof = await loadJson(args["promotion-proof"]);
  verifyPromotionProof({
    proof: promotionProof,
    manifestSha256: (await digestFile(args.manifest)).sha256,
    sourceSha: manifest.sourceSha,
    runId: args["run-id"],
    runAttempt: args["run-attempt"],
    artifactName: args["artifact-name"],
  });
  const checksum = await readFile(path.join(args.directory, "SHA256SUMS"), "utf8");
  invariant(
    checksum === `${manifest.files[0].sha256}  ${manifest.files[0].name}\n`,
    "SHA256SUMS does not match the release manifest",
  );
  if (args["ci-proof"]) {
    const proof = await loadJson(args["ci-proof"]);
    invariant(proof.schemaVersion === 1, "unsupported CI proof schema");
    invariant(proof.repository === "zenstory-ai/zenstory", "CI proof repository mismatch");
    invariant(proof.sourceSha === manifest.sourceSha, "CI proof source SHA mismatch");
    invariant(proof.workflowPath === ".github/workflows/ci.yml", "CI proof workflow path mismatch");
    invariant(proof.checkSuiteAppId === githubActionsAppId, "CI proof application mismatch");
    invariant(
      JSON.stringify(proof.requiredJobs) === JSON.stringify(["ci-summary", "cli-test"]),
      "CI proof required-job set mismatch",
    );
  }
  process.stdout.write(`${JSON.stringify({ verified: true, sourceSha: manifest.sourceSha })}\n`);
}

async function resolveRemoteTag(repository, tag, token) {
  let object = await githubJson(`https://api.github.com/repos/${repository}/git/ref/tags/${encodeURIComponent(tag)}`, { token });
  object = object.object;
  for (let depth = 0; object.type === "tag" && depth < 5; depth += 1) {
    object = (await githubJson(`https://api.github.com/repos/${repository}/git/tags/${object.sha}`, { token })).object;
  }
  invariant(object.type === "commit", `tag ${tag} did not resolve to a commit`);
  return object.sha;
}

async function readResponseBytes(response, context) {
  if (!response.ok) throw new Error(`${context} failed with HTTP ${response.status}`);
  return Buffer.from(await response.arrayBuffer());
}

function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function findRelease(repository, tag, token) {
  const response = await githubRequest(`https://api.github.com/repos/${repository}/releases/tags/${encodeURIComponent(tag)}`, { token });
  if (response.status === 404) return null;
  const text = await response.text();
  if (!response.ok) throw new Error(`GitHub release lookup failed with HTTP ${response.status}: ${text.slice(0, 300)}`);
  return JSON.parse(text);
}

async function uploadReleaseAsset(repository, release, token, file, name) {
  const bytes = await readFile(file);
  const response = await fetch(`https://uploads.github.com/repos/${repository}/releases/${release.id}/assets?name=${encodeURIComponent(name)}`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/octet-stream",
      "User-Agent": "zenstory-cli-release",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: bytes,
  });
  if (!response.ok) throw new Error(`GitHub release asset upload failed with HTTP ${response.status}: ${(await response.text()).slice(0, 300)}`);
}

async function ensureReleaseAsset(repository, release, token, file, expectedSha256) {
  const name = path.basename(file);
  const existing = release.assets.find((asset) => asset.name === name);
  if (!existing) {
    await uploadReleaseAsset(repository, release, token, file, name);
    return "uploaded";
  }
  const response = await githubRequest(existing.url, { token, accept: "application/octet-stream" });
  const bytes = await readResponseBytes(response, `GitHub asset download for ${name}`);
  invariant(sha256Bytes(bytes) === expectedSha256, `GitHub release asset ${name} already exists with different bytes`);
  return "skip-exact";
}

async function commandGithubPublish(args) {
  const token = process.env.GITHUB_TOKEN;
  invariant(token, "GITHUB_TOKEN is required for GitHub publication");
  const manifest = await loadJson(args.manifest);
  await verifyReleaseManifest({ manifest, directory: args.directory, expectedSourceSha: args.sha });
  invariant(manifest.tag === args.tag, "manifest tag mismatch");
  let release = await findRelease(args.repository, args.tag, token);
  const remoteTagSha = await verifyPublicationSource({ repository: args.repository, sourceSha: manifest.sourceSha, tag: args.tag, token });
  if (!release) {
    release = await githubJson(`https://api.github.com/repos/${args.repository}/releases`, {
      token,
      method: "POST",
      body: {
        tag_name: args.tag,
        target_commitish: manifest.sourceSha,
        name: `ZenStory CLI ${args.tag}`,
        generate_release_notes: true,
        draft: false,
        prerelease: false,
      },
    });
  } else {
    invariant(!release.draft && !release.prerelease, "existing GitHub release is draft or prerelease");
  }
  const tarball = manifest.files[0];
  const manifestBytes = await readFile(args.manifest);
  const checksumFile = path.join(args.directory, "SHA256SUMS");
  const results = {};
  results[tarball.name] = await ensureReleaseAsset(
    args.repository,
    release,
    token,
    path.join(args.directory, tarball.name),
    tarball.sha256,
  );
  results[path.basename(args.manifest)] = await ensureReleaseAsset(
    args.repository,
    release,
    token,
    args.manifest,
    sha256Bytes(manifestBytes),
  );
  results.SHA256SUMS = await ensureReleaseAsset(
    args.repository,
    release,
    token,
    checksumFile,
    (await digestFile(checksumFile)).sha256,
  );
  process.stdout.write(`${JSON.stringify({ releaseId: release.id, sourceSha: remoteTagSha, assets: results })}\n`);
}

async function registryMetadata(packageName, version) {
  const url = `https://registry.npmjs.org/${encodeURIComponent(packageName)}/${encodeURIComponent(version)}`;
  let response;
  try {
    response = await fetch(url, { headers: { Accept: "application/json", "User-Agent": "zenstory-cli-release" } });
  } catch (error) {
    throw new Error(`npm registry lookup failed before an HTTP response: ${error.message}`, { cause: error });
  }
  if (response.status === 404) return { status: 404, metadata: null };
  const text = await response.text();
  if (!response.ok) throw new Error(`npm registry lookup failed with HTTP ${response.status}: ${text.slice(0, 300)}`);
  return { status: response.status, metadata: JSON.parse(text) };
}

async function run(command, args, options = {}) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit", ...options });
    child.on("error", reject);
    child.on("exit", (code, signal) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with ${code ?? signal}`));
    });
  });
}

async function commandNpmPublish(args) {
  const token = process.env.GITHUB_TOKEN;
  invariant(token, "GITHUB_TOKEN is required for live npm publication checks");
  const manifest = await loadJson(args.manifest);
  await verifyReleaseManifest({ manifest, directory: args.directory, expectedSourceSha: args.sha });
  invariant(args.repository === "zenstory-ai/zenstory", `unexpected repository: ${args.repository}`);
  invariant(args.tag === manifest.tag, "npm publication tag does not match the manifest");
  const { status, metadata } = await registryMetadata(manifest.package, manifest.version);
  const decision = npmPublicationDecision({
    status,
    remoteIntegrity: metadata?.dist?.integrity,
    localIntegrity: manifest.files[0].integrity,
  });
  await verifyPublicationSource({ repository: args.repository, sourceSha: manifest.sourceSha, tag: args.tag, token });
  if (decision === "publish") {
    await run("npm", ["publish", path.join(args.directory, manifest.files[0].name), "--access", "public", "--provenance", "--ignore-scripts"]);
  }
  process.stdout.write(`${JSON.stringify({ package: manifest.package, version: manifest.version, decision })}\n`);
}

async function retry(label, operation, { attempts = 12, delayMs = 10_000 } = {}) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw new Error(`${label} failed after ${attempts} attempts: ${lastError.message}`);
}

async function commandVerifyPublic(args) {
  const manifest = await loadJson(args.manifest);
  await verifyReleaseManifest({ manifest, directory: args.directory, expectedSourceSha: args.sha });
  const tarball = manifest.files[0];
  for (const [name, expectedSha256] of [
    [tarball.name, tarball.sha256],
    [path.basename(args.manifest), (await digestFile(args.manifest)).sha256],
    ["SHA256SUMS", (await digestFile(path.join(args.directory, "SHA256SUMS"))).sha256],
  ]) {
    const releaseUrl = `https://github.com/${args.repository}/releases/download/${encodeURIComponent(manifest.tag)}/${encodeURIComponent(name)}`;
    const releaseBytes = await retry(`anonymous GitHub release verification for ${name}`, async () => {
      const response = await fetch(releaseUrl, { redirect: "follow" });
      return readResponseBytes(response, `anonymous GitHub release download for ${name}`);
    });
    invariant(sha256Bytes(releaseBytes) === expectedSha256, `anonymous GitHub release bytes differ for ${name}`);
  }

  const metadata = await retry("npm registry propagation", async () => {
    const result = await registryMetadata(manifest.package, manifest.version);
    npmPublicationDecision({
      status: result.status,
      remoteIntegrity: result.metadata?.dist?.integrity,
      localIntegrity: tarball.integrity,
    });
    return result.metadata;
  });
  invariant(metadata.dist.integrity === tarball.integrity, "npm integrity differs from the manifest");

  const temp = await mkdtemp(path.join(os.tmpdir(), "zenstory-cli-public-"));
  const npmConfig = path.join(temp, "anonymous.npmrc");
  await writeFile(npmConfig, "registry=https://registry.npmjs.org/\nalways-auth=false\n");
  await writeFile(path.join(temp, "package.json"), '{"private":true}\n');
  await run(
    "npm",
    ["install", "--ignore-scripts", "--legacy-peer-deps", "--no-audit", "--no-fund", "--package-lock=false", `${manifest.package}@${manifest.version}`],
    { cwd: temp, env: { ...process.env, NODE_AUTH_TOKEN: "", NPM_CONFIG_USERCONFIG: npmConfig } },
  );
  const installed = JSON.parse(await readFile(path.join(temp, "node_modules", "zenstory", "package.json"), "utf8"));
  invariant(installed.version === manifest.version, `anonymous install resolved ${installed.version}`);
  await run(path.join(temp, "node_modules", ".bin", "zenstory"), ["--help"], {
    cwd: temp,
    env: { ...process.env, NODE_AUTH_TOKEN: "", NPM_CONFIG_USERCONFIG: npmConfig },
  });
  process.stdout.write(`${JSON.stringify({ github: "SUCCESS", npm: "SUCCESS", version: manifest.version })}\n`);
}

async function main() {
  const { command, args } = parseArgs(process.argv.slice(2));
  const commands = {
    check: commandCheck,
    "ci-proof": commandCiProof,
    "inspect-package": commandInspectPackage,
    manifest: commandManifest,
    "verify-manifest": commandVerifyManifest,
    "github-publish": commandGithubPublish,
    "npm-publish": commandNpmPublish,
    "npm-version": commandNpmVersion,
    "verify-public": commandVerifyPublic,
  };
  invariant(commands[command], `unknown release command: ${command ?? "missing"}`);
  await commands[command](args);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error) => {
    process.stderr.write(`release: ${error.message}\n`);
    process.exitCode = 1;
  });
}
