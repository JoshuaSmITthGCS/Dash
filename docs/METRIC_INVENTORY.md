# Analytics metric inventory and Phase 0 integrity audit

Audit date: 2026-08-13  
Committed payload: `public/data/report.json`, generated 2026-08-13T20:24:09Z  
Reproduction: `scripts/phase0-analytics-audit.mjs`

## Phase 0 findings (blocking gate)

### Resolution of the 74 returns / 20 months / 1.5 years contradiction

The three labels did not describe one sample.

| surface | source and computation | observations | actual window | actual frequency |
|---|---|---:|---|---|
| Standard Measures | `Portfolio.jsx:294-303` selects `1Y`; `portfolioAnalytics.js:921-961` computes adjacent returns | 75 values / 74 returns | 2025-08-18 to 2026-08-13 (360 calendar days) | irregular: 36 one-day intervals, 9 weekend/holiday intervals, 29 intervals longer than four days; mean gap 4.86 days, maximum 12 |
| Comparison header | `Portfolio.jsx:315-316` passes the unclipped series; `portfolioBenchmarkComparison.js:81-121` collapses it to calendar months | 20 monthly buckets | 2025-01 through 2026-08; the first month starts from the 2024-12-23 value | monthly, derived from 97 irregular intervals |
| Longest underwater | `Portfolio.jsx:317`; `portfolioAnalytics.js:829-882` uses the unclipped dated series | 98 values | 2024-12-23 to 2026-08-13 (598 calendar days) | wall-clock duration over the irregular chart grid |

The underlying published grid has 98 observations / 97 returns over 598 days. Only 36 intervals are one calendar day and 52 are longer than four days. The matching SPY exchange tape contains 410 observations / 409 returns over the same dates, so the published grid contains 23.9% of expected sessions. Within the one-year Standard Measures window it contains 75 of 249 expected observations (30.1%).

This is a combination of cases **(a)** and **(b)** from the brief:

- `pipeline/market_history.py:18-29` deliberately creates a display-oriented chart grid: the last 45 sessions are daily and older history is sampled every seventh trading date, capped at 53 older points.
- `pipeline/fetch_advisor.py:1362-1369,1799-1801,1894` publishes that chart grid as each holding's only browser-visible history and as `benchmark_history`.
- `currentHoldingsSeries()` then treats those display points as an analytics tape.
- Standard Measures clips that tape to one year, while Comparison, underwater duration, acceleration, capture and short-term reads receive the unclipped tape.

The return count is arithmetically correct for the one-year slice, and the underwater calendar duration is arithmetically correct for the full slice. The defects are the undisclosed range split, calling irregular intervals “daily returns,” and annualizing those irregular observations as if each were one trading day.

### Required unification

The implementation following this inventory uses a dedicated daily analytics history rather than the compact chart grid. One selected scope supplies the common base sample to Standard Measures, Comparison and Fast Reads. Frequency-specific metrics keep their own explicit counts and windows: monthly batting average remains monthly; rolling windows report their covered sessions; point-in-time construction metrics say so. If daily analytics history is absent, daily-only statistics become `insufficient` and name that missing input instead of annualizing the chart grid.

### Annualization audit

Naive square-root scaling exists in the following active analytics paths:

