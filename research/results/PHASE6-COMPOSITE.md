# Phase 6 — The live composite, measured

**The model's own ranking runs backwards over 2017–2026, and it is not a risk artefact.**

Numbers: `phase6_composite.json`. Harness: `research/composite.py`. This scores the *real*
model — point-in-time snapshots passed to `scorer._band_valuation_score`, so the bands,
category weights, metric weights, applicability suppressions and coverage multiplier are the
live ones read from `pipeline/config/settings.json` at run time.

---

## A hypothesis I offered and the data rejected

When the first ladders came back inverted, the bottom decile was the best bucket in seven of
eight rankings — including Phase 4 baselines sharing no code or inputs with the scorer. Eight
unrelated rankings inverting independently is implausible, so I proposed a single cause:
low-scoring companies are smaller, more levered and higher-beta, and a nine-year bull market
paid for risk. On that reading the model would be *de-risking*, not mis-ranking — an opposite
conclusion with an opposite remedy.

Per-decile volatility was added to test it, and committed before the answer was known. **The
test fails.** Decile volatility spans 18–24% across a ladder whose returns span 16–22%; the
risk differences are far too small to account for the return differences, and the Sharpe
ladders rise as the model's rating falls.

| composite | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---|---|---|---|---|---|---|---|---|---|
| return | 16% | 16% | 17% | 16% | 16% | 17% | 20% | 19% | 22% | 22% |
| volatility | 19% | 18% | 18% | 18% | 18% | 18% | 19% | 21% | 19% | 22% |
| **Sharpe** | **0.86** | 0.89 | 0.94 | 0.91 | 0.93 | 1.00 | 1.05 | 0.94 | **1.12** | 1.00 |

The best-rated decile has the worst risk-adjusted return on the ladder. De-risking is not what
is happening.

---

## The finding that matters

**The equal-weighted universe returned 18.0% at a Sharpe of 0.99. The composite's top decile
returned 15.7% at a Sharpe of 0.86.**

Buying the twenty percent the model likes most did worse, risk-adjusted, than buying
everything. Not dramatically worse — 0.13 of Sharpe — but consistently, over 153 monthly
rebalances, and in the wrong direction for a model whose entire purpose is to rank.

| block | weight | D1 return | D1 vol | D1 Sharpe | vs. universe | mono |
|---|---|---|---|---|---|---|
| growth | 11% | 23.2% | 20.5% | **1.13** | **+0.13** | **+0.32** |
| financial_health | 15% | 20.5% | 18.6% | 1.10 | +0.11 | −0.02 |
| profitability | 26% | 18.3% | 17.9% | 1.04 | +0.04 | −0.62 |
| capital_allocation | 10% | 17.7% | 18.7% | 0.97 | −0.02 | −0.66 |
| accounting_quality | 10% | 15.8% | 18.0% | 0.91 | −0.08 | −0.04 |
| **valuation** | **28%** | 16.0% | **24.1%** | **0.74** | **−0.25** | **−0.90** |
| composite | — | 15.7% | 19.2% | 0.86 | −0.13 | −0.87 |

Three things fall out, in order of how much they should change the model.

### 1. Valuation is the block doing the damage, and it carries the most weight

The 28% valuation block has the worst reading on every measure: monotonicity −0.90, the lowest
top-decile return, the highest top-decile volatility on the whole table at 24.1%, and a Sharpe
of 0.74 against the universe's 0.99.

That combination rules out the charitable reading. A block that took *less* risk for less
return would be de-risking. This one took **more** risk for less return. The cheapest decile by
the model's own valuation score was both more volatile and lower-returning than the market it
was drawn from — the signature of a value trap, not a value premium.

Phase 4 found the same thing independently: earnings yield sorted at −0.62, and its portfolio
carried a −59.5% drawdown against the universe's −32.2%.

### 2. Growth is the only block that ranks correctly, and it has the third-smallest weight

Growth is positive on every measure: monotonicity +0.32, Sharpe declining monotonically from
1.13 at the top to 0.91 at the bottom, and the best top-decile return of any block at 23.2%.
It is the only part of the model whose ordering does what ordering is for. It carries 11%.

Phase 4's independent finding rhymes: momentum was the one baseline that sorted, and growth is
fundamental momentum by another name.

### 3. Profitability, financial health and accounting quality are approximately inert

Their top deciles land within ±0.11 Sharpe of the universe. They are not harmful; they are
close to uninformative in this window. Together they carry 51% of the score. Note in
particular that profitability's monotonicity of −0.62 coexists with a top decile that is
*fine* — its ladder is U-shaped, so it is not ranking, but neither is it inverted at the top.

### And the coverage multiplier is not the culprit

`composite` (mono −0.87, Sharpe 0.86) and `composite_raw` (−0.89, 0.86) are indistinguishable.
An earlier one-year reading suggested the `0.65 + 0.35 × coverage` scalar was destroying the
ranking; over the full sample it does nothing of the kind. That earlier claim was made on 18
observations and was wrong.

---

## What this does not establish

- **Survivorship is still unmeasured and still the binding limitation.** The universe is
  companies that still have a price feed. `.github/workflows/measure-survivorship.yml` will
  size the gap; until it runs, the *levels* here mean little. The comparisons — top decile
  against the universe drawn from the same biased set — are what survive, which is why every
  claim above is a comparison.
- **One regime, and the worst possible one for this model.** 2017–2026 is the window in which
  value underperformed growth by the widest margin in decades. A model weighting valuation at
  28% is being judged in its most hostile available sample, and nine years is not enough to
  separate a factor from a regime.
- **Four inputs are absent.** `forward_pe`, `peg` and `earnings_surprise` need analyst
  estimates; `altman_z` needs retained earnings. They are passed absent and the live model's
  own renormalisation redistributes their weight, which is what it already does for a company
  with a silent provider. Median data coverage was 0.70. Forward P/E is 15% of the valuation
  block, so the block measured here leans harder on trailing multiples than the live one does.
- **No multiple-testing correction.** Phase 7.

So this is not "the model is broken". It is: **over the only window this pipeline can measure,
the composite's ranking is inverted, the inversion is concentrated in its heaviest block, and
it is not explained by risk.** That is a much narrower claim than the numbers might tempt, and
it is the one the evidence carries.

---

## What follows

1. **Do not retune weights on this result.** The brief forbids it and it would be wrong
   anyway: fitting weights to a single nine-year sample, in the regime most hostile to the
   thing being down-weighted, is how a backtest gets optimised into uselessness. What this
   licenses is Phase 5 — testing whether the *inputs* carry information — not reweighting.
2. **Valuation is where Phase 5 should start.** The block is 28% of the score and the only one
   that is actively harmful rather than merely uninformative. The question worth answering is
   whether it is the metrics, the band cutoffs, or cheapness itself.
3. **Growth deserves examination for the opposite reason.** It works, it is the smallest
   meaningful weight, and Phase 4's momentum result points the same way.
4. **The acceptance test is the ladder, not the portfolio.** The composite's top-20 beat the
   universe by 1.2 points while its deciles ran backwards. Concentrated-portfolio return would
   have reported this model as working.
