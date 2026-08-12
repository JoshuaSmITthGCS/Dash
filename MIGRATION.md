# Swing screen v2: leg corrections and a registered entry-timing overlay

Date: 2026-08-12

## The state of the evidence, before anything below is read

The swing composite has no out-of-sample record. Its prospective clock starts 2026-09-01 and
has not started. Every effect size it quotes is a published gross figure, before costs and
before decay. Nothing in this migration changes any of that, and no result in this document is
a measurement of returns, because there are none to measure yet.

The timing matters for one reason. The clock had accrued zero of its 24 required periods on
2026-08-12, so amending the specification cost nothing in forfeited prospective record. That is
why all eight amendments landed together instead of being staged: staging them would have
started the clock under a specification already known to contain defects.

## What changed to the frozen baseline, and what landed beside it

| Change | Touches the frozen baseline | Resets the clock |
|---|---|---|
| SA-2026-08-12-01 revision leg sign audit and asymmetry warning | Yes, metadata only | No |
| SA-2026-08-12-02 drift windows re-anchored on the earnings release | Yes | Yes |
| SA-2026-08-12-03 SUE drift term confirmed and published | Yes, output field only | No |
| SA-2026-08-12-04 renormalization plus a legs-resolved floor | Yes | Yes |
| SA-2026-08-12-05 decay constants verified repository-wide | No | No |
| SA-2026-08-12-06 cost model reconciled, participation cap added | No, reports on the book | No |
| SA-2026-08-12-07 sector concentration cap | Yes, after ranking | No |
| SA-2026-08-12-08 reversal variants A/B/C | No, A is unchanged | No |
| Entry-timing overlay, O-0 through O-4 | No, defaults off | No |

Two amendments reset the clock, both because they change coverage handling, which
`changes_that_reset_this_clock` in the freeze file names explicitly. The reset costs nothing,
for the reason above.

Variant A of the reversal comparison is the frozen baseline and is byte-identical in weights
and subfactors to what was registered on 2026-08-11. B and C are new challengers, which
`changes_that_do_not_reset` already covers.

---

## Part 1: defect fixes

### 1.1 The revision leg's sign

**What we found.** The sign was already correct. The audit traced it end to end: the raw
consensus inputs in `pipeline/yahoo_estimates.py` (revision breadth as net upward share,
magnitude as fractional change in consensus EPS, net upgrades as upgrades minus downgrades,
target change as percent drift), the differencing that turns a level into a change, the
standardization in `zscores`, the `negate` flags in `SWING_SUBFACTORS`, and the direction of
the cross-sectional rank. Rising consensus maps to a positive score at every step.

**What changed.** Regression tests now pin it, per subfactor as well as per leg, because three
correct signs can mask a fourth that is backwards when four subfactors are averaged into one
leg. The leg also now carries a machine-readable `LONG_ONLY_ASYMMETRY` warning.

**Why the warning.** Womack (Journal of Finance 1996) measures new sell recommendations
drifting -9.1% over six months against new buys at +2.4% over the same window. A long-only book
harvests the +2.4% side and cannot harvest the -9.1% side, so roughly 79% of the published
11.5-point spread is unreachable here. The warning is metadata rather than prose so a
downstream artifact cannot quote this leg's 0.25 weight without it.

### 1.2 The drift anchor

**The defect.** Drift windows were anchored on the 10-Q or 10-K filing date. A periodic report
lands days after the press release that carried the earnings, so every window was reported as
younger than it was, always in the same direction. At a 2-to-10-session holding period, a
multi-day misdating is a large fraction of the window.

**What changed.** `pipeline/earnings_release.py` reads a point-in-time store of earnings release
datetimes taken from Form 8-K Item 2.02, which is a different filing from the 10-Q and arrives
on the day results are released. `pipeline/collect_earnings_releases.py` builds that store from
the EDGAR submissions API. `edgar_sue.sue_for` stamps every row with its release anchor,
resolved or not, and `swing_signals.pead_factor` scores nothing on a row whose release does not
resolve.

**What it costs.** Coverage. A fiscal period with no 8-K in the store now scores nothing on the
highest-weighted leg. That price is published as `pead_anchor_diagnostic` on every run, with
the delta against the pre-amendment 85% surfaced explicitly when coverage falls below it.
Trading fewer names on a correct window is defensible; trading more names on a window that is
systematically too young is not. Coverage rises by extending the store, not by relaxing the
anchor.

