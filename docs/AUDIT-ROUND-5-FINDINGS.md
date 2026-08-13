# Audit Round 5: The As-Filed Spine, the Unbundled Fix, and the Clock

Every number is scoped to these pins unless a row states otherwise.

| Pin | Value |
|---|---|
| Pit refresh id | `advisor-2026-08-10T17:22:04.440901+00:00` (sha256 `54f86b3e9bf861a4...`) |
| Price cache tree | `9b41dfbfef494699...` (860 tickers, unchanged from Round 4) |
| EDGAR PIT store | 1,448,995 facts pre-ingest, `pipeline/data/pit/fundamentals`, plus the Round 5 retained-earnings ingest recorded below |
| settings.json | `d18a100f0b7ef91f...` (post-Round-4 remediation state) |
| scorer.py / advisor_engine.py | `43dd37eba0718dd9...` / `8dde7bf5ccdb8ebf...` |
| Factor files | ff5 `cbc3724812132654...`, momentum `f405ee2d47a5c75c...`, vintage 2026-06 |
| Harness freeze | `pipeline/validation/harness_freeze.json`, freeze hash `f0b649bf9e642d9a...` |
| Noise standard | one rule for every comparison: a CAGR difference is noise unless the paired monthly difference clears 2 SE (Task 6.5) |

Backtest artifacts carry embedded experiment manifests. Producers are committed under
`research/audit/round5/`.

---

## 1. Task 1: the as-filed backtest

Producers: `asfiled_backtest.py`, `task1_analysis.py`,
`pipeline/tests/test_asfiled_backtest.py`, `ingest_retained_earnings.py`.

### What was built

`build_snapshot_asfiled` replaces the restated-Yahoo statement reconstruction inside the
monthly backtest with EDGAR facts visible on each signal date. Visibility is the real
filing date, not the approximated 75-day lag the restated path assumes: AAPL's FY2021
10-K (filed 2021-10-29) is visible to the 2021-10-29 signal and its FY2024 10-K (filed
2024-11-01) is invisible to the 2024-10-31 signal. Amendments become visible on their own
filing date and never rewrite the earlier view. Both properties are asserted in
`test_asfiled_backtest.py` (five tests), not just in prose. Shares outstanding come from
as-filed diluted share counts, market cap from those shares times the cache price.

### The delta table, and why it cannot yet be read as the restatement-bias measurement

| | Restated (Round 4 baseline) | As-filed | Delta |
|---|---|---|---|
| CAGR | 12.59% | 19.70% | +7.11pp |
| Volatility | 17.5% | 20.5% | +3.0pp |
| Max drawdown | -19.0% | -27.8% | -8.8pp |
| Mean monthly turnover | 50.6% | 22.2% | -28.4pp |
| Six-factor alpha (HAC6, arithmetic, n=58) | +0.43%/yr (t 0.09) | +9.09%/yr (t 1.93) | +8.66pp |
| RMW loading | +0.22 (t 1.1) | +0.40 (t 2.5) | |
| Picks changed per rebalance | | | **93%** |

Paired noise test on the headline: +7.13pp against a 2 SE threshold of 12.99pp (n 59).
**The CAGR delta is inside noise**, and the alpha t of 1.93 sits below 2. The as-filed
fundamentals-only variant shows the same shape: alpha +7.90%/yr (t 1.87), RMW +0.52
(t 3.8), MOM -0.23.

Four confounds prevent reading the delta as restatement bias, and one of them is a new
measured defect:

1. **Tag-fallthrough ingest defect (new, fixed this round).** `observations_for_concept`
   (edgar_facts.py) returned on the first XBRL tag with any rows. A filer that moved to
   the ASC 606 revenue tag in 2018 lost its entire pre-2018 revenue history under the
   legacy tags. Measured consequence in the coverage-by-year table below: revenue visible
   for 1% of names in 2011 and 10% in 2014 despite the legacy tags being declared. The
   fix (union across tags, priority order preserved for conflicts, regression test
   `test_tag_union_preserves_legacy_history`) is committed, but the store was built by
   the old code, so the current as-filed run scores thinned income data in its early
   years. A re-ingest against SEC companyfacts repopulates the store. The code is fixed and
   the data job is queued.
