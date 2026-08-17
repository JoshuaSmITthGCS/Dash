# Redesign status — continuation notes

**Companion to `docs/REDESIGN-PLAN.md`. Read both.**
Last updated 2026-08-16 · Phases 0–4 and 6 as merged in `8a1d073f`, plus the
Portfolio decomposition (Phase 2d) and the SVG type-floor fix (`dc1dc3f6`) on top.

This file exists so a new session can pick the redesign up without re-deriving what
was already decided or repeating measurements. It records what is done, what is
left, and — importantly — **four places where the original plan is wrong**, one of
which will break the build if followed literally.

---

## 0. Read this before touching anything

### The Phase 0 gate is closed. Do not re-run it.

The direction was chosen by the user on 2026-08-15 and is recorded verbatim in
`design/direction-approved.md`. It is a **mix**:

- **Base:** Direction C "Studio" — tinted surfaces, layered hue-tinted shadows,
  elevation as the default, radii 8/10/14/18px.
- **Type:** 14px base, Instrument Sans only, 11px hard floor. (Direction B would
  have revived Bricolage Grotesque; it was not chosen, so that font is deleted.)
- **Signatures, all three:** coverage meter (from A), evidence rail (from C),
  score tape (from B).

`DESIGN.md` at the repo root is the constitution derived from that choice. It
passes `npx @google/design.md lint` and its DTCG export emits all four token
categories. **Treat DESIGN.md as authoritative over the plan** where they differ.

`design/directions/D-approved.html` renders the resolved mix using real
`report.json` data and is the visual reference for the remaining phases. Open it
directly in a browser; the button top-right toggles theme.

### Four corrections to `docs/REDESIGN-PLAN.md`

1. **Appendix A's dead-component list is stale and following it breaks the build.**
   Five components it says to delete are live imports today: `AnalysisLayers`,
   `ETFComparisonPanel`, `MetricSections`, `RecommendationShadowPanel` (all
   imported by `StockDetailModal`) and `MetricCard` (imported by
   `PerformanceMetrics`). The four it shelves for "revival" in Phase 4 —
   `ResearchRadarChart`, `ProjectionFanChart`, `ScoreExplainability`,
   `ETFComparisonChart` — are already wired up, so Phase 4 improves them rather
   than resurrecting them. Recompute reachability from `src/main.jsx` before
   deleting anything (script in §5 below).

2. **"59 unlabeled inputs" was 20.** Most of the 59 are inside `<label>` wrappers
   and were already labelled. The 20 that genuinely were not are fixed. A browser
   sweep now reports **zero** controls without an accessible name.

3. **`advisor.json` (37 MB) is fetched by 11 pages, not 3.** The plan names
   Search, Watchlist and Finances. The real list is ThemeExposureScreen,
   Methodology, Insights, Glossary, Finances, Diversification, PolicyRadar,
   OptionsScreen, StrategyScreen, Watchlist, Search, plus `StockDetailModal` and
   `src/lib/recommendation.js`. The payload problem is ~4× bigger than recorded.
   **Resolved in Phase 6** (§1): 7 of the 11 pages moved to `report.json`;
   ThemeExposureScreen/Methodology/Glossary/PolicyRadar were re-assessed as
   correctly needing the full file, not a remaining gap; `StockDetailModal`
   and `recommendation.js` lazy-fetch it only when a row needs enrichment.

4. **The Phase 4 bullet charts cannot be built from the data as published.** The
   plan assumes `value` + numeric `kill_threshold` on a shared scale. In
   `public/data/validation/signal_metrics.json`, `kill_threshold` is prose for 17
   of the 23 metrics that have one (e.g. "Non-monotonic quantiles are fragile"),
   only 6 parse numerically, 14 values are `null`, and the 40 metrics span
   incomparable scales. Building it requires a pipeline change that publishes a
   numeric threshold and a comparison basis. **Do not fake the numbers.**

---

## 1. What is done

Nine commits, `f99fdc1e`..`74a00676`, merged as `8a1d073f`.

### Phase 0 — visual direction ✅
Three real rendered drafts in `design/directions/` (A-ledger, B-tape, C-studio),
each showing Dashboard + a Picks table fragment + Diversification-as-heatmap, in
both themes, built from real `report.json` values — including an 8×8 Pearson
correlation matrix computed from published `analytics_history` over the 250 most
recent common trading days. Screenshots in `design/directions/shots/`.

### Phase 1 — foundations ✅
- **Type scale.** 489 `font-size` declarations, 311 `font:` shorthand sizes and
  25 `clamp()` sizes migrated to an 8-step scale with an 11px floor. The 7–10px
  cluster the audit flagged (245 declarations, 120 at 9px) now resolves to
  `--fs-2xs`.
- **Weights.** The stylesheet used 650/700/720/730/740/750/760/780/790/800 but
  only 400/500/600 were loaded — every one was synthesized. 700 is now loaded and
  302 declarations normalized to the four real weights.
- **Spacing scale.** 1,584 padding/margin/gap/inset values tokenized, 606 snapped
  onto the scale (ties resolve *downward* so nothing inflated).
- **Stylesheet rebuild.** `global.css` (2,403 lines) deleted, split into 11
  modules under `src/styles/modules/` behind `src/styles/index.css`.
- **Override layer collapsed.** One `.card`, one form-control block.
- **`!important`: 28 → 0** (the 15 that remain are reduced-motion and the
  `data-motion` / `data-chart-*` preference overrides, which must outrank
  component CSS by design).
- **Dead code.** 7 genuinely unreachable components deleted (1,173 lines);
  `useMediaQuery` extracted from its two verbatim copies.

### Phase 2 — component consolidation (partial) ✅/⚠️
- **One card.** 26 classes that independently restated background/border/radius/
  shadow now inherit from one rule in `base.css`, with `.card--inset`,
  `.card--compact`, `.card--interactive` as modifiers. 68 duplicate declarations
  removed.
- **`DataTable`** built (`src/components/DataTable.jsx` + `src/lib/dataTableSort.js`).
  Semantic table on desktop; below the mobile breakpoint the same rows as cards,
  virtualized past a threshold; **exactly one tree mounts**. Card fields default
  to the column definitions so the two views cannot drift.
  **9 pages migrated:** ShadowPortfolios, InstitutionalActivity, CongressTrades,
  ResearchScreen, BacktestComparison (both tables), FastGrowthScreen,
  ThemeExposureScreen, StrategyScreen, OptionsScreen.
- **Navigation debt resolved.** `/screens/early-session` and `/screens/shadow`
  added to the Research group; `/market` (the news reader, not a second markets
  page) linked as "News".