**What was deliberately not done.** No fallback to the filing date. The filing date stays on
every row as `pead_filed`, for provenance, and is never promoted into the anchor.

### 1.3 The SUE drift term

**What we found.** The expectation model was already the seasonal random walk with drift. The
drift is the mean of the firm's own trailing seasonal differences, and the scale is their
standard deviation, which is Foster (The Accounting Review 1977) and Foster, Olsen & Shevlin
(The Accounting Review 1984) as specified.

**What changed.** The drift term, the seasonal difference and the scale are now published on
every row, so the with-drift form is verifiable from the output rather than asserted in a
comment. Two tests pin it: one reproduces the arithmetic from the same inputs, and one
constructs a firm growing earnings by a constant amount every year and asserts it does not
register a surprise every quarter. A companion test computes what a bare year-over-year
difference would have said about the same firm, which is a SUE above 10 in every quarter, so
the first test is measuring the drift term rather than luck.

### 1.4 Renormalization

**The defect.** An unresolved leg contributed zero at its declared weight. Zero-filling pulls
every thin row toward the cross-sectional mean, and thinness is not random: coverage tracks
size and liquidity. The rule therefore muted exactly the high-idiosyncratic-volatility,
low-liquidity names where McLean & Pontiff (Journal of Finance 2016) measure post-publication
decay to be worst. That is an undeclared size and liquidity tilt inside a rule that presented
itself as conservative.

**What changed.** Declared weights are renormalized across the legs that resolved for each row.
The wider-dispersion problem the old rule was written against is handled directly instead, by a
floor: a row resolving fewer than three of five legs is excluded from the ranked output
entirely rather than scored near neutral and left in. `coverage` stays published,
`legs_resolved` is published beside it as an explicit count, and the superseded value rides
along as `composite_z_zero_filled`.

**The tension, stated rather than buried.** This reverses the direction Round 4 took on the
research score, where neutral imputation replaced renormalization to break a coverage-score
coupling measured at Spearman 0.554. The two decisions are compatible only because this one is
paired with a hard legs-resolved floor and that one was not. If the prospective clock shows
coverage-score coupling returning on the swing model, this amendment is the first thing to look
at. That is recorded in the freeze file as `acknowledged_tension` rather than left to be
rediscovered.

**The measurement.** `pipeline/diagnostics/renormalization_shift.py` scores one cross-section
both ways and reports what moved in the top decile: market capitalization, dollar volume,
realized volatility, coverage, and which names entered and left. The sector cap is switched off
on both sides so the measurement isolates the scoring change. A large shift means the old tilt
was real and this is a defect fix. A small shift means it was immaterial on this universe and
this is a tidy-up. Both answers are publishable and neither was chosen in advance. The
diagnostic's own tests construct a tilt deliberately and confirm it is detected, because a
measurement that always reports "no change" is not evidence of anything.

### 1.5 The decay constants

**What we found.** Already correct at 26% lower out of sample and 58% lower post-publication,
and no competing figure exists anywhere in `pipeline`, `src`, `docs`, `research` or `scripts`.

**What changed.** All five legs rest on published results, so all five take the
post-publication figure. That list is now enumerated on `DECAY_HAIRCUT` rather than implied.
`pipeline/tests/test_swing_decay_constants.py` fails if a leg is added without it, if either
constant drifts, or if any file in the repository quotes a different decay figure next to
McLean or Pontiff.

### 1.6 The cost model

**The defect we found.** `estimate_cost_bps` clamped participation at 100% of ADV. Past one
day's volume the quoted impact stopped rising with size, so the largest quoted points sat off
the square-root curve and understated cost by exactly the amount the clamp removed. Two figures
under one heading obeying two different models is worse than one figure a reader knows is
extrapolated.

**What changed.**

- The clamp is gone. The square-root law is applied at every size, and `beyond_measured_domain`
  marks the region where it is an extrapolation rather than a calibration.
- Curve consistency is asserted in the published output as `cost_curve_consistency`, and in a
  test, rather than being trusted because one function produced all the points.
- Book size and position size are labelled separately everywhere. `book_dollar_value` is the
  whole book, `position_dollar_value` is one position, `positions_held` is the ratio between
  them, and the capacity conclusion is exactly that ratio. The published key changed from
  `by_portfolio_size` to `by_book_dollar_value` for the same reason.