| site | affected readings | audit result |
|---|---|---|
| `src/lib/portfolioAnalytics.js:643,724,885,941,944-945` | standalone and portfolio volatility, tracking error, information ratio, Sharpe, Sortino | `sqrt(252)`; invalid on the published irregular chart grid and unadjusted for serial correlation even on a daily tape |
| `src/lib/portfolioShortTermView.js:134` | recent and baseline tracking risk | `sqrt(252)`; invalid on the mixed cadence |
| `src/lib/factorAnalytics.js:110` | factor alpha | linear `×12`; annualizes monthly alpha, while the current standard error is ordinary OLS rather than HAC |
| `pipeline/risk_metrics.py:59,71,87,135` | stock/ETF volatility, Sharpe, Sortino, beta-related risk | `sqrt(252)`; daily inputs but no serial-correlation adjustment |
| `pipeline/backtest_common.py:189` and `pipeline/validation_framework.py:185-191` | backtest volatility, Sharpe, Sortino | `sqrt(periods_per_year)`; no serial-correlation adjustment |
| `pipeline/backtest_monthly.py:256,397-398` | simulated portfolio risk measures | `sqrt(252)`; review separately because some call sites contain daily paths and others are constructed rebalance paths |
| `pipeline/etf_comparison.py:141-145` | ETF Sharpe, Sortino, tracking error | `sqrt(252)`; daily inputs but no serial-correlation adjustment |
| `pipeline/evaluation.py:104` and `pipeline/validation/ic_harness.py:407` | ICIR | `sqrt(periods_per_year)`; this is an information-coefficient consistency statistic, not a return Sharpe, but still assumes independent periods |

The portfolio analytics surface will retain naive figures for comparability and add Lo-adjusted figures labelled as serial-correlation adjusted. No pipeline-wide historical result is silently rewritten by this UI refactor.

### Benchmark audit

- The portfolio analytics comparison is hardcoded to `report.json.benchmark_history`, whose schema fixes `symbol` to `SPY` (`portfolioAnalytics.js:9-18`, `Portfolio.jsx:290-329`, `advisor.schema.json:451-478`).
- The Portfolio heading and labels also hardcode “S&P 500.”
- Benchmark choice is configurable elsewhere: Dashboard and Diversification read `preferences.defaultBenchmark`, and `benchmark-report.json` publishes several histories. That setting is not wired into the Portfolio performance panels.
- The pre-fix fast-read beta against SPY is 0.44, but it is fitted on the irregular display grid and is not a reliable universe-fit estimate. The corrected daily diagnostics below supersede it.
- Daily tradeable proxy histories already exist for SPY, RSP, IWM and IJR under `public/data/etf/`. The refactor adds explicit fit diagnostics and keeps SPY beside the best-fit result; it does not silently replace SPY.

### Post-repair daily verification

The repaired current-holdings replay aligns 503 portfolio and benchmark values / 502 daily
returns from 2024-08-12 through 2026-08-13. It covers 96.0% of calendar weekdays (market
holidays explain the remainder), has no gap over four days, and is therefore accepted as a
native session tape. On that common sample:

| candidate | beta | correlation | R² | tracking error (naive √252) | tracking error (Lo-adjusted) | information ratio |
|---|---:|---:|---:|---:|---:|---:|
| S&P 500 / SPY | 0.881 | 0.669 | 0.447 | 16.46% | 20.99% | -1.23 |
| Equal-weight S&P 500 / RSP | 0.938 | 0.627 | 0.393 | 17.19% | 20.09% | -0.95 |
| Russell 2000 / IWM | 0.566 | 0.551 | 0.304 | 20.55% | 20.89% | -1.06 |
| S&P SmallCap 600 / IJR | 0.593 | 0.551 | 0.304 | 20.14% | 19.11% | -0.92 |

Under the disclosed fit rule `|beta − 1| + (1 − correlation)`, RSP is the best fit. SPY has
the highest correlation. The former 0.44 fast-read beta came from the irregular chart grid
and is not a valid basis for declaring a universe mismatch; the corrected daily SPY beta is
0.88. Benchmark choice remains substantive—RSP improves beta proximity but reduces
correlation—so the UI shows every diagnostic and keeps SPY comparisons beside best-fit
comparisons.

On the same 502-return portfolio sample, naive Sharpe is -0.104 and Lo-adjusted Sharpe is
-0.185. PSR(0) is 44.2%, the Sharpe t-statistic is -0.146, and MinTRL is not estimable because
the measured Sharpe does not exceed zero. The trials registry supplies N=50, but portfolio
DSR remains insufficient because variance of Sharpes across those registered trials is not
recorded.

## Inventory conventions

