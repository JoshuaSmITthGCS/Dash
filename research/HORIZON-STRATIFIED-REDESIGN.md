# Horizon-Stratified Redesign of the Swing Composite

**Status:** research proposal, constructive. Nothing here is implemented.
**Target:** `pipeline/swing_signals.py`, `pipeline/build_swing_screen.py`, `pipeline/costs.py`, `pipeline/validation/`.
**Written against:** the frozen baseline (variant A, `SWING_WEIGHTS` 30/25/20/15/10) and the audit findings P1 through P5.
**Decision deadline:** 2026-09-01, when `pipeline/validation/harness_freeze.json` starts the prospective clock.

---

## Implementation status, 2026-08-13

**All three tiers were built, at the author's direction, after this report recommended funding
one.** That decision is recorded here rather than argued again. What the report changed is how
they were built.

| Report said | What was built | Where |
|---|---|---|
| Tier F fails its break-even by ~15x | Built, but **event-triggered rather than a standing cross-sectional rank**. A name enters only in the sessions after it reports, so turnover follows the earnings calendar, not the trading calendar | `swing_tiers.py::TIER_SPECS["F"]` |
| Tier M is undecidable on current evidence | Built, with the decision left to the data | `TIER_SPECS["M"]` |
| Tier S is the only tier that clears | Built | `TIER_SPECS["S"]` |
| The cost arithmetic is what decides viability | **Every row publishes its own round trip against its own expected alpha.** `net_edge_bps` is a sortable column, so a book that does not clear its costs says so per name rather than in a footnote | `swing_tiers.py::row_economics` |
| Announcement-return surprise is the structural fix for P1 | Built as a leg in all three tiers. Needs no analyst data | `swing_signals.py::announcement_return` |
| A leg may not enter a faster tier on a slower tier's effect size | Enforced as a test: a leg capturing under 20% of its documented payoff inside a tier's window cannot be in that tier | `test_swing_tiers.py::test_each_leg_only_enters_a_tier_where_its_payoff_lands` |
| The reversal leg fails at t=1.37 | **Still carried, at 20%, in the fast book only.** It is one of only two legs with any documented fast-horizon claim, so a 3-day book without it would have one leg. This is the clearest place where the built product departs from the report's recommendation | `TIER_SPECS["F"]` |

The 8-week tier was kept at 40 sessions rather than extended to the 60-90 this report argues
for. Extending it remains recommendation R3 and is still the cheapest change available.

Two design decisions the report did not anticipate, both forced by writing the code:

- **Tier M lost its 52-week leg.** The 20%-capture rule this report proposes, once written as a
  test, rejected a 15% allocation to a leg capturing 16% at that horizon. The rule was applied
  rather than relaxed, and the freed weight went to the three legs that had delivered.
- **The volume leg was rebuilt as abnormal turnover.** A raw recent-to-average volume ratio is
  mechanically larger for a quiet-baseline name, which imports the same undeclared tilt that
  raw 52-week proximity imported before rule 4 fixed it.

---

## How to read this document

Three labels appear throughout and they mean different things.

| Label | Meaning |
|---|---|
| **Established** | Published in a peer-reviewed journal, effect size quoted as published. |
| **Derived** | Arithmetic performed here from published inputs plus stated assumptions. The assumptions are always stated. |
| **Unmeasured** | Would have to be measured on this specific implementation. The author does not have it. |
| **Convention** | A threshold chosen by custom, not derived from a result. Labeled every time. |

Every published effect size carries a McLean-Pontiff haircut before it is treated as a live
expectation. This report applies the **58% post-publication haircut** to every signal whose
publication predates 2020, and the **26% out-of-sample haircut** only to constructions that
have not been published in the exact form proposed. The choice is stated per signal. The
existing code (`swing_signals.py::DECAY_HAIRCUT`) already takes the same position for the
five current legs, and this report extends it to every new candidate.

Two conversion conventions run throughout, both labeled as conventions:

- **Long-only reachable fraction: 35% of a published long-short decile spread.** A top-decile
  long-only book earns roughly half the decile spread over the universe mean by symmetry,
  and Stambaugh, Yu and Yuan (2012) show mispricing concentrates on the short leg, so the
  long side gets less than half. 35% is the midpoint of a defensible 30% to 40% range. Where
  a signal is known to be long-side-heavy (insider buying) the report uses 55% and says so.
- **Round trips per year = 252 / holding period in sessions.** This is the prompt's convention
  and it assumes full book replacement, which overstates turnover for any book with
  persistent names in it. Treated as a ceiling, not an estimate.

---

# 1. Verdict on tier viability

**Answer: fund one book, not three.**

- **Tier S is the only tier that clears costs.** Fund it. Extend its horizon past the current
  40-session cap.
- **Tier M is undecidable on current evidence.** Its viability flips depending on which
  long-only-capture and haircut conventions you adopt, and both are conventions rather than
  measurements. Run it on paper. Do not allocate capital to it until its IC is measured.
- **Tier F is not viable at any book size this author will run, at 50bp, at 25bp, or at
  10bp.** Do not build it as a book. Run it on paper as a measurement instrument, which is the
  one thing it is genuinely good for.

The reason the three-book structure fails is simple and general: **cost scales linearly in
rebalance frequency and alpha does not scale at all.** Running the same signals faster buys
nothing and pays for everything.

**Where the M-speed signals go.** Not into the S book as scoring legs. The decay matrix
(Section 2.1) shows the high-volume premium has paid out its whole 20-day window before an S
book's 60-to-90-session hold is a third done, so scoring it in S means paying for a signal
that has already expired. It goes instead into **entry timing**: among the names Tier S has
already decided to hold, prefer entering the ones currently showing a volume surge. That uses
the signal at its own horizon, adds no turnover because the trade was happening anyway, and
fits the `pipeline/config/entry_timing_overlay.yaml` mechanism this codebase already has.
This is the one place a fast signal earns its keep in a slow book, and it is worth
distinguishing sharply from carrying it as a leg.

There is a second verdict, and it is the more important one.

**The three tiers stand in inverse relationship between economic viability and statistical
verifiability. The tier you can afford to trade is the one you cannot verify, and the tier
you can verify is the one you cannot afford to trade.** Section 1.4 does that arithmetic. It
changes what the frozen harness is for.

## 1.1 The 50bp round-trip figure is the wrong shape, not the wrong number

P2 says the tiered spread proxy in `costs.py` is downward biased. That is half right. The
proxy is badly downward biased in illiquid names and roughly correct or slightly conservative
in liquid ones. The deeper problem is that a single round-trip number cannot exist for this
book, because round-trip cost varies by a factor of roughly 75 across the cap spectrum and by
a factor of roughly 3 across plausible book sizes.

Recomputed round-trip cost, using effective full spreads in the range the EDGE estimator and
the Chen-Velikov high-frequency spread data produce for US equities in the 2015 to 2025
period, plus the pipeline's own canonical square-root impact term at the base scenario
(coefficient 630, meaning impact equal to one daily sigma at 100% ADV participation).

**Derived. Book of 82 positions. Round trip = one full effective spread + 2 x one-way impact.**

| Cap band | Assumed ADV | Assumed ann. vol | Effective spread (bps) | Impact/side at $1M book (bps) | **Round trip at $1M** | Impact/side at $50M book | **Round trip at $50M** |
|---|---|---|---|---|---|---|---|
| Mega, >$200B | $500M | 28% | 1.5 | 0.9 | **3 bps** | 6.2 | **14 bps** |
| Large, $10-200B | $100M | 32% | 3.0 | 2.2 | **7 bps** | 15.7 | **34 bps** |
| Mid, $2-10B | $20M | 38% | 9.0 | 5.9 | **21 bps** | 41.7 | **92 bps** |
| Small, $300M-2B | $3M | 45% | 30.0 | 18.1 | **66 bps** | 128 | **untradable, 42% ADV** |
| Micro, <$300M | $0.5M | 60% | 120.0 | 59 | **238 bps** | n/a | **untradable** |

Blending at the realized book composition (roughly 55% mega and large, 30% mid, 15% small,
inferred from the disclosed top of book of ZD, TWLO, AMZN, COLM, GOOGL, CVX, ADM):

| Book size | Blended round trip | Versus the 50bp assumption |
|---|---|---|
| $1M | **19 bps** | 2.6x too conservative |
| $10M | **28 bps** | 1.8x too conservative |
| $50M | **45 bps**, small-cap sleeve untradable | roughly correct |
| $250M | **~110 bps**, mid-cap sleeve untradable | 2.2x too optimistic |

**The 50bp figure is not a property of the strategy. It is a property of a $50M book in large
caps.** At $1M it is 2.6 times too pessimistic and it has been making the fast tiers look
worse than they are. At $250M it is 2.2 times too optimistic and it has been making the whole
book look more capacious than it is. Publishing one number without the book size attached is
the defect, and it is a bigger defect than the spread proxy being a proxy.

This matters for P1 as well as P2. Look at the small-cap row. **The habitat where the PEAD and
high-volume-premium alpha lives carries a 66bp round trip at $1M and is untradable at $50M.**
The habitat inversion and the cost problem are the same problem. Chordia, Goyal, Sadka, Sadka
and Shivakumar's finding that costs consume 63% to 100% of paper SUE profits is reproduced by
this table without needing their data: 1.60%/month in the most illiquid decile against a 66bp
round trip is fine at monthly turnover and gone at weekly.

## 1.2 The tier cost table, both versions

**As specified in the prompt, at a flat 50bp:**

| Tier | Hold | Round trips/yr | Cost drag/yr | Break-even gross alpha/month |
|---|---|---|---|---|
| F | 3 sessions | 84 | 4200 bps | 3.50% |
| M | 10 sessions | 25.2 | 1260 bps | 1.05% |
| S | 40 sessions | 6.3 | 315 bps | 0.26% |

**Recomputed at measured effective spreads, by book size. Derived.**

| Tier | RT/yr | Drag at $1M (19bps) | Break-even/mo | Drag at $10M (28bps) | Break-even/mo | Drag at $50M (45bps) | Break-even/mo |
|---|---|---|---|---|---|---|---|
| F | 84 | 1596 bps | **1.33%** | 2352 bps | **1.96%** | 3780 bps | **3.15%** |
| M | 25.2 | 479 bps | **0.40%** | 706 bps | **0.59%** | 1134 bps | **0.95%** |
| S | 6.3 | 120 bps | **0.10%** | 176 bps | **0.15%** | 284 bps | **0.24%** |

The recomputation helps Tier F considerably at small size and does not save it. Section 1.3
explains why.

## 1.3 What is actually available to earn, and why Tier F dies

The binding constraint is not the cost model. It is the size of the prize.

Chen and Velikov (JFQA 2023), across 204 anomalies, net of effective spreads, net of
post-publication decay, and restricted to the post-2000 trading era: **the average anomaly nets
4 bps per month. The strongest anomalies net at best 10 bps. Methods for combining anomalies
net around 20 bps.** Those are long-short numbers.

That is the ceiling on this entire enterprise, and it is set by the best available estimate
across the largest available sample of exactly the kind of signal this composite is built
from. Take the most generous reading. A good multi-signal composite nets 20 bps/month
long-short. The long-only reachable side at the 35% convention is **7 bps/month**, or roughly
0.84%/year of alpha over the universe.

Working forward from gross instead, to cross-check:

**Derived. Best-case gross alpha available to a long-only top-decile book.**

| Step | Value | Source |
|---|---|---|
| Good multi-signal composite, long-short decile spread, in-sample | 60 bps/mo | Convention, generous versus Chen-Velikov's average |
| After 58% post-publication haircut | 25 bps/mo | McLean & Pontiff 2016 |
| Long-only reachable side at 35% | **8.8 bps/mo gross** | Convention, this report |

Now hold that 8.8 bps/month gross against the break-even table.

| Tier | Break-even at $1M | Available gross | Verdict |
|---|---|---|---|
| **F** | 1.33%/mo | 0.088%/mo | **Fails by 15x** |
| **M** | 0.40%/mo | 0.088%/mo | **Fails by 4.5x on the generic composite** |
| **S** | 0.10%/mo | 0.088%/mo | **Marginal. Roughly break-even.** |

**Tier M deserves one more pass, because its verdict is convention-dependent rather than
evidence-determined.** The best M-habitat signal is the high-volume premium. Take Gervais,
Kaniel and Mingelgrin at roughly 75 bps/month long-short over the 20-day window in the
relevant deciles, and price it under two defensible convention sets:

