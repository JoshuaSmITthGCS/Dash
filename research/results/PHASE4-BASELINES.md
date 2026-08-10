# Phase 4 — Baselines

**What any model has to beat, measured before anything was optimised.**

Numbers: `phase4_baselines.json`. Harness: `research/baselines.py`. Regenerate per
`README.md` — no network, about twenty minutes.

---

## The headline

Over 2017–2026, on 820 US companies, an equal-weighted holding of the whole universe returned
**18.0% annualised at a Sharpe of 0.99**. That is the bar. Measured against it, risk-adjusted:

| factor | top-decile Sharpe | vs. universe | verdict |
|---|---|---|---|
| momentum_12_1 | 1.40 | +0.41 | sorts, strongly |
| quality_and_momentum | 1.39 | +0.40 | sorts, most reliably |
| quality_roic | 1.29 | +0.30 | sorts, once risk is counted |
| value_quality_momentum | 1.25 | +0.26 | sorts |
| profitability | 1.12 | +0.12 | does not sort |
| low_accruals | 1.10 | +0.11 | sorts weakly |
| value_and_momentum | 1.05 | +0.05 | barely |
| **value_earnings_yield** | **0.79** | **−0.21** | **actively harmful** |

**Momentum and quality sort the cross-section; cheapness sorts it backwards; gross
profitability does not sort it at all.** That is the answer to the question the brief asks in
GATE 4, and it arrives before any optimisation, which is the only point at which the answer is
trustworthy.

Everything below the top-twenty table depends on a distinction that raw returns cannot make.
A decile earning 25% with 26% volatility and a decile earning 24% with 18% volatility look
alike to a return-ranked ladder and are opposite results. Per-decile risk was added after the
first pass for exactly that reason, and it changed one of the conclusions.

---

## Setup

| | |
|---|---|
| Window | 2017-01-01 to 2026-06-01, 164 rebalances, 153 with a full holding period |
| Universe | median 820 members, reconstructed per date from prices and filing recency |
| Rebalance / hold | every 21 sessions, held 21 sessions |
| Portfolio | top 20 by factor, equally weighted |
| Costs | 10 bps per side, applied to every strategy except the universe benchmark |
| Fundamentals | point-in-time, filings accepted on or before each date |

Every input is reconstructed as of the rebalance date: fundamentals from filings accepted by
then, membership from prices and filing recency as they stood, market caps with share counts
carried onto the price series' split basis. Nothing is defaulted; a factor that cannot be
computed for a company leaves that company unranked.

---

## Top-twenty portfolios

| strategy | CAGR | vol | Sharpe | max DD | turnover | vs. universe |
|---|---|---|---|---|---|---|
| momentum_12_1 | 48.8% | 29.0% | 1.54 | −38.7% | 27% | **+30.8** |
| quality_and_momentum | 33.4% | 22.8% | 1.39 | −37.9% | 23% | +15.3 |
| low_accruals | 25.5% | 31.7% | 0.87 | −43.2% | 10% | +7.5 |
| quality_roic | 24.0% | 18.8% | 1.25 | −38.3% | 7% | +6.0 |
| value_quality_momentum | 21.5% | 21.3% | 1.03 | −32.2% | 25% | +3.5 |
| profitability | 18.2% | 19.6% | 0.96 | −43.9% | 6% | +0.2 |
| **equal_weight_universe** | **18.0%** | **18.5%** | **0.99** | **−32.2%** | — | — |
| value_earnings_yield | 17.9% | 26.0% | 0.77 | −59.5% | 15% | −0.1 |
| value_and_momentum | 17.4% | 22.5% | 0.83 | −42.8% | 31% | −0.6 |

Read alone, this table says momentum is extraordinary and value is worthless. Read alone, it
would also be wrong: twenty names is one variant, and the brief warns specifically against
declaring a winner from a lucky one.

---

## Decile ladders — the part that decides how much the table above is worth

Every rankable name sorted into ten buckets, best-first, annualised, no trading costs.
`mono` is the rank correlation between decile position and realised return: **+1** means the
factor sorts the cross-section perfectly, **0** means it does not sort at all, **−1** means it
sorts backwards.