- `calculationSite` is the pre-refactor canonical producer. Dynamic JSON metrics list their pipeline producer.
- `renderSites` include every analytics presentation surface, with repeated mobile/table renders identified as duplicate renders.
- `sampleSource` distinguishes the current-holdings replay, recorded account history, prospective shadow history, retrospective backtests, and point-in-time validation panels.
- The destination groups are the Phase 4 information architecture groups. A metric may be visible in more than one view, but has one canonical group.

## Portfolio performance and comparison inventory

| id | displayName | calculationSite | renderSites | frequency | sampleSource | isDuplicateRenderOf | proposedGroup |
|---|---|---|---|---|---|---|---|
| strategy_return_twr | Strategy return (time-weighted) | `portfolioAnalytics.js:225-301` | `PortfolioReturnSummary.jsx:9-13`; `Portfolio.jsx:578-583` | point-in-time over dated flows | recorded account snapshots and settled flows | — | Return & Compounding |
| money_weighted_xirr | Your return (money-weighted) | `portfolioAnalytics.js:303-403` | `Performance.jsx:219-224`, `PortfolioScreen.jsx:351-356` | point-in-time over dated flows | holdings, purchase dates, cash flows | — | Return & Compounding |
| portfolio_score | Portfolio Score | `portfolioAnalytics.js:986-995` | `Portfolio.jsx:585-590` | point | six portfolio component scores | — | Exposure & Construction |
| versus_sp500_return | Vs S&P 500 | `portfolioPerformance.js:108-153` | `Portfolio.jsx:591-603` | position-window | purchase-date matched holdings vs SPY | — | Relative Performance |
| annualized_return | Annualized return | `portfolioAnalytics.js:900-902,931` | calculated but not rendered in Standard Measures | irregular/daily-labelled | selected current-holdings series | — | Return & Compounding |
| sharpe_naive | Sharpe ratio | `portfolioAnalytics.js:927-945` | `PerformanceMetrics.jsx:40,89,92` | daily-labelled | selected current-holdings series | — | Risk-Adjusted Return |
| sortino_naive | Sortino ratio | `portfolioAnalytics.js:927-945` | `PerformanceMetrics.jsx:93` | daily-labelled | selected current-holdings series | — | Risk-Adjusted Return |
| calmar | Calmar ratio | `portfolioAnalytics.js:931-946` | `PerformanceMetrics.jsx:94` | sample | selected current-holdings series | — | Risk-Adjusted Return |
| maximum_drawdown | Maximum drawdown | `portfolioAnalytics.js:816,932` | `PerformanceMetrics.jsx:40,95`; `BacktestSummary.jsx:18`; `BacktestComparison.jsx:65,80,159`; `ShadowPortfolios.jsx:55,61-62` | path | portfolio/backtest/shadow series | — | Drawdown |
| current_drawdown | Current drawdown | `portfolioAnalytics.js:933-934` | `PerformanceMetrics.jsx:96` | point | selected current-holdings series | — | Drawdown |
| longest_underwater | Longest underwater | `portfolioAnalytics.js:829-882` | `PerformanceMetrics.jsx:99-110` | wall-clock | full current-holdings series | — | Drawdown |
| current_underwater | Current underwater duration | `portfolioAnalytics.js:868-880` | calculated but not independently rendered | wall-clock | full current-holdings series | — | Drawdown |
| deepest_drawdown | Deepest drawdown | `portfolioAnalytics.js:859-878` | calculated; maximum drawdown is its duplicate measurement | path | full current-holdings series | maximum_drawdown | Drawdown |
| recovery_deepest | Recovery time for deepest drawdown | `portfolioAnalytics.js:841-877` | calculated but not rendered | wall-clock | full current-holdings series | — | Drawdown |
| information_ratio_spy | Information ratio | `portfolioAnalytics.js:935-954` | `PerformanceMetrics.jsx:122-125` | daily-labelled | selected holdings vs SPY | — | Relative Performance |
| acceleration | Acceleration | `portfolioAcceleration.js:70-153` | `PerformanceMetrics.jsx:126-134` | two 91-day legs | full holdings vs SPY | — | Relative Performance |
| acceleration_pct | Acceleration percentage-point change | `portfolioAcceleration.js:129-150` | supporting text in `PerformanceMetrics.jsx:132` | two 91-day legs | full holdings vs SPY | acceleration | Relative Performance |
| acceleration_beta | Acceleration fitted beta | `portfolioAcceleration.js:100-151` | methodology/supporting text | irregular intervals | full holdings vs SPY | — | Benchmark Fit |
| up_capture_spy | Up capture | `portfolioBenchmarkComparison.js:23-74` | `PerformanceMetrics.jsx:137` | interval | full holdings vs SPY | — | Capture Profile |
| down_capture_spy | Down capture | `portfolioBenchmarkComparison.js:23-74` | `PerformanceMetrics.jsx:138` | interval | full holdings vs SPY | — | Capture Profile |
| capture_spread_spy | Capture spread | `portfolioBenchmarkComparison.js:23-74` | `PerformanceMetrics.jsx:139-149` | interval | full holdings vs SPY | — | Capture Profile |
| batting_average_spy | Batting average | `portfolioBenchmarkComparison.js:81-121` | `PerformanceMetrics.jsx:115,150-158` | monthly | full holdings vs SPY | — | Consistency |
| batting_wins_losses | Winning / losing months | `portfolioBenchmarkComparison.js:96-119` | supporting text in `PerformanceMetrics.jsx:155-157` | monthly | full holdings vs SPY | batting_average_spy | Consistency |
| relative_payoff | Win/loss size ratio | `portfolioBenchmarkComparison.js:101-116` | supporting text in `PerformanceMetrics.jsx:156` | monthly | full holdings vs SPY | — | Consistency |
| average_relative_win | Average winning-month excess | `portfolioBenchmarkComparison.js:101-115` | calculated but not rendered | monthly | full holdings vs SPY | — | Consistency |
| average_relative_loss | Average losing-month excess | `portfolioBenchmarkComparison.js:101-115` | calculated but not rendered | monthly | full holdings vs SPY | — | Consistency |
| week_excess | Past week vs index | `portfolioShortTermView.js:65-116` | `PerformanceMetrics.jsx:172-181` | trailing 7 calendar days | full holdings vs SPY | — | Recent Performance |
| month_excess | Past month vs index | `portfolioShortTermView.js:65-116` | `PerformanceMetrics.jsx:182-191` | trailing 30 calendar days | full holdings vs SPY | — | Recent Performance |
| week_portfolio_return | Week portfolio return | `portfolioShortTermView.js:100-108` | supporting text in `PerformanceMetrics.jsx:179` | trailing 7 days | holdings series | week_excess | Recent Performance |
| week_benchmark_return | Week index return | `portfolioShortTermView.js:100-108` | supporting text in `PerformanceMetrics.jsx:179` | trailing 7 days | SPY series | week_excess | Recent Performance |
| month_portfolio_return | Month portfolio return | `portfolioShortTermView.js:100-108` | supporting text in `PerformanceMetrics.jsx:189` | trailing 30 days | holdings series | month_excess | Recent Performance |
| month_benchmark_return | Month index return | `portfolioShortTermView.js:100-108` | supporting text in `PerformanceMetrics.jsx:189` | trailing 30 days | SPY series | month_excess | Recent Performance |
| noise_floor_week | Week noise floor | `portfolioShortTermView.js:52-63,97-112` | calculated, used for week tone, not rendered | trailing 7 days | tracking residuals | — | Signal Strength |
| noise_floor_month | Noise floor (month) | `portfolioShortTermView.js:52-63,97-112` | `PerformanceMetrics.jsx:193-199` | trailing 30 days | tracking residuals | — | Signal Strength |
| excess_streak | Current streak | `portfolioShortTermView.js:118-130` | `PerformanceMetrics.jsx:200-208` | irregular intervals plus elapsed days | holdings vs SPY | — | Portfolio Behavior |
| recent_tracking_risk | Recent tracking risk | `portfolioShortTermView.js:132-143` | `PerformanceMetrics.jsx:209-217` | trailing 30 days | tracking residuals | — | Risk Change |
| baseline_tracking_risk | Baseline tracking risk | `portfolioShortTermView.js:73-84,134-147` | supporting text in `PerformanceMetrics.jsx:214-216` | trailing 180 days | tracking residuals | recent_tracking_risk | Risk Change |
| short_term_beta | Fast-read fitted beta | `portfolioShortTermView.js:37-49,73-83` | methodology header in `PerformanceMetrics.jsx:169` | trailing 180 days | holdings vs SPY | — | Benchmark Fit |