| Convention set | Haircut | Long-only capture | Live gross | M cost at $1M, full replacement | M cost at $1M, with banding | Verdict |
|---|---|---|---|---|---|---|
| Conservative (this report's default) | 58% | 35% | 11 bps/mo | 40 bps/mo | 22 bps/mo | Fails 2x |
| Generous | 26% | 50% | 28 bps/mo | 40 bps/mo | 22 bps/mo | Clears 1.3x |

Banding is the buy/hold spread already present in the config as `entry_percentile` 90 and
`exit_percentile` 75, and Novy-Marx and Velikov show such spreads cut turnover by roughly 40%
to 60% at minimal alpha cost. So Tier M is neither clearly alive nor clearly dead. It sits
inside the error bars of two unmeasurable conventions.

**When a tier's viability depends entirely on which convention you pick, the evidence cannot
make the decision and neither should the author.** Run Tier M on paper next to Tier F, measure
its IC, and let the measurement decide. Do not fund it in the meantime. This is also the only
recommendation in the report that a motivated author is likely to want to overrule, which is
itself a reason to hold the line on it.

This is the honest picture and it is harsher than the prompt's framing anticipated. A generic
five-leg composite of published anomalies does not clear costs at any horizon in a long-only
book. Tier S clears them only to a rounding error.

The only way any tier clears is to carry signals **materially stronger than the average
published anomaly**. Two candidates in this report do, and only two:

| Signal | Published long-short | Post-58% haircut | Long-only reachable | Section |
|---|---|---|---|---|
| Earnings Announcement Return (EAR) | 7.55%/yr = 63 bps/mo | 26 bps/mo | **9.3 bps/mo** | 3.2, 5 |
| Opportunistic insider buying | 82 bps/mo | 34 bps/mo | **19 bps/mo** at 55% long-side | 5 |

Those two, and the low-turnover accounting legs that cost almost nothing to hold, are the
report's answer. Everything else in the current composite and in the candidate list is at or
below the 8.8 bps/month generic line.

**Tier F specifically.** The 3-day tier needs 1.33%/month at $1M and 3.15%/month at $50M. The
strongest short-horizon effect in the literature is short-term reversal, and Da, Liu and
Schaumburg reduce it to 0.33%/month long-short at t=1.37 in modern samples. Post-haircut and
long-only that is roughly **5 bps/month against a 133 bps/month bar**. Nagel (2012) shows
reversal returns rise sharply in high-VIX states, perhaps by a factor of 3 to 4. Even granting
a factor of 4 in the top VIX quintile, that is 20 bps/month in 20% of months, which annualizes
to well under 5 bps/month unconditionally, against a bar 25 times higher.

**Tier F is not viable at 50bp, is not viable at 25bp, and is not viable at 10bp.** At 10bp
round trip the annual drag is still 840 bps and the break-even is 0.70%/month, which is eight
times the available gross. The execution regime that would make it viable does not exist for
this author and would need all of: sub-5bp all-in round trips (achievable only in mega caps at
tiny size), a signal with a genuine 3-day IC above 0.03 (nothing in the candidate list has
one), and a measured decay curve at daily resolution (which does not exist for any of these
legs, see Section 2). Do not build it.

## 1.4 The verifiability inversion

This is the finding that should change the harness design.

Detecting a strategy's alpha from its returns requires t = IR x sqrt(years). The registered
harness runs 24 monthly periods, or 2 years.

**Derived. Years of live returns needed to reach a t-statistic on the return series.**

| True gross IR | Years to t=2.0 | Years to t=3.0 (Harvey-Liu-Zhu) |
|---|---|---|
| 0.25 | 64 | 144 |
| 0.40 | 25 | 56 |
| 0.60 | 11 | 25 |
| 1.00 | 4 | 9 |

Section 4 derives Grinold IR ceilings of 0.25 (S), 0.37 (M) and 0.45 (F). **At the ceiling,
Tier S needs 144 years of live returns to clear a t of 3.** The 24-month harness cannot
validate any tier on returns. Worse, it can only appear to: any 2-year live result that clears
t=3 on returns implies IR ≥ 2.1, which exceeds every tier's Grinold ceiling by four to eight
times and is therefore a defect signature rather than a success.

**The harness must be evaluated on rank IC, not on returns.** IC is measured cross-sectionally
against roughly 820 names per period rather than against one portfolio return per period.

The correct standard error for a mean IC is **the time-series standard deviation of the period
IC series divided by sqrt(number of independent periods)**, not the analytic 1/sqrt(N-3).
Using 1/sqrt(N-3) with N=820 gives 0.035 per period and implies the harness is well powered.
That is wrong, because cross-sectional IC observations within a period are heavily dependent
through the common factor structure. The time-series SD of a monthly rank IC series for an
equity signal typically runs 0.08 to 0.15. Use 0.10.

Independent periods are set by the tier's own horizon, not by the rebalance frequency.
Overlapping labels do not add information. Over the 24-month clock:

**Derived. Statistical power of the 24-month registered harness, by tier.**

| Tier | Horizon | Independent obs in 24 mo | SE of mean IC (SD 0.10) | Detectable IC at t=2 | Detectable IC at t=3 |
|---|---|---|---|---|---|
| F | 3 sessions | 168 | 0.0077 | 0.015 | 0.023 |
| M | 10 sessions | 50 | 0.0141 | 0.028 | 0.042 |
| S | 40 sessions | 12.6 | 0.0282 | 0.056 | 0.085 |

Realistic rank ICs for these signals are 0.02 to 0.04. Read the table against that.

- **Tier F is the only tier the 24-month harness can measure.** It can detect an IC of 0.023 at
  t=3, which is inside the plausible range.
- **Tier M is borderline.** It needs an IC of 0.042 at t=3, roughly at the top of what is
  plausible.
- **Tier S is unmeasurable on this clock.** It needs an IC of 0.085, which is more than double
  any realistic value. To detect IC=0.03 at t=3 in Tier S requires 100 independent 40-session
  observations, which is **16 years**.

So the tier that clears costs cannot be verified for 16 years, and the tier that can be
verified in 2 years cannot clear costs by a factor of 15.

**The productive consequence.** Tier F should be built and run, on paper, at zero capital,
purely as a measurement instrument. It is the only configuration that produces statistically
usable information inside the registered clock, and what it measures, the short-horizon decay
profile of every leg, is precisely the input Section 2 currently has to source from published
papers rather than from this universe. Running a paper Tier F for 24 months converts the
biggest "unmeasured" cell in this report into a measured one, at no cost and no capital risk.

That is a real answer to the prompt's gating question, and it is better than either building
Tier F or dropping it.

---

# 2. The decay-capture matrix

The rule the prompt sets, and which this report obeys: **no leg enters a faster tier on the
strength of an effect size documented at a slower horizon.** Where the decay curve is unknown,
the cell says unknown and states what would measure it.

Capture fractions are the share of each signal's own documented total payoff realized inside
the tier's holding window, measured from signal formation. They are **derived** from the cited
CAR paths and are approximations to within roughly 5 percentage points. Where a paper reports
only endpoint returns and not a path, the cell is marked interpolated.

## 2.1 Current legs

| Leg | Total payoff and window (published) | **F: 2-5 sessions** | **M: 6-15 sessions** | **S: 16-40 sessions** | Beyond 40 | Decay source |
|---|---|---|---|---|---|---|
| **PEAD (SUE)** | CAR path to 60 sessions, drift monotone in SUE decile | **10-12%** | **25-30%** | **60-65%** | **35-40% forfeited**, incl. 25-30% at the next announcement near session 60 | Bernard & Thomas 1989, 1990, CAR path read directly |
| **Analyst revision** | 6-month drift, front-loaded in month 1 | **6-8%** | **12-15%** | **35-40%** | **60-65% forfeited** | Gleason & Lee 2003, and Jegadeesh, Kim, Krische & Lee 2004. Interpolated, the papers report endpoints |
| **High-volume premium** | Returns over 20 sessions post formation, persisting to 50-100 | **~20%** | **~55%** | **100% of the 20-day window**, ~115% to 40 | little left | Gervais, Kaniel & Mingelgrin 2001, 20/50/100-day reported windows |
| **52-week-high** | 0.45%/mo US, 6-month holds, accrual roughly linear in months | **~5%** | **~16%** | **60-65%** | continues, no long-run reversal | George & Hwang 2004. Interpolated from monthly accrual |
| **Short-term reversal** | Reversal of prior-week return, largely complete by 10 sessions | **55-65%** | **95-100%** | **100%, then adverse** as momentum takes over | negative | Jegadeesh 1990, Lehmann 1990, and Nagel 2012 |
| **Announcement return, days 0 to +5** | By construction entirely inside 5 sessions | **100%** | n/a | n/a | n/a | Definitional |

Three things fall out of this table immediately.

**P4 is quantified and it is worse for revision than for PEAD.** The 40-session ceiling forfeits
35-40% of PEAD, which matches the audit's 30-45%. It forfeits **60-65% of the analyst revision
leg**, which carries the second largest weight at 25%. The composite's second-heaviest leg is
being run at roughly one third of its documented power. Either extend the horizon for that leg
or reduce its weight. Carrying 25% weight on a signal delivering 35-40% of its payoff inside
the window is an unforced error.

**Four of the five legs fail the F column.** PEAD at 10-12%, revision at 6-8%, high-volume at
20%, and 52-week-high at 5%. Only reversal has a real F claim, and reversal is dead on effect
size. This is the decay-curve confirmation of Section 1.3's cost arithmetic, arrived at
independently. **There is no Tier F book to build because there are no Tier F legs.**

**The 52-week-high leg is close to a pure S leg.** 5% capture at F and 16% at M. Carrying it at
any weight in a fast tier is spending turnover on a signal that has not yet paid.

## 2.2 Candidate legs

| Candidate | Total payoff and window | F | M | S | Beyond 40 | Decay source |
|---|---|---|---|---|---|---|
| **Earnings Announcement Return (EAR)** | 7.55%/yr long-short, drift over the following quarter, no reversal after 3 quarters | **~15%** | **~30%** | **~65%** | continues, does not reverse | Brandt, Kishore, Santa-Clara & Venkatachalam. Path shape assumed to follow PEAD's, **interpolated** |
| **Multi-quarter SUE history** | Improves PEAD forecast using up to 12 quarters of surprise | **unknown** | **unknown** | **assumed ~60%**, same window as PEAD | assumed same | Kaczmarek & Zaremba 2025. **Decay path not reported.** Assumed to inherit PEAD's |
| **Opportunistic insider buying** | 82 bps/mo abnormal, persists several months | **~5%** | **~12%** | **~35%** | majority beyond 40 | Cohen, Malloy & Pomorski 2012. Interpolated from monthly |
| **Net share issuance** | Annual horizon, ~12-month persistence | **~1%** | **~3%** | **~13%** | most of it | Pontiff & Woodgate 2008 |
| **Cash-based operating profitability** | Annual horizon | **~1%** | **~3%** | **~13%** | most of it | Ball, Gerakos, Linnainmaa & Nikolaev 2016 |
| **Gross profitability** | Annual horizon | **~1%** | **~3%** | **~13%** | most of it | Novy-Marx 2013 |
| **Customer-supplier lead-lag** | ~1 month lag, 1.55%/mo long-short | **~15%** | **~45%** | **100%+** | flat | Cohen & Frazzini 2008 |
| **Industry lead-lag (big leads small)** | weekly to monthly lag | **~25%** | **~60%** | **100%** | flat | Hou 2007 |
| **10-K text change (Lazy Prices)** | quarterly to annual drift | **~2%** | **~6%** | **~25%** | most of it | Cohen, Malloy & Nguyen 2020 |
| **IV skew / IV spread** | weekly rebalance | **~40%** | **~85%** | **100%** | flat | Xing, Zhang & Zhao 2010, and Cremers & Weinbaum 2010 |
| **Earnings announcement premium** | announcement window only | **100%** | n/a | n/a | n/a | Frazzini & Lamont 2007 |

**The unknown cells are the honest part of this table.** Nobody publishes daily-resolution CAR
paths for most of these signals. The F and M columns for EAR, for multi-quarter SUE, and for
insider buying are interpolations from monthly or quarterly endpoints, and interpolation
across a decay curve is exactly the error the prompt forbids. **What would measure them:** a
paper Tier F harness running every candidate at 1, 2, 3, 5, 10, 20 and 40 session horizons on
this universe, producing an IC-by-horizon curve per leg. That is the single highest-value
diagnostic in this report and it is free. See Section 9, item R1.

---

# 3. Per-tier leg specification

## 3.1 Tier S, the 8-week-plus book. **Build this one.**

The horizon cap moves. P4 costs 35-40% of PEAD and 60-65% of revision, and Section 1 shows
Tier S is the only tier with a positive cost-adjusted expectation, so the fix is to stop
capping it at 40 sessions. **Target hold 60 to 90 sessions**, which captures the PEAD
next-announcement cluster and most of the revision drift, and drops round trips per year from
6.3 to 3.5. At $1M that is 66 bps of annual drag instead of 120.

**Recommended Tier S specification:**

| Leg | Weight | Construction change from current | Serves |
|---|---|---|---|
| **Earnings Announcement Return (EAR)** | 25% | **New.** Cumulative abnormal return in the [0,+1] window around the 8-K Item 2.02 timestamp, market-adjusted, ranked cross-sectionally. Replaces SUE as the primary earnings leg. | P1, P3, P5 |
| **SUE, multi-quarter** | 15% | Keep the seasonal-random-walk SUE but extend to a trailing 8-quarter surprise vector rather than the latest quarter alone. Rank-normalized as now. | P4, and Martineau's large-cap null |
| **Opportunistic insider buying** | 15% | **New.** EDGAR Form 4, open-market purchases only, opportunistic (non-routine) filers per Cohen-Malloy-Pomorski. | P3 |
| **Cash-based operating profitability** | 15% | **New.** EDGAR-native, subsumes accruals. | P3 |
| **Net share issuance** | 10% | **New.** EDGAR-native, `pipeline/pit_shares.py` already holds the input. | P3 |
| **52-week-high, sigma-scaled** | 10% | Keep the existing construction. It is correct (see 3.4). | none, it is fine |
| **Analyst revision, residualized** | 10% | Residualize on contemporaneous EAR and SUE. Use revision breadth rather than mean change. | P3, P4 |
| **Short-term reversal** | **0%** | **Drop.** | P5 |
| **High-volume premium** | **0% as a leg** | Its 20-day window closes before an S hold is a third done. Demoted to an **entry-timing overlay** on names S already selected, per Section 1. | P4 |

That is seven legs at 25/15/15/15/10/10/10. On the departure from 1/N, see Section 6.4. The
short version: this is a **two-band** structure, not a seven-way optimization. EAR sits alone
in the top band because it is the only leg with a published effect size materially above the
Chen-Velikov average, and everything else sits in a 10-15% band whose ordering carries no
claim. That is defensible under DeMiguel, Garlappi and Uppal in a way that 30/25/20/15/10 is
not.

## 3.2 The SUE repair, and why EAR replaces it at the top

This is the most consequential change in the report, so the evidence goes in full.

**The surprise-definition evidence.**

| Definition | Data needed | Coverage in an 820-name universe | Published relative strength |
|---|---|---|---|
| Seasonal random walk (current) | EDGAR net income only | ~83% (measured, per the current screen) | The Foster 1977 / Foster-Olsen-Shevlin 1984 baseline |
| Analyst-forecast-based | I/B/E/S consensus | ~100% large cap, collapses in small cap | Livnat & Mendenhall 2006 find analyst-based drift **larger** than RW-based |
| Revenue surprise | EDGAR revenue | ~83%, same as RW | Adds incrementally to earnings surprise |
| **Announcement return (EAR)** | **Daily bars + 8-K Item 2.02 timestamp** | **~100%, and it does not degrade with size** | **7.55%/yr long-short, 1.3 points above the SUE strategy, and no reversal after 3 quarters** |

Livnat and Mendenhall's result is a trap for this pipeline. Analyst-based surprise beats
random-walk surprise, but buying the analyst data to exploit it is what created P1 in the first
place, because analyst coverage is the variable that screens out small caps. **EAR resolves the
tension.** It beats SUE on published effect size, it needs no analyst data at all, and its
inputs are daily bars plus the 8-K timestamp, both of which this pipeline already stores.

**Does EAR fix P1?** Partly, and the partial is worth stating precisely.

- It removes the analyst-coverage dependency from the earnings leg entirely. A microcap with
  zero analyst coverage produces an EAR exactly as well as GOOGL does.
- Combined with dropping the revision leg's weight from 25% to 10%, it materially reduces how
  much the 3-of-5 resolution floor is really a size screen. Under the Tier S spec above, five
  of the seven legs (EAR, SUE, insider, cash profitability, issuance) come from EDGAR and daily
  bars and resolve at ~85-100% regardless of size. **The floor stops being a size screen
  because analyst data stops being load-bearing.** That is the real fix for P1, and it is
  structural rather than cosmetic.
- It does **not** fix the cost side of P1. Section 1.1's small-cap row still shows a 66bp round
  trip. EAR makes small caps *scoreable*. It does not make them *tradable*. Section 6.1 handles
  that separately, and the honest answer there is that the book cannot go where the alpha is
  richest.

**Does multi-quarter SUE revive large-cap PEAD?** Kaczmarek and Zaremba (Finance Research
Letters 2025) report that models using up to 12 quarters of surprise history outperform
shorter-horizon and streak-based approaches on returns, Sharpe and alpha, that **the gains are
stronger among large caps**, and that they have increased over time. If that holds it is a
direct answer to Martineau's finding that large-cap PEAD is non-existent since 2006, and it
matters because large caps are where this book actually trades.

Three cautions, and they are serious.

1. It is a Finance Research Letters paper, not a top-three journal, and the result is
   machine-learning-derived. ML-derived anomaly revivals have a poor replication record.
2. The 26% out-of-sample haircut applies at minimum, and arguably more given the ML
   construction and the recency.
3. This report has not read the paper, only its abstract. **Treat the citation as a lead to
   verify, not as an established input.**

Recommendation: implement the **8-quarter surprise vector** rather than 12, as a simple
rank-average of the trailing eight standardized surprises. That is the non-ML version of the
same idea, it costs nothing to build from data already stored, and it does not import an ML
overfitting risk this author cannot audit. Register it as a variant with its own out-of-sample
clock rather than folding it into the champion.

## 3.3 The revision repair

Revision drops from 25% to 10% and changes construction. Three reasons, all already
established in this report.

1. **Decay.** It captures 35-40% of its payoff inside 40 sessions and 6-8% inside 5. Weight it
   for what it delivers in the window.
2. **P3, the mechanical overlap.** Analysts revise after earnings. Revision and SUE are the
   0.3-0.5 correlated pair carrying 55% of the composite.
3. **Long-only asymmetry.** The code already documents this: Womack's 11.5-point spread is 79%
   unreachable to a long-only book, which the existing `LONG_ONLY_ASYMMETRY` warning states
   correctly and which the 25% weight then ignores.

**Construction changes, in priority order:**

- **Residualize on contemporaneous EAR and SUE.** Regress the revision score cross-sectionally
  on the earnings-surprise scores and keep the residual. What survives is the revision
  information that is not just a restatement of the surprise, which is the part that adds
  breadth. Do this on a **rolling 36-month window with the coefficients estimated only on data
  prior to the scoring date**, never in-sample. See Section 6.3.
- **Use breadth of revisions, not mean change.** The current leg already averages
  `revision_breadth_30d` with three magnitude measures. Drop the magnitude measures and keep
  breadth. Breadth is a count, it is far more robust to the I/B/E/S silent-restatement problem
  (Ljungqvist, Malloy and Marston: 1.6% to 21.7% of records change between downloads,
  non-randomly), because a restated magnitude moves a mean and rarely flips a sign.
- **On I/B/E/S integrity.** The honest position for a data-budget-constrained author is that
  point-in-time analyst data cannot be had cheaply and the silent-restatement risk cannot be
  audited on a free feed. The existing `pipeline/data/estimates` snapshots are the right
  mitigation: they are the author's own point-in-time record, and their value grows with every
  month they accumulate. **Keep snapshotting. Reduce the weight. Do not buy I/B/E/S.** At 10%
  weight on a residualized breadth measure, the restatement risk is bounded to something small.

## 3.4 52-week-high: confirm the current construction, confirm S-only

**Confirmed on both counts.**

The sigma-scaled drawdown construction is correct and the reasoning in `swing_signals.py` rule
4 is right. Raw proximity correlates -0.49 with realized volatility on this universe (the
pipeline measured this), so raw proximity is half a momentum signal and half an undeclared
low-volatility bet. Dividing out volatility is George and Hwang's ranking with the confound
removed. No change.

**One refinement worth registering as a variant, not as a champion change.** Blitz, Huij and
Martens (2011) and Blitz, Hanauer and Vidojevic (2017) show residual momentum, momentum
computed on Fama-French-residual returns, delivers roughly double the risk-adjusted return of
total-return momentum with about half the volatility. The 52-week-high measure is a
volatility-normalized momentum measure and is therefore already partway toward residual
momentum. Going the rest of the way means computing the drawdown on residual rather than total
returns. Expected gain is real but modest given the sigma-scaling already in place, and it adds
a factor-model dependency. **Register as variant, do not promote.**

**S-only is confirmed by the decay matrix:** 5% capture at F, 16% at M. It has not paid yet at
those horizons.

## 3.5 Short-term reversal: drop it to zero

**Recommendation: zero weight, in every tier. Delete the leg, do not shrink it.**

The case, entirely on evidence already in the author's own file:

| Evidence | Value |
|---|---|
| Original effect (Jegadeesh 1990, Lehmann 1990) | ~2%/month gross |
| Modern risk-adjusted (Da, Liu & Schaumburg 2014) | 0.33%/month, **t = 1.37** |
| After momentum and a refined reversal factor | near zero |
| Capacity (Frazzini, Israel & Moskowitz 2018) | the **most** capacity-constrained anomaly they measure |
| Post-58% haircut, long-only at 35% | **~5 bps/month** |
| Tier F break-even at $1M | **133 bps/month** |

A t of 1.37 does not clear a t of 2, let alone the Harvey-Liu-Zhu t of 3. **The leg fails the
significance bar the rest of this report is held to.** Carrying it at 10% because it is the
composite's only contrarian element is a diversification argument, and a 10% allocation to a
signal with no expected return is not diversification, it is a 10% allocation to noise plus
turnover.

**The conditional version.** Nagel (2012) shows reversal is a liquidity-provision return that
rises sharply with VIX. Da, Liu and Schaumburg show only the residual component survives. The
strongest defensible construction is therefore: residual weekly reversal, active only in the
top VIX quintile, in names above the existing $25M dollar-volume gate. Section 1.3 prices it at
roughly 20 bps/month in 20% of months against a 133 bps/month bar. **It fails even in its best
regime, in its best construction.** The conditional version is not worth building.

This is a straight answer to the prompt's question. The existing registered variant B (reversal
removed, weight redistributed proportionally) is the right variant and should be promoted to
champion before the clock starts. Variant C (residual reversal at the same 10%) should be
retired rather than run, because running it costs a trial on the search path for a leg whose
best case is 5 bps/month.

