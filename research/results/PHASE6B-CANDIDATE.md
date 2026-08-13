# Phase 6b — A candidate ranking, tested out-of-sample

**Yes: 43.5% a year against the live model's 15.1%, on data the candidate's design never saw.
Read the caveats before acting on that, because one of them is large.**

Numbers: `phase6b_candidate.json`. Harness: `research/candidate.py`.

---

## Method, stated before the result

The window was cut in half. Six candidates were measured on **2017-01 → 2021-07** (68
rebalances). A selection rule written into the module — highest Sharpe-decile monotonicity,
tie-broken by top-decile Sharpe — picked one winner from those numbers **in code**, before the
second half was read. The reported result is that candidate over **2021-07 → 2026-06** (85
rebalances).

The rule deliberately is not top-twenty return: Phase 4 found three factors that beat the
universe in a concentrated portfolio while failing to rank the cross-section at all, and a
concentrated return is the most overfittable number available. The live composite was measured
identically but barred from selection.

**Selected: `momentum_only`** — design-half Sharpe monotonicity +0.90, top-decile Sharpe 1.78.

---

## The out-of-sample result

| test half, 2021-07 → 2026-06 | CAGR | vol | Sharpe | max DD | turnover |
|---|---|---|---|---|---|
| **momentum_only** (selected) | **43.5%** | 29.8% | **1.38** | −38.7% | 26.0% |
| roic_and_momentum | 26.0% | 23.2% | 1.12 | −37.6% | 21.9% |
| roic_momentum_gross_profits | 21.9% | 20.9% | 1.06 | −34.2% | 16.0% |
| roic_momentum_accruals | 18.0% | 19.4% | 0.95 | −28.2% | 21.3% |
| roic_only | 16.8% | 18.5% | 0.94 | −38.3% | **5.8%** |
| **live_composite** | 15.1% | 20.6% | 0.79 | −34.3% | 17.0% |
| composite_without_valuation | 8.5% | 18.0% | 0.54 | −29.9% | 17.9% |
| equal_weight_universe | 9.8% | 17.0% | 0.64 | −28.3% | — |

It beat the live model on return **and** on Sharpe, which rules out the most common way a fake
win appears — clearing the bar by taking more risk. It did not clear it for free, though: the
drawdown is 4.4 points deeper than the live model's and 10.4 deeper than the universe's.

---

## The caveat that matters most

**Momentum is the factor most inflated by the one bias this pipeline has not fixed.**

The universe is the companies that still have a price feed today. Momentum ranks on past
returns. Selecting the twenty highest past returns *inside a set chosen for having survived* is
uncomfortably close to selecting on the survival itself — the names that went up and then
continued to exist. Every strategy here is biased upward by that; momentum is biased upward
most, and by construction rather than by accident.

I flagged this before running the test, not after seeing the answer, and nothing in the result
changes it. **43.5% is not a forward expectation.** The trustworthy content of this table is the
*ordering* of the candidates, not the level of any of them.

Two further limits: one test half of five years and one regime; and costs modelled as a flat
10bps per side, which ignores market impact — felt most by the highest-turnover candidate,
which is the winner at 26% a month.

Finally, momentum is the most documented anomaly in finance. Finding that it works is evidence
the measurement pipeline is sound, not a discovery.

---

## Two findings that cut against what I previously told you

### Removing valuation looked right and was wrong

Phase 5 found four independent valuation multiples all inverting, and I recommended acting on
it. The split sample is what caught the error:

| composite_without_valuation | design half | test half |
|---|---|---|
| Sharpe | **1.17** (live: 1.06) | **0.54** (live: 0.79) |
| Sharpe monotonicity | **+0.52** (live: −0.85) | **−0.30** (live: +0.04) |
| CAGR | 23.0% (live: 24.5%) | 8.5% (live: 15.1%) |

On the design half it looked like a clean fix: better Sharpe, and a ladder that sloped the
right way where the live model's sloped hard the wrong way. On the test half it was **worse
than the model it was fixing on every measure**, and worse than the universe on return.

Had I shipped the recommendation on Phase 5 evidence, I would have made your model worse. This
is the entire argument for the split, and it is why I will not act on the redundancy findings
without the same treatment.

### The live model's inversion is not stable

I reported a composite Sharpe monotonicity of −0.87 over the full window and described the
model as ranking stocks backwards. Split:

| live_composite | design half | test half |
|---|---|---|
| Sharpe monotonicity | −0.85 | **+0.04** |
| CAGR vs universe | 24.5% vs 29.1% (**−4.6**) | 15.1% vs 9.8% (**+5.3**) |

The inversion is concentrated in 2017–2021. Over 2021–2026 the ladder is flat, and the model's
top twenty **beat the universe by 5.3 points**. So the fair statement is narrower than the one I
made: the composite ranked backwards in the first half, ranks roughly randomly in the second,
and its concentrated portfolio has added value recently. Its deciles still do not sort — a flat
+0.04 means the score is not ordering the cross-section — but "ranks backwards" was a
full-window artifact of one half.

---

## What I would actually do

The pre-registered winner is `momentum_only`, and that is the honest answer to "beat 19.2%".
For a tool that also manages existing positions, it is probably not what you want to ship
alone: 26% monthly turnover, a −38.7% drawdown, and no fundamental basis for any holding.

`roic_and_momentum` returned 26.0% at Sharpe 1.12 with a Sharpe monotonicity of +0.92 — the
cleanest ladder in the test half — and rests on both factors that survived Phase 4
risk-adjusted. **Naming it here is post-hoc**, and its number therefore carries less weight than
the winner's; I mention it because the trade-off is real and yours to make, not because the
data selected it.

`roic_only` is worth noting for a different reason: 16.8% at Sharpe 0.94, beating the universe,
at **5.8% monthly turnover** — a third of the live model's and a fifth of momentum's. If
implementation cost matters, that is the efficient choice on this evidence.

**Before shipping any of this:** run `measure-survivorship.yml`. It bounds the bias that
inflates every number above and inflates the winner most.