- A participation cap of at most 10% of trailing 20-day ADV per round trip, defaulting to 5%,
  rejects breaching positions rather than scoring them tradable. A configured cap above the
  ceiling raises rather than clamping, because a silently clamped cap reads as if the requested
  size was accepted. The previous default was 2%, which was the research contract's figure for a
  different, monthly book.
- The cap reads a trailing 20-session mean, added as `adv_20d_dollar_volume`, rather than the
  60-day median the eligibility screens use. A name whose volume has halved in the last month
  still looks liquid on a 60-day median, and that is exactly the name a participation cap exists
  to stop. Rows that can only supply the 60-day median are labelled with `adv_source` rather than
  presented as if they had the 20-day figure.
- The liquidity-tiered spread caveat is attached to every returned estimate as `spread_caveat`,
  not only to the module docstring. It is a proxy, not a measured quoted spread and not an
  effective spread, and no provider in this pipeline serves either.

### 1.7 The sector cap

Four of the five legs are continuation signals, and continuation clusters by sector, so the top
of the ranking concentrates in mega-cap technology and communication services. A sector bet
arrived at by accident cannot be reasoned about; a declared constraint can.

A configurable cap, defaulting to 30% of the ranked book per GICS sector, is applied after
ranking by trimming the lowest-scoring names in the over-represented sector. The constraint
therefore costs the book its weakest expressions of the crowded view rather than reshuffling
the ranking. Every trim is logged with the ticker, sector, score, percentile, book size and the
cap it was measured against. Trimmed rows stay published with `SECTOR_CONCENTRATION_CAP` in
their reason codes, the same convention short-interest suppression already uses. A sector always
keeps at least one name, since on a small book a 30% cap is otherwise unsatisfiable and the trim
loop would empty it.

### 1.8 The reversal leg

Raw weekly reversal is a liquidity-provision return earned overnight (Nagel, NBER w17653, 2012),
while continuation over the same week is earned intraday and with the opposite sign (Lou, Polk &
Skouras, Journal of Financial Economics 2019). Only the residual component survives in modern
samples (Da, Liu & Schaumburg, Management Science 2014). It is also the only contrarian element
in a composite that is otherwise four-fifths continuation.

That is an argument for a measurement, not a deletion. Three variants run forward from
2026-09-01 and none is chosen on historical data:

- **A**, the frozen baseline, unchanged, reversal at 10%.
- **B**, reversal removed, its 10% redistributed proportionally across the four continuation
  legs. Proportional rather than equal, so removing one leg does not flatten the evidence
  ordering among the others as a side effect.
- **C**, reversal replaced with a residualized reversal at the same 10%: the prior-week return
  orthogonalized by one cross-sectional OLS against a constant, the row's own sector mean
  prior-week return, and the four continuation leg z-scores.

Variant C's regression drops regressors that do not vary across the cross-section. A leg that
resolved nowhere enters as a column of zeros and a single-sector universe makes the industry
return a constant; either is collinear with the intercept. Dropping them residualizes against
the controls that carry information rather than refusing to residualize at all.

---

## Part 2: the entry-timing overlay

`pipeline/overlay/entry_timing.py`. Defaults entirely off. It consumes the ranked composite and
returns `ENTER_NOW`, `DEFER` or `REJECT` per row with a reason.

**It is a gate, not a leg.** RSI and MACD do not enter the composite, do not influence rank, and
appear in no leg, subfactor, weight, evidence entry or config key in `swing_signals.py`. A test
asserts that, and asserts the dependency points one way.

**The toggles are mutually exclusive.** RSI, MACD and moving-average slope are all transforms of
the same recent price series. Reading a rising RSI and a turning MACD histogram as two
confirmations triple-counts one factor. `momentum_turn.mode` accepts exactly one value, there is
no additive mode, and the config loader raises on an attempt to build one. Testing both means
registering two variants, and both consume test budget.

**What each mode does.**

- **Trend gate.** EMA(close, 10) rising over 3 sessions and close above EMA(close, 20). An
  oversold reading inside a strongly bearish trend is a continuation signal, not a reversal
  signal, so every momentum mode is evaluated only on rows that pass here. The pass rate is
  logged on every run: a gate that passes everything is not filtering, and one that passes
  almost nothing has turned the overlay into a different strategy.
