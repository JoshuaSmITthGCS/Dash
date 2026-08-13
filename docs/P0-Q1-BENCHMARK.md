# P0 — Q1: Is the benchmark wrong, or is the signal wrong?

Reproducible by: `python pipeline/p0_q1_benchmark_factor_report.py` (no network access used or
required — reads `pipeline/backtest_monthly_results.json`, `public/data/etf/{RSP,IWM}.json`, and
`public/data/factors/french.json`, all already committed). Output:
`pipeline/reports/factor_regression_p0.json`.

## Four-benchmark comparison

SPY and the strategy are the already-published, cost-aware backtest legs (10bps one-way, 60
monthly rebalances, 2021-08-02 → 2026-07-31). RSP and IWM are simulated with the *identical*
method `backtest_monthly.py` already uses for the SPY leg — buy-and-hold from the same start date,
one 10bps entry cost, no further trading — applied to each ETF's own full daily adjusted-close
history (`public/data/etf/{RSP,IWM}.json`, both already committed and covering the entire backtest
window).

| | Strategy | SPY | RSP (equal-weight S&P) | IWM (small/mid-cap) |
|---|---:|---:|---:|---:|
| CAGR | 11.14% | 12.80% | 9.23% | 7.57% |
| Volatility | 19.43% | 17.18% | 16.15% | 22.47% |
| Max drawdown | −27.03% | −24.50% | −21.38% | −31.91% |
| Sharpe (zero rate) | 0.644 | 0.791 | 0.631 | 0.439 |
| Final value ($100k start) | $169,478 | $182,472 | $155,665 | $144,162 |

**The strategy beats both alternative benchmarks on CAGR** (11.14% vs. RSP's 9.23% and IWM's
7.57%) and beats IWM decisively on risk-adjusted return (Sharpe 0.644 vs. 0.439). It essentially
ties RSP on Sharpe (0.644 vs. 0.631). Only SPY — the largest-cap, most concentrated, and least
representative benchmark for a beta-0.79 (see below) small/mid-tilted book — beats the strategy
outright. **This confirms the first half of Q1's premise: SPY is a materially harder yardstick
than a size- or breadth-matched alternative, and the headline "loses to SPY" framing understates
how the strategy did against benchmarks that share its actual risk profile.**

