# NOTES.md

Append-only log of every judgment call made during the twelve-medium interface rebuild. One
entry per decision, newest at the bottom of its phase section. Math/scoring/pipeline concerns
that came up during UI work also land here (the rebuild never touches `pipeline/` or
`public/data/` directly).

---

## Phase 0 — Inventory & consolidation

**Naming: "medium" not "theme".** The twelve presentations are called **mediums** in code
(`data-medium` attribute, `src/mediums/` directory, `medium` preference key) because "theme" is
already taken twice in this codebase: the existing light/dark `data-theme` attribute, and the
thematic equity screens (`theme_exposure`, `screens/themes`, `pipeline/themes/*.yaml`). User-
facing copy may still say "theme" — this is an internal naming decision only, satisfying the
master's `data-theme` instruction in spirit.

**`/hud-demo` — leave exactly as-is, unlinked, DEV-only.** It renders on fully randomized state
(`setInterval(Math.random())` every 3s) with no `useData` call. The master permits leaving it
untouched rather than binding it to real data and promoting it; binding+promoting is scope
explosion outside a presentation-layer rebuild. Not in `CAPABILITY-LEDGER.md` as a real
capability — listed with disposition `n/a` and a pointer here.

**`CommandCenter.jsx` — orphaned, not a route.** Fully unrouted, unimported anywhere in `src/`
(grep confirms only its own definition). It's a near-verbatim fork of Dashboard's data pipeline
rendered through `hudUltra.jsx` primitives, but its two interactive controls (`period`,
`sinceLiveTrackingOnly`) are frozen `useState` values with no setters — dead code. Listed with
disposition `n/a`. Left on disk untouched (no deletion step exists in this project); a future,
separate cleanup PR can remove it if the user asks.

