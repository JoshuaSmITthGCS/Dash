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
| 2 | Point-in-time data integrity | **2.1 + 2.2 + 2.4 COMPLETE. 1,448,995 observations, 860/861 companies, 2010–2026, 117,837 restatements. Derivation, price and share-basis layers built. 2.3/2.5 open** |
| 3 | Industry conditioning | **COMPLETE** (3.1, 3.2 partial, 3.3 partial) |
| 4 | Baselines | **harness built, tested and committed (`research/baselines.py`). Full 2017–2026 run in flight; results land in `research/results/phase4_baselines.json`. Nothing is written up yet — if that file is absent, the run did not finish and must be repeated, not inferred** |
| 5–10 | Research program | not started. Survivorship is the binding limitation on every number Phase 4 produces |
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
...      (Phase 2 backfill: entity resolver, EDGAR facts, sharded store, derivation layer)
f251924  feat(pit): point-in-time prices and universe membership
10948be  feat(pit): reconcile filed share counts with the price series' split basis
0fac2d9  feat(research): baseline factor performance on point-in-time data
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
| No point-in-time history | **fixed** | backfill run: 1,448,995 observations, 860/861 companies, 2010–2026 |
| Entity keying by ticker, not CIK | **fixed in the new store** | `edgar_entities.EntityResolver`, fails loudly on ambiguity |
| Split-adjusted price levels read as traded prices | **fixed** (found in Phase 4, not in the brief) | `pit_market.py` — price floor off by default, liquidity screened on split-invariant dollar volume |
| As-filed share counts multiplied by adjusted prices | **fixed** (found in Phase 4, not in the brief) | `pit_shares.py` — split basis recovered from the filers' own ASC 260 restatements |
| Successor registrants lose their predecessor's filings | **open, disclosed** | 13 tickers (XOM, BLK, APO, BG, TKO, DINO, NWE, TEAM, MRVL, APA, VTRS, PNFP, OZK) |

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

**D-2.10 — The first live `sample` run returned nothing, and the cause was method
shadowing.** `SecEdgarClient` defined `company_facts` twice: a ticker-keyed one at line ~422
and the CIK-keyed one I added at ~222. Python keeps the last definition, so the backfill
passed a CIK into a ticker lookup, missed, and got back `{}` — which the job reported as a
successful fetch. 25 of 25 companies read "ok" with zero observations. Every unit test passed
because they all used a stub client with the method name I intended.

Three fixes, in order of durability:
- The CIK entry point is now `company_facts_by_cik`, and the ticker one delegates to it.
- `test_sec_edgar_contract.py` walks the AST of every pipeline module and fails the build on
  any class defining a method twice. It has a self-test so the detector cannot silently stop
  detecting.
- An empty payload is no longer a success: `collect_company` returns status
  `no_usable_facts` with the taxonomies actually present, so "fetched" and "usable" can
  never again be the same status.

The stubs in the backfill tests now use the real method name, so they exercise the surface
that exists rather than the one I meant to write.

**D-2.11 — The live sample worked, and found two parser bugs the fixtures could not.**
25 of 25 companies, **89,434 observations**, earliest period end **2010-01-30**, **4,247
restatements**. Values verified against reality: Apple FY2024 revenue $391.0B filed
2024-11-01, FY2025 $416.2B filed 2025-10-31 — both exact. The point-in-time property
demonstrably holds on real data: asked for Apple's annual revenue on 2024-10-31 the store
returns FY2023 $383.3B; on 2024-11-01, the day the 10-K was accepted, it returns FY2024
$391.0B.

Two bugs only real filings could surface:
- **Nine-month year-to-date cumulatives were classified `annual`.** Filers tag YTD figures in
  every 10-Q, so 9,074 of 23,046 supposedly-annual facts were three quarters of a year.
  Apple's nine-month $293.8B sat labelled annual against a true year of $383.3B — a
  derivation reading it would have understated by a quarter. `nine_months` is now its own
  period type.
- **Two facts were filed before their period ended** (AES share counts, a filer tagging
  error). Impossible for an as-reported fact and definitionally look-ahead; now rejected.

