# Audit Round 3: Measurements

Round 3 of the methodology dispute, resolved empirically on 2026-08-10. Every codebase claim
below was verified against live code, not the methodology document. Every measurement ran
against either the latest full pit_store refresh (`advisor-2026-08-10T17:22:04`, 880 names)
or offline five-year monthly backtests recomputed from `pipeline/data/backtest_cache` (860
cached tickers, 60 rebalances) using the production scoring functions themselves. The
measurement scripts are committed at `research/audit/round3/` and each section names the one
that produced its numbers.

The largest finding belongs to neither prior round. Statement-derived metrics currently
resolve for 14 to 21 percent of the universe, so the factors both rounds argued about are
simply unmeasured for roughly 85 percent of names. Several disputed mechanisms turn out to be
second-order next to that.

---

## 1. Verdict summary

| Open item | Measured result | Who was right |
|---|---|---|
| 1. Band compression | Bands do not compress SD or IQR (composite SD 11.8 bands vs 10.2 cross-sectional). Bands quantize: the median metric has 5 distinct values and puts 39% of names on one value, up to 70% for accruals. The effect concentrates in accounting quality and profitability, not valuation as predicted. | Split. Auditor right that it was measurable today without the harness, and right that bands destroy within-band ordering. Auditor wrong on the form (quantization, not variance compression), wrong on the location (accounting quality, not valuation), and wrong that this explains the missing loadings (coverage does, see section 7). Rebuttal's wait-for-the-harness position was wrong procedurally. |
| 2. Turnover decomposition | Baseline 50.6% monthly on today's cache. Fundamentals alone 12.2%. Adding the technical component takes it to 49.3% (+37.1pp). Modifiers add 1.3pp. News adds exactly 0 (renormalized out of the backtest blend). Pure band flicker is 6% of daily metric-score changes. | Split. Auditor right on the dominant driver (technical). Auditor wrong on news (zero by construction) and wrong on band flicker (6%, and bands are the stabilizing element, cross-sectional churns more per metric). Rebuttal right that it needed measuring, but the auditor's main attribution survives the measurement. |
| 3. Growth block vs CMA | Full model CMA loading +0.017 (se 0.300, t 0.06). Growth block zeroed: +0.025 (t 0.08), a change of +0.008. No aggressive-investment loading exists, and removing the growth block changes nothing. The fundamentals-only sleeve loads +0.339 on CMA (t 2.32). | Rebuttal. The auditor's five-to-one arithmetic is correct about weights and wrong about consequences. Raw revenue and EPS growth do not map onto the investment dimension CMA prices. Note also the round's sign error: an aggressive-investment tilt would show a negative CMA loading, not positive. |
| 4. Coverage comparability | Spearman(coverage, final score) = 0.554. The two stacked coverage multipliers alone span 0.52 to 0.97, a 1.87x score ratio from data availability. Financials score 9.9 points above the rest (Mann-Whitney p<0.001). Coverage vs log market cap is only 0.138, so the size-proxy hypothesis fails on current data. | Auditor on the defect's existence, and it is worse than claimed. Auditor wrong on the size-proxy mechanism. Rebuttal wrong twice: FINANCIAL_EXEMPT was cited as live code but is retired (scorer.py:166-179), and the suppression regime shifts financials up, not into comparability. |
| 5. Shrinkage direction | The two forms agree at rho 0.996 overall but 27.4% of names move more than 10 ranks, max 238. Production pushes every thin-data name down regardless of evidence direction and inflates well-covered mediocre names. The literature supports shrinkage toward the cross-sectional prior (James-Stein, Efron-Morris). The correct form already exists in the codebase as the cumulative challenger (advisor_engine.py:870-895, target 50). | Auditor. This is a live directional bias, not a preference. The measurement also surfaced something worse: three stacked coverage penalties, all directional (section 7). |

The published 64.9% turnover reproduces as 50.6% on the current cache state. The number both
rounds argued over is cache-dependent. All decompositions below are internally consistent
against the same 50.6% baseline.

---

## 2. Item 1: band vs cross-sectional dispersion

Setup: the pipeline already publishes both normalizers' output for every metric on every row
(`normalized_metric_scores.champion` from the band functions at scorer.py:91-156,
`normalized_metric_scores.challenger` from CrossSectionalNormalizer at scorer.py:307-461).
The comparison therefore uses production output on one identical snapshot with zero
re-implementation.

### Per-metric dispersion (880 names, values are band / cross-sectional)

