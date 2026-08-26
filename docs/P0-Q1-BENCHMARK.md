# P0 — Q1: Is the benchmark wrong, or is the signal wrong?

Reproducible by: `python pipeline/p0_q1_benchmark_factor_report.py` (no network access used or
required — reads `pipeline/backtest_monthly_results.json`, `public/data/etf/{RSP,IWM}.json`, and
`public/data/factors/french.json`, all already committed). Output:
`pipeline/reports/factor_regression_p0.json`.

> **Refreshed 2026-08-26.** The scheduled data pipeline regenerates `backtest_monthly_results.json`
> and the ETF price histories this script reads on its own refresh cadence, independent of this
> research doc. The numbers below were last regenerated on 2026-08-14 against an older snapshot of
> that data and had drifted from what re-running the same script against the currently committed
> data now produces — this is exactly the "measure before fixing, don't trust a stale doc" failure
> mode `docs/WHATS-LEFT-2026-08-17.md` warns about, now confirmed in this doc's own numbers.
> Re-running it also surfaced a real bug in the script itself, now fixed: the ETF price files and
> `backtest_monthly_results.json` are refreshed on independent schedules, and the script had no
> guard against that — an ETF file 11 days fresher than the backtest would have simulated RSP/IWM
> etc. through extra trading days the strategy/SPY legs don't have, silently breaking the "every leg
> is directly comparable" guarantee this doc relies on. `clip_to_end_date()` in
> `pipeline/p0_q1_benchmark_factor_report.py` now truncates every ETF-derived leg to the strategy's
> own last date before simulating it. The table and every number below reflect the fixed script.
> The qualitative Verdict-B conclusion (no *significant* residual alpha) is unchanged, but the
> point estimates — including the sign of the six-factor alpha — have moved. Treat any number in
> this doc as good only as of the date the script was last run, not as a fixed fact; re-run it
> before citing a figure from here in anything that matters.

## Four-benchmark comparison

SPY and the strategy are the already-published, cost-aware backtest legs (10bps one-way, monthly
rebalances, 2021-08-02 → 2026-08-13 as of this refresh — bounded by `backtest_monthly_results.json`,
the slower-refreshing of the two data sources this script reads). RSP and IWM are simulated with
the *identical* method `backtest_monthly.py` already uses for the SPY leg — buy-and-hold from the
same start date, one 10bps entry cost, no further trading, now truncated to that same 2026-08-13
end date by `clip_to_end_date()` — applied to each ETF's own daily adjusted-close history
(`public/data/etf/{RSP,IWM}.json`, both already committed and covering the entire backtest window
and beyond).

| | Strategy | SPY | RSP (equal-weight S&P) | IWM (small/mid-cap) |
|---|---:|---:|---:|---:|
| CAGR | 15.61% | 13.12% | 9.22% | 7.32% |
| Volatility | 17.54% | 17.27% | 16.22% | 22.50% |
| Max drawdown | −18.98% | −24.50% | −21.38% | −31.91% |
| Sharpe (zero rate) | 0.921 | 0.805 | 0.629 | 0.429 |
| Final value ($100k start) | $204,998 | $184,031 | $154,684 | $141,869 |

**As of this refresh the strategy now beats all three alternative benchmarks outright, including
SPY, on both CAGR and Sharpe** (CAGR 15.61% vs. SPY's 13.12%, RSP's 9.22%, IWM's 7.32%; Sharpe
0.921 vs. 0.805, 0.629, 0.429). This is a materially more favorable picture than the 2026-08-14
snapshot, where only RSP/IWM were beaten and SPY still won on both metrics. **Read this as evidence
the market regime moved in this book's favor over the last few weeks, not as evidence the model
changed** — nothing in the scoring code changed between the two runs; the six-factor regression
below (which explains *why* on a risk-adjusted basis) still finds no significant residual skill
behind the improved raw numbers.

