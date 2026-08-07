# Implementation Changelog

Changes made during the research-driven algorithm overhaul. Evidence and reasoning live in
`docs/ALGORITHM-RESEARCH-RESULTS.md`; this is the what-and-where.

Baseline at start: 652 Python tests, 337 frontend tests, 9 data contracts.
At completion: **819 Python tests, 354 frontend tests**, 9 data contracts, lint and build clean.

---

## Behaviour changes to the production champion

Three, all defect fixes rather than model changes. No new signal was promoted.

| Change | File | Effect |
|---|---|---|
| Unavailable news leaves the denominator instead of filling it with 50.0 | `news_intelligence.py` | Published scores move **+1.005 mean, +1.40 max**; 10 of 40 names change rank position. Names below 50 move down |
| Dark-provider modifiers snapshot as unavailable, not neutral 0.0 | `validation/ic_harness.py`, `fetch_advisor.py` | Immutable PIT records no longer grade an unreachable SEC layer as reviewed evidence |
| IC harness measures the contract's target | `validation/ic_harness.py`, `config/settings.json` | 63 **trading sessions**, sector-residual; every IC statistic changes meaning |

---

## New modules

| Module | Purpose |
|---|---|
| `validation/trading_calendar.py` | 8,437 real NYSE sessions read from committed SPY history. Raises rather than degrading to calendar days |
| `portfolio_construction.py` | Four turnover-control challengers: rank buffer, minimum holding, score smoothing, replacement margin |
| `strategy_diagnostics.py` | Expectancy, profit factor, payoff, R-multiples, streaks, Sortino/Calmar, rolling Sharpe, regime attribution |
| `cost_sensitivity.py` | Re-prices realized turnover across every rate `costs.py` produces |
| `benchmark_suite.py` | 14 tradeable benchmarks with per-benchmark Newey-West regressions |
| `enrichment_bias.py` | Shortlist-gating footprint, gated on a full-universe source |
| `score_calibration.py` | Score-bucket outcome table behind an observation gate |
| `experiment_registry.py` | Every attempt, including failures; supplies the deflation trial count |
| `news_weight_impact.py` | Measures the news fix against the last published refresh |
| `build_research_evidence.py` | Aggregates the reports into one UI artifact |
| `src/components/ResearchEvidence.jsx` | Seven panels on `/screens/validation` |

## Extended, not rebuilt

| File | Addition |
|---|---|
| `validation_framework.py` | `purge_periods` / `embargo_periods` on `walk_forward_splits`; `label_overlap_periods` |
| `evaluation.py` | `purge_periods` on `walk_forward` and `evaluate_candidate` |
| `backtest_monthly.py` | `--rank-buffer`, `--min-holding-months`, `--score-smoothing`, `--replacement-margin`, all defaulting off |
| `confidence.py` | `historical_calibration_component`; explicit "not a probability" interpretation |
| `fetch_advisor.py` | `FULL_UNIVERSE_RESEARCH` mode; `source_status` passed to the PIT snapshot |
| `config/settings.json` | `horizons_sessions`, `primary_horizon`, `sector_residual_minimum_peers` |
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
   strategies when 47 variants had been tried. Now sourced from the experiment registry.

---

## Artifacts produced

`enrichment_bias.json` · `benchmark_comparison.json` · `strategy_diagnostics.json` ·
`cost_sensitivity.json` · `score_calibration.json` · `experiment_registry.json` ·
`news_availability_impact.json` · `public/data/validation/research_evidence.json`

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
