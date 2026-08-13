# Session Handoff — ValueSignal Methodology Work

Written 2026-08-12 to transfer context into a new session. Everything below is
verifiable against the cited files. A persistent memory of this arc also exists in the
assistant's project memory (`valuesignal-audit-dispute`), so a new session should
recall the outline automatically; this file is the authoritative repo-side record.

**If you only read one section, read section 7 (What's next).** Sections 1-6 are
state; section 7 is the work.

**Update, same day, later session:** items 1 and 2 below are done (commits
`307e0882`, `a05fc1ad`, `a16b84d4` on main). Two things worth knowing before reading
further:

- **A parallel, independently-registered swing-reversal / entry-timing-overlay round
  landed on main while this handoff sat uncommitted** (12 commits, PR #79 merged
  2026-08-12), including its own edit to `harness_freeze.json`'s trial count. The two
  were reconciled by addition, not by picking one: true `total_enumerated` is **50**
  (base 35 + 5 pre-freeze + 2 survivorship-reconstruction + 3 swing-reversal + 5
  entry-timing-overlay), `dsr_trial_count_used` is 50, and the promotion-criteria text
  that still said "N=40" (stale, pre-dating even the 42-trial round) was corrected to
  match. If you're reading `harness_freeze.json` fresh, that reconciliation is already
  in place — don't re-derive it.
- **Item 2 turned out to be bigger than one CLI flag.** `price_archive.py`'s own
  docstring promised a `run_daily()` that didn't exist — only the zero-network
  historical `seed_from_disk()` was ever built. Running just `seed` on a schedule would
  have made `archive_health()` report healthy forever while never capturing a single
  new day's price. `run_daily()` is now implemented (live universe at zero extra
  network cost + recently-delisted names within the measured ~365-day retention
  window), tested, and wired into `refresh-advisor.yml` on the once-daily full sweep
  only. `archive_health()` is now published in `advisor.json` beside
  `statement_health`.

**Update, 2026-08-12, later session still: the swing model got its first backtest.**
`swing-v1.1.0` (registered 2026-08-11) shipped with no out-of-sample record of any
kind — see `harness_freeze.json`'s own `why_registered` for that model. A new session
built one: `pipeline/backtest_swing.py`, a point-in-time-safe historical walk-forward
that reuses `swing_signals.swing_scores()` directly (not a reimplementation) across all
three registered reversal variants, `pipeline/validation/labeling.py`'s triple-barrier
labels (that module existed, purpose-built for this horizon, and nothing used it until
now) for forward outcomes, and `pipeline/evaluation.py`'s IC/ICIR/deflated-Sharpe engine
for grading. Full detail is now recorded in `harness_freeze.json`'s
`additional_models[swing-v1.1.0].historical_diagnostic` block — read that first, it is
the authoritative record. In short:

- **Only 4 of 5 legs are measurable.** `analyst_revision` needs historical estimate-
  revision data that does not exist (`pipeline/data/estimates` is forward-collection-
  only, 8 tickers / 9 days old on the run date). Excluded and disclosed, not silently
  dropped — `leg_coverage.analyst_revision` reads 0.0 throughout by construction.
- **A real bug was caught mid-round**: `pipeline/data/backtest_cache` carries no
  `sector` field at all (`None` for every one of 860 tickers), which had silently
  zeroed variant C's residualized-reversal leg and collapsed the sector concentration
  cap to one undifferentiated bucket. Fixed by joining the live universe snapshot's
  current sector as the source (itself an approximation, disclosed in the output).
  First run (buggy) and the corrected re-run both completed; only the corrected
  numbers are published.
- **Headline result, 3 years / 74 non-overlapping periods / 860 tickers**: all three
  registered variants (A raw reversal, B reversal dropped, C residualized reversal)
  show a mean rank IC that is slightly negative and statistically indistinguishable
  from zero (t -0.77 to -0.99), and deflated Sharpe well under the 0.95 gate (0.09 to
  0.31). No variant shows a usable signal on this partial slice. This does not
  override, accelerate, or substitute for the prospective clock (starts 2026-09-01,
  still the sole promotion authority) — it is a supplementary historical read, and no
  weight was tuned or variant chosen from it.
- New test file `pipeline/tests/test_backtest_swing.py` (9 tests, including a dedicated
  no-lookahead regression test); full suite 1,853 passed as of this update (up from
  1,844).

**Update, 2026-08-12, later still: items 3 and 4 decided by the owner.** Promote the
multiplier-removal defect fix now; skip the Sharadar purchase. `pending_decision.
decision_status` moved HOLD -> **PROMOTED 2026-08-12** in `harness_freeze.json`
(commits `0338d005`, `6ba916b6`, `67217703`).