## 3.6 High-volume premium: the one leg that belongs in Tier M

Decay capture of ~55% at 10 sessions makes this the only current leg with a real M claim.
Specify it carefully, as the prompt asks.

**Construction changes:**

- **Abnormal turnover, not raw volume ratio.** The current subfactors are
  `volume_ratio_1d_50d` and `volume_ratio_5d_50d`, both raw ratios. A raw ratio is
  mechanically larger for names with low and stable baseline volume, which imports a liquidity
  tilt in the same way raw 52-week proximity imported a volatility tilt. **Replace with the
  volume shock standardized by the trailing distribution of that name's own log volume:**
  `(log V_t - mean(log V, 50d)) / sd(log V, 50d)`. Same fix as rule 4, applied to the volume
  leg. This is a defect repair, not a new signal.
- **Order-flow-imbalance proxy from daily bars.** A tick-rule approximation is buildable from
  OHLC alone: sign the day's volume by the close-to-close return, or better, use the
  close's position within the day's range, `(C - L) - (H - C)) / (H - L)`, as a signed
  participation weight. This is the Chaikin construction and it has no independent published
  support as a return predictor, so **it should enter as a refinement of the volume leg's sign,
  not as a leg of its own.** Do not let it become leg number eight.
- **Can it work outside microcaps?** Gervais, Kaniel and Mingelgrin document the effect across
  NYSE size deciles and it is present, though smaller, in large caps. Directionally this is one
  of the better legs for this book's actual habitat, and it is the reason Tier M is
  conditionally viable rather than dead.

## 3.7 Short interest: keep it binary, keep it a screen, do not make it a leg

**Recommendation: keep the current binary suppression. Do not convert to a continuous
negative-weighted leg.**

The reasoning in `swing_signals.py` rule 3 is correct and should not be disturbed. Boehmer,
Jones and Zhang is a **top-decile level** result, and converting a top-decile result into a
continuous linear leg extrapolates a monotone relationship the paper does not establish across
the interior of the distribution. The days-to-cover asymmetry is also handled correctly: an
absolute threshold on days-to-cover fires on low-turnover names rather than heavily-shorted
ones, and the existing code identifies that as a liquidity screen wired backwards. That is a
good catch and it stands.

**On superior inputs.** Utilization rate and borrow fee are better proxies for short-side
constraint than short interest as a percent of float. They are also the crux of a finding in
Section 5: Muravyev, Pearson and Pollet (JFE 2025) show that predictability from IV spread and
IV skew **falls by at least two thirds when high-borrow-fee stocks are excluded**, which means
the option-implied signals and the short-interest screen are largely the same signal. Two
consequences:

1. Borrow-fee data would improve the screen. It costs money (IHS Markit / S3 Partners, and
   neither publishes retail pricing). **Not worth buying** for a screen that already works
   binary at zero cost.
2. **Because the screen already captures the borrow-fee premium in binary form, buying
   options data to capture it again would be paying Tier 3 prices for a signal already held.**
   This is the strongest single argument against the options candidates in Section 5.

**Should the screen differ by tier?** Yes, one difference. Short interest is reported
semi-monthly with a settlement lag of roughly 8 to 10 business days. In Tier S at a 60-session
hold the staleness is immaterial. In Tier M at a 10-session hold the data can be older than the
holding period itself. **In Tier M the screen should suppress on the most recent reading and
otherwise not fire**, and the tier should not pretend to a precision the reporting calendar
does not support.
## 3.8 Tier M specification. **Paper only, no capital.**

Specified in full so it can be run and measured, not because it should be funded.

| Leg | Weight | Construction | Rationale |
|---|---|---|---|
| **High-volume premium** | 40% | Abnormal turnover, standardized log-volume shock against the name's own trailing 50-day distribution (see 3.6). Not the raw ratio. | Only leg with 55% decay capture at 10 sessions |
| **Earnings Announcement Return** | 25% | Same construction as Tier S, but scored only inside a 15-session window from the announcement. | 30% capture at M, and it is the strongest signal available |
| **Industry lead-lag** | 20% | Prior-month return of the large-cap members of the name's GICS industry, applied to the small-cap members. Hou (2007). | 60% capture at M, near-zero correlation with the other two |
| **52-week-high, sigma-scaled** | 15% | Unchanged. | 16% capture. Carried at low weight as a continuation anchor |
| **Analyst revision** | 0% | Excluded. 12-15% capture at M. | Decay |
| **SUE** | 0% | Excluded. 25-30% capture, and EAR dominates it. | Decay plus redundancy |
| **Short-term reversal** | 0% | Excluded. | Section 3.5 |

Four legs. Turnover control is mandatory here, not optional: entry at the 92nd percentile,
exit at the 70th, which widens the existing band. Liquidity floor rises to $25M median dollar
volume, matching the current reversal gate, because M cannot afford the small-cap row of the
cost table.

## 3.9 The Tier F instrument. **Paper only, no capital, and it is not a book.**

Tier F should not be specified as a cross-sectional rank at all. Specified instead as **the
decay-measurement harness** described in Section 1.4, because that is the only thing at this
horizon with positive expected value.

**What it computes.** For every leg in Sections 3.1 and 3.8, and every candidate in Section 5,
the rank IC of that leg against forward returns at horizons of 1, 2, 3, 5, 10, 20, 40 and 60
sessions, computed daily on this universe, with Newey-West standard errors at lag equal to the
horizon.

**What it produces.** An IC-by-horizon curve per leg, measured on this universe rather than
interpolated from published endpoints. That converts every "interpolated" and "unknown" cell in
Section 2's decay matrix into a measured one.

**What it costs.** Nothing. No capital, no data purchase, no execution. It reads the same
`pit_store` and `ohlc_cache` the screen already reads.

**Why this is the right use of the fast horizon.** Section 1.4 shows the fast horizon is the
only one with enough independent observations to say anything statistically inside a 24-month
clock. Spending that statistical power on measuring decay curves, which every other tier
depends on and none currently has, is worth far more than spending it on a book that loses
1.33% a month to costs.

If, after 24 months, the paper harness shows a Tier F composite with a measured 3-session rank
IC above 0.04 and a Newey-West t above 3, revisit. Nothing in the literature suggests it will.

---

# 4. Per-tier evaluation standards

## 4.1 The five dimensions