### Phase 3 — accessibility ✅
- **`src/lib/useDialog.js`** — focus in, focus trap, Escape, focus restore.
  `StockDetailModal` and `MobileSheet` both use it. Verified in a real browser:
  focus enters the dialog, holds for 40 consecutive Tabs, and Escape returns it
  to the exact button that opened it.
- **All 20 genuinely unlabelled inputs fixed.**
- **Mobile clip hack removed** — `.analytics-counts small` was clipped to 1px
  while the icon beside it is `aria-hidden`, leaving a phone reader with a bare
  glyph. The chips reflow onto two columns instead.

### Phase 4 — charts ✅ (see the two disclosed gaps below)
- **All four chart palettes validated** with the dataviz validator and fixed in
  the tokens. Three failed. See §3 for the details — they were real bugs.
- **`CorrelationHeatmap`** replaces the raw `<td>` matrix on Diversification:
  diverging scale, neutral gray at zero, value printed in every cell, per-cell
  accessible name stating the number *and its meaning in words*, live-region
  hover readout, and a table view carrying the same numbers.
- **The plan's "10 charts unbuilt" was stale before this pass started** —
  research found `ResearchRadarChart`/`ScoreExplainability` already wired into
  `StockDetailModal`, and `ProjectionFanChart` already wired into Planning via
  `ProjectionPanel`. Corrected list: 8 genuinely new build items, all shipped.
