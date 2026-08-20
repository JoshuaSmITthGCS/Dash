# Feature Removal Candidates

Per the merged audit prompt's §18 "signal zoo" concern — features, code paths, or screens whose
maintenance cost exceeds their decision value, found while verifying the rest of this audit. This
is a candidate list for review, not a set of deletions already made (deletion is out of scope for
an autonomous pass unless explicitly cheap and confirmed dead — see the one exception below).

## Confirmed dead code — strong candidate

### `pipeline/scorer.py::run()` and its six supporting political-score functions

`score_track_record`, `score_committee`, `score_cluster`, `score_size`, `score_direction_recency`,
`score_policy` (lines ~30-90), and the `run()` entrypoint that composes them (lines 831-943+),
implement the broader 6-factor "political/congressional trade score" that
`docs/MASTER-METHODOLOGY.md:519-544` describes in detail (track record, committee relevance,
cluster detection, trade size, direction/recency, policy catalyst).

**This code has zero production callers and zero test coverage** — confirmed by exhaustive grep
across `pipeline/` (excluding the function's own definition) and `pipeline/tests/`. The only
in-repo reference to it running at all is `seed_mock_data.py`'s docstring, which just tells a
human to separately run `python scorer.py` after generating mock data — not an actual import or
call. Production congressional scoring runs through the much smaller, explicitly-scoped
`pipeline/congress_signal.py::score_congressional_buying` instead (a deliberate, documented,
reward-only exception to the "no political inputs" rule — see `docs/AUDIT-VERIFICATION-RESULTS.md`
§4.3).

**Why this matters**: `docs/MASTER-METHODOLOGY.md` describes this dead function's design as if it
were the live political-score mechanism, which is exactly the "documentation describes something
that doesn't run" pattern the merged audit prompt's §4 was built to catch — it's already caught
and disclosed in the same methodology doc's own text ("The two are not the same score and are
never combined"), but the dead code itself remains in `scorer.py`, available to be re-imported by
mistake or mistaken for live logic by a future reader who doesn't cross-check.

**Recommendation**: remove `run()` and its six supporting functions from `scorer.py`, or move them
to an explicitly-labeled `pipeline/archive/` or `pipeline/legacy_political_scorer.py` if there's a
reason to keep them as reference. **Not removed this session** — deletion of ~150 lines of scoring
logic, however dead, is a larger and more consequential change than the copy/label fixes this
pass's tier-1 authorization covers, and deserves a human decision on which of the two options
above (delete vs. archive) rather than a unilateral choice.

## Already addressed this session (not a removal, a fix)

### `/hud-demo`

Confirmed live, ungated, serving randomized fake data (`docs/AUDIT-VERIFICATION-RESULTS.md`
§4.7). The merged audit prompt calls for removal or route-gating "regardless of everything else."
**Gated this session** (`import.meta.env.DEV`), not deleted — it doesn't exist in the production
build, but the demo component and its supporting `src/lib/hudAdvanced.jsx` remain in the tree for
local development use. If there's no ongoing use for a HUD-styled component showcase, deleting the
page and its supporting library outright is a reasonable next step, but that's a product decision
(is this showcase still useful for building new HUD-styled components?) rather than a pure
correctness fix, so it wasn't made unilaterally.

## Explicitly NOT removal candidates (checked and found to be intentional)

- **Duplicate `momentum_12_1` implementations** (champion score vs. standalone Momentum screen) —
  not redundant, they answer different questions at different horizons with different resampling;
  see `docs/AUDIT-ROADMAP.md` item 27 for the disclosure/reconciliation proposal instead of removal.
- **Two Monte Carlo simulators** (user planning vs. strategy validation) — confirmed genuinely
  separate concerns (different language, different math, no shared code path), not accidental
  duplication.
- **`InsideInformation`/"Disclosed positioning" alongside the separate Politics and Institutional
  screens** — the merge screen's own copy already explains it shows only rare/flagged activity and
  points readers to "the individual Politics and Institutional screens for the full, unfiltered
  disclosures." This is intentional layering (a curated corroboration view on top of two complete
  screens), not redundant screens competing for the same job.
- **Swing model's five (really six, including announcement return) legs** — all confirmed live,
  weighted, tested, and non-overlapping with the champion score's momentum computation; no
  candidate for trimming found in this pass.
