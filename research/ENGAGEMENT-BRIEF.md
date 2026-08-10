# ValueSignal — Continuing Engagement Brief

**Hand this to a fresh session. It is written for someone with no prior context, and it is the
only document they need to read before starting.** Read `research/STATE.md` second for the
decision log; read the `research/results/*.md` reports when a specific finding matters.

---

## 1. What the system is

ValueSignal ranks US equities and manages existing positions. It publishes a static site from
JSON artifacts built by a Python pipeline.

| | |
|---|---|
| Universe | ~874 stocks, ~125 ETFs |
| Scoring | 32 metrics in 6 weighted categories, then bounded modifiers |
| Category weights | valuation 28%, profitability 26%, financial health 15%, growth 11%, capital allocation 10%, accounting quality 10% |
| Output | `public/data/advisor.json` → React site |
| Model version | 3.2.0 |

**Repository layout, and the boundary that matters:**

| path | what it is |
|---|---|
| `pipeline/` | production Python. Changes here change what users see. |
| `src/` | React frontend. |
| `research/` | the research framework. **Reads production code, never modifies it.** |
| `research/results/` | reports and the JSON they were computed from |
| `public/data/` | published artifacts |
| `.github/workflows/` | scheduled jobs; this is where anything needing network runs |

---

## 2. Your role

Senior quantitative researcher, financial-data engineer, and adversarial auditor. The objective
is **the most robust version of this system for ranking stocks and managing positions** — not a
better-looking backtest, and not a system that appears more confident.

The previous engagement ran Phases 0 through 6b of an eleven-phase programme. Phases 7–11
remain, plus a specific list of open data work. Both are in §6.

---

## 3. Hard constraints — these carried through the whole prior engagement and still hold

1. Research code lives in `research/`, alongside the live pipeline. **Do not overwrite
   production to make research easier.**
2. **One commit per task. Conventional commit messages. No squashing.**
3. **No new runtime dependencies without asking.** Research-only dependencies go in a separate
   optional group. (None have been added. The normal-tail inversion in
   `research/rank_statistics.py` is a bisection specifically to avoid pulling in SciPy.)
4. Deterministic seeds. Cached external data. Reproducible from a clean checkout.
5. **Do not touch** the options screening module, Firebase auth, or the GitHub Actions publish
   step, except where a task explicitly says so.
6. **Never present a simulation on restated fundamentals as evidence.** If point-in-time history
   cannot support a test, say so and skip it.
7. **Do not optimise around THG, CRUS, NEM or GMED.** They are audit examples, nothing more.

### Anti-patterns — each of these was tried, or nearly, and is prohibited

- Never impute, default, or fall back to a neutral value. **Absence is absence.** A missing
  metric is `None`, and the reason is recorded.
- Never tune weights so that today's top names stay on top.
- Never declare a winner from one lucky variant.
- Never manufacture certainty when the point-in-time history is too short to support it.
- Never soften a report because its conclusion is unwelcome.
- **Never patch a measurement gap into looking closed.** See §5, lesson 4.

---

## 4. What is already established. Do not re-derive these.

### 4.1 Point-in-time data (Phase 2 — complete)

Built from SEC EDGAR XBRL `companyfacts`, keyed on CIK, stamped with the date each filing was
*accepted*.

| | |
|---|---|
| Observations | 1,448,995 |
| Companies | 860 of 861 |
| Span | 2010–2026 |
| Restatements preserved | 117,837 |
| Median filing lag | 37 days |
| Storage | 352 MB across 100 shards |

Verified against Apple's real filings: FY2024 revenue $391.0B, first readable 2024-11-01, exact.

**Data defects found and fixed while building it. Do not rediscover these:**