Both are pure functions of fields already stored, so `--repair` rewrote the existing 89,436
rows in place rather than re-fetching: 89,434 kept, 9,074 reclassified, 2 dropped. The
manifest records the repair.

**Concept coverage across the sample** (missing counts are mostly correct absences, not
gaps): inventory missing for 13 of 25 and gross_profit for 12 — service and financial
businesses report neither. `liabilities` missing for 10 is the one worth revisiting; many
filers tag only `LiabilitiesAndStockholdersEquity`. Tag heterogeneity is real and handled:
revenue resolved through `RevenueFromContractWithCustomerExcludingAssessedTax` for 16 filers,
`Revenues` for 7, `RevenueFromContractWithCustomerIncludingAssessedTax` for 2.

**D-2.12 — The store is sharded and deduplicated because the single file would not fit.**
The 25-company sample was 89,434 rows in 64.5 MB, projecting to **2.2 GB** for the full
universe — past GitHub's 100 MB per-file hard limit, and permanent weight on every clone of a
repository that also serves a website. Three changes, all lossless for every point-in-time
and restatement question:

- **Deduplicate to what is knowable.** 50.8% of the sample was a later filing repeating a
  value already filed — a 10-K carries the prior two years as comparatives. Only the *first*
  filing of a series and any *later filing whose value changed* affect what could have been
  known on a date, and the second case is a restatement, preserved exactly. Tests assert that
  `as_of` and `restatements` return identical answers before and after.
- **Constants to the header.** `source`, `source_taxonomy`, `transformation`,
  `reliability_tier`, `split_adjusted` and `point_in_time` were identical on all 89,434 rows
  and cost more than the values. `requested_at`/`observed_at` duplicated `filed`;
  `period_type`, `period_days`, `amended` and `ticker` are derivable; `source_field` is
  constant per (company, concept) and lives in the manifest. All are rehydrated on read, so
  consumers see the same record.
- **Shard by CIK.** One file per CIK-suffix bucket. Re-fetching one company rewrites one
  small shard rather than a 2 GB file.

Result: 64.5 MB → **11.2 MB** for the sample, 721 → 255 bytes per row, 82.6% smaller.
Full universe now projects to **~386 MB across 100 shards, largest ~10 MB** — comfortably
inside every limit. `test_pit_store.LiveStoreTests` fails the build if any shard approaches
50 MB, and the workflow runs that test *before* fetching.

**One-time cost already incurred:** the 61.5 MB unsharded `fundamentals.jsonl` is in git
history from commit `53b15de`. It is gone from the working tree but remains in the pack. Not
worth a history rewrite of a shared `main` unless clone size becomes a real problem.

**D-2.13 — The full backfill is done and the numbers are good.** 1,448,995 observations,
860 of 861 companies (OZK 404s at `companyfacts`), period ends 2010-01-01 → 2026, evenly
covered at 63k–99k observations per year, **117,837 restatements** captured. Median filing
lag **37 days**, p25 31, p75 50 — the real distribution a fixed `report_lag_days` was
approximating. Store: 352 MB, 100 shards, largest 6.6 MB.

**D-2.14 — `pit_derive` turns filed facts into ratios, and TTM is built from quarters.**
A naive "latest annual" reading is up to a year stale for eleven months of every year, so
trailing twelve months sums the four most recent non-overlapping quarters, synthesising Q4
as `annual - nine_months` for the majority of filers who never tag a standalone fourth
quarter. The synthesised quarter is invisible until *both* its inputs were filed.

Verified against Apple's real filings: revenue TTM $385.6B on 2024-10-31, $391.0B on
2024-11-01 (the day the FY2024 10-K was accepted, and the exact figure), $400.4B through
2025-03-29, $451.4B through 2026-03-28.

One bug this surfaced: SEC period conventions are inconsistent about boundaries — Apple's Q3
FY2024 ends 2024-06-29 and the quarter after it *starts* on that same date. A `>=` overlap
test rejected the adjacent quarter, left a hole in the year, and silently fell back to a
stale annual. Now `>`.