2. **Annual cadence.** The as-filed path scores 10-K annual statements. The restated
   path scores TTM aggregates of quarterly frames. Half the turnover drop (50.6% to
   22.2%) plausibly comes from fundamentals updating yearly instead of quarterly.
3. **Universe composition.** 859 of 860 cache tickers map to CIKs, 807 have EDGAR annual
   revenue facts today, fewer in early years. IFRS filers are thinly covered because the
   ingest is us-gaap-first.
4. **The noise standard.** The paired threshold for portfolios this different is 13pp.
   One five-year window cannot certify a 7pp difference between 93%-different books.

### As-filed coverage by year (share of 859 mapped names, visible each Jan 1)

| Year | revenue | net income | op income | assets | equity | OCF | capex | D&A | retained earnings |
|---|---|---|---|---|---|---|---|---|---|
| 2011 | 0.01 | 0.09 | 0.08 | 0.59 | 0.52 | 0.10 | 0.09 | 0.05 | pre-ingest 0.00 |
| 2014 | 0.10 | 0.72 | 0.59 | 0.80 | 0.76 | 0.73 | 0.63 | 0.55 | pre-ingest 0.00 |
| 2017 | 0.11 | 0.81 | 0.68 | 0.87 | 0.85 | 0.79 | 0.73 | 0.67 | pre-ingest 0.00 |
| 2020 | 0.71 | 0.89 | 0.74 | 0.93 | 0.91 | 0.90 | 0.81 | 0.75 | pre-ingest 0.00 |
| 2023 | 0.88 | 0.95 | 0.80 | 0.98 | 0.97 | 0.97 | 0.88 | 0.84 | pre-ingest 0.00 |
| 2026 | 0.94 | 0.98 | 0.83 | 1.00 | 0.99 | 0.99 | 0.90 | 0.88 | pre-ingest 0.00 |

The revenue column is the tag-fallthrough defect made visible. The balance columns
(assets, equity) are the true tagging-era baseline: even they run 0.59 and 0.52 in 2011,
so a backtest into 2010-2014 will score fewer metrics in early years regardless, and the
findings treat 2021-2026 as the usable as-filed window until the re-ingest closes the
income gap. The retained-earnings ingest ran this round
(`ingest_retained_earnings.py`, RetainedEarningsAccumulatedDeficit for every mapped CIK
through the same idempotent amendment-preserving store path). Its achieved coverage is
recorded in the committed ingest log and unblocks Altman Z from its 66% cap on the next
scoring pass.

### Survivorship, stated plainly

This run removes the restatement bias and keeps the survivorship bias. The 860 CIKs are
today's universe. Names that delisted between 2021 and 2026 never enter, and their
absence inflates every return figure above by an unmeasured amount. Removing it requires
three things: a dated universe-membership series (the pit universe log started 2026-08,
history must come from an index-membership vendor or reconstructed 13F/index files), the
EDGAR filings of deregistered issuers (EDGAR retains them, the entity map must stop
filtering to current tickers), and delisting-return treatment per Shumway (Journal of
Finance 52(1), 1997) with the -30% imputation for performance-related delistings. Until
then every backtest in this repository, as-filed or restated, is a statement about
companies that survived to 2026.

### Verdict

The as-filed infrastructure is production-grade: point-in-time pure by test, real filing
dates, manifest-pinned. The restatement-bias measurement itself remains open until the
tag-union re-ingest completes. The honest headline is not "as-filed adds 7pp" but
"as-filed changes 93% of picks, and the restated backtest was therefore measuring a
different portfolio than the one an as-filed investor could have held."

---

## 2. Task 2: the defect fix, unbundled

Producer: `task2_multiplier_removal.py`. Implementation:
`advisor_engine.py::multiplier_removal_variant`, published per row under
`score_variants.multiplier_removal`.

Measured on the identical EDGAR-augmented snapshot (n 875, mean coverage 0.82):

| Variant | Spearman(coverage, score) | Financials vs rest |
|---|---|---|
| Production (bands, both multipliers) | +0.514 (p 3e-60) | +2.8 (p 0.032) |
| **Multiplier removal alone (renormalization intact)** | **+0.247 (p 1e-13)** | **+7.9 (p <0.001)** |
| Fixed-feature (imputation, no multipliers) | +0.195 (p 6e-9) | +0.3 (p 0.64, from Round 4 measurement +0.3/+0.2) |

