# Round 11 — Search infrastructure: optimization harness, shadow registry, trial-count fix, EDGAR PIT pilot

Infrastructure round, per its own brief: builds reusable machinery future search rounds run
through, applies it once as a smoke test, fixes one real bookkeeping bug, and scopes one
feasibility question. No production scoring weights, composite construction, or ranking logic
changed. Full detail and exact numbers are in the four new `pipeline/experiment_registry.py`
entries (`R11-P1` through `R11-P4`); this is the narrative version.

## Priority 1 — Optimization harness (`pipeline/optimization_harness.py`)

C4-turnover-controls searched nine configurations in-sample and found apparent winners;
C7-turnover-walkforward killed both on re-test (PBO 0.80–0.84, no variant survived deflated
Sharpe). The mistake was validating in-sample, not optimizing per se. `pipeline/evaluation.py`
already had every statistic this needs — `walk_forward`, `probability_of_backtest_overfitting`
(already CSCV, already defaults to 8 splits), `deflated_sharpe_ratio` — so this round did not
add new math. It added a structure where a candidate cannot be scored against data it was tuned
on: `Panel` splits a chronological period panel into train/validation/holdout exactly once, as
a plain slice (never shuffled — shuffling a time series before splitting is its own leakage
bug), and `OptimizationSession.evaluate()` only ever reads `.train` and `.validation`. Nothing
in the module's public surface can reach `.holdout`.

Applied to the standing `reweighted_composite_a` shadow proposal (R7's champion-vs-proposal-A
question) on the real 60-period `backtest_signal_panel.json`, split 30/15/15:

- Champion and proposal_a produced **byte-identical** validation-period IC series (mean IC
  0.0518 both). This reproduces Round 10's finding under a properly split, PBO-and-deflated-
  Sharpe-gated protocol rather than R7's original un-split script: `growth`/`news_sentiment`
  contribute 0% of the composite in this panel and `capital_allocation`/`accounting_quality`
  contribute only 6.5–6.7%, so zeroing them is arithmetically indistinguishable from keeping
  them, here.
- Neither configuration ships: deflated Sharpe probability 0.2077 (bar is 0.95), validation
  IC's t-statistic doesn't clear 3.0. Walk-forward efficiency of 1.97 (validation IC exceeding
  train IC) reads as small-sample noise on a 30/15-period split, not a good sign.
- **Nothing changes for `reweighted_composite_a`.** It continues on the prospective clock
  (running since 2026-08-21) exactly as before — this round is an independent, more rigorous
  backtest-side confirmation that neither backtest alone would have promoted it, which is
  consistent with promotion requiring prospective evidence in the first place.

Item 4 of this priority ("apply the harness to re-run the C4 turnover-control search") is
**not** re-simulated here: `C7-turnover-walkforward` already applied this exact rigor (split-
half walk-forward, CSCV PBO at 6 and 8 splits, deflated Sharpe against 47 trials) to that
specific question and reached ABANDON. Re-running it through this harness would need
`backtest_monthly.py`-style monthly NAV series — a different data shape than the composite-
score panel this harness consumes — and would not change C7's already-rigorous answer.

12 tests in `pipeline/tests/test_optimization_harness.py`.

## Priority 2 — Shadow portfolio registry cap (`pipeline/shadow_portfolios.py`)

The module already runs multiple strategies concurrently, but nothing distinguished permanent
product sleeves/baselines (`production`, `SPY`, `momentum`, and so on — always live since
`ACTIVATION_DATE`, never subject to a promotion decision) from genuine research-candidate
shadows (strategies with their own later activation date, currently just
`reweighted_composite_a`). Added `research_candidate_strategies()`,
`MAX_CONCURRENT_RESEARCH_CANDIDATES = 4`, and `assert_candidate_capacity()`, called once at
import time against the live registry — a future change registering a fifth concurrent
candidate without concluding one of the existing ones fails immediately, in code, not in a
process doc.

Exactly one research candidate is registered today, well under the cap. This round's harness
run found nothing that cleared the promotion bar with enough margin to warrant registering a
second candidate, so the cap ships without a new one behind it — inventing a candidate just to
exercise the plumbing would be exactly the kind of dishonest bookkeeping this whole apparatus
exists to prevent. 5 tests in `pipeline/tests/test_shadow_portfolios.py`.

## Priority 3 — Deflated Sharpe trial-count undercount (`pipeline/signal_metrics.py`)

Round 9 flagged two dashboards showing different Deflated Sharpe framing for what a reader
assumes is the same number. Direct source read found the specific defect: `honesty_metrics()`
computed its own trial count from the currently-loaded backtest's own optimizer sweep
categories, falling back to 1 if none — never reading
`experiment_registry.total_variants_tested()` at all, unlike `ic_harness.py`'s
`research_trial_count()`, which already floors at the registry total for the audit-dashboard
view. Fixed to `trials = max(sweep_trials, total_variants_tested())`, mirroring the existing
pattern exactly. One new regression test.

Two things worth being precise about:

