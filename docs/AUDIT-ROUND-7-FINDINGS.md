# Audit Round 7: Data-Quality Gate, the Already-Promoted Champion, and Small-Sample Honesty

Every number is scoped to these pins unless a row states otherwise.

| Pin | Value |
|---|---|
| Signal metrics report | `public/data/validation/signal_metrics.json`, generated 2026-08-21T19:00:09Z, model_version 3.2.0, git c54a27f0 (read from `origin/main`) |
| Refresh under test | `advisor-2026-08-21T18:56:08.284865+00:00` (881 rows) |
| Backtest panel | `pipeline/backtest_signal_panel.json`: 60 periods, 2021-09-01 → 2026-08-03, 860 tickers/period |
| Backtest equity curve | `pipeline/backtest_monthly_results.json`: 1,242 daily rows, 2021-09-01 → 2026-08-13 |
| Harness freeze | `pipeline/validation/harness_freeze.json`, frozen_at 2026-08-11, harness_start_date 2026-09-01, 0 of 24 periods observed |
| Where the fixes live | branch `claude/valuesignal-audit-verification-ulq2a1` — production refreshes run from `main`, so every code fix below reaches the published data only after merge |

---

## Task 1 — Data quality gate: AMZM and TTM

**Diagnosis.** Both breaching tickers are **portfolio holdings**, not universe-config
members: they appear only in `portfolio_coverage`, with `price: null`,
`last_polled_at: null`, and `coverage_status: "stale_provider_unavailable"` — no provider
has *ever* returned a row for either. Neither is in the Aug 14 Fidelity reference export
(`src/lib/referencePortfolio.js`), so both were hand-entered. This rules out the other two
candidate causes directly: it is not Alpha Vantage rate-limit exhaustion (Alpha Vantage is
not the price path — the Yahoo batch is, and it priced the other 879 of 881 rows in the
same refresh), and it is not a broken join (the join produced correct placeholder rows;
the providers genuinely return nothing).

- **TTM** — the Tata Motors NYSE ADR, delisted January 2025. No provider serves that line
  anymore; it can never price again.
- **AMZM** — resolves to nothing at any provider and never has; almost certainly a typo
  for AMZN (the DECJ→DECK precedent, already handled by this codebase's retirement
  mechanism). Deliberately **removed rather than remapped**: silently converting the
  typo'd entry into an AMZN position would fabricate a cost basis for a security the
  ledger never recorded. If the position was real, re-add AMZN with its actual basis.

**Why they could not be removed from the app.** Portfolio holdings re-seed themselves
from the previous run's own `portfolio_coverage` (`resolve_refresh_symbols`), so anything
that ever entered that list re-entered on every subsequent refresh — the exact
self-reseeding loop the DECJ retirement was built for.

**Fix (this round).**
1. `pipeline/fetch_advisor.py::RETIRED_SYMBOLS` is now a dict of `{ticker: reason}`
   (membership checks unchanged — `in` reads dict keys) with TTM and AMZM added.
2. The reasons are published into the point-in-time universe store: `run()` now passes a
   churn note to `pit_store.record_universe()` naming each retired symbol filtered that
   run, and `pipeline/signal_metrics.py` surfaces that note inside
   `data_quality_counters.detail.universe_churn` — so the removal arrives *explained*,
   which is what distinguishes maintenance churn from the unexplained churn this counter
   exists to catch.
3. `src/lib/useFirebasePortfolio.js::RETIRED_TICKERS` adds both tickers so the Firestore
   position documents are deleted on next portfolio load and stop being dispatched as
   holdings.
4. Regression test:
   `test_ttm_and_amzm_are_retired_and_cannot_reseed_from_prior_coverage`
   (`pipeline/tests/test_fetch_advisor.py`), which also asserts every retired symbol
   carries a non-empty reason.

**Verification status: partial by necessity.** The counter is recomputed by the
production refresh, which runs from `main` on a network this session does not have
(and `main`'s daily full sweep is itself still failing to publish on the pre-existing
conflicts.jsonl >100MB push rejection, fixed earlier on this same branch). Expected
sequence to 0: merge → next refresh drops both from universe + coverage → `universe_churn`
shows them under `removed` with the note → `missing_prices` returns to 0. The code-level
verification (retired symbols cannot enter `symbols`/`portfolio_coverage`) is green now.

