# ValueSignal UI Redesign Plan

> **⚠️ Execution status: see `docs/REDESIGN-STATUS.md` first.**
> Phases 0, 1 and 3 are complete and merged; 2 and 4 are partial; 5 is not started.
> That file also records four corrections to this plan — including a stale
> dead-component list in Appendix A that will break the build if followed.


**Status:** ready to execute · **Authored:** 2026-08-15 by Claude Fable 5 (audit + planning pass)
**Executor:** Claude Opus sessions in this repo, one phase per session (phases 1–3 may share a session)
**Scope:** frontend only (`src/`, `index.html`). No pipeline, schema, or `public/data/*` changes.

---

## How to execute this plan (read first, every session)

1. **25 skills are installed in `.claude/skills/`** (full roster with roles in Appendix B): the core four — **impeccable**, **taste**, **redesign**, **huashu-design** — plus the awesome-frontend-skills batch (**interface-design**, **improve-ui**, **frontend-design**, **better-ui**, **rams**, **web-design-guidelines**, **improve-animations**, **improve-react**, and more), the project's existing **ui-ux-pro-max**, and the built-in **dataviz** skill. **With this many skills installed, discipline matters: load ONLY the skills the current phase names, at the start of the phase.** Loading overlapping design skills simultaneously produces conflicting instructions — the phase's "Load:" line is the allowlist. When in doubt, `ui-skills-root` exists to route to the smallest useful set.
2. Work on a branch (`redesign/phase-N-<slug>`), small reviewable commits. Never commit directly to `main`.
3. After every phase: `npm run lint && npm test && npm run build` must pass. Component tests exist for many files you will touch (`Foo.jsx` + `Foo.test.jsx` colocated) — update tests with the code, never delete a test to make it pass.
4. **Phase 0 ends the session and waits for the user's choice.** Do not proceed past a STOP gate on your own, even in an autonomous session.
5. The audit findings below carry file/line references gathered on 2026-08-15. Re-verify a reference before editing if the file has since changed.

### Hard guardrails (apply to every phase)

- **Keep the token architecture.** All theming flows through CSS custom properties in `src/styles/variables.css` + `data-*` attributes on `<html>` set by `src/lib/PreferencesContext.jsx`. Extend tokens; never bypass them.
- **Accent colors are set inline on `:root` by PreferencesContext** (`--brand-primary`, `--accent`, `--series-stock`, …). A stylesheet rule can never win against that. Any accent-related change goes through `ACCENTS` in `PreferencesContext.jsx`.
- **No chart library.** Every chart is hand-rolled SVG that inherits theme tokens (see comment in `GrowthChart.jsx`). This is deliberate and stays. New charts are plain SVG/HTML using tokens.
- **No framework/styling migration.** Plain CSS stays plain CSS. No Tailwind, no CSS-in-JS, no component library.
- **Preserve the good parts:** global `:focus-visible` outline + `.skip-link`; `input/select/textarea { font-size: 16px }` iOS anti-zoom rule; the three `prefers-reduced-motion` blocks + user motion preference; 44px mobile touch targets; the anti-FOUC inline script in `index.html`; `MobileSheet`'s correct dialog semantics; `validatePreferences` schema migration.
- **Don't invent data.** Every number shown must come from the committed JSON. `docs/MODEL-CARD.md` and `docs/LIMITATIONS.md` govern claims — no new copy that overstates what the score means.
- **Operate mode.** Per impeccable's modes, every surface here is *Operate* (task completion: scanability, consistency, density) — not *Persuade*. The `redesign` skill's marketing-page advice (double whitespace, break symmetry, background imagery) does **not** apply to data screens; its typography/color/state checklists do. The `taste` skill self-describes as "not dashboards" — use it only for its typography bias-correction, dark-mode protocol, and pre-flight discipline.

---

## Audit summary (impeccable 5-dimension rubric)