| factor | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D1−D10 | mono |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| momentum_12_1 | 32% | 19% | 18% | 15% | 15% | 15% | 16% | 14% | 14% | 17% | +15.3 | **+0.61** |
| quality_and_momentum | 28% | 19% | 18% | 18% | 18% | 15% | 16% | 11% | 15% | 17% | +10.7 | **+0.81** |
| low_accruals | 28% | 21% | 16% | 17% | 17% | 14% | 14% | 14% | 17% | 21% | +6.9 | +0.48 |
| value_quality_momentum | 24% | 18% | 19% | 16% | 16% | 13% | 15% | 17% | 19% | 18% | +6.6 | +0.25 |
| value_and_momentum | 20% | 16% | 18% | 17% | 17% | 17% | 17% | 15% | 17% | 19% | +1.2 | +0.02 |
| profitability | 19% | 19% | 18% | 16% | 14% | 13% | 17% | 17% | 19% | 34% | −14.3 | +0.01 |
| quality_roic | 24% | 17% | 16% | 15% | 17% | 16% | 10% | 18% | 18% | 25% | −1.0 | −0.22 |
| value_earnings_yield | 17% | 12% | 13% | 17% | 16% | 15% | 14% | 18% | 24% | 27% | −9.4 | **−0.62** |

Four findings, in order of how much they should change the model.

### 1. Value ranked stocks backwards, and took more risk doing it

Earnings yield has a monotonicity of **−0.62**. The cheapest decile returned 17.4%; the most
expensive returned 26.8%. This is not noise around zero — it is a consistent inverse ladder,
and it is the single largest negative result here. The top-twenty portfolio also carried the
worst drawdown of anything measured, −59.5% against the universe's −32.2%.

Risk makes it worse rather than better. The cheapest decile carried **24.6% volatility**, the
highest of any top decile measured, for a Sharpe of 0.79 against the universe's 0.99. A factor
that bought lower returns with lower risk would be defensible; this one bought lower returns
with *higher* risk. That is a value trap, not a value premium.

Adding momentum to value did not rescue it. `value_and_momentum` returned 17.4%, below the
universe, with the highest turnover of any strategy at 31% a month.

**This matters to ValueSignal directly**, because the live model weights value heavily and
presents cheapness as a reason to buy. Over this window and this universe, cheapness was a
reason not to.

### 2. Quality works — but only once risk is accounted for. Gross profitability does not.

**This finding replaces an earlier version of itself, and the correction matters.** On raw
return, `quality_roic` looks like it does not sort: 24% in its best decile and 25% in its
*worst*, monotonicity −0.22. I reported it that way, and it was misleading.

The U-shape is not two ends doing the same thing. It is a good end and a *risky* end:

| quality_roic | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 |
|---|---|---|---|---|---|---|---|---|---|---|
| return | 24% | 17% | 16% | 15% | 17% | 16% | 10% | 18% | 18% | 25% |
| volatility | 17.9% | 17.4% | 17.4% | 18.9% | 17.9% | 18.6% | 17.7% | 16.7% | 19.6% | **27.7%** |
| **Sharpe** | **1.29** | 1.01 | 0.93 | 0.85 | 0.96 | 0.90 | 0.62 | 1.08 | 0.93 | 0.94 |

The bottom decile earns its 25% with 27.7% volatility — half again the rest of the ladder —
for a Sharpe of 0.94, below the universe's 0.99. The top decile earns 24% at 17.9% volatility,
*less* risk than the universe, for a Sharpe of **1.29**. That is the second-best single-factor
reading measured here and a clear +0.30 over the universe.

Return-only deciles cannot see this, and mine could not until per-decile risk was added.
High return at high risk and high return at low risk are opposite results, and a monotonicity
computed on returns scores them identically.

`profitability` (gross-profits-to-assets) does not survive the same test. Its Sharpe ladder is
1.12 at the top and 1.15 at the bottom — genuinely U-shaped in risk-adjusted terms too, and no
ordering at +0.01 monotonicity.

**The consequence for the live model is specific.** Its profitability block weights ROIC at 26%
and gross-profits-to-assets at 22%, alongside four more metrics. The one input that works is
diluted by five that do not, and the block as a whole scores +0.04 Sharpe against the
universe — against +0.30 for ROIC standing alone.

