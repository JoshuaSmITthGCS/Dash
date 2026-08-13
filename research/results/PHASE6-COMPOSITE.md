# Phase 6 — The live composite, measured

**The question:** the brief asks whether the complicated model beats simple factor
combinations after costs, and to say so plainly if it does not.

Numbers: `phase6_composite.json`. Harness: `research/composite.py`. Baselines it is measured
against: `PHASE4-BASELINES.md`.

---

## The answer

**Ranking by the live composite and holding the best-scored decile earned a Sharpe of 0.86
against 0.99 for equal-weighting the whole universe.** The ladder is inverted, and it stays
inverted after adjusting for risk:

| composite decile | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---|---|---|---|---|---|---|---|---|---|
| return | 15.7% | 15.7% | 16.6% | 15.7% | 16.4% | 17.4% | 19.5% | 18.7% | 21.9% | 21.6% |
| volatility | 19.2% | 18.3% | 18.2% | 17.8% | 18.2% | 17.8% | 18.7% | 20.5% | 19.5% | 22.2% |
| **Sharpe** | **0.86** | 0.89 | 0.94 | 0.91 | 0.93 | 1.00 | 1.05 | 0.94 | **1.12** | 1.00 |

Return monotonicity −0.87; **Sharpe monotonicity −0.88**. The model's ninth decile — companies
it rates second-worst — was the best risk-adjusted bucket on the ladder.

This is measured on the real scorer. Point-in-time snapshots go into
`scorer._band_valuation_score`, so the band cutoffs, metric weights, category weights,
applicability suppressions and coverage multiplier are the live ones read from config at run
time. 819 companies scored per rebalance at a median data coverage of 0.70, over 164
rebalances.

---

## The de-risking hypothesis, and how far it goes

Before the risk data existed, the ladders looked inverted in return and there was an innocent
explanation: low-scoring companies are smaller, more levered and higher-beta, and a nine-year
bull market pays for exactly that. On that reading the model is *de-risking*, not mis-ranking,
and the benchmark is unfair to it. Per-decile volatility was added to settle it, and committed
before either answer was known.

**The hypothesis holds for one block and fails for the composite.**

| block | return mono | **Sharpe mono** | reading |
|---|---|---|---|
| profitability | −0.62 | **+0.03** | the inversion *was* risk. Flat once adjusted — no signal either way |
| accounting_quality | −0.04 | +0.08 | flat before and after |
| financial_health | −0.02 | +0.18 | mildly positive once adjusted |
| growth | +0.32 | **+0.70** | sorts, and sorts better risk-adjusted |
| capital_allocation | −0.66 | −0.64 | inverted, and risk does not explain it |
| valuation | −0.90 | **−0.87** | inverted, and risk does not explain it |
| **composite** | −0.87 | **−0.88** | inverted, and risk does not explain it |

Profitability is the case the hypothesis was built for: its return ladder runs 18.3% at the top
and 22.5% at the bottom, but the bottom decile carries 23.2% volatility against the top's
17.9%, and once that is counted the ladder is flat. That block does not mis-rank; it simply
does not rank.

The composite does not get the same defence. Its bottom decile's extra return is *not* bought
with proportionally more risk — D9 returns 21.9% at 19.5% volatility for a Sharpe of 1.12,
comfortably the best bucket, at a volatility barely above D1's 19.2%. The inversion survives
risk adjustment essentially unchanged, −0.87 to −0.88.

---

## Which block is responsible

| block | weight | top-decile Sharpe | vs. universe | top-20 Sharpe | max DD |
|---|---|---|---|---|---|
| **valuation** | **28%** | **0.74** | **−0.25** | 0.77 | −50.1% |
| profitability | 26% | 1.04 | +0.04 | 1.11 | −30.2% |
| financial_health | 15% | 1.10 | +0.11 | 1.10 | −30.4% |
| **growth** | **11%** | **1.13** | **+0.13** | 1.09 | −33.8% |
| capital_allocation | 10% | 0.97 | −0.02 | 0.77 | −39.4% |
| accounting_quality | 10% | 0.91 | −0.08 | 0.64 | −44.8% |

**The model puts its largest weight on its worst block and its smallest on its best.**
Valuation at 28% has a top-decile Sharpe of 0.74 — the only block meaningfully below the
universe — and its top decile is also its most volatile at 24.1%, so it bought lower returns
with higher risk. Growth at 11% is the only block whose ladder sorts cleanly, at +0.70 Sharpe
monotonicity.

That is consistent with Phase 4 measured independently: earnings yield scored −0.21 against the
universe there, the worst single factor of eight, and cheapness subtracted from every
combination it entered.

**Profitability is diluting its own best input.** ROIC standing alone scored +0.30 in Phase 4.
The block that weights it at 26% scores +0.04, because it is averaged with
gross-profits-to-assets (22%, measured at +0.12 and no ladder) and four others.

---

## The coverage multiplier is not the problem

An earlier one-year cut suggested the published score's `0.65 + 0.35 × coverage` multiplier was
destroying the ranking: `composite` sorted at +0.13 monotonicity against `composite_raw` at
+0.72. Over the full sample that does not hold — −0.87 against −0.89, and both top deciles at
Sharpe 0.86. The multiplier is close to neutral for ranking purposes. The eighteen-observation
result was noise, and is recorded here because it was reported as actionable before the full
sample contradicted it.

---

## What this does and does not establish

**Does:** over 2017–2026, on 819 point-in-time-scored US companies, the composite's ranking
did not identify better forward returns, before or after adjusting for risk, and its top decile
underperformed the equal-weighted universe on a risk-adjusted basis. The brief asks for this to
be said plainly, so: **the complicated model did not beat holding everything, let alone the
simple factor combinations in Phase 4, three of which did.**

**Does not:**

- **Survivorship.** Measured on companies that still have a price feed. Bias is upward and
  unquantified — `.github/workflows/measure-survivorship.yml` exists to bound it and has not
  been run.
- **One regime, and the wrong one for this model.** 2017–2026 contains the widest growth-over-
  value margin in decades. A composite weighting valuation at 28% is being measured in its most
  hostile available sample. This is not an excuse for the result; it is a limit on how far the
  result generalises.
- **Four inputs are missing.** `forward_pe`, `peg`, `earnings_surprise` and `altman_z` cannot be
  reconstructed point-in-time and are absent throughout, so median coverage is 0.70 rather than
  the higher figure the live pipeline achieves. `forward_pe` carries 15% of the valuation
  category, and valuation is the block that failed — a forward-looking multiple might behave
  differently from the trailing ones that stood in for it. Untested either way.
- **No multiple-testing correction** across the eight rankings compared here.

---

## What follows

1. **Do not retune weights on this sample.** Fitting valuation down and growth up on the one
   window available would be curve-fitting to a nine-year regime, and the brief prohibits it
   explicitly. Phase 5 measures the thirty-two inputs individually; that is the evidence to act
   on, not this ranking of six blocks.
2. **The acceptance test is ladder slope, not top-20 return.** The composite's top-20 returned
   19.2% against the universe's 18.0% and looked fine. Its deciles ran backwards the whole way.
   Concentrated-portfolio return would have passed this model.
3. **Run the survivorship measurement.** It bounds every number in this file and in Phase 4.
4. **The valuation block needs its inputs tested before it is reweighted or removed.** Phase 5
   reports each of the eight valuation metrics separately, and "cheapness does not work" and
   "these particular cutoffs do not work" have different remedies.
