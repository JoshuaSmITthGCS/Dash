# THEMES.md — the medium manifest system

How the twelve-medium rebuild's shared architecture works, and the checklist for adding a
thirteenth medium. Companion to `DESIGN.md` (what each medium looks like) and
`CAPABILITY-LEDGER.md` (what every medium must render). Governed by
`valuesignal-rebuild-MASTER-rev11.md`.

## Why "medium" and not "theme"

The twelve presentations are called **mediums** in code — `data-medium` attribute,
`src/mediums/` directory, `medium` preference key — because "theme" is already taken twice in
this codebase: `data-theme` (light/dark) and thematic equity screens (`theme_exposure`,
`screens/themes`, `pipeline/themes/*.yaml`). User-facing copy still says "theme."

## File layout

```
src/mediums/
  registry.js                 # static meta for all 12 + import.meta.glob lazy loader
  core/
    states.js                 # canonical four-state + confidence model
    seed.js                   # deterministic PRNG for all material randomness
    chartContract.js          # the 14-type renderer interface
    capability.js              # cap(id) + dev-mode ledger-id warning
    headline.js                # Newspaper's headline generator (shared, unit-tested)
    vocab.js                   # furniture-word lookup
    MediumContext.jsx          # React context carrying the loaded manifest
    WallLabel.jsx               # the schema-driven label component every medium renders through
    entry.js                    # entry-page skip/persist/deep-link-bypass logic
    MediumShell.jsx              # mounts at /v2/*, loads the manifest, decides entry vs. shell
    screens/                     # the six destination screens — medium-agnostic composition
      HomeScreen.jsx ResearchScreen.jsx ScreensScreen.jsx PortfolioScreen.jsx
      MarketsScreen.jsx EvidenceScreen.jsx capabilityIds.js
  <medium-id>/                  # one directory per medium, e.g. gallery/, neon/, classic/
    manifest.js                  # the only file registry.js's glob ever imports
    tokens.css                   # :root[data-medium="<id>"] { --ink-primary: …; }
    renderer/index.js             # implements every key in chartContract's CHART_TYPES
    components/                    # Container, SectionHeading, Control, Tabs, LabelFrame,
                                    # EmptyState, Skeleton, ProvenanceStrip
    nav/  entry/  fonts/  textures/
src/routes/redirects.js         # the ROUTE-INVENTORY.md §2 redirect table, as data
```

## The manifest shape

```js
/** @typedef {Object} MediumManifest
 *  @property {string} id
 *  @property {'light'|'dark'} colorScheme
 *  @property {string} themeColor
 *  @property {() => Promise} loadTokens          // side-effect CSS chunk import
 *  @property {() => Promise<Renderer>} loadRenderer  // see core/chartContract.js
 *  @property {Object} components   // { Container, SectionHeading, Control, Tabs,
 *                                  //   LabelFrame, EmptyState, Skeleton, ProvenanceStrip }
 *  @property {Object} nav          // { model, Component, settingsAffordance: true }
 *  @property {null|Object} entry   // null, or { Component }
 *  @property {Object} motion       // { profile, calmSetting }
 *  @property {'compact'|'regular'|'spacious'} density
 *  @property {Object.<string,string>} vocabulary  // furniture words only
 *  @property {Object} type         // { mono, display, floorPx }
 *  @property {boolean} acceptsAccent  // true ONLY for classic
 *  @property {Object} budgets      // { textureBytes }
 */
```

`src/mediums/core/screens/*` compose **exclusively** from `manifest.components` + `WallLabel` +
the loaded renderer + shared data hooks (`useData`, formatters, `signalMetrics.js`, the
Planning worker) — never from `src/pages/*` or page-level `src/components/*` (the one exception:
`classic/manifest.js`, the only manifest permitted to import existing components, built last in
Phase 2c).

## Checklist for adding medium #13 (or building one of the existing twelve in Phase 2b)

1. Add one row to `MEDIUM_META` in `src/mediums/registry.js` (id, colorScheme, themeColor,
   acceptsAccent: false, hasEntry, shipAtLaunch).
2. Add the same `[colorScheme, themeColor]` pair to the `MEDIUM_PAINT` table inlined in
   `index.html`'s pre-paint script — the two tables must never drift.
