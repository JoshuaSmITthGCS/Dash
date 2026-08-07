# P0 — Q2: What is actually driving turnover?

Reproducible by: `python pipeline/p0_q2_turnover_attribution.py` (no network access). Output:
`pipeline/reports/turnover_attribution.json`.

## What this measures, and what it does not

The brief's real target is the 5-year monthly backtest's 64.9%-per-month rank churn. Attributing
*that* into band-crossing / genuine-change / availability-flicker / price-driven buckets, and
re-running the backtest under `normalization_mode: "cross_sectional"` to see whether turnover
falls, both require re-deriving `rank_week()` across the full ~860-name, 5-year historical
universe — the same data WO-3 already established is not committed to disk
(`pipeline/data/backtest_cache/` is empty) and cannot be fetched from this session (Yahoo Finance
is blocked by the network policy; see `docs/P0-REPAIRS.md` WO-3 for the proxy evidence). **Both
are skipped here for that reason.** Reproduction, once run somewhere with real internet access:

```bash
python pipeline/backtest_monthly.py --out pipeline/reports/backtest_bands.json
# scorer.py's normalization_mode is a settings.json-level switch, not a CLI flag; the
# cross-sectional re-run needs a config override or a small CLI passthrough added to
# backtest_monthly.py before this second command is meaningful:
python pipeline/backtest_monthly.py --out pipeline/reports/backtest_cross_sectional.json
```

**What this script measures instead:** `pipeline/pit_store/*.jsonl`, the validation harness's
own append-only scored-refresh log — currently 2 days deep, 5 `advisor-` refreshes, 4
transitions. This is real, on-disk, live production refresh-to-refresh churn (same-day and
next-day re-scoring of a ~400-name intraday universe), not the monthly backtest's churn. It bears
on the same underlying mechanism (does a metric's discretized score move when the metric barely
changed?) at a much shorter horizon, and it is real evidence, not a substitute for the blocked
measurement — treat the two as related, not identical.

## Attribution: live refresh-to-refresh churn

For every (ticker, metric) pair whose *banded* score changed between two consecutive refreshes,
its raw input is checked: if the raw value moved by under 2% (relative), the banded score change
is classified as a band-crossing artifact; 2% or more is classified as a genuine input change.
Metrics that flipped between missing and present are counted separately (this reuses
`stability_report.py`'s already-tested `decompose_score_delta`, not a new implementation).

| Transition | Shared tickers | Band crossing | Genuine change | Availability flicker | Rank movement (top-100) |
|---|---:|---:|---:|---:|---:|
| 00:23 → 00:42 | 400 | 1 | 1 | 55 | 607 |
| 00:42 → 02:04 | 400 | 0 | 12 | 23 | 375 |
| 02:04 → 15:46 | 401 | 12 | 94 | 2,588 | 1,886 |
| 15:46 → 22:50 | 416 | 6 | 24 | 1,760 | 2,755 |
| **Aggregate** | | **19 (0.42%)** | **131 (2.86%)** | **4,426 (96.72%)** | |

**Availability flicker dominates every single transition, not just one outlier** — it is not an
artifact of the documented 2026-08-06 enrichment-collapse incident (`docs/BASELINE-2026-08-06.md`)
recovering; it is consistent from the smallest transition (57 total events) to the largest
(2,708). Genuine input changes are a small minority (2.86% of events). Band crossings on
effectively unchanged values — the leading hypothesis in the brief — are the *smallest* bucket by
a wide margin (0.42%).

**This is a real, if partial, answer to Q2's falsifiable claim.** The claim was: "if band
quantization is the cause, turnover should fall materially under cross-sectional normalization
with no change to the underlying weights." That specific test is blocked. But the attribution
that *is* measurable points away from band quantization and toward metric availability — whether
a statement-derived value is present or absent at refresh time — as the dominant source of
score movement at the refresh-to-refresh horizon. If the same mechanism operates at the monthly
horizon (untested here, but plausible: `extended_coverage`/enrichment eligibility already varies
name-to-name and refresh-to-refresh by design per `fetch_advisor.py`'s shortlist gating), a
continuous normalizer would not be expected to fix most of the churn, because the underlying
problem isn't discretization — it's a metric being computed in one refresh and not the next.

## Price-driven residual (supplementary, low confidence)

A per-ticker residual — overall champion score delta minus a reconstructed fundamentals
contribution (category scores weighted by `settings.json fundamentals.category_weights`, at the
0.78 fundamentals blend weight) minus the modifier-total delta — was computed as a proxy for
market-behavior-driven movement, since no PIT-tracked field isolates that component directly.
**This is reported but not folded into the main attribution table**: only 22–39 of ~400 shared
tickers per transition had every field the reconstruction needs (most rows are missing one or
more of the six fundamental categories, per the already-documented 84/374 coverage gap in
`capital_allocation`/`accounting_quality`), and the residual magnitude swings from 0.05 to 16.8
across transitions — too noisy at this sample size to report as a percentage of total movement.
**What would fix this:** track a `market_behavior_score` field in the PIT snapshot schema (one
new tracked field, same shape as WO-3's `average_dollar_volume` addition) so this bucket can be
read directly instead of reconstructed.

## Turnover controls (rank buffering, minimum holding periods, score smoothing)

Not tested. All three require the same blocked backtest re-run to measure net-of-cost CAGR impact
(the brief's own decision threshold — "net-of-cost CAGR improves by more than 150bps under any
single control" — is a backtest-level statistic). Skipped for the same stated reason as the
cross-sectional re-run above.

## Decision-threshold read

The brief's threshold for the (blocked) monthly re-run was: cross-sectional turnover < 40%/month
confirms band quantization; turnover staying above 55% points to availability flicker instead.
That specific test didn't run. But the live-refresh attribution — a different, real, on-disk
measurement of the same mechanism — already lands decisively on the "availability flicker"
side (96.72% of events) rather than the "band quantization" side (0.42%). **Read this as
evidence that shifts the prior toward availability flicker being the dominant driver, not as
the brief's own threshold test resolved.** The honest position is: band quantization is probably
not the primary lever here; fixing metric availability consistency (why a statement-derived
metric is present in one refresh and absent in the next, for the same company, a few hours apart)
is a more promising place to look before or instead of the continuous-normalization fix the
brief's leading hypothesis pointed at.
