# DATA-INVENTORY.md

Phase 0d deliverable. Plain-language meaning, unit, cadence, level/rate/delta, which uncertainty
kind applies, its state source, and the decision it informs — for every published data file the
frontend consumes. Ambiguities marked `UNCLEAR`.

> **Standing warning — read this before touching any number in Phase 1/2.** The counts below
> (18-day live sample, 9 of 64 breached, 0 of 24 IC periods) are a snapshot of the repo at
> authoring time and **move on every pipeline refresh** (6×/day on `refresh-advisor.yml`'s
> schedule). Never hardcode "17 of 24", "9 of 64", or "17 days" anywhere in the rebuilt UI or its
> tests — always read `public/data/validation/signal_metrics.json`'s own `summary` and
> `live_sample` blocks, and `research_evidence.json`'s `headline` block. The master's own prose
> was written at a 17-day snapshot; live is already past that.

**Row schema:** `| file/block | meaning | unit | cadence | range/level-rate-delta | uncertaintyKind | stateSource | decisionInformed | schema | notes |`

- `uncertaintyKind` ∈ `quantitative` (has a confidence interval / standard error / bootstrap) ·
  `qualitative` (expert judgment — classification, promotion state, reproducibility) · `both` ·
  `none` (a plain fact, e.g. a price).
- `stateSource` names which of the three independent state vocabularies governs the file (see
  "Three state vocabularies" below), or `n/a` for files with no state field.
- `schema` — the `pipeline/schemas/*.schema.json` path where one exists, else
  `UNCLEAR (contract lives in <code file>)`.

---

## Three independent state vocabularies

The rebuild's canonical four-state model (Established/Accumulating/Breached/Unavailable) is
built by mapping from whichever of these three vocabularies a given file actually carries — they
are **not interchangeable** and a file may carry more than one:

1. **Pipeline health** — `healthy | degraded | error`. Lives in `status.json` per-stage, feeds a
   chrome-level notice, never a per-metric state.
2. **Artifact build status** — `success | partial | gated | unavailable` (+ free-form
   `reason_code` / `degraded_reason` string). Lives on most `screens/*.json` files — describes
   whether the *file itself* built cleanly this run.
3. **Metric readiness** — `ready | provisional | accumulating | awaiting_input |
   awaiting_live_sample | unavailable`, crossed with `breached: true | false | null`. Lives on
   every row of `validation/signal_metrics.json` — describes whether *one number* is safe to
   read yet, independent of whether its container file built successfully.

---

## Cadence (from `.github/workflows/`)