3. Create `src/mediums/<id>/manifest.js` exporting the shape above as its default export.
   `registry.js`'s `import.meta.glob('./*/manifest.js')` picks it up automatically — no other
   registry change needed.
4. Implement `components.LabelFrame` first — `WallLabel` renders through it, and every screen's
   metric rows depend on it existing before anything else is visible.
5. Implement `renderer/index.js` against every key in `chartContract.js`'s `CHART_TYPES`; run
   `validateRenderer(renderer)` (same file) in the medium's own smoke test.
6. Implement `nav.Component` (and `entry.Component` if `hasEntry`). Every nav model must expose
   a settings affordance reachable in one tap (the nav-contract rule DESIGN.md's per-theme
   sections rely on).
7. All material randomness — rough.js seeds, registration offsets, dither phase, bristle
   displacement — must go through `core/seed.js`'s `seedFor(id)`. `Math.random()` is banned
   under `src/mediums/**`.
8. Write the medium's own test: mount each of the six core screens with the real manifest (no
   fake `LabelFrame`) and confirm `validateRenderer` passes, `data-capability-id` is present on
   every rendered ledger row this medium currently implements, and `npm run lint && npm test &&
   npm run build` are clean.
9. Update `DESIGN.md`'s corresponding section only if implementation surfaced something the
   design didn't anticipate — log the deviation in `NOTES.md`, don't silently redesign.
10. Commit as its own unit (one medium = one commit, per the execution plan's cadence).

## What Phase 2 shipped vs. what's still open

All twelve medium manifests are built (`registry.isMediumImplemented(id)` is `true` for every
id) — Cockpit, Neon, Poster, Ticker, Gallery, Chalkboard, Beige Box, Newspaper, Book, Blueprint,
Star Chart, then Classic last (Phase 2c, the only manifest permitted to import existing
components).

The six core screens still render a **real, working, but intentionally partial** slice of their
destination — enough to prove the data plumbing and capability-id pattern are correct, not yet
every row in `CAPABILITY-LEDGER.md`. See `NOTES.md` for the exact scope of what's wired today
(Home's three-item first viewport is complete; Research/Screens/Portfolio/Markets/Evidence each
render a representative structural slice) and `PARITY-REPORT.md` for the current ledger-coverage
count. Extending each screen to full ledger-row coverage is the largest remaining body of work
before cutover.

## Phase 3 — the Playwright harness

`playwright.config.mjs` defines the sixteen-assertion harness (`tests/e2e/*.spec.mjs`) the plan
requires green before cutover. Two things to know before touching it:

- **The harness needs a Firebase-safe build.** `src/lib/firebase.js` calls `getAuth()` as a
  module-load side effect, which throws in any checkout without real credentials. `npm run
  build:e2e` (`vite build --mode e2e`) picks up `.env.e2e`'s committed placeholder config so the
  built bundle actually renders; `npm run build` (real production) still requires real secrets
  and is untouched by this.
- **`/e2e-harness/:mediumId`** (`src/mediums/core/E2EHarness.jsx`, gated on `import.meta.env.MODE
  === 'e2e'`, absent from the real production bundle) mounts one medium's actual `WallLabel`/
  `LabelFrame`/renderer against fixed fixtures, bypassing the app's Firebase-dependent chrome.
  Most of the harness's non-visual specs (renderer/rules/motion/a11y) run against this route
  rather than `/v2` directly, since the six core screens don't yet call
  `manifest.loadRenderer()`/`WallLabel` from live traffic for most capabilities.

### Running it

```bash
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chromium   # only if the default resolution fails
npm run build:e2e
npx vite preview --port 5175 --strictPort &
npx playwright test                                        # everything, or:
npx playwright test parity.spec.mjs --project=default       # one spec, non-visual project
npm run e2e:update-baselines                                # regenerate visual.spec.mjs's baselines locally
```

### Regenerating baselines in the pinned container (authoritative for CI)

Local Chromium and CI's pinned `mcr.microsoft.com/playwright:v1.62.1-noble` image can render
subtly different pixels (fonts, GPU rasterization) even at the same browser version — baselines
committed from a local run are a good-enough starting point, but the pinned container is the
source of truth `.github/workflows/e2e.yml` actually checks against. Regenerate there via:

```bash
docker run --rm -v "$PWD":/work -w /work mcr.microsoft.com/playwright:v1.62.1-noble \
  bash -c "npm ci && npx playwright test visual.spec.mjs --update-snapshots"
```

Or trigger `.github/workflows/update-baselines.yml` (`workflow_dispatch`, manual-only) to do the
same in CI and commit the result automatically. Bump the pinned tag and the `@playwright/test`
devDependency version together — a version-mismatched container is the #1 cause of baseline
churn nobody can explain from the diff alone.
