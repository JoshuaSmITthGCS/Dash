# ValueSignal Audit & Rebuild — Persistent State

**Written for a future session that has lost all context.** Read this file first.

---

## Engagement

Adversarial audit, integrity remediation, and evidence-based rebuild of the ValueSignal
scoring pipeline. Eleven phases, gated. Full brief is in the originating prompt; the
operative constraints are restated below so this file stands alone.

**Branch:** `claude/valuesignal-audit-rebuild-638m8r`
**Repo root:** `/home/user/Dash`

## Hard constraints (do not violate)

1. **Gated.** Stop at every GATE, report, wait. Never run ahead.
2. **No production edits in Phase 0.** Integrity fixes are Phases 1–3 only, each after its gate clears.
3. Research framework lives in `research/`, alongside the live pipeline. Never overwrite production.
4. One commit per task, conventional messages, no squashing.
5. No new runtime dependencies without asking. Research-only deps go in a separate optional group.
6. Deterministic seeds, cached external data, reproducible from clean checkout.
7. Do not touch: options screening modules, Firebase auth, the GitHub Actions publish step.
8. **No backtest until Phase 2 delivers point-in-time data.** If PIT history cannot support a
   test, say so and skip it. Never present a simulation on restated fundamentals as evidence.
9. Do not optimize around THG / CRUS / NEM. They are audit examples.

## Phase status

| Phase | Title | Status |
|---|---|---|
| 0 | Reverse-engineer the system (no edits) | **COMPLETE — awaiting GATE 0** |
| 1 | Integrity fixes | not started |
| 2 | Point-in-time data integrity | not started |
| 3 | Industry conditioning | not started |
| 4 | Targets, universes, baselines | **blocked on Phase 2** |
| 5 | Feature validation and redundancy | blocked on Phase 2 |
| 6 | Scoring method bakeoff | blocked on Phase 2 |
| 7 | Robustness, costs, multiple testing | blocked on Phase 2 |
| 8 | Calibration | blocked on Phase 2 |
| 9 | Guidance, position, stop policies | blocked on Phase 2 |
| 10 | Timeliness layer, regimes, ranking | blocked on Phase 2 |
| 11 | Deliverables | blocked |

## Deliverables produced so far

- `research/audit/PIPELINE-MAP.md` — data sources, request map, caching, dependency graph.
- `research/audit/CURRENT_MODEL_AUDIT.md` — defect trace, silent defaults, redundancy,
  precision audit, corrections to the brief's premises.

## Decisions made, with justification

**D-0.1 — Audit against the published artifact, not a fresh run.**
`public/data/advisor.json` (generated 2026-08-09T09:09:35Z, schema 5, model 3.2.0, 926-name
universe, 877 scored rows) is a real production output committed to the repo. Every numeric
claim in the Phase 0 audit is computed from it rather than asserted from code reading, so the
findings are reproducible without network access. Code reading establishes *why*; the artifact
establishes *that*.

**D-0.2 — Correlation analysis on current cross-sectional data is legitimate in Phase 0.**
Measuring whether two *inputs* are redundant with each other is a statement about the feature
matrix, not about returns. It needs no point-in-time data and carries no look-ahead. Any claim
about *predictive* value does need PIT data and is deferred to Phase 5.

**D-0.3 — Three of the brief's four confirmed defects are confirmed; the fourth is confirmed
with a corrected location.** See CURRENT_MODEL_AUDIT.md §7. The premise corrections do not
weaken the case; two of them make it worse.

**D-0.4 — Phase 2 is the binding constraint and is worse than the brief assumed.** The
point-in-time store holds **8 calendar days** of observations (2026-08-02 → 2026-08-09).
Not 8 months. Not 8 quarters. Eight days. Every test in Part II is unsupportable today, and
will remain so for years unless fundamentals are reconstructed from SEC EDGAR XBRL with real
filing dates (Phase 2.2). This is the single most important fact in the engagement.

## Blockers

- **B-1 (critical).** No usable point-in-time fundamental history. Blocks Phases 4–10 entirely.
  Resolution path is Phase 2.2 (EDGAR XBRL `companyfacts` with `filed` dates). Until then, no
  number produced by this engagement about future returns is admissible.
- **B-2.** No network access has been used in this session. Every finding is from committed
  code and committed artifacts. Phase 2 requires live EDGAR access; if that is unavailable,
  Phase 2 cannot complete and the engagement stops at Phase 3.

## Open questions for the user

Listed at the end of the GATE 0 report. Nothing in Phase 1 is blocked on them.