| Metric | Category | SD | IQR | Modal fraction | Distinct values |
|---|---|---|---|---|---|
| ev_to_ebitda | valuation | 35.0 / 29.9 | 85.0 / 49.5 | 0.31 / 0.04 | 4 / 99 |
| ev_to_ebit | valuation | 33.6 / 31.0 | 65.0 / 52.5 | 0.34 / 0.04 | 4 / 108 |
| ev_to_fcf | valuation | 31.7 / 32.0 | 55.0 / 55.3 | 0.46 / 0.05 | 4 / 96 |
| forward_pe | valuation | 22.3 / 29.2 | 20.0 / 50.1 | 0.46 / 0.01 | 5 / 496 |
| peg | valuation | 33.3 / 29.4 | 75.0 / 50.6 | 0.28 / 0.01 | 5 / 412 |
| sales_multiple | valuation | 28.5 / 29.2 | 55.0 / 50.0 | 0.33 / 0.01 | 4 / 513 |
| price_to_book | valuation | 26.5 / 29.1 | 50.0 / 50.2 | 0.40 / 0.01 | 6 / 525 |
| price_to_tangible_book | valuation | 26.5 / 33.0 | 25.0 / 61.6 | 0.45 / 0.04 | 5 / 58 |
| return_on_invested_capital | profitability | 34.2 / 30.8 | 70.0 / 52.2 | 0.34 / 0.04 | 5 / 112 |
| gross_profits_to_assets | profitability | 28.2 / 31.0 | 45.0 / 54.7 | 0.49 / 0.03 | 5 / 106 |
| free_cash_flow_yield | profitability | 25.7 / 29.3 | 25.0 / 51.0 | 0.39 / 0.01 | 5 / 448 |
| cash_conversion | profitability | 31.2 / 32.6 | 20.0 / 56.6 | 0.68 / 0.03 | 5 / 123 |
| return_on_equity | profitability | 34.1 / 29.3 | 70.0 / 50.4 | 0.33 / 0.01 | 5 / 520 |
| profit_margin | profitability | 30.1 / 29.2 | 70.0 / 50.3 | 0.25 / 0.01 | 5 / 587 |
| interest_coverage | financial health | 29.3 / 30.4 | 45.0 / 54.0 | 0.55 / 0.06 | 5 / 109 |
| net_debt_to_ebitda | financial health | 31.1 / 32.7 | 45.0 / 60.7 | 0.42 / 0.04 | 5 / 111 |
| altman_z | financial health | 34.1 / 30.2 | 45.0 / 52.1 | 0.52 / 0.05 | 5 / 92 |
| debt_to_equity | financial health | 29.7 / 29.3 | 50.0 / 51.0 | 0.35 / 0.01 | 5 / 464 |
| current_ratio | financial health | 30.1 / 29.3 | 45.0 / 50.0 | 0.31 / 0.01 | 5 / 475 |
| revenue_growth | growth | 30.1 / 29.2 | 25.0 / 50.3 | 0.31 / 0.01 | 5 / 493 |
| earnings_growth | growth | 39.2 / 29.2 | 90.0 / 50.5 | 0.47 / 0.01 | 5 / 435 |
| fcf_growth_3y | growth | 36.9 / 31.4 | 70.0 / 54.9 | 0.46 / 0.03 | 5 / 118 |
| operating_margin_trend | growth | 34.3 / 30.5 | 70.0 / 53.6 | 0.34 / 0.03 | 5 / 128 |
| net_buyback_yield | capital allocation | 33.0 / 30.6 | 70.0 / 51.3 | 0.35 / 0.03 | 5 / 148 |
| stock_comp_to_revenue | capital allocation | 27.7 / 31.0 | 45.0 / 57.5 | 0.37 / 0.03 | 5 / 123 |
| asset_growth | capital allocation | 26.4 / 26.2 | 35.0 / 42.9 | 0.63 / 0.23 | 3 / 60 |
| capex_to_depreciation | capital allocation | 32.4 / 30.0 | 75.0 / 61.7 | 0.38 / 0.12 | 3 / 59 |
| piotroski_f | accounting quality | 23.1 / 31.2 | 25.0 / 48.6 | 0.39 / 0.09 | 4 / 37 |
| accruals_ratio | accounting quality | 15.3 / 29.3 | 20.0 / 46.6 | 0.70 / 0.03 | 5 / 144 |
| days_sales_outstanding_trend | accounting quality | 30.3 / 29.3 | 45.0 / 48.8 | 0.32 / 0.03 | 5 / 112 |
| inventory_days_trend | accounting quality | 33.7 / 26.9 | 45.0 / 39.0 | 0.41 / 0.04 | 5 / 65 |

### Category and composite aggregates (band / cross-sectional)

