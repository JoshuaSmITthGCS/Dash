# ValueSignal — Build Brief: better predictions, better ranking, short and long horizon

**This is a build brief, not an audit brief.** The objective is a system that ranks stocks
better than it does now — higher realised alpha over the market, rankings that hold up inside
whatever subset the user filters to, and separate answers for "what should I hold for a year"
and "what looks good over the next month."

Read `research/ENGAGEMENT-BRIEF.md` first for background and constraints. This file says what
to *build* and how each change gets accepted or rejected.

---

## 0. The honest starting position

Over 2017–2026 on point-in-time data:

| | annualised | Sharpe |
|---|---|---|
| Equal-weighting the whole universe | 18.0% | 0.99 |
| The live composite's top 20 | 19.2% | 0.91 |
| S&P 500 over the same window | ~13–14% | — |

**The live model beats holding everything by 1.2 points and does it at slightly worse
risk-adjusted return.** Its decile ladder does not slope: the score is not ordering the
cross-section. That is the gap to close.

Two things are working and are the foundation to build on:

- **Momentum sorts**, top-decile Sharpe 1.40 against the universe's 0.99, with a near-monotonic
  ladder across all ten deciles (1.40 → 0.66). It is the strongest measured effect in the study.
- **Quality (ROIC) sorts on risk**, top-decile Sharpe 1.29 at *lower* volatility than the market
  (17.9% vs 18.5%), while the junk decile earns similar returns at 27.7%.
- **Together they sort best of anything measured**: monotonicity +0.81, the cleanest ladder in
  the study, and they are not redundant with each other.

One thing is actively hurting: **valuation, 28% of the score, ranked backwards** through four
independent multiples, confirmed raw and banded, in four separate code paths.

**And the universe is not comparable to itself.** 727 of 874 rows are scored without the
statement-derived categories, so a filtered list is partly ordered by who got a data pull.

---

## 1. The five builds, in order of expected effect

### Build 1 — Make the ranking valid inside any filter *(largest immediate win)*

**Problem.** The user filters by sector, by holdings, by theme, by "most undervalued". Every one
of those sorts a mixed population: companies scored on six categories interleaved with
companies scored on four. `weighted_available` renormalises over whatever resolved, so those are
different measurements, not different scores. Within the lighter cohort, merely *having* the two
statement categories is worth 20.8 points of median score.

**Build.** Rank on a basis that is constant across the rows being compared.

1. Publish a per-row `evidence_tier` — which categories resolved — and make every sort and every
   filter cohort-aware. A filtered list should either rank within tier, or rank on the subset of
   categories every row in that filter actually has.
2. Where a filter leaves fewer than ~30 comparable names, say so rather than ranking thinly.
   The peer module already encodes this discipline (`MINIMUM_VALID_PEERS`); reuse it.
3. The bucket planner must allocate within one comparable cohort. Today its top 8 all come from
   a 40-company enriched set.

**Acceptance.** For each of the site's main filters, the rank correlation between
categories-resolved and rank position must fall below 0.1. It is currently **+0.44** across the
whole list. `research/audit_leaderboard.py` measures it; extend it to run per filter.

---

### Build 2 — Two horizons, separately scored and separately validated

**Problem.** One score answers "is this a good company to own" and "is now a good time" at once.
They have different half-lives and different winning signals, and blending them means neither is
measured at the horizon it works over.

**Build.** Two published scores, each validated at its own horizon.

| | horizon | built from |
|---|---|---|
| **Conviction** | 6–12 months | quality/ROIC, financial health, accounting quality, capital allocation — the risk-sorting evidence |
| **Timing** | 1–3 months | 12-1 momentum, volume confirmation, short interest, insider clusters, earnings drift |

The existing harnesses already take `horizon_days` as a parameter, so both can be measured
immediately: run `research/features.py` and `research/candidate.py` at 21, 63, 126 and 252
sessions and keep each signal in the score whose horizon it actually predicts at.