| Workflow | Schedule (UTC) | Writes |
|---|---|---|
| `refresh-advisor.yml` | ~6×/day, NY-time gated (~07:00 full sweep + 12:00/15:00 ET fast sweeps) | advisor.json, report.json, diagnostics.json, etfs.json, etf/*.json, factors/french.json, benchmark-report.json, status.json, most screens/*, all validation/* |
| `theme-peers.yml` | weekdays 13:30 | theme-peers.json |
| `congress-trades.yml` | every 5 days | screens/congress-trades.json |
| `inside-information.yml` | every 3 days | screens/inside-information.json |
| `sec-filings.yml` | every 3 days | screens/filings.json |
| `institutional-13f.yml` | monthly (1st) | screens/institutional-13f.json |
| `marketstack-premarket.yml` | weekdays, premarket windows | premarket quotes |
| `collect-earnings-releases.yml` | weekly | earnings-release store |
| `backfill-pit-fundamentals.yml` | monthly | point-in-time fundamentals store |
| `measure-survivorship.yml` | quarterly | survivorship measure |
| `demo-data.yml` | manual | signals/picks/news/prices/trades/politicians.json (all orphaned — see below) |

---

## Loader (unchanged by the rebuild — reuse as-is)

`src/lib/useData.js` — `useData(file)` fetches `${BASE_URL}data/${file}` with `cache:
'no-cache'` (ETag revalidation). In-flight request dedup; schema migration only for `advisor`
and `etfs` (`schemaMigrations.js`); two-tier cache (localStorage `dash:last-refresh:{file}` +
Cache API `dash-data-cache-v1` for multi-MB files) used **only as a fetch-failure fallback**,
never to paint a fresh mount — every mount shows the loading state, and `fromCache`/`cachedAt`
is the signal a screen is looking at stale data.

---

## File rows

| file/block | meaning | unit | cadence | range/level-rate-delta | uncertaintyKind | stateSource | decisionInformed | schema | notes |
|---|---|---|---|---|---|---|---|---|---|
| `advisor.json` (47 MB) | Full per-stock deep snapshot: fundamentals (~60 fields), scores, evidence, explainability, `analysis_v2`/`recommendation_v2` shadow decision layer, series history | mixed | ~6×/day | level (scores 0–100) + series | both | pipeline health (top-level) + metric readiness (per-field via `capability_status`) | Stock Detail Sheet's deep tabs, Methodology weights, News, Themes | `advisor.schema.json` | lazily fetched only when a row lacks `explainability`; `publication_gate.published/reason` gates whether a row is shown at all |
| `report.json` (8.9 MB) | Trimmed advisor payload — 17 `useData` call sites, the app's primary data file | mixed | ~6×/day | level + series | both | build status (top-level) + metric readiness (`data_coverage`) | almost every screen | `UNCLEAR` (no dedicated schema; shares advisor's shape minus `explainability`/`analysis_v2`/`recommendation_v2`/`publication_gate`/`validation_harness`/`run_manifest`/`data_freshness`/`history`) | opens instantly, advisor.json upgrades it later |
| `status.json` (5 KB) | Pipeline health board, per stage | enum | ~6×/day | level | qualitative | pipeline health | `DataStatus` chrome banner | `status.schema.json` | top-level `model_version` (3.0.0) disagrees with `model_metadata.semantic_version` (3.2.0) — **always read `model_metadata`, never the top-level field**; `status` currently reads `degraded` solely because of the stale `demo_seed` stage while `data_mode` is `live` everywhere else — a new status chip needs to decide whether `demo_seed` should count |
| `etfs.json` (383 KB) | ETF scoring + peer ranking, 125 funds | mixed | ~6×/day | level | both | metric readiness (`confidence`, `*_source`, `*_lookthrough_available`) | Home, Research, Portfolio, Diversification, Insights | `etfs.schema.json` | `sector_lookthrough_available`/`position_lookthrough_available` booleans drive the "can't see through this fund" empty states |
| `etf/<ticker>.json` ×125 | Per-ETF benchmark comparison + price series | mixed | ~6×/day | level + series | both | `benchmark.confidence` + `benchmark.quality_label` | Stock Detail Sheet ETF tab, Portfolio, Insights | `UNCLEAR` (no per-file schema found) | no `model_metadata` block — Provenance component must degrade gracefully |
| `benchmark-report.json` (280 KB) | Benchmark price histories, 8 indexes | series | ~6×/day | level | none | n/a | Finances, Diversification, Insights, Planning, Home | `UNCLEAR` | |
| `factors/french.json` | Fama-French 5 + momentum monthly factor returns, 756 obs | decimal return | monthly-ish | delta | none | n/a | Diversification factor regression | `UNCLEAR` | still says `model_version 3.0.0` |
| `theme-peers.json` (483 KB) | Thematic peer expansion beyond advisor.json's affordability, 11 themes | mixed | weekdays 13:30 | level | both | artifact build status (`status`) + metric readiness (`eligible`) | Screens `?recipe=themes` | `UNCLEAR` | anti-hype guardrail: price momentum contributes zero to `theme_exposure_score` (enforced by `pipeline/validate_data.py`) |
| `diagnostics.json` (5.3 MB) | Per-ticker scoring diagnostics, top 25 | mixed | ~6×/day | level | quantitative | n/a | **none — zero `useData` consumers in `src/`** | `UNCLEAR` | **orphan — NOTES.md, never delete; either wire into a debug view or drop from the build in a later pass** |
| `screens/swing.json` (6.4 MB) | Multi-leg swing composite, 3 horizon tiers | mixed | ~6×/day | level + z-scores | both | artifact build status (`status: success`) | Screens `?recipe=swing` | `UNCLEAR` | richest single-file disclosure set; `published_variant`, `scored_count`/`eligible_count`/`suppressed_count` |
| `screens/options.json` + 7 strategy files + matching `-backtest.json` | Options-idea screens | mixed | ~6×/day | level | both | artifact build status | Screens `?recipe=options` | `UNCLEAR` | |
| `screens/momentum.json`, `quality-value.json`, `earnings-timeliness.json`, `structural-tactical.json` | Ranked-list research screens | level | ~6×/day | level + percentile | both | artifact build status | Screens `?recipe=<id>` | `UNCLEAR` | quality-value's own-history window depth varies per row, published per row |
| `screens/early-session.json` (4.8 KB, stale since 2026-08-04) | Premarket/first-hour reversal capability gate | enum | ad hoc (currently stale) | n/a | qualitative | artifact build status (`status: gated`, `mode: shadow_only`) | Screens `?recipe=early-session` | `UNCLEAR` | gated is the correct, intended state — "killed screens are a successful data-quality outcome" |
| `screens/congress-trades.json` (4.7 MB) | Congressional trade disclosures, 5,696 results | mixed | every 5 days | level | both | artifact build status (`status: success\|partial\|unavailable` + `reason_code`) | Screens `?recipe=politics` | `congress-trades.schema.json` | currently `status: "partial"` — `SOME_SOURCES_UNAVAILABLE` |
| `screens/institutional-13f.json` (4.3 KB) | Curated institutional 13F manager coverage | level | monthly | level | both | artifact build status (`status: success`, `degraded_reason: null`) | Screens `?recipe=institutional` | `UNCLEAR` | **`results: []` while `status: "success"`** — needs an explicit "no changes this period" empty state distinct from an error |
| `screens/inside-information.json` (8.3 KB) | Political + institutional overlap | level | every 3 days | level | both | artifact build status | Screens `?recipe=inside-information`, Stock Detail Sheet | `UNCLEAR` | |
| `screens/backtest-comparison.json` (27 KB) | 15 retrospective methods compared, 14 measured | mixed | ~6×/day | level + delta | both | per-method `status`/`status_detail` | Evidence `?section=backtests` | `UNCLEAR` | every success rate carries its own basis definition alongside it |
| `screens/shadow-portfolios.json` (13 KB) | Prospective, immutable strategy tracking — the promotion-gate file | mixed | ~6×/day | delta (returns) | both | per-strategy `promotion_eligible`, `evidence_status`, `skipped_detail[].reason` | Evidence `?section=shadow` | `UNCLEAR` | **no `model_metadata` block**; `promotion_gate` text: "No strategy is promotion-eligible until 36 monthly observations are complete" |
| `validation/signal_metrics.json` (162 KB) | The 64-metric kill-threshold dashboard, groups A–H | mixed | ~6×/day | level + delta | both | metric readiness on every one of 64 rows | Evidence `?section=validation`, Portfolio `?view=data&analytics=algorithm` | `UNCLEAR` (contract lives in `pipeline/signal_metrics.py` + `src/lib/signalMetrics.js`) | **the file every disclosure ultimately points back to** — `summary: {total:64, ready, breached, sample_free_*}`, `live_sample: {days, refreshes, first_date, last_date}`; currently 9 breached incl. `deflated_sharpe` (live 0.238 vs the doc's cited retrospective 0.95 — see divergence note below) |
| `validation/ic_validation.json` (45 KB) | Champion/challenger rank-IC by horizon (1M/3M/6M/12M) | quantitative | ~6×/day | delta | quantitative | per-horizon `status: accumulating`, `eligible: false` | Evidence `?section=validation` | `UNCLEAR` | all four horizons currently `periods_accumulated: 0` of `minimum_periods: 24` |
| `validation/research_evidence.json` (83 KB) | The canonical promotion-state block — `headline` | mixed | ~6×/day | n/a | qualitative | `calibration.status: insufficient_data` per score band | Evidence `?section=validation` | `UNCLEAR` | **`headline.validation_status: "no calibration history yet"`, `ic_periods_accumulated: 0/24`, `score_is_not_a_probability` text** — this is the disclosure that closes the "classification B is docs-only" gap (see CAPABILITY-LEDGER §10c) |
| `validation/live_v2_validation.json` (345 KB) | Per-ticker structural/timeliness validation invariants, 10 results | mixed | ad hoc | n/a | both | per-row `status`, `provider_status`, `invariants[].status` | Evidence `?section=validation` | `UNCLEAR` | `production_outputs_replaced: false` |
| `validation/monte_carlo_projection.json` (3.5 KB) | Bootstrap projection paths, 4 horizons | quantitative | ad hoc (last: 2026-08-18) | n/a | quantitative | `status: ready` | Portfolio `?view=data&analytics=algorithm` | `UNCLEAR` | carries its own long "this is a projection, not a forecast" disclosure string to render verbatim |
| `validation/live_etf_validation.json` (14 KB, stale since 2026-08-03) | ETF benchmark validation, 8 results | mixed | ad hoc | n/a | both | per-row `status`, `contract_status` | **none — zero `useData` consumers in `src/`** | `UNCLEAR` | **orphan — NOTES.md, never delete** |
| `signals.json`, `picks.json`, `news.json`, `prices.json`, `trades.json`, `politicians.json` | Demo-mode fixtures | mixed | manual (`demo-data.yml`) | n/a | none | `data_mode: demo` | **none — zero `useData` consumers in `src/`** (news.json appears only in a test fixture) | `signals.schema.json`, `picks.schema.json`, `news.schema.json`, `prices.schema.json`, `trades.schema.json`, `politicians.schema.json` | **all six orphans — NOTES.md, never delete** |

---

## Universal provenance envelope

Every live artifact carries `{schema_version, model_version, generated_at,
model_metadata: {semantic_version, git_commit_sha, config_hash, generated_at}}` **except**
`shadow-portfolios.json`, `early-session.json`, and every `etf/<ticker>.json` — the shared
Provenance/`ProvenanceStrip` component every medium renders must degrade gracefully for those
three (show what's available, never fabricate a version string).

## Doc-vs-live divergence (flag prominently, cite the live file as truth)

`docs/MASTER-METHODOLOGY.md` §9 cites a retrospective battery: deflated Sharpe **0.958–0.952
(marginal pass)**, PBO **0.69, rising to 0.76 under a variant (fail)**. The **live**
`signal_metrics.json` currently publishes `deflated_sharpe: 0.238, breached: true` against
threshold 0.95, and `pbo: 0.0, status: "provisional"` (3 holdout folds, CSCV wants ≥8). These are
not the same measurement — one is a historical backtest claim frozen in prose, the other is the
artifact the UI actually reads. **The rebuilt UI must always render the live artifact's numbers,
never the doc's**, and `DESIGN.md`/`NOTES.md` should say so explicitly so a future editor doesn't
"fix" a live number to match the doc.

## Key enums (from `pipeline/schemas/`, drives the canonical state mapping in `core/states.js`)

`status.json`: `healthy | degraded | error` · `advisor.json research[].stance`: `ATTRACTIVE |
PROMISING | MIXED | CAUTION | INSUFFICIENT DATA` · `.recommendation.action`: `HOLD | WATCH | TRIM
| SELL` · `.data_freshness.status`: `healthy | degraded | error` · `.market.macro.regime.label`:
`supportive | neutral | restrictive` · `theme_screen` row `candidate_source`: `published_leader |
portfolio | sector_peer | null`, `role`: `root | enabler | supplier | infrastructure | service |
null`, `trend.verdict.label`: `broadening | narrow leadership | strong but already priced |
cooling | mixed | unmeasured` · `congress-trades.json status`: `success | partial | unavailable`
(+ free-form `reason_code`), `direction`: `BUY | SELL`, `chamber`: `house | senate | executive` ·
`recommendation-v5.schema.json policy_mode`: `shadow | active`, position action `label`:
`no_action | hold | trim | review | exit`, company `label` incl. `insufficient_evidence`, every
action object carries free-form `reason_namespace` + `reason_codes[]` · `signals.json label`:
`HIGH CONVICTION | WATCH | NEUTRAL | LOW` (demo-only, orphaned) · every live file's `data_mode`:
`demo | live`.
