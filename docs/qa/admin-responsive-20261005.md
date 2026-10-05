# Admin responsive browser audit — 2026-10-05

## Scope and method

- Browser: Playwright Chromium against local Vite only, with authenticated admin and populated API responses intercepted in-browser. No production authentication, payments, model calls, or backend data were used.
- Viewports: `1280x720`, `1366x768`, `1440x900`, `390x844`, and `768x1024`.
- Enabled routes: `/admin`, `/admin/users`, `/admin/prompts`, `/admin/prompts/new`, `/admin/prompts/novel`, `/admin/skills`, `/admin/codes`, `/admin/subscriptions`, `/admin/plans`, `/admin/audit-logs`, `/admin/feedback`, `/admin/points`, `/admin/check-in`, `/admin/referrals`, and `/admin/quota`.
- Product-default disabled route: `/admin/inspirations` was verified to redirect to `/admin`. The regression also accepts the explicitly enabled build and then requires its populated fixture content.
- The audit waited for a route-specific populated fixture value (or populated editor value) before measuring and capturing each page. It rejected page error events, error-fallback copy, and document-level horizontal overflow. Dense tables may retain intentional local horizontal scrolling.
- Representative mobile forms/dialogs were opened on users, codes, plans, and audit logs; their dialog bounds stayed inside the viewport and final actions remained reachable by scrolling.

## Demonstrated defects and fixes

1. At `768x1024`, the persistent admin sidebar leaves about 500px for page content, but several pages switched to their desktop layout at Tailwind's `md` breakpoint.
   - Users, codes, subscriptions, and audit logs showed crushed table cells, including words wrapping nearly character-by-character.
   - Fix: keep their existing compact card layouts through `1023px` and switch to tables at `lg`.
2. Dashboard, points, check-in, and quota metric grids switched to four columns in that same narrow content area.
   - Cards were about 99px wide; labels became vertical and large values visibly overlapped or clipped.
   - Fix: defer four-column grids to `lg`, retaining two readable columns at tablet width.
3. Feedback used the full desktop table at tablet width, placing key columns/actions beyond the initial view.
   - Fix: use the existing compact feedback cards through `1023px`; retain a deliberate 900px local table width on desktop.
4. Points, check-in, and referral tables had local overflow containers but no content floor, allowing dense columns to collapse instead of scroll.
   - Fix: add page-specific table minimum widths inside the existing local overflow containers.

## Results

- All 15 enabled routes loaded populated content at all five viewports: **75 populated route/viewport checks**.
- Document overflow: **0 failures** after the shared `AdminLayout` shell correction and page-specific fixes.
- Browser `pageerror` events: **0**.
- Error fallback surfaces: **0**.
- Tablet compact-layout regression: users, codes, subscriptions, audit logs, and feedback use compact cards; key metric cards remain wider than 150px.
- Intentional local scrolling remains on dense points, check-in, referral, feedback, and dashboard analytics tables.
- Screenshots: `.omx/artifacts/responsive-review-20261005/admin/` in the original repository root (75 full-page PNGs).
- Final Playwright output: `/tmp/zenstory-admin-responsive-final-20261005.log` (`8 passed`).

## Verification commands

```sh
# Browser audit (run from apps/web; verified worktree Vite was on 127.0.0.1:5195)
PATH=/Users/pite/.npm/_npx/ebaba8b9e55fd0a9/node_modules/node/bin:$PATH \
E2E_BASE_URL=http://127.0.0.1:5195 E2E_REUSE_EXISTING_SERVER=true \
PLAYWRIGHT_EXTERNAL_BACKEND=1 \
ADMIN_RESPONSIVE_ARTIFACT_DIR=/Users/pite/makemoney/zenstory/.omx/artifacts/responsive-review-20261005/admin \
./node_modules/.bin/playwright test e2e/admin-responsive-mocked.spec.ts \
  --project=chromium --workers=1 --reporter=line --no-deps

# Admin component regressions
PATH=/Users/pite/.npm/_npx/ebaba8b9e55fd0a9/node_modules/node/bin:$PATH \
./node_modules/.bin/vitest run src/pages/admin/__tests__

# Static checks
./node_modules/.bin/tsc -b --pretty false
./node_modules/.bin/eslint <changed admin files and responsive spec>
```

## Shared-shell observation

The initial browser baseline exposed document-level overflow caused by the shared `AdminLayout` sizing contract (`w-screen` plus constrained flex children). That file was outside this audit lane and was corrected by the root owner before the final measurements above.