| defect | resolution |
|---|---|
| Nine-month YTD cumulatives classified as annual (9,074 of 23,048 rows) | `nine_months` period type; store repaired |
| A duplicate method definition silently returned `{}` for every CIK lookup | renamed; AST duplicate-method test added |
| Quarter-boundary test used `>=` where SEC conventions need `>` | Apple Q3 FY2024 ends and Q4 starts on the same date |
| Split-adjusted closes read as traded prices | Apple's 2016 close reads $27.09 in cache, traded ~$108.37 |
| As-filed share counts multiplied by adjusted prices | gave Apple a $459bn market cap in July 2020 against $1.84tn |
| A ticker denoting two companies across a bankruptcy | Chord Energy: $0.12 → $31.00 in one session, a +39,130% month |
| Facts filed before their period end | rejected |

The share-basis reconstruction (`pipeline/pit_shares.py`) recovers splits from filers' own ASC
260 restatements, needing no external split feed. 212 splits recognised across 848 companies,
943 units mis-tags repaired, spot-checked against real market caps for AAPL, NVDA, AMZN, MSFT,
JPM, WMT and CSX at three dates each.

### 4.2 Factor results (Phases 4, 5, 5b, 6, 6b — complete)

**The benchmark: equal-weighting the universe returned 18.0% annualised at a Sharpe of 0.99 over
2017–2026.** Every comparison is against that, not against zero.

Top-decile Sharpe versus the universe's 0.99:

| factor | vs. universe | verdict |
|---|---|---|
| momentum_12_1 | +0.41 | sorts, strongly |
| quality_and_momentum | +0.40 | sorts, most reliably (monotonicity +0.81) |
| quality_roic | +0.30 | sorts **on risk, not return** |
| value_quality_momentum | +0.26 | sorts |
| profitability (GPA) | +0.12 | does not sort |
| low_accruals | +0.11 | sorts weakly |
| value_and_momentum | +0.05 | barely |
| **value_earnings_yield** | **−0.21** | **actively harmful** |

**Per-metric information coefficients: none of the 32 survives multiple-testing correction.**
Largest t-statistic +2.4 against a Bonferroni threshold of 3.163. Critically, **this sample
cannot resolve an IC below ~0.028**, and every effect observed is smaller. "Not significant" is
partly a statement about nine years of data — do not report it as "proven worthless".

What the sample *does* support is direction and coherence: four of five testable valuation
inputs have negative ICs, hit rates below half, and Sharpe ladders between −0.72 and −0.93. The
same result appears in Phase 4's standalone factor, Phase 5's per-metric ICs, Phase 5b's raw
values, and Phase 6's category ladders — **four independent code paths, one answer.**

**Redundancy, measured:** `ev_to_fcf` ↔ `free_cash_flow_yield` at ρ=0.845 and 9.2% of the score
combined — and they sit in *different categories*, so the structure presents one opinion about
free cash flow as two independent judgements. Two further pairs are within-category
(`ev_to_ebit`↔`ev_to_ebitda` 0.826/10.9%, `ROE`↔`ROIC` 0.752/9.4%). **~29 points of weight
express about three opinions.**

### 4.3 Remedies that are closed. Do not propose these again without new evidence.

| remedy | why it is closed |
|---|---|
| Recalibrate band cutoffs | 26 of 27 metrics rank identically raw and banded (Phase 5b) |
| Remove the valuation category | tested out-of-sample; **worse** than the model it fixed (Phase 6b) |
| Reweight on measured ICs | nothing survives correction (Phase 5) |
| Rank on raw metrics rather than scores | identical ICs (Phase 5b) |
| Widen undersized peer groups to sector | rejected by Phase 1 regression tests, correctly (§5, lesson 3) |

### 4.4 The live-artifact findings — these do not depend on any backtest

**The published leaderboard ranks data volume.** 147 of 874 companies carry the
statement-derived categories; **all of the top 100 come from that 147**; no company without them
places above #127; rank correlation between categories-resolved and score is +0.44.

Root cause, now fixed: of a 150-company statement budget, ~110 slots were ordered by descending
*pre-enrichment* score. Enrichment supplies the metrics that raise a score, so the data went to
whoever already had it. Those slots now follow staleness. **Verify this worked** — see §6.1.

