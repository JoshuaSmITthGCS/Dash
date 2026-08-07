# Algorithm Research Results

Every experiment run against the ValueSignal research score, including the ones that produced
nothing and the ones that could not run. Machine-readable counterpart:
`pipeline/reports/experiment_registry.json`.

**The question this set out to answer:** after fixing the structural defects and benchmarking
correctly, does the ranking contain useful information?

**The answer, stated up front:** on the evidence available, **Verdict B — a transparent
factor tilt with no demonstrated residual alpha**, with a genuine Verdict D caveat that the
properly-specified target has still never been measured. Details in §Verdict.

---

## Operating constraint

This session had **no network egress**. Yahoo Finance, SEC EDGAR, FRED and Alpha Vantage are
all unreachable, verified directly. That blocks every experiment needing new market data: the
backtest cannot re-run, the full-universe enrichment pass cannot execute, and the IC harness
cannot accumulate periods.

What it does not block is arithmetic on the 577MB of committed artifacts — 126 ETF daily
histories back to 2000, 756 months of Ken French factors, a 60-rebalance backtest with a
1,255-day value series, and three days of point-in-time snapshots. Roughly half the brief's
empirical questions turn out to be answerable from those without simulating anything.

Blocked experiments are recorded as blocked with reproduction commands. None are estimated.

---

## 1. The news component was inert

**Hypothesis.** The 4% news weight is neutral for essentially the whole universe, so it moves
score levels without ordering anything.

**Method.** Read the last published refresh. Recompute the champion blend from each row's
stored components, once with the neutral fill and once with news dropped from the denominator,
reusing `advisor_engine.blend_research_components` so the measurement cannot drift from
production.

**Result. Supported.** `weighted_sentiment` returned a hard `50.0` at coverage `0.0` whenever
no article cleared the entity/recency filters — **373 of 374** screen-universe names and
**39 of 40** published names. Because the blend renormalizes only over non-`None` components,
that 50.0 stayed *in* the denominator.

| | Value |
|---|---:|
| Mean score change once dropped | **+1.005** |
| Maximum | +1.40 |
| Published names changing rank position | 10 of 40 |

The correction is not a uniform uplift: names below 50 move *down*. What is removed is a pull
toward neutral in both directions. `screen_universe` is reported as skipped rather than
estimated — those rows do not publish the coverage blocks the confidence multiplier needs, so
their pre-change score cannot be reproduced and their delta would not be evidence.

**Decision: PROMOTE (shipped as a defect fix to the champion).**

---

## 2. Unavailable provider data was recorded as neutral evidence

**Hypothesis.** A dark provider's modifier is indistinguishable in the validation record from
one that was evaluated and found neutral.

**Result. Supported.** `modifiers.all_points` wrote a literal `0.0` for every modifier that did
not fire. Correct for an evaluated modifier; wrong for a dark SEC Form 4 layer, which was being
snapshotted as "reviewed insider activity, neutral" into an immutable record that later
validation would grade as real evidence.

**Decision: PROMOTE.** `snapshot_row` now takes the refresh's `source_status` and writes a
`modifiers.availability` map. Absent provider health defaults to unavailable; a modifier that
actually fired stays available regardless of the run-level flag.

---

## 3. Selection bootstrapping — measured, and smaller than it looks

**Hypothesis.** Shortlist gating materially changes which names can reach the top.

**Method.** `pipeline/enrichment_bias.py` against the most recent clean full-universe refresh.
The last *published* refresh is a fast one where 288 of 290 unenriched rows are simply names
that were not re-polled; the script refuses any payload more than 5% carry-forwards rather than
reporting that confound.

**Result. Inconclusive, with one settled half.**

| Rank band | Statement-enriched |
|---|---:|
| Top 10 / 20 / 40 / 100 | **100%** |
| Whole sample | 150 / 378 (39.7%) |

**No unenriched name reaches the top 100** — zero of 228. `capital_allocation` and
`accounting_quality` are 20% of the fundamental weight and cannot contribute for 60% of the
published universe.