- **`rsi_change`.** RSI(14) rising over 3 sessions AND crossing upward through its own trailing
  60-session median. No RSI < 25, no RSI < 30, no fixed level of any kind is the trigger. There
  is no level parameter in the config to tune, because there is no level rule to tune it for.
  The reference point is a property of each series rather than a constant, and the trigger is an
  event rather than a state.
- **`macd_hist_slope`.** Histogram slope turning positive while the histogram is still negative,
  which precedes the signal-line crossover. The crossover is not implemented as a trigger. It is
  measured against the implemented one: every fired signal records `sessions_to_crossover`, so
  the claim that the crossover is later is a number rather than an assertion.
- **Volume gate.** RVOL over trailing 20-session mean dollar volume, threshold 1.5. The only
  overlay component with direct Tier-1 support at this horizon (Gervais, Kaniel & Mingelgrin,
  Journal of Finance 2001), which is why O-2 exists to test it without any momentum mode.

**DEFER semantics.** A row that passes the composite but fails the momentum turn is deferred for
up to 3 sessions, then rejected. Every deferral records what it would have returned had it been
entered immediately, and the result is reported as a distribution with deciles and the share of
deferrals where waiting helped. Never as a mean: a filter that improves outcomes by clipping a
few disasters and one that improves them by missing the right tail are different filters with
opposite implications, and a mean cannot tell them apart.

**The ablation.** O-0 through O-4, five cells, and that is the entire budget. A sixth raises the
multiple-testing correction applied to all five and makes every one of them harder to validate,
so adding one requires documenting what is being given up.

**The acceptance rule, written before any result exists.** Registered in the freeze file on
2026-08-12 with a timestamp. A variant is adopted only if it improves net-of-cost deflated
Sharpe over O-0 by at least 0.10 AND its improvement clears t > 3.0 (Harvey, Liu & Zhu, Review
of Financial Studies 29(1), 2016). Both conditions, not either. Otherwise the overlay stays off
permanently and the momentum-turn code is deleted rather than left dormant, because dormant code
is a standing invitation to re-run the comparison with one parameter moved, which is the
mechanism the whole registration exists to block.

The 0.10 margin was registered in advance and is deliberately not derived from any measurement
on this universe. It is the level below which the overlay's operational cost, in extra decisions
per refresh and in the deferral tracking it requires, is not worth carrying regardless of
statistical significance.

**One threshold flagged rather than chosen.** The task specified the acceptance rule as
"a margin registered in advance" without naming it. Choosing it by looking at any outcome would
be the exact error the registration prevents, so it was set on an operational-cost argument and
that argument is written into the freeze file beside the number. If the intended margin was
different, change it in the freeze file before 2026-09-01. After that date, changing it is
choosing a threshold with results in view.

### The statistical harness

- `pipeline/validation/deflated_sharpe.py`: deflated Sharpe ratio (Bailey and Lopez de Prado,
  Journal of Portfolio Management 40(5), 2014) with the non-normality correction from the
  series' own skew and kurtosis, and PBO by combinatorially symmetric cross-validation (Bailey,
  Borwein, Lopez de Prado and Zhu, Notices of the American Mathematical Society 61(5), 2014).
  A DSR computed without a trial return matrix labels its own variance assumption as optimistic
  rather than presenting an understated bar as a measured one.
- `pipeline/validation/labeling.py`: triple-barrier labels with upper and lower barriers at
  multiples of the name's own ATR and a vertical barrier at 10 sessions, inverse-overlap
  weights, and purged embargoed cross-validation. A path whose vertical barrier has not been
  reached returns None rather than a zero, because filling the most recent rows with
  vertical-barrier zeros is a forward-looking error. `overlap_inflation` reports the factor by
  which counting raw labels would have overstated the sample size.
- `pipeline/validation/hypothesis_log.py` and `hypothesis_log.jsonl`: append-only, timestamped,
  eight hypotheses registered on 2026-08-12. The trial count is read from the file, never
  recalled, because a remembered trial count only ever goes down and the variants that did not
  work are the easiest to forget. The freeze file's enumerated total rose from 35 to 43 and the
  DSR trial count from 40 to 48.

Implemented on the standard library. No scipy dependency was added.

---

## Part 3: documentation integrity

`pipeline/validate_documentation_claims.py`, wired into CI. It scans every generated report,
README and published artifact for six classes of claim this repository cannot support:
confirmed replication, survival of a data-snooping correction, matching published returns,
out-of-sample validation, a backtest proving something, and a proven track record. A match fails
the build unless a registered result file in `pipeline/validation/results/` declares that it
supports that specific claim.

