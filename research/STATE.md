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
| 2 | Point-in-time data integrity | **2.1 verified against live SEC (861/910, 0 ambiguous); 2.2 written, awaiting a `sample` run; 2.4 done; 2.3/2.5 open** |
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
149fc3f  Merge the ValueSignal integrity audit and Phase 1/3 remediation  (merged to main)
31335a4  feat(integrity): screen implausible provider values and break the enrichment loop
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
| Enrichment feedback loop | **fixed** | `enrichment_rotation` admits 15 statement-starved names per refresh |
| 17% coverage cliff on two categories | **open** | needs `FULL_UNIVERSE_RESEARCH=1` run |
| Implausible provider values accepted unscreened | **fixed** | `plausibility.py` + `derive_margins` source guard |
| No point-in-time history | **job written, not yet run** | `build_pit_fundamentals.py` + `.github/workflows/backfill-pit-fundamentals.yml` |
| Entity keying by ticker, not CIK | **fixed in the new store** | `edgar_entities.EntityResolver`, fails loudly on ambiguity |

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

**D-2.4 — Plausibility violations drop the field; they never correct it.** The module can
establish that a number is wrong and cannot establish what the right number was. Guards live
at the source where the source holds the inputs (`derive_margins` owns both revenue figures,
so it owns the incremental-margin denominator test) and downstream as a backstop over
whatever the row carries.

**D-2.6 — Point-in-time observations are stamped with `filed`, never with the period end.**
A 10-Q for the quarter ending June 30 is typically accepted in early August, and the gap
varies by weeks between filers. `backtest_historical.quarter_known_dates` approximates this
with a fixed `report_lag_days`; `edgar_facts.as_of` uses the real date, so a quarter is
invisible between its period end and its filing. That single property is what the whole
research program rests on.

**D-2.7 — Amendments are additional observations, never overwrites.** A restated-fundamentals
provider destroys the original. companyfacts carries every filing that ever reported a
period, so `edgar_facts.restatements` can report both sides and a later analysis can ask how
often a decision made on the original would have been made differently on the revision. This
is the one thing the current data sources can never supply.

**D-2.9 — Entity resolution verified against the live SEC map on 2026-08-09.** 861 of 910
universe tickers resolve to a CIK (94.6%), **zero ambiguous**, zero CIKs claimed by two
tickers. The resolver is sound; proceed to fetching. The 49 that do not resolve are not
resolver failures and are now classified rather than pooled:

| Kind | Count | Meaning |
|---|---|---|
| `fund` | 3 | VOO, VGT, PINC. Funds file no operating-company financials; no CIK is correct. |
| `absent_from_data` | 45 | Configured in `advisor_universe.json` but absent from the published payload too. Acquisitions that closed and tickers reassigned — the universe file is stale. |
| `scored_but_unresolved` | 1 | AEP, scored live at 36.2 with no CIK behind it. The only case needing a person. |

Two ticker changes are confirmed in the SEC map itself: **BK → BNY** (CIK 1390777) and
**MMC → MRSH** (CIK 62709). Both companies still file; the universe holds their old symbols.

**PINC is the ticker-reuse defect happening live, not hypothetically.** The universe was
configured with PINC meaning Premier Inc; PINC now resolves to the PGIM Securitized Income
ETF, and the pipeline published a score of 41.1 for it. It is flagged `is_etf` so it never
reached the fundamentals model — the damage is contained — but it is the exact failure mode
section 10 of the audit described, with a live example.

**Universe hygiene is now a named open item:** 47 of 910 configured tickers never appear in
published data at all. That is both a wasted-fetch problem and a survivorship signal — those
names stopped trading and the universe still lists them.

**D-2.8 — The backfill writes raw facts, not derived ratios.** Deriving point-in-time ROIC or
EV/EBITDA from these observations is a separate step on purpose: the facts should be written
once and re-derived from as often as the derivation changes. Baking a derivation into the
store would mean re-fetching SEC every time the formula moves.

**D-2.5 — The plausibility screen is deliberately narrow.** Rules encode arithmetic and
accounting impossibilities, not opinions about companies. A margin above 100% is impossible;
a P/E of 3 is merely unusual and the module does not touch it. Measured rejection rate on the
committed universe: 0.8% of rows, one field each. A test asserts it stays under half the
universe — a screen that fires everywhere is not a screen.