## Risk, construction, factor and exposure inventory

| id | displayName | calculationSite | renderSites | frequency | sampleSource | isDuplicateRenderOf | proposedGroup |
|---|---|---|---|---|---|---|---|
| diversification_score | Diversification score | `portfolioAnalytics.js:755-813` | `Diversification.jsx:48-57` | point plus daily correlation | current holdings | portfolio_score component | Exposure & Construction |
| raw_holding_count | Raw holdings | `portfolioAnalytics.js:807` | `Diversification.jsx:48,57` | point | priced holdings | — | Exposure & Construction |
| hhi | Herfindahl concentration | `portfolioAnalytics.js:770,805` | explained at `Diversification.jsx:123`; value implicit | point | current weights | — | Exposure & Construction |
| effective_holdings | Effective holdings | `portfolioAnalytics.js:806` | `Diversification.jsx:57` | point | current weights | — | Exposure & Construction |
| effective_bets | Effective bets | `portfolioAnalytics.js:633-686,775-812` | `Diversification.jsx:48-57` | daily | common holding returns | — | Exposure & Construction |
| diversification_ratio | Diversification ratio | `portfolioAnalytics.js:600-686,778-810` | `Diversification.jsx:73,81` | daily | common holding returns | — | Exposure & Construction |
| holding_breadth_score | Holding HHI score component | `portfolioAnalytics.js:770-785` | `Diversification.jsx:66-73` | point | current weights | — | Exposure & Construction |
| sector_breadth_score | Sector HHI score component | `portfolioAnalytics.js:766-785` | `Diversification.jsx:66-73` | point | look-through sector weights | — | Exposure & Construction |
| industry_breadth_score | Industry HHI score component | `portfolioAnalytics.js:768-785` | `Diversification.jsx:66-73` | point | holding industries | — | Exposure & Construction |
| pairwise_correlation | Pairwise correlation matrix | `portfolioAnalytics.js:600-686` | `Diversification.jsx:74-81` | daily | common holding returns | — | Exposure & Construction |
| sector_allocation | Look-through sector allocation | `portfolioAnalytics.js:512-598,766-803` | `Diversification.jsx:58-66` | point | holdings and ETF look-through | — | Exposure & Construction |
| industry_allocation | Industry concentration | `Diversification.jsx:14-15` | `Diversification.jsx:116-123` | point | holdings metadata | — | Exposure & Construction |
| position_weight | Holdings by allocation | `portfolioAnalytics.js:759-760` | `Diversification.jsx:109-115` | point | current holding values | — | Exposure & Construction |
| portfolio_volatility | Portfolio volatility | `portfolioAnalytics.js:690-752` | calculated but not rendered in covariance panel | daily | holding covariance | — | Tail Risk |
| expected_shortfall_95 | Expected shortfall 95% | `portfolioAnalytics.js:688,748` | `Diversification.jsx:82-90` | daily | portfolio covariance return reconstruction | — | Tail Risk |
| tracking_error_selected | Tracking error | `portfolioAnalytics.js:717-725` | `Diversification.jsx:90`; duplicate supporting value in `PerformanceMetrics.jsx:123-125` | daily | portfolio vs selected benchmark | — | Benchmark Fit |
| active_share | Active share | `portfolioAnalytics.js:728-741` | `PerformanceMetrics.jsx:220-228`; `Diversification.jsx:90` | point | holdings vs benchmark constituents | — | Portfolio Behavior |
| risk_contribution | Share of total risk | `portfolioAnalytics.js:690-714` | `Diversification.jsx:90` | daily | holding covariance | — | Exposure & Construction |
| marginal_risk_contribution | Marginal contribution to risk | `portfolioAnalytics.js:703-714` | calculated but not rendered | daily | holding covariance | — | Exposure & Construction |
| standalone_volatility | Standalone holding volatility | `portfolioAnalytics.js:643,706` | calculated but not rendered | daily | holding returns | — | Exposure & Construction |
| factor_alpha | Annualized factor alpha | `factorAnalytics.js:65-114` | `Diversification.jsx:91-99` | monthly | portfolio vs French factors | — | Factor Attribution |
| factor_alpha_t | Factor alpha t-statistic | `factorAnalytics.js:97-112` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| factor_r_squared | Factor R² | `factorAnalytics.js:94-113` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| market_loading | Market factor loading | `factorAnalytics.js:4,99-109` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| size_loading | Size factor loading | `factorAnalytics.js:4,99-109` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| value_loading | Value factor loading | `factorAnalytics.js:4,99-109` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| profitability_loading | Profitability factor loading | `factorAnalytics.js:4,99-109` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| investment_loading | Investment factor loading | `factorAnalytics.js:4,99-109` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| momentum_loading | Momentum factor loading | `factorAnalytics.js:4,99-109` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| factor_loading_se | Factor loading standard errors | `factorAnalytics.js:97-110` | `Diversification.jsx:99` | monthly | portfolio vs French factors | — | Factor Attribution |
| theme_exposure_score | Theme exposure | `factorAnalytics.js:117-140` | `Diversification.jsx:100-108` | point | current weights and theme screen | — | Exposure & Construction |
| theme_coverage | Theme portfolio coverage | `factorAnalytics.js:136-140` | `Diversification.jsx:108` | point | current weights and theme screen | theme_exposure_score | Exposure & Construction |

