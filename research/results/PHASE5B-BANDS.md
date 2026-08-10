# Phase 5b — The band cutoffs are not the problem

**26 of 27 comparable metrics score faithfully. The hypothesis this was built to test is
wrong, and that is the useful part: it closes off "just recalibrate the thresholds" as a
remedy.**

Numbers: `phase5b_bands.json`. Harness: `research/bands.py`. 153 rebalances, 2017–2026.

---

## The question it was built to settle

Phase 5 measured return on invested capital *as the model ranks it* — through its band score —
and got t = +0.5. Phase 4 measured the raw metric and found its top decile at a Sharpe of 1.29
against the universe's 0.99. Same input, same window, opposite readings, with only the band
configuration between them.

I flagged the cutoffs as the likely culprit and said so twice. The measurement says otherwise.

---

## Result

| verdict | metrics | weight of score |
|---|---|---|
| bands faithful | **26** | — |
| bands cost information | **1** (`accruals_ratio`) | 2.2% |
| bands add information | 0 | — |
| not comparable | 5 | 12.6% |

The single exception is `accruals_ratio`: raw IC +0.0125 against scored +0.0048, a gap of
0.0077 on a metric carrying 2.2% of the score — and well below the 0.028 this sample can
resolve after multiple-testing correction. It is a lead, not a finding.

Across every metric that matters, raw and scored track each other within a few thousandths:

| metric | weight | raw IC | scored IC | gap |
|---|---|---|---|---|
| ev_to_ebitda | 7.6% | −0.0115 | −0.0139 | +0.0024 |
| return_on_invested_capital | 6.8% | +0.0064 | +0.0049 | +0.0015 |
| gross_profits_to_assets | 5.7% | +0.0160 | +0.0189 | −0.0029 |
| ev_to_fcf | 5.0% | −0.0061 | −0.0107 | +0.0047 |
| piotroski_f | 4.5% | −0.0094 | −0.0074 | −0.0020 |
| interest_coverage | 4.5% | −0.0066 | −0.0065 | −0.0002 |
| free_cash_flow_yield | 4.2% | −0.0073 | −0.0061 | −0.0012 |
| price_to_book | 1.4% | −0.0176 | −0.0174 | −0.0002 |

Direction was inferred per period from the bands themselves rather than declared in this file,
so these signs are the model's own reading of each metric, not mine.

---

## What follows from it

### 1. Valuation's inversion is real, not an artifact of the cutoffs

Every enterprise multiple is negative *raw*: ev_to_ebitda −0.0115, ev_to_ebit −0.0097, ev_to_fcf
−0.0061, price_to_book −0.0176. The bands were not hiding a working signal. Over 2017–2026,
cheap did not beat expensive in this universe, measured directly on the underlying numbers.

That closes the last remaining innocent explanation for the valuation result. It does **not**
license removing the category — that exact change was tested in Phase 6b and came out worse out
of sample than the model it was fixing.

### 2. The Phase 4 / Phase 5 contradiction resolves — differently than I expected

Raw ROIC's information coefficient is +0.0064. Effectively zero, the same as its scored version.
So the gap against Phase 4's Sharpe of 1.29 was never about banding. The two statistics were
measuring different things, and both were right:

- **Information coefficient** asks whether the metric orders the cross-section by *return*.
  ROIC does not.
- **Top-decile Sharpe** asks what happens if you hold the best-rated names. ROIC's top decile
  earned roughly market returns at 17.9% volatility against the universe's 18.5%, with the
  bottom decile at 27.7%.

**ROIC sorts companies by risk, not by return.** That is a real and useful property — it is
most of what "quality" means as an investment idea — and it is invisible to a rank correlation
against returns. Neither measurement was wrong; I read a contradiction into two questions that
were never asking the same thing.

### 3. There is no cheap fix left in the scoring

The remedies this engagement has now tested and closed:

| remedy | status |
|---|---|
| Recalibrate band cutoffs | **closed** — bands are faithful (this file) |
| Remove the valuation category | **closed** — worse out of sample (Phase 6b) |
| Reweight on measured ICs | **closed** — nothing survives correction (Phase 5) |
| Rank on raw metrics instead of scores | **closed** — same ICs (this file) |

What remains open is not in the scoring formula at all: the leaderboard is stratified by data
availability (`LIVE-LEADERBOARD-AUDIT.md`), and survivorship is unmeasured. Both are data
problems, both are actionable now, and neither depends on any factor question.

---

## Limitations

- Same power limit as Phase 5: effects below roughly 0.028 IC are unresolvable here, and every
  effect measured is smaller than that. "Bands faithful" means the two readings agree, not that
  either carries signal.
- A faithful band is not a well-chosen band. This tests whether the cutoffs *preserve the
  ordering* of the underlying metric, not whether that ordering is the best available cut.
- Five metrics are not comparable: `forward_pe`, `peg`, `earnings_surprise` and `altman_z` are
  absent point-in-time, and `price_to_tangible_book` is suppressed for nearly every profile.
- Two-tailed metrics have no monotone raw direction. `asset_growth` and `capex_to_depreciation`
  were resolved as directional here because the band midpoint sits near one end of the observed
  range, so their comparison is weaker than the others' and should be read as indicative.