| Dimension | **Tier F (2-5 sessions)** | **Tier M (6-15 sessions)** | **Tier S (16-60+ sessions)** |
|---|---|---|---|
| **1. Eligible legs** | None qualify. Only reversal has decay-capture above 50%, and reversal fails on effect size (t=1.37). Announcement-window return is the sole event-conditional exception. | High-volume premium (55% capture), industry lead-lag (60%), EAR (30%), 52wk (16%). Excludes SUE, revision. | EAR, multi-quarter SUE, insider buying, cash profitability, net issuance, 52wk, residualized revision. Excludes high-volume premium, reversal. |
| **2. Cost budget** | Max one-way turnover: n/a, not funded. Would need <5bp round trip. Min position: n/a. Liquidity floor would need to be mega-cap only. | Max one-way turnover **600%/yr**. Min position $10k (below that, fixed costs dominate). Liquidity floor **$25M ADV, $10 price, $2B market cap**. | Max one-way turnover **150%/yr**. Min position $5k. Liquidity floor **$5M ADV, $5 price, $300M market cap** (current gates). |
| **3. Statistical bar** | Required 3-session rank IC **>0.04** with NW t>3. Breadth 84 x 30 = 2520. **IR ceiling 0.45.** | Required 10-session rank IC **>0.042** at t=3 on the 24-month clock. Breadth 25.2 x 30 = 756. **IR ceiling 0.37.** | Required 40-session rank IC **>0.03**, but see 1.4: unverifiable in 24 months, needs 16 years. Breadth 6.3 x 30 = 189. **IR ceiling 0.25.** |
| **4. Habitat** | Would have to trade mega-cap only (3bp round trip). **Published fast alpha lives in microcaps at 238bp round trip. Total inversion, 79x.** | Tradable in large and mid ($7-21bp). GKM's effect is strongest in small caps ($66bp). **Partial inversion, 5x.** | Tradable down to small ($66bp round trip is 5.5% of a 60-session hold's cost budget). **Mildest inversion.** S is the only tier that can go near the alpha. |
| **5. Validation protocol** | Label overlap 3 sessions. **Embargo 5 sessions.** Purged K-fold, K=10. 168 independent obs per 24 months. | Label overlap 10 sessions. **Embargo 15 sessions.** Purged K-fold, K=5. 50 independent obs. | Label overlap 60 sessions. **Embargo 70 sessions.** Purged walk-forward only, K-fold is unusable at 12.6 independent observations. |

## 4.2 Where the IR ceilings come from

**Derived.** IR ≤ TC x IC x sqrt(BR).

- **TC, the transfer coefficient**, is set to **0.45**. Clarke, de Silva and Thorley (2002)
  measure TC in the 0.3 to 0.5 range for long-only constrained portfolios. This book is
  long-only, holds roughly 82 of 820 names, and carries a 30% sector cap, so it sits in the
  middle of that range. **Convention, sourced.**
- **BR, breadth**, is (252 / holding period) x N_effective. **N_effective is not 820.** With a
  common factor structure, N_eff = N / (1 + (N-1)ρ) where ρ is the average residual pairwise
  correlation. At ρ = 0.03, N_eff = 820 / 25.6 = **32**. This report uses **30**. This is the
  single most important and least appreciated number in the breadth calculation: **the
  effective breadth of an 820-name US equity cross-section is roughly 30 independent bets, not
  820.**

| Tier | Rebalances/yr | N_eff | BR | sqrt(BR) | Assumed IC | **IR ceiling** |
|---|---|---|---|---|---|---|
| F | 84 | 30 | 2520 | 50.2 | 0.02 | **0.45** |
| M | 25.2 | 30 | 756 | 27.5 | 0.03 | **0.37** |
| S | 6.3 (40d) / 4.2 (60d) | 30 | 189 / 126 | 13.7 / 11.2 | 0.04 | **0.25 / 0.20** |

**Sensitivity.** If N_eff is 100 rather than 30, multiply every ceiling by sqrt(100/30) = 1.83,
giving F 0.82, M 0.68, S 0.46. **Under even the generous breadth assumption, no tier's gross IR
ceiling reaches 1.0.** The audit's finding that any backtested IR above ~1.0 is a defect
signature is correct and conservative. This report tightens it: **any backtested gross IR above
0.5 in any tier should be treated as a defect signature until the breadth assumption behind it
is written down.**

## 4.3 P3 quantified: what collapsed breadth actually costs

**Derived.** For K legs with average pairwise correlation ρ, the composite's IC relative to the
same K legs if they were orthogonal is sqrt(K) / sqrt(1 + (K-1)ρ), and the effective number of
independent legs is K / (1 + (K-1)ρ).

| ρ | Effective independent legs (K=5) | Composite IC as % of the orthogonal case |
|---|---|---|
| 0.00 | 5.00 | 100% |
| 0.10 | 3.57 | 85% |
| **0.15** | **3.12** | **79%** |
| 0.20 | 2.78 | 75% |
| 0.30 | 2.27 | 67% |
| 0.50 | 1.67 | 58% |

The audit's estimate of 3 to 3.5 effective legs corresponds to **ρ ≈ 0.13 to 0.15**, which is
consistent with its pairwise estimates (SUE-revision 0.3-0.5, PEAD-52wk 0.1-0.3, reversal
near-zero against everything). **So the current composite runs at roughly 79% of the IC it
would have if its five legs were independent.** That is the cost of P3, stated as a number.

The Tier S spec in 3.1 has seven legs. If the added legs are genuinely orthogonal, ρ falls. At
K=7 with ρ=0.10, effective legs = **4.38** against the current **3.12**. Composite IC scales
with sqrt(effective legs), so that is a **18% increase in composite IC** from breadth alone,
before counting any of the new legs' own alpha. **The gain from adding EAR, insider buying,
cash profitability and net issuance is not only their alpha, it is an 18% lift in the IC of
everything already held, purchased by breaking the SUE-revision concentration.** That is the
P3 answer and it is why the new legs are accounting and event signals rather than more price
signals.

**ρ is measurable on this pipeline today and has never been measured.** See Section 9, item R2.
It is a one-afternoon job against `pit_store` and it should be done before the clock starts.

---

# 5. New signal candidates

All effect sizes are published long-short unless noted. Live expectation = published x (1 -
haircut) x long-only capture. Haircut column states which was applied and why.

## 5.1 The candidate table

| # | Candidate | Published effect | Haircut applied | Long-only capture | **Live expectation** | Habitat | Turnover/yr | Data | **Tier** |
|---|---|---|---|---|---|---|---|---|---|
| **1** | **Earnings Announcement Return (EAR)**. CAR in [0,+1] around the 8-K Item 2.02 timestamp, market-adjusted, ranked. | **7.55%/yr = 63 bps/mo**, 1.3pts above the SUE strategy, no reversal after 3 quarters | 58%, published 2008 | 35% | **9.3 bps/mo** | **All caps, does not degrade with size.** Needs no analyst data | ~400% (4 events/name, quarterly hold) | **Tier 1, free.** Daily bars + existing 8-K store | **S primary, M secondary** |
| **2** | **Opportunistic insider buying**. Form 4 open-market purchases by non-routine filers. | **82 bps/mo** | 58%, published 2012 | **55%**, long-side-heavy by construction | **19 bps/mo** | All caps, stronger small | ~200-250% (3mo hold) | **Tier 1, free.** EDGAR Form 4 | **S** |
| **3** | **Cash-based operating profitability**. Ball-Gerakos-Linnainmaa-Nikolaev, subsumes accruals. | ~60 bps/mo | 58%, published 2016 | 40% | **10 bps/mo** | Large and mid | ~30% | **Tier 1, free.** EDGAR | **S** |
| **4** | **Net share issuance**. 12-month change in split-adjusted shares outstanding, negated. | ~85 bps/mo | 58%, published 2008 | 30%, short-side-heavy | **11 bps/mo** | All caps | ~20% | **Tier 1, free.** `pipeline/pit_shares.py` already holds it | **S** |
| **5** | **Multi-quarter SUE history**. Rank-average of trailing 8 standardized surprises. | Improves on 1-quarter SUE, **gains stronger in large caps** | **26%**, published 2025 and not yet replicated | 35% | **unquantified, treat as a SUE improvement not a new leg** | **Large caps, which is this book's habitat** | same as SUE | **Tier 1, free.** Already stored | **S, as a variant** |
| **6** | **Gross profitability**. Novy-Marx. | ~31 bps/mo VW | 58%, published 2013 | 40% | **5 bps/mo** | Large | ~20% | **Tier 1, free** | **S, only if cash-based OP is not built** |
| **7** | **Customer-supplier lead-lag**. Cohen-Frazzini. | **155 bps/mo** | 58%, published 2008 | 35% | **23 bps/mo** | Mid and small | ~250% | **Tier 1 data, Tier 2 engineering.** SFAS 131 major-customer disclosure in 10-K, requires text extraction | **M and S. High value, high build cost** |
| **8** | **Industry lead-lag**. Hou (2007), big firms lead small within industry. | ~50-100 bps/mo | 58% | 35% | **8-15 bps/mo** | Small, led by large | ~400% | **Tier 1, free.** Daily bars + GICS | **M** |
| **9** | **10-K text change (Lazy Prices)**. Cohen-Malloy-Nguyen. | ~35 bps/mo | 58%, published 2020 | 35% | **5 bps/mo** | All caps | ~100% | **Tier 1 data, Tier 2 engineering.** EDGAR text diffs | **S, low priority** |
| **10** | **Accruals**. Sloan 1996. | ~80 bps/mo originally | **~100%.** Green, Hand & Soliman document decay to statistical zero in large caps by 2010 | n/a | **~0** | dead in large caps | ~40% | free | **None. Subsumed by #3** |
| **11** | **Earnings announcement premium**. Frazzini-Lamont. | ~34 bps/mo | **~100%.** Heitz, Narayanamoorthy & Zekhnini find US disappearance | n/a | **~0** | n/a | ~1200% | free | **None** |
| **12** | **IV skew**. Xing-Zhang-Zhao. | ~90 bps/mo | 58%, **plus a further two-thirds** for borrow-fee overlap | 35% | **~4 bps/mo** | mid and small | ~1000% | **Tier 3.** OptionMetrics | **None. See 5.2** |
| **13** | **IV spread / put-call parity deviation**. Cremers-Weinbaum. | ~50 bps/mo | 58%, **plus two-thirds** | 35% | **~2 bps/mo** | mid and small | ~1000% | **Tier 3** | **None. See 5.2** |
| **14** | **Option-to-stock volume ratio (O/S)**. Johnson-So. | ~34 bps/wk | 58%, plus overlap | 35% | **~5 bps/mo before turnover** | mid | ~1000% | **Tier 2-3** | **None** |
| **15** | **13F institutional holdings**. | weak | n/a | n/a | **~0** | n/a | quarterly | **Tier 1, already stored** | **None as a leg. Keep as display context** |
| **16** | **13D activist filings**. Brav-Jiang-Partnoy-Thomas, ~5-7% announcement return. | large but rare | 58% | n/a | **not a cross-sectional leg**, too few events in an 820-name large-cap universe | small caps | event | **Tier 1, free** | **None. Optional event flag** |
| **17** | **Index add/delete**. | ~0 in modern samples (Patel & Welch, and Greenwood & Sammon) | ~100% | n/a | **~0** | n/a | event | free | **None** |

## 5.2 The options verdict, and why it saves the most money

Muravyev, Pearson and Pollet (Journal of Financial Economics, October 2025) derive the relation
between the option-implied volatility spread and the stock borrow fee, and show that **return
predictability from implied volatility spread and skew decreases by at least two thirds when
high-borrow-fee stocks are excluded.**

The prompt asks whether they are right that this is repackaged borrow-fee premium already
captured by the short-interest leg. **Take the finding at face value and the conclusion
follows regardless of the interpretive dispute.** Whether the mechanism is a borrow-fee premium
or short-sale-constraint-driven mispricing, the *measured overlap* with the short-constraint
dimension is two thirds. This book already holds that dimension through the short-interest
suppression screen. Buying options data would therefore purchase, at Tier 3 prices, a signal
that is two thirds a restatement of something already held for free.

Add the arithmetic. Candidate 12 nets roughly 4 bps/month live at ~1000% annual turnover. At
the $1M blended round trip of 19bp, 1000% one-way turnover is 5 round trips per year on the
affected sleeve, or **79 bps/year of cost against 48 bps/year of alpha.** It is negative before
the data bill arrives. OptionMetrics academic access runs in the five figures annually and
commercial access substantially more.

**Recommendation: do not buy options data. This is the single largest avoided cost in the
report.** It also directly serves P3: adding a signal two-thirds redundant with an existing
screen reduces effective breadth while appearing to increase leg count, which is precisely the
McLean-Pontiff post-publication correlation-increase mechanism the prompt warns about.

## 5.3 Expected correlations with existing legs

**Unmeasured.** These are priors from mechanism, not measurements. Every cell is a hypothesis
that Section 8 item R2 should test on this pipeline before any weight is assigned.

| Candidate | PEAD/SUE | Revision | High-volume | 52wk-high | Reversal | **Net effect on breadth** |
|---|---|---|---|---|---|---|
| **EAR** | **0.45-0.60** | 0.25-0.40 | 0.30-0.45 | 0.10-0.20 | -0.20 to -0.35 | **Replaces SUE rather than adding to it.** Do not run both at full weight |
| **Insider buying** | 0.05-0.15 | 0.05-0.15 | 0.00-0.10 | -0.05 to 0.10 | ~0 | **Strongly additive.** Best breadth-adder in the table |
| **Cash-based op. profitability** | 0.10-0.20 | 0.10-0.20 | ~0 | 0.10-0.20 | ~0 | **Strongly additive** |
| **Net share issuance** | ~0 | 0.05-0.15 | **-0.15 to -0.25** (issuers trade heavy) | 0.05-0.15 | ~0 | **Strongly additive** |
| **Gross profitability** | 0.10-0.20 | 0.10-0.20 | ~0 | 0.10-0.20 | ~0 | Additive, but **0.6-0.8 with cash-based OP.** Pick one |
| **Customer-supplier** | 0.05-0.15 | 0.05-0.15 | 0.10-0.20 | 0.15-0.25 | ~0 | **Strongly additive** |
| **Industry lead-lag** | ~0 | 0.05-0.15 | **0.25-0.40** | **0.30-0.45** | -0.10 | Moderately additive, overlaps the price legs |
| **10-K text change** | 0.10-0.20 | 0.10-0.20 | ~0 | ~0 | ~0 | Additive |
| **IV skew** | 0.05-0.15 | 0.05-0.15 | 0.10-0.20 | ~0 | ~0 | Additive on paper, **but 0.6+ with the short-interest screen** |

The pattern is the point. **Every genuinely additive candidate is an accounting or event
signal, and every price-derived candidate correlates 0.25 to 0.45 with the price legs already
present.** P3 is not solved by finding better price signals. It is solved by leaving the price
family.

---

# 6. Construction and portfolio, per tier

## 6.1 Fixing the habitat inversion (P1)

Three designs were considered.