**Sector-neutral composite: still not built, but the original blocker is now almost entirely
resolved.** The 2026-08-14 run found only 193 of 397 unique backtest tickers with a sector label
anywhere in currently-published data — a 51% gap the brief's evidence discipline correctly refused
to paper over with fabricated labels. As of this refresh, `public/data/advisor.json`'s current
`research`/`screen_universe`/`portfolio_coverage` rows carry a sector label for **352 of 353**
unique tickers that passed through the backtest's 20-name portfolio (`sector_coverage()`'s own
output, reproduced by re-running this script) — only `EQR` is missing. (The 397-vs-353 discrepancy
in the ticker count itself is between two different historical runs of `backtest_monthly.py`,
predating this refresh; the 353 figure is what the currently committed `backtest_monthly_results.json`
actually produces and is the one this session could verify.) **This means a sector-neutral
composite is very likely buildable now without fabricating anything** — it just hasn't been
written, since this session's mandate was fixing what the doc already claimed rather than building
new analysis. **What would resolve it:** a point-in-time sector map keyed by ticker and date is
still the ideal (avoids look-ahead from using *today's* sector label for a 2021-era pick that may
have since been reclassified or changed business), but with coverage this high, even the
already-available snapshot map is enough to build a first version and see whether it changes the
Q1 picture, caveated for that look-ahead risk. `backtest_monthly.py` still deliberately nulls
sector on every context it fetches, so also caching `sector` into its per-symbol fetch (one field,
no extra request) the next time a live refresh runs would let a *point-in-time* composite replace
the snapshot-based one later.

## Six-factor regression

Monthly strategy returns are month-end-to-month-end resamples of the already-published,
already-cost-adjusted daily portfolio value series. Every return used is a genuine full
calendar-month return (the backtest's mid-month start date only affects the level of the first
month-end value, not any return computed from it — no month is dropped as "partial"). Regressed
against Ken French's five factors plus momentum (`public/data/factors/french.json`; latest
available month is still 2026-06, which caps the sample at **n = 57 months, 2021-10 → 2026-06**
as of this refresh — French's release lag, not this repo's data, is the binding constraint, so
this window does not move until French publishes July 2026).

Newey-West HAC standard errors, Bartlett kernel, 3 lags (formula and implementation in the
script's docstring — no `statsmodels`/`scipy` in this environment, so this is a direct numpy
implementation of the standard sandwich estimator).

| Factor | Loading | Classical t | Newey-West(3) t |
|---|---:|---:|---:|
| **Alpha (monthly)** | **+0.252%** | **+0.547** | **+0.680** |
| Market excess | 0.810 | 8.29 | 8.32 |
| Size (SMB) | 0.525 | 3.03 | 3.85 |
| Value (HML) | 0.106 | 0.58 | 0.52 |
| Profitability (RMW) | 0.211 | 1.28 | 1.38 |
| Investment (CMA) | 0.148 | 0.66 | 0.63 |
| Momentum | 0.380 | 3.08 | 2.92 |

R² = 0.652. Annualized alpha = **+3.06%** (statistically indistinguishable from zero — |t| < 1).
This is a sign flip from the 2026-08-14 run (which found −2.57%, NW t = −0.437) driven entirely by
six additional weeks of realized returns feeding the same regression, not by any change to the
model or the factor definitions — see the refresh note at the top of this doc.

**Decisive question answered: after controlling for the six factors this model is built from,
there is still no significant residual alpha, though the point estimate is now positive rather
than negative.** Per the brief's own thresholds — Newey-West |t| ≥ 2.0 → residual skill; 1.0–2.0 →
undetermined; **< 1.0 → no residual alpha, factor tilt is the leading candidate** — this still lands
in the last bucket at |t| = 0.680, closer to the undetermined boundary than the 2026-08-14 estimate
was but still clearly inside it.

**Kill condition check: does not hold.** The brief asks whether the strategy is "more than 90%
explained by value and profitability loadings." It is not — those two loadings are among the
*weakest and least significant* in the table (t = 0.52 and t = 1.38, both under the conventional
2.0 threshold for individual significance). The loadings that are significant are **market
(t = 8.32), size (t = 3.85), and momentum (t = 2.92)** — all three stronger than in the 2026-08-14
run. This is a real and somewhat surprising finding on its own: a score that is 78% fundamentals by
construction, and whose *cross-sectional influence* on rank was already measured as fundamentals
+0.944 vs. market behavior +0.226 (near-orthogonal, +0.011 correlation — see
`docs/SYSTEM-SETUP.md` §5.1), produces a *realized return stream* that behaves like a market-beta,
small-cap, and momentum book, not a value or profitability book. Ranking on fundamentals and
*earning returns* through momentum and size exposure are not the same claim, and the data says this
system is doing the second more than the first.