## Task 2 — Pre-clock promotion decision: **already decided and executed**

The premise of this task is stale. `harness_freeze.json`'s `pending_decision` block is a
*record of a resolved decision*, not an open one:

> `"decision_status": "PROMOTED 2026-08-12, ownership approved (\"riskier but still safe\"
> against the alternative of holding), zero clock cost since harness_start_date had not
> arrived"`

with `promoted_commits` 0338d005 and 6ba916b6. The code confirms the promotion is live:
`build_research()` passes `apply_coverage_multiplier=False` to
`blend_research_components()` and reads the pre-multiplier `raw_score` for the
fundamentals component; `multiplier_removal_variant` was retired from
`signal_correction_variants()` as redundant the same day. The disclosed side effect
(financials-vs-rest gap +2.8 → +7.9) was on file at promotion time. Zero prospective
periods had accrued (clock starts 2026-09-01), so the promotion cost nothing — exactly
the outcome this task was written to secure. **No action taken; nothing to promote.**

**One genuine residue, surfaced for Josh (not acted on):** the frozen champion block's own
note admits `config_hash` "is carried over unverified against current settings.json; it
was already stale before this promotion." Re-deriving the champion's `config_hash`
(and re-stamping `frozen_at`) before 2026-09-01 would make the freeze self-consistent at
zero clock cost; after 9/1 it becomes a mid-clock edit to the frozen reference. This
touches the clock's integrity record, so it is Josh's call, not a monitoring pass's.

## Task 3 — Rolling beta discrepancy: **case 3, display truncation, no bug**

Confirmed from code and by exact reproduction. Both metrics are computed from the **same**
`betas` list (`signal_metrics.py::_rolling_beta` over the backtest equity curve):
`rolling_beta_60d.detail.series` is literally `betas[-60:]` — the most recent 60 of 1,182
observations — while `swing`/`beta_range` take `min`/`max` over all 1,182. Recomputing
from the pinned inputs through the same functions reproduces every published number
byte-for-byte: 1,182 betas, range [0.19, 1.31], swing 1.12, latest 0.21, last-60 range
[0.19, 0.55].

**The specific dates.** Beta first crossed above 1.0 on **2021-12-02** (1.04), was above
1.0 on 171 observation dates in total, peaked at **1.31 on 2025-10-29**, and was last
above 1.0 on **2025-12-17** — all months before the ~2026-05 start of the 60-observation
display tail. The trough (0.19) is recent: **2026-07-31**.

To keep this from being re-flagged, `rolling_beta_60d.detail` now carries a
`series_note` stating the series is the most recent 60 observations and that
`swing`/`beta_range` span the full history.

## Task 4 — Leg-level rot (diagnostics complete; reweighting proposed, **not applied**)

**4.1 — the null-IC legs are zero *panel* coverage, not broken computation.** Across all
60 panel periods × 860 tickers, `growth` and `news_sentiment` have **exactly zero**
non-null leg scores; `per_leg_ic` correctly returns null on an empty series. Two
consequences worth stating precisely:

- Inside the panel they already carry **no effective weight**: `composite_score`
  renormalizes over legs present per ticker, so their configured 8.58% + 4% redistributes
  every period. The composite IC was never propped up or dragged by them.
- These nulls say the *backtest panel* cannot see these legs (no historical news archive
  exists to reconstruct sentiment; growth needs statement-history depth the as-filed
  store lacks at panel dates). They say nothing about the *live* pipeline, where both
  legs resolve. Zeroing their production weight on this evidence would be acting on
  absence of measurement, not measurement. Recommendation: leave production weights
  alone, treat both legs as *backtest-unvalidatable*, and let the prospective clock —
  which starts 2026-09-01 and does see them — grade them.

**4.2 — the negative legs rest on 5 scoreable periods, and no longer window exists.**
The panel is the entire history; `capital_allocation` and `accounting_quality` resolve
scores in only 6 of 60 periods (5 with computable IC). Full summaries over everything
that exists:

