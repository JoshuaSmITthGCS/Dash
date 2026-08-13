# Phase 5 — Feature validation

**Which of the model's thirty-two inputs carry information, and which are the same opinion
counted twice.**

Numbers: `phase5_features.json`. Harness: `research/features.py`. 153 non-overlapping monthly
rebalances, 2017–2026, roughly 819 point-in-time-scored companies each.

Measured on the **scored** value, not the raw metric. The live model does not rank on
return-on-invested-capital; it ranks on the 0–100 band score it assigns to it. So the band
cutoffs are under test as much as the metrics, which is the point of auditing a model rather
than a literature.

---

## The headline

**None of the thirty-two metrics passes a significance bar that accounts for testing
thirty-two metrics.** The largest t-statistic on the table is +2.4 against a Bonferroni
threshold of 3.163. Three pass the naive bar of 1.96 — and testing thirty-two things at once
expects about 1.6 nominal passes from noise alone, so three is barely distinguishable from
chance.

But the first thing to say about that headline is what it does **not** mean, because the study
has a power limit and it sits right where the answer would be:

| | |
|---|---|
| median per-date IC dispersion | 0.108 |
| rebalances | 153 |
| **smallest IC this sample can detect** (nominal) | **0.017** |
| **smallest IC this sample can detect** (Bonferroni) | **0.028** |
| largest IC actually observed | 0.019 |

A genuine, useful equity factor typically has an information coefficient in the 0.02–0.05
range. **This sample cannot reliably detect the lower half of that band.** So "nothing is
significant" is partly a statement about nine years of data, not only about the metrics.
Anyone reading this as "all thirty-two inputs are proven worthless" is reading it wrong, and
anyone reading it as "the inputs are fine, the test is weak" is also reading it wrong — the
observed effects are small enough that even the best of them would be marginal with twice the
history.

What the sample *can* support are statements about **direction and coherence across related
metrics**, and there the picture is much clearer than any single t-statistic.

---

## Where the score's weight actually sits

| | share of total score |
|---|---|
| metrics with **positive** measured IC | 43.2% |
| metrics with **negative** measured IC | **44.2%** |
| metrics **not testable at all** point-in-time | **12.6%** |

Nearly half the model's weight is on inputs whose scored values pointed the wrong way over this
window, and an eighth is on inputs this exercise could not evaluate at all.

The five untested metrics are `forward_pe` (4.2% of the score), `altman_z` (2.7%), `peg`
(2.5%), `earnings_surprise` (1.8%) and `price_to_tangible_book` (1.4%). The first four need
analyst estimates or retained earnings, which the fundamentals store does not hold. The fifth
is different and worth noting on its own: `price_to_tangible_book` came back at **zero
coverage across every rebalance**, because the applicability registry suppresses it for every
profile outside a short list of sectors. It carries weight in the configuration and is scored
for almost nobody.

---

## The clearest signal in the table is not a single metric

Individually, no valuation metric is significant. Collectively they are unanimous:

| valuation metric | weight | IC | t | Sharpe monotonicity | hit rate |
|---|---|---|---|---|---|
| price_to_book | 1.4% | **−0.017** | −1.2 | **−0.83** | 0.44 |
| ev_to_ebitda | **7.6%** | **−0.014** | −1.1 | **−0.83** | 0.45 |
| ev_to_ebit | 3.4% | **−0.012** | −0.9 | **−0.72** | 0.46 |
| ev_to_fcf | 5.0% | **−0.011** | −1.0 | **−0.93** | 0.46 |
| sales_multiple | 2.5% | +0.008 | +0.6 | +0.22 | — |

Four of the five tested valuation inputs have negative ICs, hit rates below half, and Sharpe
decile ladders between −0.72 and −0.93 — near-perfect inversions. Four independent multiples
constructed from different numerators and denominators do not all invert by coincidence.

Read alongside Phase 4, where earnings yield scored −0.21 against the universe as a standalone
factor and subtracted from every combination it entered, and Phase 6, where the valuation block
was the only one meaningfully below the universe at a top-decile Sharpe of 0.74 — this is the
same finding arriving three times through three independent code paths. **Cheapness, as this
model measures it, ranked stocks backwards over 2017–2026.** That block carries 28% of the
score.

The same coherence argument works in reverse for the metrics that behaved well. The three
nominal passes — `gross_profits_to_assets` (+0.019, t=+2.0, Sharpe monotonicity **+0.82**),
`net_debt_to_ebitda` (+0.017, t=+2.4, **+0.67**) and `days_sales_outstanding_trend` (+0.018,
t=+2.2) — are not individually established, but the first two also have clean ladders, which a
lucky t-statistic does not usually come with.