Rank effect of the removal alone: correlation 0.937 to production, mean absolute shift
62.5 ranks, 416 names move more than 50.

The unbundling worked, and it also complicated the brief's premise. The multipliers
carry roughly half the coverage bias (+0.514 to +0.247). The remainder is the
within-block renormalization. And the removal **unmasks** a defect the multipliers were
partially hiding: financials, whose suppressed metrics leave the weight denominator,
renormalize onto fewer, systematically friendlier metrics, and without the completeness
multiplier dragging them down their gap versus the rest of the universe widens from +2.8
to +7.9 points.

### Promotion recommendation

Promote the multiplier removal to champion, now, on defect grounds, with the financials
side effect disclosed and bounded, for three reasons:

1. It is a bug by the standard the dispute already accepted. No published construction
   multiplies a positively-oriented composite by completeness (Jensen, Kelly, and
   Pedersen, Journal of Finance 78(5), 2023. Freyberger, Hoeppner, Neuhierl, and Weber,
   Review of Financial Studies 38(3), 2025. Bryzgalova, Lerner, Lettau, and Pelger,
   Review of Financial Studies 38(3), 2025. Chen and McCoy, Journal of Financial
   Economics 153, 2024).
2. The cost of not promoting is two more years of a champion that ranks thin-coverage
   names down by construction: coverage-score correlation +0.51, identical evidence
   scoring up to 1.87x apart, every published stance and screen inheriting it, while the
   correct number sits in a shadow column.
3. The clock (Task 5) makes now the cheapest possible moment: zero prospective periods
   have accrued, so promotion costs nothing. Promoting in month 13 costs 13 months.

The financials unmasking does not reverse the recommendation, because the +7.9 gap is
the renormalization defect becoming visible, not a new distortion the removal created.
Its fix is the imputation construction, which stays behind the 24-period harness where
it belongs. Interim mitigation if the gap is operationally unacceptable: the publication
gate already withholds sub-floor names, and the sector-valuation modifier is
sector-relative, so the gap does not compound within sector-ranked screens.

The champion remains unchanged in this commit. The freeze file records the
recommendation and its clock arithmetic as a pending decision, because promoting a
champion is an ownership call, not an auditor's.

---

## 3. Task 3: technical sleeve ablation, on the as-filed spine

Producer: `asfiled_backtest.py` variants plus `task3_ablation_analysis.py`.

All eleven variants run on the as-filed spine, identical cache and calendar, manifests
embedded. Paired dCAGR is the noise-standard test against the as-filed base (2 SE
threshold beside it).

| Variant | TO/mo | dTO | CAGR | Max DD | CMA (t) | MOM (t) | paired dCAGR / 2SE |
|---|---|---|---|---|---|---|---|
| As-filed full sleeve (base) | 22.2% | | 19.70% | -27.8% | +0.08 (0.5) | -0.04 (-0.3) | |
| drop momentum_12_1 | 21.5% | -0.7 | 15.20% | -30.5% | +0.02 (0.1) | -0.14 (-1.1) | **-3.86 / 3.31 SIGNAL** |
| drop risk_adjusted | 22.7% | +0.5 | 20.14% | -26.6% | +0.04 (0.2) | -0.01 (-0.1) | +0.27 / 1.54 noise |
| drop relative_strength | 22.2% | 0.0 | 19.70% | -27.8% | identical | identical | byte-identical no-op |
| drop drawdown_resilience | 23.0% | +0.8 | 20.27% | -26.6% | +0.08 (0.5) | -0.08 (-0.7) | +0.50 / 1.42 noise |
| drop volume_confirmation | 22.2% | -0.0 | 20.04% | -26.1% | +0.04 (0.3) | -0.03 (-0.3) | +0.24 / 1.16 noise |
| drop low_beta | 22.9% | +0.7 | 20.09% | -25.5% | +0.10 (0.6) | -0.06 (-0.5) | +0.43 / 1.59 noise |
| drop technical_extended | 22.9% | +0.7 | 20.26% | -26.5% | +0.04 (0.3) | -0.04 (-0.4) | +0.45 / 1.04 noise |
| drop RS + volume (fast pair) | 22.2% | -0.0 | 20.04% | -26.1% | +0.04 (0.3) | -0.03 (-0.3) | +0.24 / 1.16 noise |
| relative_strength slowed to 63d | 22.2% | 0.0 | 19.70% | -27.8% | identical | identical | byte-identical no-op |
| Fundamentals only | 18.4% | -3.8 | 17.91% | -29.2% | -0.01 (-0.0) | -0.23 (-1.8) | -1.71 / 5.60 noise |