The **+25.29** mean score gap is reported but explicitly *not* offered as the cost of the
defect. Enrichment targets names the preliminary model already liked, and those names already
lead by +11.8 to +19.8 on the categories that need no enrichment at all. Most of the gap is
circular selection, not suppression.

**Decision: RETAIN AS CHALLENGER.** `FULL_UNIVERSE_RESEARCH=true` is implemented and tested —
the suite asserts a populated and an empty `previous_top` produce byte-identical selections, so
the bias cannot leak in by construction. The decisive unseeded comparison needs network access.

---

## 4. Turnover is not driven by band quantization

**Hypothesis (the brief's leading one).** Discrete scoring bands flip names on trivial input
changes, so a continuous normalizer would cut turnover materially.

**Result. Rejected.** Measured across four live refresh transitions: band crossings on
effectively unchanged inputs were **0.42%** of score-change events; genuine input changes
**2.86%**; **metric availability flicker 96.72%**. The dominant driver is whether a
statement-derived value is present at all, not how it is bucketed.

This shifts the prior rather than settling it — the measurement is at the refresh-to-refresh
horizon, not the monthly one.

**Decision: ABANDON the band-quantization hypothesis.** Cross-sectional normalization remains a
shadow challenger on its own merits, not as a turnover fix.

---

## 5. Cost sensitivity at realized turnover

**Hypothesis.** A realistic cost model gives up more than 200bps a year relative to the
published flat 10bps.

**Method.** Cost drag is `turnover × rate`, and the backtest records its own realized turnover
per rebalance, so re-pricing it at every rate `costs.py` can produce is arithmetic on committed
data, not a simulation.

**Result. Rejected at the floor.**

| | Value |
|---|---:|
| Mean monthly turnover | 64.9% |
| Published 10bps drag | 78 bps/yr |
| Breakeven rate for +200bps | **35.7 bps one-way** |
| Worst rate the model produces without volatility | 25.0 bps (stress, illiquid) |
| Additional drag at that worst case | 116.9 bps/yr |

**The spread-and-fee floor does not cross the threshold.** But these rates omit the
volatility-scaled market-impact term for want of per-name volatility, so every figure is a
lower bound, and the full model could push an illiquid book past 36bps. Turnover this high is a
real cost problem — just not yet a demonstrated 200bps one.

**Decision: PENDING DATA.**

---

## 6. Benchmarks — could a user have just bought an ETF?

**Hypothesis.** The strategy delivers something a liquid style ETF could not.

**Method.** 13 committed style/size ETFs plus a fixed 50/50 IJH+IWD blend chosen in advance to
match the *measured* beta-0.79 / SMB-0.455 profile. Each priced exactly as `backtest_monthly.py`
prices its SPY leg, then a Newey-West regression of the strategy on each.

**Result. Rejected.**

| | CAGR | Vol | Sharpe | Max DD | NW t of alpha |
|---|---:|---:|---:|---:|---:|
| **ValueSignal** | 10.33% | 19.20% | 0.611 | −20.76% | — |
| SPY | 12.74% | 15.74% | 0.844 | −23.93% | 0.25 |
| **VTV** | **12.17%** | **13.90%** | **0.899** | **−15.34%** | −0.09 |
| IWD | 11.57% | 14.87% | 0.814 | −17.80% | 0.11 |
| IJH+IWD 50/50 | 10.05% | 16.19% | 0.674 | −19.69% | 0.42 |
| IWM | 7.04% | 20.63% | 0.433 | −26.75% | 1.04 |

Beaten on CAGR: 9 of 14. **Beaten with statistically significant alpha: zero.** Largest |t| is
1.11. VTV returns more, at lower volatility, with a shallower drawdown — better on every
dimension.

**Decision: ABANDON the "beats the market" framing.**

One bug caught before publishing: the first run read the alpha t-statistic under a key
`ols_newey_west` does not emit, and the `.get()` default published `0.00` for every benchmark —
which reads as a confident null. Now read directly, with a test asserting the key exists and a
constant-uplift fixture that must produce t > 2.

---

## 7. Strategy diagnostics — the shape of the returns

None of these existed anywhere in the repository before.

| | Value |
|---|---:|
| Win rate | 61.0% |
| Average win / loss | +4.29% / −4.21% |
| Payoff ratio | 1.019 |
| **Expectancy per month** | **+0.977%** |
| **Profit factor** | **1.594** |
| Longest losing streak | 3 months |
| Costs as share of gross return | 7.0% |

A "trade" here is one monthly rebalance period holding a 20-name book, not a position — the
artifact stores picks and the value path but not per-name fills. Per-position R-multiples are
listed as not measured rather than approximated.

---

## 8. Regime attribution — the most informative result

Regimes defined from benchmark and macro series only, fixed before any strategy performance was
inspected.

| Regime | n | Strategy | SPY | Excess |
|---|---:|---:|---:|---:|
| Bear | 11 | −13.9% | −24.2% | **+10.3pp** |
| Bull | 40 | +20.1% | +31.3% | −11.2pp |
| High volatility | 29 | −2.1% | +7.9% | −10.0pp |
| Low volatility | 28 | +24.0% | +17.0% | +7.0pp |
| Falling rates | 32 | +18.9% | +8.6% | **+10.3pp** |
| Rising rates | 26 | +0.6% | +17.5% | **−16.9pp** |

**Result. Rejected — the edge is not stable.** This is a duration-sensitive, defensive book. It
protects capital in drawdowns and in falling rates, and lags badly in rising rates and high
volatility. That is a coherent and useful description of what the strategy *is*; it is not an
alpha.

**Decision: RETAIN AS SHADOW.** Not actionable as a timing overlay without out-of-sample
evidence, and turning regimes into an optimization layer is exactly what the brief rules out.

---

## 9. Forecast target correction

**Result. Supported.** The contract specifies a 63-trading-day sector-residual return; the
harness measured raw returns over calendar-day horizons.

Why it went unnoticed: **the medians coincide.** 63 sessions spans 91 calendar days at the
median, 21 spans 30, 126 spans 182, 252 spans 365 — exactly the old constants. The error was in
the variance: a fixed 91-day window is 62 sessions in one part of the year and 64 in another,
so label length drifted.

Sector residualization changes the ranking outright — a test demonstrates the best raw
performer can be the worst residual performer, which is the whole point of residualizing.

**Decision: PROMOTE.** 3M / 63 sessions is preregistered as primary, with
`secondary_horizons_are_diagnostic_only` set so the best of four cannot be chosen after the
fact.

---

## 10. Purge and embargo

**Result. Supported (a real gap, now closed).** No implementation existed anywhere. The correct
purge is derived rather than guessed: a 63-session label observed monthly is still resolving two
periods later, so `label_overlap_periods(63, 21) == 2`.

Both controls act on the trailing edge of training because these splits are strictly expanding.
The post-test embargo band of combinatorial cross-validation has no analogue here — no path
exists by which post-test data reaches a training fold — and that is documented rather than
implemented as theatre.

---

## 11. Score calibration

**Result. Blocked, and published as blocked.** The harness has **0 of 24** periods and the PIT
store is three days deep, so every bucket reports `insufficient_data` with its shortfall named.

That is the deliverable. The machinery exists, the gate is explicit, and
`confidence_detail.historical_calibration` cannot quietly acquire a plausible number.
Fabricating calibration would convert an admitted unknown into a false claim.

One inconsistency caught in testing: publishability was gated on the adaptive quintiles while
`confidence.py` reads the fixed bands, and the two can disagree — 60 observations at a single
score measure the 80+ band fine while every equal-count quintile starves at 12. The consumer
would then have read a measured bucket out of a report flagged unpublishable. Now gated on the
bands actually consumed, with a test pinning that they cannot diverge.

---

## 12. Turnover controls

Four challengers implemented behind flags that all default to the champion's plain top-N
selection: rank buffer (1.25/1.5/2.0×N), minimum holding period (1/3/6 months with a
thesis-break release), score smoothing (α ∈ {0.5, 0.7}), replacement margin (2 or 5 points).

**Result. Blocked.** Each is proved to behave exactly as specified — 33 tests including exact
boundary conditions and the turnover-reduction property — which is the precondition for
trusting the measurement. Whether any improves net-of-cost return needs a backtest re-run.

---

## Trial accounting

**12 experiments, 47 variants tested.** `settings.json validation.shadow_strategy_trials` was
`5`, counting only the live shadow strategies — understating the search by nearly an order of
magnitude, which is the standard way a deflated Sharpe gets quietly re-inflated. The harness now
deflates against the registry total, and the published artifact records `trials_considered: 47`.

Promoted to champion: **3 defect fixes.** New signals promoted: **none.**

---

## Verdict

### B — primarily a known factor tilt, with a D-shaped caveat

**Why B.** Three independent lines of evidence agree, and none of them is the SPY comparison the
brief correctly identified as the wrong yardstick:

1. **Six-factor regression:** annualized alpha −2.57%, Newey-West |t| = 0.437. Inside the
   brief's own "no residual alpha" band, not the ambiguous middle.
2. **Fourteen tradeable benchmarks:** none beaten with significant alpha; largest |t| = 1.11.
   VTV dominates the strategy on return, volatility and drawdown simultaneously.
3. **Regime attribution:** the return pattern is a coherent duration-and-defensiveness profile,
   not a selection effect — strongly positive in falling rates and drawdowns, strongly negative
   in rising rates.

The significant factor loadings are **market (t = 6.50), size (t = 2.06) and momentum
(t = 2.50)** — not value or profitability, which is what the score is 78% built from. A model
that ranks on fundamentals and earns its returns through beta, size and momentum is doing the
second thing, whatever the first thing says.

**Why the D caveat is real and not hedging.** The properly-specified target has still never been
measured. Every number above comes from a five-year backtest that is survivorship-biased in the
strategy's favour, uses approximated filing timestamps, and measures raw returns rather than the
63-session sector-residual target the contract preregisters. The corrected harness has **0 of
24** periods. So B is the best-supported reading of the evidence that exists, not a settled
finding — and the specific evidence that would overturn it is named below.

**What this means in practice.** Reposition the score honestly as a transparent, moderately
concentrated quality/value tilt that is defensive in drawdowns and rate-sensitive. Stop
presenting SPY outperformance as the target. The screening, evidence-organization and
risk-analysis value of the platform is real and independent of whether the score has alpha.

**Do not** proceed to the Capital Efficiency or FCF Quality sleeves. The brief gates them on
validation being positive or plausibly positive, and it is neither. Adding a five-component
sleeve to an unvalidated model adds surface area, not evidence.

### What would change the verdict

| Evidence | Would move it to |
|---|---|
| 24 monthly PIT periods showing positive rank IC on the 63-session sector-residual target | A |
| Unseeded full-universe enrichment producing a materially different, better-performing top 40 | A (partly) |
| A turnover control lifting net-of-cost return by >150bps with the signal intact | A |
| More of the same: null residual alpha once PIT history exists | C |

### The three highest-expected-value next actions

1. **Run one full-universe unseeded refresh** (`FULL_UNIVERSE_RESEARCH=true`) from an
   environment with network access, then re-run `enrichment_bias.py`. This is the only
   outstanding structural question, the code is written and tested, and it is a single job.
2. **Set the `SEC_USER_AGENT` repository secret and reconstruct PIT history from EDGAR filing
   dates.** Everything downstream — component IC, calibration, ICIR, the entire verdict — is
   gated on periods accumulating, and waiting two years for them is a choice, not a constraint.
   EDGAR carries real filing timestamps and is free.
3. **Re-run the backtest under tiered costs and each turnover control**
   (`--cost-model tiered`, `--rank-buffer`, `--min-holding-months`). Three of the brief's
   open thresholds resolve in one batch of runs, and all the code exists.

Notably absent from that list: any new factor, sleeve, or indicator. The bottleneck has not
moved — it is still evidence, not signal count.
