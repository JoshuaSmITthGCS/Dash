# ValueSignal Audit & Rebuild — Persistent State

**Written for a future session that has lost all context.** Read this file first.

---

## Engagement

Adversarial audit, integrity remediation, and evidence-based rebuild of the ValueSignal
scoring pipeline. Eleven phases. **Gating was lifted by the user** after GATE 0 ("just go
write through... just make it better"), so Phases 1 and 3 were executed without stopping.

**Branch:** `claude/valuesignal-audit-rebuild-638m8r`
**Repo root:** `/home/user/Dash`

## Hard constraints (still in force)

1. Research framework lives in `research/`, alongside the live pipeline.
2. One commit per task, conventional messages, no squashing.
3. No new runtime dependencies without asking. (None added.)
4. Deterministic seeds, cached external data, reproducible from clean checkout.
5. Do not touch: Firebase auth, the GitHub Actions publish step. The options screening
   modules were touched **only** to follow the `confidence` → `data_coverage` field rename;
   no options logic changed.
6. **No backtest until Phase 2 delivers point-in-time data.** If PIT history cannot support a
   test, say so and skip it. Never present a simulation on restated fundamentals as evidence.
7. Do not optimize around THG / CRUS / NEM. They are audit examples.

## Phase status

| Phase | Title | Status |
|---|---|---|
| 0 | Reverse-engineer the system | **COMPLETE** |
| 1 | Integrity fixes | **COMPLETE** (1.1, 1.2, 1.3 + two extras) |
| 2 | Point-in-time data integrity | **NOT STARTED — blocked on network** |
| 3 | Industry conditioning | **COMPLETE** (3.1, 3.2 partial, 3.3 partial) |
| 4–10 | Research program | **BLOCKED on Phase 2** |
| 11 | Deliverables | blocked |

## Commits on this branch

```
c011bf2  docs(research): Phase 0 audit — reverse-engineer the scoring pipeline
ac24342  fix(scoring): delete the fabricated timeliness score and guard against constant layers
cb3cc53  fix(peers): publish valuation tiers over a sufficient sample, or nothing
cd581b5  refactor(contract): rename the completeness scalar from confidence to data_coverage
790d0da  fix(guidance): stop the deterioration rule failing open, drop a duplicated factor
0e0a9ad  fix(conditioning): make the applicability registry authoritative on the live path
```

## What changed, by defect

| Defect (Phase 0) | Status | Where |
|---|---|---|
| False peer-relative claim | **fixed** | `peer_groups.py` — n≥30 gate, tiers not percentiles, averaged ranks kill the alphabetical tie-break |
| Fictional timeliness layer | **fixed** | `scoring_v2.py` publishes `None`; `layer_health.assert_layers_vary` fails the build on any constant layer |
| Coverage called confidence | **fixed** | renamed throughout pipeline, contract and frontend; schema 5→6 with read-time migration |
| Inconsistent industry conditioning | **fixed** | `scorer.py` reads `applicability_matrix.json`; required-for-score gate added |
| Deterioration engine fails open | **fixed** (found in Phase 0, not in the brief) | `advisor_engine.action_for` is None-safe; `unmeasured_inputs` published |
| `relative_strength_20d` duplicates `return_20d` | **fixed** (not in the brief) | champion `short_horizon_treatment: neutral` |
| Enrichment feedback loop | **open** | `select_enrichment_priority` still seeds from the prior top 20 |
| 17% coverage cliff on two categories | **open** | needs `FULL_UNIVERSE_RESEARCH=1` run |
| No point-in-time history | **open, critical** | Phase 2 |

## Decisions made, with justification

**D-0.1 — Audit against the published artifact, not a fresh run.** Every numeric claim is
computed from `public/data/advisor.json` (2026-08-09, 877 scored rows) so findings reproduce
without network access. Code reading establishes *why*; the artifact establishes *that*.

**D-0.2 — Correlation analysis on current cross-sectional data is legitimate.** Redundancy
between *inputs* is a statement about the feature matrix, not about returns. Any claim about
*predictive* value needs PIT data and is deferred to Phase 5.

**D-0.4 — Phase 2 is the binding constraint.** The PIT store holds **8 calendar days**
(2026-08-02 → 2026-08-09). Every test in Part II is unsupportable today.

**D-1.1 — No replacement confidence metric was introduced.** There is no calibration history
to build one from; the model's own `limitations` array says so on every row. Absence is
correct until Phase 8.

**D-1.2 — An unresolved layer classifies as unresolved, and never reaches "buy".** Structural
quality alone cannot establish that now is a favourable time to enter, so
`*_timeliness_unavailable` maps to watch/quality-watch, never buy.

**D-1.3 — Company confidence is the minimum over layers that *resolved*.** Folding an
unresolved layer's zero into that minimum is what pinned all 40 published rows to
`insufficient_evidence` while structural coverage sat at 92%.

**D-1.4 — Peer tiers, not percentiles, and the downstream ordinal is a tier midpoint
(16.7 / 50 / 83.3).** Coarse evidence, coarse effect. `sector_percentile_modifier` awards
three discrete outcomes rather than scaling continuously off a number with 7.7-point
resolution.

**D-1.5 — `validate_data` is schema-aware.** A payload is judged under the contract it was
written under; the schema-6 peer rules apply only to schema-6 payloads. The committed
schema-5 artifact is migrated at read time by `advisorV5ToV6`, which strips the fields the
new rules reject.

**D-3.1 — `TANGIBLE_BOOK_SECTORS` survives; `FINANCIAL_EXEMPT` does not.** The former is not
an applicability question about the business but about whether tangible book carries economic
meaning at all (it is an accounting accident for asset-light software). The latter was a
sector-string heuristic contradicting the registry.

**D-3.2 — The `semiconductor` profile covers the whole industry, not just fabless designers.**
Distinguishing fabless from integrated manufacturers requires a filing parse this pipeline
does not do. Suppressing the capex interpretation for the industry is better than applying it
wrongly to part of it. Documented in the registry rule text.

**D-3.3 — Customer concentration enters the live score; geographic concentration does not.**
The concentration objection (penalty-only modifiers reward untagged filers) is a *coverage*
problem, solved by separating "filing read, nothing disclosed" from "no filing read" — ASC
280-10-50-42 makes the former affirmative evidence. The geographic objection is a
*correctness* problem (tagged geography often means shipping destination, not end demand) and
is not solved by the same move.

**D-3.4 — NEM's small fall is reported as a small fall.** The gate expected a material fall.
Suppressing its cycle-contaminated metrics removed a maxed margin trend and FCF growth but
also removed gross-profits-to-assets, which was a drag. A material fall requires valuation
against a normalized mid-cycle commodity price, which needs a commodity price series this
pipeline does not ingest. Not faked. See "Next" below.

## Blockers

- **B-1 (critical).** No usable point-in-time fundamental history — 8 days. Blocks Phases
  4–10 entirely. Resolution: Phase 2.2, SEC EDGAR XBRL `companyfacts` keyed on `filed` dates.
- **B-2.** No network access has been used in this session. Everything is from committed code
  and artifacts. Phase 2 requires live EDGAR; without it the engagement stops here.

## Next, in order

1. **Phase 2.2 — EDGAR XBRL backfill.** The critical path. Needs network. Key by CIK
   (Phase 2.1) before anything else downstream.
2. **Commodity mid-cycle valuation.** Candidate source: FRED PPI series (e.g. `PCU2122`,
   `WPU10`) plus LBMA/COMEX settle prices. Completes Phase 3.3 and makes D-3.4 resolvable.
3. **Run `FULL_UNIVERSE_RESEARCH=1` once.** Statement metrics currently exist only for the
   previous run's top 20 + 5 challengers, so quality-metric redundancy is measurable on 40
   rows instead of 877, and the leaderboard cannot discover names a weaker model missed.
4. **Break the enrichment feedback loop** (`select_enrichment_priority`). No scoring work
   fixes a ranking that can only ever re-examine what it already liked.
5. **Sector profiles still unbuilt** (Phase 3.2): REIT AFFO/NAV, bank NIM/efficiency/ROTCE,
   insurer combined ratio and reserve development. All need inputs the pipeline does not yet
   derive; the registry declares them as `replacement_metrics` already.

## Verification for any future session

```
pip install --ignore-installed PyJWT -r pipeline/requirements.txt
PYTHONPATH=pipeline python -m pytest pipeline/tests -q     # 1458 passed
npm ci && npm test                                          # 508 passed
npm run lint && npm run build
python pipeline/check_ui_weights.py
python pipeline/validate_data.py
```