| Design | What it does | Verdict |
|---|---|---|
| **A. Drop the 3-of-5 resolution floor** | Score every row on whatever resolves | **Reject.** The floor exists because a 1-leg row is an opinion about one input wearing a composite's clothes. Removing it makes thin rows noisier, not fairer |
| **B. Impute missing legs from a neutral prior** (cross-sectional median rank) | Fill unresolved legs at the median, keep the row | **Reject as the primary fix.** Imputing at the median is functionally the zero-fill rule the pipeline already abandoned in SA-2026-08-12-04, and for the same reason: it pulls thin rows toward the mean and thinness is not random |
| **C. Remove the analyst dependency so the floor stops being a size screen** | Replace SUE-plus-revision with EAR-plus-SUE, cut revision to 10% | **Recommend.** Structural rather than cosmetic |

**Recommended: C, plus size-bucketed book construction.**

C is the fix because it attacks the cause. The floor screens for size **only because two of the
five legs need analyst data**. Under the Tier S spec, five of seven legs come from EDGAR and
daily bars and resolve at 85-100% independent of size. The floor can then stay at 3-of-7
without acting as a size screen, and it keeps doing the job it was written for.

**Size-bucketed book construction** handles the residual. Rather than one cross-sectional rank
across 820 names, rank within three size buckets (large, mid, small) and take the top decile of
each. This guarantees the book cannot become a mega-cap bet by default, which the realized top
of book suggests it currently is. It is also strictly better than size-neutralizing the
composite score, because neutralization removes the size *tilt* while leaving the *ranking*
dominated by whichever bucket has the widest score dispersion.

**Should the design differ by tier? Yes.** Tier M's liquidity floor of $25M ADV eliminates the
small bucket entirely, so Tier M ranks in two buckets. Tier S ranks in three.

**State the limit honestly.** None of this puts the book where the alpha is richest. Chordia et
al measure the SUE long-short at 1.60%/month in the most illiquid decile against 0.14% in the
most liquid, an 11x ratio, and Section 1.1 prices the most illiquid decile at a 238bp round
trip. **At a 60-session hold, 238bp of round-trip cost is 4.2 round trips per year and 10% per
year of drag, which eats the entire 1.60%/month advantage and more.** The alpha in microcaps is
real and it is not reachable from here. Size bucketing gets the book to the small-cap bucket
above $300M market cap and $5M ADV, and that is the boundary. Say so in the output rather than
implying the inversion has been solved.

## 6.2 Combination method: integration versus mixing

**The disagreement, presented rather than resolved.**

| Position | Claim | Source |
|---|---|---|
| **Integration** | Combine signals into a single composite score per name, then select. Captures interaction effects, avoids holding a name that is excellent on one style and terrible on another. | Fitzgibbons, Friedman, Pomorski & Serban, Journal of Investing 2017 |
| **Mixing** | Build separate single-style sleeves and combine the portfolios. Preserves style purity, is transparent to attribution, avoids concentrating on names that are mediocre-everywhere. | Research Affiliates dissent |
| **Neither, robustly** | The integrated-versus-mixed advantage is not robust to reasonable specification choices. The measured gap shrinks or vanishes under alternative constructions. | Leippold & Rueegg 2018 |

**Recommendation: integration, on grounds that have nothing to do with which side is right
about returns.** The Leippold-Rueegg replication says the return difference is not robust, so
the return argument should not decide it. What does decide it here is that **this book is
long-only with a 3-of-N resolution floor**, and mixing requires each sleeve to independently
resolve enough legs to rank, which reintroduces exactly the coverage-driven size screen
Section 6.1 just removed. Integration lets a name with strong EAR and no analyst coverage rank
on what it has.

**Rank versus z-score: use rank.** The pipeline already rank-normalizes SUE for the correct
reason (heavy tails from a difference divided by the standard deviation of eight prior
differences, with 12 of the top 15 rows sitting on the winsorization cap before the change).
That reasoning generalizes. EAR, insider buying and net issuance are all heavy-tailed or
bounded-on-one-side. **Extend `RANK_NORMALIZED_SUBFACTORS` to cover every new leg**, and keep
z-scores only for the bounded ratios where they are already safe.

## 6.3 Orthogonalization

**Recommendation: residualize exactly one pair, and do it on a rolling out-of-sample window.**

The pair is **revision on EAR and SUE** (Section 3.3). That is the one relationship where the
mechanism is unambiguous, the correlation estimate is largest (0.3 to 0.5), and the two signals
carry the most combined weight. Everything else stays raw.

Do not residualize the full set Asness-Frazzini-Pedersen style. In-sample residualization of
seven legs against each other estimates 21 pairwise relationships on a cross-section whose
effective breadth is 30, which is an overfitting engine. The gain from orthogonalizing weakly
correlated legs is small (Section 4.3: going from ρ=0.10 to ρ=0 buys 15% of composite IC across
all legs) and the estimation risk is large.

**Registered protocol, to be frozen before 2026-09-01:**

1. Coefficients estimated on a **rolling 36-month window ending at least one month before the
   scoring date**. No contemporaneous estimation.
2. Winsorize the regressors at 1% and 99% before fitting.
3. If the rolling coefficient's sign flips relative to the prior window, **use zero rather than
   the new coefficient**. A sign flip means the relationship is not estimable, and following it
   is chasing noise.
4. Publish the coefficient series alongside the score so the residualization is auditable.
5. The unresidualized revision score rides along as a published field, the same way
   `composite_z_zero_filled` rides along today. That precedent is good practice and should be
   repeated.

## 6.4 Weighting: the burden of proof for departing from 1/N

DeMiguel, Garlappi and Uppal show that across 14 datasets, no optimization method consistently
beat 1/N out of sample, and that the estimation window needed for mean-variance optimization to
beat 1/N on 25 assets is roughly 3000 months. The burden is on any departure.

**The standard this report holds itself to, and which the current 30/25/20/15/10 vector does not
meet:** a departure from equal weights is permitted only when it is (a) a *reduction* justified
by a documented decay curve or a documented failure, (b) expressible in **bands** rather than
point values, and (c) unchanged by any in-sample fitting.

Against that standard:

| Weight decision | Meets the standard? | Why |
|---|---|---|
| Current 30/25/20/15/10 | **No** | Provenance unexplained. Five distinct point values, none derived. This is P5 and it is a real defect |
| Reversal to 0% | **Yes** | Documented failure, t=1.37, below the significance bar |
| Revision 25% to 10% | **Yes** | Documented decay, 35-40% capture in-window, plus documented long-only asymmetry of 79% |
| High-volume out of S | **Yes** | Documented decay, its window closes before S's hold begins to pay |
| EAR at 25%, top band | **Marginal, and disclosed as such** | Justified by a published effect size 2x the Chen-Velikov strong-anomaly line. This is the report's one upward departure and it is the one a skeptic should attack first |
| Remaining six legs at 10-15% | **Yes** | This is 1/N within a band. The ordering inside the band carries no claim and should not be read as one |

So the Tier S vector is really **one signal at 25% and a near-equal-weighted book of six at
10-15%**, not a seven-way optimization. Stating it that way is more honest than publishing
seven point values, and it makes clear that only one departure needs defending.

## 6.5 Position sizing

| Tier | Recommendation | Reasoning |
|---|---|---|
| **S** | **Equal weight above the cutoff, with a volatility cap rather than volatility scaling.** Cap any position whose annualized volatility exceeds 1.5x the book median at a proportionally reduced size. | Full inverse-vol scaling imports a low-volatility factor bet nobody declared, which is the same error rule 4 fixed for the 52-week leg. A cap removes the tail without importing the tilt |
| **M** | **Equal weight, tighter volatility cap at 1.25x.** | Less time for vol scaling to pay, more sensitivity to a single blow-up over a 10-session hold |
| **F** | n/a | Not funded |

**Reject signal-strength weighting in every tier.** Weighting by composite z-score assumes the
score is cardinal. It is a rank-normalized composite of rank-normalized inputs, which makes it
ordinal by construction. Treating an ordinal score as a position size is a category error, and
it concentrates the book in the extreme tail where the score is least reliable.

## 6.6 Book size per tier, derived rather than conventional

**Derived.** Model expected gross alpha as linear in the composite z-score, alpha_i = a x z_i.
For a standard normal cross-section, the mean z above the p-th percentile is φ(z_p) / (1 - p).
Cut where the **marginal** name's expected alpha equals the cost drag, not where the average
does.

| Cutoff | Names (of 820) | Marginal z | Mean z of book | Marginal alpha as % of book average |
|---|---|---|---|---|
| Top 20% | 164 | 0.842 | 1.400 | 60% |
| Top 15% | 123 | 1.036 | 1.554 | 67% |
| **Top 10% (current)** | **82** | **1.282** | **1.754** | **73%** |
| Top 5% | 41 | 1.645 | 2.063 | 80% |
| Top 2% | 16 | 2.054 | 2.421 | 85% |

Now solve for the cutoff where marginal alpha clears the tier's cost drag.

**Tier S at $1M, cost drag 10 bps/month (40-session) or 5.5 bps/month (60-session):**

| Assumed book-average gross alpha | Implied `a` | Cutoff where marginal = 5.5 bps | Optimal book size |
|---|---|---|---|
| 8.8 bps/mo (generic composite, Section 1.3) | 5.02 | z = 1.10 | **~110 names** |
| 20 bps/mo (EAR-led spec) | 11.4 | z = 0.48 | **~260 names**, capped by other constraints |
| 5 bps/mo (pessimistic) | 2.85 | z = 1.93 | **~22 names** |

**The non-obvious result: a stronger signal justifies a wider book, not a narrower one.** More
names clear the cost hurdle, and more names means more breadth, which raises the IR ceiling.
The instinct to concentrate when confident is backwards under a cost constraint.

**The honest warning attached to this method.** In the pessimistic row the calculation says 22
names. **If the marginal-name calculation returns a very small book, the correct reading is
that the strategy does not clear costs, not that the book should be tiny.** A 22-name book has
BR = 4.2 x 22 = 92, sqrt(BR) = 9.6, and an IR ceiling of 0.17. That is not a portfolio, it is a
rounding error with a name list.

**Recommendation:**

| Tier | Cutoff | Names | Basis |
|---|---|---|---|
| **S** | **Top 15%, ranked within three size buckets** | **~123**, roughly 41 per bucket | Marginal-name calculation at the mid-case alpha, widened from the current 90th percentile |
| **M** | **Top 8%, ranked within two size buckets** | **~50** | Higher cost drag pushes the cutoff tighter |
| **F** | n/a | n/a | Not funded |

The current 90th-percentile convention is not far wrong for Tier S. It is wrong in being a
convention. **The recommendation is not primarily "hold 123 rather than 82", it is "publish the
alpha assumption that produced the cutoff so a reader can check it."**

---

# 7. Cross-tier portfolio design

## 7.1 The four portfolio questions

**1. Three portfolios, three sleeves, or one book with tier-determined exits?**

**One book with one capital pool.** Tier S is the only funded tier, so the question partly
dissolves. For the paper tiers, run them as independent shadow books in
`pipeline/shadow_store/` (the infrastructure already exists and already carries
`quality_value`, `structural_tactical`, `momentum` and `production` sleeves) so their ICs are
measured without contaminating the funded book.

The version of this question that survives: **should the funded S book use tier-determined
exit rules?** Yes. Exit on the 70th percentile or at 90 sessions, whichever comes first, with
the horizon cap being a genuine cap rather than the current 40-session ceiling that forfeits
35-40% of PEAD.

**2. Expected correlation between the three books' returns, and the collapse threshold.**

**Unmeasured, and the estimate is high.** The three tiers share four of their legs, the same
universe, the same long-only constraint and the same sector cap. Estimated return correlation
**0.75 to 0.90** between S and M, and 0.45 to 0.65 between M and F.

**Collapse threshold: 0.70.** Above that, the second book contributes less than 30% of a
portfolio's worth of independent variation, and the complexity of running two specifications,
two harnesses and two multiple-testing corrections is not repaid.

**S and M are expected to sit above the threshold.** That is a second, independent argument for
the Section 1 verdict, arrived at from diversification rather than from cost. Two arguments
reaching the same conclusion by different routes is the strongest form the case takes.

**3. Capital allocation across tiers.**

| Tier | Allocation | Reasoning |
|---|---|---|
| **S** | **100%** | Only tier with positive expected net alpha |
| **M** | **0%** | Undecidable on current evidence, expected correlation with S above the collapse threshold |
| **F** | **0%** | Fails by 15x |

Frazzini, Israel and Moskowitz's capacity findings cut hard against a fast allocation and this
report agrees, but note that **capacity is not the binding constraint at $1M.** At this book
size the binding constraint is the ratio of alpha to spread, not market impact. FIM matters
for the author's future self at $50M+, and the cost table in Section 1.1 shows where that
becomes binding: the small-cap sleeve goes untradable between $10M and $50M.

**4. Combined position rule for a name in more than one book.**

Moot under a single funded book. Specify it anyway so the paper tiers cannot silently
double-count in any future comparison: **cap the combined position at the larger of the two
tier weights, never the sum.** Summing tier weights turns a name that two correlated models
both like into a concentrated bet justified by one signal counted twice.

## 7.2 Cross-tier netting, quantified

**Derived.** Suppose S and M were both funded, S at 123 names and M at 50 names, with M drawn
from a universe S also ranks. Because they share legs, the overlap is well above the 7.5 names
random selection would give. Estimate **18 to 25 names of overlap**, or roughly 40% of the M
book.

| Regime | Annual round trips on the overlapping sleeve | Cost at 19bp |
|---|---|---|
| Independent execution books | S's 4.2 + M's 25.2 = **29.4** | 559 bps |
| Shared execution book, netted | max-side plus residual rebalancing ≈ **26.5** | 504 bps |
| **Saving** | **2.9 round trips** | **55 bps/yr on the overlapping sleeve** |

Scaled to the whole M book (overlap is 40% of it), the saving is roughly **22 bps/year on M's
capital.** Real, and modest. It does not change any viability verdict.

**The larger benefit is not the saving, it is the avoided pathology.** Without a shared
execution book, a name can be sold by M and bought by S on the same morning, paying two full
spreads to end where it started. That is not a cost inefficiency, it is a correctness bug, and
netting is the fix regardless of the basis points.

**Recommendation: if more than one tier is ever funded, one shared execution book, always.**

## 7.3 The aim-portfolio framework, and why it is the rigorous version of this whole report

Gârleanu and Pedersen (Journal of Finance 2013) solve for the optimal dynamic portfolio under
transaction costs. Two results matter here.

