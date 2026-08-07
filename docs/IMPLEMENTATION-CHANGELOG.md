# Implementation Changelog

Changes made during the research-driven algorithm overhaul. Evidence and reasoning live in
`docs/ALGORITHM-RESEARCH-RESULTS.md`; this is the what-and-where.

Baseline at start: 652 Python tests, 337 frontend tests, 9 data contracts.
At completion, merged with `main` (which landed PR #46's overlapping work first):
**820 Python tests, 373 frontend tests**, 9 data contracts, lint and build clean.

**Overlap with PR #46.** That branch solved several of the same problems and merged first.
Where the two converged this branch takes `main`'s implementation and drops its own: the
trading calendar, the sector-residual/session target, purge/embargo, unseeded enrichment mode,
the news-availability fix, the experiment registry, `cost_sensitivity.py`, `enrichment_bias.py`,
and `news_fix_impact.py` (which supersedes this branch's `news_weight_impact.py` -- it also
recomputes stance, finding 5 stance changes this branch's narrower version missed).

---

## Behaviour changes to the production champion

All defect fixes rather than model changes. No new signal was promoted. The news fix and the
target correction came from `main`; the availability channel is this branch's.

| Change | File | Effect |
|---|---|---|
| Unavailable news leaves the denominator instead of filling it with 50.0 | `news_intelligence.py` | Published scores move **+1.005 mean, +1.40 max**; 10 of 40 names change rank position. Names below 50 move down |
| Dark-provider modifiers snapshot as unavailable, not neutral 0.0 | `validation/ic_harness.py`, `fetch_advisor.py` | Immutable PIT records no longer grade an unreachable SEC layer as reviewed evidence |
| IC harness measures the contract's target | `validation/ic_harness.py`, `config/settings.json` | 63 **trading sessions**, sector-residual; every IC statistic changes meaning |

---

## New modules this branch contributes

| Module | Purpose |
|---|---|
| `portfolio_construction.py` | Four turnover-control challengers: rank buffer, minimum holding, score smoothing, replacement margin |
| `strategy_diagnostics.py` | Expectancy, profit factor, payoff, R-multiples, streaks, Sortino/Calmar, rolling Sharpe, regime attribution |
| `benchmark_suite.py` | Per-benchmark Newey-West regression of the strategy on each of 14 tradeable ETFs |
| `score_calibration.py` | Score-bucket outcome table behind an observation gate |
| `build_research_evidence.py` | Aggregates the reports into one UI artifact |
| `src/components/ResearchEvidence.jsx` | Seven panels on `/screens/validation` |

## Adopted from `main` (PR #46), not from this branch

Both branches built these independently. `main` merged first, so its implementation stands and
this branch's equivalents were discarded rather than merged on top.

`validation/trading_calendar.py` · `validation/ic_harness.py`'s session/sector-residual target ·
`validation_framework.py` purge/embargo · `evaluation.py` purge · `experiment_registry.py` ·
`cost_sensitivity.py` · `enrichment_bias.py` · `news_intelligence.py`'s availability fix ·
`fetch_advisor.py`'s `FULL_UNIVERSE_RESEARCH` · `config/settings.json` horizon config ·
`news_fix_impact.py`

Where `main`'s version is better it is worth naming: its harness keeps the calendar-day raw-return
path as a *labelled diagnostic* beside the new primary target rather than replacing it, and its
`news_fix_impact.py` also recomputes stance (finding 5 stance changes this branch's version did
not look for).

## Extended on top of `main`

| File | Addition |
|---|---|
| `validation/ic_harness.py` | `unavailable_modifiers()` + `modifiers.availability`; `research_trial_count()` sourcing deflation from the registry |
| `experiment_registry.py` | `total_variants_tested()` accessor; 5 experiments from this branch |
| `fetch_advisor.py` | `source_status` passed into the PIT snapshot |
| `backtest_monthly.py` | `--rank-buffer`, `--min-holding-months`, `--score-smoothing`, `--replacement-margin`, all defaulting off |
| `confidence.py` | `historical_calibration_component`; explicit "not a probability" interpretation |
| `p0_q1_benchmark_factor_report.py` | Loaders and OLS reused by `benchmark_suite.py` |
| `src/components/AnalysisLayers.jsx` | "Confidence" → "Evidence confidence" |

Deliberately **not** rebuilt: Deflated Sharpe, PBO, walk-forward, bootstrap, feature registry,
model manifests, the cost model, champion/challenger. All existed and were correct.

---

## Bugs found and fixed

1. **Silently-defaulted t-statistic.** `benchmark_suite` read the alpha t under a key
   `ols_newey_west` does not emit; the `.get()` default published `0.00` for all 14 benchmarks —
   which reads as a confident null result. Caught because every value was *exactly* zero.
2. **Gate/consumer disagreement in calibration.** Publishability was gated on adaptive quintiles
   while `confidence.py` reads fixed bands. 60 observations at one score measure the 80+ band
   while every quintile starves at 12, so the consumer could read a measured bucket out of a
   report flagged unpublishable.
3. **Confounded enrichment measurement.** The first run of `enrichment_bias.py` used the last
   published refresh — a *fast* one where 288 of 290 unenriched rows were simply names not
   re-polled. The script now refuses any payload more than 5% carry-forwards.
4. **Understated deflation trial count.** The harness deflated against 5 configured shadow
   strategies when 44 variants had been tried. Now sourced from the experiment registry.
5. **Silent report-path collision, caught during the merge.** `benchmark_suite.py` and
   `p0_q1_benchmark_factor_report.py` both wrote `benchmark_comparison.json` with different
   schemas, so whichever ran last silently won and the UI panel would have read whichever it
   got. Retargeted to `benchmark_alpha_regressions.json`.
6. **Three UI panels reporting "measured" with every field empty**, also caught during the
   merge: `build_research_evidence.py` read this branch's report schemas, and `main`'s
   differ. Remapped, with a null sweep over the published artifact to confirm.
7. **Calibration reading the wrong harness path.** `observations_from_harness` called the
   calendar-day raw-return diagnostic and read a field it never produces. Invisible while the
   PIT store is empty, since both paths return nothing. Now pinned by a test.

---

## Artifacts produced

`benchmark_alpha_regressions.json` · `strategy_diagnostics.json` · `score_calibration.json` ·
`public/data/validation/research_evidence.json`

`benchmark_alpha_regressions.json` is deliberately a separate file from
`benchmark_comparison.json`: `p0_q1_benchmark_factor_report.py` owns the latter and writes
buy-and-hold metrics for the same benchmark set. Two scripts writing one path would mean
whichever ran last silently won.

Plus `pipeline/data/full_refresh_snapshots/advisor-2026-08-06T002332-full.json`, a 140K
field-trimmed extract of the last clean full-universe refresh so the enrichment measurement
reproduces without network access.

---

## Test coverage added

167 Python tests and 17 frontend tests, covering every brief-mandated case:

- full-universe enrichment cannot use previous rank (byte-identical selections)
- manifest score distribution matches the published champion *(pre-existing, retained)*
- sector-residual forward returns use trading sessions, and the best raw performer can be the
  worst residual performer
- purge prevents overlap — no purged observation ever appears in training
- unavailable news is not neutral evidence, in both directions
- unavailable SEC insider data is not neutral evidence
- cost scenarios applied correctly, and the verdict tracks turnover rather than being hardcoded
- score normalization deterministic *(pre-existing, retained)*
- turnover buffers behave exactly as specified, at exact boundaries

---

## Not done, and why

| Item | Reason |
|---|---|
| Backtest re-run under tiered costs or any turnover control | Needs 5y daily price/volume for ~860 names; no network egress |
| Unseeded full-universe enrichment comparison | Same |
| Component IC, ICIR, populated calibration | 0 of 24 PIT periods |
| Portfolio size / weighting matrices | The artifact stores only the top-20 picks, no full rankings or per-name returns |
| Sector-neutral benchmark composite | Only 193 of 397 historical picks carry a sector label; labelling the rest is fabrication |
| Capital Efficiency, FCF Quality, Balance-Sheet Resilience sleeves | Gated on validation being positive or plausibly positive. It is neither — see the Verdict |
| Catalyst Continuation model | Correctly out of scope; a separate tactical model with its own validation |