| Level | SD | IQR | Modal fraction |
|---|---|---|---|
| Valuation | 21.5 / 24.3 | 30.6 / 38.1 | 0.025 / 0.007 |
| Profitability | 21.0 / 19.4 | 28.4 / 25.3 | 0.066 / 0.006 |
| Financial health | 26.0 / 25.4 | 40.7 / 41.0 | 0.187 / 0.006 |
| Growth | 27.9 / 24.3 | 47.8 / 36.2 | 0.138 / 0.007 |
| Capital allocation | 20.4 / 19.5 | 29.0 / 31.3 | 0.122 / 0.016 |
| Accounting quality | 16.1 / 22.0 | 18.4 / 32.3 | 0.155 / 0.021 |
| Fundamentals composite (n=875) | 11.8 / 10.2 | 15.7 / 13.2 | 0.009 / 0.010 |

Spearman between the two fundamentals composites: **0.700**. Distinct composite values: 379
band, 357 cross-sectional. Percentile-rank SD: 28.9 both (ties wash out at composite level).

### Valuation collinearity, eight metrics, pairwise-complete correlations

| | Band | Cross-sectional |
|---|---|---|
| Mean off-diagonal correlation | 0.338 | 0.375 |
| First eigenvalue share | 0.450 | 0.475 |
| Core-5 complete case (n=119, EV multiples + fPE + sales) | mean 0.492, first eig 0.597 | mean 0.566, first eig 0.657 |
| EV/EBITDA vs EV/EBIT pair | 0.83 | 0.87 |

Only 13 names carry all eight valuation metrics, which is itself a finding (section 7).

### Item 1 verdict

The dispersion defect exists but is not the defect the auditor described.

1. Bands do not compress variance. Band SD exceeds cross-sectional SD on 17 of 31 metrics,
   and the band composite has more SD and IQR than the cross-sectional composite. The claim
   "compressed dispersion" is refuted in the variance sense.
2. Bands quantize. The median metric produces 5 distinct values and puts 39 percent of the
   universe on a single value. Accruals puts 70 percent on one value, cash conversion 68,
   asset growth 63. Within a band, ordering information is destroyed entirely. A stock at
   EV/EBITDA 5.1 and one at 9.9 receive identical scores.
3. The location prediction fails. The worst quantization sits in accounting quality (category
   IQR 18.4 vs 32.3) and in individual profitability and capital-allocation metrics, not in
   valuation. Valuation category dispersion is modestly lower under bands (IQR 30.6 vs 38.1),
   nothing like an order-of-magnitude collapse.
4. Collinearity: the auditor's 0.7 to 0.9 claim holds only for the EV/EBITDA and EV/EBIT
   pair. The block-wide mean correlation is 0.34 to 0.57 depending on the case, first
   eigenvalue share 0.45 to 0.66. Real redundancy, but the effective breadth of the block is
   roughly 3, not 1.
5. The auditor was right that all of this was measurable today without forward returns. The
   Round 2 position that promotion arguments had to wait for the 24-period harness confused
   an alpha question with a construction question.
6. Promotion recommendation: not on dispersion grounds alone. Cross-sectional wins on
   comparability and tie-breaking and loses on stability (section 3 shows it churns more per
   metric). The measured driver of the missing factor loadings is coverage, not
   normalization (sections 4 and 7). Fix coverage first, then promote cross-sectional for
   its comparability properties, with the turnover-control layer in place to absorb its
   higher churn.

Script: `research/audit/round3/item1_dispersion.py` and `item1b_collinearity.py`. Core logic:

```python
rows = [json.loads(l) for l in open("pipeline/pit_store/2026-08-10.jsonl")]
rows = [r for r in rows if r["refresh_id"] == max(r["refresh_id"] for r in rows)]
# per metric, per mode: np.std, IQR via np.percentile, modal share via Counter,
# composites re-derived with settings.json category/metric weights exactly as
# weighted_available() does, then scipy.stats.spearmanr between modes
```

---

## 3. Item 2: turnover decomposition

Two frequencies. Monthly, from full five-year offline backtests through the production
scoring path (`rank_week` at backtest_historical.py:331 calls the real `valuation_score` and
`build_research`), with components patched out one at a time. Daily, from consecutive
pit_store refreshes where both normalizers' scores are published.

### Monthly decomposition, 60 rebalances, identical cache and calendar

| Variant | Mean monthly turnover | Median | CAGR | Max drawdown |
|---|---|---|---|---|
| Full model (fund + technical + modifiers, news absent) | **50.6%** | 50.2% | 12.59% | -19.0% |
| Fundamentals only | **12.2%** | 3.5% | 14.17% | -26.7% |
| Fundamentals + technical, no modifiers | 49.3% | 49.9% | 12.46% | -19.0% |
| Full model + rank-buffer 2.0 (hold while rank <= 2N) | **33.7%** | 31.1% | 12.37% | -19.8% |

