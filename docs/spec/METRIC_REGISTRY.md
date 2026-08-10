# ValueSignal Metric Registry
Code-grounded specification of every metric that feeds ValueSignal's fundamentals, market-behavior, and news-sentiment scoring, plus the canonical/v2-only and profile-replacement metrics declared in config but not (yet) computed. Every claim below cites the `file:line` it was read from. Where verification was not possible from the code actually read, the field says `UNDETERMINED` with a one-line reason rather than guessing.

Companion machine-readable file: `docs/spec/registry.json` (same fields, plus a top-level `weights` block and a `defaults` array of every silent-default site found feeding a score or decision).

**Scope note on `defaults`.** The audit swept the modules the task named explicitly (`scorer.py`, `advisor_engine.py`, `scoring_v2.py`, `recommendation_policy_v2.py`, `peer_groups.py`, `data_coverage.py`, `technical_indicators.py`, `risk_metrics.py`) plus every module those modules call into for the champion score and its modifiers (`fundamentals_extended.py`, `fetch_advisor.py`, `fetch_prices.py`, `canonical_metrics.py`, `insider_signal.py`, `institutional_ownership.py`, `congress_signal.py`, `concentration_risk.py`, `geographic_exposure.py`, `plausibility.py`, `news_intelligence.py`, `layer_health.py`, `peer_groups.py`). It is a thorough sweep of the scoring/decision pipeline, not a literal grep of all 116 files under `pipeline/`; see the closing report for exact counts.

---

## 1. Weight hierarchy (numeric, with citations)

### 1.1 Top-level ranking weights

| Component | Weight | Source |
|---|---|---|
| fundamentals | 0.78 | `pipeline/config/settings.json` `ranking_weights.fundamentals`; read/merged `pipeline/advisor_engine.py:32,42` |
| market_behavior | 0.18 | `pipeline/config/settings.json` `ranking_weights.market_behavior` |
| news_sentiment | 0.04 | `pipeline/config/settings.json` `ranking_weights.news_sentiment` |

Source detail: pipeline/config/settings.json 'ranking_weights' (fundamentals 0.78, market_behavior 0.18, news_sentiment 0.04); DEFAULT_RANKING_WEIGHTS fallback at pipeline/advisor_engine.py:32; merged at pipeline/advisor_engine.py:35-42 (_weights, RANKING_WEIGHTS); applied at pipeline/advisor_engine.py:846-867 (blend_research_components).

### 1.2 Fundamentals category weights (sum to 1.0)

| Category | Weight |
|---|---|
| valuation | 0.28 |
| profitability | 0.26 |
| financial_health | 0.15 |
| growth | 0.11 |
| capital_allocation | 0.1 |
| accounting_quality | 0.1 |

Source: pipeline/config/settings.json fundamentals.category_weights; read by pipeline/scorer.py:24,546 (cfg=SETTINGS['fundamentals']); applied at pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])).

### 1.3 Fundamentals metric weights within each category (each category sums to 1.0)

**valuation** (sums to 1.0)

| Metric | Weight in category | Effective weight in composite (`ranking_weights.fundamentals × category_weight × metric_weight`) |
|---|---|---|
| peg | 0.09 | 0.019656 |
| forward_pe | 0.15 | 0.032760 |
| sales_multiple | 0.09 | 0.019656 |
| price_to_book | 0.05 | 0.010920 |
| price_to_tangible_book | 0.05 | 0.010920 |
| ev_to_ebitda | 0.27 | 0.058968 |
| ev_to_ebit | 0.12 | 0.026208 |
| ev_to_fcf | 0.18 | 0.039312 |

**profitability** (sums to 1.0)

| Metric | Weight in category | Effective weight in composite (`ranking_weights.fundamentals × category_weight × metric_weight`) |
|---|---|---|
| return_on_equity | 0.1 | 0.020280 |
| return_on_invested_capital | 0.26 | 0.052728 |
| gross_profits_to_assets | 0.22 | 0.044616 |
| cash_conversion | 0.16 | 0.032448 |
| free_cash_flow_yield | 0.16 | 0.032448 |
| profit_margin | 0.1 | 0.020280 |

**financial_health** (sums to 1.0)

| Metric | Weight in category | Effective weight in composite (`ranking_weights.fundamentals × category_weight × metric_weight`) |
|---|---|---|
| interest_coverage | 0.3 | 0.035100 |
| net_debt_to_ebitda | 0.24 | 0.028080 |
| debt_to_equity | 0.18 | 0.021060 |
| current_ratio | 0.1 | 0.011700 |
| altman_z | 0.18 | 0.021060 |

**growth** (sums to 1.0)

| Metric | Weight in category | Effective weight in composite (`ranking_weights.fundamentals × category_weight × metric_weight`) |
|---|---|---|
| revenue_growth | 0.26 | 0.022308 |
| earnings_growth | 0.2 | 0.017160 |
| fcf_growth_3y | 0.22 | 0.018876 |
| operating_margin_trend | 0.16 | 0.013728 |
| earnings_surprise | 0.16 | 0.013728 |

**capital_allocation** (sums to 1.0)

| Metric | Weight in category | Effective weight in composite (`ranking_weights.fundamentals × category_weight × metric_weight`) |
|---|---|---|
| net_buyback_yield | 0.34 | 0.026520 |
| stock_comp_to_revenue | 0.28 | 0.021840 |
| capex_to_depreciation | 0.16 | 0.012480 |
| asset_growth | 0.22 | 0.017160 |

**accounting_quality** (sums to 1.0)

| Metric | Weight in category | Effective weight in composite (`ranking_weights.fundamentals × category_weight × metric_weight`) |
|---|---|---|
| accruals_ratio | 0.22 | 0.017160 |
| piotroski_f | 0.45 | 0.035100 |
| days_sales_outstanding_trend | 0.17 | 0.013260 |
| inventory_days_trend | 0.16 | 0.012480 |

Source: pipeline/config/settings.json fundamentals.metric_weights.<category>; read by pipeline/scorer.py:24,546; applied per-category at pipeline/scorer.py:526-534 (weighted_available(metrics, weights) inside _categories_with_required_gate).

### 1.4 Market-behavior sub-weights

**Declared** (`pipeline/config/settings.json` `market_behavior.weights`) sum to **1.06**, not 1.00 -- this does not break scoring because `technical_score_from_parts` always divides by the sum of weights actually present (`pipeline/advisor_engine.py:231-233`), but the raw table is not itself a share-of-one table.

