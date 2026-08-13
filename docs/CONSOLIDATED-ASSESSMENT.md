# Consolidated Assessment — ValueSignal

Two independent assessments of the same system, reconciled.

**Source A — "ValueSignal Consolidated Algorithm Feedback."** A design-level review synthesizing a
long discussion plus comparisons against retail trading approaches. Rates architecture 9/10 and
empirical confidence ~6/10. Its core takeaway: *the system does not need more signals, it needs
evidence the existing signals are real.*

**Source B — `docs/ALGORITHM-RATING-2026-08-07.md`.** An evidence-level audit that ran the numbers
in the committed artifacts. Rates the system 5.0/10 overall. Its core finding: *the 5-year backtest
underperforms SPY on return, volatility, drawdown, and Sharpe simultaneously.*

The two agree on the diagnosis and disagree on the prognosis. This document reconciles them, audits
every recommendation against what the repository actually contains, and produces one sequenced plan.

Supporting detail: `docs/SYSTEM-SETUP.md` (what the system is), `docs/RESEARCH-PROMPT.md` (the open
research questions), `docs/LIMITATIONS.md` (the repo's own gap list).

---

## 1. Where the two assessments agree

These conclusions are independently reached and should be treated as settled:

1. **Validation, not signal count, is the bottleneck.** Source A §33: "ValueSignal does not
   primarily need more signals." Source B's research prompt opens with "do not propose new factors
   without evidence they add incremental IC." Same conclusion from opposite directions.
2. **Point-in-time integrity is the critical missing piece.** Source A §23.1; Source B's Q6. The PIT
   store is 2 days deep and the IC harness has 0 of 24 required periods.
3. **Transaction costs and capacity must enter validation.** Source A §19; Source B Q6. `costs.py`
   exists, is tested, and is not wired into the harness — the harness still assumes a flat 10bps.
4. **Selection and timing must stay separate.** Source A §4 and §13; the repo already enforces this
   and Source B credits it as the cleanest design choice present.
5. **Champion/challenger with predefined promotion gates.** Source A §17 and §25; already
   implemented in `docs/RESEARCH-CONTRACT.md` §4, with 5 shadow challengers and zero promotions.
6. **Baselines are mandatory.** Source A §17 lists equal-weight, simple value, simple quality,
   simple momentum, market, sector, random, previous champion. Source B's Q1 makes the same point
   more sharply: the current benchmark is wrong.
7. **Robustness beats peak backtest performance.** Source A §15; Source B's insistence on deflation
   before any promotion.
8. **Scores should eventually carry empirical meaning.** Source A §24's score-bucket outcome table
   is the correct end state. `confidence_detail.historical_calibration` is currently always `null`
   for exactly this reason.

On these eight points there is no tension. They are the plan.

---

## 2. Where the measured evidence updates Source A

Source A was written without access to the backtest artifacts. Four of its positions need revision.

### 2.1 "This does not mean there is evidence the system does not work"

Source A §1 states the absence of validation is not negative evidence. That was true when written.
It is no longer true. `pipeline/backtest_monthly_results.json` — 60 monthly rebalances,
2021-08 → 2026-07, top 20 score-weighted, next-close execution, 10bps one-way, 860 usable names:

| | Strategy | SPY |
|---|---:|---:|
| CAGR | 11.14% | 12.80% |
| Volatility | 19.43% | 17.18% |
| Max drawdown | −27.03% | −24.50% |
| Sharpe (zero rate) | 0.644 | 0.791 |

Decomposed: beta **0.70**, correlation 0.62, annualized CAPM alpha **+2.99% at t = 0.44**, residual
volatility 15.2%, tracking error 16.1%, information ratio **−0.066**.

This is weak *negative* evidence, not absent evidence — and it is weak in both directions. It is
survivorship-biased in the strategy's favour (`bias_disclosures.survivorship_bias: true`), five
years is short, and beta 0.70 in a strongly rising market explains part of the return shortfall
without implying bad selection. But "we have not tested it" is no longer the accurate position.
The accurate position is: **we have tested it once, against the wrong benchmark, and it lost.**

That changes the sequencing. Source A's plan is largely additive — build the capital-efficiency
sleeve, build the catalyst model, build the validation dashboard. The measured evidence argues for
a diagnostic phase first, because two of Source A's three highest-value additions are premised on
the core model having an edge worth extending.

### 2.2 Architecture 9/10 rates the design, not the implementation

Source A's 9/10 is defensible as a rating of intent. Applied to what runs, it is too generous, for
one reason Source A had no way to see:

**The metrics that carry most of the model's weight are only computed for names a weaker model
already ranked highly.** Statement-derived metrics — EV/EBITDA (27% of valuation), ROIC (26% of
profitability), interest coverage (30% of financial health), Piotroski F (45% of accounting
quality) — are fetched only for the top 150 of 910 names. That shortlist is chosen by a preliminary
score computed *without* those statements, and is seeded with the previous refresh's top 20,
admitting only 5 new challengers per refresh (`fetch_advisor.py:820`, `:988`).

A company with an unattractive trailing multiple but excellent returns on capital and a fortress
balance sheet cannot surface: it never enters the shortlist, so its best metrics are never computed,
so it never scores well. Measured consequence — `capital_allocation` and `accounting_quality` are
scored for **84 of 374** names in the published screen universe.

This is a structural defect, not a tuning issue, and it sits upstream of everything else. An honest
implementation-architecture rating is closer to **6.5/10**: excellent separation of concerns and
configuration discipline, undermined by a selection stage that biases the input to every downstream
layer.

### 2.3 Turnover is absent from Source A entirely

The backtest replaces **64.9% of the portfolio every month**, with 36% month-over-month name
retention and 397 unique tickers cycling through 20 slots.

A model that is 78% fundamentals, reading inputs that update quarterly and lag the fiscal period by
one to three months, cannot justify that. Something with a far shorter half-life is driving the
ranking. The leading hypothesis is band quantization (`scorer.py:90–157`): every metric maps to
0–100 through discrete thresholds, so a name near a band edge flips several points on a trivial
input change.

This matters for Source A's framework specifically. Source A §14 and §19 correctly emphasize
expectancy, profit factor, and cost-aware backtesting — but at 65% monthly turnover the cost
sensitivity of this strategy is not a reporting problem, it is a design problem. The fix is
upstream of the diagnostics.

### 2.4 The top recommendation is currently blocked

Source A §32 ranks the **Capital Efficiency upgrade** (ROIC−WACC, ROIC persistence, incremental
ROIC, FCF conversion, leverage quality) as the single highest-value addition. It is a genuinely good
idea, and it cannot be built as specified today:

- **ROIC persistence** needs a 5-year ROIC series. Yahoo serves restated statements only, and
  statements are fetched only for the 150-name shortlist. There is no multi-year ROIC series for
  most of the universe.
- **Incremental ROIC** (ΔNOPAT / ΔInvested Capital) needs two consecutive periods of both — same
  constraint, doubled.
- **ROIC−WACC** needs a WACC estimate, which needs a cost of equity. No free provider serves one;
  it must be assumed (CAPM with an assumed equity risk premium), and the assumption will dominate
  the spread for most names. A 13%-ROIC/8%-WACC versus 20%-ROIC/17%-WACC comparison is only as good
  as the WACC, and a hand-set equity risk premium is not evidence.

There is also a tension inside Source A worth naming: §33 says the system needs proof rather than
signals, and §32 then proposes a new five-component sleeve. Building it before the existing score is
validated adds surface area to an unvalidated model.

**This does not mean drop it.** It means the enabling work — fixing the shortlist gating so the full
universe gets statement coverage — is a prerequisite, and it is the same fix §2.2 calls for. That is
a useful convergence: one repair unblocks both.

---

## 3. Recommendation audit — what already exists

Source A proposes a substantial amount that is already built. Mapping every recommendation against
the repository:

### Already built (do not rebuild)

| Source A recommendation | Where it lives |
|---|---|
| §18 Rank IC, ICIR, quantile spread, monotonicity | `evaluation.py:81,122,145` |
| §18 Deflated Sharpe Ratio | `evaluation.py:189`, `validation_framework.py:188` |
| §18 Probability of Backtest Overfitting | `evaluation.py:214` (combinatorially-symmetric CV) |
| §18 Multiple-testing controls | `validation_framework.py:200` `append_multiple_testing_log` |
| §16 Walk-forward evaluation | `evaluation.py:271`, `validation_framework.py:58` |
| §16 Untouched final test | `validation_framework.py:125` `untouched_holdout` |
| §16 Prospective shadow testing | `shadow_portfolios.py`, 4 strategies, immutable snapshots |
| §15 Bootstrap stability | `validation_framework.py:218` `block_bootstrap_excess` |
| §17 Challenger promotion rule | `docs/RESEARCH-CONTRACT.md` §4; 5 shadow challengers |
| §25 Model registry | `run_manifest` — model version, config hash, code SHA, universe version per artifact |
| §26 Feature registry | `config/feature_registry.json` — **58 features**, 14 fields each including `economic_rationale`, `availability_lag`, `missingness_policy`, `direction`, `target_horizons`, `references`, `not_used_for` |
| §19 Spread, impact, ADV participation cap | `costs.py` — `half_spread + fees + volatility_scaled_impact`, 3 scenarios, 2% ADV cap |
| §20 Amihud-style liquidity classification | `costs.py::liquidity_tier()` |
| §3 Independent factor families | `sleeves/` interface; value, quality, growth built |
| §4 Selection/timing separation | Enforced; themes contribute exactly zero price momentum |
| §10 Event-class modeling | `news_intelligence.py` event-type classification |
| §21 "Reddit for hypotheses, not truth" | `technical_indicators.py` docstring declines the broader indicator set as likely data-snooping |

Source A's §25 and §26 are the clearest case: it proposes building a model registry and a feature
registry that already exist, the latter with 58 documented features. The gaps against Source A's
specified field list are narrower and worth closing: the feature registry lacks `winsorization`,
`sector_neutralization`, `oos_ic`, `stability`, and `retirement_status`.

### Partially built

| Recommendation | State |
|---|---|
| §16 Exact forecast targets | Specified as 63-trading-day sector-residual return; **implemented** as raw forward return over calendar-day horizons (`ic_harness.py`) |
| §19 Costs in backtests | Model built and tested; **not wired** into `ic_harness.py`, which uses flat 10bps |
| §16 Point-in-time data | `pit_store.py` is well-designed with a separate revision log and departed-name membership; **2 days deep** |
| §13 Layer 2 factor sleeves | 3 of 14 built (value, quality, growth) |
| §28 P1 factor sleeves | 7 of 16 screen presets wired, 9 specification-only |
| §12 Model confidence | `confidence.py` publishes 6 components; `historical_calibration` always null |

### Not built — this is where Source A adds real value

| Recommendation | Note |
|---|---|
| **§16 Purge / embargo** | No implementation anywhere. Real gap in the walk-forward machinery |
| **§18 Score calibration** | No Brier score, calibration curve, or score-bucket outcome table |
| **§24 Score interpretation system** | The single most valuable UX idea in Source A. Nothing computes it |
| **§14 Strategy diagnostics** | No expectancy, profit factor, R-multiple, payoff ratio, or losing-streak tracking anywhere in `pipeline/` or `src/` |
| **§15 Regime analysis** | `grouped_attribution()` accepts a regime group field; nothing computes regime buckets |
| **§27 Validation dashboard** | No UI surface for any of the above |
| **§19 Capacity analysis** | ADV cap exists; days-to-liquidate and turnover-adjusted alpha do not |
| **§8–12 Catalyst Continuation model** | Not built. Architecturally sound as a *separate* model |
| **§5–7 Capital efficiency / FCF quality / balance-sheet resilience sleeves** | Not built; blocked per §2.4 |

---

## 4. Reconciled rating

Source A and Source B rate different axes. Combined:

| Dimension | Rating | Basis |
|---|---:|---|
| Design intent & separation of concerns | **9.0** | Source A's assessment stands. Selection/timing separation, sleeve architecture, explainability, portfolio context |
| Architecture as implemented | **6.5** | Selection bootstrapping (§2.2) biases every downstream layer; manifest certifies the wrong model |
| Multi-factor structure | **8.0** | Genuinely independent families — fundamentals vs. market behavior correlate at **+0.011**. Stated weights are realized weights (fundamentals Spearman +0.944) |
| Fundamental framework | **7.0** | Sector-aware bands, Altman variants, applicability suppression. Capital-efficiency depth is the real gap Source A identifies |
| Validation architecture | **7.5** | Higher than either source alone credits — deflated Sharpe, PBO, walk-forward, holdout, bootstrap all exist |
| Validation *evidence* | **1.5** | 0 of 24 IC periods. 2 days of PIT data. 0 promotions. The machinery has never run |
| Empirical confidence in alpha | **3.0** | Down from Source A's 6/10. Alpha t = 0.44; underperforms SPY on all four metrics |
| Turnover & cost realism | **4.0** | 65% monthly turnover from a quarterly signal; costs not wired to the harness |
| Risk & portfolio analytics | **7.0** | Strong concepts; missing expectancy, profit factor, R-multiples, regime conditioning |
| Documentation honesty | **9.5** | States its own weaknesses more accurately than most institutional model documentation |
| **Overall** | **5.5** | Weighted toward evidence of edge, because that is what a trading algorithm is for |

The half-point above Source B's standalone 5.0 reflects validation machinery Source B under-weighted:
deflated Sharpe, PBO, walk-forward splits, and untouched-holdout support are all present and tested.
The system is closer to producing real evidence than the raw "0 of 24 periods" figure suggests — it
is short of data, not short of method.

---

## 5. Reconciled priority plan

Source A's P0/P1/P2 is sound but assumes the core model has an edge worth extending. The measured
evidence argues for a diagnostic phase first. Revised sequence:

### P0 — Diagnose before building (weeks, no new data)

Everything here uses data already in the repo.

1. **Re-benchmark.** Re-run the monthly backtest against equal-weight, IWM/mid-cap, and a
   sector-neutral benchmark. Factor-decompose returns against market/size/value/profitability/
   investment/momentum using free Ken French data (`fetch_factors.py` exists). *Decisive question:
   after controlling for the factors this model is built from, is there residual alpha?*
   → This is Source A §17's "baselines are required," made specific.
2. **Attribute the turnover.** Split month-over-month rank changes into band crossings on unchanged
   values, genuine input changes, availability flicker, and price moves. `stability.json` and
   `signal_diff.json` already log part of this. Then re-run with the existing
   `cross_sectional_normalization` challenger and measure whether turnover falls.
3. **Measure the cost of shortlist gating.** Run one unconstrained research pass with statements
   for all 910 names. How many names in the unconstrained top 40 never entered the production
   shortlist, and what were their forward returns? This sizes the §2.2 defect and gates the
   capital-efficiency work.
4. **Fix `observability.py:30`** so the run manifest describes the champion, not the shadow.
5. **Set `SEC_USER_AGENT`.** One variable turns on the insider layer, which is currently scoring
   zero symbols.
6. **Wire `costs.py` into `ic_harness.py`.** Replace the flat 10bps. At 65% monthly turnover this
   is not cosmetic.

### P1 — Close the validation chain (Source A's P0, re-scoped)

7. **Implement the contract's forecast target**: 63-trading-day sector-residual return, trading-day
   horizons. This is the largest declared contract-vs-code gap.
8. **Add purge/embargo** to the walk-forward machinery. Genuine gap; Source A is right.
9. **Bootstrap point-in-time history** rather than waiting two years for the harness. SEC EDGAR
   full-text filings are free and carry real dates — enough to reconstruct as-reported fundamentals
   for a meaningful backtest window.
10. **Score calibration and the score-interpretation table** (Source A §24). Once the harness has
    periods, populate `confidence_detail.historical_calibration` and publish the bucket outcome
    table. This is the highest-value user-facing idea in Source A and it converts every score from
    an opinion into a statement about historical outcomes.
11. **Strategy diagnostics**: expectancy, profit factor, R-multiples, payoff ratio, losing streaks,
    regime-conditional performance. None exist today.

### P2 — Extend, once there is something worth extending

12. **Fix shortlist gating**, then build the **Capital Efficiency sleeve** (Source A §5) and **FCF
    Quality sleeve** (§6). Order matters: the sleeves are blocked on the fix.
13. **Balance-Sheet Resilience** (Source A §7) — cross-cycle leverage behavior rather than snapshot
    ratios.
14. **Validation dashboard** (Source A §27) — surface the above in the UI.
15. **Catalyst Continuation model** (Source A §8–12) as a genuinely separate tactical model with its
    own Watch/Confirmed/Extended/Failed states and its own validation. Source A's insistence that it
    must not blend into the Research Score is correct and should be treated as binding — Source A
    itself rates the blended version 4/10 against 8.5/10 standalone.
16. **Remaining sleeves and screen presets** (11 sleeves, 9 presets specification-only).

### Drop or defer

- **Microstructure** (OFI, Kyle's lambda, VPIN). Source A §20 and §29 already call this low priority
  for a multi-day horizon. Agreed — defer indefinitely.
- **More technical indicators.** Both sources agree. `technical_indicators.py` deliberately caps the
  family at four and documents why.
- **Rebuilding the model and feature registries.** They exist. Extend the feature registry with the
  five missing fields (`winsorization`, `sector_neutralization`, `oos_ic`, `stability`,
  `retirement_status`) instead.
- **The 4% news component**, unless real coverage is wired. 373 of 374 names sit at neutral; it is
  currently decorative.

---

## 6. The combined takeaway

Source A: *the system does not need more signals, it needs evidence the signals are real.*

Source B: *the one piece of evidence available says the signal loses to the index.*

Together those are not contradictory — they are a sequence. The system has been built for evidence
it has never generated, and the first time anyone generated any, the result was negative and
ambiguous: negative on the headline comparison, ambiguous because the benchmark is wrong, the
sample is survivorship-biased, and a structural defect upstream is suppressing the model's own
inputs.

Which means the honest next step is not to build the capital-efficiency sleeve or the catalyst
model. It is to spend a few weeks answering one question with data already on disk:

> **After controlling for the factors this model is explicitly built from, and after fixing the
> selection stage that starves it of its own best inputs, is there residual alpha?**

Four answers are possible, and all four are useful:

- **A.** Real alpha, suppressed by portfolio construction and turnover. → Fix construction, then
  extend along Source A's plan.
- **B.** A factor tilt with no residual alpha. → Reposition as a cheap, transparent factor tilt;
  benchmark honestly; stop trying to beat SPY.
- **C.** No edge; the score's value is as a screening and evidence-summary tool. → Say so, drop the
  return framing, keep the dashboard. Source A's §24 score-interpretation system is still worth
  building — it is what makes a screening tool credible.
- **D.** Undetermined until point-in-time history exists. → Bootstrap it from EDGAR; specify exactly
  what would resolve it and how long it takes.

Source A rates this system 9/10 on architecture and 6/10 on empirical confidence. That gap *is* the
project. The architecture was never the problem, and it is not the solution either.
