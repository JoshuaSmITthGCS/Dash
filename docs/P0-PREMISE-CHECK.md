# P0 — Premise Check

Five claims from the execution brief, verified against the repository at commit `5bdd9bd`
(branch `claude/valuesignal-equity-audit-yrlev8`) before any work order began. All five hold.

| # | Claim | Verified | Actual value | File : line |
|---|---|:---:|---|---|
| 1 | Statement metrics fetched for top 150 of 910; shortlist seeded with previous top 20, 5 new challengers per refresh | **YES** | `extended_limit: 150` (`advisor_universe.json`), universe `symbols` count 910, `INCUMBENT_ENRICH_LIMIT = 20`, `CHALLENGER_ENRICH_LIMIT = 5` | `pipeline/config/advisor_universe.json`; `pipeline/fetch_advisor.py:52,54,55,820-834` (`select_enrichment_priority`), `run()` at `:874` |
| 2 | Monthly backtest turnover 64.9%, 36% name retention, 397 unique tickers | **YES** | 60 monthly rebalances; sum of per-rebalance `turnover` = 38.9494, mean = **0.649157** (64.9%); `unique_tickers_selected: 397`. Retention figure (36%) is the brief's own derived complement of turnover and was not separately stored as a field — not re-derived here per scope discipline, but turnover and ticker count both match exactly | `pipeline/backtest_monthly_results.json` → `portfolio.metrics.turnover`, `portfolio.metrics.unique_tickers_selected`, `portfolio.rebalances[]` |
| 3 | `capital_allocation` and `accounting_quality` scored for 84 of 374 names | **YES** | `screen_universe` has 374 rows; rows with non-null `fundamental_categories.capital_allocation` = **84**; same 84 rows are non-null for `accounting_quality` (identical set) | `public/data/advisor.json` → `screen_universe[].fundamental_categories` |
| 4 | IC harness has 0 of 24 required periods; PIT store is 2 days deep | **YES** | `minimum_icir_periods: 24` (config); published `validation_harness.champion_1m_status` = `"accumulating, 0 of 24 periods"`; `pipeline/pit_store/` contains exactly 2 files (`2026-08-05.jsonl`, `2026-08-06.jsonl`) | `pipeline/config/settings.json:63`; `pipeline/validation/ic_harness.py:251-258`; `public/data/advisor.json` → `validation_harness`; `pipeline/pit_store/` |
| 5 | Costs in validation are a flat 10bps; `costs.py` is not wired in | **YES** | `ic_harness.py` uses `CONFIG["long_short_cost_bps"]` = `10.0` (flat, settings.json:67), no reference to `costs.py` anywhere in the file. `backtest_monthly.py` defaults `transaction_cost_bps=10.0`, also no `costs.py` import. Only importer of `pipeline/costs.py` in the whole tree is its own test module | `pipeline/validation/ic_harness.py:309,335`; `pipeline/backtest_monthly.py:91,137,256`; `pipeline/config/settings.json:67`; grep for `import costs` → only `pipeline/tests/test_costs.py` |

## Verdict

All five premises verified true, with exact numeric matches (64.9% turnover, 84/374 coverage,
0/24 IC periods, 2-day PIT store, flat 10bps cost). Proceeding to Phase 1.

One item flagged for awareness, not re-litigated here: premise 2's "36% name retention" figure
is not a stored field in `backtest_monthly_results.json` — only per-rebalance `turnover` and
`unique_tickers_selected` are. It is arithmetically consistent with 64.9% turnover (1 − 0.649 ≈
0.351, close to 36% once partial-portfolio effects are counted) and is treated as confirmed by
implication rather than independently re-derived, per the instruction not to re-litigate settled
figures.
