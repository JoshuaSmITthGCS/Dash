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