### 3. Momentum sorts cleanly, and its ladder is the best-behaved thing measured

Its Sharpe ladder runs **1.40, 1.10, 1.09, 0.93, 0.94, 0.92, 0.91, 0.78, 0.71, 0.66** — a
near-monotonic decline over ten buckets, which is what a factor that carries information looks
like. `quality_and_momentum` is nearly identical at 1.39 down to 0.67, with the highest
return-monotonicity on the table (+0.81).

On returns alone the picture looked more tail-concentrated than it is: monotonicity +0.61,
spread +15.3 points, but deciles 2 through 10 spanning only 14% to 19%. The Sharpe ladder
shows the ordering continues well past the first bucket even where returns flatten, because
the lower deciles are taking progressively more risk for it. Within D1 the effect does still
concentrate: the top twenty returned 48.8% against the decile's 32.3%.

**A tail-concentrated effect is exactly where survivorship bias lands.** Selecting on past
returns inside a set chosen for having survived is close to selecting on the survival itself,
so of everything measured here, momentum's number is the one most inflated by the bias below.
I do not report 48.8% as an expectation and no part of this engagement should.

### 4. The best-sorting construction is quality *and* momentum, and the two legs are not equals

`quality_and_momentum` has the highest monotonicity at **+0.81** and a Sharpe ladder running
1.39 down to 0.67 — the steadiest decline measured. Both of its legs sort on their own once
risk is counted (momentum +0.41 over the universe, ROIC +0.30), so this is two working signals
composing rather than two weak ones rescuing each other.

Adding value to the pair makes it *worse*, not better: `value_quality_momentum` drops to +0.26
and monotonicity +0.25, and `value_and_momentum` collapses to +0.05 and +0.02. Cheapness
subtracts from every combination it enters here. That is the clearest single statement this
table makes about the live model, which weights valuation at 28%.

On a nine-year sample with no multiple-testing correction, all of this is a hypothesis worth
testing in Phase 5 rather than a finding to act on.

---

## What these numbers cannot support

The benchmark is inflated and so is everything measured against it. **The equal-weighted
universe returned 18.0% while the S&P 500 returned roughly 13–14% over the same window.** Part
of that gap is an equal-weight small-cap tilt and part is survivorship, and this pipeline
cannot yet separate them.

- **Survivorship.** The candidate set is the companies that still have a price feed today.
  Everything that delisted, was acquired, or went to zero between 2016 and now is absent, and no
  rule evaluated on this data recovers it. Every return above is biased upward by an unquantified
  amount. `research/STATE.md` blocker B-3.
- **One regime.** 2017–2026 is roughly nine years, and it is the window in which growth and
  momentum beat value by the widest margin in decades. Value's inverse ladder is a fact about
  this window before it is a fact about value.
- **No multiple-testing correction.** Eight strategies were measured. Phase 7 is where that gets
  paid for, and the sample is short enough that it will not pay much.
- **Successor registrants.** Thirteen tickers reorganised under a new CIK, so their pre-reorganisation
  filings are unreachable. They sit out the fundamental factors and remain in momentum —
  a bias that favours momentum, in the same direction as everything else here.

So these results support statements about the **relative ordering** of simple strategies over
one period. They support no statement about the level of return any of them would earn, and
none is made.

---

## What this licenses for Phases 5–10

1. **The bar is 18.0% at a Sharpe of 0.99, not zero.** A model that beats cash is not
   interesting. Every later phase compares to the equal-weighted universe.
2. **Decile monotonicity is the acceptance test, not top-twenty return.** Three factors here
   beat the universe in a concentrated portfolio while failing to sort the cross-section at all.
   Any scoring layer that cannot show a ladder should not be carrying weight.
3. **Value's weighting in the live model needs evidence, and this is evidence against it.**
   Not proof that value fails — proof that over the only window this pipeline can measure, it
   ranked backwards. Phase 6 should test whether the live composite beats the universe at all
   before any question of tuning arises.
4. **Nothing here is optimised, and nothing here should be.** These are the numbers to beat.
   The brief's instruction is that a complicated model unable to beat simple combinations after
   costs should be reported as such, plainly. On this evidence four of the eight simple
   constructions cannot beat holding everything either — which raises the bar for the composite
   and lowers confidence in the components it is built from.
