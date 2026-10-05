# Responsive review — 2026-10-05

## Scope and acceptance
All reachable React routes and representative dialog/detail states, plus every generated organization/docs template family in English/Chinese. Disabled inspirations routes are checked as redirects; no feature is re-enabled. Template coverage is not individual review of every article. Local deterministic fixtures are explicitly not production/admin credentials.

Target laptop viewports: 1280×720, 1366×768, 1440×900; shared responsive checks include 390×844, 768×1024 and ordinary desktop. Physical screen inches do not specify browser CSS pixels. Preserve necessary long-content/file/message/table scrolling, full text and reachable actions. No redesign, dependencies, or blanket hiding of overflowing content.

## Regression-first repair plan
1. Workbench/admin fixed shells must stretch within available viewport, not use `100vw` alongside the existing document scrollbar gutter. Keep the global public-page gutter.
2. Correct resizable-panel unit semantics and enforce usable minima. Installed v4 numeric units are pixels; initial defaults normalize to percentages, but an actual drag currently collapses the sidebar to 15px. Desktop defaults 20/48/32%, minimum sidebar180px/editor30%/chat300px. Tablet defaults25/40/35%, minimum20%/30%/280px. Preserve mobile mounted/inert panels and keyboard viewport logic.
3. Give empty desktop textarea64px and input-panel floor144px, shorten existing bilingual idea placeholder, preserve adjustable input/accessory/long-text scrolling and44px mobile controls.
4. Dashboard viewport-height shell with one main content scroller; preserve reachable bottom content. Repair flex min-width/min-height chains instead of cutting content.
5. Fix demonstrated tool-result label/title wrapping; use existing tokens and full, wrapping titles. Audit empty-editor expanded actions before any density changes.
6. Check every route and representative dialogs with loaded valid data; distinguish intentional local scroll from viewport clipping. Fix additional reproduced defects in their existing components.

## Baseline evidence
Operator artifacts: `.omx/artifacts/responsive-review-20261005/baseline-geometry.json` (15 cases, zero page errors), browser RED log `/tmp/zenstory-responsive-browser-red.log`, unit RED log `/tmp/zenstory-responsive-contract-red.log`.
- Workbench at1366px: fixed root starts11px, width1366px, ends1377px. `scrollWidth` alone misses the clipping because outer overflow is hidden.
- Empty input at1366: client36px/scroll56px (auto), client46px/scroll56px (saved120).
- Dashboard at1440×900: document/main height1118px rather than an independently scrolling viewport-height main.
- Actual drag to minimum: sidebar15px, proving unusable numeric minimum.
- Three new unit contracts fail (73 existing tests pass). All10 new browser contracts fail against unchanged product source.

## Coverage / final evidence
Pending implementation and complete route/template matrix. Do not interpret this plan as a pass report.

## Additional reproduced mobile defect
The six settings tabs overflowed a320px dialog: last tab ended479px while dialog ended355px; personal-details label wrapped into a96px-high row. Browser regression failed before repair. Mobile settings now use a3-column wrapping grid (desktop vertical navigation unchanged), preserving every tab and touch target without hiding labels or adding another horizontal scroller.

## Executed coverage
- React app: all22 route entries at1280×720,1366×768,1440×900,390×844,768×1024;148 loaded-route/representative-state screenshot/geometry records, zero page errors or document horizontal overflow. Includes public/auth/docs/pricing, onboarding, all dashboard modules, workbench, project statistics, material detail, settings profile/general/subscription/Agent/referral, material upload and skill create/my-skills. Inspirations redirects were verified with the product default-off build.
- `/forgot-password` is also disabled by default and correctly redirects to login. `/auth/callback` without credentials follows its existing login/error recovery path; this is not an OAuth success-flow test.
- Additional browser contracts cover every settings tab (including optional points), actual material chapter content, skill edit/resources and reachable Save on all5 sizes. These use an explicitly local Pro fixture to exercise unlocked materials, alongside the free billing state.
- Admin: all15 enabled route/editor variants at all5 sizes, populated long data, default-off inspirations redirect, representative forms/dialogs. Details and tablet card/table repairs: `admin-responsive-20261005.md`.
- Generated static sites:120 records =24 valid EN/ZH route/template representatives ×5 sizes. Includes home/project index/detail/practical guide/craft article/guides/topic pagination/comparison/glossary/docs. No document horizontal overflow or page errors; code/table/media local scroll remains intentional. Not an individual audit of every corpus article.

Operator evidence is under `.omx/artifacts/responsive-review-20261005/{app-final,admin,static}` in the original workspace, with additional before/after mobile-settings geometry and screenshots. These are local artifacts, not committed customer data. Automated all-route geometry is supplemented by representative screenshot inspection; it does not establish all browsers, every content string, or generated-writing quality.
- Material detail mobile header: a long title squeezed Search to50px, leaving essentially no readable text area after icon/padding. A new browser regression failed at50px versus required200px. The existing mobile header now stacks full-width search below the title; content-view back/search visibility semantics and desktop layout are unchanged.