Attribution table, summing to the observed baseline:

| Source | Contribution |
|---|---|
| Fundamentals (band mode, quarterly statements) | 12.2pp |
| Technical component (18% weight) | +37.1pp |
| Modifier stack | +1.3pp |
| News sentiment | +0.0pp |
| **Total** | **50.6%** |

News contributes exactly zero because `rank_week` passes empty news, `sentiment_score`
returns None (verified by direct call), and `blend_research_components`
(advisor_engine.py:846-867) renormalizes over available components. The 64.9% figure the
auditor attributed partly to news was produced by a configuration in which news cannot
contribute turnover at all.

### Band-boundary flicker, daily, five consecutive refresh pairs

Champion metric-score changes across all pairs: 395. Changes where the raw input moved less
than 1 percent (pure band flicker): **24, which is 6 percent**. Forward P/E accounts for half
of those (12). For comparison, cross-sectional scores moved more than 5 points on 1,686 of
30,326 raw-stable observations (5.6 percent), because a percentile repricing needs no raw
move at all. Bands are the turnover-stabilizing normalizer, not the destabilizing one.

### Daily top-decile turnover, common tickers only

| Variant | Mean daily turnover |
|---|---|
| Full champion (published score) | 0.239 |
| Full cumulative challenger | 0.374 |
| Fundamentals only, band mode | 0.168 |
| Fundamentals only, cross-sectional | 0.389 |

Caveat: the 08-05 to 08-07 pairs are contaminated by the enrichment recovery (universe grew
365 to 880 and coverage was climbing daily). On the two stable pairs the gap narrows and
partially reverses (champion 0.26 and 0.32, challenger 0.21 and 0.29). Daily churn of a
quarter of the top decile per refresh is itself a defect (section 7).

### Item 2 verdict

The decomposition is in hand. The technical component drives roughly three quarters of the
observed turnover. The auditor's attribution was half right (technical), half wrong (news is
structurally zero, band flicker is 6 percent). The Round 2 objection that the attribution was
unmeasured was sustained, and the measurement then mostly vindicated the auditor's main
suspect. The rank buffer, run through the backtest's own `apply_controls`
(portfolio_construction.py:151), cuts turnover by a third and transaction cost by 30 percent
(3,715 to 2,595 dollars on the simulated book) for 22bps of CAGR, inside noise. Fix
recommendation now that the decomposition exists: rank-buffer hysteresis first, then reweigh
or dampen the technical sleeve, and ignore news and band flicker as turnover levers.

Scripts: `bt_variant.py` (patches `advisor_engine.RANKING_WEIGHTS`, `apply_modifiers`, or
`scorer.SETTINGS` category weights, then runs `backtest_monthly.main()` offline with
`--cache-only`), `item2_daily_turnover.py`.

---

## 4. Item 3: growth block vs investment factor

Method: reconstruct clean monthly returns from each backtest's locked picks (weight times
price relative between consecutive execution dates, prices from the same cache the backtest
traded on), regress excess returns on the Fama-French five factors plus momentum from the
locally cached French Data Library files (`pipeline/data/factors/*.zip`), Newey-West HAC
standard errors, 6 lags, 58 months.

| | Full model | Growth block zeroed | Fundamentals only |
|---|---|---|---|
| Annualized alpha | +0.43% (t 0.09) | +0.41% (t 0.09) | +3.34% (t 0.83) |
| Mkt-RF | +0.70 (t 6.78) | +0.71 (t 7.06) | +0.95 (t 9.62) |
| SMB | +0.30 (t 2.30) | +0.30 (t 2.22) | +0.09 (t 0.55) |
| HML | +0.11 (t 0.58) | +0.11 (t 0.54) | +0.02 (t 0.12) |
| RMW | +0.22 (t 1.09) | +0.24 (t 1.14) | +0.08 (t 0.47) |
| **CMA** | **+0.017 (se 0.300, t 0.06)** | **+0.025 (se 0.306, t 0.08)** | **+0.339 (se 0.146, t 2.32)** |
| MOM | +0.32 (t 2.03) | +0.32 (t 2.10) | -0.27 (t -3.07) |
| R2 | 0.529 | 0.529 | 0.715 |

The full-model regression independently reproduces the disputed Round 1 pattern: market,
size, and momentum load, value and profitability do not, alpha is indistinguishable from
zero. Nobody fabricated that result.

Cross-sectional characteristic tilts on the current snapshot: Spearman(champion score, raw
asset growth) = -0.037 (p 0.41, no balance-sheet-expansion tilt), revenue growth +0.203,
earnings growth +0.361.

### Item 3 verdict

The auditor's arithmetic was right and the implication fails measurement.