**Do not** let Timing move Conviction. The prior engagement deleted a fabricated timeliness layer
that defaulted to 50/100 with 0% coverage; the replacement must publish nothing when it cannot
resolve, exactly as the current one does.

**Acceptance.** Each score's decile ladder must slope the right way *at its own horizon*, tested
on the held-out half. A Conviction score that only works at one month is a Timing score
mislabelled.

---

### Build 3 — Put the measured winners where they can act

**Problem.** Momentum is the strongest effect in the study and it sits in an 18% "behaviour"
bucket, blended and diluted. Quality is 26% but its best metric (ROIC, 6.8% of score) is diluted
by five metrics in the same block that do not sort — the block scores +0.04 against the universe
while ROIC alone scores +0.30.

**Build.**
1. Construct and test a **quality × momentum** ranking as a first-class published model
   alongside the composite — the construction with the cleanest measured ladder (+0.81).
2. Within profitability, stop averaging a metric that sorts with five that do not. Either drop
   the non-sorters or move them to a diagnostic role that does not carry score weight.
3. Deduplicate the correlated pairs. `ev_to_fcf` (valuation) and `free_cash_flow_yield`
   (profitability) correlate at 0.845 and carry 9.2% between them across two categories, so the
   structure presents one free-cash-flow opinion as two independent judgements. Same for
   `ev_to_ebit`↔`ev_to_ebitda` (0.826, 10.9%) and `ROE`↔`ROIC` (0.752, 9.4%). **~29 points of
   weight express about three opinions.** Collapsing each pair to one input frees real weight
   for signals that are genuinely independent.

**Acceptance.** Design on 2017–2021, report on 2021–2026, selection rule fixed in code first.
`research/candidate.py` is the harness and already does this. Beat the live composite on **both**
CAGR and Sharpe in the held-out half, or the change does not ship.

**Warning, and it is not hypothetical.** Removing the valuation category looked like a clean fix
in-sample — Sharpe 1.17 against the live model's 1.06 — and was **worse on every measure out of
sample** (8.5% vs 15.1%, Sharpe 0.54 vs 0.79). Any reweighting here will look good on the design
half. That is what design halves do.

---

### Build 4 — Widen the measured cross-section

Ranking quality scales with how many genuinely comparable names you can rank. Three levers, all
data rather than modelling:

1. **Close the coverage gap.** 727 of 874 rows lack statement metrics. The enrichment budget was
   just repointed from "highest scorer" to "longest unmeasured", so coverage should now spread
   over ~6 refreshes. Verify with `research/audit_leaderboard.py`; if `enriched_share` is not
   climbing, find out why before building anything on top.
2. **Expand the universe.** 70 companies sit in 17 peer groups too small to ever support a peer
   claim — 6 medical device makers, 7 P&C insurers, 2 large banks. Thirty comparable names per
   group is a data requirement. A wider universe also gives every cross-sectional rank more
   resolution.
3. **Add the missing concepts.** No dividend-per-share, no book value, no retained earnings in
   the point-in-time store, so dividend yield, book yield and Altman-Z cannot be reconstructed
   historically. Widening `edgar_facts.CONCEPT_TAGS` before the next backfill is cheap and
   unlocks whole metrics for testing.

---

### Build 5 — Signals the model does not have

Reweighting correlated inputs cannot add information. New, genuinely independent signals can.
Ranked by (evidence it works) × (cost to obtain):

| signal | status | note |
|---|---|---|
| **Earnings revisions / drift** | absent, needs provider | the best-documented anomaly the model lacks entirely. `earnings_surprise` is configured and resolved for 0 of 40 companies. |
| **Short-horizon reversal** | partially there | the champion treats short-horizon strength as neutral, the challenger as reversal. Never resolved — settle it at the 21-day horizon. |
| **13F institutional changes** | wired, never run live | verify CUSIP resolution on the first real run. |
| **Insider clusters** | live | opportunistic vs scheduled split already implemented. |
| **Backlog / RPO growth** | wired via XBRL dimensions | coverage never measured on a production run. |
| **Share count trend** | derivable now | net buyback yield exists; the *trend* in diluted share count is point-in-time available and untested. |