| Leg | periods | mean IC | ICIR | t-stat |
|---|---|---|---|---|
| valuation | 14 | +0.0857 | 2.47 | 2.67 |
| financial_health | 14 | +0.0310 | 1.71 | 1.85 |
| market_behavior | 59 | +0.0208 | 0.38 | 0.85 |
| profitability | 5 | −0.0168 | −0.63 | −0.41 |
| capital_allocation | 5 | −0.0424 | −1.06 | −0.69 |
| accounting_quality | 5 | −0.0468 | −2.85 | −1.84 |

At n=5 with |t| < 2 (registered evidence bar: t > 3), neither negative sign is
distinguishable from noise — this is not a Round-3-style sign inversion, it is an
unpowered sample. Nothing here justifies a production change; it justifies patience.

**4.3 — a measurement artifact in `drop_one_leg` itself, found while verifying.** The
published `mean_ic_without_leg = 0.0749` for `market_behavior` (delta −0.0398, the
largest "hurting" reading) is computed over only **14 periods** — because in 45 of 59
periods `market_behavior` is the *only* leg with scores, and removing it deletes those
periods from the sample rather than improving them. The delta therefore compares a
59-period mean against a 14-period mean of a different regime. The "market_behavior hurts
the composite" reading is substantially a sample-composition artifact, not a measured
marginal harm. Fixing `drop_one_leg` to compare on the common period sample is a metric-
methodology change outside this round's contract — flagged for the next round rather than
changed mid-pass.

**4.4 — proposed reweighting (NOT applied), evaluated on the same panel, same horizon,
same 59-period composite sample as the published numbers:**

| Variant | periods | mean IC | ICIR | t-stat | hit rate |
|---|---|---|---|---|---|
| Baseline (champion weights) | 59 | 0.0351 | 0.687 | 1.523 | 0.678 |
| **A — zero growth, news_sentiment, capital_allocation, accounting_quality** | 59 | 0.0354 | 0.693 | 1.536 | 0.678 |
| B — A + market_behavior halved (0.18 → 0.09) | 59 | 0.0361 | 0.710 | 1.574 | 0.661 |
| C — zero all four hurting legs incl. market_behavior + profitability | **14** | 0.0815 | 2.511 | 2.712 | 0.714 |

Recommendation, for Josh's review only: **none of these clears the bar for a production
change.** A is cosmetically tidier (+0.0003 IC) but its real content is bookkeeping — the
zeroed legs were already renormalized away (growth/news) or nearly unmeasurable
(5 periods). B's gain leans on the 4.3 artifact and costs hit rate. C's headline numbers
are an illusion of sample selection (14 fundamentally-covered periods only, a different
and easier regime — not comparable to the 59-period baseline). Given the prospective
clock starts in 10 days and will grade the *current* champion, changing weights now on
n=5 subsamples and a mismeasured drop-one would be exactly the overfitting the deflated-
Sharpe machinery exists to punish. Revisit when the clock has real periods.

## Task 5 — `sample_size_warning` on the performance export: **done**

`src/lib/exportSnapshot.js::buildExportSnapshot` now stamps
`portfolio_analytics.performance.sample_size_warning` whenever
`performance.observations < SAMPLE_SIZE_WARNING_FLOOR` (60 — an exported constant, one
line to change if Josh sets a different floor). Display layer only: no number changes,
sibling blocks keep reference identity, and blocks with no observation count are left
untouched. Four tests in `src/lib/exportSnapshot.test.js`. Rendered output against the
exact defect case (Sharpe 5.75 / Sortino 12.46 / 89.8% on 24 observations):

```json
{
 "available": true,
 "observations": 24,
 "sharpe": 5.75,
 "sortino": 12.46,
 "annualizedReturn": 89.8,
 "sample_size_warning": "Computed from only 24 observations (reporting floor: 60). Headline ratios in this block (Sharpe, Sortino, annualized return) are not yet statistically meaningful at this sample size. For the honest view, read deflated_sharpe and probabilistic_sharpe in signal_metrics_report, which account for sample length and the number of configurations tried."
}
```