1. **The optimal policy trades a constant fraction of the way toward an "aim" portfolio, never
   all the way to the Markowitz portfolio.** Trading to the target is always wrong when costs
   are convex.
2. **The aim portfolio overweights persistent signals relative to their raw alpha and
   underweights fast-decaying ones**, because a fast signal decays before the partial
   adjustment reaches it. The weighting is by signal persistence, not by signal strength.

This is the formal statement of what Sections 1 through 4 derive informally, and it is a
cleaner statement. **The three-tier structure is a discretized approximation to a continuous
persistence weighting, and the discretization is what makes it expensive.** GP say: do not
build three books at three speeds, build one book whose per-signal weight already embeds each
signal's decay rate, and trade partially toward it.

**Concretely, what GP recommends for this pipeline:**

- Weight each leg by (published effect size) x (persistence), where persistence is the decay
  rate from Section 2's matrix. **This is what the Tier S spec in 3.1 does by hand.** The 52-week
  and profitability legs survive at 10-15% not because they are strong but because they are
  slow, and a slow signal is still there when the partial adjustment arrives.
- Replace the binary entry/exit percentile bands with a **partial adjustment rate**: each
  rebalance, move a fixed fraction (start at 0.2 to 0.3) of the distance from current weights
  to target weights. This subsumes banding and is better founded.
- The adjustment rate is a function of cost and risk aversion, both of which the pipeline
  already estimates.

**Recommendation: adopt the partial-adjustment trading rule (Tier 1, free, ~50 lines against
the existing book construction). Do not adopt the full GP closed-form solution**, which needs a
covariance matrix estimated on 820 names, and estimating an 820x820 covariance on this data
budget is exactly the estimation-error problem DeMiguel, Garlappi and Uppal warn about.

Take the trading rule, leave the optimizer. That is the honest read of GP for a
data-budget-constrained author.

## 7.4 Pricing the constraint relaxations

Each constraint priced separately so the author can decide one at a time.

| Constraint | Cost of keeping it | What relaxing it buys | What relaxing it costs | **Verdict** |
|---|---|---|---|---|
| **Long-only** | **65% of every published effect size.** This is the single most expensive constraint in the strategy. Womack's revision spread is 79% unreachable, and Stambaugh-Yu-Yuan show mispricing concentrates short | Roughly **2.9x the alpha.** It converts the whole report from marginal to comfortable | Margin account, borrow fees (which for hard-to-borrow names can exceed the alpha), short-squeeze risk, and the short-interest screen would have to be rebuilt as a leg | **The highest-value relaxation by a wide margin.** If the author will ever relax one constraint, this is it |
| **40-session horizon cap** | **35-40% of PEAD, 60-65% of revision** | Recovers most of both. Also drops turnover from 6.3 to 4.2 round trips/yr, saving 40 bps/yr at $1M | Nothing. There is no cost | **Free money. Do this first.** It is the cheapest change in the entire report |
| **~820-name universe** | Excludes the microcap band where PEAD alpha is 11x richer | Access to 1.60%/month SUE deciles | Section 6.1: a 238bp round trip eats it entirely at any realistic hold. Plus survivorship and delisting bias get much worse, and `research/audit/survivorship/` shows the author has already paid to fix that once | **Not worth it.** The alpha is real and unreachable |
| **No market hedge** | Book is ~100% beta. Every IR quoted in this report is a gross alpha IR that the realized return will not resemble | A beta-hedged book converts a 15% vol equity book into a ~6% vol alpha book, roughly **2.5x the realized IR on the same alpha** | One SPY short or futures position, financing cost, basis risk. `pipeline/shadow_store/SPY` already exists as a benchmark | **Second-highest value, and far cheaper than relaxing long-only.** Strongly recommended |
| **US single-stock** | Forgoes George-Hwang's international 0.60-0.94%/month against the US 0.45% | Higher effect sizes in less-arbitraged markets | Data, FX, settlement, tax, and a whole new point-in-time store. Entirely out of budget | **No** |

**The ranking is: extend the horizon (free), hedge the beta (cheap), then long-short (expensive
but transformative). Do not expand the universe.**
---

# 8. The output artifacts

## 8.1 Fields, per tier

The funded Tier S book, and the two paper books, share a schema. Fields marked **new** do not
exist in the current screen output.

| Field | Type | Purpose | Tier |
|---|---|---|---|
| `ticker`, `name`, `gics_sector` | str | Identity | all |
| `composite_z` | float | **Sort key.** Renormalized across resolved legs | all |
| `tier_percentile` | float | **New.** Percentile within the tier's own ranking, not the global one | all |
| `size_bucket` | enum | **New.** large / mid / small. The bucket the row was ranked within (6.1) | all |
| `bucket_percentile` | float | **New.** Percentile within the size bucket. This is the field that actually determines inclusion | all |
| `legs_resolved` | int | Count, out of the tier's leg count | all |
| `coverage` | float | Share of declared weight that resolved | all |
| `leg_scores{}` | dict | Per-leg standardized score, including nulls, so a reader can see which leg is carrying the row | all |
| `leg_weights_applied{}` | dict | **New.** Post-renormalization weights actually used for this row. Without this the reader cannot reconstruct the score | all |
| `estimated_round_trip_bps` | float | **New.** From the EDGE spread estimate plus impact at the configured book size. Replaces the tier proxy | all |
| `spread_estimator` | str | **New.** `edge` / `corwin_schultz` / `tier_proxy_fallback`. Never let the source be implicit | all |
| `spread_estimate_n_days` | int | **New.** Observations behind the EDGE estimate. A 5-day estimate and a 60-day estimate are not the same number | all |
| `cost_as_pct_of_expected_alpha` | float | **New. The single most important diagnostic in the artifact.** Round-trip cost divided by the tier's expected per-holding-period gross alpha. Above 1.0 the name is a loss | all |
| `expected_holding_sessions` | int | **New.** Tier target, 60-90 for S, 10 for M | all |
| `adv_participation_at_size` | float | Position size over 20-day ADV | all |
| `tradable` | bool | Participation cap check, already implemented | all |
| `short_interest_flag` | enum | suppressed / corroborated / clear | all |
| `short_interest_data_age_days` | int | **New.** Section 3.7: in M this can exceed the holding period | M |
| `pead_window_session` | int | Sessions since the 8-K Item 2.02 timestamp | S, M |
| `ear_value`, `ear_percentile` | float | **New.** The announcement return itself, published beside its rank | S, M |
| `decay_capture_estimate` | float | **New.** From Section 2's matrix, the fraction of this row's dominant leg's payoff the tier's window captures | all |
| `evidence{}` | dict | Existing `SWING_EVIDENCE` block, per resolved leg | all |
| `warnings[]` | list | Existing machine-readable warnings, including `LONG_ONLY_ASYMMETRY` | all |
| `variant_id` | str | **New.** Which registered variant produced this row | all |
| `is_paper_only` | bool | **New.** True for M and F. Must be impossible for a paper row to reach a funded book by accident | M, F |

## 8.2 The two fields that matter most

**`cost_as_pct_of_expected_alpha`.** Every other diagnostic in the artifact describes the
signal. This one describes whether the signal survives being traded. It is the field this
entire report reduces to, and no current output has it. A reader looking at one name should be
able to see, without arithmetic, that a small-cap name with a 66bp round trip and a 60-session
hold is spending 66bp to earn an expected 15bp.

**`spread_estimator`.** The current cost model is honest in its docstring about the proxy being
a proxy, and that honesty is then lost by the time a number reaches a page. Carrying the
estimator name on every row makes the limitation travel with the number.

---

# 9. Sequenced roadmap and harness registration

## 9.1 The roadmap, ranked by expected improvement over implementation cost

| # | Change | Tier | Data cost | Addresses | **Resets harness?** | What would have to be true | Confirming diagnostic |
|---|---|---|---|---|---|---|---|
| **R1** | **Build the paper Tier F decay harness.** IC by leg by horizon (1,2,3,5,10,20,40,60 sessions), Newey-West at lag = horizon | all | **0** | P4 | **No.** Measurement only, changes no score | Nothing. It reads data already stored | Produces the IC-by-horizon curve that replaces every interpolated cell in Section 2 |
| **R2** | **Measure the inter-leg correlation matrix** on `pit_store` | all | **0** | **P3** | No | Nothing | If average ρ > 0.15, effective legs < 3.1 and P3 is confirmed as measured rather than estimated |
| **R3** | **Extend the horizon cap from 40 to 90 sessions** | S | **0** | **P4** | **YES** | The decay matrix is right that 35-40% of PEAD sits past session 40 | PEAD leg IC at 60 sessions exceeds IC at 40 (R1 measures this directly) |
| **R4** | **Drop the reversal leg to zero.** Promote registered variant B | all | **0** | **P5** | **YES** | t=1.37 is below the bar. Already established, no new evidence needed | Reversal leg IC indistinguishable from zero in R1 |
| **R5** | **Replace the tier spread proxy with EDGE.** `bidask` Python package, cross-check against Corwin-Schultz, calibrate against Chen-Velikov | all | **0** | **P2** | **No.** Changes cost reporting, not scores | EDGE is accurate on daily OHLC for US equities | EDGE and Corwin-Schultz agree within 30% in small caps. If they diverge in large caps, trust EDGE (Corwin-Schultz correlates only 18% with effective spread there) |
| **R6** | **Add the EAR leg** (announcement return surprise) | S, M | **Tier 1, 0** | **P1, P3, P5** | **YES** | Brandt et al's 7.55%/yr survives a 58% haircut and this universe | EAR leg coverage ≥ 95% versus SUE's 83%, and EAR IC ≥ SUE IC in R1 |
| **R7** | **Add opportunistic insider buying** (Form 4) | S | **Tier 1, 0** | **P3** | **YES** | Cohen-Malloy-Pomorski's routine/opportunistic split is reproducible from Form 4 filing history | Correlation with every existing leg below 0.20 (R2 measures it) |
| **R8** | **Cut revision 25% to 10%, residualize on EAR and SUE, switch to breadth-only** | S | 0 | **P3, P4** | **YES** | Revision captures only 35-40% in-window and overlaps SUE at 0.3-0.5 | Residualized revision retains ≥ 50% of raw revision's standalone IC. If it retains almost all of it, the overlap estimate was wrong |
| **R9** | **Add cash-based operating profitability and net share issuance** | S | **Tier 1, 0** | **P3** | **YES** | Both survive a 58% haircut at 10-11 bps/month | Both correlate below 0.20 with all price legs |
| **R10** | **Size-bucketed book construction**, three buckets | S | 0 | **P1** | **YES** | The resolution floor stops being a size screen once analyst data stops being load-bearing (needs R6 and R8 first) | Median market cap of the book falls materially. Small-bucket rows resolve ≥ 3 legs at the same rate as large-bucket rows |
| **R11** | **Abnormal-turnover reconstruction of the high-volume leg** | M | 0 | P2 | **YES** | Raw volume ratio imports a liquidity tilt the same way raw 52wk proximity imported a volatility tilt | Correlation between the volume leg and market cap falls toward zero |
| **R12** | **Partial-adjustment trading rule** (Gârleanu-Pedersen), replacing entry/exit bands | S | 0 | **P2** | **YES** | Convex costs make trading to target suboptimal. Well established | Realized annual turnover falls 30-50% at under 10% IC loss |
| **R13** | **Measure realized annual turnover.** Currently unmeasured | all | 0 | **P2** | No | Nothing | The number itself. Novy-Marx and Velikov: above 50% monthly, few anomalies survive net |
| **R14** | **Multi-quarter (8-quarter) SUE vector** | S | 0 | P1 (large-cap PEAD) | **YES, register as variant** | Kaczmarek-Zaremba replicates without the ML machinery | 8-quarter SUE IC exceeds 1-quarter SUE IC **in the large-cap bucket specifically** |
| **R15** | **Beta hedge via SPY** | S | Tier 1 | none of P1-P5 | **YES** | The book is ~100% beta and every IR here is an alpha IR | Realized book volatility falls from ~15% to ~6-7% |
| **R16** | **Customer-supplier lead-lag** from SFAS 131 10-K disclosures | M, S | **Tier 1 data, Tier 2 engineering** | P3 | **YES** | Cohen-Frazzini's 1.55%/month survives haircut at 23 bps/month, and customer identity is extractable | Extraction accuracy ≥ 80% against a hand-checked sample of 50 filings |
| **R17** | **10-K text change (Lazy Prices)** | S | Tier 1 data, Tier 2 engineering | P3 | **YES** | 5 bps/month survives. It is the weakest keeper in the table | IC above zero at t>2 in R1 |
| **R18** | **Buy options data for IV skew / IV spread** | M | **Tier 3, five figures** | none | YES | Muravyev-Pearson-Pollet is wrong about the borrow-fee overlap | **Do not.** Negative expected value before the data bill (Section 5.2) |
| **R19** | **Buy I/B/E/S point-in-time** | S | **Tier 3** | P2 (integrity) | YES | Revision were worth more than 10% weight, which the decay matrix says it is not | **Do not.** Keep snapshotting to `pipeline/data/estimates` instead |

## 9.2 What must be decided before 2026-09-01

**Tier 0, meaning defect repairs that must land before the clock starts.** Launching a
registered prospective harness on a specification with known defects wastes the only clean
out-of-sample evidence this author will ever get on this version of the strategy.

| Item | Why it is Tier 0 |
|---|---|
| **R3, extend the horizon** | The 40-session cap is a known defect costing 35-40% of the heaviest leg. Registering it means registering the defect |
| **R4, drop reversal** | The leg fails at t=1.37 on the author's own cited numbers. Freezing a known-dead leg into the champion spends 2 years measuring noise |
| **R5, EDGE spread estimator** | Every net figure the harness produces will be computed against the cost model. Freezing a proxy known to be biased means every net result is uninterpretable |
| **R1 and R2, the two measurements** | Free, reset nothing, and both are inputs to decisions R3 through R11. Doing them after the clock starts means the clock measures a specification chosen without them |
| **R13, measure turnover** | P2 is "unmeasured turnover". Starting a 2-year clock without measuring it leaves P2 open for 2 more years |

**Everything else should wait, and the reason is the search path.** R6 through R12 are genuine
improvements, and every one of them is also a trial. See 9.4.

## 9.3 The recommended registration structure

Register **three specifications**, not three tiers, and register them all before the clock
starts.