---

## Redundancy: three pairs, and one of them crosses categories

Two metrics correlated at 0.85 that each carry 5% of the score are not two independent 5%
opinions. They are one opinion at 10%, and the configured weights are not the effective ones.
Phase 0 asserted this was happening. Here it is measured — average cross-sectional rank
correlation over 153 dates:

| pair | ρ | combined weight | same category? |
|---|---|---|---|
| `ev_to_fcf` ↔ `free_cash_flow_yield` | **+0.845** | **9.2%** | **no — valuation vs profitability** |
| `ev_to_ebit` ↔ `ev_to_ebitda` | +0.826 | 10.9% | yes (valuation) |
| `return_on_equity` ↔ `return_on_invested_capital` | +0.752 | 9.4% | yes (profitability) |

The first is the one that matters most, because it is invisible to anyone reading the
configuration. `ev_to_fcf` sits in valuation and `free_cash_flow_yield` sits in profitability;
the category structure presents them as two independent judgements about a company from two
different angles. At ρ = 0.845 they are one judgement about free cash flow, expressed twice,
carrying 9.2% of the score between them — more than any single metric except `ev_to_ebitda`.

The other two are within-category and so at least visible in principle, but they have the same
effect. `ev_to_ebit` and `ev_to_ebitda` differ only by depreciation and together carry 10.9%.
`return_on_equity` and `return_on_invested_capital` — where the configuration's own comment
says ROIC "is the one ROE should have been" — are 75% correlated and together carry 9.4%,
which means the metric the model prefers is being pulled back toward the one it says is
inferior.

**Effective concentration.** Of the 100 points of score weight, roughly 29 sit in three pairs
that each express approximately one opinion. The model has fewer independent views than its
thirty-two metrics suggest.

---

## The band cutoffs are a live suspect, and this is how to test them

`return_on_invested_capital` carries the largest single weight in the profitability block
(6.8% of the score). Its **scored** value here measures at IC +0.005, t = +0.5 — nothing.

But Phase 4 measured the **raw** metric and found its top decile achieved a Sharpe of 1.29
against the universe's 0.99, the second-best single-factor reading in that study.

Those are the same underlying quantity, measured on the same data, over the same window, with
one difference: Phase 5 passes it through the model's band cutoffs first. The scored version's
Sharpe monotonicity is +0.45 against a raw top-decile result that was clearly good.

That is a hypothesis, not a conclusion — the two studies also differ in universe construction
details and in decile-versus-IC framing. **The test is cheap and specific:** run this same
harness on raw metric values instead of scored ones and compare ICs metric by metric. Where the
raw IC materially exceeds the scored IC, the band configuration is destroying information that
the input actually had, and the remedy is recalibrating cutoffs rather than reweighting or
removing the metric. That distinction matters more than anything else in this file, because
"cheapness does not work" and "these particular cutoffs do not work" have completely different
fixes.

No metric had `dates_with_no_variation` above zero, so no band collapsed the cross-section
entirely. That was worth checking and is a clean result.

---

## Limitations

- **Survivorship.** Measured on companies that still have a price feed today. Unquantified;
  `.github/workflows/measure-survivorship.yml` bounds it and has not been run.
- **Statistical power.** Detectable at 0.028 IC after correction; observed effects top out at
  0.019. Absence of significance here is weak evidence of absence of signal.
- **One regime.** 2017–2026 contains the widest growth-over-value margin in decades. The
  valuation result is the finding most exposed to this, and it is also the finding most
  corroborated across independent measurements.
- **12.6% of the score is untested**, not tested-and-cleared.
- **Redundancy is measured after banding**, which is what the model adds up. Two metrics can be
  redundant after banding without being redundant before.

---

## What to do with this

1. **Do not reweight on these numbers.** Nothing passes correction, and fitting weights to a
   single nine-year regime is what the brief prohibits. The coherent directional findings
   justify *investigating*, not tuning.
2. **Run the raw-versus-scored comparison.** It is the cheapest high-value test available and
   it separates two remedies that look identical from the outside.
3. **Fix the cross-category redundancy first**, because it is a specification error rather than
   an empirical judgement. `ev_to_fcf` and `free_cash_flow_yield` at ρ = 0.845 in two different
   categories is a defect regardless of which way the factor points.
4. **Decide what `price_to_tangible_book` is for.** It carries weight and is scored for nobody.
5. **Run the survivorship measurement**, which caps the confidence of every statement here.