Support is per claim rather than per file. One registered replication result does not license a
sentence about surviving a data-snooping correction, and a blanket "some results exist" check
would let it through.

A document quoting a claim in order to deny it is not making the claim, so denial markers in the
matched line and the two lines around it suppress the finding. The repository currently scans
clean across 93 files, and no registered result files exist, which is the correct state today.

---

## Measured effect on the published screen

Run on the live 860-name cross-section, comparing against the `swing.json` committed
2026-08-11. The published artifact was not overwritten. Measured after the Form 8-K Item 2.02
store was collected, which matters: an earlier version of this section was measured with the
store absent and reported a 28.1% book churn. That figure described a screen whose drift leg
was dark, not the effect of the amendments, and it is corrected here.

| Comparison | Book churn | Top 10 kept | Median rank move |
|---|---|---|---|
| All eight amendments, store present | **1.9%** | 10/10 | 7 places |
| Drift leg dark against drift leg live | 28.1% | 4/10 | 43 places |

**All eight amendments together move the screen by about two percent.** Same top ten in the
same order, one name into the traded book and one out, median rank move of seven places across
the published three hundred. The second row is not a property of the amendments; it is the cost
of publishing before the release store exists, and it is why the deployment note below matters.

The amendments measured as close to inert on this cross-section, which is worth stating plainly
because it is the less flattering answer.

- **The re-anchoring moves the median drift window by about one day, not by several.** Across
  the 298 published rows carrying both dates, the 10-Q lagged the earnings release by a median
  of 0 to 1 calendar days and a 75th percentile of 2. Most issuers release after the close and
  file the periodic report the next morning: Amazon released its June quarter at 20:06 on
  2026-07-30 and filed the 10-Q on 07-31. The mean lag is 3.6 days because the distribution has
  a real tail, with 24% of rows at three days or more and 21% at seven or more, running out to
  40. So the defect was real and it was smaller in the median than the amendment's rationale
  implied. It costs 1.9 points of leg coverage, 84.7% to 83.1%, which is 9 rows with no
  resolvable release and a handful more whose windows correctly read as closed once dated from
  the release rather than the filing.
- **Renormalization changed the top decile by exactly nothing.** Same 82 names, same size,
  liquidity and volatility distributions. The reason is in the coverage histogram: 698 of 860
  rows resolve all five legs and 159 resolve four, so the renormalization factor is nearly
  constant across rows and the transform is close to a monotone rescale. The undeclared size
  and liquidity tilt the amendment targets is real as a mechanism and is not binding on this
  universe today. The fix stays, as a guard against the coverage dispersion a thinner release
  store would create, but it is currently prophylactic.
- **The legs-resolved floor** excludes zero rows with the store present.
- **The sector cap** made zero trims. The largest sector holds 18 of 82 and the cap allows 24.
  The 3.4x Energy tilt recorded as an open question shows here as Energy at 12 of 82, or 15%.

The cost model is the change that most affects a decision. Removing the participation clamp
raised every quoted round trip, and most at the top: the $1B book went from 100.3 to 128.7 bps
per position, understated by 28%. The 50 bps ceiling still first breaches at a $250M book, but
the participation cap now rejects 5 of 82 positions there and 45 of 82 at $1B, so the old $1B
figure was an average over positions half of which could not be put on. Curve consistency
passes at 1.2% maximum deviation.

## Deployment note: the drift leg is dark until the release store is collected

**Status: collected 2026-08-12.** The store holds 33,103 Item 2.02 records covering 851 of the
860 universe companies, a median of 41 releases each, and `pead_drift` coverage is 83.1%. The
anchor is a minute-accurate EDGAR acceptance timestamp on 298 of the 300 published rows.

The rest of this note stands as the operating rule, because the failure mode recurs on any
fresh clone or any universe expansion.

Without `pipeline/data/pit/earnings_releases.jsonl`, `pead_drift` coverage is 0.0%: every row
with a resolvable surprise reports `RELEASE_DATE_UNRESOLVED`, and the composite silently
becomes a four-leg model with weights renormalized to .357 / .286 / .214 / .143. That state
moves the traded book by 28% against the same screen with the leg live, so it is not a
cosmetic difference.