| Registration | Content | Clock | Purpose |
|---|---|---|---|
| **Champion** | Current spec **plus Tier 0 repairs only** (R1-R5, R13). Five legs minus reversal, four legs at redistributed weights, 90-session cap, EDGE costs | Starts 2026-09-01 | The clean out-of-sample test of the existing idea with its known defects removed |
| **Challenger-1: EAR-led** | Tier S spec from Section 3.1. Seven legs | **Separate clock, starts when built** | Tests whether leaving the analyst-data dependency improves coverage and IC |
| **Challenger-2: minimal** | The four-leg spec argued for in Section 10.2. EAR, insider, cash profitability, net issuance | **Separate clock** | Tests the fewer-legs hypothesis directly |
| **Paper-M, Paper-F** | Sections 3.8, 3.9 | Separate clocks, **never funded** | Measurement instruments |

**The champion keeps the existing clock date and the challengers do not.** That preserves the
one thing already registered while letting the improvements accumulate their own records. It
also means the author is not tempted to compare a 24-month champion against a 6-month
challenger and call the difference signal.

## 9.4 Multiple testing, honestly accounted

**Does running three books multiply the multiple-testing burden by three? Nearly, but not
quite, and the correction is not the important part.**

Harvey, Liu and Zhu (RFS 2016) argue that given the several hundred factors published, a
newly-claimed factor needs roughly **t > 3.0** rather than 2.0. That hurdle already prices the
literature's collective search. It does not price this author's search.

**This author's own trial count, counted honestly:**

| Source of trials | Count |
|---|---|
| Registered swing variants A, B, C | 3 |
| Three tiers | 3 |
| Configurations tested before settling on 30/25/20/15/10 (**undisclosed, and the fact that it is undisclosed is itself a finding**) | unknown, ≥ 1 |
| Legs added and dropped across audit Rounds 3-6 | ≥ 5 |
| Champion promotions in `harness_freeze.json` | ≥ 2 |

The tiers are not independent trials. They share legs, universe and constraint set, so their
test statistics are correlated at perhaps 0.7 to 0.9, and Bonferroni over-corrects badly. A
defensible adjustment for three correlated trials adds roughly 0.2 to 0.3 to the t-hurdle
rather than the 0.4 Bonferroni would.

**Recommended hurdle: t > 3.2 for any leg or tier retained after a search, and t > 3.0 for
anything pre-registered before the clock starts.** The 0.2 difference is the honest price of
searching, and making the pre-registered path cheaper is the right incentive.

**But the correction is not the important part.** Section 1.4 shows that no tier can reach t=3
on returns inside 24 months, and Tier S cannot reach it in 16 years. **A t-hurdle the
experiment cannot reach is not a discipline, it is a decoration.** The operative disciplines
are the three that bind:

1. **Register the full trial list before the clock**, including the undisclosed
   pre-settlement configurations. A search path that is not written down cannot be corrected
   for, and this is the single largest open integrity item in the strategy.
2. **Report every registered variant's result, always, including the losers.** This is what
   actually controls the search-path inflation. It costs nothing and it is the only fully
   effective control available.
3. **Evaluate on IC with Newey-West at the tier's horizon, not on returns**, and publish the
   number of *independent* observations beside every t-statistic. Section 1.4's table is the
   template.

**The failure mode to guard against:** running three tiers, finding that one of them shows a
positive 24-month return, and promoting it. Given the correlations and the power calculations,
that outcome is roughly as likely under the null as under any hypothesis this report considers
plausible. Pre-committing to IC-based evaluation removes the temptation before it arrives.

---

# 10. What not to add, and the case for fewer legs

## 10.1 The exclusions, confirmed

**The retail technical canon: exclusion confirmed, and the existing reasoning in
`swing_signals.py` is correct.**

| Signal | Why it stays out |
|---|---|
| **RSI 70/30** | The thresholds are arbitrary and untested against a multiple-testing correction. RSI is a bounded transform of trailing returns, so at short lookbacks it is short-term reversal in disguise (already dead at t=1.37) and at long lookbacks it is momentum in disguise (already held via the 52-week leg, better constructed). It adds a leg count without adding a mechanism |
| **MACD crossovers** | A difference of two exponential moving averages of price. Pure trailing return, decomposable into the momentum and reversal components the composite already holds explicitly. Sullivan, Timmermann and White's data-snooping work on technical rules found no survival after correction |
| **Bollinger bands** | Price relative to a trailing volatility band. This is the raw-52-week-proximity error the pipeline already fixed in rule 4, in a different wrapper: it mixes a momentum signal with an inverse-volatility bet. The sigma-scaled 52-week leg is the correctly-constructed version of this idea and it is already held |
| **VWAP** | An execution benchmark, not a return predictor. It has a legitimate role in this pipeline, in the cost model, and no role in the signal |
| **OBV** | The `swing_signals.py` caveat is right: on-balance volume has no support comparable to the high-volume premium. It is a cumulative signed-volume sum with an arbitrary sign rule and an unbounded level, which makes it non-stationary and non-comparable cross-sectionally |
| **Candlestick patterns** | The most-tested and least-surviving family in the technical literature. Any pattern set large enough to be interesting is large enough that some member fits any sample |

**One nuance worth stating.** Section 3.6 proposes a Chaikin-style close-position-in-range term
as an order-flow proxy. That is drawn from the same family as OBV. It is admitted **only as a
sign refinement inside the volume leg, never as a leg**, precisely because it has no
independent published support. If it ever appears in an output as its own row, that is the
error this paragraph exists to prevent.

**Additional exclusions established in Section 5:** accruals (subsumed, decayed), earnings
announcement premium (US disappearance), index add/delete (arbitraged away), 13F (stale on
arrival), all options-implied signals (Tier 3 cost, two-thirds redundant with the
short-interest screen).

## 10.2 The harder argument: fewer legs

**The case, and it is stronger than "diminishing returns".** Section 4.3 gives the arithmetic.
A composite of K legs with average pairwise correlation ρ has effective breadth
K / (1 + (K-1)ρ). Start from a 4-leg composite at ρ = 0.1, which has 3.08 effective legs, and
add a fifth.

| Fifth leg's correlation with the existing four | New average ρ | **New effective legs** | Change |
|---|---|---|---|
| ρ = 0.1 (orthogonal-ish) | 0.100 | **3.57** | **+0.49** |
| ρ = 0.2 | 0.140 | **3.16** | +0.08 |
| ρ = 0.3 | 0.180 | **2.87** | **-0.21** |
| ρ = 0.4 (a typical price-signal correlation) | 0.220 | **2.66** | **-0.42** |

**Adding a leg correlated at 0.4 does not deliver a small gain. It makes the composite
strictly worse**, by 0.42 effective legs, while adding a full leg's worth of implementation,
data and turnover cost. The break-even correlation is roughly 0.22: above that, a new leg
subtracts.

Section 5.3's correlation table says every price-derived candidate sits at 0.25 to 0.45
against the price legs already held. **They are all above the break-even.** That is the
quantified reason the candidate list is accounting and event signals, and the quantified
reason the answer to P3 is not "add more legs."

**Per-tier minimum orthogonal sets:**

| Tier | Minimum set | K | Est. avg ρ | Effective legs | Verdict versus the current five |
|---|---|---|---|---|---|
| **S** | **EAR** (earnings event), **opportunistic insider buying** (informed trading), **cash-based operating profitability** (accounting quality), **net share issuance** (managerial signaling) | **4** | **~0.10** | **3.08** | **Ties the current five (3.12) on breadth with one fewer leg.** The win is elsewhere, see below |
| **M** | **Abnormal turnover**, **industry lead-lag** | **2** | ~0.30 | 1.54 | Thin, which is another reason M is undecidable |
| **F** | **None** | 0 | n/a | 0 | There is no viable fast leg |

**Be precise about what the four-leg set wins and what it does not.** On effective breadth it
is a wash: 3.08 against 3.12. Anyone claiming the minimal spec wins on diversification is
misreading the arithmetic. What it actually wins:

| Dimension | Four-leg minimal | Current five |
|---|---|---|
| Effective breadth | 3.08 | 3.12. **Tie** |
| Per-leg live alpha | 9-19 bps/mo (EAR, insider) | ~5 bps/mo, and one leg at zero (reversal) |
| Analyst-data dependency | **None** | Two legs, 55% of weight |
| Coverage in small caps | ~95%+ | ~83% and falling with size |
| Annual turnover | Low, event and accounting driven | Higher, price-signal driven |
| Legs failing the significance bar | 0 | 1 (reversal, t=1.37) |

**So the case for four legs is a case about alpha quality and data independence, not about
breadth.** It covers four distinct mechanisms: what the market learned at the announcement,
what insiders know, what the accounts show about profitability, and what management's
financing behavior reveals. The current five cover roughly two mechanisms (an earnings-news
family and a price-continuation family) wearing five labels.

**Why Section 3.1 nonetheless specifies seven.** Going from four legs at ρ=0.10 to seven at
ρ=0.10 raises effective legs from 3.08 to 4.38, which is a genuine 19% lift in composite IC.
The three extra legs (52-week-high, residualized revision, multi-quarter SUE) are already
built and cost nothing further to carry at 10-15% weights. **The seven-leg version wins on
breadth. The four-leg version wins on simplicity, search path and data independence.**

**If forced to choose one before the clock starts, choose the four-leg version**, on the
grounds that a smaller search path and no analyst-data dependency are worth more to an author
with no out-of-sample record than a 19% IC lift that has never been measured. Register both as
Challenger-1 and Challenger-2 per Section 9.3 and let the paper harness settle it.

## 10.3 The thing most likely to be wrong in this report

Stated explicitly, because the prompt asks for correction of a motivated author, and that
correction applies to the report as well as to the strategy.

**The EAR leg is doing too much work.** It carries the top weight in Tier S, it is the
justification for the fix to P1, it is one of only two signals in the entire report above the
Chen-Velikov strong-anomaly line, and Section 1.3 uses it to rescue Tier S from a break-even
verdict. That is a lot of load on one 2008 working paper whose headline number, 7.55% per year
long-short, has not been re-verified here against a modern sample.

**If EAR fails to replicate on this universe, the Tier S book does not clear costs and the
correct action is to trade none of this.** That conditional should be written into the harness
registration, not discovered later. The diagnostic in R6 (EAR IC ≥ SUE IC, coverage ≥ 95%) is
the check, and it should be treated as a gate rather than a nice-to-have.

---

# 11. Threshold reference table

Every numeric bar in this report, in one place. **Convention** means chosen by custom.
**Derived** means computed here from stated inputs. **Established** means published.

| Threshold | Value | Kind | Source |
|---|---|---|---|
| McLean-Pontiff out-of-sample haircut | 26% | Established | McLean & Pontiff 2016 |
| McLean-Pontiff post-publication haircut | **58%, applied to every pre-2020 signal here** | Established | McLean & Pontiff 2016 |
| Long-only reachable fraction of a long-short spread | **35%** (55% for insider buying, 30% for issuance) | **Convention** | This report, informed by Stambaugh, Yu & Yuan 2012 |
| Round trips per year | 252 / holding sessions | **Convention** | Prompt. Assumes full replacement, so it is a ceiling |
| Average anomaly net expected return | **4 bps/month** | Established | Chen & Velikov 2023, 204 anomalies |
| Strongest anomalies, net | **10 bps/month** | Established | Chen & Velikov 2023 |
| Anomaly combination methods, net | **~20 bps/month** | Established | Chen & Velikov 2023 |
| Available gross alpha, long-only generic composite | **8.8 bps/month** | **Derived** | Section 1.3 |
| Blended round trip, $1M book | **19 bps** | **Derived** | Section 1.1, EDGE-range spreads + canonical impact |
| Blended round trip, $10M / $50M / $250M | **28 / 45 / ~110 bps** | **Derived** | Section 1.1 |
| Round trip by cap band at $1M | mega 3, large 7, mid 21, small 66, micro 238 bps | **Derived** | Section 1.1 |
| Tier F break-even, $1M / $50M | **1.33% / 3.15% per month** | **Derived** | Section 1.2 |
| Tier M break-even, $1M / $50M | **0.40% / 0.95% per month** | **Derived** | Section 1.2 |
| Tier S break-even, $1M / $50M | **0.10% / 0.24% per month** | **Derived** | Section 1.2 |
| Transfer coefficient, long-only | **0.45** | **Convention**, sourced | Clarke, de Silva & Thorley 2002 range 0.3-0.5 |
| Effective independent names, 820-name US cross-section | **30** (at residual ρ = 0.03) | **Derived** | Section 4.2 |
| IR ceiling, Tier F / M / S | **0.45 / 0.37 / 0.25** | **Derived** | Section 4.2 |
| IR ceiling under generous breadth (N_eff = 100) | 0.82 / 0.68 / 0.46 | **Derived** | Section 4.2 |
| **Defect signature threshold** | **Backtested gross IR > 0.5 in any tier** | **Derived** | Section 4.2, tightens the audit's 1.0 |
| Effective independent legs, current composite | **3.12** at ρ = 0.15 | **Derived** | Section 4.3, reconciles the audit's 3-3.5 |
| Composite IC as share of the orthogonal case | **79%** | **Derived** | Section 4.3 |
| Monthly rank IC time-series SD (assumption) | **0.10** | **Convention** | Section 1.4 |
| Detectable IC at t=3 in 24 months, F / M / S | **0.023 / 0.042 / 0.085** | **Derived** | Section 1.4 |
| Years of returns to reach t=3 at IR 0.25 | **144** | **Derived** | Section 1.4 |
| Years of 40-session observations to detect IC 0.03 at t=3 | **16** | **Derived** | Section 1.4 |
| Harvey-Liu-Zhu t-hurdle | **3.0** | Established | Harvey, Liu & Zhu 2016 |
| Recommended hurdle, post-search | **3.2** | **Convention**, derived from HLZ + 3 correlated trials | Section 9.4 |
| Novy-Marx-Velikov turnover danger line | **50% monthly** | Established | Novy-Marx & Velikov 2016 |
| Corwin-Schultz correlation with effective spread | 70% low-cap, **18% high-cap** | Established | Corwin & Schultz 2012, per the audit |
| Costs as share of paper SUE profit | **63-100%** | Established | Chordia, Goyal, Sadka, Sadka & Shivakumar 2009 |
| SUE long-short, most liquid vs most illiquid decile | **0.14% vs 1.60% per month** | Established | Chordia et al 2009 |
| I/B/E/S records changing between downloads | **1.6% to 21.7%, non-randomly** | Established | Ljungqvist, Malloy & Marston 2009 |
| Options predictability lost when high-borrow-fee names are excluded | **at least two thirds** | Established | Muravyev, Pearson & Pollet 2025 |
| EAR strategy abnormal return | **7.55%/yr, 1.3 pts above SUE** | Established | Brandt, Kishore, Santa-Clara & Venkatachalam |
| Womack revision spread reachable by a long-only book | **21%** (2.4 of 11.5 points) | Established | Womack 1996, already in the code |
| PEAD forfeited by the 40-session cap | **35-40%** | **Derived** | Section 2.1 |
| Revision forfeited by the 40-session cap | **60-65%** | **Derived** | Section 2.1 |
| Book cutoff, Tier S | **Top 15%, ~123 names, within 3 size buckets** | **Derived** | Section 6.6 |
| Book cutoff, Tier M | **Top 8%, ~50 names, within 2 size buckets** | **Derived** | Section 6.6 |
| Current cutoff | Top 10%, ~82 names | **Convention** | Existing `entry_percentile` |
| Tier correlation collapse threshold | **0.70** | **Convention** | Section 7.1 |
| Expected S-M return correlation | **0.75-0.90** | **Unmeasured estimate** | Section 7.1 |
| Partial adjustment rate (Gârleanu-Pedersen) | **start at 0.2-0.3** | **Convention** | Section 7.3 |
| Liquidity floor, Tier S / Tier M | **$5M / $25M** median dollar volume | **Convention** | Existing config, extended |