Each addition must pass the same gate: pre-registered, design half only, reported on the test
half, and counted against the multiple-testing budget in `pipeline/evaluation.py`.

---

## 2. How improvements get accepted

**This is the part that makes the difference between real alpha and a fitted backtest.**

1. **Pre-register.** Write the selection rule into code before looking at results.
   `research/candidate.py::select` is the pattern.
2. **Design half only.** 2017-01 → 2021-07 designs. 2021-07 → 2026-06 reports. Never both.
3. **Judge on the ladder, not the top 20.** Three factors beat the universe in a concentrated
   portfolio while failing to rank the cross-section at all. Decile monotonicity — in Sharpe as
   well as return — is the acceptance test.
4. **Count every variant tried.** With 32 metrics a nominal t of 1.96 expects false winners; the
   corrected threshold is 3.163. `pipeline/evaluation.py` has deflated Sharpe, expected-max
   Sharpe and PBO already implemented and unwired. Wire them.
5. **Beat the right benchmark.** Equal-weighting the universe returned 18.0% at Sharpe 0.99.
   Beating cash, or beating zero, is not a result.
6. **Report risk with return.** A candidate clearing 19.2% by taking more risk has not improved
   anything. Report CAGR, Sharpe, max drawdown and turnover together, always.

### The ceiling on any claim, until it is fixed

**Every performance number in this repository is survivorship-biased upward by an unmeasured
amount.** The universe is companies that still have a price feed today. Momentum is the factor
most inflated by this — ranking on past returns inside a set selected for surviving is close to
ranking on the survival itself, and momentum is also the strongest measured effect. Treat that
as a live risk to the headline result, not a footnote.

`.github/workflows/measure-survivorship.yml` bounds the gap in *count*. It has never been run.
**Run it before publishing any alpha claim.**

---

## 3. What "better" means, measured

Track these before and after every change. All are computable today.

| metric | now | target |
|---|---|---|
| Composite decile Sharpe monotonicity, test half | +0.04 | > +0.5 |
| Composite top-20 Sharpe vs universe (0.99) | 0.79 | > 1.10 |
| Rank correlation, categories-resolved vs rank | +0.44 | < 0.10 |
| Companies with full evidence | 147 / 874 | > 700 / 874 |
| Companies with a peer claim | 804 / 874 | 874 / 874 |
| Metrics passing multiple-testing correction | 0 / 32 | ≥ 1 honestly |
| Independent opinions in the top 29% of weight | ~3 | ≥ 6 |

The last row is the one most likely to produce real alpha and the least likely to be noticed:
the model currently has far fewer independent views than its 32 metrics imply.

---

## 4. What not to do

- **Do not tune weights on the full sample.** It will look better and be worse. This has already
  happened once in this engagement, on evidence that seemed strong.
- **Do not add a signal because it is available.** Add it because it is independent of what is
  already there, and test it.
- **Do not report a concentrated-portfolio return as evidence a ranking works.** Show the ladder.
- **Do not fill a gap with a neutral value.** Absence is absence — a fabricated 50/100 timeliness
  layer with 0% coverage is exactly what this engagement started by deleting.
- **Do not chase the 43.5% out-of-sample momentum number.** It is real in the data and it is the
  most survivorship-inflated figure in the study. It is not a forward expectation.

---

## 5. Start here

1. Run the survivorship workflow. It caps what every other number is allowed to claim.
2. Verify the enrichment fix is spreading coverage (`research/audit_leaderboard.py`).
3. Build 1 — filter-aware ranking. Largest immediate effect on what a user actually sees, and
   independent of every unresolved factor question.
4. Build 2 — split the horizons, then re-measure every signal at both.
5. Builds 3–5 in whatever order the data supports, each through the design/test split.