`.github/workflows/collect-earnings-releases.yml` builds the store from Form 8-K Item 2.02 by
way of the EDGAR submissions API, weekly and on demand, scoped to the configured universe of
860 companies rather than the eight thousand filers in the SEC ticker map. It requires the
`SEC_USER_AGENT` secret the point-in-time backfill already uses, and commits the store back to
main because scheduled runs happen on ephemeral runners.

Run it before publishing a screen, or the published file is a different model from the
registered one. The job reports company coverage before and after, and states on every run that
company coverage is not leg coverage: a company with releases on disk still needs its most
recent fiscal period to have one inside the lag band before the leg scores it, which the screen
build reports as `pead_anchor_diagnostic`.

What the job buys is a working, correctly dated leg. It is not evidence that the screen
predicts anything, and it does not move the prospective clock.

## Files added

```
pipeline/earnings_release.py                        release-datetime store, Form 8-K Item 2.02
pipeline/collect_earnings_releases.py               builds that store from the EDGAR submissions API
pipeline/overlay/__init__.py
pipeline/overlay/entry_timing.py                    the overlay
pipeline/overlay/ablation.py                        O-0..O-4 and the acceptance rule
pipeline/config/entry_timing_overlay.yaml           config, defaults entirely off
pipeline/validation/deflated_sharpe.py              DSR, PBO, the HLZ hurdle
pipeline/validation/labeling.py                     triple barrier, overlap weights, purged CV
pipeline/validation/hypothesis_log.py               append-only trial register
pipeline/validation/hypothesis_log.jsonl            the eight registered hypotheses
pipeline/validation/register_swing_v2_hypotheses.py one-shot registration, idempotent
pipeline/validate_documentation_claims.py           the CI gate
pipeline/diagnostics/__init__.py
pipeline/diagnostics/renormalization_shift.py       the 1.4 before/after diagnostic
.github/workflows/collect-earnings-releases.yml     weekly release-store collection
```

## Files changed

```
pipeline/swing_signals.py                 renormalization, floor, variants, sector cap, diagnostics
pipeline/build_swing_screen.py            new published fields, release anchor, 20-day ADV
pipeline/edgar_sue.py                     release anchor, published drift term
pipeline/costs.py                         participation cap, clamp removed, caveats on every estimate
pipeline/validation/harness_freeze.json   amendments, variants, overlay, acceptance rule
.github/workflows/ci.yml                  documentation integrity gate
```

## Published output: what a consumer has to change

| Was | Is |
|---|---|
| `composite_z_renormalized` | `composite_z_zero_filled` (the meaning inverted, so the name had to) |
| `cost_model.by_portfolio_size` | `cost_model.by_book_dollar_value` |
| `...portfolio_value` | `...book_dollar_value` |
| `...median_round_trip_bps` | `...median_position_round_trip_bps` |
| `median_position_capacity_at_2pct_adv` | `median_position_capacity_at_participation_cap` |
| `pead_source.announcement_anchor: sec_filing_date` | `earnings_release_datetime_8k_item_202` |

`legs.<leg>.weight` is unchanged and still carries the declared weight, so existing readers keep
working. `legs.<leg>.effective_weight` is new and carries what the leg was actually worth on that
row after renormalization. New top-level keys: `legs_resolved`, `pead_anchor_diagnostic`,
`sector_concentration`, `registered_variants`, `published_variant`. New per-row keys:
`legs_resolved`, `legs_declared`, `sector_capped`, `sector_trim`.

## What was not done, and why

- **No thresholds were chosen by looking at outcomes.** Every default here is either carried
  over unchanged, taken from a cited paper, or set on a stated operational argument. The one
  number the task left open, the acceptance margin, is flagged above.
- **No results are reported for any variant.** The clock starts 2026-09-01.
  `overlay/ablation.py` returns `status: awaiting_prospective_data` and will not adopt anything
  until it has periods to read.
- **The overlay is off.** Enabling it requires a registered variant id present in the freeze
  file, and the loader raises otherwise.

## Verification

`PYTHONPATH=pipeline python -m pytest pipeline/tests -q`: 1828 passed, plus 281 subtests. That
includes 29 overlay tests, 28 statistical-harness tests, 10 ablation tests, 12
documentation-gate tests, 5 decay-constant tests and 3 renormalization-diagnostic tests, all
new. `npm test`: 529 passed across 63 files. `npm run lint`, `python -m compileall pipeline`,
`pipeline/check_ui_weights.py`, `pipeline/validate_data.py` and
`pipeline/validate_documentation_claims.py` all clean.