---

# 12. Annotated bibliography

Papers only, grouped by the role they play in this report.

## Cost, capacity and the ceiling on everything

- **Chen, A. & Velikov, M. (2023), "Zeroing In on the Expected Returns of Anomalies", JFQA.**
  The most important citation in this report. Across 204 anomalies, net of effective spreads,
  post-publication decay and the post-2000 trading era, the average anomaly nets 4 bps/month,
  the strongest net 10 bps, and combination methods net around 20 bps. This is the ceiling
  Section 1.3 is built on. Their high-frequency effective-spread code is public.
- **Novy-Marx, R. & Velikov, M. (2016), "A Taxonomy of Anomalies and Their Trading Costs", RFS.**
  Anomalies under 50% monthly turnover generate significant net spreads and few above it do.
  Also the source for buy/hold spreads and rebalance banding as turnover mitigation.
- **Frazzini, A., Israel, R. & Moskowitz, T. (2018), "Trading Costs".** Live institutional
  trading data rather than modeled costs. Finds short-term reversal the most
  capacity-constrained anomaly measured, which is decisive against the reversal leg and
  against Tier F.
- **Gârleanu, N. & Pedersen, L. (2013), "Dynamic Trading with Predictable Returns and
  Transaction Costs", JF.** Optimal policy trades partway to an aim portfolio that overweights
  persistent signals. The rigorous version of this report's entire argument, and the source of
  recommendation R12.
- **Chordia, T., Goyal, A., Sadka, G., Sadka, R. & Shivakumar, L. (2009), "Liquidity and the
  Post-Earnings-Announcement Drift", FAJ.** SUE long-short at 0.14%/month in the most liquid
  decile against 1.60% in the most illiquid, with costs consuming 63-100% of paper profits.
  The empirical core of P1.

## Spread estimation from daily data

- **Ardia, D., Guidotti, E. & Kroencke, T. (2024), "Efficient Estimation of Bid-Ask Spreads
  from Open, High, Low, and Close Prices", JFE 161.** The EDGE estimator, asymptotically
  unbiased and the most accurate OHLC-based estimator available. **Recommended primary.**
  Implemented in the `bidask` package for Python and R, with open spread-estimate data for US
  CRSP stocks.
- **Corwin, S. & Schultz, P. (2012), "A Simple Way to Estimate Bid-Ask Spreads from Daily High
  and Low Prices", JF.** The widely-used predecessor. **Recommended cross-check**, with the
  caveat that its correlation with effective spread falls to 18% in high-cap names, which is
  where this book trades.
- **Abdi, F. & Ranaldo, A. (2017), "A Simple Estimation of Bid-Ask Spreads from Daily Close,
  High, and Low Prices", RFS.** Improves on Corwin-Schultz. Superseded by EDGE for this
  purpose but useful as a third opinion where EDGE and CS disagree.

## The earnings family

- **Bernard, V. & Thomas, J. (1989, JAR and 1990, JAE).** The PEAD CAR path over 60 sessions and
  the 25-30% clustered at the next announcement. The decay curve in Section 2.1 reads directly
  off these.
- **Foster, G. (1977, TAR), and Foster, Olsen & Shevlin (1984, TAR).** The seasonal-random-walk SUE
  construction the pipeline currently implements.
- **Brandt, M., Kishore, R., Santa-Clara, P. & Venkatachalam, M., "Earnings Announcements are
  Full of Surprises".** The EAR construct. 7.55%/yr long-short, 1.3 points above the SUE
  strategy, and unlike SUE it does not reverse after three quarters. **The single most
  load-bearing new citation in this report, and the one most in need of independent
  verification.**
- **Livnat, J. & Mendenhall, R. (2006), "Comparing the Post-Earnings Announcement Drift for
  Surprises Calculated from Analyst and Time Series Forecasts", JAR.** Analyst-based surprise
  produces larger drift than random-walk-based. The finding that creates the P1 tension EAR
  resolves.
- **Martineau, C. (2022), "Rest in Peace Post-Earnings Announcement Drift", Critical Finance
  Review.** Large-stock PEAD non-existent since 2006. The reason the SUE leg cannot carry 30%
  weight in a large-cap book.
- **Kaczmarek, T. & Zaremba, A. (2025), "Beyond the last surprise: Reviving PEAD with machine
  learning and historical earnings", Finance Research Letters 86.** Up to 12 quarters of
  surprise history improves PEAD forecasts, with gains stronger in large caps and increasing
  over time. **Treated as a lead rather than an input:** recent, ML-derived, not a top-three
  journal, and not verified beyond its abstract here.
- **Frazzini, A. & Lamont, O. (2007), "The Earnings Announcement Premium and Trading Volume".**
  The scheduled-date volume effect. Excluded on the strength of the next entry.
- **Heitz, Narayanamoorthy & Zekhnini (2020).** The earnings announcement premium's US
  disappearance. Kills candidate 11.

## Revision, and the data-integrity problem

- **Jegadeesh, N., Kim, J., Krische, S. & Lee, C. (2004), JF.** The change in consensus as a
  robust predictor orthogonal to a wide range of variables.
- **Gleason, C. & Lee, C. (2003), TAR.** Forecast revision relative to consensus, the
  innovation measure. Source for the revision drift path.
- **Womack, K. (1996), JF.** New sells drift -9.1% over six months against new buys at +2.4%.
  The asymmetry that makes 79% of the revision leg's published spread unreachable long-only.
  Already correctly disclosed in the pipeline's `LONG_ONLY_ASYMMETRY` warning.
- **Ljungqvist, A., Malloy, C. & Marston, F. (2009), "Rewriting History", JF.** 1.6% to 21.7%
  of I/B/E/S records change between downloads, non-randomly. The reason to prefer revision
  *breadth* over revision *magnitude* and to keep the author's own estimate snapshots.

## Price and volume

- **Gervais, S., Kaniel, R. & Mingelgrin, D. (2001), JF.** The high-volume return premium over
  20, 50 and 100 days. The only current leg with a real Tier M claim.
- **George, T. & Hwang, C. (2004), JF.** 52-week-high proximity, US spread ~0.45%/month, no
  long-run reversal. The pipeline's sigma-scaled implementation is a correct improvement on the
  raw measure.
- **Blitz, D., Huij, J. & Martens, M. (2011), and Blitz, Hanauer & Vidojevic (2017).** Residual
  momentum roughly doubles risk-adjusted momentum returns at about half the volatility. The
  basis for the registered 52-week variant in Section 3.4.
- **Hou, K. (2007), RFS.** Intra-industry lead-lag, large firms leading small. Tier M candidate 8.
- **Cohen, L. & Frazzini, A. (2008), "Economic Links and Predictable Returns", JF.**
  Customer-supplier lead-lag at 1.55%/month. The best orthogonal candidate whose data is
  free and whose extraction is hard.
- **Jegadeesh, N. (1990), JF, and Lehmann, B. (1990), QJE.** The original short-term reversal.
- **Da, Z., Liu, Q. & Schaumburg, E. (2014), Management Science.** Reversal reduced to
  0.33%/month at t=1.37, and near zero after momentum and a refined reversal factor. **The
  number that kills the reversal leg.**
- **Nagel, S. (2012), "Evaporating Liquidity", RFS.** Reversal as a liquidity-provision return
  that rises sharply with VIX. The basis for the conditional version evaluated and rejected in
  Section 3.5.
- **Lou, D., Polk, C. & Skouras, S. (2019), JFE.** Intraday versus overnight decomposition of
  momentum and reversal, already cited in the pipeline's variant registration.

## Accounting and event signals

- **Novy-Marx, R. (2013), "The Other Side of Value", JFE.** Gross profitability, ~0.31%/month
  value-weighted.
- **Ball, R., Gerakos, J., Linnainmaa, J. & Nikolaev, V. (2016), "Accruals, Cash Flows, and
  Operating Profitability", JFE.** Cash-based operating profitability subsumes accruals. The
  reason to build one leg instead of two, which is a P3 gain as well as an alpha gain.
- **Sloan, R. (1996), TAR**, with **Green, Hand & Soliman (2011)** on its decay to statistical
  zero in large caps by 2010. Included to justify an exclusion.
- **Pontiff, J. & Woodgate, A. (2008), "Share Issuance and Cross-Sectional Returns", JF.**
  Net share issuance. EDGAR-native and the input is already stored.
- **Cohen, L., Malloy, C. & Pomorski, L. (2012), "Decoding Inside Information", JF.** The
  routine/opportunistic split in insider trades, ~0.82%/month for opportunistic. **The best
  breadth-adding candidate in this report: free, EDGAR-native, and near-orthogonal to
  everything already held.**
- **Cohen, L., Malloy, C. & Nguyen, Q. (2020), "Lazy Prices", JF.** Changes in 10-K text
  predict returns. The one NLP signal with a credible effect size, and still only ~5 bps/month
  live.
- **Boehmer, E., Jones, C. & Zhang, X. (2008), JF**, and **Boehmer, Huszár, Wang, Zhang &
  Zhang (2022), RFS.** The short-interest results underpinning the negative screen. A
  top-decile level result, which is why the screen must stay binary rather than becoming a
  continuous leg.
- **Muravyev, D., Pearson, N. & Pollet, J. (2025), "Why does options market information predict
  stock returns?", JFE.** Predictability from IV spread and skew falls by at least two thirds
  when high-borrow-fee stocks are excluded. **The reason not to spend five figures on options
  data.**
- **Xing, Zhang & Zhao (2010), JFQA. Cremers & Weinbaum (2010), JFQA. Johnson & So (2012),
  JFE.** The three options-implied candidates, all excluded on the strength of the entry above.
- **Brav, Jiang, Partnoy & Thomas (2008), "Hedge Fund Activism", JF.** 13D announcement
  returns. Too few events in this universe to be a cross-sectional leg.
- **Patel & Welch (2017), and Greenwood & Sammon (2024).** The disappearance of the index inclusion
  premium.

## Portfolio construction and validation

- **DeMiguel, V., Garlappi, L. & Uppal, R. (2009), "Optimal Versus Naive Diversification", RFS.**
  No optimization consistently beat 1/N across 14 datasets. The burden of proof behind Section
  6.4, and the direct rebuke to the unexplained 30/25/20/15/10 vector.
- **Grinold, R. (1989), "The Fundamental Law of Active Management".** IR = IC x sqrt(BR). The
  IR ceilings in Section 4.2, and the reason a high backtested IR is evidence against a
  strategy rather than for it.
- **Clarke, R., de Silva, H. & Thorley, S. (2002), "Portfolio Constraints and the Fundamental
  Law of Active Management", FAJ.** The transfer coefficient. Long-only constrained portfolios
  run at 0.3-0.5, which is where the 0.45 in Section 4.2 comes from.
- **Fitzgibbons, S., Friedman, J., Pomorski, L. & Serban, L. (2017), "Long-Only Style
  Investing: Don't Just Mix, Integrate", Journal of Investing**, against the **Research
  Affiliates** dissent and **Leippold & Rueegg (2018)**, whose replication finds the
  integrated-versus-mixed advantage not robust to specification. Presented as an unresolved
  disagreement in Section 6.2, and decided there on constraint-compatibility grounds rather
  than on returns.
- **Harvey, C., Liu, Y. & Zhu, H. (2016), "...and the Cross-Section of Expected Returns", RFS.**
  The t > 3.0 hurdle.
- **McLean, R. & Pontiff, J. (2016), "Does Academic Research Destroy Stock Return
  Predictability?", JF.** 26% out-of-sample and 58% post-publication decay across 97
  predictors, worst in high-idiosyncratic-risk low-liquidity names. Also the
  post-publication *correlation increase* among published predictors, which is the mechanism
  behind the warning against naive anomaly stacking.
- **Stambaugh, R., Yu, J. & Yuan, Y. (2012), "The Short of It", JFE.** Mispricing concentrates
  on the short leg. The basis for the 35% long-only capture convention.
- **Shumway, T. (1997), JF, and Shumway & Warther (1999), JF.** Delisting bias. Already addressed
  by the work in `research/audit/survivorship/`, and the reason not to expand into microcaps
  where it bites hardest.

---

## Closing note on what this report is and is not

Everything above is established literature plus arithmetic. **Nothing in it is a measurement on
this implementation.** The author currently has no out-of-sample record, no measured turnover,
no measured inter-leg correlation matrix, no measured decay curves and no measured effective
spreads. Five of those six are free to obtain and four of them (R1, R2, R5, R13) should be
obtained before 2026-09-01.

The single most useful sentence in this document is probably Section 1.4's: the tier that
clears costs cannot be verified for 16 years, and the tier that can be verified in two years
cannot clear costs by a factor of fifteen. Any redesign that does not confront that tension is
rearranging legs.
