# ValueSignal — Metric Registry

Code-grounded, one-metric-per-entry registry. All formulas and citations were read directly from
the working tree this session; `settings.json` weight values were spot-checked directly and
match `ARCHITECTURE.md` §6 exactly.

**Correction to this task's own brief**: the fundamentals score covers **32 metrics, not ~29**.
`pipeline/scorer.py:231-240` (`SCORED_METRICS`) lists 8 valuation + 6 profitability + 5
financial_health + 5 growth + 4 capital_allocation + 4 accounting_quality = 32, matching
`research/features.py`'s own comment ("across all 32 scored metrics") and the fact that every
category's `metric_weights` in `settings.json` sums to exactly 1.0 over that count.

## How to read this document

Cutoffs for every fundamentals metric live at `pipeline/config/settings.json` →
`fundamentals.<metric_name>` (or `fundamentals.<metric>_by_sector` for `forward_pe`/
`sales_multiple`'s sector-banded bases). Scoring-function line numbers are all in
`pipeline/scorer.py`: `band_score` 91-102, `higher_is_better_score` 105-113,
`lower_is_better_score` 116-128, `range_score` 131-139, `multiple_score` 142-156, `altman_score`
196-209, `sales_multiple_score` 212-226; main assembly `_band_valuation_score` 538-623.

**Winsorization: confirmed absent everywhere in the champion `bands` path.** All six scoring
functions above are fixed-threshold table lookups with no percentile clipping. Winsorization
exists only in the `cross_sectional` **challenger** (`scorer.py:307-461`,
`CrossSectionalNormalizer._fit`, 1st/99th percentile per
`settings.json.challengers.cross_sectional_normalization`) — never consulted by the champion
score published to the frontend. **Population for normalization**: in `bands` mode there is no
reference population at all — every metric's score depends only on fixed absolute thresholds
(ARCHITECTURE.md §4.4). "Population" only exists for the `cross_sectional` challenger (sector
distribution if ≥8 members else full universe, `scorer.py:317,426-429`).

`Eff. wt` = `0.78 × category_weight × metric_weight` for fundamentals metrics, `0.18 × sub_weight`
for market_behavior (subject to the `relative_strength` override noted below), and N/A for
news_sentiment/timeliness (single-scalar layers, or shadow-only).

---

## A. Valuation (`category_weight = 0.28`)

| Metric | Direction | Wt in factor | Eff. wt in composite |
|---|---|---|---|
| ev_to_ebitda | lower_is_better (`multiple_score`, `scorer.py:563`) | 0.27 | **5.90%** |
| ev_to_fcf | lower_is_better (`scorer.py:565`) | 0.18 | 3.93% |
| forward_pe | lower_is_better (`scorer.py:558`) | 0.15 | 3.28% |
| ev_to_ebit | lower_is_better (`scorer.py:564`) | 0.12 | 2.62% |
| peg | lower_is_better (`band_score`, `scorer.py:557`) | 0.09 | 1.97% |
| sales_multiple | lower_is_better (`sales_multiple_score`, `scorer.py:212-226,559`) | 0.09 | 1.97% |
| price_to_book | lower_is_better (`band_score`, `scorer.py:561`) | 0.05 | 1.09% |
| price_to_tangible_book | lower_is_better (`band_score`, `scorer.py:562`) | 0.05 | 1.09% |

- **ev_to_ebitda**: `EV / TTM_EBITDA` if EBITDA>0. EV = `info["enterpriseValue"]` or
  `market_cap + total_debt − cash`; guard: result discarded if >500 (scale-mismatch guard).
  Computed `fundamentals_extended.py:479-516` (`derive_enterprise_multiples`), banded
  `scorer.py:563`. Cutoffs `settings.json.fundamentals.ev_to_ebitda`
  (`suspicious_below:3, cheap_max:10, healthy_max:15, elevated_max:22`). Source: derived from
  Yahoo statements + `info`, no configured fallback provider. Units: multiple. Period:
  **UNDETERMINED/likely inconsistent** — EBITDA is built from annual income-statement lines but
  the Observation is stamped `is_ttm=False` regardless (`fundamentals_extended.py:697`), a real
  TTM-labeling gap. Missing → excluded from category weight base. Suppressed for:
  `bank, property_casualty_insurer, life_insurer, diversified_insurer` (→`price_to_book`). Not
  `required_for_score` anywhere. Display: `MetricSections.jsx:29`, label **"EV/EBITDA"**.

- **ev_to_fcf**: `EV / TTM_FCF`, same EV construction. `fundamentals_extended.py:512`, banded
  `scorer.py:565`. Suppressed for P&C/life/diversified insurers (→`price_to_book`). **No explicit
  bank rule found in `applicability_matrix.json`** for this metric (every other EV multiple has
  one) — UNDETERMINED whether this is a real gap or an intentional omission. Display: **"EV/FCF"**.

- **forward_pe**: `price / consensus_FY1_EPS`, raw Yahoo `forwardPE` field, no recomputation
  (`canonical_metrics.py:233`). Sector-specific bands,
  `settings.json.fundamentals.forward_pe_by_sector`. Source chain (one of only 6 metrics with an
  explicit one): `provider_reconciliation.json` = `["calculated_from_canonical_inputs",
  "alpha_vantage","yahoo"]`. `is_forward=True`, `stale_after_days: 14`. Suppressed for reit
  (→price_to_ffo), pre_profit_biotech, other_pre_profit. **Champion/shadow suppression-surface
  divergence**: the metric registry's own `applicability_profiles` (`metric_registry.json:65`)
  omits `profitable_biotechnology`/`semiconductor` — relevant only to the shadow path
  (`applicability_for` consults this registry fallback), since the legacy `scorer.py` path
  (`canonical_metrics.suppressed_metrics`) only reads explicit `applicability_matrix.json` rules
  and never consults the registry fallback at all. Display: **"Forward P/E"**.

- **peg**: canonical formula `forward_pe / expected_eps_growth_points`
  (`canonical_metrics.calculate_peg`, lines 81-92) — rejects (`None`) rather than substitutes
  when growth ≤0, periods mismatched, or definition unknown; clamps to `[-20,50]`. The **legacy**
  scored metric instead uses the raw Yahoo `trailingPegRatio` scalar (flagged
  `unknown_growth_definition_and_horizon`, diagnostic only), scored via `band_score`, bucketed
  0/1/1.5/2/3. The shadow path recomputes PEG from scratch (`scoring_v2.py:89-96`) — so
  `analysis_v2`'s PEG can legitimately differ from `fundamental_detail.peg`. Suppressed for
  bank/P&C/life/diversified insurer (→forward_pe), reit(→price_to_ffo),
  commodity_producer(**replaced**→midcycle_ev_ebitda), pre_profit_biotech(→cash_runway_months),
  other_pre_profit(→gross_margin_and_runway). Display: **"PEG"**.

- **sales_multiple**: synthetic, not a single raw field. `sales_multiple_score`
  (`scorer.py:212-226`) prefers `ev_to_sales` (sector-banded), falls back to `price_to_sales`
  (sector-banded) if EV/Sales unavailable — basis recorded in `sales_multiple_basis`.
  `ev_to_sales` computed `fundamentals_extended.py:511`; `price_to_sales` is raw Yahoo
  `priceToSalesTrailing12Months`, `is_ttm=True`. **`ev_to_sales` is absent from
  `EXTENDED_METRIC_UNITS`**, so it carries no canonical-Observation lineage — in the shadow path
  this metric is aliased to `price_to_sales` only (`scoring_v2.ALIASES:75`) and never the
  EV-based value, even when the legacy score actually used the EV-based one. **A real
  champion/shadow scoring-basis mismatch, newly found this session.** Not shown in the UI under
  this name — the UI shows the raw `ev_to_sales`/`price_to_sales` fields instead.

- **price_to_book**: `market_cap / common_equity`, raw Yahoo `priceToBook`, one of the 6 metrics
  with an explicit provider chain (`["calculated_from_canonical_inputs","yahoo",
  "alpha_vantage"]`). **Required for score** (category-withholding) for
  `property_casualty_insurer, life_insurer, diversified_insurer, reit` — its absence zeroes the
  entire `valuation` category for those 4 profiles rather than renormalizing. Suppressed only for
  `pre_profit_biotechnology`. Display: **"P/B"**.

- **price_to_tangible_book**: `market_cap / (equity − goodwill − intangibles)`
  (`fundamentals_extended.py:493-495,513-514`). **Not governed by `applicability_matrix.json` at
  all** — a separate, hardcoded gate lives directly in `scorer.py:180-181,254-258`
  (`TANGIBLE_BOOK_SECTORS = (Financial Services, Financials, Financial, Real Estate, Utilities,
  Energy, Basic Materials, Materials, Industrials)`), applied whenever the ticker's sector is in
  that tuple OR `business_profiles.json` names it a replacement metric. **This is the one metric
  in the system whose suppression logic is a code-level tuple, not a config table** —
  inconsistent with `canonical_metrics.suppressed_metrics`'s own "one authority" docstring claim.
  **Required for score** for `bank` only. Display: **"P/Tangible book"**.

## B. Profitability (`category_weight = 0.26`)

| Metric | Direction | Wt in factor | Eff. wt |
|---|---|---|---|
| return_on_invested_capital | higher_is_better (`scorer.py:568`) | 0.26 | **5.27%** |
| gross_profits_to_assets | higher_is_better (`scorer.py:572`) | 0.22 | 4.46% |
| free_cash_flow_yield | higher_is_better (`scorer.py:575`) | 0.16 | 3.24% |
| cash_conversion | higher_is_better (`scorer.py:574`) | 0.16 | 3.24% |
| return_on_equity | higher_is_better (`scorer.py:566`) | 0.10 | 2.03% |
| profit_margin | higher_is_better (`scorer.py:576`) | 0.10 | 2.03% |

- **return_on_invested_capital**: `NOPAT / avg(invested_capital)`;
  `NOPAT = EBIT × (1 − effective_tax_rate)`; `invested_capital = debt + equity − cash`
  (`fundamentals_extended.py:161-184`). **Tax rate falls back to the statutory 0.21 literal** if
  the computed effective rate is outside `[0,0.6]` (lines 163-165) — a genuine imputation, newly
  documented in §4.5 below. Suppressed for bank(→ROE), P&C/life/diversified(→normalized_roe),
  reit(→same_store_noi_growth), pre_profit_biotech(→pipeline_stage). Display: **"ROIC"**.
- **gross_profits_to_assets**: `gross_profit / avg(total_assets)` (Novy-Marx measure),
  `fundamentals_extended.py:341-357`. Suppressed for bank(→net_interest_margin),
  P&C/life/diversified(→underwriting_income), commodity_producer(→lifting_production_cost).
- **free_cash_flow_yield**: `freeCashflow / marketCap`, raw Yahoo fields, `is_ttm=True`
  (`canonical_metrics.py:269-275`). No statement-derived alternative exists — relies solely on
  the Yahoo quote-level field. Suppressed for bank(→P/B), P&C/life/diversified
  (→total_capital_return_yield), **replaced** for utility(→funds_from_operations_yield),
  pre_profit_biotech(→cash_runway_months).
- **cash_conversion**: `FCF / net_income`, requires net_income>0 else `None` (a deliberate
  rejection, `fundamentals_extended.py:187-196`). Suppressed for P&C/life/diversified
  (→combined_ratio).
- **return_on_equity**: raw Yahoo `returnOnEquity`, `is_ttm=True`. No applicability-matrix
  suppression rule found for any profile (always "applied" on the legacy path).
- **profit_margin**: raw Yahoo `profitMargins`, `is_ttm=True`. **Dual role**: also the sole input
  to `classify_profile`'s pre-profit branch (`profit_margin < 0`, `canonical_metrics.py:123,128`)
  — this metric doubles as a profile-classification input, not just a scored one.

## C. Financial health (`category_weight = 0.15`)

| Metric | Direction | Wt | Eff. wt |
|---|---|---|---|
| interest_coverage | higher_is_better (`scorer.py:580`) | 0.30 | **3.51%** |
| net_debt_to_ebitda | lower_is_better (`scorer.py:581`) | 0.24 | 2.81% |
| debt_to_equity | lower_is_better (`band_score`, `scorer.py:578`) | 0.18 | 2.11% |
| altman_z | higher_is_better (`altman_score`, `scorer.py:583`) | 0.18 | 2.11% |
| current_ratio | higher_is_better (`scorer.py:579`) | 0.10 | 1.17% |

- **interest_coverage**: `EBIT / |interest_expense|`; **imputed to `99.0`** when interest is
  `None` or `|interest|<1` and EBIT>0 (`fundamentals_extended.py:264-266` — "no debt service
  reads as maximum comfort," a documented imputation, newly found this session). Also a direct
  input to `advisor_engine.action_for`'s deterioration rule (`<2 → fundamentals concern`, line
  743-744) — **used twice with different cutoffs**: a 0-100 band (excellent≥12/good≥6/fair≥3/
  weak≥1.5) for scoring, and a flat `<2` threshold for guidance.
- **net_debt_to_ebitda**: `(total_debt − cash) / EBITDA`, requires EBITDA>0
  (`fundamentals_extended.py:269-277`). Suppressed for bank(→capital_ratio), P&C/life/diversified
  (→debt_to_capital).
- **debt_to_equity**: Yahoo `debtToEquity` **divided by 100** (`canonical_metrics.py:261-267` —
  Yahoo reports it as a percentage where 80 means 0.8×; this transform is load-bearing and
  undocumented in the raw payload). **Required for score** for `property_casualty_insurer,
  life_insurer, diversified_insurer, bank` — one of only two metrics (with `price_to_book`/
  `price_to_tangible_book`) whose absence zeroes a whole category for those profiles.
- **altman_z**: variant-dependent 4-5-term weighted sum (`fundamentals_extended.py:280-338`); `z`
  (1968 original, manufacturing) vs `z_double_prime` (non-manufacturer revision), chosen by
  sector. **Financials get `(None,None)` unconditionally** — `derive_altman_z` returns nulls for
  `FINANCIAL_SECTORS` regardless of applicability-matrix rules, **a second, independent
  suppression mechanism at the derivation layer**, redundant with but separate from the
  config-driven bank/insurer rules. Requires ≥4 of 5 (`z`) or ≥3 of 4 (`z''`) component ratios,
  else `None` — not partial credit. Suppressed also for reit, profitable_biotechnology,
  pre_profit_biotechnology.
- **current_ratio**: raw Yahoo `currentRatio`. Suppressed for bank, P&C/life/diversified
  (→risk_based_capital_ratio), reit(→fixed_charge_coverage).

## D. Growth (`category_weight = 0.11`)

| Metric | Direction | Wt | Eff. wt |
|---|---|---|---|
| revenue_growth | higher_is_better (`scorer.py:584`) | 0.26 | **2.23%** |
| fcf_growth_3y | higher_is_better (`scorer.py:586`) | 0.22 | 1.89% |
| earnings_growth | higher_is_better (`scorer.py:585`) | 0.20 | 1.72% |
| operating_margin_trend | higher_is_better (`scorer.py:587-588`) | 0.16 | 1.37% |
| earnings_surprise | higher_is_better (`scorer.py:590`) | 0.16 | 1.37% |

- **revenue_growth**: raw Yahoo `revenueGrowth`, `is_ttm=True`. Aliased to
  `trailing_revenue_growth` in the shadow path — whose own registry entry restricts
  `applicability_profiles` to `general, utility, commodity_producer, pre_profit_biotechnology,
  other_pre_profit` (`metric_registry.json:191`), meaning **the shadow path suppresses this
  metric for banks/insurers/REITs/biotech via the registry fallback even though the legacy path
  never does** — a second confirmed champion/shadow divergence, same shape as `forward_pe`'s.
- **fcf_growth_3y**: CAGR of FCF across every annual period on file (3-4y), requires ≥3 periods.
  Suppressed for commodity_producer(→free_cash_flow_breakeven).
- **earnings_growth**: raw Yahoo `earningsGrowth` (internally `quarterly_eps_growth`, flagged
  `not_forward_growth`). Aliased to `trailing_eps_growth` in shadow path.
- **operating_margin_trend**: `current_op_margin − prior_op_margin`
  (`fundamentals_extended.py:225-245`). Suppressed for commodity_producer
  (→normalized_midcycle_margin — "trailing margin trend for a producer is the realized commodity
  price, not structural improvement").
- **earnings_surprise**: weighted average of last 4 quarters' surprise %, weights
  `[0.4,0.3,0.2,0.1]` newest-first (`fundamentals_extended.py:519-540`). **Dual role**: the same
  raw field also feeds the shadow **timeliness** layer via a completely different formula (see
  section I) — one raw value, two independent scoring transforms in two layers.

## E. Capital allocation (`category_weight = 0.10`)

| Metric | Direction | Wt | Eff. wt |
|---|---|---|---|
| net_buyback_yield | higher_is_better (`scorer.py:591`) | 0.34 | **2.65%** |
| stock_comp_to_revenue | lower_is_better (`scorer.py:592`) | 0.28 | 2.18% |
| asset_growth | ideal_range (`range_score`, `scorer.py:596`) | 0.22 | 1.72% |
| capex_to_depreciation | ideal_range (`range_score`, `scorer.py:593`) | 0.16 | 1.25% |

- **net_buyback_yield**: `−(diluted_shares_now/diluted_shares_prior − 1)`, i.e. share-count
  shrink net of dilution (`fundamentals_extended.py:454-469`).
- **stock_comp_to_revenue**: `|stock_comp| / revenue` (`fundamentals_extended.py:471`).
- **asset_growth**: `total_assets_now/total_assets_prior − 1`. `range_score`: ideal
  `[-0.02, 0.12]` scores 100, acceptable `[-0.12,0.25]` scores 65, else 25 — **both too-fast and
  too-slow asset growth are penalized** (Fama-French CMA-style investment factor).
- **capex_to_depreciation**: `|capex| / |depreciation|`. `range_score`, ideal `[0.9,1.8]`,
  acceptable `[0.6,2.8]`. Suppressed for bank(→efficiency_ratio), P&C/life/diversified
  (→book_value_growth), **semiconductor**(→gross_margin_cycle — confirmed live for CRUS).

## F. Accounting quality (`category_weight = 0.10`)

| Metric | Direction | Wt | Eff. wt |
|---|---|---|---|
| piotroski_f | higher_is_better (`scorer.py:600`) | 0.45 | **3.51%** |
| accruals_ratio | lower_is_better (`scorer.py:599`) | 0.22 | 1.72% |
| days_sales_outstanding_trend | lower_is_better (`scorer.py:601-602`) | 0.17 | 1.33% |
| inventory_days_trend | lower_is_better (`scorer.py:603`) | 0.16 | 1.25% |

- **piotroski_f**: 9-point binary composite, **rescaled to `9 × sum(answered)/len(answered)`** if
  ≥6 of 9 tests resolve, else `None` (`fundamentals_extended.py:374-406`) — this rescaling is
  itself a form of imputation-by-proxy: a company answering only 6 tests and passing 5 gets
  `9×5/6=7.5`, treated identically to a company answering all 9 with the same pass-rate, with no
  confidence discount reaching the score itself. Suppressed for bank(→CET1 ratio), P&C/life/
  diversified(→combined_ratio).
- **accruals_ratio**: `(net_income − operating_cash_flow) / avg(total_assets)`.
- **days_sales_outstanding_trend** / **inventory_days_trend**: year-over-year fractional drift in
  DSO/inventory-days levels. Both suppressed for bank and P&C/life/diversified — insurers hold no
  inventory and receivable days don't represent underwriting quality (the exact defect `0e0a9ad`
  fixed). `inventory_days_trend` also suppressed for semiconductor(→inventory_cycle).

## G. Market behavior (composite weight 0.18; sub-weights `settings.json.market_behavior.weights`)

| Sub-metric | Formula | Wt | Eff. wt (of 100) |
|---|---|---|---|
| momentum_12_1 | `(close[-21]/close[-253]−1)×100`, 12-month return skipping the last month; `clamp(50+momentum×1.2)`. Falls back to `return_60d` if <253 closes. | 0.30 | **5.40%** |
| risk_adjusted | `0.65×ratio_to_score(Sortino) + 0.35×ratio_to_score(Sharpe)`, `ratio_to_score(neutral=0,span=1.5)`. Trailing 252 sessions, min 20 obs. | 0.26 | 4.68% |
| relative_strength | `ret_20d(stock) − ret_20d(SPY)`, `clamp(50+relative×3)`. | 0.16 nominal | **0% effective on champion** — see note below |
| drawdown_resilience | `100/(1+depth)`, `depth=|min(0,dd)|/25` over 252d max drawdown. | 0.14 | 2.52% |
| volume_confirmation | Up-day/down-day dollar-volume ratio, trailing 60 sessions, capped 3.0; `clamp(35+(ratio−1)×55)`. | 0.08 | 1.44% |
| low_beta | `100/(1+distance²)`, `distance=|beta−0.85|/0.55` — rewards beta near 0.85, not minimal beta (betting-against-beta). | 0.06 | 1.08% |
| technical_extended | Equal-weighted average of 4 resolved sub-indicators (MA slope, RSI, Bollinger %B, OBV slope). | 0.06 | 1.08% |

**`relative_strength`'s nominal 0.16 weight does not apply on the live champion score.**
`settings.json`'s top-level `short_horizon_treatment: "neutral"` causes
`technical_score_from_parts` (`advisor_engine.py:207-234`) to drop this weight entirely and
renormalize the remaining 6 (sum 0.90) up to 1.0. A config comment (`settings.json:1299`) states
the reason: `relative_strength` is Spearman +1.00 rank-correlated with `return_20d` by
construction and was "drawing 16% of this blend for a signal already present." A reader of
`settings.json.market_behavior.weights` alone would wrongly assume 16% applies.

Direction: all 7 map higher-composite-score = better (raw inputs like drawdown/volatility are
pre-negated before mapping). No winsorization. No cross-sectional normalization (fixed formulas).
Missing-value: `technical_score_from_parts` renormalizes over whichever sub-scores resolved; if
none resolve, `market_behavior` drops from the composite blend entirely. **Not governed by
`applicability_matrix.json` at all** — that file is fundamentals-only; ETFs still receive a
`market_behavior` component (only `fundamentals` is null for `is_etf` rows). Display: the raw
underlying inputs (return_20d, sortino_ratio, max_drawdown_252d, etc.) are shown in
`MetricSections.jsx`'s "Behaviour & tradability" section — **the composite 0-100 sub-scores
themselves have no dedicated UI label found in `src/`**.

## H. News / sentiment layer (composite weight 0.04)

Single aggregate scalar, not decomposed. `advisor_engine.sentiment_score` (`advisor_engine.py:
237-249`) → `news_intelligence.weighted_sentiment` (`news_intelligence.py:129-219`).

**Formula**: for each eligible article (entity-matched, confidence ≥0.25, within a 7-day window),
`weight = recency_weight × source_quality_weight × content_type_weight × entity_confidence`,
`recency_weight = exp(-ln2 × age_days / 3)` (3-day half-life). `average = Σ(sentiment×weight)/
Σ(weight)`. `score = clamp(50 + average×100, 0, 100)`. **If no article clears the filters, returns
`(None, {news_available:False})` — not a fabricated neutral 50.**

Source: Marketaux primary (`ticker_sentiment[].ticker_sentiment_score`/`relevance_score`), RSS
fallback per `pipeline/fetch_news.py` (not read this session). Deduplicated by title-similarity
≥0.82. Units: 0-100 score (underlying `average` is signed `[-1,1]`). No winsorization/
normalization. Missing-value: layer drops from the composite blend entirely, renormalized among
fundamentals/market_behavior. Not applicability-matrix-governed — applies universally including
ETFs. Published: `components.news_sentiment` (`null` for THG — no news this row). Display: no
dedicated glossary entry found in `MetricSections.jsx` — UNDETERMINED for exact display
component.

## I. Timeliness layer (shadow-only; `scoring_v2.py:169-240`; feeds `analysis_v2.timeliness`, never the champion score)

| Metric | Formula | Weight in `timing_raw` |
|---|---|---|
| forward_eps_revision_30d | `revision_score = clamp(50 + revision×5, 0, 100)`, `revision` = % change in consensus FY1 EPS over 30 calendar days. `required_normalized_inputs: [forward_eps_fy1_now, forward_eps_fy1_30d_ago]`, `stale_after_days: 7`. | 0.70 |
| earnings_surprise | `surprise_score = clamp(50 + surprise×2, 0, 100)` — **same raw field as the fundamentals `growth` category's `earnings_surprise` (weight 0.16 there), but a completely different transform here.** | 0.30 |

`timing_raw` = weighted average over whichever of the two resolved, renormalized if one is
missing (`pipeline/layer_health.renormalize`). `timing_confidence = timing_coverage × (0.85 if
observations else 0.55)` (line 180 — hardcoded literals, no config reference, same pattern as
the structural layer's 0.72/0.55). `timing_effective = 50 + timing_confidence×(timing_raw−50)` if
`timing_raw` resolves, else `None` — **confirmed no 50.0 fallback** (the `ac24342` fix). Both
inputs unresolved for THG (`coverage: 0.0`, both scores `null`). Direction: higher-is-better for
both. No winsorization/normalization. Missing-value: publishes `null` with an explicit
`unavailable_reason` string (no free provider for broad consensus estimates; earnings-surprise
collection is opt-in via `ENABLE_EARNINGS_SURPRISE`). Not applicability-matrix-governed — data
*availability*, not applicability, gates this layer. Display: `AnalysisLayers.jsx` — exact
tooltip copy UNDETERMINED, not read line-by-line this session.

## J. Structural layer (shadow-only; `scoring_v2.build_v2_analysis`) — not a separate metric set

Re-scores the same 32 fundamentals metrics plus the canonically-recomputed `peg`, using the same
`settings.json` category/metric weights, via `ALIASES` (`revenue_growth→trailing_revenue_growth`,
`earnings_growth→trailing_eps_growth`, `sales_multiple→price_to_sales`, `scoring_v2.py:72-76`).
Differs from the champion path in: (1) requires an actual `Observation` lineage row — a legacy
scalar with no matching Observation is discarded, not scored; (2) applicability resolved via
`applicability_for` (rule-first, **registry-fallback-second** — the mechanism creating the
champion/shadow divergences documented above for `forward_pe`/`trailing_revenue_growth`);
(3) confidence uses a hardcoded `provenance_reliability = 0.72 if observations else 0.55` minus
stale/conflict penalties, not the champion's `0.65+0.35×coverage`; (4) `effective_score = 50 +
confidence×(raw−50)`, a mean-reversion toward 50 the champion path never applies.

---

## Notes for whoever reads this next

1. **32, not ~29, fundamentals metrics** — corrects this task's own brief; `scorer.py:231-240` is
   authoritative.
2. **Genuinely new imputation/suppression findings this session** (all also logged in
   `registry.json`'s `defaults` array and cross-referenced into `ARCHITECTURE.md` §4.5/§10): the
   0.21 statutory-tax-rate fallback in `derive_roic`; the `interest_coverage=99.0` imputation;
   `derive_altman_z`'s independent, code-level financial-sector suppression; `piotroski_f`'s
   6-of-9 partial-coverage rescaling; `price_to_tangible_book`'s hardcoded `TANGIBLE_BOOK_SECTORS`
   tuple sitting outside `applicability_matrix.json`'s stated single authority; and at least two
   confirmed champion/shadow suppression-surface divergences (`forward_pe`,
   `trailing_revenue_growth`) caused by `applicability_for`'s registry-fallback branch, which
   `canonical_metrics.suppressed_metrics` (the legacy path) never consults.
3. **Winsorization**: zero exceptions confirmed — no fundamentals metric winsorizes on the
   champion `bands` path.
4. **Remaining UNDETERMINED**: TTM/annual/quarterly period convention for most
   `fundamentals_extended.py`-derived metrics (Observations are written `is_ttm=False` uniformly
   even where the underlying figure is economically TTM-like); display label/tooltip for the 7
   market-behavior composite sub-scores, `news_sentiment`, and both timeliness metrics (the UI
   surfaces their *raw* underlying inputs, not the 0-100 composite scores); exact fallback
   provider chain for any field absent from `provider_reconciliation.json`'s 6-entry table (only
   `revenue_ttm`, `market_cap`, `forward_eps_fy1`, `forward_pe`, `current_ratio`, `price_to_book`
   have an explicit chain — every other metric is effectively single-source).

See `docs/spec/registry.json` for the machine-readable version, including the full numeric
weight hierarchy and the exhaustive `defaults` (imputation) list.
