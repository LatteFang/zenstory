# Release, CI, and deployment contract

## Repository CI

`CI / ci-summary` remains the required repository check. It is deliberately
fail-closed:

- `detect-changes` must succeed and emit literal `true` or `false` values.
- A relevant job must succeed; it may not be skipped.
- An irrelevant job must be skipped rather than producing unrelated evidence.
- Main runs are not cancelled because provider-native gates need a terminal
  check suite for every pushed commit.

`E2E Tests` applies the same detector rules. Scheduled and manually dispatched
runs force E2E execution even when there is no meaningful Git diff. The GitHub
workflow is currently disabled and must not be reported as enabled until an
offline-reviewed revision is explicitly enabled and its bounded smoke run is
green. The local/mocked lane starts PostgreSQL, Redis, the backend, and the web
app; it uses test API keys and does not call a paid model provider.

## ZenStory CLI release

The website has no invented version. The existing public npm package is an
independent channel:

- package: `zenstory`
- version authority: `apps/cli/package.json`
- tag namespace: `cli-vX.Y.Z`
- release notes: `apps/cli/CHANGELOG.md`

The checked-in `0.2.0` is an **Unreleased candidate**, not a claim that it has
been published. The public registry currently labels `0.1.0` as `latest`; this
repository change does not alter that registry state. Before a future `cli-v0.2.0` tag, move its notes to an exact
dated `## [0.2.0] - YYYY-MM-DD` heading. PR/manual metadata validation
accepts that prepared dated version but remains nonpublishing; it does not require
a misleading duplicate Unreleased candidate marker.

`.github/workflows/cli-release.yml` has two paths:

1. A main-only manual dispatch packages, inventories, installs, and runs
   `zenstory --help` without an API key. It never publishes.
2. A future stable tag additionally requires exact-SHA successful main CI,
   packages once, promotes the artifact by ID and digest, and separates GitHub
   `contents: write` from npm `id-token: write`.

Publishing is currently `NOT_CONFIGURED` and fails closed unless
`CLI_NPM_PUBLISH_ENABLED` is exactly `true`. Set that repository variable only after the npm owner has verified the Trusted
Publisher binding for repository `zenstory-ai/zenstory` and workflow filename
`cli-release.yml`. Existing versions and GitHub assets are append-only: lookup
errors are not treated as absence, and different bytes are rejected.

## Hosted delivery

The authoritative producers remain the existing provider Git integrations:

| Surface | Producer | Required external gate | Repository evidence |
| --- | --- | --- | --- |
| Web (`zenstory.ai`, `app.zenstory.ai`) | Vercel Git integration | Vercel Deployment Checks selecting `ci-summary` for the deployment commit before production-domain promotion | exact CI proof plus post-promotion readiness receipt |
| API / Prefect | Railway Git integration | Railway **Wait for CI** for the canonical main branch | exact CI proof plus post-deployment `/health` and anonymous 401 readiness |

These provider settings require separate production approval and authenticated
readback. Until both are confirmed, report `PROVIDER_GATE_NOT_VERIFIED`; a
repository workflow does not make the external gate complete. Do not add a
second `vercel deploy` or Railway deploy path, and do not change routing,
authentication, CORS, project roots, domains, or production environment values
as part of this contract.

`zenstory Online Smoke` is a manual, read-only, source-bound receipt workflow.
It requires a 40-character deployed source SHA and the exact successful main CI
run ID, checks only the canonical public origins, uses no credentials, and
records `providerSourceBinding: NOT_VERIFIED` until provider deployment metadata
is read back independently. It is post-deployment observability, **not** a
pre-deployment or pre-promotion gate. The workflow is currently disabled and
therefore remains `NOT_ENABLED` until separately activated.

After provider approval, enable the workflow and run a bounded receipt for a
known deployed commit:

```sh
gh workflow run zenstory-online-smoke.yml --ref main \
  -f source_sha=<40-character-deployed-main-sha> \
  -f ci_run_id=<successful-ci-run-id> \
  -f frontend_origin=https://app.zenstory.ai
```

Do not substitute arbitrary URLs, credentials, a moving `main` reference, or a
"latest successful" run. Record the resulting run ID/attempt and retain the
downloaded receipt alongside the provider deployment IDs and source readback.