**Universe-wide coverage as of 2025-06-30**: 774 of 860 companies (90%) get a true
four-quarter TTM, 33 (4%) fall back to the latest annual, 53 (6%) have nothing usable.
Median derived-metric coverage 95%. Most-often-absent ratios are `gross_margin` (48% — many
filers report no gross-profit line), `interest_coverage` (27%) and `return_on_invested_capital`
(26%). Those absences are honest: no ratio is defaulted.

**D-2.15 — I was wrong twice about price adjustment, and the second error was the expensive
one.** First I recorded that today's adjusted closes embed future corporate actions and are
therefore unusable for a backtest. That is false for *returns*: `adj[t] = price[t] × F[t]`,
so a ratio between two dates cancels every factor outside the window. Verified on Apple
across its 2020 4:1 split — adjusted +78.24% against raw +76.71% over 2020, and −24.68%
against −24.88% over a split-free H1 2022, the small gaps being dividends.

Then I recorded that `raw_closes` were prices as actually traded, and that reading them fixed
the level problem. Also false. `raw_closes` is `yfinance` `Close` with `auto_adjust=False`,
which Yahoo delivers **split-adjusted and merely dividend-unadjusted**. Apple's 2016-08-08
close reads $27.09 there against roughly $108.37 as it traded — exactly a quarter, four years
before the split. Checked across every split in the cache: none appears as a jump in either
series.

So the repository holds two series and **neither is a traded price level**. Consequences,
each handled in code rather than described:

| Question | Series | Correction needed |
|---|---|---|
| Total return between two dates | `closes` | none |
| Dollar volume | `raw_closes` × volume | none — a split divides one and multiplies the other |
| Market cap | `raw_closes` × shares | shares must be carried onto the same basis (D-2.16) |
| Minimum price screen | *neither* | not recoverable; the rule is off by default |

The price floor is the one that cannot be salvaged, and it fails in the dangerous direction:
a company that later reverse-split is admitted historically at a price it never traded, and
reverse splits are what delisting candidates do. `minimum_dollar_volume` does that work
instead.

**D-2.16 — Market cap needed the filers' own restatements, not a split feed.** Filed share
counts are as-reported; the price series is on today's basis. Multiplying them gave Apple a
$459bn market cap in July 2020 against $1.84tn, and an earnings yield four times too high —
which does not average out, it puts a stock top of every value ranking.

ASC 260 requires share counts to be restated for splits in every period presented, so the
same period filed twice across a split *is* the split: Apple's June 2020 quarter appears as
4,354,788,000 filed 2020-07-31 and 17,419,154,000 filed 2021-07-28. Comparing a period
against itself is what makes this exact; consecutive periods fold buybacks in and read 3.79.

Two mistakes of my own inside this, both caught by testing against the store rather than
fixtures:

1. A candidate set of every fraction with terms up to 20 matches almost any ratio, so it
   recognises nothing — 19/5 is within a quarter of a percent of that same 3.79, and 13/5 of
   a 2.6× stock-funded acquisition. Replaced with the ratios boards actually declare.
2. A filer's units mis-tag is not a corporate action. CenterPoint reported 402 diluted shares
   in 2010 meaning 401,993,000. Treated as a basis change it multiplied a decade of earlier
   periods by a million. Scale errors are repaired per period and never propagate.

Result over the 848 companies with share counts: 212 splits recognised, 943 units mis-tags
repaired, 26 companies left with an unresolved period that publishes nothing, and three
residual discontinuities — RH, ELF, IRT — all pre-IPO and all before the price series starts.
Spot-checked against real market caps for Apple, Nvidia, Amazon, Microsoft, JPMorgan, Walmart
and CSX at three dates each.

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

- **B-1. RESOLVED.** Point-in-time fundamentals now cover 2010–2026 for 860 of 861 companies.
- **B-2. RESOLVED — and it was never what it looked like.** This sandbox's egress policy
  blocks `sec.gov`, `data.sec.gov`, Yahoo and FRED, which I recorded as a project blocker. It
  is not: the user's GitHub Actions runners have full network access, and the same code that
  cannot reach the SEC from here fetched 1.45m observations from there. **A future session
  must not conclude a data source is unavailable from a sandbox probe.** Anything needing
  network runs as a workflow; `.github/workflows/backfill-pit-fundamentals.yml` is the
  pattern — it commits its own output back to `main` so the result is readable afterwards.