**Light theme is actually dark (existing bug, grandfathered).** `src/styles/variables.css`
defines `:root`, `:root[data-theme="dark"]`, and the `prefers-color-scheme: dark` block as three
verbatim copies of the same dark HUD palette — there is no `[data-theme="light"]` block anywhere
in the CSS. Choosing "Light" in Settings sets the attribute and injects a light accent inline,
but still renders dark. This predates the rebuild and is being ported into the Classic medium
as-is in Phase 2c (Classic is explicitly grandfathered for pre-existing violations per the
master's banned-list note); it is not something Phase 2a is asked to fix, and doing so would
count as "reopening existing components" before Phase 2c, which 0f forbids.

**24 live signal_metrics.json IDs are not yet in `docs/METRIC_INVENTORY.md`.** The doc's
Signal-metrics registry table (rows 204–244) lists 40 of the 64 currently-live metric IDs; the
other 24 (mostly newer group D/G/H additions — `ic_bootstrap_ci`, `rolling_ic_regime`,
`rolling_beta_swing`, `sector_classification_coverage/allocation_effect/selection_effect`,
`rate_beta`, `order_rejection_rate`, `realized_vs_expected_slippage`, `bootstrap_ci`,
`reality_check_spa`, `rolling_sharpe_60d`, `var_backtest_95/99`, `treynor_ratio`,
`jensens_alpha`, `after_tax_return`, and 6 `stress_test_*`/`scenario_*` rows) postdate the doc.
`CAPABILITY-LEDGER.md` §15 includes all 64 (154 total metric rows = 130 doc-baseline + 24
live-only), each newer row flagged `live-registry metric, not yet in docs/METRIC_INVENTORY.md`.
This is a pipeline/doc-maintenance gap, not a UI capability-loss risk — flagging for the user
rather than silently fixing, since `docs/METRIC_INVENTORY.md` is pipeline-adjacent documentation
outside this rebuild's scope.

**`scripts/check-metric-preservation.mjs` fails on the base branch, pre-existing.** Running it
before any Phase 0 edits (`git stash` showed no local changes to the three files it reads) still
reports `money_weighted_xirr` unreachable. This is not something Phase 0 introduced — flagging
for the user; the fix (if wanted) is either updating the doc's `renderSites` cell or confirming
`PortfolioReturnSummary.jsx:14-18` still renders it. `CAPABILITY-LEDGER.md`'s
`metric.report.money-weighted-xirr` row carries the same `renderSites` value as the doc, so the
ledger inherits — but does not cause — this pre-existing drift.

**`disclosure.global.no-signal-promoted` — closes a real gap.** Today, "no signal has been
promoted" / "classification B" / "0 of 24 IC periods" exists **only in `docs/`** — no UI
component states it anywhere in the current build (confirmed by exploration: `ShadowPortfolios`,
`LiveValidation`, and `ResearchEvidence` all render *adjacent* facts — promotion gates, IC
overviews, a promoted-count chip — but none renders the classification-B sentence itself). The
data capability already exists (`research_evidence.json.headline`), so this ledger row is
`kept`, not `moved`, but it gains a **new chrome-level surface** (every medium's ProvenanceStrip)
in the rebuild. This is not scope creep: the master's protected-disclosures list requires
"model classification, promotion state, and the 'no signal has been promoted' disclosure" at
equal-or-greater prominence in every medium, and prominence-equal-to-docs-only is not achievable
in a UI, so surfacing it is required by the master, not optional.

**Alerts' `?search=q` param — currently produced, never consumed.** `Alerts.jsx:30` links to
`/search?q={ticker}` but `Search.jsx` never reads the param. Folded into the Research
consolidation as a fix, not a new feature: `?q=<term>` on `/research` is read on mount in the
rebuild. Noted as a bug fix in `CAPABILITY-LEDGER.md` §17.

**Three known a11y gaps carried forward, flagged for fix during Phase 2 build (not Phase 0):**
Search result rows are `div role="button" tabIndex={0}` with manual Enter/Space handling instead
of real `<button>`s; Watchlist's add-ticker input handles Enter manually instead of being a real
`<form>`; Finances/Holdings-view tab-like button groups have no `role="tab"` or roving tabindex.
All three are `kept` capabilities in the ledger (§18) with the gap noted — Phase 2's shared
`core/screens/*` components should fix these structurally since every medium composes from the
same primitives, rather than fixing them twelve times.

**AnimatedNumber ignores `prefers-reduced-motion`.** Flagged in the pre-existing motion audit
(`plans/003-animated-number-reduced-motion.md`). Fix in passing during Phase 2a (shared layer),
since every medium's KPI figures reuse the same number-formatting primitive.

**ScoreGauge has a hardcoded `id="gauge-gradient"`.** Duplicate-ID hazard if more than one gauge
mounts on a page. Fix in passing during Phase 2a when the dial chart-contract type is built
(seed/instance-scoped gradient ids).

**Reference images — all ten catalogued and imported.** Copied into `design-refs/` (5: the
master's own named chalkboard/beige-box/neon references + TradeHub) and
`design-refs/session-refs/` (5: additional taste references the user shared mid-session — light
minimal trading UI, "InVest" neo-brutalist chartreuse type, "Finova" purple glass dashboard,
"CRYPTIQ" dark terminal, dark navy mobile trading app). The Finova purple-glass reference and the
CRYPTIQ stepped-chart reference both touch items on the master's banned list (purple→blue
gradients outside Neon; stepped charts on continuous series) — usable for layout/type cues only,
never for palette or chart-geometry decisions. Still missing and not blocking: `stocky.webp`,
the second chalk reference (a slate-board game interface), and the six Fidelity mobile
screenshots — Phase 1 substitutes the companion doc's prose specs for these, which are complete
enough not to block.

**Metric-row destination assignment method.** `CAPABILITY-LEDGER.md` §15's 154 metric rows are
generated mechanically (not hand-classified) via a script reading `docs/METRIC_INVENTORY.md`'s
three tables + `signal_metrics.json`'s 64 live IDs, classifying each row's destination by
matching its `renderSites` cell against a small file→view lookup table (documented in the
ledger's §15 preamble). This keeps the metric section auditable and regenerable rather than
hand-typed, at the cost of some destination assignments being coarser than a fully bespoke
per-metric judgment call would produce (e.g. all of `PerformanceMetrics.jsx`'s ~35 metrics land
on `?view=data` uniformly, even though a couple render in sub-sections that could in principle
get their own anchor). Acceptable for Phase 0 — Phase 2's `core/screens/PortfolioScreen.jsx`
is free to organize them into finer sub-views without changing any capabilityId or disposition.

**Feature registry (53 features, `docs/FEATURE-REGISTRY.md`) — represented in aggregate, not as
53 individual rows.** Every one of the 53 pipeline features already reaches the UI exclusively
through `detail.stock.factor-bars` (`FactorBars`, one bar per `explainability.factor_bars` entry,
count is data-driven not fixed) and the `chart.stock.metric-sections` 8-group breakdown — both
already ledger rows. Adding 53 near-duplicate rows underneath those two would pad the ledger
without adding a distinct UI capability; the feature registry's real contribution (usage
classification: ranking-signal vs. eligibility-filter vs. risk-control vs. confidence-input vs.
explanatory-only) is a pipeline-facing concern, not a rendering one. If a future reviewer wants
per-feature IDs for finer Phase-3 parity checking, they can be split out of `factor-bars` without
changing any other row.

**Font self-hosting deferred, not faked.** The Phase 2a shared-layer plan called for
self-hosting Geist Sans/Mono (replacing the current render-blocking jsdelivr link) and each
medium's display face as build-time-subsetted assets. This session has no font-fetching/
subsetting tooling available (`pyftsubset` and a source for the actual font files), and
fabricating placeholder font files would be worse than leaving the current jsdelivr link in
place. **Deferred to whichever Phase 2b commit first needs a self-hosted display face** — that
commit adds the subsetting step for real, for that one face, rather than this session guessing
at binary assets it can't verify. The jsdelivr link stays untouched for now.

**`/v2` mounted at the app-router level, medium loading proven end-to-end.** `src/App.jsx` now
routes `/v2/*` to `MediumShell` (lazy-loaded — confirmed as its own ~13 kB chunk in the
production build, not bundled into the entry chunk). `registry.js` uses `import.meta.glob`
rather than a template-literal dynamic import specifically so the build succeeds cleanly with
zero medium manifests on disk (confirmed: `npm run build` succeeds with `MEDIUM_META` listing
all twelve while `isMediumImplemented()` is `false` for all of them) — Phase 2b adds each
`manifest.js` file and the glob picks it up automatically, no registry edit required.

**The six core screens are a real, working, intentionally partial slice — not full ports.**
Phase 2a's job was proving the manifest/WallLabel/capability-id/canonical-state pattern works
end-to-end against real data, not porting all ~600 remaining `CAPABILITY-LEDGER.md` rows into
JSX before any medium exists to render them through. What's actually wired, with real data
fetching (no mocked/fake data in the shipped code, only in tests):
- **HomeScreen**: the full three-item first viewport (portfolio hero + today's delta + as-of,
  a growth-chart summary, the live evidence/provenance strip with the promotion disclosure).
  Uses the same current-holdings-applied-to-published-closes computation Dashboard.jsx already
  uses for its own hero (`enrichPortfolio` + `currentHoldingsSeries` + `buildPortfolioPriceData`
  + `liveTodayPortfolioReturn`) — real and correct, but not yet the live-quote-overlaid or true
  TWR chart DESIGN.md's first-viewport recommendation named as the ideal (that chart lives in
  `Portfolio.jsx`'s `?view=performance` today and needs `usePortfolioTracking` +
  `modifiedDietzReturn` wiring — tracked here as follow-on work, not silently approximated).
- **ResearchScreen**: real search over `report.json`, and critically, **the `?q=` param is read
  on mount** — the concrete fix for the Alerts-produces-but-Search-never-reads bug.
- **ScreensScreen**: resolves `?recipe=` to its real published file and renders the artifact's
  own build-status state correctly (gated-is-a-feature for early-session, partial-collection
  alert for politics, success-with-empty-results distinct from failure).
- **PortfolioScreen, MarketsScreen, EvidenceScreen**: each fetches its real primary data source
  and renders one representative, correctly-stated capability (portfolio KPI row, market
  session badge, and — closing the docs-only gap — the live no-signal-promoted disclosure with
  real IC period counts).
Every screen composes only through `manifest.components` (with plain-DOM fallbacks when a key is
absent, matching `WallLabel`'s own fallback pattern) and never imports `src/pages/*` or
page-level `src/components/*`, so nothing here needs to change when Phase 2b starts supplying
real manifests — the screens just start rendering richer material automatically.

**Consolidation shape decided once, not re-litigated per section.** The six-destination set
(Home / Research / Screens / Portfolio / Markets / Evidence) was fixed in the approved execution
plan before ledger authoring began, per the plan's own instruction ("refine during authoring,
don't reopen the shape"). Every `merged`/`moved` row in the ledger targets one of these six —
no row proposes a seventh destination or a different shape.

**Phase 2c — Classic port, judgment calls.**
- **`ResearchRadarChart` reused unmodified, grandfathered from the radar ban.** The banned list
  (root doc "Banned in every theme") retires radar everywhere in favor of `profile` (a sorted
  bar/dot factor-loading chart); the master's own banned-list self-audit explicitly allows
  Classic to keep it, "grandfathered only with NOTES.md listing" — this is that listing.
  `classic/renderer/index.jsx`'s `profile()` function adapts the shared `values: [{label,
  value}]` contract shape into the `{fundamental_categories}` object `ResearchRadarChart`
  expects; the component itself is untouched.
- **Chart-renderer split: 10 of 14 types are literal component reuse, 4 are new-but-token-
  consistent.** `line/sparkline/pairedBar/barTimeline/scatter/heatmap/fan/dotPlot/dial/profile`
  wrap `GrowthChart/Sparkline/PairedBarChart/BarTimeline/ScatterChart/CorrelationHeatmap/
  ProjectionFanChart/DotPlot/ScoreGauge/ResearchRadarChart` directly via thin prop adapters —
  exactly DESIGN.md §12's stated approach ("adapter maps contract props onto existing component
  APIs rather than rewriting them"). `bar/composition/bullet/waterfall` have no existing
  component with a shape generic enough to adapt without inventing new page-specific coupling
  (e.g. `ScoreExplainability`'s waterfall needs a whole `stock` object, not a flat `values[]`),
  so those four are small new SVG functions using the existing design-token set
  (`var(--positive)`/`var(--negative)`/`var(--surface-tertiary)`) rather than a chart library —
  still zero new dependencies, still the existing visual language.
- **`LabelFrame` is new markup, ported CSS classes.** `WallLabel`'s `parts` contract (used
  identically by all twelve mediums) is deliberately narrower than the raw `signal_metrics.json`
  row `SignalMetricsPanel`'s private `Metric` function needs (kill_threshold_value/comparison/
  cadence aren't in `parts` — passing the full raw row through would violate the "structured
  parts, not free text" design the whole rebuild depends on for its disclosure guarantees).
  Reusing `Metric` verbatim was rejected for that reason; instead `classic/components/
  LabelFrame.jsx` derives the exact same tone vocabulary `src/lib/signalMetrics.js`'s
  `metricTone()` produces (`breached/ready/accumulating/pending`) from the canonical state
  already in `parts`, and renders through the identical `.signal-metric`/`.tone-*`/
  `.chip.signal-status-*`/`.signal-kill` CSS classes — full visual/CSS reuse, new markup.
- **ESLint enforcement of 0f was a real gap, closed here.** The Phase 2a plan called for a
  `no-restricted-imports` rule banning `src/mediums/**` (except `classic/`) from importing
  `src/pages/*`/top-level `src/components/*`, but it was never actually added to
  `eslint.config.js` during 2a — nothing enforced the isolation boundary mechanically until now.
  Added as part of this pass (the natural point, since Classic is the first and only medium that
  legitimately crosses it) — verified to catch a real violation and stay silent on all eleven
  other mediums and on Classic's own legitimate imports before being committed.
- **`ProvenanceStrip`/`Nav` are new, not `ModelVersionFooter`/`DataStatus`/the inline `App.jsx`
  nav markup.** Those existing components fetch their own data (`useData('report.json')`
  directly) or are inline JSX in `App.jsx`, not extractable components with the
  `{ready, breached, liveDays, modelVersion, promotionText}` / bare-nav-with-props shape every
  other medium's manifest contract expects. Classic's versions are new, prop-driven components
  styled with the existing CSS classes (`.model-version-footer`, `.mobile-nav`/`.mobile-nav-item`
  /`.mobile-more-nav`, `MobileSheet`, `Icon`) for full visual continuity rather than duplicating
  their own data-fetching a second time.
- **Bottom nav: five destinations become four tabs + a six-destination-consolidated More sheet.**
  Per DESIGN.md §12 exactly: Home/Portfolio/Research/Markets stay direct tabs; the More sheet
  now holds Screens/Evidence (new, absorbing the old route sprawl) plus the pre-existing
  Alerts/Settings entries — same one-more-tap interaction budget as the other eleven mediums.
- **Phase 2c drift check: clean.** `git diff --stat src/mediums/core/` is empty for this commit —
  no core file needed a change to make Classic work. (The three earlier additive `WallLabel.jsx`
  extensions — `previous`, `headline`, `confidenceInterval` — were made during Chalkboard/
  Newspaper/Star Chart respectively, each already committed in its own medium's commit, each in
  service of that medium's own must-include device, not "to make Classic work.")

**Phase 3 — harness build, real bugs the harness caught on its first real-browser run.**
Every vitest test across Phase 2 rendered through jsdom, which never resolves CSS custom
properties or loads a `.css` module's actual rules — so several real, present defects were
invisible until Playwright opened a real `vite build` in a real browser for the first time.
Fixed in place rather than worked around, since a harness that quietly excused its own findings
wouldn't be doing its job:

- **`manifest.loadTokens()` was never called anywhere.** `MediumShell.jsx` loaded a manifest and
  rendered it immediately; nothing ever awaited `loadTokens()`, so every medium's `tokens.css` —
  all twelve mediums' entire `[data-medium="x"]` token/structural CSS — was dead code no browser
  ever injected. Every `var(--ink-primary)`-style reference in every `LabelFrame`/`Container`/
  renderer rendered as an unresolved custom property. `manifest.test.jsx`'s jsdom assertions all
  passed regardless, since RTL checks DOM structure and inline `style` attribute strings, never
  actual computed/resolved colors. Fixed in `MediumShell.jsx` (awaits `loadTokens()` before
  `status: 'ready'`) and the new `E2EHarness.jsx` (same). Confirmed visually after the fix:
  Gallery's frames, Chalkboard's chalk-white-on-slate, Neon's magenta glow all render correctly.
- **Every medium's LabelFrame showed the wrong text in its "big numeral" slot.** `WallLabel`'s
  `parts.read` is `metric.reads` — always PROSE (e.g. "Spearman correlation of score against
  forward return."), never the metric's actual numeric reading. Every one of the twelve mediums'
  `LabelFrame.jsx` files used `read || title` (or an equivalent fallback chain) as the large
  numeral display — meaning the "numeral" position was actually showing a prose sentence, or the
  metric's own label, never a number. Invisible in every medium's `manifest.test.jsx` because
  every fixture across all twelve only ever set `reads: 'A read.'`-style prose and asserted on
  that same string, never a realistic `value`/`display` field. Root cause: `parts` never carried
  the metric's actual formatted numeral at all. Fixed by extending `WallLabel.jsx` with
  `parts.value = metric?.display ?? (metric?.value != null ? String(metric.value) : null)` and
  updating all twelve `LabelFrame.jsx` files to use `value ?? read ?? title` for the numeral slot
  and a separate line for `read` (prose), shown only when a real `value` exists elsewhere on the
  row (never duplicating the same string in both places when there's no numeral to distinguish
  it from). `WallLabel.test.jsx` and every medium's `manifest.test.jsx` updated to match.
- **Several numerals sat under the 16px legibility floor or carried an unintended filter**,
  caught only once Playwright measured real computed styles: Ticker's title/reason spans
  inherited `font-variant-numeric: tabular-nums` from the row-level CSS rule even though they
  hold prose, not readings (fixed by explicitly resetting `fontVariantNumeric: 'normal'` on
  them, and giving the value/status spans an explicit 16px floor they'd been inheriting a
  smaller default without); Beige Box's accumulating caption was 11px; Book's superscript
  observation-count and dagger inherited tabular-nums at sub-floor size (fixed the same way as
  Ticker's prose spans — they're decorative badges, not primary readings); Chalkboard's erasure
  smudge inherited tabular-nums alongside its deliberate `blur(0.4px)` (the blur is the whole
  point of that device — fixed by removing tabular-nums from the smudge specifically, since an
  aria-hidden decorative echo of a prior reading isn't itself "a numeral" the legibility floor
  was ever meant to police); Classic's ported (pre-existing) `GrowthChart` hover-legend value
  renders at an established smaller size — left as-is and excluded from
  `renderer.spec.mjs`'s scan by class name, grandfathered the same way its radar chart and
  light-theme bug already are (chart-internal supporting text, not a `WallLabel` reading).
- **Star Chart's whole magnitude/area-scaling device was reading the wrong field.** It computed
  a star's plotted size from `parts.read` (prose) via a best-effort digit-scrape regex, which
  only ever coincidentally worked when a stray digit happened to appear in the sentence. Fixed
  to read `parts.value` instead, and added a legend line showing the actual numeral (previously
  the metric's real value was never displayed as text anywhere on the plate at all — only
  implied by circle size, which is inaccessible to a screen reader and imprecise for a sighted
  reader too).
- **Classic's `renderer.line()` crashed outright when called with `values` but no `series`** —
  a direct `series.length` access with no default parameter, unlike every other function in the
  same file which routes through `seriesData(series = [], values = [])`'s own defaults first.
  Every other medium's `line()` has the same shape but never dereferences the raw `series` param
  a second time, so only Classic's adapter (which needs `series` to build GrowthChart's `dates`
  array) ever hit it. Fixed with `series = []` on the destructured signature.
- **The `no-restricted-imports` ESLint rule the Phase 2a plan called for was never actually
  added.** Nothing mechanically enforced "only `src/mediums/classic/**` may import
  `src/pages/*`/top-level `src/components/*`" until Phase 3, when it was the natural point to
  close the gap (Classic is the first and only medium that legitimately crosses the boundary).
  Verified against a real violation before committing.
- **`/e2e-harness/:mediumId`, a new diagnostic-only route** (`src/mediums/core/E2EHarness.jsx`,
  gated on `import.meta.env.MODE === 'e2e'`, never present in the real production bundle) mounts
  one medium's real `WallLabel`/`LabelFrame`/renderer against fixed fixtures, isolated from the
  app's Firebase-dependent chrome. Built because the six core screens are still an intentionally
  partial slice (this file, above) that doesn't yet call `manifest.loadRenderer()`/`WallLabel`
  from live traffic — this route is what let `renderer.spec.mjs`/`rules.spec.mjs` inspect real,
  compliant contract behavior at real browser fidelity without waiting on that separate,
  larger page-composition effort. `vite build --mode e2e` (`.env.e2e`, committed, placeholder
  Firebase config only — see its own header comment) is required to build a runnable bundle at
  all: `src/lib/firebase.js` calls `getAuth()` as a module-load side effect that throws
  `auth/invalid-api-key` when `VITE_FIREBASE_API_KEY` is undefined, which is every environment
  without a real `.env.local` — nothing had ever opened the production `dist/` bundle in an
  actual browser before this harness, so this was invisible until now too.
- **`scripts/check-metric-preservation.mjs` still fails on `money_weighted_xirr`**, confirmed
  again via `parity.spec.mjs`'s direct invocation of it — this is the same pre-existing,
  pre-rebuild failure flagged earlier in this file (Phase 0), not something Phase 3 introduced.
  Left failing (not skipped, not worked around) since hiding a currently-red gate would defeat
  the harness's own purpose; the parity report states this explicitly rather than claiming a
  false all-green.

**Phase 3 — motion/a11y/budget spec pass, more real bugs the harness caught.** Full detail (exact
contrast numbers, colors, fixes per medium) is in `PARITY-REPORT.md`'s "Real bugs the harness
found and this session fixed" section — this entry is the short version. Fixed: `main.jsx`
unconditionally injecting an animated HUD overlay into every route regardless of medium (violated
every medium's own "no motion" claim); `/v2/*` nested inside Classic's entire app shell instead of
mounting standalone (sidebar, mobile nav, `Dashboard`, and unconditional idle-preloading of
Classic-only page chunks all loading on every medium); Classic's global ~340 kB stylesheet loading
unconditionally for every route; Ticker's confidence-via-opacity direction inverted relative to
every other medium's stated DESIGN.md convention (low confidence should fade, Ticker's original
formula faded *high*-confidence numerals instead); Ticker's 127px horizontal overflow at 390px
(missing `flex-wrap` + no min-width/overflow clipping on the value column); eight mediums'
`--ink-faint` token failing WCAG AA text contrast at full opacity, before any confidence-wash;
four mediums' confidence-wash/unavailable opacity floors crushing even `--ink-primary` text below
3:1 in the worst case; three mediums' hairline/graticule chart-gridline colors failing the 3:1
graphical floor; Classic's `line` chart adapter never passing a `color` to the reused
`GrowthChartImpl` (its real callers always do — this is this rebuild's own adapter bug, not a
pre-existing one), rendering the SVG stroke as literal black. Also found and fixed two bugs in the
harness itself (not the app): `a11y.spec.mjs`'s chart-ink check resolved the wrong background
element (`[data-e2e-harness]` never carries its own `background-color` — every medium sets it on
`body`), and separately checked `fill` on `<line>` elements, which SVG never renders (no enclosed
area) but which still resolves a computed default. Both test fixes make the assertion more
correct, not weaker. `motion.spec.mjs` also gained one narrow, explicit exemption: Classic's own
DESIGN.md section (unlike the other eleven) does not claim zero motion — it explicitly keeps its
pre-existing, correctly-gated hover transitions, and 0f forbids reopening that shared styling to
force a false "zero motion" claim onto it. The "reduced motion never hides content" half of the
same assertion still applies to Classic. One real, large, unresolved item: `budget.spec.mjs`'s
500 kB ceiling is still red for all twelve mediums after these fixes (cut from ~1.88 MB to ~1.26
MB) — the remainder is Firebase's SDK (~610 kB) plus the core JS runtime (~550 kB), both genuinely
used by the new mediums' core screens, not medium-specific chrome. Getting under budget needs
deferred Firebase loading behind first real auth use, scoped as this rebuild's next piece of work
rather than attempted in this pass.

**Phase 4 — Firebase deferral, closing budget.spec.mjs for eleven of twelve mediums.** Full detail
in `PARITY-REPORT.md`'s "Phase 4" and "Budget" sections; short version here. Root cause:
`App.jsx` statically imported `FirebaseAuthContext.jsx`, and `AppContent()` called `useAuth()`
unconditionally as its first hook, before the `/v2` pathname branch existed in the function —
static imports are resolved at bundle time regardless of which branch runs, so every medium paid
for Firebase's SDK even though only `HomeScreen.jsx` and `PortfolioScreen.jsx` (via
`useFirebasePortfolio`) ever call it. Fixed by making `main.jsx` dynamically import one of two
separate root components based on the entry pathname — a new `MediumApp.jsx` for `/v2`/
`/e2e-harness`, unchanged `App.jsx` for Classic — instead of one component that branched
internally, extending the same route-gated dynamic-import pattern already used for Classic's
stylesheet. `HomeScreen.jsx`'s Firebase-dependent portion moved into a new lazy
`HomePortfolioPanel.jsx`; `PortfolioScreen.jsx` (entirely Firebase-dependent) is now lazy-loaded
from `MediumShell.jsx`. Real regression found and fixed before calling this done: the first cut of
this split left both lazy chunks calling `useAuth()` with no `FirebaseAuthProvider` anywhere above
them in the `/v2` tree (since `MediumApp.jsx` deliberately never mounts one) — this throws and
silently blanked the entire page. Neither `budget.spec.mjs` nor the manual browser checks used
while building this caught it, since neither reads `pageerror` events or confirms real content
rendered, only that navigation completed and bytes stayed under budget; `visual.spec.mjs`'s
pixel-diff did (Home's screenshot was ~2.7 kB instead of ~33 kB — genuinely blank). Fixed by
wrapping each lazy chunk's own content in its own `<FirebaseAuthProvider>` — free, since
`AuthProvider` is the other named export of the same module already being pulled in. Also found:
one medium's Nav.jsx links to the Classic-only `/settings` route as its required "settings
affordance" — under the new two-root split, that's a path `MediumApp.jsx`'s own `<Routes>` can't
serve (only `/v2/*` matches). A soft `<Navigate>` can't reach `App.jsx` either, since main.jsx
never loaded it for this pathname. Added a catch-all in each root (`EscapeToClassic` in
`MediumApp.jsx`, `NotFoundOrMedium` in `App.jsx`, symmetric for the reverse direction even though
nothing currently links that way) that hard-reloads through `main.jsx`'s bootstrap instead.
Measured result: eleven of twelve mediums dropped from ~1.26 MB to ~300–310 kB per cold `/v2` load
— confirmed via a running preview server, not just estimated. Classic-as-a-medium stays at ~660 kB,
but the fix applies to it too (zero `firebase-*` chunks in its own budget breakdown) — its overage
is purely its own pre-existing ~341 kB legacy stylesheet plus the shared ~220 kB vendor runtime,
a separate, already-named, accepted tradeoff, not attempted here.

**Phase 4b-1 — first ledger-coverage slice: Evidence `?section=validation` now renders every
published metric.** `EvidenceScreen.jsx` previously showed only a one-line ready/breached/total
summary for the 64-metric report; it now iterates the full `signal_metrics.json` artifact through
`splitBySampleRequirement`/`defaultOpenGroups`/`sharedStatusMessage` (the same helpers
`SignalMetricsPanel.jsx` already used) and renders every row through `<WallLabel metric={metric}>`
— zero transformation, since the file's rows are already shaped exactly as `WallLabel` expects.
This is the cheapest slice named in the plan (Phase 4b-1 step 2): every medium's own `LabelFrame`
already implements the render contract, so wiring this one screen gets the same ~64 capability
rows live across all twelve mediums at once, at no marginal per-medium cost. Confirmed structurally
sound before committing: `parity.spec.mjs` #1b (every rendered `data-capability-id` is a known
ledger row) passes in isolation — the new `metric.report.*` ids are all pre-existing rows from
CAPABILITY-LEDGER.md §15, none hallucinated; #1a (`check-metric-preservation.mjs`) is unaffected,
its one failure (`money_weighted_xirr`) predates this change. Visual baselines regenerated for the
`evidence-validation` destination across all twelve mediums × two widths (48 screenshots) — the
new content is real, legible growth (checked directly against a rendered screenshot: group
headers, breach markers, kill-threshold text, sample counts all present), not a layout break.
Still not wired here: Portfolio `?view=data`'s ~38 portfolio-derived metric rows (different data
shape — `portfolioAnalytics.js`'s live computation, not a published JSON file — so they need their
own mapping into a `signal_metrics.json`-shaped row before `WallLabel` can render them, unlike this
slice); Evidence backtests/shadow; the ~483 non-metric-class rows (column/control/state/disclosure/
figure/chart/etc.) per screen. Next per the plan's phasing.

**Phase 4b — the six-screen fan-out.** User asked to "hook up everything" and to run parallel
agents. Six agents ran concurrently, one per core screen (`HomeScreen.jsx`, `ResearchScreen.jsx`,
`ScreensScreen.jsx`, `PortfolioScreen.jsx`, `MarketsScreen.jsx`, `EvidenceScreen.jsx`), each scoped
to its own file pair (screen + test) so they could edit the live checkout in parallel without
conflicting — no worktree isolation needed since no two agents ever touched the same file. Every
agent was instructed to copy capabilityIds verbatim from the ledger, never invent one, run only
lint/vitest scoped to its own files (not the full suite, to avoid racing the others), and leave
`capabilityIds.js`/the ledger itself untouched. Results, independently verified after the fact
(every capabilityId literal in each changed file cross-checked against `scripts/ledger-ids.json`,
zero hallucinated in any of the six):

- **Home**: +14 rows (top signal, 5 focused-screen cards via real `researchScreens.js` rank
  functions, inside-information card, privacy toggle, chart-period control, top-5 holdings).
- **Research**: +44/45 rows (sector/sort/asset-type/ownership toolbar, ranked pool honoring every
  `RANKING_MODELS` entry, per-row actions, allocation planner, the watchlist absorbed view).
- **Screens**: +87 of ~117 rows across 7 of 12 recipe families (swing in full — the ledger's own
  "richest disclosure set" — options + 7 strategies, the momentum/quality-value/earnings/matrix
  generic family, early-session, politics, institutional, inside-information). `fast-growth` and
  `themes` still resolve to `null` (unchanged from Phase 2a) — their sources aren't fetched yet.
- **Portfolio**: +124 rows across all 7 views — the single largest slice (77 metric rows in
  `?view=data` alone, 25 more in `?view=diversification`, 4 in `?view=summary`, plus structural rows
  in every view). Insights/Finances/Planning got only an honest floor (loading/no-holdings states) —
  explicitly deferred, not stubbed.
- **Markets**: +23 of 25 rows — both `?view=indexes` and `?view=news`, close to full coverage
  (smallest section).
- **Evidence**: +47 rows completing backtests/shadow/methodology/glossary (validation was already
  done in the prior slice).

Total: parity's own `#1b` DOM scan under the frozen e2e fixture set (which only ships 4 of the
~30 published files newer screens now fetch — `report.json`, `screens/swing.json`, and the two
`validation/*.json` files) reports a modest rendered-id count, but that undercounts badly: most of
the newly-wired rows are gated behind data the fixture harness doesn't carry (backtests, shadow,
options, congress-trades, institutional-13f, inside-information, etfs.json, etc.), so they correctly
render their `unavailable`/empty states rather than crash — confirmed intentional, not broken, by
a direct real-browser check against the actual `.env.e2e`-built dist serving real `public/data/`
JSON (not the trimmed fixtures), which found dense, correctly-structured, real content everywhere
(a 2.3MB real-content DOM on `/v2/research` alone). **Follow-up worth doing, not done here**:
extend `tests/e2e/fixtures/data/` with trimmed real copies of the files the six screens now fetch,
so `parity.spec.mjs`'s DOM scan and the visual-regression matrix can actually exercise this
much of the newly-wired code automatically, instead of relying on ad-hoc manual verification.

**Two real bugs found and fixed during consolidation** (not by the wiring agents themselves — by
running the merged result through the full harness before calling this done, same discipline as
Phase 4a's own regression):
1. `MediumShell.jsx` still statically imported all five non-Home screens. Research/Screens/Evidence
   grew to 800–1200+ lines each during the fan-out, and Screens/Evidence each now mount their own
   `<FirebaseAuthProvider>` — so every `/v2` route's cold load was pulling in all five screens' code
   plus Firebase's SDK again, silently reintroducing Phase 4a's exact problem via a different route
   (confirmed: gallery and classic both regressed past 1.6MB before the fix). Fixed by lazy-loading
   Research/Screens/Markets/Evidence the same way Portfolio already was; Home stays static since
   it's the actual cold-loaded route. Back to 11/12 mediums under budget afterward.
2. `ResearchScreen.jsx` called `useAuth()` directly (for the watchlist/portfolio/alerts absorption)
   without ever wrapping its content in a local `FirebaseAuthProvider` — the one screen among the
   Firebase-touching four that missed this pattern. Crashed the entire `/v2/research` tree to blank
   (no ErrorBoundary above it) — same failure mode as Phase 4a's own HomePortfolioPanel regression,
   and just as invisible to unit tests (whose `useAuth` mock is a no-op regardless of provider
   context) and to `budget.spec.mjs` (measures bytes, not render success). Only a direct
   `pageerror`-listening real-browser check caught it — the same lesson from Phase 4a, learned
   again: verify against a real browser before declaring a multi-agent merge done, not just a green
   test suite. Fixed with the same wrapper pattern as Portfolio/Screens/Evidence.

**Two more issues found chasing a visual-regression flake**, neither invented, both real:
`ResearchScreen.jsx`'s ranked pool had no display cap in its default (non-model) sort branch — with
filters off it rendered every one of the ~900-name universe as a full card, unbounded (the
model-ranked branch already capped at `MODEL_LIMIT`/20; the default branch didn't). Capped at a new
`DISPLAY_LIMIT` (100) with an honest "showing top 100 of N" disclosure, matching the model branch's
own wording convention. Separately, the component gated its loading state on `report.json` alone,
not `etfs.json` — the ranked pool mixes both, so it rendered once report.json resolved and then
silently grew again once etfs.json caught up, after `data-app-ready` had already fired (that flag
only tracks font-settling, not in-flight fetches). Fixed by gating on both. Even after both fixes,
neon's heavier per-card glow CSS still occasionally exceeded the visual harness's default 10s
screenshot-stability window on Research's now much taller page — bumped `visual.spec.mjs`'s
`toHaveScreenshot` timeout to 20s for just that assertion (not the global config), verified stable
across 3 consecutive isolated re-runs before and after.

Final state: lint clean; 1408/1408 vitest tests; production build succeeds; `budget.spec.mjs`
11/12 (classic's own pre-existing ~676kB legacy-stylesheet gap, unrelated); the full
parity/renderer/a11y/motion/rules suite green except the three pre-existing documented exceptions
(classic's axe violation, `check-metric-preservation.mjs`'s `money_weighted_xirr` gap — both
predate this session); `visual.spec.mjs` 208/208 passing, fully stable (no flakes) after the fixes
above.

**Phase 5 — "connect the rest, also add a way to switch back to what i have now."** Closes the
remaining known gaps from Phase 4b: the two still-unwired Screens recipes, Portfolio's three
still-unported views, most of the chart-contract gap, and — new — a discoverable path into `/v2`
and a labeled way back out, since neither existed before this phase (confirmed via a whole-tree
grep: zero links/buttons/`navigate()` calls anywhere targeted `/v2`; `App.jsx`'s
`NotFoundOrMedium` even had a code comment admitting it).

**5a — establishing the chart-renderer pattern.** `manifest.loadRenderer()`/`chartContract.js` had
existed since Phase 2b but was never called from a `core/screens/*` file — only from
`E2EHarness.jsx`'s fixture route. Rather than fan out six agents to each independently discover an
unproven contract (both real bugs in Phase 4b's consolidation came from full-harness/real-browser
checks after a merge, not before — the same risk applied here with more force, since this contract
had zero prior screen call-sites), one agent went first, alone: built `src/mediums/core/
useRenderer.js` (a one-line `const renderer = useRenderer()` hook wrapping the async
`manifest.loadRenderer()` load-once-per-medium dance) and wired `chart.markets.growth-chart` as
the reference implementation, verified with a real browser (`pageerror` listening) across two
mediums before calling it done. Its doc comment became the verbatim reference every Stage 1 agent
was given. One real finding worth keeping: the contract's own doc language (`series | values`)
doesn't specify each chart type's actual payload shape — `line`/`scatter` want `series: {x,y}[]`,
`bar`/`dotPlot` want a flat `values` array — only discoverable by reading an actual per-medium
renderer implementation, not the doc comment alone. Every subsequent agent hit and correctly
resolved the same ambiguity by doing the same thing.

**5b — six parallel agents, same split as Phase 4b, now against a proven chart pattern.**
- **Screens**: both remaining recipes fully wired — `fast-growth` (11 rows, `report.json` +
  `researchScreens.js`) and `themes` (14 rows, `advisor.json`'s `theme_screen` block +
  `theme-peers.json` + the existing `useAdvisorRefresh` hook). Required restructuring the shell:
  it previously gated every recipe on one `useData(RECIPE_FILES[recipe])` call, which would have
  permanently blocked both recipes since neither maps to a single `screens/*.json` file — added a
  `SELF_FETCHING_RECIPES` set so they own their own loading/unavailable states. All 12 Screens
  recipe families are now wired.
- **Portfolio**: all three remaining views fully wired — Insights (13 rows), Finances (25 rows, all
  3 tabs), Planning (31 rows, same Monte Carlo worker and <400ms budget `Planning.jsx` already
  uses). One correction the agent made against its own task brief: age/retirement inputs actually
  come from `useFirebaseFinances()` (Firestore-backed), not `preferences.forecast` as the brief
  suggested — the agent verified against the real reference implementation and the ledger's own
  `dataSource` column rather than following a wrong note, which is exactly the kind of self-check
  this process depends on.
- **Home**: 7 more rows, including two real charts (`chart.home.growth-chart`,
  `chart.home.allocation` via `CHART_TYPES.composition` per the ledger's own donut-retirement
  note) and computed figures (action-needed, watchlist-preview, opportunity-cost,
  performance-evidence-summary). Deferred: `chart.home.projection-panel` (needs the full
  Dashboard.jsx Monte Carlo input chain, a standalone pass).
- **Evidence**: the last two deferred rows closed — `chart.evidence.backtests-dotplots`,
  `chart.evidence.shadow-scatter`.
- **Research and Markets**: both reported nothing left in scope — Research has zero `chart.*` rows
  in the ledger at all (its one visible chart, `chart.home.score-gauges`, is `moved` from Home and
  keeps a `chart.home.*` id — worth a future ledger pass to make that ownership explicit), and
  every `figure.*` row was already wired; Markets' entire §3 section (24 non-redirect rows,
  including the growth chart from 5a) was already complete. Clean no-ops, not oversights.

Deferred, not attempted: `chart.screens.generic-quadrant-scatter` and the 5 already-named Portfolio
chart rows (Monte Carlo panel, scenario sensitivity, rolling-Sharpe, correlation heatmap,
theme-exposure grid) — Screens/Portfolio's data-wiring priorities used the full budget, same
honest-deferral discipline as Phase 4b.

**5c — the switcher.** `src/pages/Settings.jsx` gained a "Try a new look" section listing the five
`shipAtLaunch: true` mediums (gallery/ticker/newspaper/chalkboard/beige-box — the six
`shipAtLaunch: false` mediums stay ungated from a real user's reach, respecting that existing
registry flag rather than overriding it). Picking one writes the medium preference directly to
`localStorage` before navigating — not through `updatePreferences()`, whose own write happens
inside a `useEffect` a render later, which a hard reload to `/v2` immediately after can beat,
silently discarding the pick (confirmed this matters with a real browser check, not just
reasoning). `src/mediums/core/MediumShell.jsx` gained a small, neutrally-styled "← Back to Classic"
button (`window.location.assign('/')`, hard reload — a client-side navigate can't reach `/`, a
structurally different root `main.jsx`'s bootstrap only picks by pathname) in the main-content
branch only, not the entry-page branch, since entry-having mediums already have their own
skip/continue framing. It does not touch the `medium` preference — pure escape hatch, not a reset.
Verified end-to-end with a real browser, both directions, for both a no-entry medium (ticker) and
an entry-having one (gallery/newspaper, dismissed first): zero errors either way.

**Two things found and fixed during consolidation** (same discipline as Phase 4b — full harness +
real browser before declaring done, not just green unit tests):
1. `budget.spec.mjs` intermittently failed under concurrent `--workers` load (newspaper: 531kB) —
   passed cleanly every time in isolation, so a timing race, not a structural regression, but a
   real one worth closing. `HomePortfolioPanel`'s `lazy()` boundary only deferred *when* its import
   (and Firebase's SDK weight) started, not how long it took — mounting it unconditionally inside a
   `<Suspense>` on Home's first render still fired that import in the same tick as everything else,
   and under resource contention it could finish before `data-app-ready` fires (gated only on
   `document.fonts.ready`) and get counted. This is the exact contingency Phase 4a's original plan
   named up front but never needed until Home grew enough content this round to tip the race.
   Fixed with a small `useMountWhenIdle()` hook (`requestIdleCallback`, mirroring `App.jsx`'s own
   idle-preload pattern) gating the actual mount, not just the lazy import — verified stable across
   3 repeated runs at the same concurrency that surfaced it.
2. The new exit control renders on every `/v2` destination, so it alone invalidated every visual
   baseline regardless of content changes — confirmed by reading an actual diff image for
   `evidence-validation` (a section otherwise untouched this round) before regenerating anything,
   rather than assuming. All 208 baselines regenerated and reconfirmed stable across two full
   re-runs.

**Still open, named rather than hidden**: the e2e fixture gap (`tests/e2e/fixtures/data/` ships 4
of the now even more files the six screens fetch) grew rather than closed this round — a
deliberate scope call (the user asked to connect the app, not extend test infrastructure), verified
instead via 13 real-browser route×medium checks plus the switcher round trip, all zero errors. The
generic-quadrant-scatter chart and the 5 named Portfolio chart rows remain deferred. Research's
`chart.home.score-gauges` id-ownership question is a small future ledger cleanup, not a functional
gap.
