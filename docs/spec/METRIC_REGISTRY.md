# ValueSignal — Metric Registry

**Status: complete for the current working tree.** Compiled 2026-08-10 against branch
`claude/valuesignal-spec-audit-qf2wni` and cross-checked against the live published artifact
`public/data/advisor.json` (`generated_at: 2026-08-10T05:23:37.933120+00:00`,
`schema_version: 6`, `model_version:
3.2.0`, 40 published research rows). Machine-readable
companion: `docs/spec/registry.json` (same compilation pass, same evidence).

Every factual claim carries a `path/to/file:line` citation to code or config read directly in
this session. Nothing here is copied from `research/audit/CURRENT_MODEL_AUDIT.md`,
`research/audit/PIPELINE-MAP.md`, or `research/STATE.md` — those are stale prior audits.
Anything that could not be verified from the working tree is marked **UNDETERMINED**.

---

## 1. Composite structure

The published research score blends three components (`advisor_engine.build_research`,
`advisor_engine.py:1093-1122`):

| Component | Weight | Source of weight |
|---|---|---|
| `fundamentals` | 0.78 | `settings.json:1104-1109` (`ranking_weights`) |
| `market_behavior` | 0.18 | same |
| `news_sentiment` | 0.04 | same |

**Answer to the open question: `settings.json` DOES contain a top-level `ranking_weights` key**
(`settings.json:1104-1109`). `advisor_engine.py:32` defines
`DEFAULT_RANKING_WEIGHTS = {"fundamentals": 0.78, "market_behavior": 0.18, "news_sentiment": 0.04}`
and `advisor_engine.py:42` merges the config values over those defaults
(`RANKING_WEIGHTS = _weights(SETTINGS.get("ranking_weights"), DEFAULT_RANKING_WEIGHTS)`). The two
are numerically identical today, so config is operative and the code constant is an inert,
identical fallback. Confirmed by direct read of both files, 2026-08-10.

Blend mechanics (`blend_research_components`, `advisor_engine.py:846-867`):

```
raw   = Σ(component_i × weight_i) / Σ(weight_i)   over components that are not None
base  = raw × (0.8 + 0.2 × data_coverage)
final = clamp(base + modifier_points, 0, 100)      modifiers capped at ±15 (advisor_engine.py:551-552)
data_coverage = 0.65×fund_cov + 0.25×mkt_cov + 0.10×news_cov   (advisor_engine.py:838-843)
```

A `None` component is silently dropped and its weight renormalized over the survivors — with no
news coverage, fundamentals is effectively 0.78/0.96 ≈ 0.8125 of the evidence blend. Inside the
fundamentals component itself there is a second coverage scaling:
`total = raw × (0.65 + 0.35 × coverage)` (`scorer.py:615-616`).

**Effective composite weight** below therefore means the *nominal* share of the final score:
`0.78 × category_weight × metric_weight`, before any renormalization from missing/suppressed
metrics, before the two coverage multipliers, and before modifiers. It is an upper-bound design
weight, not a per-row realized weight — on any given row, every missing sibling metric inflates
the survivors' realized shares (§4).

## 2. Category weights

`settings.json:594-601` (`fundamentals.category_weights`):

| Category | Weight | Effective composite (0.78 × w) |
|---|---|---|
| valuation | 0.28 | 0.21840 |
| profitability | 0.26 | 0.20280 |
| financial_health | 0.15 | 0.11700 |
| growth | 0.11 | 0.08580 |
| capital_allocation | 0.10 | 0.07800 |
| accounting_quality | 0.10 | 0.07800 |

## 3. Master metric table

All 32 metrics scored by the champion (`scorer.SCORED_METRICS`, `scorer.py:231-240`;
scoring dispatch `scorer.py:553-604`). "Suppressing profiles (of 13)" counts suppressions across
the 12 rule-bearing business profiles plus `etf` (which suppresses everything,
`canonical_metrics.py:164-165`). "Non-null in artifact" is a direct count over the 40
published leaderboard rows' `fundamental_detail` in `public/data/advisor.json`.

| Metric | Category | Weight in category | Effective composite | Scoring function | Direction | Suppressing profiles (of 13) | Non-null in artifact (of 40 rows) |
|---|---|---|---|---|---|---|---|
| `peg` | valuation | 0.09 | 0.01966 | band_score | lower_is_better | 9 | 18 |
| `forward_pe` | valuation | 0.15 | 0.03276 | multiple_score | lower_is_better | 4 | 40 |
| `sales_multiple` | valuation | 0.09 | 0.01966 | multiple_score (sales basis) | lower_is_better | 5 | 28 |
| `price_to_book` | valuation | 0.05 | 0.01092 | band_score | lower_is_better | 2 | 40 |
| `price_to_tangible_book` | valuation | 0.05 | 0.01092 | band_score | lower_is_better | 1 | 22 |
| `ev_to_ebitda` | valuation | 0.27 | 0.05897 | multiple_score | lower_is_better | 5 | 28 |
| `ev_to_ebit` | valuation | 0.12 | 0.02621 | multiple_score | lower_is_better | 5 | 28 |
| `ev_to_fcf` | valuation | 0.18 | 0.03931 | multiple_score | lower_is_better | 5 | 28 |
| `return_on_equity` | profitability | 0.10 | 0.02028 | higher_is_better | higher_is_better | 1 | 39 |
| `return_on_invested_capital` | profitability | 0.26 | 0.05273 | higher_is_better | higher_is_better | 7 | 28 |
| `gross_profits_to_assets` | profitability | 0.22 | 0.04462 | higher_is_better | higher_is_better | 6 | 17 |
| `cash_conversion` | profitability | 0.16 | 0.03245 | higher_is_better | higher_is_better | 4 | 31 |
| `free_cash_flow_yield` | profitability | 0.16 | 0.03245 | higher_is_better | higher_is_better | 8 | 28 |
| `profit_margin` | profitability | 0.10 | 0.02028 | higher_is_better | higher_is_better | 1 | 40 |
| `debt_to_equity` | financial_health | 0.18 | 0.02106 | band_score | lower_is_better | 1 | 36 |
| `current_ratio` | financial_health | 0.10 | 0.01170 | higher_is_better | higher_is_better | 6 | 28 |
| `interest_coverage` | financial_health | 0.30 | 0.03510 | higher_is_better | higher_is_better | 1 | 37 |
| `net_debt_to_ebitda` | financial_health | 0.24 | 0.02808 | lower_is_better | lower_is_better | 5 | 28 |
| `altman_z` | financial_health | 0.18 | 0.02106 | altman_score | higher_is_better | 8 | 26 |
| `revenue_growth` | growth | 0.26 | 0.02231 | higher_is_better | higher_is_better | 1 | 40 |
| `earnings_growth` | growth | 0.20 | 0.01716 | higher_is_better | higher_is_better | 1 | 40 |
| `fcf_growth_3y` | growth | 0.22 | 0.01888 | higher_is_better | higher_is_better | 2 | 28 |
| `operating_margin_trend` | growth | 0.16 | 0.01373 | higher_is_better | higher_is_better | 2 | 27 |
| `earnings_surprise` | growth | 0.16 | 0.01373 | higher_is_better | higher_is_better | 1 | 0 |
| `net_buyback_yield` | capital_allocation | 0.34 | 0.02652 | higher_is_better | higher_is_better | 1 | 40 |
| `stock_comp_to_revenue` | capital_allocation | 0.28 | 0.02184 | lower_is_better | lower_is_better | 1 | 30 |
| `capex_to_depreciation` | capital_allocation | 0.16 | 0.01248 | range_score | ideal_range | 6 | 27 |
| `asset_growth` | capital_allocation | 0.22 | 0.01716 | range_score | ideal_range | 1 | 40 |
| `accruals_ratio` | accounting_quality | 0.22 | 0.01716 | lower_is_better | lower_is_better | 1 | 40 |
| `piotroski_f` | accounting_quality | 0.45 | 0.03510 | higher_is_better | higher_is_better | 5 | 28 |
| `days_sales_outstanding_trend` | accounting_quality | 0.17 | 0.01326 | lower_is_better | lower_is_better | 5 | 28 |
| `inventory_days_trend` | accounting_quality | 0.16 | 0.01248 | lower_is_better | lower_is_better | 6 | 17 |