1. The composite carries no aggressive-investment loading. CMA is +0.02 with a standard
   error of 0.30. Zeroing the entire growth block moves CMA by +0.008 and CAGR by +0.14pp.
   The five-to-one weight arithmetic has no measurable factor consequence, because revenue
   and EPS growth are not the investment characteristic CMA prices, and the score shows zero
   rank correlation with raw asset growth.
2. One sign correction to this round's framing: a tilt toward aggressive investment would
   appear as a negative CMA loading. CMA is long conservative, short aggressive.
3. The fundamentals-only sleeve loads +0.34 on CMA at t 2.32. The correctly-signed
   investment exposure the Round 2 rebuttal claimed is real and statistically visible, and
   the 18 percent technical sleeve plus modifiers dilute it to zero in the shipped score.
   The same dilution flips MOM from -0.27 to +0.32. The blend is spending the fundamentals
   sleeve's factor structure to buy a momentum loading.
4. Power caveat: with se 0.30 in the full model, loadings under about 0.6 are undetectable
   at 58 months. The claim is "no detectable tilt," not "exactly zero." The fundamentals-only
   result is detectable because its se is half as large.
5. The growth block still fails to earn its 8.58 percent: removing it changes returns by
   +14bps and factor structure by nothing. It is dead weight by measurement, just not the
   wrong-signed weight the auditor claimed.

Script: `item3_regression.py`.

```python
rets[ym_of(exec_a)] = sum(w_i * (P_i(exec_b)/P_i(exec_a) - 1)) / sum(w_i)
sm.OLS(rets - RF, sm.add_constant(ff[["MktRF","SMB","HML","RMW","CMA","MOM"]]))
  .fit(cov_type="HAC", cov_kwds={"maxlags": 6})
```

---

## 5. Item 4: coverage comparability

`weighted_coverage()` lives at scorer.py:496-512. FINANCIAL_EXEMPT does not exist in live
code. It was retired with an explanatory comment at scorer.py:166-179 documenting exactly the
defect this item hypothesized (deleting evidence raised measured coverage, THG published a
95.7 value score with 13 of 33 metrics missing). Applicability now has one authority,
`canonical_metrics.suppressed_metrics`. The Round 2 rebuttal cited FINANCIAL_EXEMPT as an
active mitigation. That was stale, and the auditor's instinct to audit this area was correct.

### Measurements, current snapshot, 879 scored names

Fundamentals coverage deciles: 0.17, 0.23, 0.25, 0.29, 0.29, 0.29, 0.29, 0.32, 0.91.
Bimodal: a statement-enriched minority near 0.9, a majority scored on roughly 30 percent of
intended metric weight.

| Measurement | Value |
|---|---|
| Spearman(fundamentals coverage, final champion score) | **+0.554** (p 6e-72) |
| Pearson | +0.634 |
| Combined multiplicative coverage penalty, range | 0.52 to 0.97 |
| Max score ratio between identical evidence at different coverage | **1.87x** |
| Spearman(coverage, log market cap) | +0.138 (p 4e-5) |
| Spearman(log market cap, score) | +0.016 |
| Financials score vs all others | mean 56.9 vs 47.0, median 54.6 vs 45.6, Mann-Whitney p<0.001 |
| Real Estate (lowest coverage, 0.20) score | mean 39.9, lowest of all sectors |

The coverage penalty is applied twice multiplicatively, both times pulling toward zero:
`raw * (0.65 + 0.35 * coverage)` inside the fundamentals score (scorer.py:642-643, and again
in the cross-sectional path at scorer.py:680-681), then `raw * (0.8 + 0.2 * data_coverage)`
at the blend (advisor_engine.py:861), where fundamentals coverage re-enters
`data_coverage_scalar` at 65 percent weight (advisor_engine.py:827-843).

### Item 4 verdict

1. The model substantially ranks data availability. A rank correlation of 0.554 between
   coverage and the output score, under a currently degraded provider, means the leaderboard
   today is closer to "which names have statements enriched" than to any factor thesis.
2. The size-proxy hypothesis fails on current data. Coverage correlates with size at 0.138
   and score correlates with size at 0.016. The 2.06 SMB loading in the backtest regression
   cannot be attributed to coverage-as-size from this snapshot, and the backtest-era
   coverage structure is not reconstructable from the pit store, so that hypothesis stays
   open, unproven either way.
3. Financials are shifted up, not down. Suppression removes inapplicable metrics from the
   denominator (scorer.py:633-637), so banks and insurers are scored on fewer metrics with
   higher average scores. The direction is opposite to the "banks penalized" framing.
4. Coverage vs forward return is unmeasurable today. Zero pit rows have realized horizons
   (store opened 2026-08-05). Measurable after roughly 21 trading sessions for the 1-month
   horizon.