- Both completeness multipliers are gone from the champion path. `scorer.py` itself
  was left untouched (its `confidence_multiplier` calc still exists for non-champion
  callers of `valuation_score`); the fix is entirely in how `build_research` and
  `rescore_row` consume that output — they now read `raw_score` instead of `total` —
  plus a new `apply_coverage_multiplier` flag on `blend_research_components` (default
  `True`, so every *other* challenger keeps comparing against the pre-fix blend it was
  measured against; only `build_research` passes `False`). `multiplier_removal_variant`
  was retired — post-promotion it's always identical to champion, so publishing it was
  pure noise.
- **Caught a real live bug while promoting**: `migrate_advisor_v2.rescore_row` (the
  workflow's `rescore-only` refresh path) independently called
  `blend_research_components` and would have silently kept applying the retired
  multiplier on every rescore-only run, regressing the fix on that path specifically.
  Two more modules (`news_fix_impact.py`, `news_weight_impact.py`) make the same
  "reproduces `build_research` exactly" fidelity claim and needed the same flag —
  caught by their own test suites failing once the champion changed, not by inspection.
- Rank effect (measured in Round 5 Task 2, not re-measured here): correlation 0.937 to
  the pre-fix champion, mean absolute shift 62.5 ranks, 416 of 875 names move more than
  50 ranks. Financials-vs-rest gap widens from +2.8 to +7.9 — unmasked, not created.
- New/updated tests: `test_champion_carries_no_completeness_multiplier`
  (test_advisor_engine.py), `pipeline/tests/test_migrate_advisor_v2.py` (new, pins
  `rescore_row`/`build_research` parity so the two can't drift again),
  `test_news_weight_impact.py`'s reconstruction-exclusion test updated to a scenario
  that's still genuinely unreproducible post-promotion. Full suite 1,853 -> 1,856.
- `trial_count_for_deflated_statistics` was **not** changed — it counts everything
  historically tried, promoted or not, per its own stated discipline.

---

## 1. Where the project stands

Nine work rounds ran across 2026-08-10 to 2026-08-12, in order:

| Round | Document | One-line outcome |
|---|---|---|
| Audit R1-R2 | docs/AUDIT-REBUTTAL.md | External audit vs rebuttal, superseded by measurement |
| Audit R3 | docs/AUDIT-ROUND-3-FINDINGS.md | First measurement round; several conclusions later withdrawn |
| Audit R4 | docs/AUDIT-ROUND-4-FINDINGS.md | Alpha/turnover reconciled exactly, coverage bias measured, imputation challenger built |
| Audit R5 | docs/AUDIT-ROUND-5-FINDINGS.md | As-filed backtest built (PIT-pure), tag-union ingest defect found+fixed, harness frozen |
| Audit R6 | docs/AUDIT-ROUND-6-FINDINGS.md | Corrected spine: restatement bias isolated (alpha +8.44 t2.54 vs +0.43 t0.09 at constant cadence), valuation block vindicated, cost model canonicalized |
| Survivorship R1 | docs/SURVIVORSHIP-RECONSTRUCTION.md | Zero-cost reconstruction, null on an empty sample (reframed in place) |
| Survivorship R2 | docs/SURVIVORSHIP-RECONSTRUCTION-2.md | Ranking probe: AUC 0.81 on 317 real deaths, price archive built, symlink-clobber postmortem |
| Pre-freeze | docs/PRE-FREEZE-SIGNALS.md | Five never-built signals constructed to published specs, entered as challengers |
| Remediation record | docs/METHODOLOGY-REMEDIATION.md + research/audit/remediation/ | Per-defect before/after |

Grades at last assessment: research artifact A-, investment tool C-.
Roadmap scorecard (latest): data 93, validation 85, cost/turnover 74, portfolio 42,
signal construction 65, missing factors 70.

## 2. The freeze — the single most important operational fact

`pipeline/validation/harness_freeze.json`:
- **Clock starts 2026-09-01, completes 2028-09-01** (24 monthly periods).
- **10 challengers** entered with hashes and citations (11 minus `multiplier_removal`,
  promoted into champion 2026-08-12 — see the update note above). Champion = production
  bands model, now without either completeness multiplier.
- Promotion criteria (numeric, pre-committed): ICIR >= 0.5, IC t >= 2.4, net-of-cost
  spread > 0 under the canonical impact law, DSR >= 0.95 at **N=50** (the freeze file's
  own trial count total, updated 2026-08-12 to reconcile two independently-registered
  variant families — see the parallel-merge note above), PBO <= 0.50.
- Abandonment: ICIR <= 0 or net spread <= 0 at 24 periods.
- Changes to champion score semantics reset the clock. Provider fixes proven
  score-identical do not. (The multiplier-removal promotion did not reset anything in
  practice — the clock hadn't started, so it cost zero accrued months.)
- Deferred with pre-registered spec: idiosyncratic volatility (Ang-Hodrick-Xing-Zhang
  JF 61(1) 2006, FF3 residuals). Build it to that spec or not at all; picking a
  different residual model later = search.

## 3. Key measured facts a new session must not re-derive

- **Restatement bias, cadence-constant** (R6 §1): as-filed TTM quarterly vs restated:
  alpha +8.44%/yr (t 2.54) vs +0.43% (t 0.09), turnover 24.3% vs 50.6%, pick overlap
  10%. Restated churn was ~26pp/mo of data artifact.
- **Deflation battery** on the best estimate: DSR ~0.95 marginal, PBO 0.76 and rising
  with family size, HLZ t>3 failed. The point estimate is not evidence of alpha.
- **Valuation block is NOT broken** (R6 §3): category carries +0.508 vs B/M; the blend's
  52% quality weight cancels it to -0.11. The AFP orthogonalization (pre-freeze round)
  fixes this by construction: composite -0.115 -> +0.087, rank corr 0.971.
- **Coverage bias** (R4/R5 Task 2): production multiplied scores by completeness twice
  until the 2026-08-12 promotion removed both multipliers, cutting Spearman(coverage,
  score) 0.514 -> 0.247 and unmasking a +2.8 -> +7.9 point financials-vs-rest gap that
  the multipliers had partially hidden. The fixed-feature imputation challenger (still
  behind the 24-period harness) goes further, to 0.186, and is what eventually closes
  that gap.
- **Survivorship**: bounded and shrinking from the price archive start 2026-08-11
  forward; unmeasurable at $0 for 2021-2025 deaths (provider purges dead tickers in
  ~1 year: 2026 hit rate 49%, 2020-2025 all 0%). Ranking probe on 317 real deaths:
  price-free composite AUC 0.812 (0.833 within 12m); financial health and Altman Z
  earn their distress purpose, accounting quality does not. Paid fix (Sharadar
  ~$600-900/yr) recommended only when real capital enters.
- **Noise standard**: paired monthly diff vs 2 SE, with MDE reported. Every CAGR
  difference across all rounds is inside noise. Turnover differences are deterministic
  and are the decision axis. Cross-book comparisons (MDE > 12pp) are permanently
  underpowered at 5y.
- **Cost model**: canonical square-root law is now the base scenario in
  pipeline/costs.py (coef 630); the old 15 is the labeled optimistic scenario.
  Capacity ~$13M @ 50bps/yr, ~$200M @ 200bps. Personal-account instrument, stated in
  the model card.
- **Buffer 1.5** is the specified portfolio default, confirmed benign on three spines.

## 4. Data stores and their states

| Store | State |
|---|---|
| `pipeline/data/pit/fundamentals/` | 4,867,491 as-filed EDGAR observations, 100 shards. Includes: tag-union re-ingest (R6), retained earnings, dead cohort (+2.93M rows, 3,178 deregistered CIKs), R&D + SG&A (+102k rows). Tag-union bug in `edgar_facts.observations_for_concept` is FIXED (union across tags) with regression test |
| `pipeline/data/price_archive/` | Append-only daily price archive, 2,151 tickers / 7.1M rows, first-write-wins, conflict log, `archive_health()` goes critical after 4 stale days. **Needs a scheduled run wired into the daily refresh** (one-line job: `python pipeline/price_archive.py seed`) |
| `pipeline/data/backtest_cache/` | The pinned price cache (tree sha `9b41dfbf...`). NEVER write through its symlinks (see postmortem, SURVIVORSHIP-2 §3a) |
| `research/audit/survivorship/data/` | delisting_log.json (5,120 classified events), price_recovery.json, ranking_probe.json etc. committed; companyfacts/, form_index/, submissions/, merged_cache/ are **gitignored refetchable caches** (multi-GB) |
| `pipeline/data/ohlc_cache/` | 120-name OHLC sample for Corwin-Schultz (measured unusable at daily frequency; effective spreads need intraday data) |

## 5. Uncommitted right now

`pipeline/validation/harness_freeze.json` (11 challengers + N=50) and
`docs/PRE-FREEZE-SIGNALS.md`. Everything else was committed by the user mid-round
(user commits directly to main with terse messages; remote = local as of the last
push).

## 6. Operational gotchas learned the hard way

1. **Pushes fail from the sandboxed shell** with HTTP 408 regardless of size: the
   sandbox stalls large HTTP upload bodies. Run `git push` with the sandbox disabled.
   Downloads are unaffected.
2. **Never run 4-way parallel backtests** anymore: the enlarged EDGAR store gives each
   process a 1-2GB warm cache and contention degraded 12 months of ranking from ~15
   min to 52. Sequential is faster in wall time.
3. **The merged-cache symlink clobber**: writing a file where a symlink to
   backtest_cache exists overwrites the pinned cache. reconstruction_backtest.py has
   the guard; keep it in any new cache-merging code.
4. **zsh eats `:r` after `$VAR`** in refspecs (history modifier). Quote as
   `"${C}:refs/..."`.
5. **`git ls-tree` output is not `update-index --index-info` input** (extra type
   column). Use `--format='%(objectmode) %(objectname)%x09%(path)'`.
6. **ls-tree pathspec wildcards silently match nothing** in this repo's git (2.51).
   Use directory pathspecs or explicit file lists.
7. The scheduled runner and the user's other machine **push to main continuously**.
   Fetch before any push; expect merges; generated public/data conflicts resolve as
   theirs, append-only .jsonl conflicts resolve as line-union.
8. Backtest variant drivers live in research/audit/{round5,round6,preFreeze}/ and
   patch modules before importing backtest_monthly (which executes main() at import in
   the round6 driver: stub it with a fake module first, see preFreeze_backtests.py).

## 7. What's next (in priority order)

**Done:**

1. ~~Commit the two open files~~ — done, `307e0882`.
2. ~~Wire the price archive into the daily schedule~~ — done, `a16b84d4`. Built the
   missing `run_daily()` (not just the seed wiring originally scoped — see the update
   note at the top of this file), added `pipeline/tests/test_price_archive.py`
   coverage for it, and staged `pipeline/data/price_archive/` in the refresh
   workflow's commit allowlist so runs actually persist past the ephemeral runner.
   **Not yet verified**: the step hasn't executed in a real scheduled run yet (next
   07:00 ET full sweep will be the first). Check `archive_health()` in the next
   published `advisor.json` and `pipeline/data/price_archive/archive_manifest.json`
   for a `run_daily` entry to confirm it actually ran rather than just parsing.

**Decided by the owner:**

3. ~~Multiplier-removal promotion~~ — **PROMOTED 2026-08-12** (see the update note
   above). Coverage-score bias 0.514 -> 0.247; the imputation challenger (already
   entered, behind the 24-period harness) is still the fix for the +7.9 financials
   gap the promotion unmasked.
4. ~~Survivorship data purchase~~ — **declined**, correctly deferred until real
   capital enters (~$600-900/yr Sharadar). Re-run the reconstruction with real prices
   as the acceptance test if it's ever bought.

**Then the clock owns the calendar:**

5. **First harness period lands ~2026-10-01** (pipeline/validation/ic_harness.py,
   minimum_icir_periods 24, criteria frozen). The job between now and 2028-09-01 is to
   NOT touch champion score semantics (resets the clock) while the 11 challengers
   accumulate prospective IC. Provider fixes proven score-identical by regression test
   are allowed.

**Future construction windows (each is optional, none urgent):**

6. Idiosyncratic-volatility challenger, ONLY to the pre-registered spec
   (Ang-Hodrick-Xing-Zhang JF 61(1) 2006, FF3 residuals). Any other residual model is
   search and forbidden by the round discipline.
7. Extend the survivorship ranking probe to the valuation/technical halves for the
   2021-2025 dead cohort once any price source for them exists.
8. Model-card consolidation pass: docs/MASTER-METHODOLOGY.md carries R4-R6 correction
   blocks inline and reads as sediment; a clean regeneration would consolidate them
   without changing any number.
9. Portfolio-construction layer beyond the buffer (position sizing exists as config,
   covariance-aware sizing does not). Roadmap category still at 42.

**What NOT to do:** no weight tuning (unfalsifiable, R6 confirmed), no new backtest
variants without entering them in the freeze and raising N, no comparisons of variant
families to pick winners (PBO is 0.76 and that is how it got there).

## 8. Test suite

`PYTHONPATH=pipeline .venv/bin/python -m pytest pipeline/tests -q` from repo root:
1,706 passed as of handoff. New test files this arc: test_round4_remediation.py,
test_asfiled_backtest.py, test_dead_cohort_pit.py, test_price_archive.py.
