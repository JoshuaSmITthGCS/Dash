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

**Consolidation shape decided once, not re-litigated per section.** The six-destination set
(Home / Research / Screens / Portfolio / Markets / Evidence) was fixed in the approved execution
plan before ledger authoring began, per the plan's own instruction ("refine during authoring,
don't reopen the shape"). Every `merged`/`moved` row in the ledger targets one of these six —
no row proposes a seventh destination or a different shape.