### Literature

The field's answer to incomplete metric coverage is imputation to a neutral cross-sectional
value plus explicit missingness handling, never renormalization onto whatever happens to be
present, and never scaling the composite by completeness:

- Jensen, Kelly, and Pedersen, "Is There a Replication Crisis in Finance?", Journal of
  Finance 78(5), 2023, 2465-2518. Characteristics are cross-sectionally rank-transformed
  and missing values are imputed at the neutral cross-sectional value in their factor
  construction, documented in the paper's Global Factor Data codebase.
- Bryzgalova, Lerner, Lettau, and Pelger, "Missing Financial Data," Review of Financial
  Studies 38(3), 2025, 803-882. Missingness affects over 70 percent of firms, is systematic
  rather than random, and invalidates naive handling. Directly on point: this model's
  missingness is provider-driven and sector-correlated, the systematic case they warn about.
- Freyberger, Hoeppner, Neuhierl, and Weber, "Missing Data in Asset Pricing Panels," Review
  of Financial Studies 38(3), 2025, 760-802. Conditional-mean imputation with weighted least
  squares yields valid inference and better out-of-sample predictability.
- Chen and McCoy, "Missing Values Handling for Machine Learning Portfolios," Journal of
  Financial Economics, 2024. Simple cross-sectional imputation performs close to complex
  EM approaches for portfolio construction.

The production design (renormalize weights over present metrics, then multiply the score by
completeness twice) matches nothing in this literature. The renormalization silently changes
what the score measures per stock, and the completeness multipliers convert missing data
into a directional short on thin-coverage names.

Script: `item4_coverage.py`.

---

## 6. Item 5: confidence shrinkage direction

Both transforms applied to identical raw blends and coverages, reconstructed exactly from
published rows (raw = (score - modifier_total) / (0.8 + 0.2 * coverage), valid for the 878 of
880 unclamped rows). Modifiers excluded from both sides.

| Measurement | Value |
|---|---|
| Spearman(production ranking, v2 ranking) | 0.996 |
| Names moving more than 10 ranks | 241 (27.4%) |
| Names moving more than 25 / 50 ranks | 50 / 20 |
| Largest single move | 238 ranks |
| Spearman(coverage, rank): production / v2 / raw | -0.659 / -0.627 / -0.614 |
| Below-neutral names (raw <= 50): corr(coverage, rank shift) | **-0.895** |
| Below-neutral, low-coverage tercile: mean shift vs v2 | +17.2 ranks worse under production |
| Below-neutral, high-coverage tercile | -17.9 ranks better under production |

Concrete pairs: PINC (raw 50.6, coverage 0.17) sits 94 ranks lower under production than
under neutral shrinkage. BROS (raw 46.1, coverage 0.87) sits 238 ranks higher under
production than under v2. Production treats "well-measured and slightly below average" as
better than "thinly measured and average." Neutral shrinkage treats measurement quality as
uninformative about direction, which is the Bayesian position.

Note the rank correlations with raw: coverage predicts rank at -0.614 before either
transform touches anything, because the fundamentals composite is already
coverage-multiplied (item 4). The blend-level shrink only adds -0.045 of coverage-rank
correlation on top. The production bias is real, and it is the third coverage penalty in a
stack of three, not the first.

### Literature

- James and Stein, "Estimation with Quadratic Loss," Proceedings of the Fourth Berkeley
  Symposium, 1961. Shrinkage toward the grand mean dominates the unshrunk estimator in
  dimension three and above.
- Efron and Morris, "Data Analysis Using Stein's Estimator and Its Generalizations," Journal
  of the American Statistical Association 70(350), 1975, 311-319. The empirical Bayes form:
  posterior = prior mean + reliability * (observation - prior mean). The v2 formula
  `50 + confidence * (raw - 50)` is exactly this with the prior at the scale midpoint.
- Grinold, "Alpha Is Volatility Times IC Times Score," Journal of Portfolio Management,
  1994. Signal-weighting practice scales the deviation from neutral by signal quality. A
  low-quality reading shrinks toward zero alpha, meaning toward the cross-sectional center,
  never toward the bottom of the scale.

No published construction multiplies a positively-oriented composite by a completeness
scalar. The production form is a directional bias.

### Item 5 verdict

The auditor is right. The v2 form is the textbook empirical Bayes construction, the
production form penalizes thin data directionally, and the fix already exists in the
codebase: `shrink_research_components` (advisor_engine.py:870-895) with
`shrinkage_target: 50` is live in the cumulative challenger config (settings.json
challengers.signal_corrections). The correct remediation is one promotion decision plus
removal of the two other coverage multipliers, not new code. One prior-choice refinement for
that promotion: the cross-sectional mean score (currently near 48) is a better shrinkage
target than the constant 50, and a sector-conditional prior is better still.

