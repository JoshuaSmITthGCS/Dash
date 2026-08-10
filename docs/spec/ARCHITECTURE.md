# ValueSignal — Architecture Specification

**Status: draft in progress.** Sections 4, 5, 6, 8, and part of 10 are complete and
independently verified against current code (branch `claude/valuesignal-spec-audit-qf2wni`,
HEAD as of 2026-08-10, working tree matching commit `e312488`). Sections 1–3, 9, and 12 are
pending synthesis from a parallel research pass and are marked accordingly below. Do not treat
this file as finished; it is being assembled incrementally and will be redeployed in place.

Every factual claim below carries a `path/to/file.py:line` citation to code read directly in
this session, not copied from this repository's own internal audit documents
(`research/audit/CURRENT_MODEL_AUDIT.md`, `research/audit/PIPELINE-MAP.md`), which are dated
2026-08-09 and are confirmed to be one or more fix-commits behind current code. Those documents
were used only for orientation — every specific number or line reference from them was
re-verified against the live file before being repeated here.

---

## 0. A note on system state

This system is under active, same-day development. Between the internal audit's date
(2026-08-09) and this document's compilation (2026-08-10), at least the following fix commits
landed (`git log --oneline`, confirmed present in this branch's history):

| Commit | Effect |
|---|---|
| `cb3cc53` | Peer-relative claims now require ≥30 valid peers or publish nothing; alphabetical tie-break removed |
| `ac24342` | Fabricated `timeliness.effective_score = 50.0` deleted; layer now publishes `null` when no input resolves; a guard (`layer_health.assert_layers_vary`) fails the publish path if a layer ever becomes constant across the universe again |
| `cd581b5` | The legacy `confidence` field renamed to `data_coverage` throughout the champion path, to stop the completeness ratio being read as a reliability score |
| `0e0a9ad` | The live scorer's per-sector metric suppression now reads the same `applicability_matrix.json` registry the shadow path reads, replacing two standalone sector-string heuristics (`FINANCIAL_EXEMPT`, `TANGIBLE_BOOK_SECTORS`) that disagreed with it |
| `790d0da` | The live deterioration-guidance rule (`action_for`) no longer treats a missing input as "no concern" (`... or 0`, `... or 99` patterns removed); missing inputs are now reported in an `unmeasured` list instead |

Four defects this task's brief lists as "already-confirmed" — the 14-name peer percentile, the
`EARNINGS_TIMELINESS` 50/100 default, the cross-path confidence disagreement, and insurer DSO
surviving suppression while P/B and D/E are nulled — map directly onto commits `cb3cc53`,
`ac24342`, `cd581b5`, and `0e0a9ad` respectively, and no longer reproduce in their original form
against current code and the current published artifact. Section 10 documents what I verified
instead: the residual, differently-shaped version of the confidence issue, and defects found
independently during this pass. See `docs/spec/TRACE_THG.md` for the full verification trail
against a live example (THG).

---

## 1. System overview

**ValueSignal** is one research module inside a larger personal-finance PWA ("Dash", this
repository) that also covers portfolio tracking, retirement projection, options-strategy
screens, and a Congressional/13F trading tracker. ValueSignal specifically is the module that
scores a universe of equities on a 0-100 "research score" and attaches a HOLD/WATCH/TRIM/SELL
recommendation, published as `public/data/advisor.json` (25.8 MB as committed, confirmed by
direct `wc -c` this session) and rendered across 12+ React pages (`Watchlist.jsx`,
`Dashboard.jsx`, `Picks.jsx`, `Insights.jsx`, `StrategyScreen.jsx`, `PolicyRadar.jsx`,
`Glossary.jsx`, `OptionsScreen.jsx`, `Diversification.jsx`, `ThemeExposureScreen.jsx`,
`Finances.jsx`, `Search.jsx`, `Methodology.jsx` — confirmed by grepping `useData('advisor.json')`
call sites across `src/pages/`).

**Full path from a scheduled run to a rendered number:**

1. A GitHub Actions workflow fires on a cron schedule or manual dispatch — the primary one is
   `.github/workflows/refresh-advisor.yml`, `cron: '7 11,12,16,17,19,20 * * 1-5'` (weekdays,
   ET-market-hours-aligned, ~6×/day), also triggerable via `workflow_dispatch` with modes
   `data-only` / `full-alpha` / `rescore-only` (per `docs/spec/FILE_INVENTORY.md`, "Runtime
   topology" — that document's citations were re-used, not re-derived, since it is already
   code-grounded).
2. The workflow runs `python pipeline/fetch_advisor.py` (entry point `run()`, currently starting
   near line 1313 — this line number shifted once already during this session's investigation of
   an earlier draft, confirming the file is under active modification; do not trust line numbers
   from any document older than this one), which pulls fundamentals/prices/estimates from Alpha
   Vantage and Yahoo, scores every name (`pipeline/scorer.py`, `pipeline/advisor_engine.py`,
   `pipeline/scoring_v2.py`, `pipeline/recommendation_policy_v2.py` — detailed in §4-§8 below),
   then a chain of further scripts (options-strategy screens, `rescore.py`,
   `build_quality_value_screen.py`, `build_tactical_screens.py`, `shadow_portfolios.py`,
   `validate_data.py`, `stability_report.py`, `evaluate_alerts.py`) before the workflow commits
   the refreshed `public/data/*.json` files back to the repository (chain per
   `FILE_INVENTORY.md`'s "Runtime topology" section, itself read from `refresh-advisor.yml`
   directly).
3. Two run modes are selected by the `ADVISOR_UNIVERSE_MODE` environment variable
   (`fetch_advisor.py:1337`, default `"full"`): full mode polls the entire configured universe
   and refits normalization distributions from scratch; fast mode reuses a prior fit and only
   re-polls a rotating subset (exact rotation mechanics: see §3, UNDETERMINED in that section
   whether independently re-verified this pass).
4. Alpha Vantage statement-enrichment calls are capped at 5 symbols per refresh regardless of
   universe size (`fetch_advisor.py:1343`, `ALPHA_ENRICH_LIMIT`, clamped `max(0, min(5, ...))`)
   — which symbols get the scarce enrichment slots is itself a scoring-feedback mechanism, see
   `docs/spec/TRACE_THG.md` §1 (`enrichment_selection.previous_top`).
5. Committing to `main` is the publish step — there is no separate deploy/build trigger observed
   this session beyond Netlify's normal git-push-triggered static rebuild (Netlify config/build
   hooks not independently re-verified this session; UNDETERMINED whether a webhook or polling
   deploy is in use).
6. The React app never talks to a database or API for this data at render time: `src/lib/useData.js`
   (`useData(file)`, confirmed by direct read, fetch call at line 95) does
   `fetch('${BASE_URL}data/${file}?v=${Date.now()}', { cache: 'no-store' })` — a plain static-file
   fetch of the committed, deployed JSON with a cache-busting query parameter, not a live query
   against the pipeline. Every page listed above calls `useData('advisor.json')` and reads fields
   directly out of the fetched object.