---

## 5. Lessons from the prior engagement. These are the most valuable part of this document.

**1. Split the sample before you recommend anything.** Phase 5 found four valuation multiples
inverting and the obvious conclusion was to drop the category. Designed on 2017–2021 it looked
like a clean fix: Sharpe 1.17 against the live model's 1.06, ladder sloping the right way.
Tested on 2021–2026 it was **worse than the model it was fixing on every measure** — 8.5% against
15.1%, Sharpe 0.54 against 0.79. Shipping that recommendation would have degraded the product.
`research/candidate.py` has the harness: selection rule fixed in code, applied to the design
half only, before the test half is read.

**2. Information coefficient and decile Sharpe answer different questions.** ROIC has an IC of
+0.006 — nothing — and a top-decile Sharpe of 1.29 against the universe's 0.99. Both are
correct. IC asks whether a metric orders the cross-section *by return*; decile Sharpe asks what
happens if you hold its best names. **ROIC sorts by risk, not by return**, which is most of
what "quality" means and is invisible to a rank correlation. A contradiction between two
statistics is usually two different questions.

**3. When a regression test rejects your fix, it is probably right.** The peer-group fix
(widening an undersized profile group to its sector) was rejected by the Phase 1 tests. They
were correct: an insurer ranked against banks, exchanges and payment networks is the
universal-multiple error the profiles exist to prevent. The module's own principle — *a degraded
estimate is worse than an absent one, because it still reads as a measurement* — is the whole
point of the n≥30 gate.

**4. Some gaps must be measured, not patched.** 70 companies sit in 17 peer groups that can
never reach n≥30 — being classified precisely costs them the comparison. That is a
universe-size problem, not a code defect. `research/audit_peer_coverage.py` reports it rather
than closing it.

**5. Verify a claim against the code before repeating or refuting it.** The methodology page
made three assertions about validation rigour. One was materially false (survivorship
protection "in force" with 8 days of history and zero removals recorded). Two were **better
than assumed** — the deflated Sharpe machinery is real and thorough, and the out-of-sample
harness runs on every build and honestly reports `accumulating`. Do not assume a claim is
overstated.

**6. Expect to be wrong, and check your own prior work hardest.** In the last stretch of the
prior engagement, three of four findings were errors in its own earlier output: a band
hypothesis stated twice and refuted, a misattributed enrichment fix (the artifact predated the
fix by 13 hours), and a UI regression caused by its own field rename that made a data-quality
badge fire on 100% of rows. **The audits catch the auditor at roughly the same rate they catch
the original code. That is the main reason to trust them.**

**7. A sandbox network failure is not a project blocker.** An earlier session recorded SEC,
Yahoo and FRED as blocked and declared four phases impossible. They were blocked *in the
sandbox only*; GitHub Actions has full network. Anything needing network goes in a workflow
that commits its own output back to the repository —
`.github/workflows/backfill-pit-fundamentals.yml` is the pattern.

---

## 6. Open work

### 6.1 Short term — do these first

1. **Run `.github/workflows/measure-survivorship.yml`.** Survivorship is the binding limitation
   on every performance number in `research/results/`. The job exists, is tested, and has never
   run. It bounds the gap in *count*; it cannot correct returns, and the output says so.
   Requires the `SEC_USER_AGENT` repository secret, which is already configured.
2. **Verify the enrichment fix worked.** After several refreshes, run
   `PYTHONPATH=pipeline python research/audit_leaderboard.py`. `enriched_share` should climb
   well above 0.17 and `concentration.top_100.from_enriched_cohort` should fall below 100. If
   it does not, the budget change did not take effect and the cause is upstream of `enrich()`.
3. **Run the pipeline once with `FULL_UNIVERSE_RESEARCH=1`.** Quality-metric redundancy on the
   live path is still measured on 40 rows instead of 874.