**Production-effective** (as fraction of `market_behavior`'s own 0.18, under the **currently configured** `short_horizon_treatment = "neutral"`, `pipeline/config/settings.json`): `relative_strength` is popped out of the weight table entirely -- not merely reweighted when missing, but structurally absent on every row -- and the remaining six sub-metrics' declared weights (summing to 0.90) are renormalized over that 0.90. See `pipeline/advisor_engine.py:207-234` (`technical_score_from_parts`) and the `market_behavior.weights` comment block in `settings.json`, which explains why: `relative_strength` (`ret_20d - benchmark_ret_20d`) is rank-identical to `return_20d` ("Spearman +1.00 across 877 published rows") and was double-counting a signal already present elsewhere.

| Sub-metric | Declared weight (settings.json) | Effective share of `market_behavior`'s 0.18 under production default (`neutral`) | Effective share under `legacy_momentum` (all 7 present, denominator 1.06) |
|---|---|---|---|
| momentum_12_1 | 0.3 | 0.060000 | 0.050943 |
| risk_adjusted | 0.26 | 0.052000 | 0.044151 |
| relative_strength | 0.16 | 0.000000 | 0.027170 |
| drawdown_resilience | 0.14 | 0.028000 | 0.023774 |
| volume_confirmation | 0.08 | 0.016000 | 0.013585 |
| low_beta | 0.06 | 0.012000 | 0.010189 |
| technical_extended | 0.06 | 0.012000 | 0.010189 |

### 1.5 News sentiment

Single metric, no sub-weights: effective weight in composite = `ranking_weights.news_sentiment` = **0.04**.

### 1.6 Cross-cutting notes on the weight hierarchy

1. **No separate "Quality"/"Value" factor layer exists beyond the six fundamentals categories.** `pipeline/scoring_v2.py:79-154` (`build_v2_analysis`) reuses the exact same six category names read from `SETTINGS['fundamentals']['metric_weights']` (`pipeline/scoring_v2.py:99-105`) -- it does not introduce a different taxonomy. What v2 adds is an orthogonal second axis, `timeliness` (`forward_eps_revision_30d` + `earnings_surprise`, weighted 0.7/0.3, `pipeline/scoring_v2.py:169-182`), which is shadow-only, never read by the champion `advisor_engine.build_research` path, and -- per the module's own docstring -- almost always unavailable in practice because `forward_eps_revision_30d` is never populated by any fetch module (confirmed by grep; see that metric's entry below).
2. **`short_horizon_treatment` materially changes the true market_behavior weights** (see 1.4) and this is easy to miss because the raw `settings.json` weight table alone suggests `relative_strength` carries 16% of market_behavior when in the current configuration it carries 0%.
3. **The frontend's "bull/bear thesis" gauge uses a different, hardcoded 40/30/20/10 split** (`src/lib/bullBearScore.js:1-17`: Fundamentals 0.4, Price behavior 0.3, News sentiment 0.2, Risk quality 0.1) that has no relationship to the backend's published `ranking_weights` (78/18/4) or `market_behavior.weights`. It reads the same `components.fundamentals` / `components.market_behavior` / `components.news_sentiment` / `technical_detail.risk_adjusted` fields the champion score already computed, but recombines them under its own weights for a separate 0-10 display gauge (`src/components/StockDetailModal.jsx:220-240`, whose caption text "40% fundamentals · 30% price behavior · 20% news sentiment · 10% risk quality" is literally describing `bullBearScore.js`'s weights, not the backend composite score shown a few lines above it in the same component). This is a real, verifiable divergence between two numbers with overlapping names in the same product, not a scoring bug in either individual formula.
4. **A `semiconductor` applicability-matrix gap exists but only affects the v2/shadow layer.** `pipeline/canonical_metrics.py:121-122` (`classify_profile`) assigns the profile `"semiconductor"` to companies whose sector/industry text contains "semiconductor", and `pipeline/config/applicability_matrix.json:325-336` has a `rules.semiconductor` block (two suppression rules: `capex_to_depreciation`, `inventory_days_trend`). But the file's top-level `profiles` enumeration (`applicability_matrix.json:3-15`) does **not** include `"semiconductor"`, and neither does `metric_registry.json`'s `declaration_defaults.applicability_profiles` list that every auto-expanded metric inherits (`pipeline/canonical_metrics.py:27-40`). `canonical_metrics.applicability_for()` (`pipeline/canonical_metrics.py:141-150`) falls through to `"suppressed"` with reason `"Metric registry does not declare this profile applicable"` for **any metric without an explicit semiconductor rule** -- which is every fundamentals metric except the two named above. Consequence: `scoring_v2.build_v2_analysis`'s `structural` score for a semiconductor company is built almost entirely from suppressed inputs in the v2/shadow layer. The **live champion score is unaffected** -- `pipeline/canonical_metrics.py:153-171` (`suppressed_metrics`, the function the champion path actually calls via `scorer.py:252`) only consults the explicit per-profile `rules` dict and has no registry-allowlist fallback, so it suppresses only `capex_to_depreciation`/`inventory_days_trend` for semiconductors, exactly as intended. This is a genuine config/code inconsistency, confined to the shadow layer.

---

## 2. Fundamentals metrics

### Valuation (category weight 0.28)

### peg

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** band_score(lower_is_better=True): value<0 -> 15.0; else tiered 100/75/50/25 by <=excellent_max/<=good_max/<=fair_max/<=poor_max, else 10.0 (pipeline/scorer.py:91-102)
- **code_reference:** pipeline/scorer.py:557 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: band_score)
- **source_field:** Alpha Vantage OVERVIEW.PEGRatio (primary) / Yahoo info.trailingPegRatio or info.pegRatio (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:633-646 merge_snapshots(primary=alpha_vantage overview_snapshot, fallback=yahoo fetch_snapshot): Alpha Vantage PEGRatio wins when present (pipeline/fetch_advisor.py:621), else Yahoo trailingPegRatio then pegRatio (pipeline/fetch_prices.py:97). Note: this raw provider PEG is what the champion scores; canonical_metrics.calculate_peg (a stricter forward-inputs-only recomputation) exists only in the scoring_v2.py shadow layer and never overrides the champion's snap['peg'].
- **units:** multiple
- **period_convention:** Provider-declared, unvalidated by the champion path (Alpha Vantage/Yahoo do not disclose the growth horizon behind PEGRatio/trailingPegRatio/pegRatio)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.09
- **effective_weight_in_composite:** 0.019656 (1.9656% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.peg (0.09); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better (band_score default lower_is_better=True, pipeline/scorer.py:557)
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, reit, commodity_producer(replaced), pre_profit_biotechnology, other_pre_profit
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** PEG
- **display_tooltip:** Growth-adjusted earnings multiple
- **notes:** cfg cutoffs: excellent_max 1.0, good_max 1.5, fair_max 2.0, poor_max 3.0 (settings.json fundamentals.peg). The v2/shadow layer treats this provider PEG as diagnostic-only and quality-flags it 'unknown_growth_definition_and_horizon' (pipeline/canonical_metrics.py:234,249) -- the champion score does not apply that caution.

### forward_pe

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** multiple_score: value<=0 -> 5.0; 0<value<suspicious_below -> 60.0 (value-trap flag); <=cheap_max -> 100; <=healthy_max -> 80; <=elevated_max -> 45; else 15.0 (pipeline/scorer.py:142-156)
- **code_reference:** pipeline/scorer.py:558 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: multiple_score)
- **source_field:** Alpha Vantage OVERVIEW.ForwardPE (primary) / Yahoo info.forwardPE (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:619 (Alpha Vantage) then pipeline/fetch_prices.py:95 (Yahoo forwardPE), merged via merge_snapshots.
- **units:** multiple
- **period_convention:** forward (next-fiscal-year consensus per canonical_metrics.py:233 declaration; Yahoo/Alpha Vantage do not independently confirm the horizon)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.15
- **effective_weight_in_composite:** 0.032760 (3.2760% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.forward_pe (0.15); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** reit, pre_profit_biotechnology, other_pre_profit
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Forward P/E
- **display_tooltip:** Price against next year's earnings
- **notes:** Sector-specific bands: cfg['forward_pe_by_sector'][sector] falling back to ['default'] (settings.json fundamentals.forward_pe_by_sector; default suspicious_below 5, cheap_max 15, healthy_max 25, elevated_max 40) -- pipeline/scorer.py:549.

### sales_multiple

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** multiple_score: value<=0 -> 5.0; 0<value<suspicious_below -> 60.0 (value-trap flag); <=cheap_max -> 100; <=healthy_max -> 80; <=elevated_max -> 45; else 15.0 (pipeline/scorer.py:142-156)
- **code_reference:** pipeline/scorer.py:559 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: multiple_score via sales_multiple_score)
- **source_field:** Derived at score time: snap['ev_to_sales'] preferred, else snap['price_to_sales']
- **source_provider:** yahoo (ev_to_sales, statement-derived, shortlist-only) preferred; alpha_vantage/yahoo (price_to_sales) fallback
- **fallback_chain:** pipeline/scorer.py:212-226 sales_multiple_score: prefers snap['ev_to_sales'] (fundamentals_extended.derive_enterprise_multiples, shortlist-only statement derivation) and falls back to snap['price_to_sales'] (Alpha Vantage PriceToSalesRatioTTM, pipeline/fetch_advisor.py:617, no Yahoo fallback field set in fetch_prices.py) when EV/Sales is unavailable.
- **units:** multiple
- **period_convention:** TTM for price_to_sales basis (Alpha Vantage 'PriceToSalesRatioTTM'); annual-statement basis for ev_to_sales (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.09
- **effective_weight_in_composite:** 0.019656 (1.9656% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.sales_multiple (0.09); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** No single UI label for the composite 'sales_multiple' key itself -- the frontend instead renders the two underlying raw fields it can be built from separately as 'EV/Sales' and 'P/S' (src/components/MetricSections.jsx:32-33); which one the score actually used is recorded in fundamental_detail.sales_multiple_basis (pipeline/scorer.py:284,622) but that basis field is not itself rendered anywhere I found in src/. Sector bands: ev_to_sales_by_sector / price_to_sales_by_sector (settings.json), default ev cheap_max 1.5/healthy_max 3.5/elevated_max 8.5; default price cheap_max 1.0/healthy_max 3.0/elevated_max 8.0.

### price_to_book

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** band_score(lower_is_better=True): value<0 -> 15.0; else tiered 100/75/50/25 by <=excellent_max/<=good_max/<=fair_max/<=poor_max, else 10.0 (pipeline/scorer.py:91-102)
- **code_reference:** pipeline/scorer.py:561 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: band_score)
- **source_field:** Alpha Vantage OVERVIEW.PriceToBookRatio (primary) / Yahoo info.priceToBook (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:618 (Alpha Vantage) then pipeline/fetch_prices.py:94 (Yahoo priceToBook).
- **units:** multiple
- **period_convention:** Latest-quarter book equity vs point-in-time market cap (per canonical_metrics.py:159-167 declaration); provider period not independently confirmed
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.05
- **effective_weight_in_composite:** 0.010920 (1.0920% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.price_to_book (0.05); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** pre_profit_biotechnology
- **required_for_parent_score:** property_casualty_insurer (valuation), life_insurer (valuation), diversified_insurer (valuation), reit (valuation)
- **published_to_frontend:** True
- **display_label:** P/B
- **display_tooltip:** Price against reported book value
- **notes:** cutoffs: excellent_max 1.0, good_max 3.0, fair_max 6.0, poor_max 10.0.

### price_to_tangible_book

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** band_score(lower_is_better=True): value<0 -> 15.0; else tiered 100/75/50/25 by <=excellent_max/<=good_max/<=fair_max/<=poor_max, else 10.0 (pipeline/scorer.py:91-102)
- **code_reference:** pipeline/scorer.py:562 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: band_score)
- **source_field:** Derived: market_cap / (common equity - goodwill - intangibles), annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_enterprise_multiples), shortlist-only
- **fallback_chain:** No cross-provider fallback -- computed only from Yahoo annual statement frames; None when the shortlist enrichment did not run for this ticker or equity<=0.
- **units:** multiple
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.05
- **effective_weight_in_composite:** 0.010920 (1.0920% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.price_to_tangible_book (0.05); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** bank (valuation)
- **published_to_frontend:** True
- **display_label:** P/Tangible book
- **display_tooltip:** Book value with goodwill stripped out - the honest one for financials
- **notes:** Applicability for this one metric is NOT governed by applicability_matrix.json's 'rules' block (it has no entry there for any profile) -- it is special-cased inside pipeline/scorer.py:applicability() (lines 253-259). It is SCORED (not suppressed) only when the profile's business_profiles.json 'replacement_metrics' list names it (bank, property_casualty_insurer, life_insurer, diversified_insurer per pipeline/config/business_profiles.json) OR the row's sector string is one of TANGIBLE_BOOK_SECTORS = ('Financial Services','Financials','Financial','Real Estate','Utilities','Energy','Basic Materials','Materials','Industrials') (pipeline/scorer.py:180-181). Suppressed otherwise -- e.g. a general tech/software company, a REIT profile (not listed as a replacement-metric profile despite 'Real Estate' sector membership potentially overlapping), commodity_producer, biotech, etc. cutoffs: excellent_max 1.5, good_max 3.0, fair_max 6.0, poor_max 12.0.

### ev_to_ebitda

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** multiple_score: value<=0 -> 5.0; 0<value<suspicious_below -> 60.0 (value-trap flag); <=cheap_max -> 100; <=healthy_max -> 80; <=elevated_max -> 45; else 15.0 (pipeline/scorer.py:142-156)
- **code_reference:** pipeline/scorer.py:563 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: multiple_score)
- **source_field:** Derived: enterprise_value / EBITDA, annual statements (with info fallback for EV/EBITDA components)
- **source_provider:** yahoo (fundamentals_extended.derive_enterprise_multiples), shortlist-only
- **fallback_chain:** No cross-provider fallback. None when shortlist enrichment did not run, EBITDA<=0, or the multiple exceeds the 500x sanity guard (pipeline/fundamentals_extended.py:497-500).
- **units:** multiple
- **period_convention:** Annual statement EBITDA vs point-in-time enterprise value (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.27
- **effective_weight_in_composite:** 0.058968 (5.8968% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.ev_to_ebitda (0.27); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** EV/EBITDA
- **display_tooltip:** Whole-company price against operating profit - debt included. The best-validated single value multiple in the published research
- **notes:** cutoffs: suspicious_below 3.0, cheap_max 10.0, healthy_max 15.0, elevated_max 22.0.

### ev_to_ebit

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** multiple_score: value<=0 -> 5.0; 0<value<suspicious_below -> 60.0 (value-trap flag); <=cheap_max -> 100; <=healthy_max -> 80; <=elevated_max -> 45; else 15.0 (pipeline/scorer.py:142-156)
- **code_reference:** pipeline/scorer.py:564 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: multiple_score)
- **source_field:** Derived: enterprise_value / EBIT, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_enterprise_multiples), shortlist-only
- **fallback_chain:** No cross-provider fallback. None when shortlist enrichment did not run or EBIT<=0.
- **units:** multiple
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.12
- **effective_weight_in_composite:** 0.026208 (2.6208% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.ev_to_ebit (0.12); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** EV/EBIT
- **display_tooltip:** The same multiple without the depreciation add-back, so capital intensity cannot hide in it
- **notes:** cutoffs: suspicious_below 4.0, cheap_max 12.0, healthy_max 18.0, elevated_max 26.0.

### ev_to_fcf

- **factor:** valuation
- **layer:** fundamentals
- **formula_as_implemented:** multiple_score: value<=0 -> 5.0; 0<value<suspicious_below -> 60.0 (value-trap flag); <=cheap_max -> 100; <=healthy_max -> 80; <=elevated_max -> 45; else 15.0 (pipeline/scorer.py:142-156)
- **code_reference:** pipeline/scorer.py:565 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: multiple_score)
- **source_field:** Derived: enterprise_value / free cash flow, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_enterprise_multiples), shortlist-only
- **fallback_chain:** No cross-provider fallback. None when shortlist enrichment did not run or FCF<=0.
- **units:** multiple
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.18
- **effective_weight_in_composite:** 0.039312 (3.9312% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.valuation (0.28) and fundamentals.metric_weights.valuation.ev_to_fcf (0.18); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** EV/FCF
- **display_tooltip:** Whole-company price against actual cash generated
- **notes:** cutoffs: suspicious_below 5.0, cheap_max 18.0, healthy_max 28.0, elevated_max 45.0.

### Profitability (category weight 0.26)

### return_on_equity

- **factor:** profitability
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:566 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Alpha Vantage OVERVIEW.ReturnOnEquityTTM (primary) / Yahoo info.returnOnEquity (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:622 (Alpha Vantage) then pipeline/fetch_prices.py:101 (Yahoo returnOnEquity).
- **units:** decimal
- **period_convention:** TTM (Alpha Vantage field name confirms; Yahoo's returnOnEquity period is undocumented but canonical_metrics.py:238 flags it is_ttm=True in the v2 Observation lineage)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.1
- **effective_weight_in_composite:** 0.020280 (2.0280% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.profitability (0.26) and fundamentals.metric_weights.profitability.return_on_equity (0.1); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** ROE
- **display_tooltip:** Return on shareholder equity only - flattered by debt
- **notes:** cutoffs: excellent_min 0.20, good_min 0.15, fair_min 0.10, weak_min 0.05.

### return_on_invested_capital

- **factor:** profitability
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:568-569 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: NOPAT / average invested capital, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_roic), shortlist-only
- **fallback_chain:** No cross-provider fallback. Effective tax rate defaults to 0.21 (statutory federal) when the filed rate is missing or outside [0,0.6] (pipeline/fundamentals_extended.py:161-165) -- see registry.json 'defaults'.
- **units:** decimal
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.26
- **effective_weight_in_composite:** 0.052728 (5.2728% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.profitability (0.26) and fundamentals.metric_weights.profitability.return_on_invested_capital (0.26); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, reit, pre_profit_biotechnology
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** ROIC
- **display_tooltip:** Return on every dollar of capital, debt and equity alike
- **notes:** cutoffs: excellent_min 0.20, good_min 0.13, fair_min 0.08, weak_min 0.04.

### gross_profits_to_assets

- **factor:** profitability
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:572-573 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: gross profit / average total assets, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_gross_profits_to_assets), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.22
- **effective_weight_in_composite:** 0.044616 (4.4616% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.profitability (0.26) and fundamentals.metric_weights.profitability.gross_profits_to_assets (0.22); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, commodity_producer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Gross profits / assets
- **display_tooltip:** Profitability measured above the line where accounting discretion operates - about as predictive as book-to-market, and complementary to it
- **notes:** cutoffs: excellent_min 0.33, good_min 0.22, fair_min 0.13, weak_min 0.06.

### cash_conversion

- **factor:** profitability
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:574 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: TTM free cash flow / positive TTM net income, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_cash_conversion), shortlist-only
- **fallback_chain:** No cross-provider fallback. None when net income<=0.
- **units:** decimal
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.032448 (3.2448% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.profitability (0.26) and fundamentals.metric_weights.profitability.cash_conversion (0.16); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Cash conversion
- **display_tooltip:** Free cash flow per dollar of reported net income
- **notes:** cutoffs: excellent_min 1.0, good_min 0.8, fair_min 0.6, weak_min 0.35.

### free_cash_flow_yield

- **factor:** profitability
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:575 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Yahoo info.freeCashflow / info.marketCap (yahoo-only; not present in Alpha Vantage OVERVIEW)
- **source_provider:** yahoo only
- **fallback_chain:** pipeline/fetch_prices.py:104 -- computed directly in fetch_snapshot(); Alpha Vantage's overview_snapshot sets no free_cash_flow_yield key, so merge_snapshots never overrides it (it can only fill a None).
- **units:** decimal
- **period_convention:** TTM free cash flow over point-in-time market cap (per canonical_metrics.py:138-146 declaration)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.032448 (3.2448% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.profitability (0.26) and fundamentals.metric_weights.profitability.free_cash_flow_yield (0.16); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, reit(replaced), utility(replaced), pre_profit_biotechnology
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** FCF yield
- **display_tooltip:** Free cash flow against market value
- **notes:** cutoffs: excellent_min 0.08, good_min 0.05, fair_min 0.02, weak_min 0.0.

### profit_margin

- **factor:** profitability
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:576 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Alpha Vantage OVERVIEW.ProfitMargin (primary) / Yahoo info.profitMargins (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:623 (Alpha Vantage) then pipeline/fetch_prices.py:102 (Yahoo profitMargins).
- **units:** decimal
- **period_convention:** TTM (Alpha Vantage 'ProfitMargin'; Yahoo profitMargins period undocumented, flagged is_ttm=True in v2 lineage, canonical_metrics.py:239)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.1
- **effective_weight_in_composite:** 0.020280 (2.0280% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.profitability (0.26) and fundamentals.metric_weights.profitability.profit_margin (0.1); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Net margin
- **display_tooltip:** Bottom-line profit per dollar of revenue
- **notes:** cutoffs: excellent_min 0.20, good_min 0.12, fair_min 0.06, weak_min 0.0.

### Financial health (category weight 0.15)

### interest_coverage

- **factor:** financial_health
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:580 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: EBIT / |interest expense|, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_interest_coverage), shortlist-only
- **fallback_chain:** No cross-provider fallback. When interest expense is None or under $1 (absolute), returns a hardcoded 99.0 if EBIT>0 (treated as maximum comfort / no debt service) else None -- pipeline/fundamentals_extended.py:259-266. See registry.json 'defaults'.
- **units:** multiple
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.3
- **effective_weight_in_composite:** 0.035100 (3.5100% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.financial_health (0.15) and fundamentals.metric_weights.financial_health.interest_coverage (0.3); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Interest coverage
- **display_tooltip:** Operating profit per dollar of interest owed
- **notes:** cutoffs: excellent_min 12.0, good_min 6.0, fair_min 3.0, weak_min 1.5.

### net_debt_to_ebitda

- **factor:** financial_health
- **layer:** fundamentals
- **formula_as_implemented:** lower_is_better_score: value<=excellent_max -> 100; <=good_max -> 80; <=fair_max -> 55; <=poor_max -> 30; else 10.0. Never penalizes negative values (unlike band_score) (pipeline/scorer.py:116-128)
- **code_reference:** pipeline/scorer.py:581-582 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: lower_is_better_score)
- **source_field:** Derived: (total debt - cash) / EBITDA, annual statements with info-field fallback for each component
- **source_provider:** yahoo (fundamentals_extended.derive_net_debt_to_ebitda), shortlist-only
- **fallback_chain:** Statement EBITDA/debt/cash each individually fall back to info.get('ebitda')/info.get('totalDebt')/info.get('totalCash') (pipeline/fundamentals_extended.py:269-277) when the statement line is missing. None when EBITDA<=0.
- **units:** multiple
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.24
- **effective_weight_in_composite:** 0.028080 (2.8080% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.financial_health (0.15) and fundamentals.metric_weights.financial_health.net_debt_to_ebitda (0.24); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better (explicit LOWER_IS_BETTER_METRICS membership, pipeline/scorer.py:183-188)
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Net debt/EBITDA
- **display_tooltip:** Years of operating profit needed to clear net debt
- **notes:** cutoffs: excellent_max 0.5, good_max 1.5, fair_max 3.0, poor_max 4.5.

### debt_to_equity

- **factor:** financial_health
- **layer:** fundamentals
- **formula_as_implemented:** band_score(lower_is_better=True): value<0 -> 15.0; else tiered 100/75/50/25 by <=excellent_max/<=good_max/<=fair_max/<=poor_max, else 10.0 (pipeline/scorer.py:91-102)
- **code_reference:** pipeline/scorer.py:578 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: band_score)
- **source_field:** Yahoo info.debtToEquity (yahoo-only; not present in Alpha Vantage OVERVIEW)
- **source_provider:** yahoo only
- **fallback_chain:** pipeline/fetch_prices.py:79,99 -- Yahoo reports debtToEquity as a percentage (80 means 0.8x); fetch_snapshot divides by 100 before publishing. No Alpha Vantage source exists for this field.
- **units:** multiple
- **period_convention:** Latest-quarter (per canonical_metrics.py:31 metric_inventory declaration); Yahoo's own period is undocumented
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.18
- **effective_weight_in_composite:** 0.021060 (2.1060% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.financial_health (0.15) and fundamentals.metric_weights.financial_health.debt_to_equity (0.18); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** property_casualty_insurer (financial_health), life_insurer (financial_health), diversified_insurer (financial_health), bank (financial_health)
- **published_to_frontend:** True
- **display_label:** Debt/equity
- **display_tooltip:** Leverage against book equity
- **notes:** cutoffs: excellent_max 0.5, good_max 1.0, fair_max 2.0, poor_max 3.0.

### current_ratio

- **factor:** financial_health
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:579 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Yahoo info.currentRatio (yahoo-only; not present in Alpha Vantage OVERVIEW)
- **source_provider:** yahoo only
- **fallback_chain:** pipeline/fetch_prices.py:100 -- no Alpha Vantage source exists for this field.
- **units:** multiple
- **period_convention:** Latest-quarter (canonical_metrics.py:117-125 declaration); Yahoo's own period undocumented
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.1
- **effective_weight_in_composite:** 0.011700 (1.1700% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.financial_health (0.15) and fundamentals.metric_weights.financial_health.current_ratio (0.1); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, reit
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Current ratio
- **display_tooltip:** Short-term assets against short-term bills
- **notes:** cutoffs: excellent_min 2.0, good_min 1.5, fair_min 1.0, weak_min 0.75.

### altman_z

- **factor:** financial_health
- **layer:** fundamentals
- **formula_as_implemented:** altman_score: dispatches to higher_is_better_score using the band table for the sector-fitted variant (z or z_double_prime); returns None if no variant assigned (financials) (pipeline/scorer.py:196-209)
- **code_reference:** pipeline/scorer.py:583 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: altman_score)
- **source_field:** Derived composite (working capital, retained earnings, EBIT, equity/liabilities, [asset turnover for the 'z' variant]), annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_altman_z), shortlist-only
- **fallback_chain:** No cross-provider fallback. Variant selection (z vs z_double_prime) is itself sector-driven and independent of applicability_matrix.json: altman_variant_for() returns None for FINANCIAL_SECTORS (('Financial Services','Financials','Financial')), 'z' for MANUFACTURING_SECTORS, else 'z_double_prime' (pipeline/fundamentals_extended.py:280-284) -- this is a second, code-level suppression mechanism layered on top of the applicability_matrix.json rule that ALSO suppresses altman_z for bank/insurer profiles.
- **units:** score (raw composite; scored via higher_is_better_score into 0-100 against the variant's own band table)
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.18
- **effective_weight_in_composite:** 0.021060 (2.1060% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.financial_health (0.15) and fundamentals.metric_weights.financial_health.altman_z (0.18); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, reit, profitable_biotechnology, pre_profit_biotechnology
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Altman Z-score
- **display_tooltip:** Composite bankruptcy risk, computed with the variant fitted for this sector - the original manufacturing model or Altman's non-manufacturer revision. Suppressed for financials, where it has no meaning
- **notes:** z bands: excellent_min 3.0, good_min 2.6, fair_min 1.8, weak_min 1.1. z_double_prime bands: excellent_min 2.6, good_min 2.0, fair_min 1.1, weak_min 0.5 (settings.json fundamentals.altman_z).

### Growth (category weight 0.11)

### revenue_growth

- **factor:** growth
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:584 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Alpha Vantage OVERVIEW.QuarterlyRevenueGrowthYOY (primary) / Yahoo info.revenueGrowth (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:624 (Alpha Vantage) then pipeline/fetch_prices.py:105 (Yahoo revenueGrowth).
- **units:** decimal
- **period_convention:** MIXED BY PROVIDER: Alpha Vantage's field is explicitly quarterly year-over-year (flagged 'quarterly_not_ttm' in the v2 Observation lineage, pipeline/fetch_advisor.py:598-599); Yahoo's revenueGrowth period is undocumented by Yahoo and is asserted is_ttm=True only inside canonical_metrics.yahoo_observations (pipeline/canonical_metrics.py:240) -- a v2-shadow-only lineage, not a verification. The champion's raw snap['revenue_growth'] carries no period marker at all.
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.26
- **effective_weight_in_composite:** 0.022308 (2.2308% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.growth (0.11) and fundamentals.metric_weights.growth.revenue_growth (0.26); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Revenue growth
- **display_tooltip:** Year-over-year revenue change
- **notes:** cutoffs: excellent_min 0.20, good_min 0.10, fair_min 0.03, weak_min 0.0. scoring_v2.py:73 aliases this to canonical id 'trailing_revenue_growth' for the shadow layer.

### earnings_growth

- **factor:** growth
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:585 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Alpha Vantage OVERVIEW.QuarterlyEarningsGrowthYOY (primary) / Yahoo info.earningsGrowth (fallback)
- **source_provider:** alpha_vantage primary, yahoo fallback
- **fallback_chain:** pipeline/fetch_advisor.py:625 (Alpha Vantage) then pipeline/fetch_prices.py:106 (Yahoo earningsGrowth).
- **units:** decimal
- **period_convention:** MIXED BY PROVIDER, same caveat as revenue_growth. The v2 lineage additionally flags Yahoo's equivalent field 'not_forward_growth' (pipeline/canonical_metrics.py:251-252).
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.2
- **effective_weight_in_composite:** 0.017160 (1.7160% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.growth (0.11) and fundamentals.metric_weights.growth.earnings_growth (0.2); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Earnings growth
- **display_tooltip:** Year-over-year earnings change
- **notes:** cutoffs: excellent_min 0.20, good_min 0.10, fair_min 0.03, weak_min 0.0. scoring_v2.py:74 aliases this to canonical id 'trailing_eps_growth'.

### fcf_growth_3y

- **factor:** growth
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:586 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: FCF CAGR across every annual period on file (3-4 in practice, requires >=3)
- **source_provider:** yahoo (fundamentals_extended.derive_fcf_growth), shortlist-only
- **fallback_chain:** No cross-provider fallback. None when fewer than 3 annual FCF observations exist.
- **units:** decimal
- **period_convention:** Multi-year annual CAGR (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.22
- **effective_weight_in_composite:** 0.018876 (1.8876% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.growth (0.11) and fundamentals.metric_weights.growth.fcf_growth_3y (0.22); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** commodity_producer(replaced)
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** FCF growth (3y)
- **display_tooltip:** Compound annual free-cash-flow growth
- **notes:** cutoffs: excellent_min 0.15, good_min 0.08, fair_min 0.02, weak_min -0.05.

### operating_margin_trend

- **factor:** growth
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:587-588 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: current operating margin - comparable prior-period margin, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_margins), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal (percentage-point change)
- **period_convention:** Annual statement, year-over-year (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.013728 (1.3728% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.growth (0.11) and fundamentals.metric_weights.growth.operating_margin_trend (0.16); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** commodity_producer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Margin trend
- **display_tooltip:** Year-over-year change - direction beats level
- **notes:** cutoffs: excellent_min 0.02, good_min 0.005, fair_min -0.005, weak_min -0.02.

### earnings_surprise

- **factor:** growth
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:590 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: weighted average of the last 4 quarters' surprise_pct, newest weighted 0.4/0.3/0.2/0.1
- **source_provider:** yahoo (ticker_obj.earnings_dates scrape via fundamentals_extended.derive_earnings_surprise), shortlist-only, OPT-IN
- **fallback_chain:** No cross-provider fallback. Additionally gated behind an environment flag: collection only runs when ENABLE_EARNINGS_SURPRISE is truthy (pipeline/fetch_advisor.py:472); off by default. The module comment records that the first production run resolved 0/40 companies on this endpoint (pipeline/fetch_advisor.py:466-471).
- **units:** percentage_points (surprise_pct as reported, not converted from a decimal)
- **period_convention:** Trailing four reported quarters
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.013728 (1.3728% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.growth (0.11) and fundamentals.metric_weights.growth.earnings_surprise (0.16); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Earnings surprise
- **display_tooltip:** Recent quarters against expectations, newest weighted heaviest. Beating expectations carries drift in a way trailing growth alone does not
- **notes:** cutoffs: excellent_min 8.0, good_min 3.0, fair_min 0.0, weak_min -5.0.

### Capital allocation (category weight 0.1)

### net_buyback_yield

- **factor:** capital_allocation
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:591 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: -1 * (diluted/basic share count change year over year), annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_capital_allocation), shortlist-only
- **fallback_chain:** No cross-provider fallback. Prefers balance-sheet 'shares_outstanding' history, falls back to income-statement 'diluted_shares' when fewer than 2 balance-sheet observations exist (pipeline/fundamentals_extended.py:455-457).
- **units:** decimal
- **period_convention:** Annual statement, year-over-year (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.34
- **effective_weight_in_composite:** 0.026520 (2.6520% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.capital_allocation (0.1) and fundamentals.metric_weights.capital_allocation.net_buyback_yield (0.34); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Net buyback yield
- **display_tooltip:** Share count change over the year, net of dilution - positive means your stake grew
- **notes:** cutoffs: excellent_min 0.03, good_min 0.01, fair_min 0.0, weak_min -0.02.

### stock_comp_to_revenue

- **factor:** capital_allocation
- **layer:** fundamentals
- **formula_as_implemented:** lower_is_better_score: value<=excellent_max -> 100; <=good_max -> 80; <=fair_max -> 55; <=poor_max -> 30; else 10.0. Never penalizes negative values (unlike band_score) (pipeline/scorer.py:116-128)
- **code_reference:** pipeline/scorer.py:592 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: lower_is_better_score)
- **source_field:** Derived: |stock-based compensation| / revenue, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_capital_allocation), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.28
- **effective_weight_in_composite:** 0.021840 (2.1840% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.capital_allocation (0.1) and fundamentals.metric_weights.capital_allocation.stock_comp_to_revenue (0.28); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Stock comp / revenue
- **display_tooltip:** The dilution cost GAAP earnings hide
- **notes:** cutoffs: excellent_max 0.01, good_max 0.03, fair_max 0.07, poor_max 0.12.

### capex_to_depreciation

- **factor:** capital_allocation
- **layer:** fundamentals
- **formula_as_implemented:** range_score: ideal_min<=value<=ideal_max -> 100; acceptable_min<=value<=acceptable_max -> 65; else 25.0 (pipeline/scorer.py:131-139)
- **code_reference:** pipeline/scorer.py:593 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: range_score)
- **source_field:** Derived: |capex| / |depreciation & amortization|, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_capital_allocation), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** multiple
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.012480 (1.2480% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.capital_allocation (0.1) and fundamentals.metric_weights.capital_allocation.capex_to_depreciation (0.16); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** range/ideal-band (RANGE_METRICS membership, pipeline/scorer.py:193)
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, semiconductor(not in top-level profiles enum -- see notes)
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Capex / depreciation
- **display_tooltip:** Under 1x flatters near-term cash flow and starves the business
- **notes:** cutoffs: ideal_min 0.9, ideal_max 1.8, acceptable_min 0.6, acceptable_max 2.8.

### asset_growth

- **factor:** capital_allocation
- **layer:** fundamentals
- **formula_as_implemented:** range_score: ideal_min<=value<=ideal_max -> 100; acceptable_min<=value<=acceptable_max -> 65; else 25.0 (pipeline/scorer.py:131-139)
- **code_reference:** pipeline/scorer.py:596 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: range_score)
- **source_field:** Derived: total assets(t) / total assets(t-1) - 1, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_asset_growth), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal
- **period_convention:** Annual statement, year-over-year (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.22
- **effective_weight_in_composite:** 0.017160 (1.7160% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.capital_allocation (0.1) and fundamentals.metric_weights.capital_allocation.asset_growth (0.22); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** range/ideal-band
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Asset growth
- **display_tooltip:** Total balance-sheet expansion year over year. Aggressive growth has historically preceded weak returns, and shrinking is not a virtue either - both tails count against
- **notes:** cutoffs: ideal_min -0.02, ideal_max 0.12, acceptable_min -0.12, acceptable_max 0.25.

### Accounting quality (category weight 0.1)

### accruals_ratio

- **factor:** accounting_quality
- **layer:** fundamentals
- **formula_as_implemented:** lower_is_better_score: value<=excellent_max -> 100; <=good_max -> 80; <=fair_max -> 55; <=poor_max -> 30; else 10.0. Never penalizes negative values (unlike band_score) (pipeline/scorer.py:116-128)
- **code_reference:** pipeline/scorer.py:599 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: lower_is_better_score)
- **source_field:** Derived: (net income - operating cash flow) / average total assets, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_accruals_ratio), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal
- **period_convention:** Annual statement (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.22
- **effective_weight_in_composite:** 0.017160 (1.7160% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.accounting_quality (0.1) and fundamentals.metric_weights.accounting_quality.accruals_ratio (0.22); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Accruals ratio
- **display_tooltip:** Net income minus operating cash flow, over assets - negative is healthy. Weighted lightly: its predictive power has largely decayed since the early 2000s
- **notes:** cutoffs: excellent_max -0.02, good_max 0.03, fair_max 0.08, poor_max 0.15.

### piotroski_f

- **factor:** accounting_quality
- **layer:** fundamentals
- **formula_as_implemented:** higher_is_better_score: value>=excellent_min -> 100; >=good_min -> 80; >=fair_min -> 55; >=weak_min -> 30; else 10.0 (pipeline/scorer.py:105-113)
- **code_reference:** pipeline/scorer.py:600 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: higher_is_better_score)
- **source_field:** Derived: 9 binary tests scaled from however many are answerable (>=6 required), annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_piotroski), shortlist-only
- **fallback_chain:** No cross-provider fallback. None when fewer than 6 of the 9 tests can be evaluated.
- **units:** count (0-9 scale)
- **period_convention:** Annual statement, year-over-year (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.45
- **effective_weight_in_composite:** 0.035100 (3.5100% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.accounting_quality (0.1) and fundamentals.metric_weights.accounting_quality.piotroski_f (0.45); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** higher_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Piotroski F-score
- **display_tooltip:** Nine-point fundamental-strength composite, and the one earnings-quality signal that still validates well
- **notes:** cutoffs: excellent_min 8.0, good_min 6.5, fair_min 5.0, weak_min 3.0.

### days_sales_outstanding_trend

- **factor:** accounting_quality
- **layer:** fundamentals
- **formula_as_implemented:** lower_is_better_score: value<=excellent_max -> 100; <=good_max -> 80; <=fair_max -> 55; <=poor_max -> 30; else 10.0. Never penalizes negative values (unlike band_score) (pipeline/scorer.py:116-128)
- **code_reference:** pipeline/scorer.py:601-602 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: lower_is_better_score)
- **source_field:** Derived: (DSO(t)/DSO(t-1)) - 1, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_working_capital_trends), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal
- **period_convention:** Annual statement, year-over-year (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.17
- **effective_weight_in_composite:** 0.013260 (1.3260% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.accounting_quality (0.1) and fundamentals.metric_weights.accounting_quality.days_sales_outstanding_trend (0.17); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** DSO trend
- **display_tooltip:** Rising receivable days can mean revenue booked ahead of cash
- **notes:** cutoffs: excellent_max -0.05, good_max 0.03, fair_max 0.10, poor_max 0.20.

### inventory_days_trend

- **factor:** accounting_quality
- **layer:** fundamentals
- **formula_as_implemented:** lower_is_better_score: value<=excellent_max -> 100; <=good_max -> 80; <=fair_max -> 55; <=poor_max -> 30; else 10.0. Never penalizes negative values (unlike band_score) (pipeline/scorer.py:116-128)
- **code_reference:** pipeline/scorer.py:603 (metric dict entry inside _band_valuation_score), pipeline/scorer.py (scoring-function definition: lower_is_better_score)
- **source_field:** Derived: (inventory_days(t)/inventory_days(t-1)) - 1, annual statements
- **source_provider:** yahoo (fundamentals_extended.derive_working_capital_trends), shortlist-only
- **fallback_chain:** No cross-provider fallback.
- **units:** decimal
- **period_convention:** Annual statement, year-over-year (see STMT_NOTE)
- **winsorization:** None under the champion (bands mode). Challenger cross_sectional mode winsorizes at p1/p99 -- see population_for_normalization.
- **normalization:** None. bands mode uses fixed absolute cutoffs, not a cross-sectional distribution.
- **population_for_normalization:** None under the champion. A pipeline/scorer.py:CrossSectionalNormalizer challenger exists (scorer.py:307-461, mode='cross_sectional') that winsorizes at the 1st/99th percentile (settings.json challengers.cross_sectional_normalization.winsor_lower/upper_percentile) against the sector distribution when >=8 sector peers exist (sector_minimum_count) else the full refreshed universe -- published only as a shadow/challenger variant, never the primary score.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.012480 (1.2480% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json fundamentals.category_weights.accounting_quality (0.1) and fundamentals.metric_weights.accounting_quality.inventory_days_trend (0.16); ranking_weights.fundamentals (0.78) at pipeline/config/settings.json 'ranking_weights'; read by pipeline/scorer.py:24 (SETTINGS load) and pipeline/advisor_engine.py:32,42 (RANKING_WEIGHTS); applied by pipeline/scorer.py:609 (weighted_available(categories, cfg['category_weights'])) and pipeline/advisor_engine.py:846-867 (blend_research_components).
- **direction:** lower_is_better
- **missing_value_behavior:** Dropped from its category and the category reweighted over whichever metrics did resolve via weighted_available (pipeline/scorer.py:159-163), UNLESS the metric is declared required_for_score for the row's business profile/category (pipeline/canonical_metrics.py:174-182, pipeline/config/applicability_matrix.json 'required_for_score'), in which case the whole category publishes null ('categories_withheld', pipeline/scorer.py:515-535).
- **suppressed_for_profiles:** bank, property_casualty_insurer, life_insurer, diversified_insurer, semiconductor(not in top-level profiles enum -- see notes)
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Inventory trend
- **display_tooltip:** Rising inventory days is the retail and industrial version of the same warning
- **notes:** cutoffs: excellent_max -0.05, good_max 0.03, fair_max 0.10, poor_max 0.20.

---

## 3. Market-behavior sub-metrics

### momentum_12_1

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** momentum_12_1() = 12-month return skipping the most recent month (Jegadeesh & Titman 1993 construction), then momentum_score = clamp(50 + momentum_pct*1.2, 0, 100). Falls back to the 60-day return when <253 closes exist (no full 12-1 window), marked via the same score path (pipeline/advisor_engine.py:124,157-158).
- **code_reference:** pipeline/risk_metrics.py:36-49 (momentum_12_1), pipeline/advisor_engine.py:124,157-158 (score mapping)
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.3
- **effective_weight_in_composite:** 0.060000 (6.0000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.momentum_12_1 (declared 0.3) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** 12-1 momentum
- **display_tooltip:** Twelve-month return excluding the most recent month, the standard construction - the skipped month is dominated by short-term reversal

### risk_adjusted

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** risk_adjusted = 0.65*ratio_to_score(sortino) + 0.35*ratio_to_score(sharpe) over whichever of the two resolve; ratio_to_score maps an unbounded ratio to 0-100 via score=50*(1+x/(1+|x|)) where x=(value-neutral)/span, neutral=0.0, span=1.5 (so ratio 0 -> 50, 1.5 -> 75, 3.0 -> 87.5).
- **code_reference:** pipeline/risk_metrics.py:62-87 (sharpe_ratio, sortino_ratio), pipeline/risk_metrics.py:138-149 (ratio_to_score), pipeline/advisor_engine.py:159-165
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.26
- **effective_weight_in_composite:** 0.052000 (5.2000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.risk_adjusted (declared 0.26) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Sortino ratio / Sharpe ratio (raw ratios shown; the blended 0-100 risk_adjusted score itself has no direct UI label but is exposed as bullBearScore's 'Risk quality' factor and rankingModels.js's 'Trend quality' factor)
- **display_tooltip:** Return per unit of downside deviation - upside volatility is not a risk worth penalising (Sortino) / Return per unit of total volatility (Sharpe)
- **notes:** src/lib/bullBearScore.js:10-16 labels this factor 'Risk quality' (its own separate 40/30/20/10 gauge, not the champion composite -- see cross-cutting notes). src/lib/rankingModels.js:237 labels it 'Trend quality' in a different alternate-ranking-model list.

### relative_strength

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** relative = ret_20d - benchmark_ret_20d (SPY); relative_score = clamp(50 + relative*3, 0, 100). STRUCTURALLY EXCLUDED from the champion blend under the production short_horizon_treatment='neutral' setting -- see notes.
- **code_reference:** pipeline/advisor_engine.py:137-140,166 (relative_score computation), pipeline/advisor_engine.py:207-234 (technical_score_from_parts, pops this key when treatment=='neutral')
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.16
- **effective_weight_in_composite:** 0.000000 (0.0000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.relative_strength (declared 0.16) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Vs SPY (20d)
- **display_tooltip:** Relative 20-day return against the S&P 500 benchmark
- **notes:** IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole. Raw value is still published as technical_detail.relative_strength_20d and rendered by src/components/StockDetailModal.jsx:398 ('Vs SPY (20d)') and consumed by src/lib/sellWatchLogic.js, src/lib/researchScreens.js, src/lib/rankingModels.js -- so the raw number reaches the frontend even though its 0-100 score contributes nothing to the champion composite in the current configuration.

### drawdown_resilience

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** drawdown_score(drawdown_252_or_60) = clamp(100 / (1 + depth), 0, 100) where depth=|min(0,drawdown_pct)|/25.0 (tolerance=25.0; a 25% drawdown scores 50). Prefers the 252-day max drawdown, falling back to the 60-day peak-to-trough figure when <252 closes exist.
- **code_reference:** pipeline/risk_metrics.py:104-113 (max_drawdown), pipeline/risk_metrics.py:165-170 (drawdown_score), pipeline/advisor_engine.py:129-131,168
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.14
- **effective_weight_in_composite:** 0.028000 (2.8000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.drawdown_resilience (declared 0.14) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Max drawdown (1y)
- **display_tooltip:** Deepest peak-to-trough fall over the past year

### volume_confirmation

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** confirmation = min(sum(volume on up days)/sum(volume on down days), 3.0) over the trailing 60 sessions (1.0 = neutral); volume_score = clamp(35 + (confirmation-1)*55, 0, 100).
- **code_reference:** pipeline/advisor_engine.py:77-92 (volume_confirmation), pipeline/advisor_engine.py:141,169
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.08
- **effective_weight_in_composite:** 0.016000 (1.6000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.volume_confirmation (declared 0.08) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Volume confirmation
- **display_tooltip:** Volume on up days against down days - under 1 means rallies are unconvinced

### low_beta

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** low_beta_score(beta) = clamp(100/(1+distance^2), 0, 100) where distance=|beta-0.85|/0.55 (ideal=0.85, tolerance=0.55; betting-against-beta, Frazzini & Pedersen 2014). Beta itself is read from Yahoo info.beta first, else OLS-estimated against SPY daily returns.
- **code_reference:** pipeline/risk_metrics.py:90-101 (beta_vs_benchmark), pipeline/risk_metrics.py:152-162 (low_beta_score), pipeline/advisor_engine.py:134-136,170
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.06
- **effective_weight_in_composite:** 0.012000 (1.2000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.low_beta (declared 0.06) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** Beta
- **display_tooltip:** Sensitivity to the broad market - the link between the Fed backdrop and this name
- **notes:** MetricSections.jsx displays the raw beta value under label 'Beta', not the derived low_beta 0-100 score.

### technical_extended

- **factor:** market_behavior
- **layer:** market_behavior
- **formula_as_implemented:** Equal-weighted average of up to 4 sub-indicator scores, reweighted over whichever resolve: moving_average_slope (50-session MA % change over 10 sessions, scored clamp(50+slope*4)); relative_strength_index (14-day Wilder RSI, used directly as the 0-100 score); bollinger_percent_b (price position in a 20-session/2-std-dev band, scored clamp(%b*100)); on_balance_volume_slope (20-session OBV net change / (avg volume * window), scored clamp(50+slope*500)).
- **code_reference:** pipeline/technical_indicators.py:36-144 (all four sub-indicators + technical_extended_score), pipeline/advisor_engine.py:171,179
- **source_field:** Derived from 2 years of daily closes/volumes (pipeline/fetch_prices.py yahoo_history) plus SPY benchmark closes
- **source_provider:** yahoo (price history)
- **fallback_chain:** None (pure price/volume arithmetic; sub-metric is None when insufficient history, e.g. <21 sessions overall or the specific window each formula needs).
- **units:** score_0_100 (each sub-metric is itself mapped onto 0-100 before blending)
- **period_convention:** Rolling trading-day windows on daily closes (windows vary per sub-metric, see formula)
- **winsorization:** None.
- **normalization:** Deterministic closed-form transform per sub-metric (see formula_as_implemented), not a cross-sectional percentile.
- **population_for_normalization:** None -- each sub-metric is computed independently per ticker from its own price/volume history, not against a peer universe.
- **weight_in_factor:** 0.06
- **effective_weight_in_composite:** 0.012000 (1.2000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json market_behavior.weights.technical_extended (declared 0.06) with DEFAULT_TECHNICAL_WEIGHTS fallback at pipeline/advisor_engine.py:53-57; ranking_weights.market_behavior (0.18) at pipeline/config/settings.json 'ranking_weights'; combined by pipeline/advisor_engine.py:846-867 blend_research_components. IMPORTANT: settings.json's top-level 'short_horizon_treatment' is 'neutral' in the current config (pipeline/config/settings.json), and pipeline/advisor_engine.py:build_research (the champion path, line 1099) never overrides it, so pipeline/advisor_engine.py:182-184 always resolves treatment='neutral' for the published score. Under 'neutral', technical_score_from_parts (pipeline/advisor_engine.py:207-234) POPS relative_strength out of the weight table entirely (not merely 'reweights when missing' -- it is structurally absent for every row), and the remaining six sub-metrics' declared weights (momentum_12_1 0.30 + risk_adjusted 0.26 + drawdown_resilience 0.14 + volume_confirmation 0.08 + low_beta 0.06 + technical_extended 0.06 = 0.90) are renormalized over that 0.90, not over the full 7-metric declared sum of 1.06. The settings.json market_behavior.weights comment explains why: relative_strength (ret_20d minus a benchmark return that is the same scalar for every row) is rank-identical to return_20d 'Spearman +1.00 across 877 published rows' and was double-counting a signal already present. Also note the 7 raw declared weights (0.30+0.26+0.16+0.14+0.08+0.06+0.06) sum to 1.06, not 1.00 -- this does not break scoring because technical_score_from_parts always divides by the sum of the weights actually present (line 231-233), but it means the naive declared-weight table does not itself represent shares of a whole.
- **direction:** higher_is_better (all seven sub-metrics are constructed 0-100, higher=better, before blending)
- **missing_value_behavior:** Dropped from the market_behavior blend and the remaining sub-metrics reweighted over their own declared-weight sum (pipeline/advisor_engine.py:227-233 technical_score_from_parts). If NO sub-metric resolves, market_behavior itself is None and the top-level composite reweights over fundamentals/news_sentiment only (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** No sub-indicator (moving_average_slope, relative_strength_index, bollinger_percent_b, on_balance_volume_slope) or the blended technical_extended score itself appears in src/components/MetricSections.jsx's 'Behaviour & tradability' section or any other src/ component I found -- the raw detail is carried in technical_detail.technical_extended_detail (pipeline/advisor_engine.py:200) but I found no renderer for it. Mark published_to_frontend=False with this caveat rather than UNDETERMINED, since the search was exhaustive across src/components and src/lib for these exact field names.

---

## 4. News sentiment

### news_sentiment

- **factor:** news_sentiment
- **layer:** news_sentiment
- **formula_as_implemented:** weighted_sentiment(): filters articles to those with a resolvable per-ticker entity sentiment score and confidence >= entity_confidence_minimum within the trailing window (default 7 days per SETTINGS.news_intelligence.window_days), deduplicates syndicated copies by title similarity, then computes a weighted average of each article's entity sentiment score using weight = recency_weight * source_quality_weight * content_type_weight * entity_confidence, where recency_weight = exp(-ln(2) * age_days / recency_half_life_days) (exponential half-life decay). Final score = clamp(neutral_score + weighted_average * sentiment_score_scale, score_minimum, score_maximum). Returns None (not a neutral placeholder) when zero articles clear the filters.
- **code_reference:** pipeline/news_intelligence.py:129-219 (weighted_sentiment), pipeline/advisor_engine.py:237-249 (sentiment_score adapter)
- **source_field:** Marketaux news API (preferred) or Alpha Vantage NEWS_SENTIMENT (fallback), plus Yahoo per-symbol news for headline-lexicon-only coverage
- **source_provider:** marketaux primary; alpha_vantage fallback when marketaux is absent or failed; yahoo supplies additional headline coverage without provider entity-sentiment scores
- **fallback_chain:** pipeline/fetch_advisor.py:994-1013: for the Alpha-Vantage-eligible shortlist, Marketaux is tried first (marketaux_client.news); on failure or absence, Alpha Vantage NEWS_SENTIMENT is queried instead. Both are prepended to the Yahoo per-symbol news feed (pipeline/fetch_advisor.py:985-986, fetch_company_news) which runs for every polled ticker regardless of Alpha Vantage eligibility, but Yahoo's own feed carries no entity sentiment score, so it contributes coverage but not a sentiment reading unless a headline lexicon elsewhere (yahoo_news.headline_direction) assigns one -- see evidence_events.py, which is a separate consumer from this scorer path.
- **units:** score_0_100
- **period_convention:** Trailing window, default 7 days (SETTINGS.news_intelligence.window_days), recency-weighted with an exponential half-life inside the window
- **winsorization:** None.
- **normalization:** Weighted average of per-article entity sentiment (already -1..1 scale per provider), rescaled to 0-100 via config neutral_score/sentiment_score_scale/score_minimum/score_maximum -- not a cross-sectional percentile.
- **population_for_normalization:** None -- purely per-ticker, no peer comparison.
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** 0.040000 (4.0000% of the total composite score)
- **weight_defined_at:** pipeline/config/settings.json ranking_weights.news_sentiment (0.04) with DEFAULT_RANKING_WEIGHTS fallback at pipeline/advisor_engine.py:32,42; combined by pipeline/advisor_engine.py:846-867 blend_research_components. This is the only weight level for news_sentiment -- there is no sub-metric breakdown analogous to fundamentals' categories or market_behavior's 7 sub-metrics.
- **direction:** higher_is_better (0-100, higher = more positive coverage)
- **missing_value_behavior:** None (not neutral 50) when zero articles clear the confidence/window/dedup filters (pipeline/news_intelligence.py:177-197) -- the module docstring records this was previously bugged: returning a neutral_score placeholder made '373 of 374 screen-universe names read as we checked and its neutral' when the honest state was no evidence at all (fixed; see pipeline/news_intelligence.py:177-183 comment). The top-level composite then reweights fundamentals/market_behavior over the remaining 0.78/0.18 (pipeline/advisor_engine.py:846-867).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** True
- **display_label:** News Sentiment
- **display_tooltip:** UNDETERMINED -- src/components/StockCard.jsx:196-201 renders a 'News Sentiment' ComponentBar from components.news_sentiment but no title/tooltip text is attached to it in that file; no other src/ component was found rendering a tooltip for this field.
- **notes:** src/lib/bullBearScore.js independently re-weights this at 0.20 (vs the backend's 0.04) inside a SEPARATE frontend-only 'bull/bear thesis' gauge -- see cross-cutting notes; this is not an error in this entry, it documents that two different numbers with the same name coexist in the product.
- **determined:** False (one or more fields above are UNDETERMINED)

---

## 5. Canonical/v2-only and profile-replacement metrics

These are declared in `pipeline/config/metric_registry.json` (and, for the replacement metrics, named as `replaced_by` targets in `pipeline/config/applicability_matrix.json` and `replacement_metrics` in `pipeline/config/business_profiles.json`) but do **not** appear in `settings.json`'s `fundamentals.metric_weights` tables. Two are alias keys the v2/shadow layer uses to look up the same champion field under a canonical id (`trailing_revenue_growth`, `trailing_eps_growth`); two feed the v2-only "timeliness" axis and canonical PEG recomputation but are never populated by any fetch module (`expected_eps_growth`, `forward_eps_revision_30d`); the remaining seven are pure **declared-but-never-computed placeholders** for specialized business profiles (bank, insurer, REIT, biotech) -- confirmed by grepping every `pipeline/*.py` file (excluding config loading) for each name and finding no assignment anywhere.

### trailing_revenue_growth

- **factor:** fundamentals (v2/shadow canonical id)
- **layer:** fundamentals
- **formula_as_implemented:** Alias target only: canonical id for the champion's 'revenue_growth' field, used by scoring_v2.py's ALIASES map (pipeline/scoring_v2.py:72-76) so the v2 shadow layer's applicability/lineage lookups (canonical_metrics.applicability_for, canonical_metrics.reconcile) key on this name instead of the legacy id. Champion score value and formula are identical to the 'revenue_growth' entry above -- this is not a separately computed number.
- **code_reference:** pipeline/scoring_v2.py:72-76 (ALIASES), pipeline/config/metric_registry.json ('metrics' or 'metric_inventory' declaration for trailing_revenue_growth)
- **source_field:** Same as 'revenue_growth'
- **source_provider:** Same as 'revenue_growth'
- **fallback_chain:** Same as 'revenue_growth' -- this id has no independent data source; it is a lookup key.
- **units:** decimal
- **period_convention:** See scoring_v2.py ALIASES caveat above; no independent period declaration.
- **winsorization:** None.
- **normalization:** Not scored independently (see formula_as_implemented).
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted independently -- inherits 'revenue_growth''s weight (see that entry). Fully declared in pipeline/config/metric_registry.json 'metrics.trailing_revenue_growth' (not metric_inventory).
- **direction:** higher_is_better
- **missing_value_behavior:** Same as 'revenue_growth'.
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)

### trailing_eps_growth

- **factor:** fundamentals (v2/shadow canonical id)
- **layer:** fundamentals
- **formula_as_implemented:** Alias target only: canonical id for the champion's 'earnings_growth' field, used by scoring_v2.py's ALIASES map (pipeline/scoring_v2.py:72-76) so the v2 shadow layer's applicability/lineage lookups (canonical_metrics.applicability_for, canonical_metrics.reconcile) key on this name instead of the legacy id. Champion score value and formula are identical to the 'earnings_growth' entry above -- this is not a separately computed number.
- **code_reference:** pipeline/scoring_v2.py:72-76 (ALIASES), pipeline/config/metric_registry.json ('metrics' or 'metric_inventory' declaration for trailing_eps_growth)
- **source_field:** Same as 'earnings_growth'
- **source_provider:** Same as 'earnings_growth'
- **fallback_chain:** Same as 'earnings_growth' -- this id has no independent data source; it is a lookup key.
- **units:** decimal
- **period_convention:** See scoring_v2.py ALIASES caveat above; no independent period declaration.
- **winsorization:** None.
- **normalization:** Not scored independently (see formula_as_implemented).
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted independently -- inherits 'earnings_growth''s weight (see that entry). Declared in pipeline/config/metric_registry.json 'metric_inventory.trailing_eps_growth' (auto-expanded via declaration_defaults, pipeline/canonical_metrics.py:27-40).
- **direction:** higher_is_better
- **missing_value_behavior:** Same as 'earnings_growth'.
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)

### expected_eps_growth

- **factor:** fundamentals (v2/shadow-only, feeds canonical PEG recomputation)
- **layer:** fundamentals
- **formula_as_implemented:** Not computed by any pipeline module. Read via snapshot.get('expected_eps_growth') inside scoring_v2.build_v2_analysis to (re)compute a stricter canonical PEG via canonical_metrics.calculate_peg (pipeline/canonical_metrics.py:81-92), which requires this field AND a declared unit AND periods_match/definition_known flags that are also never set anywhere in fetch_advisor.py/fetch_prices.py.
- **code_reference:** pipeline/scoring_v2.py:89-94, pipeline/canonical_metrics.py:81-92 (calculate_peg)
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- confirmed by grep: no pipeline/*.py file (outside config declarations) ever assigns snapshot['expected_eps_growth'].
- **fallback_chain:** None exists. Always absent in practice, so canonical_peg is always None and scoring_v2.py:96 nulls out the v2 'peg' entry for every row ('provider_peg_rejected' quality flag).
- **units:** decimal or percentage_points (declared, never populated)
- **period_convention:** Declared forward horizon (never populated)
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted -- declared metric with no computation path.
- **direction:** higher_is_better (declaration)
- **missing_value_behavior:** Always None in this pipeline's current state; forces the v2 shadow layer's canonical PEG to always be unavailable.
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Declared-but-never-computed metric -- see formula_as_implemented.

### forward_eps_revision_30d

- **factor:** fundamentals (v2/shadow-only 'timeliness' layer, never published as champion)
- **layer:** fundamentals
- **formula_as_implemented:** revision_score = clamp(50 + revision*5, 0, 100) if snapshot.get('forward_eps_revision_30d') is not None. This 'timeliness' layer (structural is the champion-equivalent axis; timeliness is a second, entirely separate v2-only axis blending this with earnings_surprise at weights 0.7/0.3 via layer_health.renormalize) is read by recommendation_policy_v2.py's two-axis classification but is NEVER read by the champion advisor_engine.build_research path at all.
- **code_reference:** pipeline/scoring_v2.py:169-182,203-240, pipeline/recommendation_policy_v2.py (two_axis_classification, shadow-only)
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- confirmed by grep: no pipeline/*.py file ever assigns snapshot['forward_eps_revision_30d'].
- **fallback_chain:** None. scoring_v2.py's own docstring (lines 1-9) states this explicitly: 'There is no free source of broad forward consensus estimates or revisions... the honest state of this layer today is absent, not neutral.' pipeline/layer_health.assert_layers_vary is designed to fail the publish path if this ever silently becomes a universe-wide constant again.
- **units:** percentage_points (declared)
- **period_convention:** 30 calendar days (declared)
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** 0.7
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** pipeline/scoring_v2.py:176 (hardcoded 0.7/0.3 split inside build_v2_analysis, not read from settings.json)
- **direction:** higher_is_better
- **missing_value_behavior:** Always None currently -> the entire v2 'timeliness' layer publishes 'unavailable' (pipeline/scoring_v2.py:213-217) for every row unless ENABLE_EARNINGS_SURPRISE supplies earnings_surprise alone.
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Declared-but-never-computed metric; shadow/v2 only, never influences the champion score or recommendation.

### combined_ratio

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** decimal
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** lower_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: peg/ev_to_ebitda/ev_to_ebit/ev_to_fcf/sales_multiple/piotroski_f suppression reasons in applicability_matrix.json's property_casualty_insurer rules cite this as the underwriting-quality replacement.. Declared for profiles: property_casualty_insurer, diversified_insurer.
- **determined:** False (one or more fields above are UNDETERMINED)

### risk_based_capital_ratio

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** decimal
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** higher_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: current_ratio/altman_z suppression reasons in applicability_matrix.json's property_casualty_insurer rules.. Declared for profiles: property_casualty_insurer, life_insurer, diversified_insurer.
- **determined:** False (one or more fields above are UNDETERMINED)

### normalized_roe

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** decimal
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** higher_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: return_on_invested_capital suppression reason in applicability_matrix.json's property_casualty_insurer rules.. Declared for profiles: property_casualty_insurer, life_insurer, diversified_insurer.
- **determined:** False (one or more fields above are UNDETERMINED)

### capital_ratio

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** decimal
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** higher_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: net_debt_to_ebitda/altman_z suppression reasons in applicability_matrix.json's bank rules.. Declared for profiles: bank.
- **determined:** False (one or more fields above are UNDETERMINED)

### price_to_ffo

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** multiple
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** lower_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: peg/forward_pe suppression reasons in applicability_matrix.json's reit rules.. Declared for profiles: reit.
- **determined:** False (one or more fields above are UNDETERMINED)

### affo_yield

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** decimal
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** higher_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: free_cash_flow_yield suppression reason in applicability_matrix.json's reit rules.. Declared for profiles: reit.
- **determined:** False (one or more fields above are UNDETERMINED)

### cash_runway_months

- **factor:** profile replacement metric (declared concept, no computation)
- **layer:** fundamentals
- **formula_as_implemented:** NOT COMPUTED. This id appears only as a 'replaced_by' target in pipeline/config/applicability_matrix.json and/or a 'replacement_metrics' entry in pipeline/config/business_profiles.json, and gets an auto-generated declaration_defaults entry in pipeline/config/metric_registry.json's metric_inventory (pipeline/canonical_metrics.py:27-40) purely so applicability_for() has a definition/unit/direction string to report. No pipeline/*.py module (fundamentals_extended.py, fetch_advisor.py, canonical_metrics.py, scorer.py, scoring_v2.py) ever computes or fetches a value for it -- confirmed by grep across pipeline/*.py excluding config files.
- **code_reference:** pipeline/config/metric_registry.json ('metric_inventory' entry), pipeline/config/applicability_matrix.json ('replaced_by' target), pipeline/config/business_profiles.json ('replacement_metrics')
- **source_field:** None (verified absent -- see formula_as_implemented/notes)
- **source_provider:** NONE -- not computed anywhere in pipeline/*.py.
- **fallback_chain:** None. A row whose primary metric is suppressed and replaced by this id ends up with NEITHER metric scored -- the suppression removes the primary metric from the coverage denominator (pipeline/scorer.py:606-610 weighted_coverage(exempt=...)), but the named replacement never appears to fill the gap it names.
- **units:** count
- **period_convention:** UNDETERMINED -- Declared in metric_registry.json's metric_inventory but never computed by any pipeline/*.py module, so no real period convention exists to observe.
- **winsorization:** N/A
- **normalization:** N/A
- **population_for_normalization:** N/A
- **weight_in_factor:** None (verified absent -- see formula_as_implemented/notes)
- **effective_weight_in_composite:** None (verified absent -- see formula_as_implemented/notes)
- **weight_defined_at:** Not weighted anywhere -- no metric_weights entry exists for this id in settings.json.
- **direction:** higher_is_better
- **missing_value_behavior:** Always absent (never computed); the profile/category that names it as a critical_metric in business_profiles.json will always show that gap (see scoring_v2.py:241-247 critical_gaps / profile_confidence, which is driven toward 0 by exactly this).
- **suppressed_for_profiles:** none
- **required_for_parent_score:** none
- **published_to_frontend:** False
- **display_label:** None (verified absent -- see formula_as_implemented/notes)
- **display_tooltip:** None (verified absent -- see formula_as_implemented/notes)
- **notes:** Named as the intended replacement for: altman_z (both biotech profiles) and peg/forward_pe/price_to_book/free_cash_flow_yield/return_on_invested_capital (pre_profit_biotechnology) suppression reasons in applicability_matrix.json.. Declared for profiles: profitable_biotechnology, pre_profit_biotechnology.
- **determined:** False (one or more fields above are UNDETERMINED)

---

## 6. Silent-default sites feeding a score or decision

23 sites found. Full machine-readable list in `docs/spec/registry.json` `defaults`. Summary table:

| Location | Default value | Consequence (short) | Already fixed? |
|---|---|---|---|
| `pipeline/scorer.py:96` | `15.0` | Any negative reading for a band-scored metric (peg, price_to_book, price_to_tangible_book, debt_to_equity) is forced to a fixed score of 15.0/100 regardless of magnitude -- a peg of -0.01 and a peg of -50 score identically. | N/A -- current, intentional behavior; no prior bug reference found for this specific line. |
| `pipeline/scorer.py:146-149` | `5.0` | Any non-positive valuation multiple (forward_pe, ev_to_ebitda, ev_to_ebit, ev_to_fcf, sales_multiple) is forced to 5.0/100 flat, and values just above zero but below bands['suspicious_below'] are forced to 60.0/100 flat -- both are fixed literals substituting for a real reading across a wide input range. | N/A -- intentional. |
| `pipeline/scorer.py:102` | `10.0 if lower_is_better else 100.0` | A present-but-extreme value silently collapses to one of two fixed literals. | N/A -- intentional band-table design. |
| `pipeline/scorer.py:113,128` | `10.0` | A present, real, but sufficiently poor reading collapses to a fixed 10.0/100 floor rather than a continuously scaled score. | N/A -- intentional. |
| `pipeline/fundamentals_extended.py:161-165` | `0.21` | Silently substitutes the US statutory federal corporate rate whenever a company's effective tax rate cannot be computed from its own statements (e.g. | No -- current behavior, not previously flagged as a bug in comments (the comment frames it as deliberate: 'statutory federal fallback keeps NOPAT comparable across filers'). |
| `pipeline/fundamentals_extended.py:264-266` | `99.0 (if EBIT > 0) else None` | A company with no reported interest expense (which the pipeline cannot distinguish from a company with a genuinely tiny/rounding-error interest line) is scored as if it had 99x interest coverage -- the maximum practical value under settings.json's interest_coverage cutoffs (excellent_min 12.0), so this always resolves to a perfect 100/100 interest_coverage score via higher_is_better_score. | N/A -- intentional per the docstring, but the ambiguity between 'no debt' and 'field missing' is not resolved. |
| `pipeline/fundamentals_extended.py:180` | `0` | A company with unresolved total-debt data is silently treated as debt-free when computing invested capital for ROIC, understating invested capital and therefore overstating ROIC, rather than leaving ROIC unresolved. | No. |
| `pipeline/fundamentals_extended.py:192` | `0` | When operating cash flow is present but capex is missing, FCF is approximated as operating cash flow with zero capex subtracted, inflating the implied free cash flow and therefore cash_conversion, instead of leaving the metric unresolved. | No. |
| `pipeline/fundamentals_extended.py:277` | `0` | Missing cash silently reads as zero cash, overstating net debt and therefore net_debt_to_ebitda (a lower-is-better metric), pushing the score in the pessimistic direction rather than leaving it unresolved. | No. |
| `pipeline/fundamentals_extended.py:486` | `0` | When Yahoo's enterpriseValue is absent AND statement/info debt or cash is missing, the missing side is silently zeroed while computing a fallback enterprise value, understating or overstating EV and therefore every EV-based multiple (ev_to_ebitda, ev_to_ebit, ev_to_sales, ev_to_fcf) derived from it that refresh. | No. |
| `pipeline/fundamentals_extended.py:493-494` | `0` | Missing goodwill/intangibles silently reads as zero, inflating tangible_book_value and therefore understating price_to_tangible_book (making a company with unresolved goodwill data look cheaper on this metric than it may be). | No. |
| `pipeline/insider_signal.py:144,148,198` | `0` | A Form 4 transaction with an unparsed/missing dollar value is still counted toward insider_count and trade_count (which drive the breadth term of the insider_activity modifier) but contributes $0 to total_value and is silently excluded from the min_trade_value materiality filter (line 198) as if it were a trivial trade, rather than being flagged as data-quality-uncertain. | No. |
| `pipeline/recommendation_policy_v2.py:289-291` | `0.0 for current_weight; config-declared default_target_weight/default_max_weight for the other two (not a Python literal)` | A position with no known current_weight is silently treated as a 0% holding for the overweight/underweight classification that downstream drives trim-percentage decisions in the (shadow-only) v2 recommendation policy -- a real but unreported position would classify as 'below_target' rather than surfacing as unmeasured. | N/A -- shadow-only policy, not the champion recommendation. |
| `pipeline/recommendation_policy_v2.py:303,305` | `0` | Missing sector/theme concentration data silently reads as 0% concentration, so a position with genuinely unmeasured sector/theme exposure never triggers the 'sector_concentration_limit'/'theme_concentration_limit' reason codes it should be flagged for review under. | N/A -- shadow-only. |
| `pipeline/recommendation_policy_v2.py:392` | `0.0` | An unanticipated flagged-group count (e.g. | N/A -- shadow-only. |
| `pipeline/recommendation_policy_v2.py:406` | `1.0` | An unrecognized liquidity label is silently treated as a full 1.0x multiplier (no discount) on the trim percentage, rather than being treated as a data-quality gap. | N/A -- shadow-only. |
| `pipeline/recommendation_policy_v2.py:422-429` | `0` | Missing position shares/price/portfolio-value silently zero out the computed trade size, which then fails the 'economically_material' test (rounded>0) -- so a position with genuinely unmeasured share count or price silently resolves to 'do not trim' rather than 'cannot assess', converting missing position data into a no-action decision without saying so. | N/A -- shadow-only. |
| `pipeline/data_coverage.py:48-50` | `0.0` | Feeds only the additive, diagnostic-only data_coverage_detail breakdown (explicitly NOT the champion score or row['data_coverage'] per the module docstring), so the blast radius is limited to a displayed-but-non-authoritative explanatory number reading artificially low when a coverage key is absent versus genuinely zero. | N/A -- low-severity, diagnostic-only, and the module's own docstring states it never changes the champion score. |
| `pipeline/advisor_engine.py:775` | `0` | Low severity: article_count feeding the SELL/TRIM/WATCH guidance's sentiment-concern threshold (article_count >= 3) defaults to 0 when unmeasured, which conservatively suppresses (never falsely raises) a sentiment-based concern -- the surrounding function (_reading, lines 700-712) was rewritten specifically to eliminate the dangerous version of this pattern; this is the one remaining 'or 0' and it is safe by construction (a missing count cannot satisfy >=3). | Partially -- this file's docstring (lines 703-709) documents that EVERY other 'or fallback' in this function was a real bug already fixed (interest coverage defaulting to 99x, drawdown defaulting to 0%, both read as 'no concern' and silently failing the guidance engine open). This one instance was left in place because it is provably safe. |
| `pipeline/congress_signal.py:73` | `0` | A disclosed trade with an unparsed amount_lower silently reads as $0 and is therefore always excluded from the 'material' purchases list (since $0 < min_trade_value), rather than being flagged as amount-unknown. | N/A -- effectively safe by construction (exclusion, not inclusion). |
| `pipeline/advisor_engine.py:446` | `0` | Missing analyst_count silently reads as 0 analysts, which correctly falls below the count<3 gate and suppresses the modifier -- safe by construction, not a scoring-inflation bug. | N/A -- safe by construction. |
| `pipeline/scoring_v2.py:162` | `0.72 or 0.55 (both hardcoded literals, neither read from settings.json)` | The v2 shadow layer's 'confidence' multiplier (which scales its effective_score toward/away from neutral 50) is computed from one of two hand-picked constants depending only on whether ANY canonical Observation lineage exists for the row, not on how much of it does or its actual quality -- a coarse, undocumented-rationale binary switch feeding a shadow-only score. | N/A -- shadow-only; current, unexplained hardcoded constant. |
| `pipeline/scoring_v2.py:167` | `50` | Not a missing-value substitution in the dangerous sense (raw is explicitly checked for None first, so this never silently invents a score from nothing) -- documents the shrinkage-toward-50 formula itself, which is the intended, disclosed design (also used by recommendation_policy_v2.effective_score) rather than a bug. | N/A -- intentional, disclosed shrinkage-to-neutral design. |

### Full detail

**`pipeline/scorer.py:96`**

- **condition:** band_score(value, bands, lower_is_better=True): value is not None and value < 0
- **default_value:** `15.0`
- **consequence:** Any negative reading for a band-scored metric (peg, price_to_book, price_to_tangible_book, debt_to_equity) is forced to a fixed score of 15.0/100 regardless of magnitude -- a peg of -0.01 and a peg of -50 score identically. This is a deliberate design choice (comment: 'negative earnings / odd data -> penalize, don't zero out'), not a missing-data bug, but it is a hardcoded literal substituting for the real value.
- **already_fixed:** N/A -- current, intentional behavior; no prior bug reference found for this specific line.

**`pipeline/scorer.py:146-149`**

- **condition:** multiple_score(value, bands): value <= 0
- **default_value:** `5.0`
- **consequence:** Any non-positive valuation multiple (forward_pe, ev_to_ebitda, ev_to_ebit, ev_to_fcf, sales_multiple) is forced to 5.0/100 flat, and values just above zero but below bands['suspicious_below'] are forced to 60.0/100 flat -- both are fixed literals substituting for a real reading across a wide input range. Intentional design (documented as a distress/value-trap signal), not a missing-value bug.
- **already_fixed:** N/A -- intentional.

**`pipeline/scorer.py:102`**

- **condition:** band_score(): value present but exceeds every band boundary (falls through the loop)
- **default_value:** `10.0 if lower_is_better else 100.0`
- **consequence:** A present-but-extreme value silently collapses to one of two fixed literals. For lower_is_better metrics this is a floor (harsh, plausibly intended); the 100.0 branch (higher_is_better use of band_score) is currently dead code because every live band_score() call in _band_valuation_score uses the default lower_is_better=True.
- **already_fixed:** N/A -- intentional band-table design.

**`pipeline/scorer.py:113,128`**

- **condition:** higher_is_better_score()/lower_is_better_score(): value present but does not clear/exceed any configured band
- **default_value:** `10.0`
- **consequence:** A present, real, but sufficiently poor reading collapses to a fixed 10.0/100 floor rather than a continuously scaled score. Intentional band-table design (identical shape for all ~20 metrics using these two functions), not a missing-value bug.
- **already_fixed:** N/A -- intentional.

**`pipeline/fundamentals_extended.py:161-165`**

- **condition:** effective_tax_rate(income): computed rate is None or outside [0.0, 0.6]
- **default_value:** `0.21`
- **consequence:** Silently substitutes the US statutory federal corporate rate whenever a company's effective tax rate cannot be computed from its own statements (e.g. missing tax_provision/pretax_income) or is implausible. This value directly multiplies EBIT to produce NOPAT, which is the numerator of return_on_invested_capital -- so ROIC for any company with unresolvable tax data is computed against an assumed, not measured, tax rate, with no flag surfaced downstream distinguishing a measured 21% rate from this fallback.
- **already_fixed:** No -- current behavior, not previously flagged as a bug in comments (the comment frames it as deliberate: 'statutory federal fallback keeps NOPAT comparable across filers').

**`pipeline/fundamentals_extended.py:264-266`**

- **condition:** derive_interest_coverage(income): interest expense is None or |interest expense| < 1
- **default_value:** `99.0 (if EBIT > 0) else None`
- **consequence:** A company with no reported interest expense (which the pipeline cannot distinguish from a company with a genuinely tiny/rounding-error interest line) is scored as if it had 99x interest coverage -- the maximum practical value under settings.json's interest_coverage cutoffs (excellent_min 12.0), so this always resolves to a perfect 100/100 interest_coverage score via higher_is_better_score. Documented as intentional ('no debt service at all reads as maximum comfort') but the same code path also fires for a data gap that looks identical to true zero debt.
- **already_fixed:** N/A -- intentional per the docstring, but the ambiguity between 'no debt' and 'field missing' is not resolved.

**`pipeline/fundamentals_extended.py:180`**

- **condition:** derive_roic(): invested(index): total_debt is None (`(total_debt or 0)`)
- **default_value:** `0`
- **consequence:** A company with unresolved total-debt data is silently treated as debt-free when computing invested capital for ROIC, understating invested capital and therefore overstating ROIC, rather than leaving ROIC unresolved.
- **already_fixed:** No.

**`pipeline/fundamentals_extended.py:192`**

- **condition:** derive_cash_conversion(): capex is None (`abs(capex or 0)`)
- **default_value:** `0`
- **consequence:** When operating cash flow is present but capex is missing, FCF is approximated as operating cash flow with zero capex subtracted, inflating the implied free cash flow and therefore cash_conversion, instead of leaving the metric unresolved.
- **already_fixed:** No.

**`pipeline/fundamentals_extended.py:277`**

- **condition:** derive_net_debt_to_ebitda(): cash is None (`(cash or 0)`)
- **default_value:** `0`
- **consequence:** Missing cash silently reads as zero cash, overstating net debt and therefore net_debt_to_ebitda (a lower-is-better metric), pushing the score in the pessimistic direction rather than leaving it unresolved.
- **already_fixed:** No.

**`pipeline/fundamentals_extended.py:486`**

- **condition:** derive_enterprise_multiples(): debt is None or cash is None (`(debt or 0) - (cash or 0)`), only on the enterprise_value is None fallback branch (i.e. Yahoo's own enterpriseValue field was also absent)
- **default_value:** `0`
- **consequence:** When Yahoo's enterpriseValue is absent AND statement/info debt or cash is missing, the missing side is silently zeroed while computing a fallback enterprise value, understating or overstating EV and therefore every EV-based multiple (ev_to_ebitda, ev_to_ebit, ev_to_sales, ev_to_fcf) derived from it that refresh.
- **already_fixed:** No.

**`pipeline/fundamentals_extended.py:493-494`**

- **condition:** derive_enterprise_multiples(): goodwill is None or intangibles is None (`at(...) or 0`)
- **default_value:** `0`
- **consequence:** Missing goodwill/intangibles silently reads as zero, inflating tangible_book_value and therefore understating price_to_tangible_book (making a company with unresolved goodwill data look cheaper on this metric than it may be).
- **already_fixed:** No.

**`pipeline/insider_signal.py:144,148,198`**

- **condition:** cluster_trades()/score_insider_activity(): transaction 'value' field is None (`float(row.get('value') or 0)`)
- **default_value:** `0`
- **consequence:** A Form 4 transaction with an unparsed/missing dollar value is still counted toward insider_count and trade_count (which drive the breadth term of the insider_activity modifier) but contributes $0 to total_value and is silently excluded from the min_trade_value materiality filter (line 198) as if it were a trivial trade, rather than being flagged as data-quality-uncertain.
- **already_fixed:** No.

**`pipeline/recommendation_policy_v2.py:289-291`**

- **condition:** classify_portfolio_fit(): portfolio.get('current_weight'/'target_weight'/'maximum_weight') is not a number
- **default_value:** `0.0 for current_weight; config-declared default_target_weight/default_max_weight for the other two (not a Python literal)`
- **consequence:** A position with no known current_weight is silently treated as a 0% holding for the overweight/underweight classification that downstream drives trim-percentage decisions in the (shadow-only) v2 recommendation policy -- a real but unreported position would classify as 'below_target' rather than surfacing as unmeasured.
- **already_fixed:** N/A -- shadow-only policy, not the champion recommendation.

**`pipeline/recommendation_policy_v2.py:303,305`**

- **condition:** classify_portfolio_fit(): portfolio.get('sector_weight'/'theme_weight') is not a number (`_number(..., 0)`)
- **default_value:** `0`
- **consequence:** Missing sector/theme concentration data silently reads as 0% concentration, so a position with genuinely unmeasured sector/theme exposure never triggers the 'sector_concentration_limit'/'theme_concentration_limit' reason codes it should be flagged for review under. Shadow-only.
- **already_fixed:** N/A -- shadow-only.

**`pipeline/recommendation_policy_v2.py:392`**

- **condition:** _trim_percent(): rule['base_by_flag_count'].get(str(count), 0.0) -- flagged-group count not present in the configured lookup table
- **default_value:** `0.0`
- **consequence:** An unanticipated flagged-group count (e.g. more simultaneous deterioration groups than the config table enumerates) silently produces a 0% base trim recommendation rather than erroring or falling back to the highest configured tier. Shadow-only.
- **already_fixed:** N/A -- shadow-only.

**`pipeline/recommendation_policy_v2.py:406`**

- **condition:** _trim_percent(): rule['liquidity_multipliers'].get(liquidity, 1.0) -- position's liquidity label not present in the configured multiplier table
- **default_value:** `1.0`
- **consequence:** An unrecognized liquidity label is silently treated as a full 1.0x multiplier (no discount) on the trim percentage, rather than being treated as a data-quality gap. Shadow-only.
- **already_fixed:** N/A -- shadow-only.

**`pipeline/recommendation_policy_v2.py:422-429`**

- **condition:** _economic_trade(): position.get('shares'/'current_price'/'portfolio_value'/'estimated_transaction_cost') is not a number (`_number(..., 0)`)
- **default_value:** `0`
- **consequence:** Missing position shares/price/portfolio-value silently zero out the computed trade size, which then fails the 'economically_material' test (rounded>0) -- so a position with genuinely unmeasured share count or price silently resolves to 'do not trim' rather than 'cannot assess', converting missing position data into a no-action decision without saying so. Shadow-only.
- **already_fixed:** N/A -- shadow-only.

**`pipeline/data_coverage.py:48-50`**

- **condition:** completeness_component(): fundamental_detail/technical_detail/sentiment_detail 'coverage' key is None (`.get('coverage') or 0.0`)
- **default_value:** `0.0`
- **consequence:** Feeds only the additive, diagnostic-only data_coverage_detail breakdown (explicitly NOT the champion score or row['data_coverage'] per the module docstring), so the blast radius is limited to a displayed-but-non-authoritative explanatory number reading artificially low when a coverage key is absent versus genuinely zero.
- **already_fixed:** N/A -- low-severity, diagnostic-only, and the module's own docstring states it never changes the champion score.

**`pipeline/advisor_engine.py:775`**

- **condition:** action_for(): _reading(sentiment_parts, 'article_count') or 0
- **default_value:** `0`
- **consequence:** Low severity: article_count feeding the SELL/TRIM/WATCH guidance's sentiment-concern threshold (article_count >= 3) defaults to 0 when unmeasured, which conservatively suppresses (never falsely raises) a sentiment-based concern -- the surrounding function (_reading, lines 700-712) was rewritten specifically to eliminate the dangerous version of this pattern; this is the one remaining 'or 0' and it is safe by construction (a missing count cannot satisfy >=3).
- **already_fixed:** Partially -- this file's docstring (lines 703-709) documents that EVERY other 'or fallback' in this function was a real bug already fixed (interest coverage defaulting to 99x, drawdown defaulting to 0%, both read as 'no concern' and silently failing the guidance engine open). This one instance was left in place because it is provably safe.

**`pipeline/congress_signal.py:73`**

- **condition:** score_congressional_buying(): row.get('amount_lower') or 0, compared against settings['min_trade_value']
- **default_value:** `0`
- **consequence:** A disclosed trade with an unparsed amount_lower silently reads as $0 and is therefore always excluded from the 'material' purchases list (since $0 < min_trade_value), rather than being flagged as amount-unknown. This is a conservative (never-inflates-the-signal) default, not a scoring-inflation bug.
- **already_fixed:** N/A -- effectively safe by construction (exclusion, not inclusion).

**`pipeline/advisor_engine.py:446`**

- **condition:** expectations_modifier(): extended.get('analyst_count') or 0, compared against `count < 3`
- **default_value:** `0`
- **consequence:** Missing analyst_count silently reads as 0 analysts, which correctly falls below the count<3 gate and suppresses the modifier -- safe by construction, not a scoring-inflation bug.
- **already_fixed:** N/A -- safe by construction.

**`pipeline/scoring_v2.py:162`**

- **condition:** build_v2_analysis(): provenance_reliability = 0.72 if observations else 0.55
- **default_value:** `0.72 or 0.55 (both hardcoded literals, neither read from settings.json)`
- **consequence:** The v2 shadow layer's 'confidence' multiplier (which scales its effective_score toward/away from neutral 50) is computed from one of two hand-picked constants depending only on whether ANY canonical Observation lineage exists for the row, not on how much of it does or its actual quality -- a coarse, undocumented-rationale binary switch feeding a shadow-only score.
- **already_fixed:** N/A -- shadow-only; current, unexplained hardcoded constant.

**`pipeline/scoring_v2.py:167`**

- **condition:** build_v2_analysis(): effective = None if raw is None else 50 + confidence * (raw - 50)
- **default_value:** `50`
- **consequence:** Not a missing-value substitution in the dangerous sense (raw is explicitly checked for None first, so this never silently invents a score from nothing) -- documents the shrinkage-toward-50 formula itself, which is the intended, disclosed design (also used by recommendation_policy_v2.effective_score) rather than a bug. Included for completeness since it is a literal '50' baked directly into the score formula.
- **already_fixed:** N/A -- intentional, disclosed shrinkage-to-neutral design.

## 7. ⚠️ `replaced_by` is NOT a weight transfer

The applicability matrix (`pipeline/config/applicability_matrix.json`) annotates most
suppressions with a `replaced_by` metric (e.g. insurer `ev_to_ebitda → price_to_book`). **The
scorer never reads `replaced_by`.** `canonical_metrics.suppressed_metrics`
(`canonical_metrics.py:153-171`) returns only the *set* of suppressed metric ids — both
`suppressed` and `replaced` statuses collapse into the same suppression (`rule[0] in
("suppressed", "replaced")`, line 169) — and `weighted_available` (`scorer.py:159-163`) then
renormalizes the suppressed weight blindly across **all** surviving metrics in the category, in
proportion to their configured weights.

Worked example, verified against config: for a `property_casualty_insurer`, valuation suppresses
`peg` (0.09), `sales_multiple` (0.09), `ev_to_ebitda` (0.27), `ev_to_ebit` (0.12), `ev_to_fcf`
(0.18). Survivors are `forward_pe` 0.15, `price_to_book` 0.05, `price_to_tangible_book` 0.05
(sum 0.25). The insurer valuation category is therefore **60% forward P/E**
(0.15/0.25) and 20%/20% the two book multiples. `ev_to_ebitda`'s 0.27 was *not* routed to its
declared replacement `price_to_book` (which stays at 0.05/0.25 = 20%). `replaced_by` is a
display/explanation pointer (surfaced by `scoring_v2.build_v2_analysis`'s `metric_status`,
`scoring_v2.py:145-152`), nothing more. Any reader of this registry — or of the payload — who
interprets `replaced_by` as weight routing will mis-state every suppressed profile's weights.

The one guard against renormalizing a category onto nothing meaningful is
`required_for_score` (`applicability_matrix.json:339-378`): insurers/REITs cannot publish
valuation without `price_to_book` (banks: `price_to_tangible_book`), and insurers/banks cannot
publish financial_health without `debt_to_equity` (`scorer.py:515-535`,
`canonical_metrics.py:174-182`). A withheld category's *category* weight then renormalizes
across the surviving categories — the same blind renormalization one level up.

## 8. Sanity checks (executed 2026-08-10, python3 over live config)

| Check | Result |
|---|---|
| `category_weights` sum | **1.0** (exactly 1.0 in IEEE-754) |
| `metric_weights[valuation]` sum | 1.0 (8 metrics) |
| `metric_weights[profitability]` sum | 1.0 (6 metrics) |
| `metric_weights[financial_health]` sum | 1.0 (5 metrics) |
| `metric_weights[growth]` sum | 1.0 (5 metrics) |
| `metric_weights[capital_allocation]` sum | **1.0000000000000002** (4 metrics — the float artifact lives here) |
| `metric_weights[accounting_quality]` sum | 1.0 (4 metrics) |
| `ranking_weights` sum | 1.0 |
| `market_behavior.weights` sum | **1.06** (intentionally ≠ 1; see §5) |
| Σ effective composite weights (32 fundamentals metrics) | 0.78003 (= 0.78 up to 5-dp rounding of each term) |
| All 32 scored metric ids present in all 40 published `fundamental_detail` blocks | ✓ (direct artifact scan) |

The much-cited `1.0000000000000002` float artifact was **reproduced at the
`capital_allocation` metric-weight level** (0.34+0.28+0.16+0.22 in double precision), **not** at
the category-weight level — `category_weights` sums to exactly `1.0` in this working tree. Any
document placing the artifact on the category weights is describing an older tree or is wrong.
`weighted_available` divides by the summed weights it actually used (`scorer.py:163`), so the
artifact has no effect on scores.

---

*Compiled by direct file reads and executed checks on 2026-08-10. Companion artifact:
`docs/spec/registry.json`. Not committed to git by this pass.*

## 9. Second defaults sweep

A second, independently produced sweep (46 findings across 23 pipeline files, including the screens/picks/ETF paths this document's §6 sweep deliberately scoped out) is retained in `docs/spec/registry.json` under `defaults_second_sweep`, with its own files-swept and pattern lists. The two sweeps overlap on the core scoring sites; neither is a subset of the other. §6's table plus that array together are the authoritative union.