| # | Dimension | Score /4 | Key finding |
|---|-----------|----------|-------------|
| 1 | Accessibility | 2 | Main modal has no dialog semantics; 59 unlabeled inputs; 155 CSS rules at ≤9px text |
| 2 | Performance | 2 | 37 MB `advisor.json` fetched by Search/Watchlist/Finances; 31 MB `score-history.json` shipped and never read |
| 3 | Responsive | 3 | Solid mobile nav/sheets/virtualization, but content hidden via `clip` hack and `!important` table suppression |
| 4 | Theming | 3 | Real token system with dark mode across all charts; leaks: ~20 hardcoded colors, ~340 inline styles, override-layer CSS |
| 5 | Implementation integrity | 2 | ~⅓ of `src/components/` dead; 31 `*card*` classes; no type or spacing scale; second stylesheet layered over the first |
| | **Total** | **12/20** | **Acceptable — significant work needed, foundation worth keeping** |

### The five structural problems (everything else hangs off these)

1. **`global.css` is two stylesheets in one file.** Lines ~1178+ (`/* ValueSignal application frame */`, `/* Second-pass financial report... */`) re-declare `.card`, `.card-pad`, form controls, etc. already defined near line 122. The last ~1200 lines patch the first ~1200, which is why there are 30 `!important`s (e.g. `.portfolio-table { display:none !important }` at ~line 1970).
2. **No typographic scale.** 30+ font sizes, including 7/8/9/9.5/10.5/11.5/12.5px. The single most common size in the app is **9px (120 occurrences)**; 155 rules sit at ≤9px, mostly in `--text-tertiary` (#7a838c) — a legibility and WCAG AA problem at once.
3. **No spacing scale.** 34 distinct px values in padding/margin/gap including 7, 9, 11, 13, 17, 19. Tokens (`--card-padding`, `--section-gap`) exist and are bypassed constantly.
4. **Dead third.** 16 unimported components (~2,000 of 6,316 lines), including three *good* visualizations (`ResearchRadarChart`, `ProjectionFanChart`, `ScoreExplainability`) and a mobile card system (`StockCard`/`StockCardGrid`). Also unused: `score-history.json` (31 MB), `diagnostics.json` (4.9 MB), the Bricolage Grotesque font loaded in `index.html` but referenced by nothing, `.dashboard-widget-grid`/`.widget-*` CSS for a layout that no longer exists.
5. **Rich data, poor encodings.** A pairwise correlation matrix rendered as a raw `<table>`; 40 validation metrics each carrying `value` + `kill_threshold` + `breached` rendered as text; 10 shadow strategies × 6 risk stats with no chart; a quadrant classification (`quality company / wait / high-conviction / avoid / tactical-only`) in `earnings-timeliness.json` that is literally a scatter plot stored as JSON; 112 keys per research row rendered as 8 metric pills.

Positives to keep are listed in the guardrails. Full page/component inventory is in the appendix.

---

## Phase 0 — Visual direction gate (huashu-design) · STOP GATE

**Load:** `huashu-design` + `frontend-design` (Anthropic's aesthetic-direction guidance, applied while authoring the drafts) + `interface-design` (dashboard-specific craft constraints so drafts stay Operate-mode honest).
**Why:** huashu's core rule — any task producing a new visual design gets **three differentiated direction drafts as real rendered HTML, then the user chooses**. The current identity ("institutional cool-gray + deep green, flat, dense, mono numerals") is decent; the user must decide whether the redesign *refines* it or *replaces* it.
**Alternative process:** if the user prefers interview-driven exploration over three fixed directions, `design-lab` runs a structured interview and generates five variants in a temporary lab — offer it once, default to huashu's three-direction gate.

**Do:** Build three standalone HTML mockups (in `design/directions/`, not routed) of the **Dashboard** — the cold-open page — each also showing one table screen fragment (Picks) and one chart-heavy fragment (Diversification-as-heatmap), light + dark. Use real values copied from `public/data/report.json`. Three genuinely different interpretations that all keep the Operate-mode density, e.g.:

- **A. Refined incumbent** — keep cool-gray + deep green/mint identity, fix scale/hierarchy, flat outlined surfaces. Lowest risk.
- **B. Terminal editorial** — near-mono palette, one accent, heavier display type for headline numbers, hairline rules instead of card borders; Bloomberg-meets-print.
- **C. Soft-depth analytics** — subtle elevation (`data-surface="elevated"` becomes default), tinted shadows, larger radii, calmer density; Linear/Stripe-dashboard feel.

Each draft ships with a palette strip and a one-line positioning statement (huashu's 方向板 format).

**Done when:** three drafts + screenshots presented. **STOP — end the session; the user picks a direction (or asks for a mix).** Record the choice verbatim in `design/direction-approved.md`; later phases read it.

**Immediately after approval (start of the Phase 1 session):** run `create-design-md` to write a `DESIGN.md` capturing the chosen system — tokens, type scale intent, surface treatment, chart conventions — from the approved draft + existing code. Every later phase treats `DESIGN.md` as the visual constitution (impeccable's `document`/`doctor` machinery reads it too).

---

## Phase 1 — Foundations: scales, stylesheet rebuild, dead-code purge

**Load:** `redesign` skill (its audit checklists) + impeccable `reference/typeset.md` and `reference/layout.md` + `taste` §4.1–4.2 (typography/color calibration). `baseline-ui` is the quick per-file deslop checklist while migrating rules to the new scales.

### 1a. Type scale
Define in `variables.css` a real scale as tokens, e.g. `--fs-2xs: 11px` (hard floor), `--fs-xs: 12px`, `--fs-sm: 13px`, `--fs-base: 14px`, `--fs-lg: 16px`, `--fs-xl: 20px`, `--fs-2xl: clamp(24px…)`, `--fs-num-hero` for headline figures. Migrate every `font-size` in `global.css` to the nearest token. **The 7–10px cluster (th, `.eyebrow`, `.card-kicker`, `.metric-status`, `.rail-note`, sublabels) moves to ≥11px**; where uppercase+tracking made 9px "work", keep the treatment at 11px. Numbers stay IBM Plex Mono `tabular-nums`. Delete the Bricolage Grotesque `<link>` from `index.html` (dead payload) — unless the chosen Phase-0 direction adopts it, in which case wire it into `--font-display` properly.

### 1b. Spacing scale
Token scale `--sp-1: 4px` … `--sp-8: 32px` (+`--sp-10/12` for page gutters). Snap all 34 ad-hoc values to it; odd values (7/9/11/13/17/19px) round to the grid. Keep `data-density` overrides working by expressing `--card-padding`/`--section-gap`/`--row-height` in the new scale.

### 1c. Rebuild `global.css` as layered files
Split into `src/styles/` modules imported in order from a single entry: `variables.css` → `base.css` (reset, typography, a11y helpers) → `layout.css` (shell, rail, mobile nav) → `components.css` (cards, tables, controls, pills) → `charts.css` → `pages/*.css` (only truly page-specific rules). **Collapse the "second-pass" override layer into the primary definitions** — one `.card`, one form-control block. Target: zero non-reduced-motion `!important`s; the `.portfolio-table { display:none !important }` hack is resolved by actually removing/branching the markup it suppresses. Replace the ~20 hardcoded hex/rgba colors with tokens (add `--shadow-1`/`--shadow-2` tinted-shadow tokens per the chosen direction; `redesign` skill: tint shadows toward the surface hue, never pure black).

### 1d. Dead-code purge
Delete (git keeps history): `AnalysisLayers`, `DataFreshnessIndicator`, `DataQualityDebugView`, `ETFComparisonPanel`, `MetricCard`, `MetricSections`, `PortfolioChartOverlay`, `PortfolioReturnSummary`, `RecommendationShadowPanel`, `ScoreBandView`, `StockCard`, `StockCardGrid` + their tests + their orphaned CSS (`.dashboard-widget-grid`, `.widget-*`, `.brand-sub`, …). **Keep and shelve for Phase 4:** `ResearchRadarChart`, `ProjectionFanChart`, `ScoreExplainability`, `ETFComparisonChart`. Extract the duplicated `useMediaQuery` (in `GrowthChart.jsx` and `MarketHeatmap.jsx`) to `src/lib/useMediaQuery.js`.

**Done when:** all font sizes and spacing values are tokens; `global.css` gone, modules ≤ ~500 lines each; zero layout `!important`s; dead components removed; `npm run lint && npm test && npm run build` green; visual smoke-check of Dashboard/Portfolio/Picks light+dark shows no regression beyond the intended scale changes.

---

## Phase 2 — Component consolidation

**Load:** impeccable `reference/distill.md` + `reference/extract.md`. Before decomposing, run `improve-react` (React Doctor scan) once over `src/` — its findings (re-render hotspots, effect misuse, state placement) decide *where* the seams go in the Portfolio/Swing/Picks splits; it plans, the split commits execute.

1. **One card.** Replace the 31 `*card*` class variants with a single `.card` base + modifier classes (`.card--stat`, `.card--flush`, `.card--interactive`) driven by tokens. Page-level card classes may remain only as *layout* hooks (grid placement), never restyling padding/border/radius.
2. **One table system.** Today three strategies coexist: raw `<table>` (13 files), `ResultCards`, `MobileVirtualList`. Build `DataTable` (wrapping the sortable-header pattern from `Picks.jsx`/`SwingScreen.jsx`) that renders: semantic `<table>` on desktop, and at the mobile breakpoint delegates to `ResultCards` (short lists) or `MobileVirtualList` (≥50 rows) automatically. Migrate Picks, SwingScreen, ResearchScreen, StrategyScreen, CongressTrades, InstitutionalActivity, FastGrowthScreen, ShadowPortfolios, BacktestComparison, Diversification, Portfolio tables to it.
3. **Decompose the giants.** `Portfolio.jsx` (1,422 lines, three views) → `portfolio/Summary.jsx`, `portfolio/Performance.jsx`, `portfolio/DataOverview.jsx` + shared hooks. `SwingScreen` (839) and `Picks` (816) each split view components from data/sort logic. Pure refactor — behavior and tests preserved.
4. **Inline-style diet.** ~340 `style={{}}` sites → keep only computed values (bar widths, `order`, chart geometry); everything static moves to classes. Worst offenders first: `Finances.jsx` (46), `Portfolio.jsx` (32), `Bits.jsx` `Loading`/`Empty`, `Dashboard.jsx:407`.
5. **Navigation debt:** add `/screens/shadow` and `/screens/early-session` to a nav group; link or retire `/market` (PolicyRadar) — it is currently reachable only by URL.

**Done when:** one card base, one table entry point, no page file >500 lines, inline styles only where computed, orphan routes resolved, suite green.

---

## Phase 3 — Accessibility & hardening

**Load:** impeccable `reference/harden.md` + `fixing-accessibility` (the working checklist: ARIA, keyboard, focus, contrast, forms) + `ui-ux-pro-max` accessibility/touch sections. Verification pass at the end: `rams` per changed file (WCAG findings with line numbers) and `web-design-guidelines` for the compliance sweep.

P0s (fix before any visual polish ships):
1. **`StockDetailModal.jsx` (~line 192):** adopt `MobileSheet`'s existing correct pattern — `role="dialog"`, `aria-modal`, `aria-labelledby`, focus trap, Escape to close, focus restore on close. The correct code already lives in this repo; reuse it.
2. **59 unlabeled inputs:** every filter/search/toolbar input gets `id`+`htmlFor` or `aria-label`. `Settings.jsx`'s `SelectRow` shows the house pattern.
3. **Contrast:** after the Phase-1 type scale, run a contrast pass on `--text-tertiary`/`--text-faint` on all surfaces (both themes, all 8 accents for accent-on-surface text like `.value-capsule`). Adjust token values, not per-site colors.
4. **Mobile clip-hack** (`.analytics-counts small` hidden inside a media query): reflow the content instead of hiding it.
5. **Chart a11y:** fix `ResearchRadarChart`'s contradictory `aria-hidden` + `figure aria-label` when revived; give `MarketHeatmap`/`AllocationDonut` a real fallback — each chart gets a "view as table" affordance (dataviz skill requirement) instead of a paragraph-length `aria-label`.

**Done when:** keyboard-only walkthrough of Dashboard → Picks → StockDetailModal → Settings completes without traps; axe/devtools contrast check passes AA on both themes; suite green.

---

## Phase 4 — Data-visualization program

**Load:** built-in `dataviz` skill (mandatory, before any chart code) + shelved components from Phase 1d. Follow its procedure per chart: pick the form → color by job → **validate the palette with `scripts/validate_palette.js` for light AND dark surfaces** (surfaces: `#ffffff`/`#f4f5f7` and `#131a16`/`#090D0B`) → mark specs → hover layer → legend/table fallback. Categorical hues in fixed order; one axis, never dual; diverging = two hues + neutral gray midpoint; status colors (`--positive`/`--warning`/`--negative`) never used as series colors.

First: **validate the existing palettes** (11 sector colors, 4 series colors, both themes) and snap any failing step to a passing one *in the tokens*, so every chart inherits the fix.

Build order (each item = one commit, reusing `GrowthChart`/`Sparkline` conventions — SVG, tokens, `useMediaQuery`):

| # | Where | New encoding | Data (already shipped) |
|---|-------|--------------|------------------------|
| 1 | `Diversification` | **Correlation heatmap** (diverging, gray midpoint at 0, cell hover, table toggle) replaces the raw `<td>` matrix | `report.json` pairwise correlations |
| 2 | `Diversification` | Factor-exposure **bar chart** (loadings ±, diverging around 0) + optional rolling line | `factors/french.json` (756 monthly obs) |
| 3 | `SignalMetricsPanel` | **Bullet charts**: value vs `kill_threshold`, `breached` flagged with icon+label (status treatment, never color-alone) — 40 metrics grouped by `group` | `validation/signal_metrics.json` |
| 4 | `ShadowPortfolios` | **Risk/return scatter** (CAGR vs max drawdown, point = strategy, direct labels) + sortable stat columns retained | `screens/shadow-portfolios.json` |
| 5 | `BacktestComparison` | **Dot-plot small multiples** across the 15 methods (one panel per stat, shared scale per panel) | `screens/backtest-comparison.json` |
| 6 | `LiveValidation` | Champion-vs-challenger **paired bars** across 1M/3M/6M/12M horizons | `validation/ic_validation.json` |
| 7 | `StrategyScreen`/`OptionsScreen` | Backtest **stat-tile row** (hero numbers per dataviz stat-tile spec) + one cross-strategy comparison dot plot | `screens/*-backtest.json` |
| 8 | `ResearchScreen` (earnings, matrix) | **Quadrant scatter** — the JSON already classifies rows into `quality company / wait / high-conviction candidate / avoid / tactical-only`; draw the two scoring axes, color by quadrant (categorical), click-through to `StockDetailModal` | `screens/earnings-timeliness.json`, `structural-tactical.json` |
| 9 | `StockDetailModal` | Revive **`ResearchRadarChart`** (8 fundamental categories) + **`ScoreExplainability`** factor bars; add score-history line from the row's own `history`/`analytics_history` (do **not** fetch the 31 MB `score-history.json` in the browser) | `advisor.json → research[]` (112 keys/row) |
| 10 | `Planning` | Revive **`ProjectionFanChart`** (p10–p90 bands) as the projection visual | already-computed percentiles |
| 11 | `CongressTrades` | Monthly **volume timeline** + top-politicians/top-issuers bars above the table | `screens/congress-trades.json` (1,162 rows) |
| 12 | `MarketPulsePreview` + `ThemeExposureScreen` | Macro-regime **mini bullet trio** (rates/inflation/labor 0–100); theme **signal-contribution bars** (weighted `signals`, `leading` flagged) | `report.json → market.macro`, `theme_screen` |

Every chart: crosshair/tooltip hover layer, legend when ≥2 series, `data-chart-*` preference attributes respected, reduced-motion honored, renders correctly on both themes **by token inheritance, verified by screenshot**.

**Done when:** all 12 shipped with table fallbacks; palette validator passes both modes; check each against dataviz `references/anti-patterns.md`; suite green.

---

## Phase 5 — Page-by-page application of the chosen direction

**Load:** `design/direction-approved.md` + `DESIGN.md` + `interface-design` (the dashboard/SaaS craft skill — primary companion for this phase) + impeccable `reference/craft-floor.md` (immediately before editing UI) + `reference/layout.md`. Per-page workflow: `improve-ui` audits the page against `DESIGN.md` and writes the work order; the same session executes it; `better-ui` is the detail-polish checklist (optical alignment, borders, shadows, icon consistency) before each page's commit.

Apply the Phase-0 direction across pages in traffic order, using the Phase-1 tokens and Phase-2 components — this phase is *composition*, not new systems:

1. **Dashboard** — hierarchy pass: one clear headline number per widget (dataviz hero-number spec), consistent widget chrome, `FocusedScreenCard` grid aligned to the card system.
2. **Portfolio** (all three views) — the money pages; table density, `PerformanceMetrics` layout, move-explanation readability.
3. **Picks / research library** — the 112-keys-per-row problem: layered disclosure (pills → expandable evidence → modal), consistent tier/rating/action badge language.
4. **SwingScreen + screens family** — unified screen-page template: title/KPI strip/filters/DataTable/evidence panel, so all 15+ screen routes share one skeleton.
5. **Finances, Planning, Insights, Watchlist, Markets** — apply template + Phase-4 charts.
6. **Methodology, Glossary, Settings, Alerts** — *Read*-mode typography (impeccable `operate.md` covers Read-in-app), Settings grouped with the house `SelectRow` pattern.
7. **Empty/edge states** (impeccable `onboard.md`): `InstitutionalActivity` currently ships `results: []` permanently — design a real "no current data" state explaining why (13F cadence), not a blank table. Same for logged-out portfolio, empty watchlist, `EarlySessionResearch` gate.

**Done when:** every routed page uses the shared skeleton/tokens; no page-specific font sizes/spacings outside the scales; screenshots of all pages in light+dark reviewed against the approved direction.

---

## Phase 6 — Polish, performance, rescore

**Load:** impeccable `reference/polish.md` + `reference/audit.md`.

1. **Perf:** investigate slimming the 37 MB `advisor.json` dependency in `Search`/`Watchlist`/`Finances` — if `report.json` (6.5 MB) or a per-page slice covers their fields, switch; if it requires a pipeline change, write the finding to `TODO.md` and stop (out of scope). Confirm `MobileVirtualList` thresholds; check bundle for accidental heavy imports (`npm run build` chunk report).
2. **Motion pass, plan-then-execute:** run `improve-animations` (read-only motion audit → prioritized plans), review its plans against `12-principles-of-animation`'s rubric and the restraint rules (impeccable `animate.md`: 150–350ms token durations, transform/opacity only, staggered entry on card grids at most), then execute the accepted plans with `interaction-design` for the microinteraction details and `fixing-motion-performance` as the perf checklist. `data-motion` and `prefers-reduced-motion` always respected.
3. **Metadata pass** (`fixing-metadata`): `index.html` currently ships minimal meta — add proper title/description, theme-color (already dynamic), favicon set, and Open Graph/Twitter tags for the deployed site.
4. **Re-run the Phase-audit:** score the five dimensions again against the rubric in this file (`rams` + `web-design-guidelines` as independent checkers). **Target ≥17/20**, with Accessibility ≥3 and Implementation integrity ≥3.
5. Final `npm run lint && npm test && npm run build`, plus `npm run docs:breakdown` to regenerate the component breakdown doc.

---

## Appendix A — dead components inventory (Phase 1d source list)

Unimported as of 2026-08-15: `AnalysisLayers`, `DataFreshnessIndicator`, `DataQualityDebugView`, `ETFComparisonChart`, `ETFComparisonPanel`, `MetricCard`, `MetricSections`, `PortfolioChartOverlay`, `PortfolioReturnSummary`, `ProjectionFanChart`, `RecommendationShadowPanel`, `ResearchRadarChart`, `ScoreBandView`, `ScoreExplainability`, `StockCard`, `StockCardGrid`. (Several have passing tests — tests don't make them alive.) Revive list: `ResearchRadarChart`, `ProjectionFanChart`, `ScoreExplainability`, `ETFComparisonChart`; delete the rest.

## Appendix B — installed skill roster and roles

**Load discipline:** phases name their skills; never load the whole roster. Roles:

| Skill | Source | Role in this plan |
|---|---|---|
| `impeccable` | pbakaus/impeccable | Backbone: audit rubric, per-phase playbooks (`typeset`, `distill`, `harden`, `craft-floor`, `polish`, `animate`). Its `critique`/`delight`/`overdrive` commands from the skills.sh listing are playbooks *inside* this skill, not separate installs |
| `huashu-design` | alchaincyf/huashu-design | Phase 0 three-direction gate + critique guide |
| `interface-design` | Dammyjay93/interface-design | Phase 0 + 5: dashboard/SaaS-specific craft — the closest-fit skill for this app |
| `frontend-design` | anthropics/skills | Phase 0 + 5: aesthetic direction, anti-generic choices |
| `design-lab` | 0xdesign/design-plugin | Phase 0 alternative: interview → five variants → feedback |
| `create-design-md` | ibelick/ui-skills | Post-approval: write `DESIGN.md` from the chosen direction |
| `redesign` | Leonxlnx/taste-skill | Phase 1 checklists (typography/color/states) + fix-priority ordering |
| `taste` | Leonxlnx/taste-skill | Phase 1 §4.1–4.2 bias correction + dark-mode protocol only (self-scoped: not for dashboards) |
| `baseline-ui` | ibelick/ui-skills | Phase 1 quick per-file deslop pass |
| `improve-react` | millionco/react-doctor | Phase 2: React Doctor scan guides the big-file decomposition |
| `improve-ui` | ibelick/ui-skills | Phase 5: per-page audit against `DESIGN.md`, writes the work order |
| `better-ui` | jakubkrehel/skills | Phase 5: detail polish — optical alignment, borders, shadows, icons |
| `fixing-accessibility` | ibelick/ui-skills | Phase 3 working checklist |
| `rams` | rams.ai | Phase 3 + 6 verification: per-file WCAG/visual findings with line numbers |
| `web-design-guidelines` | antfu/skills | Phase 3 + 6 verification: Web Interface Guidelines compliance sweep |
| `dataviz` | built-in | Phase 4: chart forms, palette validator, anti-patterns |
| `improve-animations` | emilkowalski/skills | Phase 6: read-only motion audit → prioritized plans |
| `12-principles-of-animation` | raphaelsalaja/skill | Phase 6: motion review rubric |
| `interaction-design` | wshobson/agents | Phase 6: microinteraction implementation patterns |
| `fixing-motion-performance` | ibelick/ui-skills | Phase 6: animation perf checklist |
| `fixing-metadata` | ibelick/ui-skills | Phase 6: title/OG/favicon/meta pass |
| `improve` | shadcn/improve | Optional wrap-up: whole-codebase advisor for the post-redesign roadmap |
| `ui-skills-root` | ibelick/ui-skills | Router when unsure which skill fits |
| `ui-ux-pro-max` | pre-existing in repo | Phase 3 a11y/touch sections; style/palette search reference |
| `bencium-innovative-ux-designer` | bencium/bencium-marketplace | Reserve: alternative aesthetic-direction voice for Phase 0 drafts |
| `gpt-tasteskill` | Leonxlnx/taste-skill | **Not used** — GSAP/AIDA marketing-page constraints conflict with Operate mode; installed for completeness |

**Deliberately not installed:** the `shadcn` skill (shadcn-ui workflow) — this app has no shadcn/ui and the guardrails forbid component-library migration; installing a skill that steers toward adding components would fight the plan.

## Appendix C — key file references

- Tokens: `src/styles/variables.css` (189 lines, light/dark/density/corners/surface/contrast)
- Stylesheet: `src/styles/global.css` (2,403 lines; second-pass layer begins ~line 1178; `.portfolio-table` suppression ~line 1970)
- Theming controller: `src/lib/PreferencesContext.jsx` (localStorage `valuesignal.ui-preferences.v1`, schema v5, 8 accents inline on `:root`)
- Shell/routes: `src/App.jsx` (307 lines; orphan routes `/screens/shadow`, `/screens/early-session`, `/market`)
- Giants: `src/pages/Portfolio.jsx` (1,422), `src/pages/SwingScreen.jsx` (839), `src/pages/Picks.jsx` (816)
- Charts: `src/components/GrowthChart.jsx` (354, the conventions to follow), `Sparkline.jsx`, `MarketHeatmap.jsx`, `AllocationDonut.jsx`, `ScoreGauge.jsx`
- Modal to fix: `src/components/StockDetailModal.jsx` (~line 192); correct pattern in `src/components/MobileSheet.jsx`