4. **Widen `edgar_facts.CONCEPT_TAGS` before the next backfill.** Known gaps:
   `WeightedAverageNumberOfDilutedSharesOutstanding` is absent for ~15 filers (Exxon among
   them) and per-share-class for Alphabet; add
   `WeightedAverageNumberOfSharesOutstandingBasicAndDiluted` and
   `dei:EntityCommonStockSharesOutstanding`. No dividend-per-share or book-value concepts are
   collected, so no dividend or book yield is derivable. Retained earnings is absent, which is
   why `altman_z` cannot be reconstructed point-in-time.
5. **Resolve successor-registrant chains.** 13 tickers (XOM, BLK, APO, BG, TKO, DINO, NWE,
   TEAM, MRVL, APA, VTRS, PNFP, OZK) reorganised under a new CIK, so their predecessor filings
   are unreachable and they sit out fundamental factors while remaining in momentum. EDGAR
   submissions carry `formerNames` and the predecessor CIK.

### 6.2 Long term

- **Phase 7 — robustness.** Multiple-testing correction across every variant tried; subperiod
  and subsector stability; sensitivity to rebalance spacing, portfolio size and cost model. The
  machinery in `pipeline/evaluation.py` (deflated Sharpe, expected-max-Sharpe, PBO via CSCV) is
  real and unused — wire it to the research harnesses.
- **Phase 8 — calibration.** The score is published to 0.1 of a point. Nothing measured supports
  that resolution. Either establish it or coarsen the published number.
- **Phase 9 — guidance policies.** Four duplicated guidance implementations remain. The shadow
  policy (`decision-v2.0.0`) is evaluated but does not control production.
- **Phase 10 — timeliness, regimes, ranking.** The timeliness layer publishes `None` by design
  since Phase 1; nothing has replaced it. No free provider supplies broad forward consensus.
- **Phase 11 — deliverables.** A single coherent report over the whole programme.
- **Universe expansion.** 30 comparable medical device companies is a data requirement, not a
  code change. It is what would restore peer claims to the 70 stranded companies.
- **Point-in-time universe.** The genuine survivorship fix needs prices for delisted securities,
  which no current provider supplies.

---

## 7. How to work

**Before changing production scoring**, ask whether the change can be tested out-of-sample. If
it cannot, it is a hypothesis, and it belongs in `research/` until it can be.

**When you find something in the published artifact**, prefer it to a backtest finding. Artifact
arithmetic holds regardless of what turns out to be true about valuation, momentum or
survivorship, and it determines what users see today. `research/audit_leaderboard.py` and
`research/audit_peer_coverage.py` are the pattern: no network, no store, no backtest.

**When you write a number in a report**, verify it against the JSON it came from before
committing. Every report in `research/results/` was checked this way and two errors were caught
doing it.

**Correct your own prior findings loudly.** Several reports in `research/results/` contain
explicit corrections to earlier claims in the same file. That is the intended style, not an
embarrassment.

---

## 8. Verification

```bash
pip install --ignore-installed PyJWT -r pipeline/requirements.txt
PYTHONPATH=pipeline python -m pytest pipeline/tests -q     # 1646 passed
npm ci && npm test                                          # 515 passed
npm run lint && npm run build
python pipeline/check_ui_weights.py
python pipeline/validate_data.py
PYTHONPATH=pipeline python research/audit_leaderboard.py    # artifact only, no network
PYTHONPATH=pipeline python research/audit_peer_coverage.py  # artifact only, no network
```

Re-running the research programme from a clean checkout — no network, the point-in-time store
and price cache are both committed. Each is roughly 15–25 minutes:

```bash
PYTHONPATH=pipeline python -c "import sys,json; sys.path.insert(0,'research'); \
  import baselines; print(json.dumps(baselines.run(), indent=2, default=str))"
# also: composite.py (live model), features.py (per-metric IC), bands.py (raw vs banded),
#       candidate.py (design/test split)
```

**Branch:** `claude/valuesignal-audit-rebuild-638m8r`, 16 commits ahead of `main` at the time of
writing. Develop there; merge to `main` only when asked.
