# Questions for Owner — Round 7 Phase 1

Batched once, at the end of Phase 1, per the work order's §3. Full evidence for each
finding lives in `docs/ENRICHMENT-PIPELINE-AUDIT.md`; this document states only what a
decision requires and the tradeoffs, not the full investigation.

---

## Question 1 — Does the enrichment ladder reset the prospective-validation clock?

**Status: mandatory per the work order's §1. Phase 5 does not ship until this is
answered.**

**Finding.** The rotating enrichment ladder (Phase 5) expands statement coverage from a
shortlist to a much larger share of the ~910-name universe. Production code already
contains a smaller-scale version of this — `enrichment_rotation()`
(`pipeline/fetch_advisor.py:1360-1388`), 15 names/run, live and unit-tested today (see
`docs/ENRICHMENT-PIPELINE-AUDIT.md` §0). It measurably changed published scores for the
names it enriched (the enriched-vs-non-enriched score gap in `pipeline/reports/
enrichment_bias.json` shrank from ~24.5 points to ~8.9 points as rotation ran). Phase 5's
specific design goes further still: 20 ranked slots + 3 random-draw slots per day, 5-7
day cadence, targeting 100-140 names.

**Why a decision is required.** Two readings of the registered rule conflict, and they
produce different clock outcomes:

- **Resets the clock** — the ladder is a change to *coverage handling*, which §1
  explicitly enumerates as clock-resetting ("weights, bands, normalization mode,
  modifier caps, **coverage handling**, blend formula").
- **Does not reset the clock** — it is a data-provider fix restoring intended inputs
  (§1's own parenthetical example is "statement enrichment"), and on a frozen snapshot
  with fixed inputs the champion's scoring *function* is unchanged — only which inputs
  are available to it. The exemption clause's own regression test (score-identical on
  frozen input) would pass for the ladder mechanism itself, because the ladder doesn't
  touch how a *resolved* metric is scored, only which metrics get resolved.

Production scores for the ~80 additional names the Phase 5 ladder would reach *will*
change, because those names will have data they previously lacked — this is not
avoidable and not a bug; it's the entire point of the ladder.

**Option A — Coverage handling, resets the clock.** Treat the Phase 5 ladder (not the
already-live 15/run rotation, which predates the freeze registration and is treated as
already-baked-in) as a score-semantics change. Restart the 24-period harness after
shipping it.
- *Tradeoff:* Clean, conservative, unambiguous. Costs real calendar time — every month of
  delay before shipping the ladder is a month the 24-period clock doesn't start, and the
  ladder is precisely the mechanism most likely to reduce the very flicker (WO-5's 96.7%
  finding) that's degrading rank stability today. Delaying it delays the fix to the
  problem the clock is supposed to be measuring against.

**Option B — Provider fix, does not reset the clock, gated on the regression test.**
Ship the ladder before the freeze (which is what Phase 5's own timeline already assumes:
ship days 9-13, freeze 2026-09-01), backed by the frozen-snapshot invariance test Phase 2
specifies: prove that on identical, complete input (every name already enriched),
champion score/rank/recommendation/universe membership are byte-identical whether the
ladder code path ran or not. The ladder's *effect* — more names get enriched — is not
what's being tested; the *scoring function's invariance to already-resolved data* is.
- *Tradeoff:* Faster to a working clock, and matches the explicit "statement enrichment"
  example in §1's own exemption clause. Risk: if the invariance test is built loosely
  (e.g., doesn't actually exercise the renormalization pathway in Question 2 below), it
  could pass while still masking a real semantic shift for names whose category
  membership changes because they cross the `required_for_score` gate for the first
  time on enrichment.

**Recommendation: Option B, conditioned on the invariance test actually covering
Question 2's renormalization pathway.** The already-live 15/run rotation is a working
precedent that this class of change does not, in practice, alter the scoring *function* —
only its inputs — and the clock hasn't started yet (2026-09-01), so there is no accrued
cost to reconcile from the smaller rotation already having shipped. But Option B is only
as safe as the invariance test's coverage: if renormalization inflation (Question 2) is
still live in the champion when the ladder ships, more names crossing from "few resolved
metrics" to "fully resolved" will change scores through a *pathway the invariance test
needs to explicitly exercise*, not just the pathway of "new data appearing where none
existed." Recommend resolving Question 2 before or alongside shipping Phase 5, not
after.

**Clock implication:** Option A — the 24-period clock starts only after the ladder ships
and stabilizes, deferring 2026-09-01. Option B — the clock starts 2026-09-01 as currently
scheduled, and the ladder ships into it under the "provider fix" exemption, contingent on
the invariance test passing.

---

## Question 2 — Renormalization inflates scores for companies with fewer resolved metrics. Fix, or leave as-is?

**RESOLVED 2026-08-19 — owner directed: fix now, split the clock rather than discard the
old one.** Neither Option A (switch modes, one clock) nor Option C (leave as-is) below as
originally framed — a fourth path: fix the actual renormalization defect directly inside
`bands` mode (impute missing-but-applicable metrics at neutral instead of switching the
whole champion to `fixed_feature`'s percentile basis, which would have required plumbing
a fitted cross-sectional normalizer through `rescore_row` and other parity-sensitive call
sites — the exact class of lockstep-regression risk the prior multiplier-removal
promotion was bitten by), and **register both the pre-fix and post-fix champion as
separately clocked strategies** rather than letting the fix silently retire the old
registration's evidence. Implemented in commits `52ba45c1` (the fix),
`f61595aa` (publishing the retired variant alongside the new one), and `d54154a0`
(registering the split in `harness_freeze.json`/`hypothesis_log.jsonl`, trial count 50 ->
51). The retired `bands_champion` registration keeps accruing its own prospective clock,
published every refresh as `score_variants.bands_pre_imputation_fix`; the new
`bands_champion_imputation_fix` registration is what the site now actually publishes as
`score_variants.champion` and what drives `research`/`screen_universe` ranking. Both
clocks start 2026-09-01, same as originally scheduled — zero periods had accrued to
either as of the decision, so nothing was forfeited. The original finding, evidence, and
options below are kept for the record.

**Finding.** The champion's live `normalization_mode: "bands"` scoring path renormalizes
each category's weight across only the metrics that resolved
(`scorer.py:159-163` `weighted_available`, used within-category at `:560` and
across-category at `:636,670,764`). `required_for_score` — the one guard that prevents
this — only protects `valuation`/`financial_health` for 5 financial-sector profiles
(insurers, banks, REITs); every other category, for every profile including the
`general` profile covering most of the universe, renormalizes freely on missing data.

**Evidence — a minimal synthetic example** (full arithmetic in the audit doc §5): two
economically identical companies, one with all 6 `profitability` metrics resolved, one
missing 2 of them (an unrelated data-vendor gap, not an economic fact). The company
missing data scores **15.6 points higher in that category (64.4 → 80.0, +24%
relative) solely because two data points are missing.** This flows into the published
score largely undamped — fundamentals carries 78% of the composite, and the Round 5
multiplier-removal promotion means nothing downstream dampens category-level dilution.
The existing publication gate (`min_publication_coverage: 0.35`) does not catch this
case: aggregate coverage stays ≈93% even while one category is 74% resolved, because the
gate is calibrated to catch gross outages, not concentrated single-category dilution.

**Why a decision is required.** This is squarely a score-semantics question the work
order forbids fixing unilaterally (§3.1: "Score semantics would change"). The team has
already built and tested the alternative — `fixed_feature` mode (`scorer.py:705-784`),
which imputes at the neutral percentile instead of renormalizing, and is documented as
closing an analogous gap in Round 4/5's own audit trail — but it is a challenger, not the
champion. Switching the champion's `normalization_mode` from `bands` to `fixed_feature`
is exactly the kind of change §1 says resets the clock ("normalization mode").

**Option A — Switch the champion to `fixed_feature` (imputation) mode.** Removes the
renormalization inflation identified above by construction.
- *Tradeoff:* Fixes a real, measured distortion that gets *worse*, not better, as the
  Phase 5 ladder brings more variably-complete companies into the scored universe (a
  company newly enriched to 4/6 profitability metrics is exactly the profile that
  triggers this). Costs: resets the clock (normalization-mode change, unambiguous under
  §1), and changes every published score to some degree, which is a large, highly
  visible change to ship right before a freeze.

**Option B — Leave `bands`/renormalization as the champion; extend
`required_for_score` to more categories/profiles as a narrower mitigation.** Keep the
existing champion untouched, but close the biggest gaps (e.g. require
`profitability`/`capital_allocation`/`accounting_quality` for profiles where they carry
the most weight) rather than switching modes wholesale.
- *Tradeoff:* Smaller, more targeted change; still touches `coverage handling`/score
  semantics per §1 and would still need its own clock-status decision, just a narrower
  one. Leaves the general-case renormalization gap open for any profile/category
  combination not explicitly added to the required list.

**Option C — Leave it entirely as-is; publish the limitation.** Document the
renormalization behavior in `docs/LIMITATIONS.md`/`docs/MODEL-CARD.md` (which already
disclose several similar known limitations) and rely on the Phase 5 ladder shrinking the
population of severely under-resolved companies over time, without changing scoring
semantics before the freeze.
- *Tradeoff:* Zero clock cost, zero implementation risk right before the freeze deadline.
  Leaves a measured, real distortion live in the champion for the entire 24-month
  validation window — any prospective IC measured during that window is partly measuring
  this artifact's interaction with whatever population of variably-enriched companies
  the ladder produces, which is difficult to disentangle after the fact.

**Recommendation: Option C for the freeze date, Option A as a registered post-freeze
challenger.** Given the freeze is 2026-09-01 and this is unambiguously a score-semantics
change, switching the champion now trades a known, bounded, disclosed limitation for an
unbounded, un-validated one (a champion with zero prospective track record under the new
mode). This matches the work order's own governing rule: don't improve the algorithm
based on outcomes already observed, and don't reset a clock that hasn't started yet on
the eve of starting it. `fixed_feature` mode should be registered as a Phase 6
challenger (it may already qualify, given it exists and is tested) so its prospective
evidence accumulates from day one rather than after a later, more disruptive switch. The
one exception: if Question 1 resolves to Option B (ladder ships without resetting the
clock), this renormalization gap should be explicitly covered by that invariance test so
the ladder's real effect on champion scores — new data resolving previously-missing
metrics — is measured and disclosed, not silently absorbed into "normal" score movement.

**Clock implication:** Option A resets the clock (normalization-mode change). Option B
likely resets the clock (coverage-handling change, narrower scope than A). Option C does
not touch the clock at all — status quo.

---

## Question 3 — The DSR trial-count discrepancy (201 vs. 50): which figure should the live validation surface show before the freeze?

**Finding.** `public/data/validation/signal_metrics.json`'s `deflated_sharpe` metric
independently computes and displays `trials: 201` (`pipeline/signal_metrics.py:997`,
counting every row — 201 — of the raw, unfiltered category-weight optimizer's search
space in `optimize_weights_results.json`). `pipeline/validation/harness_freeze.json`'s
`dsr_trial_count_used: 50` counts distinct, pre-registered hypothesis families from the
append-only `hypothesis_log.jsonl`, and is what the promotion criteria and the
prospective-clock UI (`PerformanceMetrics.jsx:223`, `portfolioAnalyticsModel.js:40`)
actually read. **These are two different populations under one word ("trials"), computed
by two uncoordinated code paths, with no cross-check between them anywhere in the
codebase.**

**Why a decision is required.** The work order's own Phase 6 names this discrepancy
explicitly and forbids resolving it by whichever number is more favorable. Right now,
before the freeze, the live signal-metrics honesty panel is already showing a deflated
Sharpe computed against 201 raw search iterations (0.2377) with no label distinguishing
it from the 50-trial figure the promotion gate actually uses — a reader of the live site
today cannot tell which "trials" claim they're looking at.

**Option A — Label both figures distinctly on the live surface now, resolve
authoritatively at Phase 6.** Add a label to the `signal_metrics.json` honesty-panel
entry clarifying that its 201-trial deflated Sharpe is a diagnostic over the raw
optimizer search space, not the registered-hypothesis promotion-gate figure (which is 50
and lives in the prospective-clock panel). No change to either computation.
- *Tradeoff:* Cheap, fast, removes the immediate misleading-display risk without
  prejudging Phase 6's fuller audit (which the work order already scopes: "audit and
  explain... do not silently adopt whichever produces the more favorable DSR").

**Option B — Do nothing before the freeze; leave Phase 6 to resolve both the label and
the computation.** 
- *Tradeoff:* Matches the work order's own phase sequencing exactly (this is explicitly
  a Phase 6, post-freeze task). Leaves an unlabeled, ambiguous "trials" figure live and
  publicly visible for the duration between now and the freeze plus however long Phase 6
  takes to reach it.

**Recommendation: Option A.** Labeling is not a resolution — it changes no computation
and prejudges nothing about which trial count is "correct" — so it does not conflict
with the work order's instruction not to silently adopt a favorable figure ahead of
Phase 6's full audit. It only prevents the live site from implying a false consistency
between two numbers that currently share a label but not a meaning.

**Clock implication:** None either way — this is a display/labeling question about
already-computed validation statistics, not a change to champion score semantics,
universe membership, or scoring inputs.