Five findings, three of them revisions to earlier rounds:

1. **The relative-strength signal was never in the effective champion.** The drop and
   the slowed variant are byte-identical to base because production
   `short_horizon_treatment` is `neutral` (settings.json), which removes
   `relative_strength` and renormalizes. The methodology doc claimed `legacy_momentum`
   in production. Corrected this round. The brief's fast-signal hypothesis is moot for
   RS and measured for volume: dropping volume_confirmation changes turnover by -0.0pp.
   The daily-updating signals contribute no measurable turnover on this spine.
2. **momentum_12_1 is the only sub-signal that survives the noise standard, in any
   direction, in any round.** Removing it costs -3.86pp paired CAGR against a 3.31
   threshold, worsens drawdown by 2.7pp, and saves only 0.7pp of turnover. It is the
   sleeve's entire measurable value.
3. **The +37.1pp technical-turnover attribution does not transfer to the as-filed
   spine.** Full sleeve versus fundamentals-only here: +3.8pp monthly turnover, not
   +37pp. The restated spine's technical churn was substantially an interaction with
   statement-availability flicker (the mechanism `docs/ALGORITHM-RESEARCH-RESULTS.md`
   section 4 measured at 96.7% of score-change events), which stable as-filed facts
   eliminate. Round 3 and 4's sleeve-cost numbers were real measurements of the
   restated system, and the restated system's churn was mostly a data artifact, not a
   signal property.
4. **The drawdown-protection trade re-prices to almost nothing.** On the restated spine
   the sleeve bought 7.7pp of drawdown for 38pp of turnover. On the as-filed spine it
   buys 1.4pp (-27.8 vs -29.2) for 3.8pp of turnover and -1.79pp of paired CAGR
   (inside noise). Priced per point of drawdown protection: 2.7pp turnover and 1.3pp
   CAGR per point, and the point estimate of the CAGR cost exceeds the protection. The
   drawdown_resilience signal itself makes realized drawdown slightly worse when
   present (-27.8 base vs -26.6 without it).
5. **The redesign candidate writes itself, and stays a challenger.** Every sub-signal
   except momentum_12_1 is removable within noise on this spine. The natural challenger
   is a sleeve of momentum_12_1 alone (or momentum plus low_beta for its 2.3pp
   drawdown improvement, the largest DD gain of any drop). Defining it is free.
   Promoting it takes the harness, because this table is one five-year window on a
   survivorship-biased universe with tag-thinned early years.

---

## 4. Task 4: portfolio construction

Producers: `asfiled_backtest.py asfiled_stack`, `task4_capacity.py`.

### The specified default stack

Selection criteria for the buffer, stated first: minimize turnover subject to (a) paired
CAGR difference inside the noise standard, and (b) max drawdown within 1pp of baseline.
On the pinned restated sweep, k=2.0 fails (b) marginally (-19.8 vs -19.0) and k=1.25
leaves 11pp of turnover on the table against 1.5. **Default: rank buffer k=1.5** (hold
while rank <= 30 for a top-20 book). On the as-filed spine the stack (buffer 1.5)
produced turnover 12.3% monthly against the unbuffered 22.2%, CAGR 20.70% vs 19.70%
(paired difference inside noise), drawdown -25.7% vs -27.8%, modeled cost $1,243 vs
$2,049.

Position rules adopted with it, from thresholds that already exist in config: maximum
single-name weight 8%, maximum sector weight 30%, minimum liquidity $5M median daily
dollar volume with the $25M threshold marking reduced-size eligibility
(settings.json modifiers.liquidity). These are risk constraints, not alpha claims, and
the momentum screen's eligibility gates already enforce the liquidity floor upstream.

### Capacity, measured through the repo's own impact model and the canonical law

Annualized modeled cost for the as-filed stack book (one-day execution, both legs):

| AUM | Repo base scenario | Repo stress | Canonical square-root law |
|---|---|---|---|
| $10M | 4 bps/yr | 6 | 45 |
| $50M | 5 | 9 | 98 |
| $100M | 6 | 12 | 137 |
| $500M | 10 | 22 | 296 |
| $2B | 14 | 33 | 471 |