- **B-3 (open, and now the binding one). Survivorship.** Every Phase 4 number is measured on
  the 860 companies that exist in today's price cache. Companies that delisted, were acquired,
  or went to zero between 2016 and now are absent, and no rule evaluated on this data can
  recover them. The bias is upward and unquantified. SEC's full filer list includes delisted
  registrants, so this is buildable; until it is built, Phase 4 supports statements about the
  *relative ordering* of strategies and no statement about their level of return.
- **B-4 (open, small, disclosed). Successor registrants.** 13 tickers reorganised under a new
  CIK and the SEC ticker map reaches only the successor, so their predecessor filings are
  unreachable under the current key. They carry no fundamentals for part of the window and
  therefore sit out fundamental factors while remaining in momentum. Fixable by resolving
  former-name/former-CIK chains from EDGAR submissions, which needs a network run.

## Next, in order

1. **Point-in-time universe (survivorship) — B-3.** The largest remaining contamination and
   the one that caps what every later phase may claim. Needs a network run: SEC's
   `company_tickers.json` plus submissions history covers delisted registrants, and the
   missing half is a price series for names Yahoo no longer serves. Write it as a workflow
   that commits its output, the way the fundamentals backfill does. Until it exists, no phase
   may state an expected return — only a relative ordering.
2. **Successor-registrant chains — B-4.** EDGAR submissions carry `formerNames` and the
   predecessor CIK. Resolving them recovers a full history for 13 tickers and removes a bias
   that currently favours momentum over every fundamental factor for those names.
3. **Phase 5, feature validation.** Now runnable on real point-in-time data: information
   coefficient per metric, decile monotonicity, Spearman redundancy across the 21 metrics
   `pit_derive` produces. This is where the Phase 0 finding about hidden factor overweighting
   gets measured rather than asserted.
4. **Commodity mid-cycle valuation.** Candidate source: FRED PPI series (e.g. `PCU2122`,
   `WPU10`) plus LBMA/COMEX settle prices. Completes Phase 3.3 and makes D-3.4 resolvable.
5. **Run `FULL_UNIVERSE_RESEARCH=1` once.** Quality-metric redundancy on the *live* path is
   still measurable on 40 rows instead of 877. Independent of the PIT work above, which uses
   its own store.
6. **Sector profiles still unbuilt** (Phase 3.2): REIT AFFO/NAV, bank NIM/efficiency/ROTCE,
   insurer combined ratio and reserve development. All need inputs the pipeline does not yet
   derive; the registry declares them as `replacement_metrics` already.

### Widening `edgar_facts.CONCEPT_TAGS` on the next backfill

Gaps found while building Phase 4, each of which costs coverage today:

- `WeightedAverageNumberOfDilutedSharesOutstanding` is absent for ~15 filers (Exxon among
  them) and sparse for Alphabet, which tags per share class. Add
  `WeightedAverageNumberOfSharesOutstandingBasicAndDiluted` and
  `dei:EntityCommonStockSharesOutstanding`.
- No dividend-per-share or book-value concepts, so no dividend or book yield is derivable.
- No split concept exists in `companyfacts` at all; `pit_shares` recovers splits from
  restatements instead, and does not need one.

## Verification for any future session

```
pip install --ignore-installed PyJWT -r pipeline/requirements.txt
PYTHONPATH=pipeline python -m pytest pipeline/tests -q     # 1595 passed
npm ci && npm test                                          # 508 passed
npm run lint && npm run build
python pipeline/check_ui_weights.py
python pipeline/validate_data.py
```

Re-running Phase 4 from a clean checkout (about fifteen minutes, no network — the store and
the price cache are both committed):

```
PYTHONPATH=pipeline python -c "import sys,json; sys.path.insert(0,'research'); \
  import baselines; print(json.dumps(baselines.run(), indent=2, default=str))"
```