Notable rows:

- **`earnings_surprise` is configured at 0.16 of growth but is null in 40/40 published rows.**
  Its collection is opt-in behind `ENABLE_EARNINGS_SURPRISE` (`fetch_advisor.py:472`), off by
  default; the weight silently renormalizes onto the other four growth metrics on every row
  (`scorer.py:159-163`). The artifact's own `capability_status` block documents this
  (`fetch_advisor.py:1853-1857`).
- **`peg` is non-null in only 18/40 rows** — suppressed for 9 of 13 profiles, and requires a
  positive provider PEG elsewhere.
- **`gross_profits_to_assets` and `inventory_days_trend` resolve in 17/40 rows** — statement
  enrichment only runs for a shortlist (Alpha Vantage enrichment capped at 5 symbols/run,
  `fetch_advisor.py:1343`), so statement-derived metrics are structurally sparse.

## 4. ⚠️ `replaced_by` is NOT a weight transfer

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

## 5. Market-behavior sub-metrics

Configured in `settings.json:1300-1308` (`market_behavior.weights`), merged over identical code
defaults at `advisor_engine.py:53-59`. **The configured weights sum to 1.06, not 1.00.** The
champion runs `short_horizon_treatment: "neutral"` (`settings.json:52`), which removes
`relative_strength` (0.16) and renormalizes over the surviving 0.90
(`technical_score_from_parts`, `advisor_engine.py:207-234`) — relative strength was measured
rank-identical to `return_20d` (Spearman +1.00 per the config comment, `settings.json:1299`).
So the champion-effective composite share of each surviving sub-metric is
`0.18 × w / 0.90`, not `0.18 × w`:

| Sub-metric | Configured weight | Nominal composite (0.18 × w) | Champion status | Champion effective composite (full coverage) |
|---|---|---|---|---|
| `momentum_12_1` | 0.30 | 0.05400 | included | 0.06000 |
| `risk_adjusted` | 0.26 | 0.04680 | included | 0.05200 |
| `relative_strength` | 0.16 | 0.02880 | excluded (short_horizon_treatment='neutral') | 0.00000 |
| `drawdown_resilience` | 0.14 | 0.02520 | included | 0.02800 |
| `volume_confirmation` | 0.08 | 0.01440 | included | 0.01600 |
| `low_beta` | 0.06 | 0.01080 | included | 0.01200 |
| `technical_extended` | 0.06 | 0.01080 | included | 0.01200 |

Champion effective weights sum to 0.18000 (the full market-behavior allocation). Sub-scores:
`momentum_12_1` = clamp(50 + momentum% × 1.2) with a 60-day-return fallback
(`advisor_engine.py:155-158`); `risk_adjusted` = 0.65 × Sortino + 0.35 × Sharpe through
`ratio_to_score` (saturating, neutral 0 → 50, `risk_metrics.py:138-149`,
`advisor_engine.py:159-165`); `relative_strength` = clamp(50 + (ret_20d − SPY_20d) × 3)
(computed and published, excluded from the champion blend); `drawdown_resilience` =
`drawdown_score` on the 252-day max drawdown (25% fall → 50, `risk_metrics.py:165-170`);
`volume_confirmation` = clamp(35 + (up/down volume ratio − 1) × 55) (`advisor_engine.py:169`);
`low_beta` = 100/(1 + ((β−0.85)/0.55)²) (`risk_metrics.py:152-162`); `technical_extended` =
four-indicator composite (`technical_indicators.py:116+`). Missing sub-scores are dropped and
renormalized with coverage marked down (`advisor_engine.py:227-234`).

## 6. Per-metric detail

Scoring functions (`pipeline/scorer.py`):

- **`band_score`** (`scorer.py:91-102`): lower-is-better tiers 100/75/50/25 across the four band
  keys in order, 10 beyond the last band, and a fixed **15 for any negative value**.
- **`multiple_score`** (`scorer.py:142-156`): 5 for ≤0, 60 below `suspicious_below` (value-trap
  flag), then 100/80/45/15.
- **`higher_is_better_score`** (`scorer.py:105-113`): 100/80/55/30 at the four `*_min` keys, 10 below.
- **`lower_is_better_score`** (`scorer.py:116-128`): 100/80/55/30 at the four `*_max` keys, 10
  beyond; unlike `band_score` it never penalizes negatives (net cash is a strength).
- **`range_score`** (`scorer.py:131-139`): 100 inside the ideal band, 65 inside acceptable, 25 outside.
- **`altman_score`** (`scorer.py:196-209`): `higher_is_better_score` against the bands for the
  variant the value was computed under; no variant → None.

### 6.1 Valuation (category weight 0.28)

#### `peg`