**Sector-neutral composite: not built.** Only 193 of the 397 unique tickers that passed through
the backtest's 20-name portfolio have a sector label anywhere in currently-published data
(`public/data/advisor.json`'s `research`/`screen_universe`/`portfolio_coverage` rows are the only
place sector is recorded at all — `backtest_monthly.py` deliberately nulls sector on every context
it fetches, and the committed backtest artifact carries no sector field). Building a sector-weighted
composite would mean fabricating labels for the uncovered 51% of historical picks, which this
brief's evidence discipline rules out. **What would resolve it:** a point-in-time sector map keyed
by ticker and date (doesn't exist); the cheapest version is caching `sector` into
`backtest_monthly.py`'s per-symbol fetch (one field, no extra request) the next time a live refresh
runs with network access, so future re-runs of this script can build the composite.

## Six-factor regression

Monthly strategy returns are month-end-to-month-end resamples of the already-published,
already-cost-adjusted daily portfolio value series. Every return used is a genuine full
calendar-month return (the backtest's mid-month start date only affects the level of the first
month-end value, not any return computed from it — no month is dropped as "partial"). Regressed
against Ken French's five factors plus momentum (`public/data/factors/french.json`, cached
2026-08-05; latest available month is 2026-06, which caps the sample at **n = 58 months,
2021-09 → 2026-06** — one month short of the backtest's own 60, and short of its 60-month endpoint
by the two months French hadn't published yet plus the always-lost first-differenced month).

Newey-West HAC standard errors, Bartlett kernel, 3 lags (formula and implementation in the
script's docstring — no `statsmodels`/`scipy` in this environment, so this is a direct numpy
implementation of the standard sandwich estimator).

| Factor | Loading | Classical t | Newey-West(3) t |
|---|---:|---:|---:|
| **Alpha (monthly)** | **−0.217%** | **−0.400** | **−0.437** |
| Market excess | 0.859 | 7.48 | 6.50 |
| Size (SMB) | 0.455 | 2.21 | 2.06 |
| Value (HML) | 0.198 | 0.92 | 1.00 |
| Profitability (RMW) | 0.162 | 0.83 | 0.70 |
| Investment (CMA) | 0.083 | 0.31 | 0.31 |
| Momentum | 0.404 | 2.77 | 2.50 |

R² = 0.589. Annualized alpha = **−2.57%** (statistically indistinguishable from zero — |t| < 1).

**Decisive question answered: after controlling for the six factors this model is built from,
there is no significant residual alpha, and the point estimate is negative.** Per the brief's own
thresholds — Newey-West |t| ≥ 2.0 → residual skill; 1.0–2.0 → undetermined; **< 1.0 → no residual
alpha, factor tilt is the leading candidate** — this lands cleanly in the last bucket at
|t| = 0.437, not the ambiguous middle.

**Kill condition check: does not hold.** The brief asks whether the strategy is "more than 90%
explained by value and profitability loadings." It is not — those two loadings are the *weakest
and least significant* in the table (t = 1.00 and t = 0.70, both under the conventional 2.0
threshold for individual significance). The loadings that are significant are **market
(t = 6.50), size (t = 2.06), and momentum (t = 2.50)**. This is a real and somewhat surprising
finding on its own: a score that is 78% fundamentals by construction, and whose *cross-sectional
influence* on rank was already measured as fundamentals +0.944 vs. market behavior +0.226
(near-orthogonal, +0.011 correlation — see `docs/SYSTEM-SETUP.md` §5.1), produces a *realized
return stream* that behaves like a market-beta, small-cap, and momentum book, not a value or
profitability book. Ranking on fundamentals and *earning returns* through momentum and size
exposure are not the same claim, and the data says this system is doing the second more than the
first.

## Shortfall decomposition: beta vs. selection

Single-factor CAPM on the same 58-month sample: beta = **0.793** (Newey-West t = 6.44, highly
significant — this is *this* script's own re-estimate from monthly, French-aligned data, not a
citation of the daily-return 0.70 figure elsewhere in the docs; the two differ because of sampling
frequency and the two-month truncation to French's latest release, not because either is wrong).
CAPM alpha: **+0.104%/month, +1.26% annualized, Newey-West t = 0.198** — smaller in magnitude and
opposite in sign from the earlier-cited "+2.99% at t=0.44," but the same qualitative verdict:
statistically indistinguishable from zero either way.

Decomposing the strategy's mean monthly excess return (0.684%) against SPY's mean monthly excess
return (0.731%) via that beta:

| | Monthly | Annualized |
|---|---:|---:|
| Explained by running at beta 0.793 in this market | 0.579% | 7.18% |
| Residual (selection) | 0.104% | 1.26% |
| **Total (= strategy's actual mean excess return)** | **0.684%** | — |

**Nearly all of the gap between the strategy and SPY is arithmetic, not selection.** Being
underweight market beta (0.79 instead of 1.0) in a period where SPY's mean monthly excess return
was 0.73% costs about 0.15 points of monthly excess return by construction — that alone accounts
for the great majority of the shortfall. What's left over (selection, i.e. the residual after
beta) is *slightly positive*, not negative, and nowhere near significant. **The headline
"strategy loses to SPY" is real but is overwhelmingly a beta-and-benchmark artifact, not evidence
of bad stock-picking.**

## Verdict for Q1

**No significant residual alpha after controlling for the six factors this model is explicitly
built from (|NW t| = 0.437 < 1.0).** Per the brief's own decision tree, this makes **Verdict B —
a factor tilt with no residual alpha — the leading candidate**, and makes WO-6 (does selection
bootstrapping cost real alpha) optional rather than load-bearing: there is no alpha upstream of
WO-3's turnover fix to find, so a defect that *suppresses inputs to an alpha-generating process*
matters less if the process is not shown to generate alpha net of its factor exposures in the
first place. WO-6 is still worth running as a diagnostic (it answers a structural-defect question
independent of Q1), but it is no longer the thing standing between this system and a demonstrated
edge.

Two things are simultaneously true and both matter for the Phase 3 verdict: (1) against
better-matched benchmarks (RSP, IWM) the strategy is competitive or better, so "loses to SPY" is
not evidence of a bad score; and (2) once the six factors the model is explicitly built from are
controlled for, there is nothing left — no residual alpha, in either direction, distinguishable
from zero. Both push toward the same conclusion: this is closer to a **transparent, moderately
concentrated beta/size/momentum tilt that ranks by fundamentals but doesn't (yet) demonstrate
selection skill beyond that tilt**, not a broken model and not a proven stock-picker.