- The currently-published `signal_metrics.json` artifact (`trials: 201, value: 0.238`) does
  **not** change from this fix alone — 201 already exceeded the registry total (55 at fix
  time, 60 after this round's own new entries), so this specific committed number is
  unaffected until the next refresh recomputes it. The bug's exposure is any backtest run
  whose *own* sweep is shallower than the registry total, which would previously have silently
  reported `trials=1`.
- **`backtest_swing.py`'s separate `DSR_TRIALS = 3` was investigated and deliberately left
  alone.** Its comment and `pipeline/validation/harness_freeze.json` both document it as the
  swing-reversal family's own registered trial count — a narrower, family-scoped denominator
  for "did this variant survive the search it was actually selected from," not a forgotten
  repo-wide count. That is a different, defensible design question this round did not have
  grounds to override. A genuinely unified single trial registry across
  `experiment_registry.py` (55 → 60), `pipeline/validation/hypothesis_log.jsonl` (8, only
  covers two 2026-08-12 families), and `harness_freeze.json` (50, a manual backfill snapshot
  of pre-hypothesis-log history) does not exist — three partially-overlapping accounting
  systems, not two. Reconciling them without risking double-counting or under-counting is a
  real audit task in its own right and was not attempted this round; flagging it here as the
  honest state of things rather than force-merging logs whose overlap isn't yet understood.

## Priority 4 — EDGAR PIT growth-reconstruction feasibility

**Feasible, decisively.** Round 10 found the backtest panel's `growth` leg at 0.0% coverage
(0 of 51,600 ticker-periods), because Yahoo's quarterly statement history rarely reaches the
two full TTM windows YoY growth needs. `pipeline/data/pit/fundamentals/` already holds 4.78M+
as-filed SEC XBRL observations with `filed` timestamps back to 2009-08 — the exact
look-ahead-safe primitive Priority 4 asked about — and `pipeline/edgar_enrichment.py`'s
`edgar_ttm_statements(symbol, as_of)` already enforces `filed <= as_of` for the live enrichment
path. It just never gets called by the backtest reconstruction path.

`research/audit/round11/edgar_pit_growth_pilot.py` reconstructed TTM revenue growth for the 19
of 21 `portfolio_symbols` with a resolvable CIK (2 are ETFs — correctly excluded), over the 24
most recent months already in `backtest_signal_panel.json`, entirely from already-committed
local data — no network access used or needed:

- **98.0% coverage** (447 of 456 ticker-periods), against the existing path's 0.0%.
- Sanity check against live production's published growth score agreed directionally for 5 of
  6 comparable tickers. The one outlier, AGO (a financial guarantor), most likely reflects the
  generic `Revenues` XBRL concept netting premiums/losses oddly for insurance profiles — the
  same reason this session's enrichment-expansion work already special-cases financial/
  insurance names elsewhere — not a flaw in the `filed<=as_of` reconstruction method.
- This measured revenue TTM growth only, a bounded proxy for the full multi-input production
  growth score, not a re-derivation of it.

**Follow-up, done in this same session (`R11-P4-2-edgar-pit-wired-into-backtest-historical`):**
`backtest_historical.py::build_snapshot` now calls `edgar_pit_growth_fallback` whenever Yahoo's
own history leaves `revenue_growth` and/or `earnings_growth` `None`, filling only what's
missing and never overwriting a Yahoo-resolved value. Revenue growth is skipped for
bank/insurer/REIT profiles (via `canonical_metrics.classify_profile`, reusing the AGO-shaped
caveat above); earnings growth is not, since net income doesn't share the "Revenues" tag's
netting ambiguity. `DISABLE_EDGAR_PIT_BACKTEST_GROWTH=1` reproduces the pre-this-round
Yahoo-only baseline for comparison. 7 new tests. A new CLI, `pipeline/run_backtest_suite.py`,
sequences panel rebuild → Round 10's leg diagnosis → the Round 11 harness in one command
(`shadow_portfolios.RESEARCH_CANDIDATE_WEIGHTS` supplies the default candidate set explicitly,
rather than guessing an attribute name from a strategy id — an earlier draft of this script
did exactly that and silently found nothing).

**What's still open, and why:** the committed `backtest_signal_panel.json` itself has not been
regenerated with this fallback live — that needs `backtest_monthly.py`'s real yfinance network
access across ~860 tickers × 60 periods, which is `blocked_network_policy` in this sandbox, the
same constraint every prior round's live-data work in this repository has hit. Round 10's leg
diagnosis, re-run via the new CLI against the existing panel, therefore still reads 0.0% growth
coverage — that number only changes after a real `python3 pipeline/run_backtest_suite.py
--years 5` run somewhere with network access. This is an environmental blocker, not an open
methodological question: R11-P4's pilot already proved the method works at 98% coverage on
real data.

## What NOT done, per the brief and this session's standing constraints

No production leg weights, composite construction, or ranking logic changed. No shadow variant
promoted — `reweighted_composite_a` keeps its existing `KEEP_AS_CHALLENGER` status and
prospective clock, untouched. EDGAR PIT growth reconstruction was piloted and found feasible,
not shipped into production. The three-way trial-registry fragmentation
(`experiment_registry.py` / `hypothesis_log.jsonl` / `harness_freeze.json`) was found and
reported, not reconciled — that needs its own careful audit pass.