Script: `item5_shrinkage.py`.

---

## 7. New defects found

Nothing below was raised in Round 1 or Round 2.

**7.1 Statement-enrichment coverage collapse, still live.** Champion-scored coverage on the
current full refresh: profit margin 99%, P/B 96%, forward P/E 85%, then a cliff:
net buyback yield 21%, ROIC 15%, EV/EBITDA 15%, gross profits/assets 14%, Piotroski 16%,
Altman Z 14%, inventory-days trend 8%. The metrics both audit rounds spent their weight
arguing about (enterprise multiples, Novy-Marx profitability, F-score) are unmeasured for
roughly 85 percent of the universe. For those names the valuation block silently renormalizes
onto forward P/E, PEG, P/S, and P/B, which is close to the exact set the evidence ranks worst
(Gray and Vogel, Journal of Portfolio Management 39(1), 2012, Loughran and Wellman, JFQA
46(6), 2011). The cause is the documented 2026-08-06 yahoo_fundamentals provider incident
(docs/BASELINE-2026-08-06.md), recovering at roughly 3 to 5 names per day (9% on 08-05, 21%
on 08-10 for buybacks). This is the single largest measured defect in the system. It
mechanically produces the item 4 coverage-score correlation, and it means the production
score today is mostly a forward P/E, P/S, P/B, margin, and momentum blend, whatever the
config says.

**7.2 Triple coverage penalty.** Three separate mechanisms each push thin-coverage names
down: the fundamentals completeness multiplier (scorer.py:642-643), the blend completeness
multiplier (advisor_engine.py:861), and the within-block weight renormalization that swaps
in weaker metrics. All three are directional. Items 4 and 5 measured their joint effect
(coverage-rank correlation -0.66, score ratio up to 1.87x).

**7.3 ETF misclassification.** VOO and VGT are scored through the stock research path on the
current refresh, and PINC (a healthcare company) carries sector "ETF" in raw inputs.
`valuation_score` is supposed to return None for ETFs (scorer.py:571). The is_etf flag is not
set for these rows. Small, concrete, worth a test.

**7.4 Daily rank churn in the published score.** Top-decile membership changes 24 to 32
percent per day between consecutive refreshes on a stable universe. Nothing in the inputs
justifies that at daily frequency for a 78-percent-fundamentals score. This extends the
narrow-spread churn finding of docs/BASELINE-2026-08-06.md and is mostly the same
technical-sleeve and coverage-recovery noise measured in item 2.

**7.5 The technical sleeve is expensive on every measured axis.** It contributes 37pp of the
50.6% monthly turnover, dilutes the fundamentals sleeve's only significant style exposure
(CMA +0.34 to +0.02), flips MOM sign, and in this window the fundamentals-only variant beat
the full model by 1.6pp CAGR before its far lower costs. It does buy 7.7pp of drawdown
protection (-19.0% vs -26.7%). That trade was never priced anywhere in the methodology, and
64 percent of one year's gross-return edge went to transaction costs it generates. One five-year
window is not proof the sleeve is worthless. It is proof the sleeve has a measurable price.

**7.6 The dispute's anchor number is unstable.** The published 64.9% turnover reproduces as
50.6% on the current cache. Both are true statements about different cache states. Any future
round should pin measurements to a stated cache hash.

---

## 8. Revised remediation order

Ranked by measured impact per unit of effort. Items conceded absent in Round 2 are included
and re-ranked against the new measurements.

