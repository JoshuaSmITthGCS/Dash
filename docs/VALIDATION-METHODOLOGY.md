# Validation Methodology

Describes infrastructure that already exists (built before this upgrade) plus what this
upgrade added. See `docs/MODEL-CARD.md` for the current validation *state* (not enough
history yet); this document describes the *method* the harness uses once it has enough.

## Walk-forward IC harness (`pipeline/validation/ic_harness.py`)

Appends one immutable row per (refresh, ticker) to `pipeline/pit_store/YYYY-MM-DD.jsonl`,
carrying `model_version`, `config_hash` (SHA-256 of the full `settings.json`), champion and
challenger scores, and realized forward returns once the horizon elapses. Computes, per
horizon (1M/3M/6M/12M — calendar days, see the gap noted in `docs/RESEARCH-CONTRACT.md`):
rank IC (Spearman), quintile/decile buckets, monotonicity, long-short spread net of 10bps,
turnover, rank stability, deflated Sharpe, and a look-ahead flag if `|IC| > 0.10` (implausibly
high, likely a data leak). Requires `minimum_icir_periods` (24) before reporting anything as
meaningful — see `settings.json validation`.

## Deflated Sharpe / probability of backtest overfitting (`pipeline/evaluation.py`)

Rank IC, ICIR, quantile buckets, deflated Sharpe accounting for the number of trials run, and
PBO (probability of backtest overfitting) via combinatorial symmetric cross-validation.
Every trial is meant to be logged so "we tried until something worked" is structurally
visible rather than hidden.

## Immutable snapshots (`pipeline/validation_framework.py`)

Content-addressed (SHA-256), append-only shadow-portfolio and validation snapshots — refuses
to overwrite an existing snapshot for the same strategy/date. Supports anchored expanding and
rolling walk-forward splits, purging for overlapping labels, and an embargo period.

## Rank-turnover / stability diagnostics (`pipeline/stability_report.py`, added this upgrade)

A different question from IC: not "does the score predict returns" but "does the score
reshuffle for reasons that have nothing to do with the business." Compares consecutive
refreshes and decomposes each ticker's score movement into a metric's value genuinely
changing versus a metric flipping between missing and present (an availability artifact).
Run against the real committed store, this diagnosed the Phase 1 enrichment bug as the
dominant cause of the rank churn the user reported — see `docs/BASELINE-2026-08-06.md` and
`docs/CHANGELOG-QUANT-UPGRADE.md`.

## Theme-screen validation (`pipeline/theme_pit_store.py`, `pipeline/validation/theme_ic.py`,
added with the structural-theme connectivity graph)

A separate, additive point-in-time store and IC harness for the theme screen's own scores
(`theme_exposure_score`, the connectivity graph's `connectivity_score`, and
`structural_rank_composite`) — it does not read from or write into `pipeline/pit_store/` or
touch the champion/challenger fundamentals harness above. `theme_pit_store` began recording on
2026-08-29, when the connectivity graph shipped; there is no history before that date, and
`theme_ic.py` never reconstructs one. Until `minimum_icir_periods` (24, the same bar as the
fundamentals harness) worth of dated snapshots have cleared the primary horizon, every graded
metric in `public/data/validation/theme_metrics.json` reports `status: "accumulating"` with no
mean IC published — the connectivity graph's edge weights and ranking formula are declared
heuristics (see `pipeline/theme_graph.py`'s module docstring), not yet validated against
out-of-sample forward returns, and should not be read as validated until this file says so.

## Signal metrics, split by sample requirement (`pipeline/signal_metrics.py`)

Publishes `public/data/validation/signal_metrics.json`, read by the signal-quality panel on
the portfolio page. Every metric carries an explicit `requires_live_sample` flag, because the
two halves of a monitoring suite have completely different readiness dates and mixing them
makes a working report look like an empty one.

**Needs no live sample (computable today on backtest data).** Rank IC at 1/5/21/63 trading
days and the decay curve across them; IC-IR; per-leg IC; drop-one-leg ΔIC against the assigned
weights; the leg correlation matrix and its redundancy flags; quantile spread and
monotonicity; score autocorrelation (turnover implied before any trade); FF5 + momentum
loadings; effective N and top-10 weight; rolling 60-day beta and its swing; breakeven gross
alpha; the alpha-versus-cost crossover horizon; percent of ADV; and the four overfitting
statistics — deflated Sharpe, probabilistic Sharpe, minimum track record length, and PBO via
CSCV.

**Needs a live sample.** Implementation shortfall, fill rate and unpositioned signals; the
distribution-shape family (Omega, Ulcer, Martin, CVaR-95, skew, excess kurtosis, tail ratio,
gain-to-pain); and the drift alarms (rolling live IC versus backtest IC, feature PSI,
live-versus-backtest return divergence, data-quality counters, position reconciliation). Each
reports its own observation counter against the sample it needs. The distribution family also
publishes a `backtest_reference` value, labeled in the UI as not a live reading, so the wiring
is demonstrably working before the sample exists.

Metrics whose input is missing publish a status and the reason rather than a value. Group A
depends on a scored cross-section panel, which `backtest_monthly.py --panel-out` writes
alongside the equity curve: one row per rebalance per ticker with the composite score, the
pre-modifier leg scores, and forward returns at each graded horizon. Without that panel the
group reports `awaiting_input` and names the command, because the alternative — grading
today's scores against today's returns — is look-ahead, not evidence.

Kill thresholds are stated in the artifact rather than left to interpretation: mean IC below
0.02, IC-IR below 0.3, leg correlation above 0.7, a negative drop-one delta, non-monotonic
quantiles, PBO above 0.5, deflated or probabilistic Sharpe below 0.95. A breached threshold
surfaces on the metric and in the group and page counters.

PBO currently runs across the optimizer's holdout folds. CSCV wants at least eight blocks and
the optimizer writes three, so the result publishes as `provisional` with the block count
attached — directional, not final.

## Promotion gates

A challenger may replace the champion only when (per the original upgrade brief, none of
these have been evaluated yet because minimum history has not been reached):

1. Specified before final test results were viewed.
2. All tuning used earlier periods only.
3. Improves a predefined primary objective.
4. Does not materially worsen drawdown, turnover, capacity, or calibration.
5. Results are not driven by microcaps, one sector, or one brief period.
6. Survives base transaction costs and remains credible under stress costs.
7. Multiple-testing diagnostics (deflated Sharpe, PBO) pass configured thresholds.
8. A prospective frozen shadow period is acceptable.
9. Has attribution and rollback support.

If minimum history is not reached, a challenger is marked `research_only` /
`collecting_prospective_evidence` and is never promoted on that basis alone.
