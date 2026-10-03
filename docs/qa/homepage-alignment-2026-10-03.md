# Homepage alignment — local acceptance, 2026-10-03

Scope: the bilingual static organization homepage, not the React writing app. The reference is Hypit's clarity and product/knowledge maturity, not its branding or pixels. Existing articles, guide URLs and workbench behavior are unchanged.

## What changed
- A real playable RPG appears in the hero; a writing workflow is the featured case, avoiding duplicate lead imagery.
- Five sourced cases cover four creative tools, including four README CDN videos. Posters are actual frames; videos use native controls, no autoplay and `preload="none"`.
- Four creative tools are visually separate from two working environments.
- Three action-based paths and four knowledge layers replace homepage directory dumping. Manuscript adaptation has two optional branches, not consecutive drama/game steps.
- Cases link to pinned owner READMEs and same-language methods. Invalid methods and missing/ambiguous homepage reading entries fail the generator rather than disappearing.

## Validation
- Homepage contracts include exact 5-case / 4-video / 4-owner assertions, negative data cases, and manuscript branch semantics.
- 46 full site-generator tests and 18 homepage contracts passed; ESLint, TypeScript, production build, CSS-token and i18n checks were run.
- Browser checks covered EN/ZH × actual light/dark media preferences × 390/640/960/1440px: no horizontal overflow or axe violations. Four videos played beyond one second with expected dimensions/durations; initial CDN video requests were zero.
- Final manuscript cards were captured separately in both languages at 390px and checked for one ordered import/continue step and two unordered adaptation branches.
- Independent code review approved the source contracts; independent visual review accepted presentation maturity and signed off the final manuscript branching repair.

Reproduce static checks from `apps/web`: `npm run test:site`, `npm run lint`, `npx tsc -b`, `npm run build:vercel`, `npm run lint:tokens`, `npm run lint:i18n-keys`. Browser evidence is retained in the execution artifacts, not shipped as website assets.

## Boundaries
This is local/PR acceptance, not proof of production deployment, search ranking or AI citation gains. SEO/GEO evidence is crawlable text, stable links, canonical/hreflang and truthful source-backed descriptions; no AI-specific schema or indexing guarantee is claimed. Only the recap has a verified caption track; the other demos do not establish full audiovisual accessibility. GitHub CDN lifetime and public-media rights remain external publication considerations; repository licenses alone do not establish rights to underlying footage.
