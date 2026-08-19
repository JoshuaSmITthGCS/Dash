# Phase 5 — The Rotating Enrichment Ladder

Status as of 2026-08-19: **built, tested, and shipped default-off.** This document
records what exists, what it replaces, what's still needed before it can actually run in
production, and how to turn it on when that's ready.

---

## What this is

`docs/ENRICHMENT-PIPELINE-AUDIT.md` §0 and §9 found that the smaller
`enrichment_rotation()` mechanism already live in `pipeline/fetch_advisor.py` (15
statement-starved names/run, unrelated to preliminary rank) resolves A3's "structurally
locked out" framing but still leaves rank score as the dominant gate on *how fast* a name
reaches statement enrichment — incumbents and challengers are still picked by rank, and
only the 15-name rotation is rank-independent. This is the work order's specified
two-armed replacement:

- **20 ranked-ladder slots/day**, walking the preliminary-ranked universe on a fixed
  day-of-cycle plan (`pipeline/enrichment_ladder.py::ladder_day_slots`):
  - Day 1: the current top 20 by preliminary rank.
  - Day 2: theme-sourced names outside the top 20, ranked by filing-evidence
    `theme_exposure_score` — **never `opportunity`**, whose business-quality leg falls
    back to price multiples for unenriched names, which would quietly re-favor exactly
    the names the ladder exists to reach.
  - Day 3+: the next 20 not-yet-enriched-this-cycle names, walking a threaded rank
    cursor. The window this scans widens past 20 ranks whenever cumulative overlap
    (incumbents, portfolio holdings, a prior ladder day, the random arm) forces it to
    skip further to find 20 fresh names — this reproduces the work order's own worked
    example (a 40-rank Day 5 window, 61-100) as an emergent property of "the next 20
    names not already spoken for," not a hardcoded per-day width.
- **3 additive random-draw slots/day**, uniform draw from the unenriched universe,
  **never carved from the 20** (`random_arm_slots`). This is the control arm: without
  it, residual rank-conditioning bias stays real but unmeasurable, which is what left
  A3 formally inconclusive before. Tagged `enrichment_source: "random"` on every row it
  touches, so the eventual Compare view can separate "this name looks strong because it
  is" from "this name looks strong because the ladder happened to reach it."

Plus the supporting machinery the work order specifies:
- **Reverse-rank AV quota allocation** (`av_quota_order`): random-arm names first, then
  the most statement-starved by `days_since_last_successful_enrichment`, with
  randomized tie-breaking so quota exhaustion doesn't deterministically strike the same
  names every cycle. Never top-down by rank — that would restore the exact
  rank-conditioning the ladder exists to remove, one layer beneath it.
- **A retry queue** (`advance_retry_queue`): a failed pull retries at the front of
  tomorrow's ranked slate (never the random arm), capped at 3 consecutive attempts
  before `enrichment_failed_persistent`.
- **`enrichment_eligible`/`in_scored_universe`** (`pipeline/scored_universe.py`): every
  row currently publishes both as `true` — no drop mechanism is wired up yet (dropping
  low scorers from the refresh queue to save provider budget is explicitly optional in
  the work order, and needs its own threshold decision this build does not make).
  `assert_scored_universe_immutable` is a real, tested runtime guard: it raises rather
  than silently publishing a payload that removes a previously-scored name on or after
  the 2026-09-01 freeze. A no-op before that date by construction.
- **`coverage_regime` tagging and the cross-regime IC guard**
  (`pipeline/validation/ic_harness.py`): every published row and every PIT snapshot
  carries `pre_enrichment_ladder` or `enrichment_ladder_v1`. `evaluate_variant`/
  `evaluate_variant_sessions` now raise `MixedCoverageRegimeError` rather than silently
  blending the two into one IC number. `build_report()` computes a fully separate report
  per regime under `coverage_regimes`, with `default_regime_view` (switches pre → post
  once 10 post-ladder refreshes exist) and `compare_available` (true once both regimes
  have ≥30).
