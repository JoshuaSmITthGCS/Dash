# Research Prompt — How to make this algorithm actually work

A self-contained brief for a research agent, model, or collaborator. Everything needed to start is
below; the two supporting documents are `docs/SYSTEM-SETUP.md` (what the system is) and
`docs/ALGORITHM-RATING-2026-08-07.md` (what's been measured about it).

Copy everything from **§ THE PROMPT** onward if you're handing this to a model.

---

## Why this brief exists

The system is well-engineered and honestly documented, and its 5-year backtest loses to SPY on
return, volatility, drawdown, and Sharpe simultaneously. The interesting question is no longer
"is the code correct" — it mostly is. It's "is there an edge here at all, and if so what is
suppressing it."

This brief is written to prevent the two failure modes that would waste the effort: proposing more
factors without evidence, and re-deriving what has already been measured.

---

# THE PROMPT

## Your task

Determine whether the ValueSignal research score can be made to beat a size- and sector-matched
benchmark net of realistic costs, and if so, what specifically to change. Produce a prioritized,
falsifiable research plan — not a list of factors to add.

You are analyzing a real system with real constraints. Recommendations that require paid data,
persistent servers, or a research team are out of scope unless you flag them explicitly as such
and also give the free-tier version.

## The system in one paragraph

A Python batch pipeline scores a 910-name US equity universe with a 0–100 "research score" and
publishes the top 40 as a static JSON file consumed by a React dashboard. The score is
`0.78 · fundamentals + 0.18 · market_behavior + 0.04 · news_sentiment`, plus bounded modifiers
capped at ±15. Fundamentals decompose into valuation 28% / profitability 26% / financial health 15%
/ growth 11% / capital allocation 10% / accounting quality 10%. Every metric is mapped to 0–100
through discrete threshold bands. It runs on GitHub Actions three times a trading day on free-tier
data (Yahoo, Alpha Vantage 25 calls/day, Marketaux, FRED, SEC EDGAR). Full detail in
`docs/SYSTEM-SETUP.md`.

## What has already been measured — do not redo this

**The 5-year monthly backtest** (`pipeline/backtest_monthly_results.json`; 60 rebalances,
2021-08 → 2026-07, top 20 score-weighted, next-close execution, 10bps one-way, 860 usable names):

| | Strategy | SPY |
|---|---:|---:|
| CAGR | 11.14% | 12.80% |
| Volatility | 19.43% | 17.18% |
| Max drawdown | −27.03% | −24.50% |
| Sharpe (zero rate) | 0.644 | 0.791 |

Decomposed against SPY: beta **0.70**, correlation 0.62, annualized CAPM alpha **+2.99% at t = 0.44**,
residual volatility 15.2%, tracking error 16.1%, information ratio **−0.066**. Turnover **64.9% per
month**, 36% month-over-month name retention, 397 unique tickers through a 20-name portfolio.
The backtest self-discloses `survivorship_bias: true` and `filing_date_approximation: true`.

**The 52-week backtest** (`backtest_historical_results.json`): 13.89% vs SPY 8.42%, but on a
120-name universe, and IWM returned 14.78% in the same file. Its edge over SPY is a size tilt.

**Realized factor influence** (tie-aware Spearman vs. final score, 374-name screen universe, one
refresh): fundamentals +0.944, market behavior +0.226, news +0.078. Within fundamentals: valuation
+0.440, profitability +0.398, financial health +0.359, accounting quality +0.355, capital
allocation +0.240, growth +0.221. Fundamentals vs. market behavior: **+0.011** (orthogonal).

**Prospective validation**: none exists. The IC harness requires 24 eligible periods and has
observed 0. The point-in-time store is 2 days deep. No model promotion has ever occurred.

## Known structural defects — take these as given

1. **Selection bootstrapping.** Financial-statement metrics — which carry most of the 78%
   fundamental weight (EV/EBITDA 27% of valuation, ROIC 26% of profitability, interest coverage
   30% of health, Piotroski 45% of accounting quality) — are only fetched for the top 150 of 910
   names. That top 150 is chosen by a *preliminary* score computed without those statements. The
   full model is only ever applied to candidates pre-filtered by a weaker model. Additionally, the
   shortlist is seeded with the previous refresh's top 20 and admits only 5 new challengers per
   refresh.
2. **Band quantization.** All metrics pass through discrete threshold bands (`scorer.py:90–157`).
   Leading hypothesis for the 65% monthly turnover. A continuous cross-sectional normalizer already
   exists as a shadow challenger (`scorer.py:296`).
3. **Coverage holes.** `capital_allocation` and `accounting_quality` — 20% of fundamental weight —
   are scored for 84 of 374 names. The weight is silently redistributed for the rest.
4. **Inert news component.** 373 of 374 names sit at neutral 50.0; 4% of the model does nothing.
5. **Dark insider layer.** `SEC_USER_AGENT` unset, so the Form 4 modifier scores 0 symbols.
6. **Manifest reports the wrong model.** `observability.py:30` builds
   `run_manifest.score_distribution` from the shadow v2 score, not the published champion.
7. **Validation gaps.** The harness targets raw forward return over calendar-day horizons, not the
   contract's 63-trading-day sector-residual target. Transaction costs in validation are a flat
   10bps; the tiered model in `costs.py` is built and tested but not wired in.

## The questions to answer

Ordered by how much the answer would change what to build. Answer them in this order and stop
early if an answer invalidates the ones below it.

### Q1 — Is the benchmark wrong, or is the signal wrong?

The strategy runs at beta 0.70 with a small/mid tilt. SPY may simply be the wrong yardstick, and
CAPM alpha of +2.99% (insignificant, but positive) hints the selection may be doing something the
raw return comparison hides.

- Re-run the monthly backtest against equal-weight, IWM/mid-cap, and a sector-neutralized benchmark.
- Decompose returns against a standard factor model (market, size, value, profitability, investment,
  momentum). Free factor data: Ken French's data library. Note the repo already has
  `pipeline/fetch_factors.py` and `pipeline/reports/factor_regression_sample.json`.
- **The decisive question: after controlling for the factors this model is explicitly built from,
  is there residual alpha, and is it significant?** A fundamentals-first model that turns out to be
  a slow value+quality tilt with no residual alpha is a *different problem* than one with real
  selection skill buried under bad portfolio construction.
- Quantify how much of the shortfall is beta 0.70 in a rising market versus genuinely worse
  selection. These call for different fixes.

### Q2 — What is actually driving 65% monthly turnover?

A 78%-fundamentals model reading quarterly-lagged inputs should have low turnover. It doesn't.

- Attribute month-over-month rank changes to (a) band crossings on unchanged underlying values,
  (b) genuine input changes, (c) metric availability flickering, (d) price-driven components.
  `pipeline/reports/stability.json` and `signal_diff.json` already log some of this.
- Re-run the backtest with `normalization_mode: "cross_sectional"` (the existing challenger). Does
  turnover fall? Does net-of-cost performance improve?
- Test explicit turnover control: rank buffering (hold until a name falls out of the top 2N),
  minimum holding periods, and score smoothing. Which recovers the most net return?
- **Falsifiable claim to test:** if band quantization is the cause, turnover should fall materially
  under cross-sectional normalization with no change to the underlying weights.

### Q3 — Does selection bootstrapping cost real alpha?

- Construct a test where all 910 names get full statement metrics (accept the runtime cost; this is
  a research run, not a production refresh) and compare rankings against the production
  shortlist-gated ranking.
- Measure: how many names in the unconstrained top 40 never entered the shortlist? What are their
  forward returns relative to the names that did?
- If the cost is material, design a two-stage selection that is *unbiased* with respect to the final
  model — e.g. stratified sampling across the universe, a cheap proxy for the expensive metrics, or
  rotating full coverage across refreshes so every name is enriched within N days.

### Q4 — Which components deserve their weight?

The weights are argued from published evidence, not fitted — deliberately, and that is defensible.
But no component has been validated on this universe.

- Compute standalone rank IC for each of the six fundamental categories and each market-behavior
  factor against forward returns, using the historical data already in the repo.
- Which components have IC indistinguishable from zero on this universe and horizon?
- Is 78/18/4 defensible, or is a different blend materially better out-of-sample after deflation?
- Specifically: growth (11%) and capital allocation (10%) show the weakest realized ranking
  influence. Are they earning their weight?
- **Constraint:** any reweighting must survive `pipeline/evaluation.py`'s deflated-Sharpe and PBO
  machinery. Do not propose weights fitted in-sample.

### Q5 — What is the right holding horizon and portfolio construction?

The model publishes a rank; the backtest turns it into a top-20 score-weighted monthly-rebalanced
portfolio. That construction was never validated.

- Test holding horizons: 1, 3, 6, 12 months. Fundamentals decay slowly; monthly rebalancing may be
  mismatched to the signal.
- Test position count (10/20/40/60) and weighting (equal, score, inverse-volatility, risk-parity).
  With 15.2% residual volatility and 397 names cycled through 20 slots, concentration is a live
  variable.
- Test sector and size constraints. The current portfolio is unconstrained, which may be the source
  of the beta-0.70 tilt.
- `docs/PORTFOLIO-CONSTRUCTION.md` specifies six methods; one is built.

### Q6 — What is the cheapest path to real prospective validation?

The IC harness needs 24 periods and has 0. At the current accumulation rate that is roughly two
years before the first statistic.

- Can point-in-time data be reconstructed well enough from what exists (SEC EDGAR full-text filings
  are free and dated) to bootstrap the harness rather than waiting?
- What is the minimum viable prospective test that produces a usable answer in months rather than
  years? Consider shorter horizons, more frequent periods, or larger cross-sections.
- Wire `costs.py` into `ic_harness.py`. What does 65%-monthly-turnover cost look like under the
  base and stress scenarios versus the flat 10bps currently assumed?

## Constraints your recommendations must respect

- **Free-tier data only** unless you explicitly flag a paid recommendation and give a free
  alternative alongside it. Current budget: Alpha Vantage 25 calls/day, Yahoo unofficial,
  Marketaux free, FRED free, SEC EDGAR free.
- **Ephemeral runners.** GitHub Actions, 90-minute timeout, no persistent compute. Anything that
  must accumulate has to be committed to the repo.
- **No look-ahead.** Yahoo serves restated statements only. Any backtest recommendation must state
  how it handles the absence of as-reported history.
- **Deflation is mandatory.** `pipeline/evaluation.py` implements deflated Sharpe and PBO for a
  reason. Any proposed improvement must be evaluated after adjusting for the number of
  configurations tried.
- **Retail single-operator context.** Recommendations requiring ongoing manual research, a data
  vendor relationship, or a team are out of scope.

## What a good answer looks like

For each recommendation:

1. **The claim**, stated so it can be falsified.
2. **The test** that would confirm or kill it, specific enough to implement — which file, which
   data, which statistic, which threshold.
3. **Expected effect size**, with reasoning. "Improves performance" is not an answer.
4. **Cost**: engineering hours, data requirements, runtime.
5. **What it would take to abandon it.**

Rank the full set by expected value per unit of effort. Be explicit about which recommendations are
*diagnostic* (they tell you something) versus *corrective* (they change performance) — the repo has
a habit of building excellent diagnostic machinery and never reaching the corrective step.

## What not to do

- **Do not propose new factors** without evidence they add incremental IC over what exists. The
  system already has more unbuilt specification (11 sleeves, 9 screen presets, 5 portfolio methods)
  than built implementation. More specification is not the bottleneck.
- **Do not recommend machine learning** as a general direction. With 910 names, 5 years, 2 days of
  point-in-time data, and no as-reported history, the sample cannot support it. If you believe a
  specific ML method clears that bar, argue the sample-size case explicitly.
- **Do not suggest fitting the weights to the backtest.** That backtest is survivorship-biased and
  five years long. Fitting to it is how this system would acquire a spurious edge it cannot keep.
- **Do not restate the limitations.** `docs/LIMITATIONS.md` already enumerates them accurately.
  Assume the reader knows.
- **Do not assume the answer is "add more data."** The most likely conclusions are that the
  benchmark is wrong, the portfolio construction is wrong, or there is no edge — all three are
  answerable with data already in the repo.

## A conclusion worth reaching

"There is no reliable edge in this score; the honest move is to reposition it as a research and
screening tool rather than a strategy, and stop measuring it against an index" is a legitimate and
valuable answer. The repository's documentation is already unusually honest; a research pass that
confirms the null result and says so cleanly is worth more than one that manufactures a
justification for continuing.

State plainly which of these you believe after doing the work:

- **A.** There is real alpha, suppressed by portfolio construction and turnover. → Fix construction.
- **B.** There is a factor tilt but no residual alpha. → Reposition as a cheap factor tilt, benchmark
  honestly, stop trying to beat SPY.
- **C.** There is no edge, and the score's value is as a screening and evidence-summary tool. →
  Say so, drop the return framing, keep the research dashboard.
- **D.** Undetermined — the data cannot answer it yet. → Specify exactly what would, and how long it
  takes.

---

## Repo entry points for whoever picks this up

| Question | Start here |
|---|---|
| Composite scoring | `pipeline/advisor_engine.py::build_research()` (line 818) |
| Band mechanics | `pipeline/scorer.py:90–157` |
| Cross-sectional challenger | `pipeline/scorer.py:296` `CrossSectionalNormalizer` |
| Weights | `pipeline/config/settings.json` → `ranking_weights`, `fundamentals`, `market_behavior`, `modifiers` |
| Pipeline orchestration | `pipeline/fetch_advisor.py::run()` (line 874) |
| Shortlist selection | `pipeline/fetch_advisor.py::select_enrichment_priority()` (line 820) |
| Backtests | `pipeline/backtest_monthly.py`, `pipeline/backtest_historical.py` |
| Promotion methodology | `pipeline/evaluation.py` |
| Prospective harness | `pipeline/validation/ic_harness.py` |
| Cost model | `pipeline/costs.py` |
| Factor data | `pipeline/fetch_factors.py`, `pipeline/reports/factor_regression_sample.json` |
| Churn diagnostics | `pipeline/reports/stability.json`, `signal_diff.json` |
| Contract vs. reality | `docs/RESEARCH-CONTRACT.md` §2, §3 |
