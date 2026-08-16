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

### Phase 4 — charts (partial) ⚠️
- **All four chart palettes validated** with the dataviz validator and fixed in
  the tokens. Three failed. See §3 for the details — they were real bugs.
- **`CorrelationHeatmap`** replaces the raw `<td>` matrix on Diversification:
  diverging scale, neutral gray at zero, value printed in every cell, per-cell
  accessible name stating the number *and its meaning in words*, live-region
  hover readout, and a table view carrying the same numbers.

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

---

## 2. What is left

Ordered by value. Everything below is also summarised in `TODO.md`.

### Phase 5 — page-by-page pass · DASHBOARD + PORTFOLIO DONE · rest not started
Per the plan, in traffic order: ~~Dashboard~~ → ~~Portfolio~~ → Picks → SwingScreen +
screens family → Finances/Planning/Insights/Watchlist/Markets →
Methodology/Glossary/Settings/Alerts → empty states.

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
- Picks still shows 112 keys per row as 8 flat metric pills — the layered
  disclosure (pills → expandable evidence → modal) is not built.

**`Portfolio.jsx` is now decomposed** (Phase 2d, below), so Phase 5's Portfolio
pass can work on one view at a time. That is the next page in traffic order.

### Phase 2d — decompose the giants · PORTFOLIO DONE
| File | Lines |
|---|---|
| ~~`src/pages/Portfolio.jsx`~~ | ~~1,288~~ → **233** (see below) |
| `src/pages/SwingScreen.jsx` | 839 |
| `src/pages/Picks.jsx` | 816 |

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

`SwingScreen.jsx` and `Picks.jsx` are unchanged. The plan suggests running
`improve-react` first to decide where their seams go.

### Phase 2e — inline-style diet
**167 sites** remain, down from ~340. Keep computed values (bar widths,
`--widget-order`, chart geometry); move static ones to classes.
Worst offenders: `Finances.jsx` 30, `Portfolio.jsx` 23, `StockDetailModal.jsx` 16,
`GrowthChart.jsx` 15, `Methodology.jsx` 10, `Insights.jsx` 10.

### Phase 4 — 10 charts unbuilt
All have their data shipped. In the plan's build order, minus the blocked one:
risk/return scatter (ShadowPortfolios), dot-plot small multiples
(BacktestComparison), champion-vs-challenger paired bars (LiveValidation),
stat-tile row + comparison dot plot (Strategy/OptionsScreen), quadrant scatter
(ResearchScreen — the JSON already classifies rows), radar + factor bars +
score-history line (StockDetailModal), projection fan (Planning), congress volume
timeline, macro bullet trio + theme signal bars.

**Load the `dataviz` skill before writing any chart code**, and re-run its
palette validator for any new colour. Do not fetch the 31 MB `score-history.json`
in the browser — the modal's row already carries `history`/`analytics_history`.

### Phase 6 — perf, motion, rescore
- **Payload.** `advisor.json` 37 MB across 11 pages (see correction #3). Check
  whether `report.json` (6.5 MB) covers their fields; if it needs a pipeline
  change, that is out of scope — write the finding down and stop.
  `score-history.json` (31 MB) and `diagnostics.json` (4.9 MB) are committed and
  read by nothing.
- **Nine unreachable lib files** (~2,020 lines) awaiting a keep-or-delete call:
  `evidenceStrength` (205), `fidelityConnectorStub` (342, deliberate stub),
  `labelDistribution` (146), `nightlyRefresh` (32), `pipelineGuardrails` (330),
  `scoreBands` (159 — **keep**: CLAUDE.md cites its test as the example command),
  `securityStub` (266, deliberate stub), `sentimentEngine` (395),
  `usePortfolio` (145).
- **Motion pass** — not started.
- **Rubric rescore** — not done. Dimensions 1, 2 and 5 have measurably improved;
  score it properly at the end.

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