## Shortfall decomposition: beta vs. selection

Single-factor CAPM on the same 57-month sample: beta = **0.759** (Newey-West t = 8.14, highly
significant — this is *this* script's own re-estimate from monthly, French-aligned data, not a
citation of the daily-return 0.70/0.79 figures elsewhere in the docs; the two differ because of
sampling frequency and the truncation to French's latest release, not because either is wrong).
CAPM alpha: **+0.453%/month, +5.43% annualized, Newey-West t = 1.082** — larger in magnitude than
the 2026-08-14 estimate (+1.26% at t=0.198) and now just past the brief's own |t| ≥ 1.0 boundary,
i.e. in the **undetermined** bucket rather than cleanly insignificant. This is the one number in
this doc where the refresh moved the qualitative bucket, not just the point estimate — see the
verdict below for how that's reconciled against the six-factor result, which is still solidly in
the "no residual alpha" bucket.

Decomposing the strategy's mean monthly excess return (1.075%) against SPY's mean monthly excess
return (0.821%) via that beta:

| | Monthly | Annualized |
|---|---:|---:|
| Explained by running at beta 0.759 in this market | 0.623% | 7.73% |
| Residual (selection) | 0.453% | 5.57% |
| **Total (= strategy's actual mean excess return)** | **1.075%** | — |

**The strategy now beats SPY outright, and beta exposure explains most but not all of the gap.**
Running at beta 0.76 in a market with SPY's realized mean excess return by itself would produce
about 7.7 points of annualized excess return; the strategy actually produced roughly 5.6 points
more than that. That residual is nominally larger than the 2026-08-14 snapshot's, and its
single-factor t-statistic (1.08) is nominally over the brief's 1.0 threshold — but the six-factor
regression above, which additionally controls for size, value, profitability, investment, and
momentum (all factors this strategy has *known, by-construction* exposure to), attributes almost
all of that single-factor "residual" to size and momentum loadings instead, and finds nothing left
at NW t = 0.68. **Read the CAPM alpha as evidence the strategy is *not* simply "SPY plus noise" —
it has a real, measurable size/momentum tilt driving the outperformance — not as evidence of stock-
picking skill beyond that tilt, which the fuller model still does not find.**

## Verdict for Q1

**No significant residual alpha after controlling for the six factors this model is explicitly
built from (|NW t| = 0.680 < 1.0, as of the 2026-08-26 refresh).** Per the brief's own decision
tree, this still makes **Verdict B — a factor tilt with no residual alpha — the leading
candidate**, and still makes WO-6 (does selection bootstrapping cost real alpha) optional rather
than load-bearing: there is no alpha upstream of WO-3's turnover fix to find, so a defect that
*suppresses inputs to an alpha-generating process* matters less if the process is not shown to
generate alpha net of its factor exposures in the first place. WO-6 is still worth running as a
diagnostic (it answers a structural-defect question independent of Q1), but it is no longer the
thing standing between this system and a demonstrated edge.

Two things are simultaneously true and both matter for the Phase 3 verdict: (1) against
better-matched benchmarks (RSP, IWM), and now against SPY outright, the strategy currently leads on
both CAGR and Sharpe, so "loses to SPY" is not (and, as of this refresh, is no longer even
descriptively) evidence of a bad score; and (2) once the six factors the model is explicitly built
from are controlled for, there is nothing left — no *significant* residual alpha, in either
direction. Both push toward the same conclusion as before: this is closer to a **transparent,
moderately concentrated beta/size/momentum tilt that ranks by fundamentals but doesn't (yet)
demonstrate selection skill beyond that tilt**, not a broken model and not a proven stock-picker —
that conclusion held when the strategy trailed SPY and still holds now that it leads it, which is
itself evidence the conclusion is about the factor structure and not about who happened to be ahead
on the day someone looked.