7. A logged-in user can also trigger an on-demand refresh from the UI (`src/lib/useAdvisorRefresh.js`,
   read in full this session): this calls the Netlify function `netlify/functions/refresh-data.mjs`,
   which dispatches the same `refresh-advisor.yml` workflow via the GitHub REST API
   (admin-authenticated) and polls its run status; the frontend distinguishes a `full`-scope
   refresh (95-minute timeout, `useAdvisorRefresh.js:10`) from a `fast` one (55 minutes, line 6)
   and a `rescore`-only reanalysis (5 minutes, line 15, since `pipeline/rescore.py` touches no
   network and finishes in under a minute per that file's own inline comment). On success the
   hook calls `reload()`, which re-runs the same static fetch described in point 6 — there is no
   separate "live" data path; a manual refresh is just a way to make the next static fetch see a
   newer file.

**Repo layout, purpose of each significant area** (full detail in `docs/spec/FILE_INVENTORY.md`,
which is already complete and code-grounded — summarized here, not repeated in full):

| Area | Purpose |
|---|---|
| `pipeline/*.py` (~100+ modules) | The Python research/scoring engine: data fetch, canonical-metric normalization, scoring (legacy `scorer.py` + shadow `scoring_v2.py`), recommendation policy, screen builders (options strategies, momentum, quality-value, tactical, institutional/Congressional), backtesting, and a substantial internal validation/audit toolkit (`evaluation.py`, `ic_harness.py`, `score_calibration.py`, `bias_report.py`, `stability_report.py`). |
| `pipeline/sleeves/` | Partial "research contract" sleeve interface — only the value sleeve is implemented; 13 of 14 specified sleeves are intentionally unbuilt (`pipeline/sleeves/__init__.py` docstring, per `FILE_INVENTORY.md`). |
| `pipeline/validation/` | `ic_harness.py` — prospective, look-ahead-safe information-coefficient validation; `trading_calendar.py`. |
| `pipeline/tests/` | 111 pytest files, largely one-to-one with `pipeline/*.py` modules (full inventory in §12). |
| `pipeline/config/*.json` | All tunable configuration: `settings.json` (master weights/thresholds), `advisor_universe.json` (the scored symbol list), `applicability_matrix.json` / `business_profiles.json` (sector suppression rules), `recommendation_policy_v2.json` (shadow policy config), and ~15 more (full list in `FILE_INVENTORY.md`). |
| `pipeline/schemas/` | Draft 2020-12 JSON Schemas that `validate_data.py` checks every published artifact against. |
| `research/` | A substantial ad hoc research/audit engagement (own Phase 4-6 factor-return, band-integrity, and out-of-sample candidate-ranking studies) plus prior narrative audit docs (`research/audit/CURRENT_MODEL_AUDIT.md`, `PIPELINE-MAP.md`, `STATE.md`) explicitly marked in `FILE_INVENTORY.md` as **not independently verified** by this document's own passes — see §12. |
| `public/data/*.json` | The published artifacts the frontend fetches directly: `advisor.json` (this document's primary subject), `etfs.json`, `picks.json`, `trades.json`, `news.json`, `prices.json`, `report.json`, `score-history.json`, `signals.json`, `status.json`, `politicians.json`, plus `etf/`, `factors/`, `screens/`, `validation/` subdirectories. |
| `netlify/functions/*.mjs` | Three serverless endpoints: `refresh-data.mjs` (dispatches/polls the GitHub Actions refresh), `portfolio-prices.mjs` (Firebase-authenticated live portfolio quotes), `alert-push.mjs` (Web Push delivery for Firestore alert events). |
| `src/` | React + Vite PWA: `src/pages/` (24 routed pages), `src/components/` (~28 components), `src/lib/` (data-loading hooks, scoring-adjacent client-side logic such as `dipWatch.js`, `recommendation.js`, `schemaMigrations.js`). |
| `.github/workflows/*.yml` | Eight scheduled/dispatchable workflows: the main hourly-ish research refresh, weekly Congressional-trades collection, monthly 13F collection, twice-daily Marketstack premarket collection, monthly PIT-fundamentals backfill, quarterly survivorship measurement, on-demand mock-data seeding, and CI (`compileall`, `check_ui_weights.py`, `pytest pipeline/tests`, `ic_harness.py --snapshot`, `validate_data.py`). |

The published artifact examined throughout this document, `public/data/advisor.json`, carries
`generated_at: 2026-08-10T05:23:37Z`, `model_version: 3.2.0`, `schema_version: 6`,
`universe_count: 926` (confirmed by direct query against the committed file) — see §3 for why
this figure is much larger than the brief's "~120 names" description and how the two relate.

---

## 2. Data sources

**[PENDING — full section from parallel research pass covering: per-provider endpoints,
authentication, rate limits as implemented in `pipeline/cache.py`, retry/backoff, caching TTLs,
failure behavior per provider, and a field-level provenance table. Will be inserted here on
completion.]**

---

## 3. Universe construction

**[PENDING — from parallel research pass: `pipeline/config/advisor_universe.json` structure,
symbol count, static vs. generated, inclusion/exclusion criteria, ticker-to-entity resolution,
and universe change history via `git log` on that file.]**

---

## 4. Metric computation

### 4.1 The live (champion) fundamental score

Formula, in full, as implemented at `pipeline/scorer.py:_band_valuation_score` (lines 538–623),
verified line-by-line this session:

1. **Profile assignment and suppression.** `profile, suppressed = applicability(snap)`
   (`scorer.py:548`). This calls into `pipeline/canonical_metrics.py:classify_profile`
   (lines 95–130), a deterministic text-match over `sector`/`industry` strings, evaluated in a
   fixed priority order: ETF → REIT → bank → insurance subtype (life / property-casualty /
   diversified, by industry substring) → utility → commodity producer (oil/gas/mining/gold/
   copper/steel/coal substrings) → semiconductor → biotech (pre-profit vs. profitable, split on
   `profit_margin < 0`) → other pre-profit (any name with negative margin not otherwise
   classified) → `"general"` fallback. Eleven named profiles are declared in
   `pipeline/config/business_profiles.json` (`general, etf, property_casualty_insurer,
   life_insurer, diversified_insurer, bank, reit, utility, commodity_producer,
   profitable_biotechnology, pre_profit_biotechnology`); two more — `semiconductor` and
   `other_pre_profit` — exist as `classify_profile` return values and have their own entries in
   `pipeline/config/applicability_matrix.json`'s `rules` (confirmed: `rules` dict keys are
   `general, bank, property_casualty_insurer, life_insurer, diversified_insurer, reit, utility,
   commodity_producer, profitable_biotechnology, pre_profit_biotechnology, other_pre_profit,
   semiconductor` — 12 keys, all 13 `classify_profile` outputs except `etf`, which is
   special-cased directly in `applicability_for`, `canonical_metrics.py:142-143) — but are
   **not** listed in `business_profiles.json`'s `profiles` object, so any lookup of
   `profile_contract` (replacement/critical metrics, used in `scoring_v2.py:241-247`) for a
   semiconductor or other-pre-profit name silently returns an empty dict rather than raising.
   Verified for a live example: CRUS (Cirrus Logic, sector "Technology", industry
   "Semiconductors") resolves to `applicability_profile: "semiconductor"` in the published
   artifact, with `capex_to_depreciation` and `inventory_days_trend` both suppressed and scored
   `null` — the applicability rule fires correctly on the live path. Whether `CRUS`'s
   `scoring_v2` applicability block (which reads `business_profiles.json`, not
   `applicability_matrix.json`) silently degrades because `"semiconductor"` is absent from that
   file's `profiles` object is UNDETERMINED — not traced this session.
2. **Per-metric suppression.** For each of the (up to) 29 fundamental metrics, if its ID is in
   the `suppressed` set returned by `applicability`, its value is forced to `None`
   (`scorer.py:607`) before any scoring or coverage computation. `applicability_for`
   (`canonical_metrics.py:141-150`) resolves a metric's status by: (a) checking a per-profile
   rule table (`profile_rules`, which supports single-level inheritance via a `$inherits` key,
   `canonical_metrics.py:133-138`); (b) if no explicit rule, checking whether the profile is
   listed in the metric's `applicability_profiles` declaration in
   `pipeline/config/metric_registry.json`; a profile not listed there is suppressed by default
   with the reason `"Metric registry does not declare this profile applicable."`; (c) otherwise
   `"applied"`.
3. **Per-metric scoring function.** Each metric's raw value is mapped to a discrete score by one
   of six functions in `scorer.py` (`band_score`, `multiple_score`, `higher_is_better_score`,
   `lower_is_better_score`, `range_score`, `altman_score` — cutoffs read from
   `settings.json.fundamentals.<metric_name>` per metric). This mapping is table-driven, not
   continuous: the internal audit's characterization of ~12 discrete output levels (0/5/10/15/
   25/45/50/55/65/75/80/100) was not independently re-verified against every band table this
   session, but `_band_valuation_score`'s output for THG (`fundamental_detail` in
   `docs/spec/SAMPLE_OUTPUT.json`) shows exactly this pattern: every populated metric scores one
   of `{55.0, 75.0, 80.0, 100.0}`.
4. **Category aggregation with a required-metric gate.**
   `_categories_with_required_gate(metrics, cfg, profile)` (`scorer.py:515-535`) is **not** a
   simple reweighting. For each category, it first checks `required_for_score(profile,
   category)` (`canonical_metrics.py:174-182`, reading `applicability_matrix.json`'s
   `required_for_score` block — declared for 5 profiles only: `property_casualty_insurer,
   life_insurer, diversified_insurer, bank, reit`). If any metric named as required for that
   category is missing (`None`) for this profile, **the entire category is withheld** — set to
   `None` rather than computed from whatever metrics did resolve — and the withheld category
   plus its missing required metrics are recorded in a `categories_withheld` map. Only if no
   required metric is missing does the category fall through to
   `weighted_available(metrics, weights)` (`scorer.py:159-163`): a simple weight-renormalized
   average over whatever metrics in that category are non-`None`. **This means missing-value
   handling is not uniform across metrics**: a required metric's absence zeroes an entire
   category; a non-required metric's absence is silently renormalized away within the category,
   with no marker in the payload distinguishing "this 90.0 valuation score came from 8 of 8
   metrics" from "this 90.0 came from 2 of 8." (`weighted_available` records only the resulting
   value, not the count or share of metrics used — confirmed by reading its 5-line body.)
5. **Coverage.** `weighted_coverage(metrics, cfg, exempt=suppressed)` (`scorer.py:496-512`):
   the fraction of total *metric weight* (not metric count) that resolved to a non-`None` value,
   with suppressed metrics excluded from both numerator and denominator entirely — so
   suppressing a metric cannot lower measured coverage, and previously could artificially raise
   it under the retired `FINANCIAL_EXEMPT` scheme (see §0 above; this exemption pathway is gone,
   but the same mathematical property — suppressed metrics leaving the denominator — persists
   under the new, code-correct suppression mechanism, and is a deliberate design choice per the
   function's docstring, not a bug).
6. **Coverage-based shrinkage (first of two).**
   `confidence_multiplier = 0.65 + 0.35 * coverage` (`scorer.py:615`); `total = raw *
   confidence_multiplier` (`scorer.py:616`). Verified exactly against THG: `raw_score: 89.0`,
   `coverage: 0.96` → `89.0 * (0.65 + 0.35*0.96) = 89.0 * 0.986 = 87.75` → rounds to the
   published `components.fundamentals: 87.7`. This is an **arithmetic match**, not an inferred
   formula.

### 4.2 The composite blend (second coverage shrink)

`pipeline/advisor_engine.py:blend_research_components` (lines 846-867):

```
raw          = Σ(component_i · weight_i) / Σ(weight_i)     over available components
weight       = RANKING_WEIGHTS = {fundamentals: 0.78, market_behavior: 0.18, news_sentiment: 0.04}
                 (advisor_engine.py:32, 42; settings.json key "ranking_weights" overrides via
                 advisor_engine.py:35-39's _weights() merge, confirmed the merge only accepts
                 numeric, non-"_"-prefixed keys)
data_coverage = data_coverage_scalar(coverage)
              = 0.65·coverage[fundamentals] + 0.25·coverage[market_behavior] + 0.10·coverage[news_sentiment]
                 (advisor_engine.py:827-843)
base         = round(raw · (0.8 + 0.2·data_coverage), 1)                        (advisor_engine.py:861)
score        = round(clamp(base + modifier_points, 0, 100), 1)
```

**This is a confirmed, currently-live double coverage-shrink**, structurally unchanged from
what the internal (stale) audit described, just renamed: the `fundamentals` component entering
this formula is *already* shrunk once by its own internal `coverage` term (§4.1 step 6) before
`data_coverage_scalar` shrinks the composite a second time using a *different* coverage figure
(a 0.65/0.25/0.10 blend across all three components, of which fundamentals' own coverage is one
input at 65% weight). The two shrink events use the same underlying completeness concept applied
at two different levels of the score tree, both derived from `weighted_coverage`. Verified
against THG: `raw_score: 85.1`, modifiers `total: -1.57` → `base_score` should be
`clamp(85.1·(0.8+0.2·0.87)) = 85.1·0.974 = 82.88 ≈ 82.9`, matching the published `base_score:
82.9` exactly; `82.9 - 1.57 = 81.33 → 81.3`, matching the published `score: 81.3` exactly. Both
arithmetic steps verified against the live artifact.

The function's own docstring (`advisor_engine.py:847-852`) states the formula plainly and does
not claim this avoids double-counting — it is presented as the intended design, not a bug being
hidden. Whether double-shrinking coverage is *methodologically* sound (as opposed to internally
consistent) is a judgment call for the external reviewer; I flag the mechanism precisely rather
than pre-judging it.

### 4.3 Units, periods, adjustments

UNDETERMINED this session: split/dividend adjustment handling in price history
(`pipeline/fetch_prices.py`, not yet read), and a systematic TTM-vs-annual-vs-quarterly audit
across all ~29 fundamental metrics. Partial evidence: `canonical_metrics.Observation`
(lines 43-58) carries `is_ttm: bool = False` and `is_forward: bool = False` fields with
default-`False` values, and both v2 call sites that construct observations
(`overview_snapshot`, `yahoo_observations` — not yet opened this session) are reported by the
internal audit to construct observations without ever setting these fields, compensating with a
`provider_period_not_supplied` quality flag that (per the same source) nothing in the live
scoring path reads. **This specific claim is NOT independently re-verified this session** — it
is repeated from the internal audit with an explicit UNDETERMINED flag, not asserted as
confirmed current fact. Follow-up needed: open `overview_snapshot`/`yahoo_observations` in
`canonical_metrics.py` directly.

### 4.4 Winsorization and normalization — two live modes

Selected by `settings.normalization_mode` (confirmed value: `"bands"` is the champion/published
mode — every `SAMPLE_OUTPUT.json` field under `fundamental_detail` and `fundamental_categories`
is produced this way).

- **`bands`** (champion): `pipeline/scorer.py:_band_valuation_score`, described fully in §4.1.
  No winsorization. No cross-sectional reference population — each metric's score depends only
  on fixed absolute thresholds in `settings.json`, so (as the internal audit correctly notes,
  and this remains true in current code) a metric's score is not regime-relative.
- **`cross_sectional`** (challenger, published alongside the champion in
  `score_variants.normalization` — confirmed present in THG's live row):
  `scorer.py:CrossSectionalNormalizer` (class located at line 296 per earlier reading this
  session; internals — winsorization percentile, sector-vs-universe selection logic, tie
  handling — not yet re-read line-by-line this session; UNDETERMINED pending follow-up, though
  the *behavior* is directly visible in THG's published `score_variants.normalization.
  fundamental_detail.normalization` block: e.g. `forward_pe` scored at `normalization_scope:
  "sector"`, `peer_count: 123`, `raw_percentile: 50.8`, `desirability_percentile: 49.2`
  (multiple mapped via `direction: "lower_is_better"` as `100 - raw_percentile` for
  `forward_pe`, consistent with a percentile-rank-then-flip scheme); `price_to_book` scored at
  `normalization_scope: "universe"` with `peer_count: 693`. This confirms a per-metric,
  per-row choice between sector and universe reference populations is actually exercised in the
  published challenger data, not merely described in a docstring.
- **Own-history percentile**: every metric's normalization block in the challenger variant
  carries `own_history_percentile: null`, `own_history_status: "accumulating"`,
  `own_history_observations: 3` (THG, confirmed in `SAMPLE_OUTPUT.json`). This mechanism exists
  and is wired into the payload but is not yet populated for any metric in the live artifact —
  confirmed by direct inspection, not inferred.

### 4.5 Missing-value handling — exhaustive list of imputation/default sites found this session

This list combines defaults found through direct reading this session. It is **not yet
cross-checked against the exhaustive mechanical grep** the parallel METRIC_REGISTRY.md-building
pass is performing over all of `pipeline/*.py` — that pass's `registry.json` `defaults` array
should be treated as the authoritative, more complete version of this list once merged in.

| Location | Trigger | Default/behavior | Feeds a score/decision? |
|---|---|---|---|
| `scorer.py:159-163` (`weighted_available`) | any metric in a category is `None` | dropped, remaining weights renormalized to sum 1 within the category | Yes — category score |
| `scorer.py:515-535` (`_categories_with_required_gate`) | a *required* metric (per `required_for_score`) is `None` | entire category → `None`, recorded in `categories_withheld` | Yes — zeroes a whole category rather than reweighting |
| `scorer.py:496-512` (`weighted_coverage`) | metric suppressed for profile | excluded from coverage denominator entirely (not counted as missing) | Yes — coverage, which feeds the shrink in §4.1 step 6 |
| `advisor_engine.py:846-867` (`blend_research_components`) | a whole component (fundamentals/market_behavior/news_sentiment) is `None` | dropped from the weighted average, remaining weights renormalized | Yes — composite raw score |
| `advisor_engine.py:870-895` (`shrink_research_components`, challenger only) | no component available at all | `raw` defaults to `config["shrinkage_target"]` (a configured neutral, not a hardcoded literal in code) | Yes, challenger score only |
| `scoring_v2.py` `_weighted` (lines 22-26) | no value in a weighted set resolves | returns `None` (not a neutral number) — confirmed this is the *fixed* behavior, contrast with the retired pattern in §0 | Publishes `null`, does not fabricate |
| `recommendation_policy_v2.py:40-43` (`effective_score`) | `raw_score` is not a number | `raw = _number(raw_score, 50.0)` — **a literal 50.0 default still exists here** | Yes, but only reached when `raw_score` itself is malformed/non-numeric, not merely absent — a distinct condition from the timeliness-layer case discussed in §0, which now short-circuits *before* this function is called when the layer's `raw_score` is legitimately `None` per `_score_layer` (`recommendation_policy_v2.py:46-62`, which passes `raw = None` through and this function is never invoked with `raw_score=None` for an unresolved layer — confirmed by reading `_score_layer`'s `"effective_score": None if raw is None else effective_score(raw, confidence)` at line 59). **Practical implication: this 50.0 default appears to be dead code for the timeliness/structural layers as currently wired, but I have not proven no other call site passes a non-numeric `raw_score` into it. Flagged as needing a full call-site audit, not resolved this session.** |
| `recommendation_policy_v2.py:289-291` (`classify_portfolio_fit`) | no `portfolio` supplied | `current_weight → 0.0`, `target_weight → config.default_target_weight (0.03)`, `maximum_weight → config.default_max_weight (0.05)` | Yes — with `current(0.0) < target(0.03)·0.75`, this is always true with no portfolio context supplied, so `classification` is always `"below_target"` for any position-free evaluation. Confirmed still present and confirmed still producing `below_target` for THG (`portfolio_fit_state.classification: "below_target"`), which has no portfolio position. This matches the internal audit's finding and **is not fixed** — this remains a constant for every unpositioned name. |
| `pipeline/canonical_metrics.py:81-92` (`calculate_peg`) | forward PE, growth, unit, or period-match/definition-known flags fail validation | returns `None` (rejects rather than substitutes) | No default — explicit rejection, confirmed the "opposite of a silent default" pattern |

**Section 4 is not fully exhaustive yet.** The mechanical sweep in progress (parallel research
pass) will supersede this table with a fuller one; this table should not be read as the final
word on silent defaults.

---

## 5. Suppression and applicability

**Classification scheme**: `pipeline/canonical_metrics.py:classify_profile` (lines 95-130),
described in full in §4.1 step 1. Source of truth for per-profile metric rules:
`pipeline/config/applicability_matrix.json` (`rules` object, 12 profile keys, confirmed by
direct read this session) plus `pipeline/config/metric_registry.json`'s per-metric
`applicability_profiles` declaration as the fallback when no explicit rule exists
(`canonical_metrics.py:147-149`).

**`suppressed` vs. `replaced` vs. `unavailable`** — three distinct status strings appear in
`metric_status` entries (confirmed against THG's live `analysis_v2.metric_status` block in
`SAMPLE_OUTPUT.json`):
- `"suppressed"`: the applicability registry has an explicit rule saying this metric does not
  apply to this profile (e.g. THG's `ev_to_ebitda`: `"EV/EBITDA is not an insurer-standard
  valuation measure."`, `replaced_by: "price_to_book"`). Excluded from both score and coverage
  denominator (§4.1 steps 2 and 5).
- `"replaced"`: appears as a possible status value in `suppressed_metrics()`
  (`canonical_metrics.py:169`, checked alongside `"suppressed"`) but was not observed as a
  distinct status string in THG's actual `metric_status` output — every suppressed entry in the
  live example carries status `"suppressed"` with a `replaced_by` field pointing at the
  substitute metric, rather than the substitute itself carrying a `"replaced"` status.
  UNDETERMINED whether `"replaced"` is ever actually assigned as a metric's own status anywhere
  in the current codebase, or whether it exists in the code as a dead branch alongside
  `"suppressed"` at `scoring_v2.py:127` (`if status in ("suppressed", "replaced"):`). Needs a
  grep across all producers of `metric_status` to confirm.
- `"unavailable"`: the metric is applicable to this profile (not suppressed) but its value is
  simply missing this run — e.g. THG's `price_to_sales`: `status: "unavailable"`, no
  applicability reason given (`reason: null`). This is a data-completeness gap, not a
  methodology decision.

**Effect on the parent score — traced precisely (§4.1 steps 2-4):**
- A **suppressed** metric is removed from its category's weight base entirely; `
  weighted_available` renormalizes the remaining metrics' weights to sum to 1 within the
  category. It does **not** contribute a zero, and it does **not** reduce coverage (it leaves
  the coverage denominator too). Net effect: a category with several suppressed metrics is
  scored purely on whatever remains, at full renormalized weight, and reads as if the
  suppressed metrics never existed as an evaluation criterion for this profile.
- If a suppressed (or merely unavailable) metric happens to be in that profile's short
  `required_for_score` list for its category (declared for only 5 of 12 profiles — the
  insurers, banks, and REITs), the *entire category* is withheld (`None`) instead of being
  renormalized. This is a materially different and more severe consequence than ordinary
  suppression, and it is profile-specific: the same missing metric is "renormalize and move on"
  for a general/tech name and "withhold the whole category" for an insurer.
- Replacement metrics named in a profile's rule (e.g. insurer `ev_to_ebitda → price_to_book`) are
  **descriptive only in the payload** (`replaced_by` field) — I did not find code this session
  that actually substitutes the replacement metric's *value* into the suppressed metric's weight
  slot. The category's weight base is renormalized over the metrics that remain scoreable, which
  for an insurer includes `price_to_book` and `price_to_tangible_book` as their own weighted
  entries in the `valuation` category (weights 0.05 each, per §6) — not as a substitute carrying
  `ev_to_ebitda`'s 0.27 weight. **This means a metric named as a "replacement" does not inherit
  the suppressed metric's weight; it only contributes its own, normally much smaller, configured
  weight**, and the suppressed weight is redistributed proportionally across *all* remaining
  valuation metrics via `weighted_available`'s renormalization, not specifically routed to the
  named replacement. Verified by the numbers: THG's applied valuation metrics are `forward_pe
  (0.15), price_to_book (0.05), price_to_tangible_book (0.05)`; after renormalizing to sum to 1,
  their effective within-category shares become `0.15/0.25=0.60`, `0.05/0.25=0.20`,
  `0.05/0.25=0.20` — `forward_pe` dominates at 60% of the category, not the "replacement"
  metrics `price_to_book`/`price_to_tangible_book` the applicability rule names as the intended
  substitutes for the suppressed enterprise-value multiples. **This is a real, currently-live
  gap between what the applicability rule's `replaced_by` field claims and what the weighting
  arithmetic actually does — flagged as a finding for Section 10, not previously identified in
  the internal audit.**

**Business-profiles.json vs. applicability_matrix.json — two registries, confirmed still
separate.** `scoring_v2.py`'s `applicability` block (payload key `applicability`, distinct from
`metric_status`) reads `BUSINESS_PROFILES` (`business_profiles.json`) for `replacement_metrics`
and `critical_metrics` per profile (`scoring_v2.py:241-247`) — a second, independent list from
`applicability_matrix.json`'s `rules`. For THG these mostly overlap in spirit (both name
insurer-specific replacement concepts) but are declared in different files with no cross-check
enforced in code that I found this session; UNDETERMINED whether they can drift out of sync
undetected.

---

## 6. Scoring architecture — the weights

**Full hierarchy, verified against `pipeline/config/settings.json` directly (not copied from
any prior audit) and against the code that reads each block:**

### 6.1 Composite level

| Component | Weight | Defined at | Read at |
|---|---|---|---|
| fundamentals | 0.78 | `settings.json` key `ranking_weights.fundamentals`, or `DEFAULT_RANKING_WEIGHTS` (`advisor_engine.py:32`) if absent from config | `advisor_engine.py:42`, `RANKING_WEIGHTS = _weights(SETTINGS.get("ranking_weights"), DEFAULT_RANKING_WEIGHTS)` |
| market_behavior | 0.18 | same | same |
| news_sentiment | 0.04 | same | same |

Sums to 1.0 exactly. `_weights()` (`advisor_engine.py:35-39`) merges config over defaults,
accepting only numeric, non-underscore-prefixed keys — so a malformed config entry is silently
dropped back to the hardcoded default rather than raising. **This is config-driven with a
code-level fallback, confirmed still present** — verifying whether `settings.json` actually
overrides these three values or the code defaults are what's live requires comparing the
config file's `ranking_weights` block against `DEFAULT_RANKING_WEIGHTS`; not yet done this
session (UNDETERMINED whether config or default is the operative source for these three
specific numbers, though they are identical either way per the values found in `settings.json`
fundamentals earlier in this session — full `ranking_weights` block not yet read directly).

### 6.2 Fundamentals: category level

`settings.json.fundamentals.category_weights` (queried directly this session):

| Category | Weight |
|---|---|
| valuation | 0.28 |
| profitability | 0.26 |
| financial_health | 0.15 |
| growth | 0.11 |
| capital_allocation | 0.10 |
| accounting_quality | 0.10 |

Sum: `1.0000000000000002` — a floating-point rounding artifact from summing six decimal
literals in Python, confirmed by direct computation this session, not a configuration error. Not
a defect worth flagging beyond noting it exists.

### 6.3 Fundamentals: metric level within category

`settings.json.fundamentals.metric_weights`, each category's weights summing to exactly 1.0
(verified by direct computation this session):

| Category | Metric | Weight in factor |
|---|---|---|
| valuation | ev_to_ebitda | 0.27 |
| valuation | ev_to_fcf | 0.18 |
| valuation | forward_pe | 0.15 |
| valuation | ev_to_ebit | 0.12 |
| valuation | peg | 0.09 |
| valuation | sales_multiple | 0.09 |
| valuation | price_to_book | 0.05 |
| valuation | price_to_tangible_book | 0.05 |
| profitability | return_on_invested_capital | 0.26 |
| profitability | gross_profits_to_assets | 0.22 |
| profitability | free_cash_flow_yield | 0.16 |
| profitability | cash_conversion | 0.16 |
| profitability | return_on_equity | 0.10 |
| profitability | profit_margin | 0.10 |
| financial_health | interest_coverage | 0.30 |
| financial_health | net_debt_to_ebitda | 0.24 |
| financial_health | debt_to_equity | 0.18 |
| financial_health | altman_z | 0.18 |
| financial_health | current_ratio | 0.10 |
| growth | revenue_growth | 0.26 |
| growth | fcf_growth_3y | 0.22 |
| growth | earnings_growth | 0.20 |
| growth | operating_margin_trend | 0.16 |
| growth | earnings_surprise | 0.16 |
| capital_allocation | net_buyback_yield | 0.34 |
| capital_allocation | stock_comp_to_revenue | 0.28 |
| capital_allocation | asset_growth | 0.22 |
| capital_allocation | capex_to_depreciation | 0.16 |
| accounting_quality | piotroski_f | 0.45 |
| accounting_quality | accruals_ratio | 0.22 |
| accounting_quality | days_sales_outstanding_trend | 0.17 |
| accounting_quality | inventory_days_trend | 0.16 |

**Effective weight in composite** = `0.78 (fundamentals) × category_weight × metric_weight`.
Example: `ev_to_ebitda` = `0.78 × 0.28 × 0.27 = 0.05896`, i.e. ~5.9% of the full composite score
before any suppression, coverage shrink, or modifier is applied — and 0% for any name where it
is suppressed (all insurers, confirmed for THG). The full one-row-per-metric table with every
metric's effective composite weight is being built as `docs/spec/METRIC_REGISTRY.md` in
parallel; it is not reproduced in full here to avoid duplication and drift between the two
documents.

### 6.4 Market behavior: sub-weights

`advisor_engine.py:53-59` (`DEFAULT_TECHNICAL_WEIGHTS`, overridable via
`settings.json.market_behavior.weights`):

| Sub-metric | Weight |
|---|---|
| momentum_12_1 | 0.30 |
| risk_adjusted | 0.26 |
| relative_strength | 0.16 |
| drawdown_resilience | 0.14 |
| volume_confirmation | 0.08 |
| low_beta | 0.06 |
| technical_extended | 0.06 |

Sums to 1.0. Effective composite weight of e.g. `momentum_12_1` = `0.18 × 0.30 = 0.054`, ~5.4%
of the full composite before shrink/modifiers.

A module comment (`advisor_engine.py:45-52`, attached directly to this weight table) explicitly
argues `technical_extended`'s small weight is deliberate given "the literature behind adding
many technical indicators mostly shows data-snooping" — this is the closest thing to a stated
methodological justification for a specific weight value found anywhere in this codebase this
session. It is a comment, not a citation to an external validation result; treated here as a
design rationale, not evidence of fitting.

### 6.5 Bounded post-blend modifiers

`pipeline/advisor_engine.py:apply_modifiers` (lines 515-557), champion path:

| Modifier | Bound | Source function |
|---|---|---|
| sector_valuation | ±3 (per internal-audit orientation, not re-verified numerically this session) | `sector_percentile_modifier` |
| short_interest | up to −6 | `short_interest_modifier` |
| liquidity | −3 | `liquidity_modifier` |
| expectations | ±3 | `expectations_modifier` |
| macro_regime | ±3 | `macro_regime_modifier` |
| insider_activity | +5 / −3 | `insider_modifier` |
| institutional_13f | — (in champion path per Phase 3.3, per docstring) | `institutional_ownership_modifier` |
| congressional_buying | reward-only, up to +4 per prior orientation | `congressional_buying_modifier` |
| customer_concentration_risk | — (added to champion path per Phase 3.3) | `concentration_risk_modifier` |

**Combined cap, confirmed by direct read**: `total = round(max(-15.0, min(15.0,
uncapped_total)), 2)` (`advisor_engine.py:552`) — a hard ±15-point cap on the summed modifiers,
confirmed as a literal in the function body, not a config value. `geographic_concentration`
remains challenger-only (`apply_challenger_modifiers`, a separate function starting at line
560), per that function's docstring, for a stated correctness reason (geography-tagged revenue
often reflects shipping/contracting entity rather than end demand) rather than a coverage
reason. Individual per-modifier point caps (the ±3/±6/etc. figures in the table above) were
sourced from the internal audit's orientation and **not independently re-derived from each
modifier function's body this session** — flagged UNDETERMINED for the exact current numeric
caps on each of the nine modifiers; only the combined ±15 cap is independently confirmed by
direct code read.

A separate challenger variant (`score_variants.modifier_recalibration`, confirmed present in
THG's live row) uses a **different combined cap of 20.0** and allocates each modifier a
*fraction* of that cap (`fractions` object in `SAMPLE_OUTPUT.json`, e.g. `short_interest_penalty:
0.3` of the 20-point cap = 6 points max) — this is a distinct, non-champion scoring path; do not
conflate its ±20 cap with the champion's ±15 cap.

### 6.6 Weight provenance

`git log --oneline -- pipeline/config/settings.json` (run directly this session): **9 commits
total** touch this file across its history. None of their messages reference fitting, IC
optimization, backtesting, or calibration against outcome data — they read as feature additions
(`"Wire customer-concentration, geographic-concentration, and 13F risk into the live score"`,
`"Add a reward-only Congressional-buying modifier"`) and periodic data refreshes. `git log -S`
on a specific weight literal (`ev_to_ebitda: 0.27`) returned only a data-refresh commit, meaning
that value has not changed since before the searchable history window used this session (or was
present from the file's current form onward without a weight-specific commit isolating its
introduction — the search does not distinguish these two cases without deeper history spelunking
not performed this session).

**Direct answer to the brief's question: no evidence was found, in either the current code or
its git history, that any weight in this system has been fitted to or validated against
outcome data.** This is corroborated from a second angle: `pipeline/advisor_engine.py:
data_coverage_scalar`'s docstring (lines 830-836) states outright that "a real confidence
metric, validated against realised prediction error, is Phase 8 work and does not exist yet,"
and the live artifact's `historical_calibration` component is `null` for every row (confirmed
for THG in `SAMPLE_OUTPUT.json`'s `data_coverage_detail.components.historical_calibration`),
with the gating explanation `"insufficient prospective calibration history (requires 24
eligible IC periods)"`. `pipeline/score_calibration.py` exists and implements a gate for this,
but the gate has apparently never opened. See §12 (pending) for the fuller test/validation
inventory.

---

## 7. Confidence and coverage

**Not one formula — at minimum four distinctly-named, distinctly-defined scalars publish on the
same row, all descending from the same underlying "how much intended evidence resolved"
concept, none validated against outcomes:**

1. **`row["data_coverage"]`** (top-level, legacy/champion path) = `data_coverage_scalar(coverage)`
   = `0.65·coverage[fundamentals] + 0.25·coverage[market_behavior] + 0.10·coverage[news_sentiment]`
   (`advisor_engine.py:827-843`). THG: `0.87`.
2. **`analysis_v2.structural.coverage`** (shadow path) = `available_weight / applicable_weight`
   over the fundamentals category weights specifically, computed inside
   `scoring_v2.build_v2_analysis` (verified against current file, lines 84-159 read in full
   earlier this session). THG: `0.84`. This is a *different population* from #1 (fundamentals
   only, not blended with market/news) computed by *different code* (`scoring_v2.py`, not
   `advisor_engine.py`) reading a *different data structure* (`observations`, the v2 provenance
   layer, not the flat scalar snapshot `scorer.py` reads) — not simply a relabeling of #1.
3. **`analysis_v2.structural.evidence_weight_resolved`** = `coverage × provenance_reliability −
   conflict_penalty − stale_penalty`, where `provenance_reliability` is a **hardcoded literal**:
   `0.72 if observations else 0.55` (`scoring_v2.py:162`, confirmed present, no derivation or
   config reference given for either constant). THG: `0.61`.
4. **`analysis_v2.timeliness.coverage`** = `0.0` for THG — the timeliness layer's own coverage,
   confirmed `0.0` because neither of its two inputs (`forward_eps_revision_30d`,
   `earnings_surprise`) resolved. This is correctly a *different number for a different layer*,
   not a bug, but it is a fifth-ish scalar in the same conceptual family appearing in the same
   payload.
5. `data_coverage_detail.components` (published via `pipeline/data_coverage.py`,
   `data_coverage_components`, read in full this session) breaks #1 into five named components
   — `completeness` (recomputes the *identical* #1 formula, by the module's own docstring
   confirmation: "Identical to the blend the champion's scalar already computes ... reused, not
   rewritten, so this component and the scalar can never silently disagree",
   `data_coverage.py:43-51`), `freshness` (linear decay, `null` if `data_fetched_at` is absent —
   `null` for THG), `source_reliability` (run-wide, not per-ticker — fraction of *configured*
   providers healthy this run; THG: `0.92`), `peer_sample` (peer count ÷ a configured
   full-strength target of 20; THG: `0.35`, from 7 valid P&C-insurer peers ÷ 20), and
   `model_agreement` (1 − stdev-of-challenger-scores/15-point scale; THG: `0.25`, meaning the
   champion and its challenger variants disagree by roughly `15×(1-0.25)≈11.25` points of
   standard deviation across variants — consistent with the champion (81.3) vs.
   cross-sectional-challenger (56.8) spread visible in THG's `score_variants`).

**Why they disagree, precisely**: #1 and #3 both claim to measure "how much evidence resolved"
but are computed from different code, different data structures, and in #3's case, an explicit
hardcoded reliability discount (`0.72`/`0.55`) that #1 does not apply at all. #2 restricts the
population to fundamentals only; #1 blends three components. None of the five numbers is a
statistical property of the signal (dispersion, realized error, hit rate) — this is stated
explicitly and repeatedly in the code's own docstrings (`data_coverage.py:10-15`,
`advisor_engine.py:830-836`), which independently corroborates §6.6's conclusion that no
validated confidence metric exists in this system.

**Verdict relative to the brief's framing**: the brief asks for "the legacy path and the shadow
path" producing "different numbers for the same name" — true, but the actual shape is not two
numbers, it is at least four to five, spread across two top-level paths and one decomposition
module, and as of `cd581b5` they are distinctly named rather than all called "confidence." I
judge this an improvement in transparency (a reader can no longer mistake one number for
"the" confidence) without being a resolution of the underlying multiplicity, and I'm stating
that judgment explicitly rather than letting the renaming read as a fix on its own.

---

## 8. Guidance and policy

### 8.1 Live (authoritative) — `advisor_engine.action_for`

Full "2-of-3" rule, `advisor_engine.py:715-799`, verified in full this session:

Three concern groups, each independently evaluated with an explicit `None`-safe check before
any threshold comparison (via a `_reading()` helper — the fail-open pattern the internal audit
flagged, `... or 0`/`... or 99`, is confirmed **absent** from the current function body):

| Group | Triggers (all thresholds are literals in the function body, confirmed by direct read) |
|---|---|
| `fundamentals` | any of `profitability`/`financial_health`/`accounting_quality`/`growth` category `< 45`; `interest_coverage < 2`; `accruals_ratio > 0.10` |
| `market_behavior` | `max_drawdown_252d < -30`; `relative_strength_20d < -10`; (`return_60d < -15` AND `return_20d < 0`) |
| `positioning` | ≥3 articles averaging sentiment `< -0.15`; `short_percent_of_float >= 0.15` |

```
agreement = count of groups with ≥1 triggered concern
agreement ≥ 2 and score < 45  → SELL,  trim 100%, strength "high"
agreement ≥ 2                 → TRIM,  trim 33% (2 groups) / 50% (3 groups), strength "moderate"
agreement == 1                → WATCH, trim 0%
stance in (ATTRACTIVE, PROMISING) and agreement == 0 → HOLD, strength "high"
else                           → HOLD, strength "moderate"
```

Every input that could not be evaluated is appended to an `unmeasured` list rather than
defaulting to "no concern" or "concern" — confirmed structurally: each check is
`if value is None: unmeasured.append(...) elif <threshold>: concerns[...].append(...)`, so a
missing input contributes to neither branch. Verified against THG: one unmeasured input
(`positioning.news_sentiment`), zero triggered concerns, `agreement_count: 0`, action `HOLD`.
There is no stop-loss, trailing stop, ATR rule, time stop, or re-entry rule anywhere in this
live function — `suggested_trim_pct` is a constant per branch (0/33/50/100), not computed from
position size or price.

`stance_for` (`advisor_engine.py:815-824`): gated first on `data_coverage < 0.45 →
"INSUFFICIENT DATA"`; else `score >= 75 → ATTRACTIVE`, `>= 60 → PROMISING`, `>= 45 → MIXED`,
else `CAUTION`. THG: `data_coverage 0.87`, `score 81.3` → `"ATTRACTIVE"`, confirmed matching the
published `stance` field exactly.

### 8.2 Shadow — `recommendation_policy_v2.py`, `shadow_mode: true` (confirmed in
`pipeline/config/recommendation_policy_v2.json`, and echoed in every published row's
`recommendation_v2.policy_mode: "shadow"` / `legacy_recommendation_unchanged: true`)

**Two-axis classification** (`two_axis_classification`, lines 65-97, verified in full):
compares `structural_score` and `timeliness_score` against `cfg["score_matrix"]` thresholds
(`recommendation_policy_v2.json`: `structural_strong: 75, structural_acceptable: 55,
timeliness_buy: 70, timeliness_tactical: 75, timeliness_acceptable: 55, timeliness_weak: 50`).
Critically, **`timeliness_score is None` is its own branch**, not a numeric comparison against
a substituted value: `structural >= 75 → "quality_watch_timeliness_unavailable"`;
`structural >= 55 → "hold_or_watch_timeliness_unavailable"`; else
`"avoid_or_sell_thesis"`. Verified exactly against THG (`structural effective_score` 74.7 or
74.5 [see the unresolved discrepancy noted in `TRACE_THG.md` §4] — either value is `>= 55` and
`< 75` — `timeliness_score: null` → `"hold_or_watch_timeliness_unavailable"`, matching the
published `matrix_classification` exactly).

**Stop-loss / floor logic** (`_stop_state`, lines 323-376, verified in full): reads a named
`stop_profile` from `config["stop_profiles"]` (default profile confirmed to exist; other named
profiles not enumerated this session). Two independent stop rules can fire:
- `hard_cost_basis_stop`: `threshold = cost_basis * (1 + hard_cost_basis_pct/100)`; triggers if
  `current_price <= threshold`.
- `trailing_high_water_stop`: threshold computed one of three ways depending on
  `profile["mode"]` — `atr_based` (`high_water_mark − atr_multiple × ATR`),
  `volatility_adjusted` (a realized-volatility-scaled decline, clamped between configured
  min/max trailing percentages), or a flat `trailing_high_water_pct` off the high-water mark.

Both rules require a configured number of "confirming closes" (`persistence_closes`) before
being treated as confirmed, not triggered on a single-day breach — the `first_breached_at` /
`confirmed_at` fields in the payload are for tracking this persistence requirement over time.
**This machinery exists, is fully implemented, and is not reachable by any live position in the
current artifact** because `position_action.classification: "no_position"` for every row with
no portfolio context (confirmed for THG: `position_rule_state.classification: "no_position"`,
`rules: {}`) — `_stop_state` returns the `no_position` short-circuit (line 324-325) before any
of the above logic runs when `position` is falsy. **The brief's requested NEM floor/recovery
example ($85.18 / $107.13) is NOT produced by this stop-loss machinery** — it is produced by an
entirely separate, frontend-only mechanism (`src/lib/dipWatch.js`), detailed next.

**Trim sizing** (`_trim_percent`, lines 388-416, verified in full): `computed = base_by_flag_
count[n] × severity_multiplier × confidence_multiplier × concentration_multiplier ×
liquidity_multiplier × (1.0 if urgent else tax_cost_multiplier)`, clamped to
`[minimum(0.10), maximum(0.75)]` once positive. Five independent multiplier tables, each
sourced from `recommendation_policy_v2.json`'s `trim` block (confirmed present with the exact
band values quoted in §0's config excerpt earlier this session:
`base_by_flag_count: {"2": 0.20, "3": 0.50}`, `severity_multipliers: {mild: 0.75, moderate: 1.0,
severe: 1.5}`, `confidence_multipliers: {limited: 0.50, normal: 0.85, high: 1.0}`,
`concentration_multipliers: {below_target: 0.75, near_target: 1.0, overweight: 1.25,
severely_overweight: 1.5}`, `liquidity_multipliers: {high: 0.85, normal: 1.0, low: 1.10}`,
`tax_cost_multipliers: {high: 0.60, normal: 0.85, low: 1.0}`).

**Entry/re-entry rules** (`evaluate_entry_rules`, lines 450-508, verified in full): four
mutually exclusive states — `reentry_after_stop` (requires cooldown days elapsed, a recorded
"recovery condition met" flag, and score requalification), `initial_buy` (requires
`company_label` in `buy/accumulate/tactical_candidate` and no portfolio/thesis block or
earnings blackout), `average_down` (only when currently losing on the position; requires
`structural_score >= structural_strong` AND a *resolved and non-weak* timeliness score — an
unresolved timeliness layer explicitly blocks averaging down, per the function's own comment,
"Unknown timing is not positive timing" — plus a `valuation_meaningfully_improved` flag, a
minimum interval since the last add, and a cap on total additions), and `add_to_winner`
(when not losing, requires `buy`/`accumulate` label).

**Portfolio fit** (`classify_portfolio_fit`, lines 286-320, verified in full): `below_target`
whenever `current_weight < target_weight × 0.75`. With no portfolio supplied, `current → 0.0`,
`target → default_target_weight (0.03)` — `0 < 0.0225` is always true, so **`below_target` is
guaranteed for every unpositioned name**, confirmed still true and confirmed still the published
value for THG. This one item from the internal audit's findings is **not fixed** — it is a
structural property of evaluating portfolio fit with no portfolio, not a bug that was patched
alongside the others in §0.

### 8.3 Floor and recovery levels — the actual mechanism (frontend, not the shadow policy)

`src/lib/dipWatch.js`, read in full this session. This is a **client-side, JavaScript**
computation over the already-published row — not part of the Python pipeline or the shadow
policy's stop-loss machinery in §8.2.

```
weekHigh = price / (1 + pct_from_52w_high/100)     // back-calculated from published fields
weekLow  = price / (1 + pct_above_52w_low/100)
drawdownFloor = weekHigh × (1 + max_drawdown_252d/100)      // if max_drawdown_252d available
longTermFloor = (weekLow + drawdownFloor) / 2                // else weekLow alone
longTermMax   = longTermFloor × 1.20                          // RECOVERY_GAIN_OFF_FLOOR = 0.20
recent        = {high, low} over the trailing 60 close prices (RECENT_WINDOW_DAYS)
floor = recent.low × 0.6 + longTermFloor × 0.4        // RECENT_WEIGHT = 0.6
max   = recent.high × 1.02 × 0.6 + longTermMax × 0.4   // BREAKOUT_BUFFER = 0.02
status = "recovering" if price >= max
         "near_floor"  if price <= floor × 1.05         // NEAR_FLOOR_BAND = 0.05
         "in_range"     otherwise
```

Gated to fire only when `stock.stance` is `ATTRACTIVE`/`PROMISING` (`ELIGIBLE_STANCES`) **and**
the stock is not already flagged `TRIM`/`SELL` by the live `action_for` recommendation **and**
is currently down ≥8% from its 52-week high with a non-positive 60-day return
(`DOWN_FROM_HIGH_THRESHOLD = -8`). All six constants (`-8, 0.20, 0.05, 60, 0.6, 0.02`) are
literals in this one file, not sourced from `settings.json` or any Python config — **this is a
fully independent, undocumented-outside-this-file threshold set from every other bounded
parameter in the system**, and I did not find any cross-reference or shared config linking it to
the modifier caps or band cutoffs described elsewhere in this document. This directly answers
the brief's NEM floor/recovery example request: reproducing NEM's specific published $85.18/
$107.13 figures would require NEM's actual `price`, `pct_from_52w_high`, `pct_above_52w_low`,
`max_drawdown_252d`, and 60-day close history as of the run that produced those numbers, none of
which were pulled this session — the **formula** above is fully verified; the **specific NEM
numbers** are UNDETERMINED without re-running this calculation against NEM's actual data.

---

## 9. Publication contract

**[PENDING — full JSON schema field-by-field walkthrough and frontend-consumption trace from
parallel research pass, including the "cheaper than approximately X% of peers" sentence's
current fate (already confirmed elsewhere in this document that the underlying percentile
mechanism was replaced by a ≥30-peer tier system — the parallel pass is confirming exactly how
this now renders, if at all, in `src/components/*.jsx`).]**

What's independently confirmed this session and stated with citation now:
- `pipeline/peer_groups.py` (full file read this session) no longer computes or exposes a
  percentage. Its output object's `peer_context` field is `None` below 30 valid peers
  (`MINIMUM_VALID_PEERS = 30`, line 36) and otherwise carries a `tier` (one of
  `cheapest_third`/`middle_third`/`most_expensive_third`) with a `tier_phrase` pre-written for
  display (`"in the cheapest third of"` etc., `TIER_LABELS`, lines 38-42) and an `ordinal`
  midpoint (16.7/50.0/83.3) rather than a computed percentile. THG's live `valuation_percentile`
  has `peer_context: null` (7 valid peers, below the 30 minimum).

---

## 10. Known defects and contradictions

### 10.1 The brief's four "already-confirmed" defects — current status (see §0 for commit mapping)

1. **Peer percentile on a 14-name set** — **fixed** (`cb3cc53`). Verified: ≥30-peer minimum now
   enforced, THG correctly publishes no peer claim.
2. **`EARNINGS_TIMELINESS` at 0% coverage defaulting to 50/100** — **fixed** (`ac24342`).
   Verified: `null`/`null` published for THG, guarded by `layer_health.assert_layers_vary`
   against recurrence (guard's actual mechanics not independently read this session —
   UNDETERMINED whether it runs in CI or only at publish time; flagged for follow-up).
3. **Confidence figures disagreeing between paths** — **open, reshaped** (`cd581b5` renamed but
   did not consolidate). Verified: 4-5 distinctly-named, distinctly-computed scalars persist on
   one row, detailed fully in §7. I judge this a transparency improvement, not a resolution.
4. **Insurer DSO scored while P/B and D/E unavailable** — **fixed, and inverted** (`0e0a9ad`).
   Verified: DSO now suppressed, P/B and D/E now applied, for THG specifically and structurally
   for the whole insurer profile via the shared applicability registry.

### 10.2 Defects found independently this session, not in the brief or the internal audit

5. **A "replacement metric" does not inherit the suppressed metric's weight.** Detailed in full
   in §5. The applicability rule's `replaced_by` field is descriptive metadata; the actual
   weight redistribution is a blind renormalization across whatever remains applicable, so a
   metric named as the intended substitute for a heavily-weighted suppressed metric (e.g.
   `price_to_book` "replacing" `ev_to_ebitda`'s 0.27 weight) receives only its own small
   configured weight (0.05), while the freed weight is spread across every surviving metric in
   the category, not concentrated on the named replacement. **Severity: moderate** — this means
   the applicability system's documentation-in-data (`replaced_by`) overstates how much the
   named replacement actually matters to the resulting score, which could mislead a reader of
   the payload (or of `docs/spec/METRIC_REGISTRY.md`, if that document reports `replaced_by`
   without this caveat) into thinking the replacement metric carries more weight than it does.
6. **Two profiles absent from `business_profiles.json`'s `profiles` object.**
   `classify_profile` can return `"semiconductor"` or `"other_pre_profit"`, both of which have
   real suppression rules in `applicability_matrix.json` (confirmed working, e.g. CRUS), but
   neither appears in `business_profiles.json`'s `profiles` dict, which `scoring_v2.py` reads
   for `replacement_metrics`/`critical_metrics`. **Severity: not yet established** — I confirmed
   the gap exists in the config files but did not trace whether `scoring_v2.py`'s fallback for a
   missing profile entry (`(BUSINESS_PROFILES.get("profiles") or {}).get(profile, {})`, which
   defaults to an empty dict) causes any visible degradation for a real semiconductor name in
   the current artifact, or is a harmless dead branch because nothing downstream requires those
   two profiles to have replacement/critical metrics declared. Flagged for follow-up, not
   asserted as a confirmed live defect.
7. **`portfolio_fit: below_target` is a structural constant for every unpositioned name** — this
   item from the internal audit is confirmed **not fixed** (§8.2), unlike its three siblings.
   Severity: low for the *score* (portfolio fit is not an input to the composite score) but
   directly affects position-sizing guidance display for any user without a matching portfolio
   entry, which given `portfolio_coverage` limitations (not yet quantified this session — see
   §11) may be most published names.
8. **THG's `effective_score` appears as two slightly different values in one payload**: `74.7`
   (`recommendation_v2.company.structural.effective_score`) vs. `74.5`
   (`analysis_v2.structural.effective_score`) — same conceptual computation, same input `raw_
   score: 90.5`, not yet root-caused. Both round from a computation of the form `50 + confidence
   × (raw − 50)`; a 0.2-point gap implies the two call sites use slightly different `confidence`
   inputs (0.61 vs. a marginally different value) despite both being fed from what appears to be
   the same `structural` block. **Not root-caused this session — flagged, not resolved.**
9. **Two different `suppressed_metrics` lists for the same THG row** (noted in
   `TRACE_THG.md` §5, not yet resolved): `fundamental_detail.suppressed_metrics` includes
   `sales_multiple` and excludes `trailing_revenue_growth`; `analysis_v2.applicability.
   suppressed_metrics` does the reverse. Likely explained by the `ALIASES` mapping in
   `scoring_v2.py:72-76` (`revenue_growth → trailing_revenue_growth`) operating on a different
   metric-ID namespace than the legacy path uses, but not confirmed by reading the producing
   code for `fundamental_detail.suppressed_metrics` this session.

### 10.3 Not yet investigated this session (candidates flagged by the internal audit, unverified either way)

The internal audit raised several further items — the enrichment feedback loop (statement-level
metrics only ever fetched for names a prior run already ranked highly), the 17%-of-universe
coverage cliff on `capital_allocation`/`accounting_quality`, cross-metric redundancy within the
market-behavior blend (`relative_strength_20d` vs. `return_20d`), and duplicated/dead guidance
implementations across `advisor_engine.action_for`, `recommendation_policy_v2`, and several
`src/lib/*.js` files. None of these were re-verified against current code this session. Given
how many of the audit's *other* claims turned out to be already fixed, **none of these should be
repeated as current fact without independent re-verification** — they are listed here only as a
follow-up checklist, explicitly not as confirmed findings.

---

## 11. Undetermined

Consolidated from every UNDETERMINED marker above, plus items not yet touched at all:

- Exact current per-modifier point caps for 8 of 9 champion-path modifiers (only the ±15
  combined cap is directly confirmed; §6.5).
- Whether `ranking_weights` (fundamentals 0.78/market_behavior 0.18/news_sentiment 0.04) is
  actually present in `settings.json` or is running on the hardcoded `DEFAULT_RANKING_WEIGHTS`
  fallback (§6.1) — the two are numerically identical in what was observed, so this doesn't
  change any number in this document, but it changes *how* a reader would edit the weight.
- Full TTM/annual/quarterly period-convention audit across all ~29 fundamental metrics (§4.3).
- `CrossSectionalNormalizer`'s internal winsorization/tie-handling logic, beyond what's visible
  in one published example row (§4.4).
- Whether `"replaced"` is ever assigned as an actual metric status anywhere in current code, or
  is dead code alongside `"suppressed"` (§5).
- Whether `business_profiles.json`'s missing `semiconductor`/`other_pre_profit` entries cause
  any visible degradation (§10.2 item 6).
- Root cause of the 74.7 vs. 74.5 `effective_score` discrepancy (§10.2 item 8).
- Root cause of the two different `suppressed_metrics` lists on one row (§10.2 item 9).
- Split/dividend adjustment handling in price history (`fetch_prices.py`, not opened this
  session).
- Everything in §10.3 (audit items not re-verified).
- All of §§1-3, 9, 12 pending the parallel research pass's completion and integration.

---

## 12. Test and validation inventory

**[PENDING — from parallel research pass: test file counts and coverage by module, whether any
test validates a financial formula against a known-correct value, and a direct check of whether
any backtest/IC/calibration result has ever actually been produced (vs. the gate simply never
opening, per §6.6's finding that `historical_calibration` is `null` for every row in the current
artifact).]**

Independently confirmed this session (§6.6): the live artifact's own published
`data_coverage_detail.limitations` states, for every row, "insufficient prospective calibration
history (requires 24 eligible IC periods)" — the system is, as of this run, self-reporting that
it has not been calibrated. This is not a test-suite finding; it's the running system's own
output, which is stronger evidence than a test result would be, since it reflects the actual
production state rather than a controlled test scenario.