The repo's impact coefficient (15, stress 40) implies 4.5bps at 100% ADV participation.
The canonical square-root law (impact of order daily volatility times the square root of
participation, the form the execution literature and Frazzini, Israel, and Moskowitz's
live-trade evidence support) implies roughly 630 in the same units, 15 to 40 times the
repo's setting. **Under the canonical law the strategy carries roughly $13M at a
50bps/yr impact budget, $50M at 100bps, and $200M at 200bps.** Under the repo's own
model it never crosses 50bps below $5B, which is a statement about the coefficient, not
about capacity. The cost-model defect is therefore quantified: the labeled proxy is not
just unfitted, it is more than an order of magnitude below the literature's floor at
scale. A measured spread model remains blocked: no provider in the stack serves quoted
or effective spreads, and the cache stores closes only, so Corwin-Schultz high-low
estimation (Journal of Finance 67(2), 2012) is also unavailable until OHLC is cached.

---

## 5. Task 5: the clock

Committed: `pipeline/validation/harness_freeze.json`, freeze hash `f0b649bf9e642d9a...`.

| Commitment | Value |
|---|---|
| Champion frozen | production bands champion at the pinned hashes above |
| Challenger set | fixed_feature, multiplier_removal, signal_corrections_cumulative, rank-buffer-1.5 portfolio layer |
| Harness start | 2026-09-01 (first full monthly period after the freeze) |
| Expected completion at monthly frequency | **2028-09-01** |
| Clock resets on | any change to champion score semantics |
| Clock survives | provider fixes proven score-identical by regression test, new challengers, UI, publication gates |
| Trial count | 35 enumerated variants across five rounds (5 R3 backtests, 3 R4, 12 R5, 4 pre-R3 turnover controls, 7 scoring variants, 4 regression constructions), DSR computed at N=40 |
| Promotion | 24 periods, mean IC > 0, ICIR >= 0.5, IC t >= 2.4, net-of-cost quintile spread > 0 under the canonical impact law, deflated Sharpe >= 0.95 at N=40 (Bailey and Lopez de Prado, Journal of Portfolio Management 40(5), 2014), PBO <= 0.50 |
| Real money | all of the above plus 12 further periods (36 total) with ICIR >= 0.3 and net six-factor alpha t >= 2 |
| Abandonment | at 24 periods, ICIR <= 0 or net spread <= 0 abandons the residual-alpha claim and repositions the product as descriptive analytics. Gray zone 0 < ICIR < 0.2 buys one 12-month extension, once |

The multiplier-removal promotion decision interacts with the clock as recorded in the
freeze file: deciding before 2026-09-01 costs zero accrued periods.

---

## 6. Task 6: loose ends

**6.1 Residual correlation mechanism: the dilution hypothesis is confirmed, Round 4's
attribution was wrong.** On complete-case names (imputed weight <= 0.02, n 180),
Spearman(coverage, fixed-feature score) is +0.038 (p 0.62): the residual vanishes when
nothing is imputed. Across all names, imputed weight correlates -0.143 (p 2e-5) with
distance from neutral. The +0.19 residual is imputation pulling thin names toward 50, an
implicit shrinkage, not coverage co-varying with characteristics as Round 4 claimed.
Characterization: the fixed-feature score embeds shrinkage with strength equal to the
imputed weight fraction. This is a defensible Bayesian property, now a documented one
rather than an accident, and the published `imputed_weight_fraction` field is its exact
per-name strength.

**6.2 Characteristic battery, re-run at restored coverage.** Producer:
`task2_multiplier_removal.py` and `task6_final_battery.py`. Round 4's battery ran on the
coverage-selected cohort and its value tilt does not survive. Rebuilt final score,
EDGAR-augmented snapshot (n 626 to 875):

| Characteristic | Round 4 (degraded snapshot) | Round 5 (restored) |
|---|---|---|
| log market cap | +0.013 (n 876) | +0.037 (n 875) |
| book-to-market | +0.152 (n 830) | **+0.029 (n 828), tilt withdrawn** |
| gross profits/assets | +0.152 (n 400) | **+0.276 (n 626)** |
| profit margin | +0.270 (n 874) | +0.273 (n 874) |
| asset growth | -0.030 (n 488) | -0.015 (n 871) |
| prior 12-1 return | +0.253 (n 859) | +0.118 (n 859) |