| # | Change | Measured impact | Effort |
|---|---|---|---|
| 1 | Finish the statement-enrichment recovery and add a coverage floor gate to publication (do not publish a research score below a stated fundamentals coverage) | Removes the 0.554 coverage-score correlation at its source. Restores the intended factors to 85% of the universe. Every other measurement is contaminated until this lands. | Low. The provider fix exists, backfill is running at 3-5 names/day. Batch it. |
| 2 | Promote neutral-target shrinkage and delete the two other coverage multipliers | Removes a measured directional bias (item 5) and two thirds of the coverage penalty stack (item 4) | Low. Code exists (advisor_engine.py:870-895). One config promotion plus removing two multipliers. |
| 3 | Rank-buffer hysteresis on the composite portfolio layer | Measured: turnover 50.6% to 33.7%, transaction cost -30%, CAGR -0.22pp | Low. Code exists (portfolio_construction.py:151), already tested through the backtest. |
| 4 | Reweigh or dampen the technical sleeve (candidate: keep momentum_12_1 and drawdown_resilience, drop or slow the 20-day relative-strength and volume signals) | The sleeve is +37pp turnover and the measured destroyer of the CMA loading. Even halving its churn outranks every valuation-weight change. | Medium. Requires a variant backtest per candidate, harness for promotion. |
| 5 | EDGAR Financial Statement Data Sets historical backfill | Enables the only honest re-run of every regression here. Unmeasurable impact by definition until done. | High. Unchanged from Round 2. |
| 6 | Valuation-block collapse to two sector-neutralized enterprise multiples | Measured support is weaker than Round 1 claimed: block breadth is ~3 effective factors, not 1, and EV metrics currently cover 15% of names. Sequence after item 1, otherwise this collapses the block onto missing data. | Medium. |
| 7 | Cross-sectional normalization promotion | Quantization is real (5 distinct values per metric) but composite dispersion is fine and cs churns more. Promote for comparability after items 1 and 3 absorb the churn. | Low. Code exists. |
| 8 | MAX / idiosyncratic-volatility screen | Unmeasured here (needs its own backtest). Literature support unchanged (Bali, Cakici, Whitelaw, JFE 99(2), 2011). | Low-medium. |
| 9 | Fix ETF misclassification (7.3) and add a regression test | Three wrong rows today, silent scoring-universe contamination | Trivial. |
| 10 | Portfolio-construction layer beyond the rank buffer (position sizing, risk model) | Partially measured: the buffer alone captures much of the turnover benefit. The rest is unquantified. | High. |

The growth-block restructuring drops off the priority list. Zeroing it moved CAGR +0.14pp and
CMA +0.008. It is dead weight, but removing dead weight ranks below removing measured biases.

---

## 9. What remains unfalsifiable

The following cannot be defended or attacked by any measurement currently available in this
repository, and the measurements above put bounds on what would be required.

1. **Every within-category sub-weight, roughly 30 numbers.** The end-to-end test available
   (60-month backtest, HAC regression) has standard errors of 0.15 to 0.31 on factor
   loadings and cannot distinguish a whole category's presence from its absence (growth
   zeroed: +0.14pp CAGR, +0.008 CMA). No sub-weight choice inside a category can produce an
   effect above that noise floor. Distinguishing EV/EBITDA at 27 versus 18 percent of the
   valuation block would need either decades of monthly cross-sections or a sustained
   metric-level IC record. The 24-period harness is the only instrument in the repo that can
   ever falsify a sub-weight, and it has observed zero periods.
2. **The 78/18/4 top-level split.** The variants measured here bound it coarsely
   (fundamentals-only beats the full model on CAGR and loses on drawdown in one window), but
   one five-year window cannot rank blends. Falsifying it needs the shadow-portfolio store
   accumulating years of net-of-cost prospective performance per blend.
3. **Band cutoffs.** All 100-plus hand-set thresholds in settings.json fundamentals. The
   quantization measurement shows what they destroy, but no measurement in the repo links
   any specific cutoff to returns. If cross-sectional mode is promoted they become moot,
   which is the cheaper resolution than defending them.
4. **Modifier caps and fractions.** The modifier stack contributed 1.3pp of turnover and its
   score contribution is bounded at plus or minus 15 points by construction, but nothing
   measures whether any individual cap (short interest -6, insider +5, macro 3) is right.
   Each would need its own event-style validation against realized returns, which the
   pit_store schema supports and zero elapsed horizons currently prevent.
5. **Coverage vs forward return** (the open half of item 4) and the backtest-era coverage
   structure. The first becomes measurable from 2026-09 as pit horizons mature. The second
   is permanently lost because the store did not exist then, which is itself the strongest
   argument for the EDGAR backfill.

What would change these from unfalsifiable to falsifiable: the pit_store accumulating 24-plus
monthly periods with realized horizons (the harness's own gate), plus deflated-Sharpe and
PBO discipline over any weight search (Bailey and Lopez de Prado, Journal of Portfolio
Management 40(5), 2014).

---

## Round attribution summary

Where measurement corrected Round 2 (my rebuttal): the wait-for-the-harness argument on
normalization was wrong, dispersion was answerable same-day (auditor's point). FINANCIAL_EXEMPT
was cited as live mitigation and is retired code. The sector-suppression regime inflates
financials rather than making them comparable. Credit to the auditor for forcing both
measurements.

Where measurement corrected Round 1 (the audit): band flicker (6 percent, not a major
turnover source), news turnover (zero by construction), dispersion compression (quantization
in accounting quality, not variance compression in valuation), block collinearity (breadth 3,
not 1), the growth-block CMA claim (no loading, and removal changes nothing), and the
coverage-as-size claim (0.138).

Where both rounds missed the point: the enrichment coverage collapse and the triple coverage
penalty dominate every disputed mechanism, and neither round measured a single number.