## Backtest, algorithm and validation inventory

The rows below are canonical metrics rendered for one or more strategy/backtest records. Repeating a canonical metric for several named strategies is a duplicate render, not a distinct measurement.

| id | displayName | calculationSite | renderSites | frequency | sampleSource | isDuplicateRenderOf | proposedGroup |
|---|---|---|---|---|---|---|---|
| backtest_total_return | Total return | `pipeline/build_backtest_comparison.py:193-252` | `BacktestComparison.jsx:61-83,75,155` | strategy-specific | retrospective backtest | — | Return & Compounding |
| backtest_cagr | CAGR | same | `BacktestComparison.jsx:63,78,157`; `ShadowPortfolios.jsx:52,61-62` | annualized | retrospective/prospective strategy path | — | Return & Compounding |
| backtest_excess_spy | vs SPY | same | `BacktestComparison.jsx:62,76,156` | strategy-specific | retrospective backtest | — | Relative Performance |
| backtest_success_rate | Success rate | `pipeline/build_backtest_comparison.py:130-178` | `BacktestComparison.jsx:59,73,152` | method-specific period | retrospective backtest | — | Consistency |
| backtest_beat_spy | Beat SPY | same | `BacktestComparison.jsx:60,74,154` | method-specific period | retrospective backtest | — | Consistency |
| backtest_sharpe | Sharpe | strategy producers via `pipeline/backtest_common.py:158-204` | `BacktestSummary.jsx:16`; `BacktestComparison.jsx:64,79,158`; `ShadowPortfolios.jsx:53,61-62` | strategy-specific | retrospective/prospective path | sharpe_naive | Risk-Adjusted Return |
| backtest_dsr | Deflated Sharpe | `pipeline/backtest_common.py:104-153` | `BacktestSummary.jsx:17,50-54`; BacktestComparison fallback | strategy-specific | registered retrospective trials | — | Statistical Confidence |
| backtest_win_rate | Win rate | `pipeline/backtest_common.py:158-204` | `BacktestSummary.jsx:19` | trade | simulated trades | — | Consistency |
| average_pnl_trade | Avg P/L per trade | strategy backtest producers | `BacktestSummary.jsx:20` | trade | simulated trades | — | Consistency |
| trade_count | Trades | strategy backtest producers | `BacktestSummary.jsx:21` | point count | simulated trades | — | Algorithm Diagnostics |
| shadow_aligned_net_return | Aligned net return | `pipeline/shadow_portfolios.py` | `ShadowPortfolios.jsx:50,61-62` | session | common prospective window | — | Relative Performance |
| shadow_net_return | Net return (own window) | `pipeline/shadow_portfolios.py` | `ShadowPortfolios.jsx:51,61-62` | session | strategy prospective window | — | Return & Compounding |
| shadow_sortino | Sortino | `pipeline/shadow_portfolios.py` | `ShadowPortfolios.jsx:54,61-62` | session | strategy prospective window | sortino_naive | Risk-Adjusted Return |
| shadow_turnover | Turnover | `pipeline/shadow_portfolios.py` | `ShadowPortfolios.jsx:56,61-62` | session | strategy weight changes | — | Cost & Capacity |
| shadow_coverage_change | Coverage change | `pipeline/shadow_portfolios.py` | `ShadowPortfolios.jsx:57,61-62` | session | strategy constituent coverage | — | Algorithm Diagnostics |
| shadow_observations | Observations / snapshots | `pipeline/shadow_portfolios.py` | `ShadowPortfolios.jsx:58,61-64` | point count | prospective store | — | Robustness & Validation |
| prospective_mean_ic | Mean rank IC | `pipeline/validation/ic_harness.py` | `LiveValidation.jsx:77` | horizon period | prospective point-in-time panels | — | Robustness & Validation |
| prospective_ic_ci | IC 95% CI | same | `LiveValidation.jsx:78` | horizon period | prospective point-in-time panels | — | Robustness & Validation |
| prospective_icir | ICIR | same | `LiveValidation.jsx:79` | horizon period | prospective point-in-time panels | — | Robustness & Validation |
| prospective_quintile_return | Quintile mean forward return | same | `LiveValidation.jsx:52-62,83-91` | monthly | prospective point-in-time panels | — | Robustness & Validation |