- **Definition**: Forward P/E divided by expected annual EPS growth expressed in percentage points. *(registry id `peg`, from `metrics`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.09 of `valuation` → effective composite 0.01966
- **Scoring**: `band_score`
- **Source**: yahoo quote info.pegRatio via providers.map_quote (providers.py:281) / Alpha Vantage OVERVIEW PEGRatio (providers.py:353, fetch_advisor.py:621); v2 layer recomputes canonically from forward_pe + expected_eps_growth (canonical_metrics.calculate_peg:81-92) and rejects provider PEG (scoring_v2.py:89-96)
- **Suppressed for**: bank (`replaced_by: forward_pe` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: forward_pe` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: forward_pe` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: forward_pe` — display pointer only, **no weight transfer**); reit (`replaced_by: price_to_ffo` — display pointer only, **no weight transfer**); commodity_producer (`replaced_by: midcycle_ev_ebitda` — display pointer only, **no weight transfer**); pre_profit_biotechnology (`replaced_by: cash_runway_months` — display pointer only, **no weight transfer**); other_pre_profit (`replaced_by: gross_margin_and_runway` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 18/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.peg`):

| Condition | Score |
|---|---|
| <=excellent_max=1.0 | 100 |
| <=good_max=1.5 | 75 |
| <=fair_max=2.0 | 50 |
| <=poor_max=3.0 | 25 |
| beyond | 10 |
| negative_value | 15 |

#### `forward_pe`

- **Definition**: Current price divided by next-fiscal-year consensus diluted EPS. *(registry id `forward_pe`, from `metrics`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.15 of `valuation` → effective composite 0.03276
- **Scoring**: `multiple_score`
- **Source**: yahoo quote info.forwardPE (canonical_metrics.py:233, providers.py:280); Alpha Vantage OVERVIEW ForwardPE fallback (providers.py:352)
- **Suppressed for**: reit (`replaced_by: price_to_ffo` — display pointer only, **no weight transfer**); pre_profit_biotechnology (`replaced_by: cash_runway_months` — display pointer only, **no weight transfer**); other_pre_profit (`replaced_by: gross_margin_and_runway` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.forward_pe_by_sector`):

Tiers: ≤0 → 5; < `suspicious_below` → 60; ≤ `cheap_max` → 100; ≤ `healthy_max` → 80; ≤ `elevated_max` → 45; above → 15.

| Sector | `suspicious_below` | `cheap_max` | `healthy_max` | `elevated_max` |
|---|---|---|---|---|
| Technology | 8 | 25 | 35 | 50 |
| Consumer Defensive | 6 | 15 | 20 | 28 |
| Utilities | 6 | 15 | 20 | 28 |
| Financial Services | 5 | 12 | 18 | 25 |
| Financials | 5 | 12 | 18 | 25 |
| Healthcare | 6 | 16 | 25 | 38 |
| default | 5 | 15 | 25 | 40 |

#### `sales_multiple`

- **Definition**: Market capitalization divided by TTM revenue. *(registry id `price_to_sales`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.09 of `valuation` → effective composite 0.01966
- **Scoring**: `multiple_score (via sales_multiple_score)`
- **Source**: ev_to_sales derived from enterpriseValue (or marketCap+totalDebt-cash) / revenue (fundamentals_extended.py:479-511); fallback yahoo info.priceToSalesTrailing12Months (canonical_metrics.py:237)
- **Suppressed for**: bank (`replaced_by: price_to_tangible_book` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.ev_to_sales_by_sector` / `fundamentals.price_to_sales_by_sector`):

Tiers: ≤0 → 5; ≤ `cheap_max` → 100; ≤ `healthy_max` → 80; ≤ `elevated_max` → 45; above → 15. ev_to_sales/price_to_sales sector tables carry no suspicious_below key, so the value-trap tier never fires for the sales multiple.

EV/Sales (preferred basis):

| Sector | `cheap_max` | `healthy_max` | `elevated_max` |
|---|---|---|---|
| Technology | 5.5 | 15.0 | 26.0 |
| Healthcare | 2.5 | 5.5 | 11.0 |
| Industrials | 1.4 | 3.0 | 5.5 |
| Consumer Cyclical | 1.4 | 3.5 | 6.5 |
| Consumer Defensive | 1.4 | 3.0 | 4.5 |
| default | 1.5 | 3.5 | 8.5 |

Price/Sales (fallback basis):

| Sector | `cheap_max` | `healthy_max` | `elevated_max` |
|---|---|---|---|
| Technology | 5.0 | 15.0 | 25.0 |
| Healthcare | 2.0 | 5.0 | 10.0 |
| Industrials | 1.0 | 2.5 | 5.0 |
| Consumer Cyclical | 1.0 | 3.0 | 6.0 |
| Consumer Defensive | 1.0 | 2.5 | 4.0 |
| default | 1.0 | 3.0 | 8.0 |

#### `price_to_book`

- **Definition**: Market capitalization divided by common shareholders equity from the latest filing. *(registry id `price_to_book`, from `metrics`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.05 of `valuation` → effective composite 0.01092
- **Scoring**: `band_score`
- **Source**: yahoo quote info.priceToBook (canonical_metrics.py:236, providers.py:281); Alpha Vantage OVERVIEW PriceToBookRatio fallback (providers.py:354)
- **Suppressed for**: pre_profit_biotechnology (`replaced_by: cash_runway_months` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Required for score in**: diversified_insurer, life_insurer, property_casualty_insurer, reit — absence nulls the parent category (`scorer.py:515-535`).
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.price_to_book`):

| Condition | Score |
|---|---|
| <=excellent_max=1.0 | 100 |
| <=good_max=3.0 | 75 |
| <=fair_max=6.0 | 50 |
| <=poor_max=10.0 | 25 |
| beyond | 10 |
| negative_value | 15 |

#### `price_to_tangible_book`

- **Definition**: Market capitalization divided by tangible common equity. *(registry id `price_to_tangible_book`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.05 of `valuation` → effective composite 0.01092
- **Scoring**: `band_score`
- **Source**: marketCap / (equity - goodwill - intangibles) from annual balance sheet (fundamentals_extended.py:492-514)
- **Suppressed for**: none except `etf`.
- **Conditional gate**: Additionally suppressed unless sector is in scorer.TANGIBLE_BOOK_SECTORS (Financial Services/Financials/Financial/Real Estate/Utilities/Energy/Basic Materials/Materials/Industrials) or the profile lists it as a replacement metric (scorer.py:180-181, 253-259). Snapshot-dependent, not expressible per profile alone.
- **Required for score in**: bank — absence nulls the parent category (`scorer.py:515-535`).
- **Published coverage**: non-null in 22/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.price_to_tangible_book`):

| Condition | Score |
|---|---|
| <=excellent_max=1.5 | 100 |
| <=good_max=3.0 | 75 |
| <=fair_max=6.0 | 50 |
| <=poor_max=12.0 | 25 |
| beyond | 10 |
| negative_value | 15 |

#### `ev_to_ebitda`

- **Definition**: Enterprise value divided by positive TTM EBITDA. *(registry id `ev_to_ebitda`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.27 of `valuation` → effective composite 0.05897
- **Scoring**: `multiple_score`
- **Source**: EV / EBITDA, statement EBITDA or info.ebitda; EV from info.enterpriseValue or marketCap+(totalDebt or 0)-(cash or 0) (fundamentals_extended.py:479-504)
- **Suppressed for**: bank (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.ev_to_ebitda`):

| Condition | Score |
|---|---|
| nonpositive | 5 |
| <suspicious_below=3.0 | 60 |
| <=cheap_max=10.0 | 100 |
| <=healthy_max=15.0 | 80 |
| <=elevated_max=22.0 | 45 |
| beyond | 15 |

#### `ev_to_ebit`

- **Definition**: UNDETERMINED - no entry in pipeline/config/metric_registry.json (see source_fields for the code-level derivation) **[no `metric_registry.json` entry — see §7.2]**
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.12 of `valuation` → effective composite 0.02621
- **Scoring**: `multiple_score`
- **Source**: EV / statement EBIT (fundamentals_extended.py:488,508)
- **Suppressed for**: bank (`replaced_by: price_to_tangible_book` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.ev_to_ebit`):

| Condition | Score |
|---|---|
| nonpositive | 5 |
| <suspicious_below=4.0 | 60 |
| <=cheap_max=12.0 | 100 |
| <=healthy_max=18.0 | 80 |
| <=elevated_max=26.0 | 45 |
| beyond | 15 |

#### `ev_to_fcf`

- **Definition**: Enterprise value divided by positive TTM free cash flow. *(registry id `ev_to_fcf`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.18 of `valuation` → effective composite 0.03931
- **Scoring**: `multiple_score`
- **Source**: EV / statement Free Cash Flow or info.freeCashflow (fundamentals_extended.py:490,512)
- **Suppressed for**: bank (`replaced_by: price_to_tangible_book` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: price_to_book` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.ev_to_fcf`):

| Condition | Score |
|---|---|
| nonpositive | 5 |
| <suspicious_below=5.0 | 60 |
| <=cheap_max=18.0 | 100 |
| <=healthy_max=28.0 | 80 |
| <=elevated_max=45.0 | 45 |
| beyond | 15 |


### 6.2 Profitability (category weight 0.26)

#### `return_on_invested_capital`

- **Definition**: NOPAT divided by average invested operating capital. *(registry id `return_on_invested_capital`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.26 of `profitability` → effective composite 0.05273
- **Scoring**: `higher_is_better_score`
- **Source**: EBIT*(1-effective tax rate)/avg(total_debt+equity-cash), annual statements (fundamentals_extended.derive_roic:168-184); tax rate falls back to 0.21 when unreadable (line 161-165)
- **Suppressed for**: bank (`replaced_by: return_on_equity` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: normalized_roe` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: normalized_roe` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: normalized_roe` — display pointer only, **no weight transfer**); reit (`replaced_by: same_store_noi_growth` — display pointer only, **no weight transfer**); pre_profit_biotechnology (`replaced_by: pipeline_stage` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.return_on_invested_capital`):

| Condition | Score |
|---|---|
| >=excellent_min=0.2 | 100 |
| >=good_min=0.13 | 80 |
| >=fair_min=0.08 | 55 |
| >=weak_min=0.04 | 30 |
| below | 10 |

#### `gross_profits_to_assets`

- **Definition**: UNDETERMINED - no entry in pipeline/config/metric_registry.json (see source_fields for the code-level derivation) **[no `metric_registry.json` entry — see §7.2]**
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.22 of `profitability` → effective composite 0.04462
- **Scoring**: `higher_is_better_score`
- **Source**: Gross Profit (or revenue-cost_of_revenue) / avg total assets, annual statements (fundamentals_extended.py:341-357)
- **Suppressed for**: bank (`replaced_by: net_interest_margin` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: underwriting_income` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: underwriting_income` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: underwriting_income` — display pointer only, **no weight transfer**); commodity_producer (`replaced_by: lifting_production_cost` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 17/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.gross_profits_to_assets`):

| Condition | Score |
|---|---|
| >=excellent_min=0.33 | 100 |
| >=good_min=0.22 | 80 |
| >=fair_min=0.13 | 55 |
| >=weak_min=0.06 | 30 |
| below | 10 |

#### `return_on_equity`

- **Definition**: Net income available to common shareholders divided by average common equity. *(registry id `return_on_equity`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.10 of `profitability` → effective composite 0.02028
- **Scoring**: `higher_is_better_score`
- **Source**: yahoo quote info.returnOnEquity (canonical_metrics.py:238); Alpha Vantage OVERVIEW ReturnOnEquityTTM fallback (providers.py:355, fetch_advisor.py:622)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 39/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.return_on_equity`):

| Condition | Score |
|---|---|
| >=excellent_min=0.2 | 100 |
| >=good_min=0.15 | 80 |
| >=fair_min=0.1 | 55 |
| >=weak_min=0.05 | 30 |
| below | 10 |

#### `free_cash_flow_yield`

- **Definition**: TTM free cash flow divided by point-in-time market capitalization. *(registry id `free_cash_flow_yield`, from `metrics`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.16 of `profitability` → effective composite 0.03245
- **Scoring**: `higher_is_better_score`
- **Source**: info.freeCashflow / info.marketCap (canonical_metrics.py:269-275)
- **Suppressed for**: bank (`replaced_by: price_to_book` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: total_capital_return_yield` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: total_capital_return_yield` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: total_capital_return_yield` — display pointer only, **no weight transfer**); reit (`replaced_by: affo_yield` — display pointer only, **no weight transfer**); utility (`replaced_by: funds_from_operations_yield` — display pointer only, **no weight transfer**); pre_profit_biotechnology (`replaced_by: cash_runway_months` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.free_cash_flow_yield`):

| Condition | Score |
|---|---|
| >=excellent_min=0.08 | 100 |
| >=good_min=0.05 | 80 |
| >=fair_min=0.02 | 55 |
| >=weak_min=0.0 | 30 |
| below | 10 |

#### `profit_margin`

- **Definition**: TTM net income divided by TTM revenue. *(registry id `profit_margin`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.10 of `profitability` → effective composite 0.02028
- **Scoring**: `higher_is_better_score`
- **Source**: yahoo quote info.profitMargins (canonical_metrics.py:239); Alpha Vantage OVERVIEW ProfitMargin fallback (providers.py:356)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.profit_margin`):

| Condition | Score |
|---|---|
| >=excellent_min=0.2 | 100 |
| >=good_min=0.12 | 80 |
| >=fair_min=0.06 | 55 |
| >=weak_min=0.0 | 30 |
| below | 10 |

#### `cash_conversion`

- **Definition**: TTM free cash flow divided by positive TTM net income. *(registry id `cash_conversion`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.16 of `profitability` → effective composite 0.03245
- **Scoring**: `higher_is_better_score`
- **Source**: FCF (or operating_cash_flow - |capex or 0|) / positive net income, annual statements (fundamentals_extended.py:187-196)
- **Suppressed for**: property_casualty_insurer (`replaced_by: combined_ratio` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: combined_ratio` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: combined_ratio` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 31/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.cash_conversion`):

| Condition | Score |
|---|---|
| >=excellent_min=1.0 | 100 |
| >=good_min=0.8 | 80 |
| >=fair_min=0.6 | 55 |
| >=weak_min=0.35 | 30 |
| below | 10 |


### 6.3 Financial health (category weight 0.15)

#### `interest_coverage`

- **Definition**: Operating income divided by interest expense for a matched period. *(registry id `interest_coverage`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: higher_is_better
- **Weight**: 0.30 of `financial_health` → effective composite 0.03510
- **Scoring**: `higher_is_better_score`
- **Source**: statement EBIT / |interest expense|; 99.0 imputed when no interest expense and EBIT>0 (fundamentals_extended.py:259-266)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 37/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.interest_coverage`):

| Condition | Score |
|---|---|
| >=excellent_min=12.0 | 100 |
| >=good_min=6.0 | 80 |
| >=fair_min=3.0 | 55 |
| >=weak_min=1.5 | 30 |
| below | 10 |

#### `net_debt_to_ebitda`

- **Definition**: Debt less cash divided by positive TTM EBITDA. *(registry id `net_debt_to_ebitda`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.24 of `financial_health` → effective composite 0.02808
- **Scoring**: `lower_is_better_score`
- **Source**: (total_debt - (cash or 0)) / positive EBITDA, statements with info fallbacks (fundamentals_extended.py:269-277)
- **Suppressed for**: bank (`replaced_by: capital_ratio` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: debt_to_capital` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: debt_to_capital` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: debt_to_capital` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.net_debt_to_ebitda`):

| Condition | Score |
|---|---|
| <=excellent_max=0.5 | 100 |
| <=good_max=1.5 | 80 |
| <=fair_max=3.0 | 55 |
| <=poor_max=4.5 | 30 |
| beyond | 10 |

#### `debt_to_equity`

- **Definition**: Interest-bearing debt divided by common equity. *(registry id `debt_to_equity`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: lower_is_better
- **Weight**: 0.18 of `financial_health` → effective composite 0.02106
- **Scoring**: `band_score`
- **Source**: yahoo quote info.debtToEquity / 100 (canonical_metrics.py:261-267)
- **Suppressed for**: none except `etf`.
- **Required for score in**: bank, diversified_insurer, life_insurer, property_casualty_insurer — absence nulls the parent category (`scorer.py:515-535`).
- **Published coverage**: non-null in 36/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.debt_to_equity`):

| Condition | Score |
|---|---|
| <=excellent_max=0.5 | 100 |
| <=good_max=1.0 | 75 |
| <=fair_max=2.0 | 50 |
| <=poor_max=3.0 | 25 |
| beyond | 10 |
| negative_value | 15 |

#### `current_ratio`

- **Definition**: Current assets divided by current liabilities for the same filing period. *(registry id `current_ratio`, from `metrics`)*
- **Unit**: multiple · **Direction**: higher_is_better
- **Weight**: 0.10 of `financial_health` → effective composite 0.01170
- **Scoring**: `higher_is_better_score`
- **Source**: yahoo quote info.currentRatio (canonical_metrics.py:235)
- **Suppressed for**: bank; property_casualty_insurer (`replaced_by: risk_based_capital_ratio` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: risk_based_capital_ratio` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: risk_based_capital_ratio` — display pointer only, **no weight transfer**); reit (`replaced_by: fixed_charge_coverage` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.current_ratio`):

| Condition | Score |
|---|---|
| >=excellent_min=2.0 | 100 |
| >=good_min=1.5 | 80 |
| >=fair_min=1.0 | 55 |
| >=weak_min=0.75 | 30 |
| below | 10 |

#### `altman_z`

- **Definition**: Declared Altman model using matched annual inputs. *(registry id `altman_z`, from `metric_inventory`)*
- **Unit**: score_0_100 · **Direction**: higher_is_better
- **Weight**: 0.18 of `financial_health` → effective composite 0.02106
- **Scoring**: `altman_score (higher_is_better_score on variant bands)`
- **Source**: annual statements + marketCap; variant by sector; partial sum over available terms with minimum term count 4 (z) / 3 (z'') (fundamentals_extended.py:287-338)
- **Suppressed for**: bank (`replaced_by: capital_ratio` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: risk_based_capital_ratio` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: risk_based_capital_ratio` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: risk_based_capital_ratio` — display pointer only, **no weight transfer**); reit (`replaced_by: fixed_charge_coverage` — display pointer only, **no weight transfer**); profitable_biotechnology (`replaced_by: cash_runway_months` — display pointer only, **no weight transfer**); pre_profit_biotechnology (`replaced_by: cash_runway_months` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 26/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.altman_z`):

Tiers: ≥ `excellent_min` → 100; ≥ `good_min` → 80; ≥ `fair_min` → 55; ≥ `weak_min` → 30; below → 10. sector-based (fundamentals_extended.altman_variant_for): financials -> None (suppressed); manufacturer_sectors -> z; else z_double_prime.

| Variant | `excellent_min` | `good_min` | `fair_min` | `weak_min` |
|---|---|---|---|---|
| z (original 1968 manufacturing model) | 3.0 | 2.6 | 1.8 | 1.1 |
| z_double_prime (non-manufacturer revision) | 2.6 | 2.0 | 1.1 | 0.5 |


### 6.4 Growth (category weight 0.11)

#### `revenue_growth`

- **Definition**: Latest TTM revenue versus the preceding TTM revenue. *(registry id `trailing_revenue_growth`, from `metrics`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.26 of `growth` → effective composite 0.02231
- **Scoring**: `higher_is_better_score`
- **Source**: yahoo quote info.revenueGrowth (canonical_metrics.py:240); Alpha Vantage OVERVIEW QuarterlyRevenueGrowthYOY fallback (providers.py:357, fetch_advisor.py:624)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.revenue_growth`):

| Condition | Score |
|---|---|
| >=excellent_min=0.2 | 100 |
| >=good_min=0.1 | 80 |
| >=fair_min=0.03 | 55 |
| >=weak_min=0.0 | 30 |
| below | 10 |

#### `earnings_growth`

- **Definition**: Latest TTM diluted EPS versus preceding TTM diluted EPS. *(registry id `trailing_eps_growth`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.20 of `growth` → effective composite 0.01716
- **Scoring**: `higher_is_better_score`
- **Source**: yahoo quote info.earningsGrowth (canonical_metrics.py:241, flagged not_forward_growth); Alpha Vantage OVERVIEW QuarterlyEarningsGrowthYOY fallback (providers.py:358)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.earnings_growth`):

| Condition | Score |
|---|---|
| >=excellent_min=0.2 | 100 |
| >=good_min=0.1 | 80 |
| >=fair_min=0.03 | 55 |
| >=weak_min=0.0 | 30 |
| below | 10 |

#### `fcf_growth_3y`

- **Definition**: Three-year compound annual growth in fiscal-year free cash flow. *(registry id `fcf_growth_3y`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.22 of `growth` → effective composite 0.01888
- **Scoring**: `higher_is_better_score`
- **Source**: CAGR over all annual Free Cash Flow periods on file, minimum 3 (fundamentals_extended.py:199-204)
- **Suppressed for**: commodity_producer (`replaced_by: free_cash_flow_breakeven` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.fcf_growth_3y`):

| Condition | Score |
|---|---|
| >=excellent_min=0.15 | 100 |
| >=good_min=0.08 | 80 |
| >=fair_min=0.02 | 55 |
| >=weak_min=-0.05 | 30 |
| below | 10 |

#### `operating_margin_trend`

- **Definition**: Current operating margin less comparable prior-period margin. *(registry id `operating_margin_trend`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.16 of `growth` → effective composite 0.01373
- **Scoring**: `higher_is_better_score`
- **Source**: operating_income/revenue now minus prior year, annual statements (fundamentals_extended.py:214-254)
- **Suppressed for**: commodity_producer (`replaced_by: normalized_midcycle_margin` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 27/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.operating_margin_trend`):

| Condition | Score |
|---|---|
| >=excellent_min=0.02 | 100 |
| >=good_min=0.005 | 80 |
| >=fair_min=-0.005 | 55 |
| >=weak_min=-0.02 | 30 |
| below | 10 |

#### `earnings_surprise`

- **Definition**: UNDETERMINED - no entry in pipeline/config/metric_registry.json (see source_fields for the code-level derivation) **[no `metric_registry.json` entry — see §7.2]**
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.16 of `growth` → effective composite 0.01373
- **Scoring**: `higher_is_better_score`
- **Source**: yfinance earnings_dates surprise column, last 4 quarters weighted 0.4/0.3/0.2/0.1 (fundamentals_extended.py:519-572); collection opt-in via ENABLE_EARNINGS_SURPRISE (fetch_advisor.py:472)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 0/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.earnings_surprise`):

| Condition | Score |
|---|---|
| >=excellent_min=8.0 | 100 |
| >=good_min=3.0 | 80 |
| >=fair_min=0.0 | 55 |
| >=weak_min=-5.0 | 30 |
| below | 10 |


### 6.5 Capital allocation (category weight 0.10)

#### `net_buyback_yield`

- **Definition**: Reduction in diluted share count divided by beginning diluted share count. *(registry id `net_buyback_yield`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: higher_is_better
- **Weight**: 0.34 of `capital_allocation` → effective composite 0.02652
- **Scoring**: `higher_is_better_score`
- **Source**: -(share count change) from shares_outstanding or diluted_shares, annual balance (fundamentals_extended.py:453-469)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.net_buyback_yield`):

| Condition | Score |
|---|---|
| >=excellent_min=0.03 | 100 |
| >=good_min=0.01 | 80 |
| >=fair_min=0.0 | 55 |
| >=weak_min=-0.02 | 30 |
| below | 10 |

#### `stock_comp_to_revenue`

- **Definition**: Stock-based compensation divided by matched-period revenue. *(registry id `stock_comp_to_revenue`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: lower_is_better
- **Weight**: 0.28 of `capital_allocation` → effective composite 0.02184
- **Scoring**: `lower_is_better_score`
- **Source**: |Stock Based Compensation| / revenue, annual statements (fundamentals_extended.py:462-471)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 30/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.stock_comp_to_revenue`):

| Condition | Score |
|---|---|
| <=excellent_max=0.01 | 100 |
| <=good_max=0.03 | 80 |
| <=fair_max=0.07 | 55 |
| <=poor_max=0.12 | 30 |
| beyond | 10 |

#### `capex_to_depreciation`

- **Definition**: Capital expenditures divided by depreciation and amortization for a matched period. *(registry id `capex_to_depreciation`, from `metric_inventory`)*
- **Unit**: multiple · **Direction**: ideal_range
- **Weight**: 0.16 of `capital_allocation` → effective composite 0.01248
- **Scoring**: `range_score`
- **Source**: |capex| / |depreciation|, annual cash-flow statement (fundamentals_extended.py:465-473)
- **Suppressed for**: bank (`replaced_by: efficiency_ratio` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: book_value_growth` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: book_value_growth` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: book_value_growth` — display pointer only, **no weight transfer**); semiconductor (`replaced_by: gross_margin_cycle` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 27/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.capex_to_depreciation`):

| Condition | Score |
|---|---|
| in_ideal | 100 |
| in_acceptable | 65 |
| outside | 25 |

#### `asset_growth`

- **Definition**: UNDETERMINED - no entry in pipeline/config/metric_registry.json (see source_fields for the code-level derivation) **[no `metric_registry.json` entry — see §7.2]**
- **Unit**: decimal · **Direction**: ideal_range
- **Weight**: 0.22 of `capital_allocation` → effective composite 0.01716
- **Scoring**: `range_score`
- **Source**: total assets now / prior year - 1, annual balance (fundamentals_extended.py:360-371)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.asset_growth`):

| Condition | Score |
|---|---|
| in_ideal | 100 |
| in_acceptable | 65 |
| outside | 25 |


### 6.6 Accounting quality (category weight 0.10)

#### `accruals_ratio`

- **Definition**: Net income less operating cash flow divided by average total assets. *(registry id `accruals_ratio`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: lower_is_better
- **Weight**: 0.22 of `accounting_quality` → effective composite 0.01716
- **Scoring**: `lower_is_better_score`
- **Source**: (net income - operating cash flow) / avg total assets, annual statements (fundamentals_extended.py:411-417)
- **Suppressed for**: none except `etf`.
- **Published coverage**: non-null in 40/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.accruals_ratio`):

| Condition | Score |
|---|---|
| <=excellent_max=-0.02 | 100 |
| <=good_max=0.03 | 80 |
| <=fair_max=0.08 | 55 |
| <=poor_max=0.15 | 30 |
| beyond | 10 |

#### `piotroski_f`

- **Definition**: Count of applicable Piotroski binary tests, with declared coverage. *(registry id `piotroski_f`, from `metric_inventory`)*
- **Unit**: count · **Direction**: higher_is_better
- **Weight**: 0.45 of `accounting_quality` → effective composite 0.03510
- **Scoring**: `higher_is_better_score`
- **Source**: 9 binary tests from annual statements, scaled 9*passed/answered, None below 6 answered (fundamentals_extended.py:374-406)
- **Suppressed for**: bank (`replaced_by: common_equity_tier_1_ratio` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: combined_ratio` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: combined_ratio` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: combined_ratio` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.piotroski_f`):

| Condition | Score |
|---|---|
| >=excellent_min=8.0 | 100 |
| >=good_min=6.5 | 80 |
| >=fair_min=5.0 | 55 |
| >=weak_min=3.0 | 30 |
| below | 10 |

#### `days_sales_outstanding_trend`

- **Definition**: Comparable-period change in receivable days. *(registry id `days_sales_outstanding_trend`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: lower_is_better
- **Weight**: 0.17 of `accounting_quality` → effective composite 0.01326
- **Scoring**: `lower_is_better_score`
- **Source**: receivables*365/revenue year-over-year drift (fundamentals_extended.py:425-448)
- **Suppressed for**: bank (`replaced_by: net_charge_off_trend` — display pointer only, **no weight transfer**); property_casualty_insurer (`replaced_by: loss_ratio` — display pointer only, **no weight transfer**); life_insurer (`replaced_by: loss_ratio` — display pointer only, **no weight transfer**); diversified_insurer (`replaced_by: loss_ratio` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 28/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.days_sales_outstanding_trend`):

| Condition | Score |
|---|---|
| <=excellent_max=-0.05 | 100 |
| <=good_max=0.03 | 80 |
| <=fair_max=0.1 | 55 |
| <=poor_max=0.2 | 30 |
| beyond | 10 |

#### `inventory_days_trend`

- **Definition**: Comparable-period change in inventory days. *(registry id `inventory_days_trend`, from `metric_inventory`)*
- **Unit**: decimal · **Direction**: lower_is_better
- **Weight**: 0.16 of `accounting_quality` → effective composite 0.01248
- **Scoring**: `lower_is_better_score`
- **Source**: inventory*365/cost_of_revenue year-over-year drift (fundamentals_extended.py:425-448)
- **Suppressed for**: bank; property_casualty_insurer; life_insurer; diversified_insurer; semiconductor (`replaced_by: inventory_cycle` — display pointer only, **no weight transfer**). (Plus `etf`: everything suppressed.)
- **Published coverage**: non-null in 17/40 leaderboard rows of the 2026-08-10 artifact.

**Cutoffs** (`pipeline/config/settings.json`, `fundamentals.inventory_days_trend`):

| Condition | Score |
|---|---|
| <=excellent_max=-0.05 | 100 |
| <=good_max=0.03 | 80 |
| <=fair_max=0.1 | 55 |
| <=poor_max=0.2 | 30 |
| beyond | 10 |


## 7. Applicability

### 7.1 Suppression matrix (live scorer authority)

Computed by re-executing `canonical_metrics.profile_rules` semantics
(`canonical_metrics.py:133-138`, `$inherits` resolved; `life_insurer` and
`diversified_insurer` inherit `property_casualty_insurer`) with `suppressed_metrics` logic
(`canonical_metrics.py:153-171`: statuses `suppressed` and `replaced` both suppress). ✓ =
applied, — = suppressed. `etf` (not shown) suppresses every metric. `price_to_tangible_book`
carries an additional snapshot-dependent sector gate (`scorer.py:180-181, 253-259`) not
expressible in this matrix; the ✓ row shows the matrix state only.

| Metric | general | bank | P&C ins. | life ins. | div. ins. | reit | utility | commodity | biotech (prof.) | biotech (pre) | other pre-profit | semi. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `peg` | ✓ | — | — | — | — | — | ✓ | — | ✓ | — | — | ✓ |
| `forward_pe` | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | — | — | ✓ |
| `sales_multiple` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `price_to_book` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| `price_to_tangible_book` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ev_to_ebitda` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ev_to_ebit` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ev_to_fcf` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `return_on_equity` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `return_on_invested_capital` | ✓ | — | — | — | — | — | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| `gross_profits_to_assets` | ✓ | — | — | — | — | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| `cash_conversion` | ✓ | ✓ | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `free_cash_flow_yield` | ✓ | — | — | — | — | — | — | ✓ | ✓ | — | ✓ | ✓ |
| `profit_margin` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `debt_to_equity` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `current_ratio` | ✓ | — | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `interest_coverage` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `net_debt_to_ebitda` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `altman_z` | ✓ | — | — | — | — | — | ✓ | ✓ | — | — | ✓ | ✓ |
| `revenue_growth` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `earnings_growth` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `fcf_growth_3y` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| `operating_margin_trend` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| `earnings_surprise` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `net_buyback_yield` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `stock_comp_to_revenue` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `capex_to_depreciation` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `asset_growth` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `accruals_ratio` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `piotroski_f` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `days_sales_outstanding_trend` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `inventory_days_trend` | ✓ | — | — | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |

Profile classification: `canonical_metrics.classify_profile` (`canonical_metrics.py:95-130`) —
ticker overrides first (`business_profiles.json:43-67`), then keyword tests on sector/industry
in this order: etf, reit, bank, insurer (life / P&C / diversified), utility, commodity,
**semiconductor** (before the pre-profit branches), pre-profit biotech, profitable biotech,
other pre-profit (negative `profit_margin`), general.

### 7.2 Config-vs-config and config-vs-code discrepancies (verified 2026-08-10)

1. **`semiconductor` and `other_pre_profit` are missing from `business_profiles.json`.**
   `business_profiles.json:3-42` declares profiles: `bank`, `commodity_producer`, `diversified_insurer`, `etf`, `general`, `life_insurer`, `pre_profit_biotechnology`, `profitable_biotechnology`, `property_casualty_insurer`, `reit`, `utility`.
   `applicability_matrix.json` carries rules for both missing names (`semiconductor` rules at
   `applicability_matrix.json:325-336`; `other_pre_profit` at 313-324), and `classify_profile`
   can return both. Consequences, confirmed by code read: (a) in `scorer.applicability`
   (`scorer.py:255-259`) the profile contract lookup returns `{}`, so `price_to_tangible_book`
   for these profiles falls back to the sector-tuple gate alone; (b) in
   `scoring_v2.build_v2_analysis` (`scoring_v2.py:241-247`) both profiles have empty
   `replacement_metrics`/`critical_metrics`, so `profile_confidence` is hard-coded to **0.0**
   (`scoring_v2.py:247`) for every semiconductor and other-pre-profit row in the shadow layer.
   Additionally `semiconductor` is absent from `applicability_matrix.json`'s own `profiles`
   array (lines 3-15) while present in its `rules` — rules-only.
2. **Four weighted metrics have no `metric_registry.json` entry at all**: `ev_to_ebit`,
   `gross_profits_to_assets`, `asset_growth`, `earnings_surprise` (checked against both the
   `metrics` object and `metric_inventory`, `metric_registry.json:22-52`). Their definitions/units
   in this document are code-derived (`fundamentals_extended.py:655-677` for units) and marked
   accordingly. In the v2 layer, `applicability_for` (`canonical_metrics.py:141-150`) treats a
   registry-less metric as *applied by default* for every profile.
3. **Two applicability authorities disagree by construction.** The live scorer uses
   `suppressed_metrics` (matrix rules only). The v2 shadow layer uses `applicability_for`, which
   *additionally* suppresses any metric whose registry entry does not list the profile in
   `applicability_profiles`. Because no registry entry lists `semiconductor` — including
   `declaration_defaults.applicability_profiles` (`metric_registry.json:12`) — the v2 layer
   suppresses nearly every registry-declared metric for semiconductors while the live scorer
   suppresses only `capex_to_depreciation` and `inventory_days_trend`. Same mechanism:
   `forward_pe`'s registry entry (`metric_registry.json:65`) omits `profitable_biotechnology`,
   so v2 suppresses forward P/E for profitable biotechs while the live scorer scores it.
   Shadow-only today, but it is a live fork in "one authority" intent.
4. **`sales_multiple` value-trap tier is unreachable**: `multiple_score` supports
   `suspicious_below`, but neither `ev_to_sales_by_sector` nor `price_to_sales_by_sector`
   defines that key (`settings.json:698-729, 923-954`), so the 60-point tier never fires for the
   sales multiple.
5. **`v2` aliases**: `revenue_growth` → registry `trailing_revenue_growth`, `earnings_growth` →
   `trailing_eps_growth`, `sales_multiple` → `price_to_sales` (`scoring_v2.py:72-76`). The live
   scorer reads the snapshot keys directly; only the shadow layer resolves the aliases.

## 8. Defaults and imputations sweep

Mechanical sweep over `pipeline/*.py` for silent defaults that can affect a published score,
coverage, modifier, guidance, or screen ranking. Patterns grepped: `' or 0'`, `' or 50'`, `' or 99'`, `', 50.0'`, `', 0.0)'`, `'.get(k, <number>)'`, `'default='`, `'else 50'`, `'else 0'`;
every hit's context was read before classification. Files swept:
`pipeline/scorer.py`, `pipeline/advisor_engine.py`, `pipeline/scoring_v2.py`, `pipeline/recommendation_policy_v2.py`, `pipeline/fetch_advisor.py`, `pipeline/fundamentals_extended.py`, `pipeline/canonical_metrics.py`, `pipeline/risk_metrics.py`, `pipeline/technical_indicators.py`, `pipeline/news_intelligence.py`, `pipeline/insider_signal.py`, `pipeline/institutional_ownership.py`, `pipeline/congress_signal.py`, `pipeline/concentration_risk.py`, `pipeline/geographic_exposure.py`, `pipeline/peer_groups.py`, `pipeline/rank_picks.py`, `pipeline/rank_emerging_growth.py`, `pipeline/research_screens_v2.py`, `pipeline/screen_inputs.py`, `pipeline/explainability.py`, `pipeline/fetch_etfs.py`, `pipeline/providers.py`. Excluded as
non-publishing: `pipeline/tests/`, `backtest_*.py`, `validation/`, `reports/`. The same 46
findings appear machine-readable in `registry.json` → `defaults_and_imputations.findings`.

Scope legend — **champion**: the live published score/guidance path; **picks**: `picks.json`
bucket rankings; **screen**: published research screens; **etf_screen**: ETF comparison screen;
**shadow_v2**: the v2 shadow layer (published beside, not driving the production label).

| # | Site | Trigger | Default / behavior | Feeds | Scope | Class |
|---|---|---|---|---|---|---|
| 1 | `pipeline/scorer.py:159-163 (weighted_available)` | a metric score is None (missing or suppressed) | metric dropped from the category mean; its weight is renormalized across the surviving metrics in the same category | every published fundamentals category score and therefore the composite | champion | renormalization (documented; coverage penalizes it separately) |
| 2 | `pipeline/scorer.py:515-535 (_categories_with_required_gate)` | a profile-required metric (applicability_matrix.required_for_score) is missing | the whole category publishes null with categories_withheld naming the metric; the null category is then dropped by weighted_available at the category level, renormalizing its category weight across surviving categories | fundamentals component | champion | withholding gate; note the withheld category's weight silently re-spreads to the other categories |
| 3 | `pipeline/scorer.py:91-96 (band_score)` | value < 0 for a band-scored metric (peg, price_to_book, price_to_tangible_book, debt_to_equity) | fixed score 15.0 ('penalize, don't zero out') | metric score | champion | fixed imputation for negative readings |
| 4 | `pipeline/scorer.py:142-148 (multiple_score)` | value <= 0 -> 5.0; 0 < value < suspicious_below -> 60.0 | fixed value-trap tiers | forward_pe / EV multiples / sales_multiple scores | champion | fixed tier (documented cutoff, not a silent default) |
| 5 | `pipeline/scorer.py:615-616` | always | fundamentals total = raw * (0.65 + 0.35*coverage): even zero measured coverage would retain 65% of the raw category blend | fundamentals component | champion | coverage scaling floor |
| 6 | `pipeline/advisor_engine.py:846-867 (blend_research_components)` | a component (fundamentals / market_behavior / news_sentiment) is None | component dropped; its ranking weight renormalizes onto the survivors (e.g. news None -> fundamentals effectively 0.78/0.96 = 0.8125). If ALL components are None, raw = 0.0 (a zero score, not a null) | published composite score | champion | renormalization + a fail-to-zero edge case |
| 7 | `pipeline/advisor_engine.py:838-843 (data_coverage_scalar)` | a coverage key absent from the coverage dict | treated as 0.0 in the 0.65/0.25/0.10 weighted completeness scalar | base = raw * (0.8 + 0.2*data_coverage), and the INSUFFICIENT DATA stance gate (<0.45, advisor_engine.py:815-817) | champion | fail-closed default |
| 8 | `pipeline/advisor_engine.py:155-158` | no 12-1 momentum (under ~13 months of history) | momentum input falls back to the 60-day return; if that is also None the momentum_12_1 part is dropped and its 0.30 weight renormalizes | market_behavior component | champion | documented substitution |
| 9 | `pipeline/advisor_engine.py:144-153` | pct_from_52w_high / pct_above_52w_low missing (statement enrichment only runs for a shortlist) | recomputed from the trailing 252 closes when >=200 closes exist | evidence/risk text and screen fields (not a scored sub-metric) | champion | derived fallback |
| 10 | `pipeline/advisor_engine.py:77-92 (volume_confirmation)` | zero down-day volume over the 60-session window | ratio pinned to 2.0 (score 90 after 35+(r-1)*55), instead of None | volume_confirmation sub-score (0.08 weight of market behavior) | champion | fixed imputation |
| 11 | `pipeline/advisor_engine.py:775` | sentiment article_count unmeasured | 'or 0' -> treated as zero articles; the negative-news concern requires >=3 articles so the concern cannot fire | action_for guidance | champion | fail-closed |
| 12 | `pipeline/advisor_engine.py:445-447` | analyst_count missing | 'or 0' -> below the 3-analyst gate -> expectations modifier contributes 0 | expectations modifier | champion | fail-closed |
| 13 | `pipeline/advisor_engine.py:264-512 (all modifier functions)` | a modifiers.* key deleted from settings.json | cfg.get(key, literal) code fallbacks that mirror current config values (e.g. max_penalty 6.0, float_severe 0.15, min_coverage 0.7) | post-blend modifiers | champion | config-mirroring fallback; inert while settings.json carries the keys (verified identical 2026-08-10) |
| 14 | `pipeline/advisor_engine.py:700-712 (_reading) + action_for` | any guidance input missing | explicitly returns None and records the input in unmeasured_inputs; the old '(x or 99)' / '(x or 0)' fail-open defaults are confirmed removed from the live file | SELL/TRIM/WATCH/HOLD guidance | champion | confirmed-fixed (no default remains) |
| 15 | `pipeline/fundamentals_extended.py:161-165 (effective_tax_rate)` | tax rate unreadable or outside [0, 0.6] | 0.21 statutory-federal fallback | return_on_invested_capital (NOPAT), a 0.26-weight profitability metric | champion | silent numeric imputation |
| 16 | `pipeline/fundamentals_extended.py:259-266 (derive_interest_coverage)` | interest expense missing or |interest| < 1 while EBIT > 0 | interest_coverage = 99.0 ('no debt service reads as maximum comfort') | interest_coverage metric (scores 100, 0.30 weight of financial_health) AND action_for's coverage<2 deterioration test (99 = no concern) | champion | deliberate imputation; the one surviving 'or 99'-shaped site |
| 17 | `pipeline/fundamentals_extended.py:176-183 (derive_roic)` | total_debt or cash line missing on the balance sheet | '(total_debt or 0)', '(cash or 0)' in invested capital | return_on_invested_capital | champion | silent zero-imputation |
| 18 | `pipeline/fundamentals_extended.py:190-192 (derive_cash_conversion)` | Free Cash Flow line missing; capex missing in the fallback | FCF = operating_cash_flow - abs(capex or 0): missing capex treated as zero, overstating FCF | cash_conversion (0.16 weight of profitability) | champion | silent zero-imputation |
| 19 | `pipeline/fundamentals_extended.py:269-277 (derive_net_debt_to_ebitda)` | cash line missing | '(cash or 0)': missing cash treated as zero, overstating net debt | net_debt_to_ebitda (0.24 weight of financial_health) | champion | silent zero-imputation (conservative direction) |
| 20 | `pipeline/fundamentals_extended.py:482-495 (derive_enterprise_multiples)` | enterpriseValue missing -> EV = marketCap + (debt or 0) - (cash or 0); goodwill/intangibles missing -> 'or 0' | missing debt/cash imputed zero in EV; missing goodwill/intangibles imputed zero so tangible book = full book equity | ev_to_ebitda, ev_to_ebit, ev_to_sales, ev_to_fcf, price_to_tangible_book | champion | silent zero-imputation |
| 21 | `pipeline/fundamentals_extended.py:314-337 (derive_altman_z)` | an Altman component unreadable | component omitted from the weighted sum (contributes 0) provided >=4 (z) / >=3 (z'') components resolve; otherwise None | altman_z | champion | partial-sum imputation with a floor |
| 22 | `pipeline/fundamentals_extended.py:402-406 (derive_piotroski)` | some of the 9 tests unanswerable | score scaled 9 * passed/answered when >=6 answered; None below 6 | piotroski_f (0.45 weight of accounting_quality) | champion | renormalization with a floor |
| 23 | `pipeline/fundamentals_extended.py:581-583 (derive_market_structure)` | averageVolume missing / 52w high missing | volume from trailing 30 sessions; high/low from trailing 252 closes | liquidity modifier input, 52w context | champion | derived fallback |
| 24 | `pipeline/technical_indicators.py:60-62 (relative_strength_index)` | zero average loss over the 14-day window | RSI = 100.0 if any gain else 50.0 | technical_extended (0.06 of market behavior, ~1% of composite) | champion | fixed imputation (standard RSI convention) |
| 25 | `pipeline/news_intelligence.py:176-191 (weighted_sentiment)` | no article clears entity-confidence/dedup filters | score None + coverage 0.0 (component then drops out of the blend); explicitly NOT the neutral 50 it used to publish | news_sentiment component | champion | confirmed-fixed (fail-closed) |
| 26 | `pipeline/rank_picks.py:30-34 (momentum_score)` | pct_30d missing | neutral 50.0 | short_term bucket_score in picks.json | picks | neutral imputation |
| 27 | `pipeline/rank_picks.py:72-78 (quality_score)` | profitability and growth categories both missing | neutral 50.0 | long_term bucket_score | picks | neutral imputation |
| 28 | `pipeline/rank_picks.py:81-89 (val_or / composite)` | valuation_score (broad fundamental score) missing | neutral 50.0 substituted into the composite. The long_term pool pre-filters non-null (rank_picks.py:210) but short_term and retirement do NOT: a name with no fundamental reading ranks at fundamental-neutral in those buckets; retirement core ETFs are seeded with valuation_score None by construction (rank_picks.py:178) | short_term and retirement bucket_scores | picks | neutral imputation (decision-relevant) |
| 29 | `pipeline/rank_picks.py:59-69 (stability_score)` | market_cap / dividend_yield missing -> 'or 0'; unknown ETF category -> 'sector' -> 55; unknown category label -> 60 | missing size/yield earn no bonus (fail-closed); unknown ETF categories get midtier constants | retirement bucket_score | picks | mixed fail-closed + constant |
| 30 | `pipeline/rank_picks.py:88 / 177` | political_score missing | 0 (no signal credit) | all bucket composites | picks | fail-closed |
| 31 | `pipeline/rank_emerging_growth.py:91-93` | operating-margin trend missing -> margin_score 50.0; volatility-contraction unmeasurable -> contraction_score 50.0 | neutral 50 imputation inside the emerging-growth composite | emerging-growth screen ranking | screen | neutral imputation |
| 32 | `pipeline/research_screens_v2.py:181-184` | price / market_cap / dollar-volume / history missing | 'or 0' -> fails the minimum gate -> row excluded | v2 screen eligibility | screen | fail-closed |
| 33 | `pipeline/research_screens_v2.py:187` | a standardized momentum component missing for a row | '(standardized[field][index] or 0)' -> contributes a 0 z-score (cross-sectional mean) to the momentum composite instead of dropping/renormalizing | momentum screen ranking | screen | neutral imputation |
| 34 | `pipeline/research_screens_v2.py:253` | peer_value_score missing | 'or 0' -> fails the >=40 cheapness test | value-turnaround screen | screen | fail-closed |
| 35 | `pipeline/fetch_advisor.py:1066` | valuation_score missing during enrichment selection | sorts as 0 -> the name is deprioritized for statement enrichment | which symbols get statement-derived metrics at all (coverage feedback loop) | champion-adjacent | fail-closed with a self-reinforcing coverage effect |
| 36 | `pipeline/fetch_etfs.py:274-275 (_average)` | no sub-scores resolve for an ETF factor average | neutral 50.0 | ETF screen score | etf_screen | neutral imputation |
| 37 | `pipeline/fetch_etfs.py:~285 (ISSUER_QUALITY.get(issuer, 60))` | unknown ETF issuer | structural-quality base 60 | ETF screen score | etf_screen | constant default |
| 38 | `pipeline/insider_signal.py:144-148,198 / pipeline/congress_signal.py:73` | transaction value / amount_lower missing | 'or 0' -> fails the min_trade_value gate -> transaction ignored | insider / congressional modifiers | champion | fail-closed |
| 39 | `pipeline/explainability.py:50,118` | fundamental raw/score not numeric | attribution weight falls back to 0.0 (no attribution credit) | published explainability attribution (display), reconciled to 0.01 tolerance | champion-display | fail-closed |
| 40 | `pipeline/scoring_v2.py:162,180` | always (constants) | provenance_reliability 0.72 with observations else 0.55; timing reliability 0.85/0.55 - hardcoded reliability priors, not measured | v2 structural/timeliness confidence (shadow) | shadow_v2 | hardcoded prior |
| 41 | `pipeline/scoring_v2.py:167,182` | confidence < 1 | effective = 50 + confidence*(raw-50): shrink toward neutral 50; raw None stays None (the old constant-50 timeliness default is confirmed removed; layer_health.assert_layers_vary guards the publish path) | v2 effective scores (shadow) | shadow_v2 | shrinkage toward 50 (fixed; fail-closed when absent) |
| 42 | `pipeline/recommendation_policy_v2.py:40-43 (effective_score)` | raw_score non-numeric | _number(raw_score, 50.0) -> neutral 50; confidence non-numeric -> 0.0 (full shrink to 50) | v2 company actions (shadow). NOTE: _score_layer (lines 46-62) guards raw None before calling, so the 50.0 default is currently unreachable through the production caller; it remains live for any direct caller | shadow_v2 | neutral imputation (guarded) |
| 43 | `pipeline/recommendation_policy_v2.py:286-299 (classify_portfolio_fit)` | portfolio context missing | current_weight -> 0.0, target_weight -> 0.03, maximum_weight -> 0.05 (config/recommendation_policy_v2.json portfolio.default_target_weight/default_max_weight); a ticker with no portfolio data classifies below_target | v2 portfolio-fit and trim sizing (shadow) | shadow_v2 | config-default imputation |
| 44 | `pipeline/recommendation_policy_v2.py:202-204` | crowded-short signal | signal confidence hardcoded 0.7 | v2 deterioration groups (shadow) | shadow_v2 | hardcoded prior |
| 45 | `pipeline/recommendation_policy_v2.py:596-598` | position action not from company_deterioration | position_action.confidence published as 1.0 | v2 position action (shadow) | shadow_v2 | constant confidence |
| 46 | `pipeline/recommendation_policy_v2.py:531-533` | no layer resolved | company_confidence 0.0 -> insufficient_evidence gate | v2 company action (shadow) | shadow_v2 | fail-closed |

Reading of the sweep: the champion *metric-scoring* path is now largely fail-closed — missing
values become `None`, drop out, and renormalize — and the three previously fail-open guidance
defaults (`interest_coverage or 99`, drawdown `or 0`, sentiment neutral-50) are confirmed
removed from `action_for`/`news_intelligence`. The surviving risk concentrations are:
(1) statement-derivation zero-imputations (`fundamentals_extended.py` — tax 0.21, `or 0` on
debt/cash/capex/goodwill, interest-coverage 99.0) which can bias *metric values* rather than
scores; (2) neutral-50 imputations in the **picks** and **screen** rankers
(`rank_picks.val_or`, `momentum_score`, `quality_score`; `rank_emerging_growth`;
`research_screens_v2.py:187`), which still rank missing data as average; and (3) hardcoded
reliability priors in the shadow v2 layer.

## 9. Sanity checks (executed 2026-08-10, python3 over live config)

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