**D-3.4 — NEM's small fall is reported as a small fall.** The gate expected a material fall.
Suppressing its cycle-contaminated metrics removed a maxed margin trend and FCF growth but
also removed gross-profits-to-assets, which was a drag. A material fall requires valuation
against a normalized mid-cycle commodity price, which needs a commodity price series this
pipeline does not ingest. Not faked. See "Next" below.

## Blockers

- **B-1 (critical).** No usable point-in-time fundamental history — 8 days. Blocks Phases
  4–10 entirely. Resolution: Phase 2.2, SEC EDGAR XBRL `companyfacts` keyed on `filed` dates.
- **B-2 (confirmed by probe, not assumption).** Outbound egress policy blocks every market
  data host this pipeline needs. Measured on 2026-08-09:

  | Host | Result |
  |---|---|
  | `www.sec.gov` | 403 on CONNECT (policy denial) |
  | `data.sec.gov` | blocked |
  | `query1.finance.yahoo.com` | blocked |
  | `api.stlouisfed.org` | blocked |
  | `www.alphavantage.co` | blocked |
  | `api.github.com` | 200 |

  The proxy status endpoint records the SEC denial explicitly as
  `connect_rejected / gateway answered 403 to CONNECT (policy denial or upstream failure)`.
  Per `/root/.ccr/README.md` a policy denial must be reported rather than routed around.
  **Phases 2.1, 2.2, 2.3 and 2.5 cannot be executed until these hosts are allowed**, and
  Phases 4–10 depend on 2.2. Ask the user to enable egress for `sec.gov`, `data.sec.gov`,
  `api.stlouisfed.org` and a price source before any further Phase 2 work is scheduled.

## Next, in order

1. **Run the backfill.** `.github/workflows/backfill-pit-fundamentals.yml`, in this order:
   `audit-only` (no fetching), then `sample` (25 companies), then `full`. Append-only and
   resumable. **Every run commits its report to `main`**, so a later session reads the
   outcome from the repo rather than from a run log:

   | File | Written by | What to read first |
   |---|---|---|
   | `pipeline/data/pit/entity_audit.json` | every run | `resolved` / `unresolved` counts, `ambiguous_tickers`, `shared_cik` |
   | `pipeline/data/pit/entity_map.json` | every run | the SEC ticker map this run resolved against, for reproducibility |
   | `pipeline/data/pit/fundamentals_manifest.json` | sample, full | per-company `resolved_tags`, `missing_concepts`, `earliest_period`, failures |
   | `pipeline/data/pit/fundamentals.jsonl` | sample, full | the observations |
   | `pipeline/data/pit/fundamental_restatements.jsonl` | sample, full | periods reported more than once |

   The code is unit-tested against fixtures but **has never touched the live SEC endpoint**,
   so the first `audit-only` run is the real test. Check the resolution rate before trusting
   anything downstream; a long `missing_concepts` list in the sample manifest means
   `edgar_facts.CONCEPT_TAGS` needs widening for tags real filers actually use.
   Do not start Phases 4–10 on `pipeline/data/backtest_cache/` in the meantime — that is
   restated Yahoo statements over today's survivors.
2. **Commodity mid-cycle valuation.** Candidate source: FRED PPI series (e.g. `PCU2122`,
   `WPU10`) plus LBMA/COMEX settle prices. Completes Phase 3.3 and makes D-3.4 resolvable.
3. **Run `FULL_UNIVERSE_RESEARCH=1` once** (needs a price/statement provider, so blocked by
   B-2). Quality-metric redundancy is currently measurable on 40 rows instead of 877. The
   ordinary path no longer starves outsiders — `enrichment_rotation` rotates 15 in per
   refresh — but one full sweep is still the fastest way to make Phase 5 possible.
4. **Sector profiles still unbuilt** (Phase 3.2): REIT AFFO/NAV, bank NIM/efficiency/ROTCE,
   insurer combined ratio and reserve development. All need inputs the pipeline does not yet
   derive; the registry declares them as `replacement_metrics` already.

## Verification for any future session

```
pip install --ignore-installed PyJWT -r pipeline/requirements.txt
PYTHONPATH=pipeline python -m pytest pipeline/tests -q     # 1489 passed
npm ci && npm test                                          # 508 passed
npm run lint && npm run build
python pipeline/check_ui_weights.py
python pipeline/validate_data.py
```
