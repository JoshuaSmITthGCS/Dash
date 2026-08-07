# P0 — Repairs (Phase 1)

Three structural fixes made before any diagnostic measurement, because each changes what later
numbers mean. This file is appended to after each work order.

---

## WO-1 — Manifest reported the wrong model

**Defect confirmed.** `pipeline/observability.py:30` built `run_manifest.score_distribution` from
`row["analysis_v2"]["structural"]["effective_score"]` — the shadow v2 canonical-metrics score —
instead of `row["score"]`, the published champion score shown in the UI and used for ranking.

**Fix.** Changed line 30 to read `row.get("score")`. One line.

**Regression test.** `pipeline/tests/test_observability.py`, two cases:
1. A synthetic payload where champion `score` and v2 `effective_score` diverge — asserts the
   manifest's `score_distribution` tracks `score`, not the shadow field.
2. Loads the committed `public/data/advisor.json` and asserts a freshly regenerated manifest's
   `score_distribution` matches the min/max/mean of the published champion `research[].score`
   values within tolerance. `skipTest`s if the artifact isn't present in the checkout.

**Verification.** Regenerated the manifest from the current `public/data/advisor.json`:

| | Before (buggy, as published) | After (fixed, regenerated) | Actual champion `research[].score` |
|---|---:|---:|---:|
| count | 40 | 40 | 40 |
| minimum | 60.0 | 71.4 | 71.4 |
| maximum | 77.8 | 83.4 | 83.4 |
| mean | 68.85 | 75.05 | 75.05 |

The regenerated distribution matches the published champion scores exactly (floating-point
tolerance only). The buggy figures (60.0–77.8, mean 68.85) undershoot the real range by roughly
7–11 points at every quantile — the manifest was certifying a materially different, lower-scoring
model than what shipped.

**Blast radius.** `pipeline/observability.py` was added in commit `cbc38ff` (2026-08-04), the
first commit to construct `run_manifest`. Since then, **23 commits** touched
`public/data/advisor.json`, of which **14** are `chore(data): refresh advisor research` /
`chore(data): rescore published research` commits — i.e. 14 actual pipeline runs that generated
and committed a `run_manifest.score_distribution` under the buggy code. Every one of those 14
committed manifests describes the shadow v2 score distribution, not the champion distribution
that was actually published alongside it. No other field in `run_manifest` depended on this line;
`stale_field_count`, `provider_conflict_count`, and the rest were computed from different paths
and are unaffected.

Quality gates after this fix: `pytest pipeline/tests` — 627 passed (625 pre-existing + 2 new,
0 failed); `validate_data.py` — 9 contracts validated; `npm run lint` — clean. `npm test` /
`npm run build` were not re-run for this commit since it touches no frontend code and were both
verified clean in the Phase 0 pass on this checkout (see `docs/P0-PREMISE-CHECK.md` commit); the
one known pre-existing gap — `src/App.test.jsx` failing to initialize Firebase because this fresh
checkout has no `.env.local` — is unrelated to this change and unaffected by it.

---

*(WO-2 and WO-3 to be appended after their respective commits.)*