- **The Pre | Post | Compare control** (`src/pages/LiveValidation.jsx`): reads the
  segmented report and lets a reader pick which regime's Model Evidence metrics to see,
  or both side by side. Stays hidden entirely today, since `coverage_regime` is
  uniformly `pre_enrichment_ladder` while the ladder is off — it activates itself the
  moment real post-ladder evidence exists, no further frontend work required.

## What's default-off, and why

`ADVISOR_ENRICHMENT_LADDER_ENABLED` (default `false`) gates all of this. Flipping it on
is the actual "ship" event, and two things have to happen alongside that flip, neither of
which this sandboxed build session can do on its own:

1. **The champion split must be registered**, per
   `pipeline/validation/harness_freeze.json`'s `enrichment_coverage_changes_policy`
   (already recorded, `docs/QUESTIONS-FOR-OWNER.md` question 1): a new champion identity
   with its own clock, the pre-ladder champion preserved as a tracked comparison rather
   than silently retired — the exact mechanism `champion_split_2026-08-19` already used
   for the renormalization fix.
2. **The before/after score-delta artifact** the work order requires be committed
   alongside the ladder shipping ("re-baseline the invariance test once, deliberately,
   with before/after score deltas for every newly-enriched name committed alongside —
   the A1-NEWS-NEUTRAL pattern of publishing the delta rather than applying silently")
   needs a real, live refresh against real provider data to produce. This environment has
   no network access to Yahoo/Alpha Vantage/EDGAR, so it cannot generate that artifact.

Until both of those happen, the ladder stays off. Nothing about today's production
output changes from this build landing.

## The cadence is provisional

`ADVISOR_ENRICHMENT_LADDER_CADENCE_DAYS` (default `5`, i.e. 5-day/100) is **not** derived
from Phase 4's measured provider/retry failure rates — that phase (five clean trading
days of the repaired system, then a failure report) has not run, and the work order is
explicit that cadence must come from measurement, never from returns or convenience. The
default exists so the mechanism is runnable and testable now; it is freely overridable
without a code change once Phase 3/4 actually produce a number.

## How to turn it on, when ready

1. Run Phase 3 (five clean trading days) and Phase 4 (the failure report) for real, and
   let their result set `ADVISOR_ENRICHMENT_LADDER_CADENCE_DAYS` if it differs from the
   provisional default.
2. Register the champion split in `harness_freeze.json` (a new champion block, a
   `champion_split_<date>` narrative block, a `retired_champion_<name>` block for
   whatever champion identity was active immediately before the ladder shipped, a new
   `hypothesis_log.jsonl` entry raising `trial_count_for_deflated_statistics`) — the
   `champion_split_2026-08-19` entries already in `harness_freeze.json` are the template.
3. Set `ADVISOR_ENRICHMENT_LADDER_ENABLED=true` for one live refresh, from an environment
   with real provider access.
4. Commit that refresh's before/after score deltas for every newly-enriched name,
   published rather than applied silently, alongside the flag flip.
5. From that point, `coverage_regime` starts actually varying between refreshes, the
   `enrichment_ladder_cycle` state in `advisor.json` starts actually cycling, and the
   Pre | Post | Compare control activates on its own once enough post-ladder refreshes
   accumulate.

## What was not built in this session

- **A live "drop names from the refresh queue" mechanism.** The work order frames this
  as optional ("low scorers *may* be dropped"), and choosing a drop threshold is itself
  the kind of decision this work order's own §3 reserves for the owner ("a threshold must
  be chosen without a principled derivation"). The fields and the freeze guard exist;
  nothing currently sets `enrichment_eligible: false`.
- **Real post-ladder data of any kind.** Everything above is mechanism, tested with
  synthetic fixtures. The Compare view, the retry queue's real-world behavior, and the
  AV quota allocation's actual exhaustion pattern are all unverified against a live
  refresh, because none has run.