- **Two new reusable chart primitives, plus two single-use ones**, all built
  to GrowthChart's existing conventions (`useElementWidth`, tokens,
  `useMediaQuery`) and CorrelationHeatmap's chart/table toggle pattern:
  - `ScatterChart` — risk/return scatter (ShadowPortfolios: max drawdown vs.
    aligned net return) and the structural/tactical quadrant scatter
    (ResearchScreen's matrix screen, 300 points, colored by the model's own
    classification with median-split reference lines).
  - `DotPlot` — dot-plot small multiples per comparable group
    (BacktestComparison), the cross-strategy annualized-return comparison
    (new `CrossStrategyComparison`, wired into OptionsScreen — the other half
    of "stat-tile row + comparison dot plot", `BacktestSummary` already had
    the stat-tile row), the macro bullet trio (Dashboard's Market pulse,
    reusing the FRED regime's rates/inflation/labor factor scores), and theme
    signal bars (ThemeExposureScreen, mean resolved score per declared signal
    across a theme's leaders).
  - `PairedBarChart` — champion-vs-challenger mean rank IC by horizon
    (LiveValidation), bars anchored to zero since IC can be negative.
  - `BarTimeline` — congress disclosed-trade volume by month (CongressTrades).
  - All four share one accessibility fix found while verifying the 300-point
    quadrant scatter: past 40 points/bars, individual marks stop being
    keyboard tab stops (40 tab presses to clear one chart is a real
    regression) and the live-region readout points keyboard users to the
    always-available Table view instead. Under the limit, every mark stays
    individually focusable.
  - One real bug found and fixed in passing: OptionsScreen's `DataTable` used
    ticker alone as the row key, but the published screen has (and, in the
    checked-in snapshot, did — 4 of 33 rows) carried the exact same contract
    at two adjacent ranks with an identical score. Composite key plus a
    defensive dedupe now in the frontend; the duplicate-row cause is a
    pipeline issue, not fixed here.
  - One spacing bug found and fixed: `.dot-plot` only had bottom margin, fine
    where a paragraph's own margin supplied the gap (BacktestComparison),
    broken where it follows a CSS grid directly (Dashboard's Market pulse).
    Now margin on both sides, re-checked against the other three usages.
- **The `SignalMetricsPanel` bullet-chart blocker is now partially closed**,
  not just documented as blocked. `pipeline/signal_metrics.py`'s `metric()`
  gained `kill_threshold_value` + `comparison` — a real, same-scale-as-`value`
  numeric pair, populated only where one genuinely exists (never derived from
  the prose `kill_threshold` text, never fabricated). 9 of the 40 published
  metrics now carry it: `rank_ic_1d/5d/21d/63d`, `ic_ir`, `percent_of_adv`,
  `deflated_sharpe`, `probabilistic_sharpe`, `pbo`. Two previously-inline magic
  numbers (`feature_psi`'s `0.25`, `percent_of_adv`'s `5`) became named module
  constants alongside the existing `MINIMUM_MEAN_IC`-style ones in the same
  pass. `SignalMetricsPanel` draws a small inline bullet (track, threshold
  tick, value dot colored by breach state) on exactly those 9 cards — nothing
  else. Verified end-to-end: pipeline tests (33/33 in this file, 1982/1982
  across the suite), `validate_data.py`, `check_ui_weights.py`, and
  `validate_documentation_claims.py` all pass; the regenerated
  `public/data/validation/signal_metrics.json` shows real breached/healthy
  bullets on the live page in both themes.

  **Not closed, and correctly still absent from the chart**: the other 14
  metrics that carry a `kill_threshold` string. Per the research behind this
  fix, they fall into three groups that a same pass legitimately cannot
  resolve: (a) `per_leg_ic`, `leg_correlation`, `drop_one_leg` compare a
  *count* against an implicit `0`, not the number already in their
  `kill_threshold` text — republishing that needs a semantic call, not
  extraction; (b) `rolling_beta_60d` and `sector_active_weights` compare a
  quantity that isn't `value` at all (a rolling swing, a coverage fraction
  sitting in `detail`) — needs a structural field change; (c)
  `quantile_spread` and `alpha_cost_crossover` have no numeric form at all (a
  monotonicity flag, a string horizon label), and `breakeven_gross_alpha`'s
  comparator — "IC-implied expected return" — is never computed anywhere in
  the codebase, a methodology gap, not a plumbing one. `live_vs_backtest_ic`
  and `live_vs_backtest_divergence` have a computable bound sitting one line
  away (`error * DIVERGENCE_Z_THRESHOLD`, already-existing confidence
  intervals) but are lower value while the live sample is this young. None of
  these are faked. See `pipeline/signal_metrics.py`'s `metric()` docstring for
  the same explanation next to the code.
- **The score-history line in `StockDetailModal` was never buildable and
  still is not** — a genuine data gap, not a chart-building task. `history`/
  `analytics_history` on a research row carry price series only; there is no
  per-row time series of the *score* anywhere except the 31 MB
  `score-history.json` the doc already forbids fetching in the browser.
  Publishing one would need a pipeline change (a small per-row score-history
  series, sized for the browser) that is out of this pass's scope.

### Phase 6 — metadata + type floor ✅ (perf/motion/rescore still open, see §2)
- Open Graph / Twitter / robots / color-scheme tags; manifest colours aligned to
  the new dark canvas.
- **11px floor closed in the DOM, NOT in SVG.** A browser sweep found 1,748 elements
  still rendering below 11px *after* the CSS was clean — `.direction-value > span` at
  `.7em` computed to 8.4px (1,002 occurrences on `/research` alone) and four SVG
  axis labels set `fontSize="10"` as an attribute. Both fixed, and DOM text is clean
  across every route swept.

  **That sweep's SVG result was wrong, and the "0 sub-11px" claim below it was too.**
  It read `getComputedStyle().fontSize`, which for SVG returns the *specified* size in
  user units. A chart with `viewBox="0 0 1080 360"` and `width="100%"` scales its
  contents, so `fontSize="11"` inside it paints at 8.9px in a 900px container. Setting
  the attribute to 11 satisfied the old sweep without changing what a reader sees.

### SVG type floor ✅
Was a `DESIGN.md` hard-rule breach on every route that draws a chart. `fontSize="11"`
inside `viewBox="0 0 920 360"` rendered into a 743px box paints at 8.9px, and
`getComputedStyle` still reports 11 because that is the specified size in *user units* —
so the attribute could never be edited into compliance while the viewBox width differed
from the box width.

Fixed by making the **viewBox width track the measured container width**, so the scale is
exactly 1 and every px inside a chart means that many px. `src/lib/useElementWidth.js`
does the measuring; `GrowthChart`, `ProjectionFanChart` and `MarketHeatmap` consume it.

| Component | Before (1440px / 820px) | After |
|---|---|---|
| `GrowthChart` axis labels | 8.9px / 7.6px | 11px |
| `ProjectionFanChart` axis + marker | 8.1px / 4.2px | 11px |
| `MarketHeatmap` tile labels | 12–15.6px / 6.8px | 11–14px |

`node design/typefloor.mjs` reports **0 violations across 10 routes × 3 widths**
(1440/1100/390), plus the stock-detail modal checked separately. It exits non-zero, so
it can gate CI — not yet wired into `.github/workflows/ci.yml`'s `site` job.

Three things that fell out of it, worth not re-breaking:

- **`GrowthChart` was letterboxing 69px of its own declared height.** `height={360}` with
  a scaled viewBox meant only 291px was ever drawn, centred, with dead bands above and
  below. Charts now fill the height they reserve.
- **Y-axis labels were clipped to `,178.00`.** The gutter was a fixed 52px and
  "$24,178.00" is ~66px of 11px mono. It is now sized from the actual tick strings.
- **`MarketHeatmap` was relying on being scaled *up*.** Its labels were specified at 8–10
  and only cleared the floor because a wide container magnified them 1.56×. Specified
  sizes raised to 11–14, with the label offsets, the `showLabel` gates and the truncation
  cutoff re-derived from the font size rather than the 10px they were first tuned for.

Two gotchas the fix had to handle, both worth knowing before touching this again:
a chart inside a **closed `<details>`** still gets a layout box but Chromium skips
`ResizeObserver` callbacks for skipped content, so `useElementWidth` measures once
directly on mount as well as observing; and `ProjectionFanChart` must **not** clamp its
viewBox to a minimum width the way `GrowthChart` does, because it clips
(`overflow-x: hidden`) where `GrowthChart` scrolls — clamping would silently reintroduce
the down-scaling.

`design/typefloor.mjs` opens every `<details>` before measuring, so collapsed sections
are audited in the state a reader actually sees.

### Phase 5 — Portfolio (done)
Second page in traffic order, after Dashboard. `ComparisonTables.jsx`'s two raw
`<table>`s now run on `DataTable` (one shared column set, `rowClassName` — new
`DataTable` prop, see below — for the bold TOTAL row), which incidentally fixed a
mobile-overflow gap neither table had a scroll wrapper for. Fixed a real
`DESIGN.md` breach: the edit-sheet's cost-basis-unit select was `fontSize: 9`,
below the 11px floor, and duplicated (with the bug) a pattern `AddPositionForm`
already had right — both now share `.field-mode-select`. 6 more static inline
styles converted to classes. Sector allocation is drawn on Summary, Dashboard,
and Diversification — Dashboard already links through to Diversification instead
of duplicating; Summary's copy stays (it's the one place you see your own
allocation while managing it) and now also links through, rather than being cut.

`DataTable` gained a `rowClassName(row, index)` prop (`src/components/DataTable.jsx`)
for pinned/summary rows — the remaining Phase 2c migrations (SwingScreen's
suppressed rows, ResearchEvidence's pinned self-row) reuse it instead of each
inventing a workaround. Verified: `npm run lint && npm test && npm run build`
green, `design/typefloor.mjs` 0 violations across all default routes (including
`/portfolio?portfolioPreview=1`, which now exercises the fixed select),
`design/a11ycheck.mjs` 0 unnamed controls.

### Phase 2c — all four remaining tables migrated to DataTable ✅
`ResearchEvidence.jsx`'s three tables, `SwingScreen.jsx`, and `Picks.jsx`'s
`ResearchPool` all now run on `DataTable`. Two more capabilities added to
support them: `rowHeader` (a column renders as `<th scope="row">`, preserving
the row-identity semantics `ResearchEvidence`'s tables already had) and
per-column `defaultSortDir` (SwingScreen's columns each have a sensible first
click direction — rank ascending, most numeric columns descending — which a
single global default would have flattened). SwingScreen's locally duplicated
`compareBy`/`SortHeader` are deleted in favor of the shared `dataTableSort.js`
and `DataTable`'s own header. Every migrated column stays `sortable: false`
where the original had no header-click sort (Portfolio's comparison tables,
ResearchEvidence, Picks) — that remains a scope decision for later, not a
side effect of the port. Two always-mounted mobile fallbacks (SwingScreen's
`ResultCards`, Picks' `MobileVirtualList`) are replaced by `DataTable`'s own
mobile config, so exactly one tree mounts on every migrated page. Verified:
lint/test/build green (759 tests), `typefloor.mjs` 0 violations on `/research`
(Picks), `/screens/swing`, and `/screens/validation` (ResearchEvidence via
LiveValidation) individually and in the default sweep.

### Phase 2e — inline-style diet ✅
161 sites at the start of this pass (the previously-recorded 167 was stale —
`MarketHeatmap.jsx`/`ProjectionFanChart.jsx` had already dropped to 0 by the
SVG type-floor fix). Computed values stay inline exactly as the rule says
(bar/fill widths, `--widget-order`/`--success`/`--dial-size` custom
properties, every `moveColor()`/`actionStyle()`-derived color, SVG chart
geometry) — roughly 78 sites across `Insights.jsx`, `StockDetailModal.jsx`,
`PortfolioMoveExplanation.jsx`, `GrowthChart.jsx`, `Diversification.jsx`,
`Dashboard.jsx`, `PerformanceMetrics.jsx`, `ActionGuidance.jsx` and a long
tail of one-or-two-site files. Everything else converted to classes:
`Finances.jsx` (27), `StockDetailModal.jsx` (8), `GrowthChart.jsx` (12),
`Methodology.jsx` (9), plus `Bits.jsx`, `ActionGuidance.jsx`,
`MetricSections.jsx`, `Glossary.jsx`, `CongressTrades.jsx`,
`InstitutionalActivity.jsx`, and `Planning.jsx` (Portfolio's files were
already done in the Phase 5 pass).

Two off-scale values (18px, 28px, both exact ties between adjacent tokens)
rounded **down** per the Phase 1 convention already established for this
codebase. One shared class was renamed mid-pass — `.chart-empty-state`
became `.muted-mono-note` (`base.css`) once it turned out `Bits.jsx`'s
`Loading`/`Empty` components, used across most of the app, needed the
identical rule; a chart-scoped name would have been misleading there.
`.component-scores--fluid` needed a compound selector
(`.component-scores.component-scores--fluid`) to keep beating a mobile
breakpoint override in `controls.css` that the original inline style had
always won against by specificity alone.

Found and fixed one real, unrelated `DESIGN.md` floor violation while
verifying a route this pass touched: `.trade-identity-reveal`'s `<small>`
(`workspace.css`, `CongressTrades.jsx`) had no explicit font-size, so it
inherited the browser's `0.8em` default against a ~12px ancestor and
rendered at 9.6px. Confirmed pre-existing (present 15 commits back, from
the Phase 1c stylesheet split) — not introduced by this pass, but cheap to
fix while already there. Verified: lint/test/build green,
`design/typefloor.mjs` 0 violations on every route checked (default sweep
plus `/methodology`, `/glossary`, `/screens/politics` individually),
`design/a11ycheck.mjs` 0 unnamed controls, visual check in both themes via
`appshot.mjs` for `/methodology` and `/glossary` and a scripted modal
screenshot for `StockDetailModal`. Not verified in-browser:
`Finances.jsx` and `GrowthChart.jsx`'s Dashboard usage both require
Firebase-backed data that's offline in local dev (same known limitation as
Portfolio/Diversification) — lint/test/build stood in for those two.

### Phase 6 — dead code + payload ✅ (motion pass, rescore still open, see §2)

**Nine unreachable lib files, resolved.** Deleted 8 with zero imports and zero
test references (confirmed by grep): `evidenceStrength.js`, `fidelityConnectorStub.js`,
`labelDistribution.js`, `pipelineGuardrails.js`, `securityStub.js`, `sentimentEngine.js`,
`usePortfolio.js` (also independently broken — imported a since-removed `AuthContext`),
and `nightlyRefresh.js` (+ its test). `scoreBands.js` kept per the existing instruction
(CLAUDE.md cites its test as the canonical example command). `nightlyRefresh.js` wasn't
a forgotten wire-up — `usePortfolioQuotes.js`'s own comment shows the current
architecture deliberately replaced a browser-side refresh timer with server-side
5-minute cloud snapshots, so the file was leftover from a superseded design, not a gap.
Fixed two stale comments (`Dashboard.jsx`, `docs/spec/FILE_INVENTORY.md`) that still
described the old 9pm-boundary design, and removed the 8 corresponding
`FILE_INVENTORY.md` entries.

**Payload: 7 of 11 `advisor.json`-fetching pages moved to `report.json`** (37 MB →
6.6 MB), after checking every field each page reads against `report_snapshot()`'s
output. `Diversification.jsx` (drops the fetch entirely — `theme_screen.by_ticker` is
already on `report.json`), `OptionsScreen.jsx` and `StrategyScreen.jsx` (drop the
`advisorByTicker` map — `StockDetailModal` already lazy-fetches `advisor.json` itself
whenever it's opened with an unenriched row), `Insights.jsx`, `Finances.jsx`,
`Watchlist.jsx` (straight swaps), and `Search.jsx` (enabled by a small pipeline
addition — `report_snapshot()` now includes `universe`, the flat ~927-ticker list, a
few KB — so Search's "covered universe, not yet enriched" tier still works without the
full file). `ThemeExposureScreen.jsx`, `Methodology.jsx`, `Glossary.jsx`, and
`PolicyRadar.jsx` stay on `advisor.json` deliberately — they're dedicated deep-dive
pages needing `theme_screen.themes` / `methodology` / `capability_status` /
`disclaimer` / `news`, none of which belong in the intentionally-compact
`report.json`. That reframes the earlier "37 MB across 11 pages" framing: 4 of those
11 were always the right pages for the full file, not a remaining gap.

Found and fixed one real, pre-existing bug while doing this: `OptionsScreen.jsx`'s
`DataTable` used `getKey={(row) => row.ticker}`, which collided because production
data genuinely publishes the same contract twice at adjacent ranks (confirmed via
direct inspection of `public/data/screens/options.json`: 4 of 33 rows duplicated,
e.g. the COP $115 call exp 2026-08-21 at both rank 4 and rank 5, identical score).
Fixed at the frontend with a composite key plus a defensive dedupe — the pipeline-side
root cause (why the row is emitted twice) is still open and out of this pass's scope.

**`score-history.json` (31 MB), removed.** Nothing read it — the one grep hit was an
unrelated `.score-history` CSS class name on a per-row field, not the file. The
per-row `explainability.score_history` field (attached by `attach_explainability()`)
is what `StockDetailModal` actually reads, and is unaffected: `fetch_advisor.py` and
`build_normalization_snapshot.py` still compute `score_history`, they just stopped
writing it out as a standalone file. `diagnostics.json` (4.9 MB) was **not** removed —
it has one real reader, `pipeline/audit_ticker.py`, a CLI debugging tool.

Verified: pipeline test suite (1,982 tests), `validate_data.py`,
`check_ui_weights.py`, `validate_documentation_claims.py`; `npm run lint && npm test
&& npm run build`; `design/typefloor.mjs` / `design/a11ycheck.mjs` / scripted
Playwright checks against a local dev server for every page not Firebase-gated.

### Phase 6 — motion pass ✅
Ran the `improve-animations` skill (recon → 8-category audit → vetted findings →
plans) non-interactively per `docs/REDESIGN-PLAN.md`'s "plan-then-execute" Phase 6
instruction, defaulting to the top-3-by-leverage findings rather than waiting for a
selection. Full audit trail — the vetted findings table, the two lower-leverage items
that were recorded but not planned, and what was checked and found already correct
(chart entrance/draw keyframes, the gauge arc) — is in `plans/README.md`; the three
executed plans are `plans/001-*.md` through `plans/003-*.md`.

- **Pull-to-refresh indicator was chasing the finger, not tracking it (HIGH).**
  `usePullToRefresh.js` calls `setPullDistance` on every native `touchmove` — real
  1:1 gesture tracking — but `.pull-to-refresh`'s CSS transitioned `height` at a
  fixed 150ms, so every frame retargeted a transition still mid-flight from the
  previous one, and `height` is a layout property besides. Fixed by tracking with
  no transition while dragging and adding it back only for the release/cancel
  settle, via a new `settling` state threaded through `usePullToRefresh` →
  `PullToRefreshIndicator` → a `.pull-to-refresh--settling` class.
- **The app's most-used dialog had zero entrance motion, on any viewport
  (MEDIUM).** `.modal-overlay`/`.modal` backs `StockDetailModal` (opened from
  Search, Picks, Watchlist, Portfolio, every screen page) and the login modal,
  and simply teleported into existence — while the *other*, lower-traffic sheet
  component in the same file already had a proper `sheet-in` entrance. Added a
  fade to the overlay and a fade+scale(0.96→1) to the panel on desktop, and reused
  the existing `sheet-in` keyframe verbatim for the mobile bottom-sheet variant,
  both gated through the file's one existing `prefers-reduced-motion` block.
- **`AnimatedNumber` was the one animation in the app that ignored motion
  preference (MEDIUM).** Every CSS animation in the codebase already respects
  `prefers-reduced-motion`; this JS `requestAnimationFrame` count-up (Portfolio's
  headline "Invested value") did not. Fixed by checking
  `window.matchMedia('(prefers-reduced-motion: reduce)').matches` — the same
  expression `GrowthChart.jsx` already uses for its haptic-feedback gate — and
  folding it into the existing early-return branch, so reduced motion jumps
  straight to the target value with the same code path already used for a no-op
  update.

Two findings were recorded but not promoted to a plan (both LOW, both explained in
`plans/README.md`): `.refresh-progress-fill`/`.live-countdown-progress` animate
`width` instead of `transform: scaleX()`, but both update at most once a minute or
once per refresh, not per-frame, so the real cost is negligible; and hand-typed
durations/easings scattered across ~10 chevron-rotate/hover sites could consolidate
onto the existing duration/easing tokens, but the values involved are already close
enough that there's no user-visible difference.

Verified: `npm run lint && npm test && npm run build` (786 tests) green,
`design/typefloor.mjs` 0 violations across the default sweep, `design/a11ycheck.mjs`
0 unnamed controls (also exercised the modal's focus trap/escape live), a scripted
Playwright check confirming both new keyframes (`modal-in`, `modal-overlay-in`)
apply on open, and a throwaway (written, run, deleted — not committed) RTL test
confirming `AnimatedNumber` jumps instantly with reduced motion mocked on and still
interpolates with it off. Not verified live in-browser: the pull-to-refresh fix and
`AnimatedNumber`'s real call site both need either a touch-capable viewport or
Firebase-backed data unavailable in local dev — the mechanical loop plus the
scripted checks above stood in.

### Phase 6 — rubric rescore ✅ · 18/20 (was 12/20) · redesign arc complete
Re-ran the original impeccable 5-dimension audit (`docs/REDESIGN-PLAN.md` §"Audit
summary"), per its own instruction to use `rams` and `web-design-guidelines` as
independent checkers. Dispatched one agent per skill, each re-scoring against the
current codebase with its own greps/reads/live checks — not asked to trust the
redesign's own claims. Two real, previously-unknown gaps came out of that and were
fixed before finalizing the score (both below). Target from the plan was **≥17/20,
with Accessibility ≥3 and Implementation integrity ≥3** — met on both counts.

| # | Dimension | Was | Now | What changed |
|---|-----------|-----|-----|-------------|
| 1 | Accessibility | 2 | **4** | Modal now has `role="dialog"`/`aria-modal`/a 40-tab focus trap/Escape-with-focus-return (verified live). Inputs spot-checked as properly labeled. Zero sub-11px text. One real gap the original audit never flagged — `.market-search-input`/`.global-search-input` both set `outline: 0` unconditionally, silently killing the app-wide `:focus-visible` ring for keyboard users on both search boxes — found and **fixed** (see below). |
| 2 | Performance | 2 | **3** | `advisor.json` eager-fetchers cut from 11 pages to 4, each independently confirmed to need the full file (§1, Phase 6 payload). `score-history.json` (31 MB) gone. Clean route-level code-split build, no monolithic chunk. **Not fixed, recorded as a gap**: `DataTable`'s desktop `<table>` path has no virtualization — a screen rendering the full ~910-name universe still mounts every `<tr>`. Real, but out of this pass's scope. |
| 3 | Responsive | 3 | **4** | No `clip`/`!important` suppression hack found anywhere (the two originally-flagged patterns are both gone); virtualization intact on mobile lists; extensive `overflow-x:auto` scroll containers. No remaining violation found by the independent checker. |
| 4 | Theming | 3 | **4** | Inline styles down to the documented ~78 computed-value sites (from ~340); hardcoded hex down to a handful of defensible cases (contrast-derived inks, illustrative swatches). One real leak the checker found — `Diversification.jsx`'s sector-allocation donut hand-rolled its own `conic-gradient` from a raw, non-token 8-color array with **no dark-mode variant**, and assigned color by array *index* rather than sector *identity* (a sector's color could change depending on what else was present that day — a `dataviz` non-negotiable: "color follows the entity, never its rank"). **Fixed**: swapped for the existing `AllocationDonut` component, already used identically by Dashboard and Summary, which draws from the validated `--sector-*` tokens. |
| 5 | Implementation integrity | 2 | **3** | Zero orphaned files in `src/components/` (was ~⅓ dead) — one flagged `src/lib/scoreBands.js` "orphan" is a false positive: it's deliberately kept, CLAUDE.md cites its test as the canonical example command. Real type scale (10 `--fs-*` tokens) and spacing scale (15 `--sp-*` tokens) confirmed. `!important` down to 6 total across the whole tree (was ~30, one of them the `display:none !important` hack, now gone). **Not fixed, recorded as a gap**: `*card*`-family class names grew to 59 (from 31) rather than consolidating — each maps to a real, purposeful surface, not duplication, but a naming pass is still owed. |
| | **Total** | **12/20** | **18/20** | |

Both fixes are committed (`286e2535`). Both recorded gaps (desktop table virtualization,
card-class naming consolidation) are real and deliberately left open — not silently
dropped, just genuinely out of this pass's scope; a future session can pick either up
without re-auditing.

This closes Phase 6, and with it every subsystem scoped into the "finish everything
out" pass: the Portfolio page pass (Phase 5), Phase 2c (table migrations), Phase 2e
(inline-style diet), Phase 4 (charts + the signal-metrics pipeline change), and
Phase 6 (dead code, payload, motion, rescore). **Phase 5's page-by-page pass itself
is not fully done** — Dashboard and Portfolio are done, but Picks, SwingScreen, the
rest of the screens family, Finances/Planning/Insights/Watchlist/Markets, and
Methodology/Glossary/Settings/Alerts were never in this pass's scope and remain
"not started," exactly as §2 already says. Don't read this rescore as covering
pages it didn't touch.

### Post-rescore — DataTable desktop virtualization ✅
Found while starting Phase 5's next page (Picks): the rescore's recorded gap
("DataTable's desktop `<table>` has no virtualization") was precisely
quantified and fixed. `src/components/DataTable.jsx` now virtualizes the
desktop `<table>` past `virtualizeFrom` rows (default 50, matching the
existing mobile threshold), using the standard "two padding `<tr>`s" technique
so a real semantic `<table>` stays intact — no `position:absolute`/`transform`
row hacks. Two scroll contexts exist in this codebase and both are handled: an
element-scoped `@tanstack/react-virtual` instance for a table that's genuinely
height-clipped (`.research-table`'s `72dvh` internal scroll, used by Picks and
SwingScreen), a window-scoped one otherwise (every other table, which grows
with the page).

**Real bug found and fixed inside the fix.** The first implementation detected
"is this an internally-scrolling table" from `getComputedStyle(...).overflowY`
— which is wrong: CSS computes `overflow-y` to `auto` on *any* box whose
`overflow-x` is non-`visible`, even with no height constraint at all (the box
can't clip one axis and leave the other fully unclipped), and `.data-table`'s
base rule sets `overflow-x: auto` unconditionally. That made every DataTable
instance register as "internally scrolling," which pointed the element-scoped
virtualizer at containers that don't actually clip — their measured height
equals their full content height, so the virtualizer concluded "everything is
in view" and rendered all rows anyway. Caught by testing against real pages,
not the unit tests (all 15 passed against this broken version too, since they
don't assert on rendered geometry). Fixed by detecting from rendered geometry
(`scrollHeight > clientHeight`) instead of declared style.

Verified against all 5 real large-table pages found in a targeted audit
(`FastGrowthScreen` ~880 rows, `CongressTrades` up to ~1,160, three
`ResearchScreen`-backed screens ~300 rows each, plus Picks) via Playwright:
row counts stay small (11-42) through wheel-scroll, keyboard PageDown, and a
cold single-flick jump; sorting still works; no visual gaps/overlaps scrolling
through hundreds of rows. Small tables (the majority of DataTable's ~12
consumers) are unaffected — same code path as before, gated entirely on
`virtualizeFrom`. `npm run lint && npm test && npm run build` green (789
tests, +3 new), `design/typefloor.mjs`/`design/a11ycheck.mjs` clean. Also
added a `ResizeObserver` stub to `src/test/setup.js` — jsdom doesn't implement
it, which `@tanstack/react-virtual`'s dynamic measurement needs, and no prior
test exercised a virtualized list closely enough to hit the gap.

---

## 2. What is left

Ordered by value. Everything below is also summarised in `TODO.md`.

### Phase 5 — page-by-page pass · DASHBOARD + PORTFOLIO DONE · PICKS + SWINGSCREEN LIGHT-TOUCH · rest not started
Per the plan, in traffic order: ~~Dashboard~~ → ~~Portfolio~~ → ~~Picks~~ →
~~SwingScreen~~ → rest of the screens family →
Finances/Planning/Insights/Watchlist/Markets →
Methodology/Glossary/Settings/Alerts → empty states. Picks and SwingScreen are
struck because their passes are complete, not because they got the
Dashboard-style rebuild treatment — see §1, each needed one real bug fixed, not
a restructure. Next: the rest of the screens family (`FastGrowthScreen`,
`OptionsScreen` + its 7 `StrategyScreen` variants, `ResearchScreen`-backed
screens, `CongressTrades`, `InstitutionalActivity`, `ThemeExposureScreen`,
`BacktestComparison`, `ShadowPortfolios`, `LiveValidation`).

**Dashboard (done).** It was 8,583px — 8.5 viewport-heights of "overview" — and
27% of that was a second copy of Portfolio → Data overview. Now 6,651px (**−22.5%**),
verified in light and dark at 1280/1440/390px with no horizontal overflow:

- **Stopped duplicating the metrics apparatus.** `PerformanceMetrics` on the Dashboard
  rendered the full four-tab, three-section, evidence-matrix workspace — mostly
  "? Insufficient" cards — from just `metrics`. Replaced with
  `PerformanceEvidenceSummary` (exported from the same file, so it shares
  `buildPortfolioMetricModel` / `sectionAssessment` / `combinedEvidence`): the read, the
  headline Sharpe/drawdown, the counts, the bar, and a link through. −1,900px.
- **One market read instead of three.** `MarketSentimentStrip` restated macro regime
  and top mover 6,000px below where `HomeMarketSummary` already showed them. Deleted;
  its one unique field (research leader) folded into the top strip, and the universe
  count moved to the page-head eyebrow where dataset metadata belongs. Its dead CSS and
  motion rules are gone too.
- **Scope switch moved above what it scopes.** The "since live tracking" toggle sat
  *between* the score gauges and the metrics, but drives both.
- **Orphaned 5th screen card.** An odd screen count left the last card beside an empty
  half-column; it now takes the full row with its list two-up, and the ETF screen shows
  4 rows so the 2×2 fills. The coupling is commented at both ends.
- **Dead second column.** `.report-two-column` stretched the short opportunity card down
  the full height of the projection panel next to it; now `align-items: start`.
- **Empty Market-pulse tiles** no longer render a `--fs-2xl` dash at the same weight as a
  real reading, and say "Not published in this run" rather than "Period unavailable".

Also fixed: `design/appshot.mjs` and `design/a11ycheck.mjs` passed `viewportSize` to
`newPage`, which is not an option there — **every screenshot and a11y check in the
redesign ran at the default 1280×720, not the 1440×1000 they claim.** Now `viewport`.

Specific known gaps:
- No shared screen-page skeleton, so 15+ screen routes each invent a layout.
- `InstitutionalActivity` ships `results: []` permanently and renders a blank
  table rather than explaining the 13F cadence.
- ~~Picks still shows 112 keys per row as 8 flat metric pills~~ **stale — already
  built.** Rereading `Picks.jsx`'s `ResearchCard`/`picksColumns` found the layered
  disclosure already exists: mobile cards show 4 headline metrics, an "expand"
  toggle reveals `MetricPills` + strengths/risks, and a "Full research" button
  opens the modal. Whoever wrote this note was looking at a state that's since
  changed, or looking at the wrong layer — leaving this struck rather than
  silently deleting it, since the note directly contradicted the code.

**`Portfolio.jsx` is now decomposed** (Phase 2d, below), so Phase 5's Portfolio
pass can work on one view at a time.

**Picks (started, infra fix only — visual/hierarchy pass not done).** Found while
starting Picks: `/research`'s default (non-model) sort renders the *entire*
scored universe — ~877 unfiltered stock rows — and `DataTable`'s desktop
`<table>` had no virtualization at all, only its mobile card path did. Confirmed
via measurement, not assumption: a Playwright check showed the mobile view
scrolling to **395,000px** of page height (correct, if extreme — its virtualizer
really does window the DOM, ~12-18 cards mounted at a time) while the desktop
table silently mounted **1,002 real `<tr>` elements** inside its own 72dvh
internal-scroll region on every load. The same gap was independently confirmed
on `FastGrowthScreen` (~880 rows), `CongressTrades` (up to ~1,160), and three
`ResearchScreen`-backed screens (~300 rows each) — five pages total, not just
Picks. Fixed at the shared `DataTable` level (below), not per-page.

**Picks — one real hierarchy fix, not a ground-up pass.** Unlike Dashboard,
Picks didn't need restructuring — it's a sophisticated, already-well-built page
(ranking models, a peer-relative allocation planner, style/sector tilt, entry
timing) with no dead weight or duplicated apparatus to remove. One genuine
`DESIGN.md`-adjacent problem found by screenshot, not assumption: the page's own
copy states its job as "Compare the ranked evidence behind every published
company," but the **Bucket planner** (a secondary what-if allocation tool, empty
until a dollar figure is typed in) rendered *above* the stock/ETF pools —
pushing every research card below the fold on every viewport. Measured on a
390px screenshot: scrolling a full screen height still left the reader inside
the planner's explanatory text, no company card visible yet. Fixed with a pure
JSX reorder (same components, same props, no logic changes) — the planner now
renders after the research pools and the empty-state, immediately before the
disclaimer. Verified: `npm run lint && npm test && npm run build` green (789
tests), `typefloor.mjs`/`a11ycheck.mjs` clean, before/after screenshots at
1440px and 390px in both themes confirming the first research card is now
visible after one scroll instead of one and a half. Also struck a stale gap
note in this doc (above) claiming Picks lacks layered metric disclosure — it
doesn't lack it, current code already has it.

**SwingScreen — one real bug, not a rebuild either.** Already well-built:
tiers → headline → collapsed methodology (its own in-code comments record two
prior hierarchy fixes — the methodology cards used to sit before the first
row, the coverage note used to sit between the filters and the table, both
already moved) → filters → column toggle → table. Screenshotted in both
themes at 1440px and 390px, no layout, contrast, or overflow problems found.
One real, confirmed bug: the closing disclaimer wrapped an `InfoTag` (renders
`<details>`) inside a `<p>` — `<details>` is not phrasing content, so the
browser's HTML parser implicitly closes the `<p>` the moment it hits it,
silently splitting the disclaimer into two untagged fragments and dropping
`.disclaimer`'s styling from the second half ("Rankings are hypotheses...").
Confirmed by a real `validateDOMNesting` React console warning (not a lint
rule — ESLint has no JSX-semantics check for this), and confirmed fixed by
querying the live DOM: one `<div class="disclaimer">` containing the full text
and the nested `<details>`, not two fragments. Switched `<p>` → `<div>`
(`.disclaimer` is a plain class selector, and this variant is already used in
`Picks.jsx`/`Methodology.jsx`, so not a new pattern). Verified: lint/test/build
green (789 tests, SwingScreen's own 37), `typefloor.mjs`/`a11ycheck.mjs` clean.

### Phase 2d — decompose the giants · PORTFOLIO DONE · SwingScreen/Picks reassessed, not decomposed
| File | Lines |
|---|---|
| ~~`src/pages/Portfolio.jsx`~~ | ~~1,288~~ → **233** (see below) |
| `src/pages/SwingScreen.jsx` | 789 |
| `src/pages/Picks.jsx` | 841 |

`Portfolio.jsx` is now a shell that loads data, derives the view models once, and
renders one of three views. Everything else moved to `src/pages/portfolio/`:

| | |
|---|---|
| `format.js` | money/percent formatters, period constants, `perShareCost` |
| `portfolioModels.js` | **pure** — `buildPriceModel`, `buildHoldingsModel`, `buildBenchmarkModel` |
| `portfolioAnalyticsModel.js` | **pure** — every `score*` statistic the Data overview renders |
| `usePortfolioForms.js` | the whole write path: add / edit / sell / remove / Fidelity sync |
| `PortfolioBits.jsx` | nav, `Move`, `StopLossNote`, sort toolbar |
| `Summary.jsx` / `Performance.jsx` / `DataOverview.jsx` | the three views |
| `Holdings.jsx`, `HoldingCard.jsx`, `ComparisonTables.jsx` | the holdings section |

Two things worth knowing:

- **Verified rather than assumed.** The rendered DOM of all three views was dumped
  from a real browser before and after (with every `<details>` forced open) and is
  **byte-identical**. 13 new unit tests cover the two pure model modules, which were
  untestable while they lived inside the component.
- **One deliberate non-cosmetic change.** `buildAnalyticsModel` — factor regression,
  deflated statistics, regime conditioning, the whole metric model — used to run on
  every portfolio route and was rendered only by Data overview. It is now gated on
  `view === 'data'`. Output is unchanged; Summary and Performance just stop paying
  for it.
- Cost: the Portfolio chunk grew 114.6 → 118.7 kB raw (+1.6 kB gzip) from module
  boundaries and prop plumbing.

Not yet gated: the `useData` fetches for `factors/french.json`,
`validation/signal_metrics.json` and the four ETF benchmark snapshots are also
Data-overview-only for the most part. `useData(null)` is a no-op, so gating them is
easy — but `candidateInputs` feeds the Performance view's benchmark *label*
fallback, so it is not a pure change and was left alone.

**`SwingScreen.jsx` and `Picks.jsx` were read in full while doing their Phase 5
passes, and deliberately not split.** Portfolio needed decomposition because it
bundled three distinct views (Summary/Performance/Data overview) with
duplicated logic behind one component — a structural problem line count was
just a symptom of. SwingScreen and Picks are long for a different reason: each
is one view with real domain complexity (SwingScreen: three horizon books,
per-leg evidence, verdict/strength derivations; Picks: ranking models, a
peer-relative allocation planner, style/sector tilt), already factored into
clear pure helper functions and small presentational components within the
file. Splitting either into multiple files to hit a line-count target, with no
duplicated-view problem to actually solve, would be exactly the kind of
abstraction-for-its-own-sake this project's own conventions warn against.
Treating this bullet as done, not skipped.

### Phase 4 remainder — one data gap, three metric groups needing methodology work
Not chart-building tasks; see §1's Phase 4 entry for the full breakdown.
- **Score-history line** (`StockDetailModal`) needs a pipeline change: a small
  per-row score-history series sized for the browser. Nothing today publishes
  one.
- **14 of `SignalMetricsPanel`'s 40 metrics** still show no bullet, correctly —
  3 need a semantic call (count-vs-threshold republishing), 2 need a
  structural field change (the compared quantity isn't `value`), 3 need real
  methodology work (`breakeven_gross_alpha`'s comparator doesn't exist yet;
  `quantile_spread`/`alpha_cost_crossover` have no numeric form), and 2 have a
  computable-but-unpublished bound that's lower priority while the live
  sample is young.

### Phase 6 — dead code + payload + motion pass + rubric rescore — all DONE (see §1)
Nothing left in Phase 6. Two gaps the rescore surfaced but deliberately left open,
for a future session: `DataTable`'s desktop `<table>` path has no virtualization for
very large row counts; `*card*`-family CSS class names grew to 59 and would benefit
from a consolidation pass.

### Smaller
- `og:image` and `og:url` in `index.html` are root-relative because the deploy
  domain is not in this repo. Facebook and Twitter want absolute URLs.

---

## 3. Bugs found and fixed (context for why things changed)

Worth knowing so nobody "restores" them:

1. **No card in the app had elevation.** A third stylesheet pass set
   `.card { box-shadow: none }` app-wide, overriding both earlier definitions,
   regardless of the surface preference.
2. **Every accent was unreadable in dark mode.** All 8 shipped `ink: #ffffff` for
   both themes; filled accent surfaces sat at **1.55–2.11:1**. Each accent now
   carries a separate `inkDark` clearing 8.9:1.
3. **Chart palettes failed CVD.** A deuteranope could not distinguish
   `--series-benchmark` from `--series-benchmark-2` (ΔE **3.1** light, **1.5**
   dark). The 11 sector hues failed at ΔE 2.4 with 9 of 11 below the chroma
   floor. Constant-lightness hues cannot pass at 11 slots — CVD collapses hue and
   leaves only lightness — so the replacements alternate lightness across
   adjacent slots. All four palettes now pass every check.
4. **`--shadow-card` is referenced twice and defined nowhere**, so `.result-card`
   and the four `.alert-*` panels silently rendered flat.
5. **A 15-column sortable table was `display:none !important` on every viewport**
   — 111 lines of dead DOM in Portfolio, plus its orphaned `SortableHeader`.
6. **Synthesized font weights** — 650–800 used, only 400/500/600 loaded.
7. `.watchlist-card` had `border-radius: 23px`; `.analysis-layer-card` 10px.

---

## 4. How to work on this

### Where things live
| | |
|---|---|
| Tokens | `src/styles/variables.css` — **every** colour, size, space, radius, shadow |
| Stylesheet entry | `src/styles/index.css` → 11 modules in `src/styles/modules/` |
| Design constitution | `DESIGN.md` (root) |
| Direction record | `design/direction-approved.md`, reference `design/directions/D-approved.html` |
| Table system | `src/components/DataTable.jsx`, `src/lib/dataTableSort.js` |
| Dialog behaviour | `src/lib/useDialog.js` |
| Portfolio views | `src/pages/Portfolio.jsx` (shell) → `src/pages/portfolio/` |

### Load-bearing constraint
**The 11 CSS modules are imported in the original source order and the cascade
depends on it.** Each file's header says so. Moving a rule between modules
without checking what it overrides will cause silent visual regressions.

### Accent tokens are set inline
`--brand-primary`, `--accent`, `--accent-ink` are written onto `:root` by
`src/lib/PreferencesContext.jsx`. A stylesheet rule can never beat them. Change
accents in `ACCENTS` there. `--brand-secondary` / `--accent-dim` / `--series-stock`
now *derive* from `--brand-primary` in CSS via `color-mix`, so a new accent needs
one value per theme, not three.

### Verification loop
```bash
npm run lint && npm test && npm run build     # must all pass

npx vite --port 5175 --strictPort              # the port all three scripts assume
node design/appshot.mjs                        # ROUTES='[["/","home"]]' TAG='x-' to target
node design/a11ycheck.mjs                      # keyboard + modal + unnamed-control check
node design/typefloor.mjs                      # 11px floor, DOM *and* scaled SVG; exits 1 on breach
```
All three hardcode a Playwright path from the npx cache — fix it if that moves.
Add `?portfolioPreview=1` to any portfolio-bearing route or it renders its empty
state locally (Firebase is offline; see below).

### Local dev caveats
- **Firebase is offline locally**, so Portfolio, Diversification and Finances
  render their empty states. The correlation heatmap therefore **cannot be
  visually verified in-app locally** — its 6 unit tests and the Phase 0 mockups
  cover it. Console "Cloud session was unavailable" errors in screenshots are
  expected and unrelated to the redesign.
- **Two pipeline tests fail on `main` and did so before the redesign**
  (`test_benchmark_suite.py::...spy_cagr...` and
  `test_themes.py::...theme_definition_loads...`). Verified against `c51fc08a`.
  The redesign touched no pipeline code. Do not chase them as regressions.

### Repo housekeeping
The 250 files of installed `.claude/skills` bundles were untracked during the
redesign, then **committed by the user in `c341eafe`** — so they are tracked on
purpose now. ESLint ignores `.claude/**` and `design/**`
(`eslint.config.js`); without that, the vendored skill scripts put 327 errors in
front of the `site` CI job.

### Rules that must hold
From `DESIGN.md` — a change that breaks one of these is a regression:
- No text below 11px, anywhere, including SVG labels.
- No raw hex, px font-size, or px spacing outside `variables.css`.
- One accent; gray carries structure.
- `positive`/`negative`/`warning` are state, never series colours, never
  colour-alone.
- Two elevation levels only; shadows tinted toward the surface hue.
- Published research scores are never plotted on a bare 0–100 axis (they span
  ~9.6 points, so the distribution disappears).
- Every chart offers a table view.