### Signal-metrics registry (all rows rendered by `SignalMetricsPanel.jsx:18-79`)

| id | displayName | calculationSite | renderSites | frequency | sampleSource | isDuplicateRenderOf | proposedGroup |
|---|---|---|---|---|---|---|---|
| rank_ic_1d | Rank IC (1d) | `pipeline/signal_metrics.py` | `SignalMetricsPanel.jsx:18-79` | daily horizon | scored panel | — | Algorithm Diagnostics |
| rank_ic_5d | Rank IC (5d) | same | same | 5d horizon | scored panel | — | Algorithm Diagnostics |
| rank_ic_21d | Rank IC (21d) | same | same | 21d horizon | scored panel | — | Algorithm Diagnostics |
| rank_ic_63d | Rank IC (63d) | same | same | 63d horizon | scored panel | — | Algorithm Diagnostics |
| ic_ir | IC-IR (annualized) | same | same | weekly | scored panel | — | Algorithm Diagnostics |
| ic_decay | IC decay curve | same | same | monthly | scored panel | — | Algorithm Diagnostics |
| per_leg_ic | Per-leg IC | same | same | monthly | scored panel | — | Algorithm Diagnostics |
| drop_one_leg | Drop-one-leg delta IC | same | same | refit | scored panel | — | Robustness & Validation |
| leg_correlation | Leg correlation matrix | same | same | monthly | scored panel | — | Algorithm Diagnostics |
| quantile_spread | Quantile spread and monotonicity | same | same | monthly | scored panel | — | Algorithm Diagnostics |
| score_autocorrelation | Score autocorrelation | same | same | weekly | scored panel | — | Algorithm Diagnostics |
| factor_betas | FF5 + momentum loadings | `pipeline/signal_metrics.py:construction_metrics` | same | monthly | retrospective strategy | factor loadings above | Factor Attribution |
| effective_n | Effective N | same | same | monthly | strategy weights | effective_holdings | Exposure & Construction |
| top_10_weight | Top-10 weight | same | same | monthly | strategy weights | — | Exposure & Construction |
| rolling_beta_60d | Rolling 60-day beta | same | same | weekly | strategy vs SPY | — | Benchmark Fit |
| net_exposure_drift | Net exposure drift | same | same | daily | strategy weights | — | Exposure & Construction |
| sector_active_weights | Sector active weights | same | same | weekly | strategy vs benchmark weights | — | Exposure & Construction |
| breakeven_gross_alpha | Breakeven gross alpha | `pipeline/signal_metrics.py:cost_metrics` | same | monthly | retrospective turnover/cost | — | Cost & Capacity |
| alpha_cost_crossover | Alpha versus cost crossover | same | same | monthly | trade/cost data | — | Cost & Capacity |
| percent_of_adv | Position as a share of ADV | same | same | daily | position and liquidity data | — | Cost & Capacity |
| implementation_shortfall | Implementation shortfall | same | same | daily | live fills | — | Cost & Capacity |
| fill_rate | Fill rate | same | same | daily | live orders/fills | — | Cost & Capacity |
| unpositioned_signals | Signals never positioned | same | same | daily | live signals/orders | — | Algorithm Diagnostics |
| deflated_sharpe | Deflated Sharpe ratio | `pipeline/signal_metrics.py:honesty_metrics` | same | quarterly | registered trials/backtest | backtest_dsr | Statistical Confidence |
| probabilistic_sharpe | Probabilistic Sharpe ratio | same | same | quarterly | retrospective strategy returns | — | Statistical Confidence |
| min_track_record_length | Minimum track record length | same | same | quarterly | retrospective strategy returns | — | Statistical Confidence |
| pbo | Probability of backtest overfitting | same | same | annual/refit | optimizer trial matrix | — | Robustness & Validation |
| omega | Omega ratio | `pipeline/signal_metrics.py:701-739` | same | daily live | live strategy returns | — | Tail Risk |
| ulcer_index | Ulcer index | same | same | daily live | live strategy returns | — | Tail Risk |
| martin_ratio | Martin ratio | same | same | daily live | live strategy returns | — | Tail Risk |
| cvar_95 | CVaR-95 | same | same | daily live | live strategy returns | expected_shortfall_95 | Tail Risk |
| skew | Skew | same | same | daily live | live strategy returns | — | Tail Risk |
| excess_kurtosis | Excess kurtosis | same | same | daily live | live strategy returns | — | Tail Risk |
| tail_ratio | Tail ratio | same | same | daily live | live strategy returns | — | Tail Risk |
| gain_to_pain | Gain to pain | same | same | daily live | live strategy returns | — | Tail Risk |
| live_vs_backtest_ic | Rolling 60-day live IC vs backtest | `pipeline/signal_metrics.py:monitoring_metrics` | same | weekly | live and backtest panels | — | Robustness & Validation |
| feature_psi | Feature distribution PSI | same | same | monthly | live vs baseline features | — | Robustness & Validation |
| live_vs_backtest_divergence | Live vs backtest return divergence | same | same | daily | live and simulated returns | — | Robustness & Validation |
| data_quality_counters | Data quality counters | same | same | daily | refresh/reconciliation | — | Algorithm Diagnostics |
| position_reconciliation | Position reconciliation | same | same | daily | intended vs held positions | — | Algorithm Diagnostics |

## Preservation baseline

- Pre-existing canonical metric IDs in this file: **130**.
- Dynamic strategy rows repeat those canonical metrics and do not create new definitions.
- The Phase 7 preservation check must show every ID above reachable in Overview, All Metrics, Algorithm, Historical, Diversification, Backtest Comparison, Shadow Portfolios, or Live Validation. Consolidating duplicate renders is permitted; deleting a canonical measurement is not.
