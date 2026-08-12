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
- **11 challengers** entered with hashes and citations. Champion = production bands
  model, unchanged.
- Promotion criteria (numeric, pre-committed): ICIR >= 0.5, IC t >= 2.4, net-of-cost
  spread > 0 under the canonical impact law, DSR >= 0.95 at **N=50** (raised from 40
  as the variant family grew to 42 enumerated), PBO <= 0.50.
- Abandonment: ICIR <= 0 or net spread <= 0 at 24 periods.
- Changes to champion score semantics reset the clock. Provider fixes proven
  score-identical do not.
- **Pending ownership decision, recorded as HOLD**: promoting the multiplier-removal
  defect fix (score_variants.multiplier_removal). Promoting before 2026-09-01 costs
  zero accrued clock. The file states the monthly cost of holding.
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
- **Coverage bias** (R4): production multiplies scores by completeness twice; fixed-
  feature imputation challenger cuts Spearman(coverage, score) 0.514 -> 0.186.
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

**Decisions that belong to the owner, sitting in the freeze file:**

3. **Multiplier-removal promotion (deadline-sensitive).** Recorded as HOLD. Promoting
   the defect fix before 2026-09-01 costs zero accrued clock; promoting later forfeits
   accrued months. The measured trade: coverage-score bias 0.514 -> 0.247, at the
   price of unmasking a +7.9 financials gap the imputation challenger later closes.
   Decide before September.
4. **Survivorship data purchase**: correctly deferred until real capital enters
   (~$600-900/yr Sharadar). Re-run the reconstruction with real prices as the
   acceptance test if bought.

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
