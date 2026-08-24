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

**Follow-up correction, done in this same session
(`R11-P3-2-trial-count-logs-are-not-actually-fragmented`):** reading `harness_freeze.json` in
full (291 lines, not just the ~15-line trial-count fragment quoted above) found the "three
partially-overlapping systems" framing was wrong. `dsr_trial_count_used: 50` is a **frozen**
promotion-criteria constant declared 2026-08-11/12 for four specific named prospective clocks
(champion, swing-v1.1.0, swing_reversal-A/B/C, entry_timing_overlay) and is not read by any
production code today — confirmed by grep, the only other reference is `backtest_swing.py`'s
comment, which uses its *own* family-scoped count (3), not this 50.
`experiment_registry.py`'s dynamic total is a separate mechanism for live dashboard statistics
not tied to any one frozen clock. `hypothesis_log.jsonl`'s 8 entries are not a third,
competing system at all — they're the literal source `harness_freeze.json`'s own note says its
swing_reversal(3)+entry_timing_overlay(5)=8 subtotal was read from. Merging any of these into
one number would be a category error, not a fix. What genuinely *is* still open: whether
`experiment_registry.py`'s 16 pre-freeze entries (WO-1..C7, dated 2026-08-07..10) overlap with
harness_freeze.json's six *other* pre-freeze categories (42 combined) can't be established —
neither file documents which source each of those six category counts traces to, and this
round did not guess. Separately found while reading the full file: `pipeline/validation/
deflated_sharpe.py` (a tested, 233-line DSR+PBO implementation, explicitly named as
`entry_timing_overlay`'s required implementation) had **zero production callers** — a real,
different gap. Built `pipeline/validation/harness_freeze_evaluator.py` to fill it:
`evaluate_against_promotion_criteria()` (the frozen ICIR/t-stat/deflated-Sharpe/PBO gates) and
`evaluate_entry_timing_overlay_variant()` (its own relative-improvement-over-baseline rule),
both correctly reporting `insufficient_periods` today since every clock this freeze covers is
still at 0 of its required periods. 9 new tests.

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

## Priority 5 — Swing/technical leg weighting and automatic candidate search

Follow-up user request: extend the harness to technical/momentum (swing) legs, and add a
bounded automatic candidate-generation mode for a human-in-the-loop round-trip (run locally,
hand results back, get the next round of candidates).

`optimization_harness.py` needed **zero changes** — it was already generic over leg names, so
extending it to a new domain was purely a matter of feeding it a differently-shaped panel.
`backtest_swing.py` gained a `--panel-out` mode (`build_swing_signal_panel()`) that captures
variant A's (the frozen baseline's) per-ticker leg scores for the 5 swing legs (`pead_drift`,
`analyst_revision`, `high_volume_premium`, `high_52w_proximity`, `short_term_reversal`) into
the exact same `{date, leg_scores, forward_returns}` shape `backtest_signal_panel.json` already
uses — written to a separate file, never embedded in the committed
`backtest_swing_results.json`, and never touching `swing_signals.SWING_WEIGHTS` or resetting
the swing-v1.1.0 prospective clock (`harness_freeze.json`'s `changes_that_reset_this_clock`).

`run_backtest_suite.py` gained `--domain {fundamentals,swing}` (selects panel path, build
command, and default candidate — `swing-reversal-B`'s exact registered weights for swing,
transcribed from `harness_freeze.json` rather than re-derived) and `--auto-search N`: N
randomly perturbed neighbors of the champion weights (`random_neighbor()`: each leg scaled by
a factor in `[1-perturbation, 1+perturbation]`, each leg independently droppable to explore
leg-removal hypotheses, renormalized to the champion's total weight mass), generated from
`--search-seed` for exact reproducibility. `N` is a required, explicit argument — no default
count — matching the master protocol's own "state up front how many candidates, and why"
discipline; this is bounded local search a human reviews each round, not open-ended tuning.
Every candidate in one invocation still shares one `Panel` split and one shared `classify()`
call (one PBO computation across the whole batch), so none of R11-P1's split-then-search or
search-wide-PBO discipline was loosened to build this. The report is now sorted PROMOTE >
KEEP_AS_CHALLENGER > ABANDON, then by validation IC within a tier, and includes each
candidate's actual weights, so a human (or a follow-up conversation) can read the ranked
results and propose the next round directly from the printed output.

Verified end-to-end with a synthetic scratch swing panel (not committed) and the real
committed fundamentals panel — both domains correctly run the full gate sequence and correctly
report a degenerate all-zero-coverage-leg candidate (a real edge case a random leg-drop can
produce) as `ABANDON` rather than crashing. 10 new tests.

## Priority 6 — A live search session, a coverage-weighted formula, and a bootstrap Elo tournament

A live, human-in-the-loop search session against a real, network-fetched panel (run on the
user's own machine) reached the same conclusion three independent ways: a thin-sample PBO
reading (17 candidates, 15 validation periods), a well-powered PBO reading after fixing the
sample-size and block-conditioning problems (5 candidates, 48 validation periods, 8 balanced
CSCV blocks), and cross-window train-IC instability (positive on a 5-year window, negative on
a 10-year window, for nearly every candidate including champion itself). Extending the panel
from 5 to 10 years — now feasible for `growth` specifically because of this round's own EDGAR
PIT fix — made the "don't trust this ranking" signal *more* credible, not less. Session
detail: `champion`'s current weights mismatch coverage badly for three legs (`profitability`
weighted 20.3% on 7.5% real coverage; `capital_allocation`/`accounting_quality` together 15.6%
on 6.5–6.7% coverage each), while `growth`'s weight (8.6%) has not been revisited since its
coverage jumped from near-zero to 95.4%.

Two follow-up tools operationalize what that session found, both opt-in and additive to the
existing harness rather than a replacement for it:

- **`optimization_harness.formula_weights(periods)`**: `weight_leg ∝ coverage_leg × max(0,
  standalone_ic_leg)`, computed only from a train slice. Directly targets the coverage/weight
  mismatch above — a leg with broad coverage but no measured predictive power is driven
  toward zero exactly as surely as a leg with strong IC but almost no coverage.
- **`pipeline/elo_tournament.py`**: instead of one closable train/validation comparison, runs
  many bootstrap resamples of the validation slice and lets candidates play a full
  round-robin each round with standard logistic Elo updates. This is explicitly *not* a way
  around the panel's data-power limit — bootstrap resampling cannot manufacture information
  beyond what the sampled periods already contain. What it buys is visibility into whether an
  apparent edge is *robust* across resamples of the same data (rating separation that grows
  and holds) versus a lucky single split (ratings that never separate). A smoke test against
  this sandbox's own stale panel confirmed the honesty property directly: `formula_weights()`
  collapsed to `{market_behavior: 1.0}` on that panel and tied `champion` and
  `reweighted_composite_a` for all 100 rounds — because on that specific panel those three
  candidates produce byte-identical scores (the coverage-collapse dynamic Priority 1 already
  found). Three functionally-identical candidates showing zero separation across 100
  independent resamples is the tool working correctly, not failing to find a winner.

Wired into `run_backtest_suite.py` as a fourth, opt-in stage: `--elo-rounds N
--include-formula`. 19 new tests. The genuinely informative next run is against a real,
network-fetched, EDGAR-refreshed panel — not available in this sandbox.

## Priority 7 — Equal-weight/blend candidates, sector-partitioned weighting, top-N-from-elo

Three more additive, opt-in tools, all still backtest-only:

- **`optimization_harness.equal_weight_candidate(legs)`**: the 1/N-per-leg no-opinion control
  every weighting scheme should beat. Wired into both the harness and elo stages via
  `--include-equal-weight`.
- **`optimization_harness.blended_full_coverage_candidate(recommended, legs, blend=0.5)`**:
  averages a recommended candidate (`reweighted_composite_a`, if registered) with
  `equal_weight_candidate`, guaranteeing every leg keeps a nonzero share — `reweighted_composite_a`
  alone drops `growth`/`capital_allocation`/`accounting_quality`/`news_sentiment` entirely, which
  is a deliberate finding but also means it never gets tested with every leg still contributing
  something. `--include-blend` / `--blend-ratio` in both stages.
- **`optimization_harness.sector_weight_report(periods)`** / `--sector-breakdown`:
  `backtest_monthly.py` now tags each panel period with each ticker's *current* GICS sector
  (`current_sector_map()`, the same current-sector-applied-retroactively approximation
  `backtest_swing.py` already discloses — panels carry no point-in-time sector history), so
  `formula_weights()` can be computed independently per sector on the train slice. Answers
  whether, say, tech genuinely warrants a different leg weighting than one champion vector
  applied uniformly, rather than assuming it. Verified live against this repo's own committed
  `advisor.json`: resolves a sector for 879/910 tickers with no network needed. A panel built
  before this change reports no sector data and the flag skips gracefully rather than erroring.
- **`run_backtest_suite.top_candidates_from_elo(path, n)`** / `--top-n-from-elo N
  --elo-results-in PATH`: pulls the top N names off a previously-written elo leaderboard
  straight into a fresh harness (and, with `--holdout-check`, holdout) pass — "test the top N"
  without hand-retyping weight vectors off a printed leaderboard.

`shadow_portfolios.MAX_CONCURRENT_RESEARCH_CANDIDATES` was raised from 4 to 5 on explicit user
request, to make room for a shortlist selected via `--top-n-from-elo` once a real run produces
one. This is a real widening of the concurrent-candidate tax on deflated Sharpe, done
deliberately rather than silently; no candidate has actually been registered against the new
capacity yet — that step still needs a real, network-fetched panel run and a specific,
human-reviewed shortlist, per this round's own standing "no fabricated results" rule. 25 new
tests (12 in `test_optimization_harness.py`, 12 in `test_run_backtest_suite.py`, 1 updated in
`test_shadow_portfolios.py` for the new cap).

## Priority 8 — EDGAR PIT statement fallback beyond growth (`R11-P7` in the registry)

A live `--sector-breakdown` run on the user's own real 10-year panel surfaced what first looked
like a fresh-fetch flake: every sector's report showed only `growth` and `market_behavior` —
never `valuation`, `profitability`, `financial_health`, `capital_allocation`, or
`accounting_quality`. `--cache-only` reproduced the identical result, ruling out a network
issue, and a direct local cache check found 0 of 861 cached tickers had empty income
statements — ruling out a thin/corrupted cache too.

Root cause, traced by reproducing `build_snapshot()` directly against a real cached ticker
(AAPL) and this repo's own committed EDGAR PIT store: Yahoo's cached quarterly statements only
reach back ~1.5–2 years. For any `as_of` older than that — most of a 5–10 year backtest —
`start_idx` comes back `None` and `income_ttm`/`balance_now`/`cashflow_ttm` were left as
**empty** statements outright, not just missing growth (Priority 4's own scope). Every ratio
`basic_ratios()`/`derive_extended()` compute from them went to `None` too. Only `growth`
(already EDGAR-backed since Priority 4) and `market_behavior` (pure price/volume) survived —
exactly the pattern observed.

Fix: `edgar_pit_statement_fallback(ticker_data, as_of)` substitutes
`edgar_enrichment.edgar_ttm_statements()`'s full income/balance/cashflow dicts directly for
that empty branch — the same adapter Priority 4 already uses for two numbers, now used for the
statements themselves. `edgar_enrichment.BALANCE_ROWS` carries no shares-outstanding concept,
so market-cap-dependent ratios needed a further fallback: diluted (then basic) weighted-average
shares from the income statement, via the existing `fundamentals_extended` `diluted_shares`
alias — a standard, disclosed stand-in for a precise point-in-time float count.

Verified two ways: 8 new tests in `test_backtest_historical.py` (mocked EDGAR, no
network/PIT-store dependency), and a direct before/after call against real committed data —
`build_snapshot(AAPL, 2024-06-30)` went from `extended_coverage=0.0` (only growth and
technicals populated) to `extended_coverage=1.0`, with real values across every category
(`price_to_sales=8.52`, `return_on_equity=1.3531`, `current_ratio=1.04`, `debt_to_equity=1.38`,
`altman_z=2.78`, `piotroski_f=7.9`, `ev_to_ebitda=25.61`, `gross_buyback_yield=0.0252`). Not a
synthetic test — the actual production function, called against the actual committed cache and
PIT store. `DISABLE_EDGAR_PIT_BACKTEST_STATEMENTS=1` reproduces the pre-fix behavior.

**This changes how every backtest result from Priorities 1–6 this round should be read.** Those
harness/Elo/holdout comparisons ran against a panel where 5 of 8 legs had almost no real
coverage outside the most recent ~1.5 years — the growth+market_behavior dominance and
near-identical scoring across candidates observed throughout this round was substantially this
bug's signature, not a settled finding about those legs' true predictive power. The panel has
NOT yet been regenerated with this fix live; that still needs a real network-fetched
`backtest_monthly.py` run across the full universe. Every number produced before that re-run
should be treated as measuring growth+market_behavior's edge specifically, not the full 8-leg
blend the weight vectors nominally describe.

## Priority 9 — Metric-level sector breakdown (`R11-P8` in the registry)

Extends Priority 8's per-sector `formula_weights()` from the 6-8 rolled-up legs to every
individual metric the methodology currently computes — trailing P/E, ROE, Piotroski F,
Altman Z, buyback yield, EV/EBITDA, and everything else `build_snapshot()` produces — so
sector analysis can answer "which specific metric carries signal in which sector", not only
"which category."

`advisor_engine.build_research()`'s row is `{**snapshot, ...}` — every individual metric was
already a top-level key on each scored row, just never extracted into the panel.
`backtest_monthly.panel_metric_scores(rows)` now captures all of them (numeric, non-boolean,
excluding an explicit set of `build_research`'s own output keys like `score`,
`fundamental_categories`, `recommendation`), stored as `metric_scores` alongside the existing
`leg_scores` on each panel period.

The reuse move: `optimization_harness.as_metric_periods(periods)` returns periods with
`metric_scores` substituted for `leg_scores`. Every existing leg-level function —
`leg_coverage`, `formula_weights`, `sector_weight_report` — has no idea whether a "leg" name is
a rolled-up category or an individual metric, so this one substitution is enough to run all of
them at the metric level with zero metric-specific reimplementation. New
`--metric-sector-breakdown` flag on `run_backtest_suite.py` (fundamentals-only, composes with
`--sector-breakdown` in the same run); console output shows the top 5 metrics per sector by
formula weight, full list still written to `--harness-out` — learned from this same round's own
console-flooding lesson (Priority 7's `_drop_series` fix).

8 new tests. Like the sector breakdown itself, this needs a panel rebuilt with the current
`backtest_monthly.py` before `metric_scores` exists to analyze — not run against real data in
this sandbox.

## Priority 10 — Sector candidate validation check (`R11-P9` in the registry)

Direct answer to "is Priority 9's per-sector finding real or noise": `formula_weights()` is
train-slice-only by contract, so nothing in Priority 9 was yet evidence a sector's pattern
generalizes rather than being fit to a thinner, sector-restricted sample.

`optimization_harness.sector_candidate_report(panel, champion_weights, ...)` fits
`formula_weights()` on each sector's own train slice, then evaluates it — alongside champion
and an equal-weight control — purely on that **same sector's validation slice**, data the
formula never saw, through the identical `walk_forward`/`evaluate_candidate` machinery (same
deflated-Sharpe gate, same trial count) every other candidate this round has been graded
through. Never touches `panel.holdout`. New `--sector-candidate-check` flag, composes with
`--sector-breakdown`/`--metric-sector-breakdown` in the same invocation.

5 new tests, plus an end-to-end CLI run against a small fabricated two-sector panel with a
deliberately planted leg per sector — the flag correctly recovered both plants
(`sector_formula` beat a mismatched champion in both sectors, matching the planted ground
truth exactly), confirming the wiring itself, not just the isolated function.

**How to read the output once it's run on the real panel**: if a sector's `sector_formula`
beats `champion` on validation IC with `walk_forward_efficiency` holding up (not collapsing
toward zero or negative), that's real evidence the sector genuinely wants different weights —
Priority 9's train-slice finding for that sector generalizes. If efficiency collapses, that
sector's train-slice pattern was fit to noise, and Priority 9's number for it should not be
trusted regardless of how intuitive it looked (e.g. "Utilities favors leverage metrics" reads
as a sensible story either way — this check is what actually tells the two apart).

## Priority 11 — Verdict gates and growth-quality focus (`R11-P10` in the registry)

Two gaps in Priority 10 as first shipped, closed before running it on real data.

**Rigor.** It reported one comparison per sector (`sector_formula` vs `champion` validation
IC). That's the weakest possible reading — beating champion in a sector is equally consistent
with champion simply being *miscalibrated* there — and searching 11 sectors for a winner is 11
chances to find one in noise. `sector_verdict()` now grades a sector `REAL` only on all four
of:

1. beats champion on validation IC,
2. **also** beats the equal-weight no-opinion control (separates "this sector wants these
   weights" from "champion is badly calibrated here"),
3. keeps ≥50% of its train IC on validation (a collapse is the overfitting signature),
4. clears a Bonferroni-adjusted |t| bar derived from the number of sectors searched, floored
   at the repo's own standing |t| ≥ 3.

Anything short of all four reads `NOT_ESTABLISHED` with the failed gates named — never a
weaker yes. (Bonferroni at 11 sectors is ~2.84, looser than the standing bar, so the floor
binds today and the adjustment only starts mattering above ~50 sectors. Stated rather than
left as a silent no-op.)

**Objective.** The harness optimizes for predicting forward returns across the *whole*
universe, which is not the same question as ranking high-growth, good-quality companies well —
and the latter is what the score exists to do. `--growth-quality-focus` restricts each period
to names clearing `GROWTH_QUALITY_GATES` (growth ≥70th percentile; profitability and
financial_health *averaged* ≥50th) within that period's own cross-section, so qualification is
point-in-time and never uses a threshold derived from later data.

Two things only came out by running it, not by reasoning about it:

- The first draft used three independent floors. Those compound multiplicatively to ~7.5%
  retention — on a per-sector slice of the real panel (~80 names/sector) that's ~6 names per
  period, below the harness's own ≥5-name floor. Rebuilt as two gates, averaging profitability
  and financial_health into one "quality" concept (they measure the same thing; two floors
  double-counted it). ~15% retention, verified at 14.9%.
- On a 160-name/90-period synthetic panel with a deliberately planted leg per sector, the
  gates discriminated correctly: full universe → both plants `REAL` (t=29.4, t=22.0); with
  growth-quality focus narrowing to 15% of names → Energy stayed `REAL` (t=10.9) while
  Technology correctly fell to `NOT_ESTABLISHED`, naming all three gates it failed (t dropped
  to 2.33). A narrower universe producing a weaker verdict is the honest result, not a
  regression.

16 new tests. Both additions make the Priority 10 check strictly harder to pass, never easier.
Still not run against the real panel — the per-sector findings from Priorities 9 and 10 remain
unvalidated until that happens.

## Priority 12 — Per-sector weight search (`R11-P11` in the registry)

A methodology audit, requested before trusting the 0-and-1-of-11 REAL results from
Priorities 10-11, found the structure sound (split-once, renormalization over present legs,
directional t, Bonferroni, equal-weight control) but the *search* missing:
`sector_candidate_report` grades exactly **one** fitted candidate per sector, and
`formula_weights`' `max(0, train-IC)` construction collapses to 1-2 legs whenever most legs'
train ICs are negative — which is precisely the real panel's train era. The real runs show it:
sector formulas of `{growth: 1.0}`, `{valuation: 1.0}`, `{capital_allocation: 1.0}`. A sector
failing that test shows one brittle guess failed, not that no sector-specific weighting
exists.

`sector_weight_search()` / `--sector-search N` is the fix — an actual bounded search per
sector, with nothing about the honesty model weakened:

1. Each sector's train slice splits chronologically into fit (60%) / select (40%).
2. The pool: N random weight vectors over the sector's own legs, plus `formula_weights(fit)`,
   that formula shrunk toward equal weight at 25/50/75% (regularizing the mono-leg collapse),
   and equal weight.
3. Winner chosen by mean IC on the select slice — **validation is never consulted for
   selection**, holdout never touched.
4. Per-sector CSCV `search_pbo` across the whole pool on the full train slice: a sector whose
   winner is just the luckiest of N announces itself.
5. Only the winner reaches validation, with the deflated-Sharpe trial count charged for the
   whole pool it beat. Same four verdict gates, Bonferroni across sectors.

Verified on a planted two-sector panel (Technology driven by growth, Energy by valuation):
the search recovered **different dominant legs per sector** — Energy winner valuation=0.95,
Technology winner growth=0.99, both REAL, search_pbo 0.0. That per-sector divergence is
exactly the capability the round's user question ("technology shouldn't have the same capital
allocation as real estate") requires, demonstrated on ground truth before touching real data.
7 new tests.

If the real panel still returns few or no REAL sectors under this search, that is *strong*
evidence the uniform champion is genuinely adequate per sector — a much stronger conclusion
than one-guess-per-sector could support. The train-era sign instability (champion IC negative
in train, positive in validation, across most sectors) remains the bigger open question.

## What NOT done, per the brief and this session's standing constraints

No production leg weights, composite construction, or ranking logic changed. No shadow variant
promoted — `reweighted_composite_a` keeps its existing `KEEP_AS_CHALLENGER` status and
prospective clock, untouched. `swing_signals.SWING_WEIGHTS` and the swing-v1.1.0 prospective
clock are untouched — the new swing domain is a research/backtest panel only. EDGAR PIT growth
reconstruction was piloted and found feasible, not shipped into production. The originally-
reported "three-way trial-registry fragmentation" was investigated in full and turned out to
be a misdiagnosis (see Priority 3's follow-up above) — corrected rather than left standing;
one real gap (six pre-freeze category labels with no traceable source) remains genuinely open
and was not guessed at. The concurrent-candidate cap was raised (4 → 5, Priority 7) but no new
shadow strategy was registered against it — that still requires a real top-N shortlist from the
user's own machine, not a fabricated one.