The score at full coverage is a profitability tilt with modest momentum. The value tilt
Round 4 promoted to a primary diagnostic was a coverage-selection artifact. The
fundamentals-only sleeve at full coverage: GP/A +0.414 (n 626), momentum -0.180, B/M
-0.096, so even the mild final-score momentum tilt comes from the technical sleeve, not
the fundamentals.

**6.3 The +1.97pp construction bucket, decomposed.** Producer:
`task6_bridge_decomposition.py`. On sample-aligned months (58): the bucket is +1.61pp,
of which explicit recorded transaction costs are +0.78pp (matching the 78bps/yr the cost
model predicted) and the joint remainder is +0.83pp (cash drag, value-path compounding,
and price-cache drift on the re-pricing side). The missing-price candidate is cleared
for the committed artifact: it records **zero** missing-holding-price days. The 12 days
Rounds 3 and 4 cited belong to the 2026-08-10 rerun, a record-keeping error now
corrected. Separating cash drag from compounding from price drift requires the
2026-08-03 price cache, which was overwritten in place. That decomposition is
permanently closed to measurement, which is itself the experiment-manifest argument.

**6.4 n=58 vs n=59: explained and fixed.** The locked-picks series includes 2021-09,
which the value-series construction consumes as its pct_change seed. Aligning to the
same 58 months moves step C from -0.63% to -0.99% and step D's bridge arithmetic by the
same amount. The corrected aligned bridge: -2.60 (net value path) to -0.99 (gross
locked) is +1.61pp construction, and -0.99 to +0.43 cache state becomes +1.42pp on
aligned samples.

**6.5 One noise standard, applied to everything.** Producer:
`task6_noise_standard.py`. Rule: paired monthly return difference against baseline,
threshold 2 SE, annualized. Results: cross-sectional -0.75pp (threshold 2.94, noise),
buffer 1.25 +0.30 (1.94, noise), buffer 1.5 +0.16 (2.70, noise), buffer 2.0 -0.32
(3.48, noise), growth-zeroed +0.12 (1.15, noise), fundamentals-only +1.80 (13.38,
noise), as-filed vs restated +7.13 (12.99, noise). Round 4 treated cross-sectional's
1.0pp CAGR gap as decision-relevant. Under the uniform standard it is noise, and that
sentence in Round 4 section 4 is corrected. No CAGR difference measured in any round of
this dispute clears the paired standard. Turnover differences are deterministic
quantities and remain the decision axis.

**6.6 Model card.** `docs/MASTER-METHODOLOGY.md` section 9 now carries the
ranking-integrity disclosure: enrichment alone reordered the published board at rank
correlation 0.820, mean shift 114 ranks, and every ranking published between 2026-08-06
and the recovery was substantially a map of data availability.

---

## 7. Investment-tool grade

**What the product can honestly claim today.** A transparent, reproducibility-pinned
research process. A champion whose defects are measured, published, and carried in
shadow columns next to their fixes. A point-in-time data spine with tested visibility
rules. A portfolio layer with a specified default and a capacity estimate under a
literature-grade cost law. A frozen prospective protocol with numeric promotion and
abandonment criteria that start accruing 2026-09-01.

**What it cannot claim.** Any expected return. The only positive alpha estimate in five
rounds (+9.09%, t 1.93) sits on a tag-thinned early sample, inside its own noise
threshold, in a survivorship-biased universe. Zero prospective periods have elapsed. The
live champion still multiplies scores by completeness. The cost model understates impact
by an order of magnitude at scale.

**Grade: D+ as an investment tool, up from D.** The plus is earned by exactly three
things: the champion's largest defect now has a promotable fix with a stated cost of
delay, the numbers the product would need to become investable are now written down in
advance with hashes, and the as-filed spine means the next backtest argument will be
about evidence rather than data vintage. The strongest counter says the grade should
stay D because nothing a user sees today has changed and no forward evidence exists. That
counter is right about the product surface and wrong about the distance: in Round 1 the
path to investability was unmeasurable, and today it is a checklist with dates. A grade
above C- requires the first 24 prospective periods to exist and the champion to carry no
known directional bias. Both have dates attached. Research-artifact grade: A- holds, with
the Round 4 battery correction (6.2) and the Round 4 residual-attribution correction
(6.1) logged against it.
