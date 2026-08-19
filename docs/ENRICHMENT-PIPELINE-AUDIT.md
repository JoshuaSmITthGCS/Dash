# Enrichment Pipeline Audit

Phase 1 of the Round 7 work order ("Stabilize the Pipeline, Preserve the Champion, Build
the Measurement System"). Read-only research plus, per §2's autonomy list, three defects
that were unambiguous engineering/data-integrity fixes were repaired in the same session
(commits `8ec091e4`, `0ee5f5f8`, `a7c10656`) and are marked **FIXED** below rather than
left for a later phase — each is test-first, one defect per commit, full suite green
before and after (baseline 2,210 passed → 2,219 passed at time of writing, zero
regressions). Everything else in this document is diagnosis only, per Phase 1's mandate
not to begin implementation after the first finding.

Every claim below is cited `file:line`. Line numbers are as of commit `8ec091e4`'s parent
(pre-repair) unless a section says otherwise; repaired files' line numbers may have
shifted slightly post-fix.

---

## 0. A finding that changes this audit's own premise

The task brief frames A3 ("names a weak preliminary model never surfaces can never
acquire statement-derived metrics") as an open, unresolved defect, and frames Phase 5's
"rotating enrichment ladder" as new construction. **Both framings are stale.** Current
production code already contains a rotation mechanism —
`enrichment_rotation()` (`pipeline/fetch_advisor.py:1360-1388`, wired into
`select_enrichment_priority` at `:1425-1428`) — that admits 15 statement-starved names
per run (`ENRICHMENT_ROTATION_SIZE`, default 15, `fetch_advisor.py:76`), selected purely
by "never enriched, then longest since enriched," independent of preliminary rank, drawn
from the full ~910-name universe on every full sweep. It is unit-tested
(`pipeline/tests/test_fetch_advisor.py:76-108,154-166`) and live in the default path, not
gated behind `FULL_UNIVERSE_RESEARCH`.

`docs/ENRICHMENT-BIAS-ANALYSIS.md` and the `A3-FULL-UNIVERSE-ENRICHMENT` entry in
`pipeline/experiment_registry.py:140-157` both still describe the pre-rotation state
("seeded from the prior refresh's top 20 plus 5 challengers," no mention of rotation) and
cite numbers — 84/374 statement-enriched, ~24.5-point score gap — that the currently
committed `pipeline/reports/enrichment_bias.json` (generated `2026-08-19T19:53:51Z`, same
day as this audit) no longer matches: **158/839 statement-enriched, ~8.9-point gap.** The
gap has shrunk by roughly two-thirds since rotation shipped, consistent with it diluting
the selection-on-outcome confound the original doc flagged as unresolved.

**This does not make Phase 5 a no-op.** The existing rotation is a flat 15/run rotation
with no distinction between "ranked ladder" vs. "control arm," no AV-quota-aware
allocation, no coverage-regime tagging, and no retry-queue priority — none of Phase 5's
specific mechanics exist yet. But the §1 clock question ("does expanding the enrichment
ladder reset the clock?") already has a live precedent to reason from: rotation shipped
without anyone treating it as a score-semantics change, and it demonstrably moved
published scores for the ~74 additional names it enriched. See
`docs/QUESTIONS-FOR-OWNER.md` question 1.

`docs/ENRICHMENT-BIAS-ANALYSIS.md` and `pipeline/experiment_registry.py`'s A3 entry
should be updated to reflect this — not done here, as it is documentation of a past
measurement, not a repair, and out of this audit's read-only scope.

---

## 1. Architecture and call topology

### 1.1 Selection — who gets statement-enriched each run

Entry point: `select_enrichment_priority()` (`pipeline/fetch_advisor.py:1391-1429`),
called once per refresh (`fetch_advisor.py:1700-1705`). Tiers, in priority order:

1. **Focused** (`fetch_advisor.py:1409`) — explicit re-rank request (`ADVISOR_FOCUS_SYMBOLS`, the theme screen's "re-run" button), front of the queue.
2. **Incumbents** — prior published leaders, `previous_top[:20]` (`INCUMBENT_ENRICH_LIMIT`, `fetch_advisor.py:71`), filtered to this run's available set (`:1413-1418`); falls back to this run's own preliminary top 20 on a first run.
3. **Challengers** — next 5 preliminary names not already incumbents (`CHALLENGER_ENRICH_LIMIT`, `fetch_advisor.py:72`, `:1420-1423`).
4. **Rotation** — `enrichment_rotation()` (`:1360-1388`), 15/run by default, statement-starved names first, score-independent (see §0).
5. **Portfolio** — the 21 configured holdings (`pipeline/config/advisor_universe.json:portfolio_symbols`), unconditional on rank (`fetch_advisor.py:1424,1428`).

That combined `priority` tuple (~55-61 names) feeds `enrich()` (`:1201-1254`) as
`statement_priority`. `enrich()` ranks all `contexts` (this cycle's refreshed tickers)
priority-first, then by preliminary score, and attempts statements for
`ranked[:effective_extended_limit]` — `effective_extended_limit` is 150
(`EXTENDED_LIMIT`/`ADVISOR_EXTENDED_LIMIT`, `:1502,1670`) except under
`FULL_UNIVERSE_RESEARCH`, where it becomes the whole preliminary universe (`:1670`).

Production scheduling (`.github/workflows/refresh-advisor.yml:45-52,93-127`): full sweep
(`universe_mode=full`, all ~910 names get a preliminary pass) fires once daily at 07:00
ET; 12:00 and 15:00 ET are `universe_mode=fast`, restricted to the prior top 100
(`ADVISOR_FAST_UNIVERSE_SIZE`) + portfolio + a separate 120-name rotation slice for
*quote* freshness (`rotation_slice`, `fetch_advisor.py:1334-1357` — a different, price-only
rotation from the statement-enrichment one).

### 1.2 Provider topology

**Yahoo (`yfinance`).** Two independent request families:
- Price/quote: batched pre-warm via `yf.download()` (`fetch_advisor.py:489-524`, retried 4x exponential 2/4/8/16s via `retry_with_backoff`, `cache.py:347-362`); quotes via a bounded thread pool (`YAHOO_QUOTE_WORKERS=6`, `parallel_map`, `fetch_advisor.py:544-573`), paced by a 240/min token bucket (`cache.py:44` — a self-declared guess, not a documented Yahoo limit).
- Statements: `yahoo_extended()` → `extended_inputs()` (`fetch_advisor.py:611-658`, `fundamentals_extended.py:90-110`), 3 (annual) or 6 (quarterly, opt-in) DataFrame pulls plus one `.info` call per symbol, run from a **strictly sequential** loop (`fetch_advisor.py:1224-1251`) with `time.sleep(delay)` between symbols. No timeout parameter is visible on these calls — they go through `yfinance` internals directly, not `cache.cached_json`.

**Alpha Vantage.** `AlphaVantageClient.query()` (`pipeline/alpha_vantage.py:52-80`), single `requests.get(timeout=30)`, **no retry**. Pacing is a `min_interval=1.1s` instance throttle (`:36-43`), **not** `cache.py`'s `limiter_for("alpha_vantage")` (5/min, `cache.py:34`) — that limiter is dead code, never called from production (only referenced in `pipeline/tests/test_cache_and_providers.py:114`). Own file cache at `pipeline/cache/alpha_vantage/*.json`, `cache_hours=20` — a cache system entirely separate from `pipeline/cache.py`'s `DiskCache`. Capped to ≤5 tickers/run (`ALPHA_ENRICH_LIMIT`, `fetch_advisor.py:1530,1535`), 2-4 calls each plus SPY/macro calls, worst case ≈24/run.

**SEC EDGAR.** 540/min limiter (`cache.py:38,116`, under the 10/s fair-access ceiling), `parallel_map(max_workers=4)` (`fetch_advisor.py:888,922-944`). This is the real statement-level fallback for Yahoo failures (`edgar_enrichment.py:309-339`, invoked unconditionally at the end of `yahoo_extended()`) — **not** Alpha Vantage, which is driven purely by static ticker-list membership independent of whether Yahoo succeeded (`fetch_advisor.py:1138`).

### 1.3 Failure taxonomy — what the system can currently distinguish

None of the ten states the work order asks about (`success / partial / http_error /
timeout / parse_failure / rate_limited / quota_exhausted / legitimate_no_data /
inapplicable / not_attempted`) exist as one clean enum anywhere. What exists piecemeal:

| State | Where it's distinguishable | How coarse |
|---|---|---|
| `inapplicable` | `scoring_v2.py:120,125,131` `metric_status[...]["status"] == "suppressed"` | Genuinely distinguished — the one clean case |
| stage-level failure | `fetch_advisor.py:628-654` diagnostics counters (`statement_fetch_failed`, `info_fetch_failed`, `derivation_failed`) | Distinguishes *which call stage* failed, not *why* (http/timeout/parse/quota all collapse into one counter per stage) |
| provider success/failure | `alpha_failed`/`marketaux_failed` booleans (`fetch_advisor.py:1136-1197`); `provider_status: "success"/"error"` (`live_v2_validation.py:110-123`) | Binary only; exception class name reaches only `reason_code`/log text, not a fixed taxonomy |
| `legitimate_no_data` vs. everything else | `scoring_v2.py:129-131` `"unavailable"` bucket | One catch-all bucket for never-attempted, attempted-and-empty, and failed-to-parse alike |
| `not_attempted` | Nowhere explicit — only inferable by absence from a diagnostics counter or from `enrich()`'s shortlist loop | Implicit only |
| `rate_limited` / `quota_exhausted` | `AlphaVantageError` carries AV's own text (`alpha_vantage.py:72-76`), reaches `LOG.warn` (`fetch_advisor.py:1098`) | **Not in the published artifact** — collapses to the same `{}` as any other AV failure once it reaches `fetch_optional`'s return value (`fetch_advisor.py:1094-1099`) and `source_status.alpha_vantage.status` (`:2216-2218`) |

This taxonomy gap is exactly what §2's Phase 2 `enrichment_attempts.jsonl` schema is
designed to close. It has not been built in this session (see §7).

---

## 2. Confirmed defects

| # | Defect | Location | Severity | Blast radius | Fix | Status |
|---|---|---|---|---|---|---|
| 1 | Statement-derived fundamentals (ROIC, EV/EBITDA, Piotroski-F, Altman-Z, accruals) silently dropped from the published row for any ticker refreshed but not re-enriched this cycle | `fetch_advisor.py`: `enrich()` only merges statement fields into `context["snapshot"]` when re-enriched this cycle (`:1224-1254`); every refreshed ticker still gets a brand-new row built unconditionally (`:1785-1889`, `advisor_engine.build_research`); `carry_forward_rows()` (`:1315-1331`) only protects tickers **not polled at all**, confirmed by its own test (`test_fetch_advisor.py:284-295`) | **HIGH** | Up to ~100-160 of 910 tickers per fast refresh (contexts refreshed minus contexts actually reaching `enrich()`'s shortlist); systemic during a full-sweep Yahoo outage (2026-08-06 precedent, `edgar_enrichment.py:3-9`) for any symbol EDGAR PIT also lacks | Carry forward the last-resolved statement fields, tagged for provenance, mirroring `carry_forward_missing_sessions`'s existing guarantee for price history | **FIXED** — `carry_forward_statement_fields()`, commit `8ec091e4` |
| 2 | `pipeline/live_v2_validation.py` hardcodes `total_peer_count: 0, valid_peer_count: 0, percentile_status: "INSUFFICIENT_VALID_PEERS"` for all 10 representative-universe tickers unconditionally — never calls `peer_groups.canonical_percentiles()` | `live_v2_validation.py:113-115` (pre-fix); companion self-check `invalid_peer_sample_no_percentile: True` at `:61` is also a bare literal that can never fail | **MEDIUM** (blocks Phase 6's live validation surface entirely) | All 10 rows of the live validation representative universe, 100% of the time | Compute real peer pools from the committed production universe's own published valuation categories and call `canonical_percentiles()` | **FIXED** — `_peer_classification()`, commit `0ee5f5f8` |
| 3 | Two genuinely silent `except Exception` blocks — no log line at all, return value shaped identically to legitimate "no data" | `fundamentals_extended.py:96-100` (`extended_inputs.frame`, runs on every enrichment attempt for every symbol); `edgar_enrichment.py:321-322` (`merge_edgar_fallback`) | **MEDIUM** | A systemic cause (yfinance schema change, corrupt PIT shard) could suppress statement data universe-wide with zero trace — this is the closest known-mechanism candidate for the 2026-08-06 incident's blast radius before it was caught by the aggregate `enriched_count=0` gate | Add `LOG.warn` with ticker + exception type/message; no behavior change | **FIXED** — commit `a7c10656` |
| 4 | No retry/backoff on Yahoo statement fetch or any Alpha Vantage call | `fundamentals_extended.py:96-100` (`extended_inputs.frame`, single attempt); `alpha_vantage.py:52-80` (`AlphaVantageClient.query`, single `requests.get`) | **MEDIUM-HIGH** | A single transient network blip permanently fails that symbol/field for the entire refresh cycle; compounds defect #1 pre-fix (a transient failure during a rare enrichment turn pushed "last good" data out a full rotation cycle — now mitigated by #1's carry-forward, but the underlying fetch is still not retried) | Wrap in `retry_with_backoff` (already exists, used elsewhere in this file for price history) | **Not fixed this session** — real work (new retry call sites, needs its own test-first pass); flagged for the next autonomous-fix pass, not escalation |
| 5 | Alpha Vantage has no enforced or tracked daily-request quota, despite the pipeline's own docstring claiming one | `alpha_vantage.py:36-80` (client never imports/calls `cache.limiter_for`); `cache.py:33-34`'s 5/min AV limiter is dead code; module docstring at `cache.py:1-13` claims insulation from "Alpha Vantage's 25-request/day free cap" that does not exist in code | **MEDIUM** | Nothing currently prevents multiple runs in one day from cumulatively exceeding AV's real free-tier cap; the only real guard is the empirically-sized `ALPHA_ENRICH_LIMIT≤5` tickers/run, not a tracked budget | Wire `limiter_for("alpha_vantage")` into `AlphaVantageClient`, or replace the dead limiter with a real daily counter | **Not fixed this session** — needs a design decision on daily-vs-per-run tracking granularity; flagged for Phase 2 continuation |
| 6 | AV quota exhaustion is indistinguishable from "no data" in the published JSON — distinguishable only in text logs | `fetch_advisor.py:1094-1099` (`fetch_optional` returns `{}` regardless of cause), `:2216-2218` (`source_status.alpha_vantage.status` only `healthy`/`degraded`/`disabled_for_intraday_refresh`) | **MEDIUM** | Every AV-covered ticker, whenever quota is actually exhausted (currently unmeasured, since nothing tracks it — see #5) | Requires #5's tracking first, then thread a `quota_exhausted` reason code into `source_status` | **Not fixed this session** — depends on #5 |
| 7 | Renormalization inflates a category score when some of its metrics are missing/inapplicable/unresolved — the champion's live `bands` scoring mode divides by the weight of *present* metrics only, not the weight of the full category | `scorer.py:159-163` (`weighted_available`), used at `:560` (within-category) and `:636,670,764` (across-category, into `raw_score`). `required_for_score` (`applicability_matrix.json`) only guards `valuation`/`financial_health` for 5 profiles (insurers, banks, REITs) — **no other category, for any profile including `general`**, is protected | **HIGH — but this is a score-semantics finding, not a bug with an obvious fix** | Any category lacking a `required_for_score` declaration, i.e. every non-financial category for every profile | See synthetic example below — this changes what "the score" means for incomplete-coverage companies | **ESCALATED, not fixed** — see `docs/QUESTIONS-FOR-OWNER.md` question 2. §4 explicitly forbids fixing this without ownership sign-off: it is a scoring-methodology decision (renormalize vs. impute), not a data-integrity bug, and the codebase already has a built, tested alternative (`fixed_feature` mode, `scorer.py:705-784`) that is deliberately **not** the production champion |
| 8 | `build_research_evidence.py`'s significance check treats a missing t-statistic as `0`, reading as a confident "measured, not significant" rather than "not measured" | `build_research_evidence.py:70,97`: `abs(regression.get("newey_west_t_statistic") or 0) >= 2.0` | **LOW today, latent** | Currently benign — every t-statistic in the committed `benchmark_alpha_regressions.json`/`factor_regression_p0.json` is populated — but has no companion flag distinguishing "measured 0" from "unmeasured," in the one file whose own docstring (`:11-12`) states the opposite design principle | Match the file's own pattern (`_missing()`, `:50-51`) at field granularity | **Not fixed this session** — zero current blast radius, flagged for a future pass rather than spent on a defect with no live consequence |
| 9 | The theme screen's 39-45% vs. 85-89% evidence-resolution split is 100% explained by "never enrolled in statement enrichment," verified directly against committed data (see §5) | `themes.py:817-818` republishes `data_coverage_scalar()` as `research_coverage`; `enrich()`'s shortlist gate (`fetch_advisor.py:1201-1229`) is the actual cause | **Confirms A3's mechanism, not a new defect** | 24 of 37 `sector_peer` rows in the current theme screen | N/A — this is the expected, disclosed consequence of A3/§0's rotation cadence, and the frontend already discloses it (`src/pages/ThemeExposureScreen.jsx:311-317`) | **Diagnosed, not a defect requiring a fix** |

---

## 3. Suspected defects (kept separate — not confirmed material, or deliberately out of scope)

- **`TANGIBLE_BOOK_SECTORS` hardcoded outside the applicability registry** (`scorer.py:180-181,253-259`) — a second, narrower applicability decision (whether tangible book is *economically meaningful* for a sector) living outside `canonical_metrics.applicability_for()`, the otherwise-single authority. The code's own comment argues this is a different question (meaningfulness vs. applicability) than the registry answers, which is defensible, but the two lists could drift without either side knowing. Worth confirming `TANGIBLE_BOOK_SECTORS` stays in sync with `business_profiles.json`'s `replacement_metrics` declarations.
- **ETF gate duplicated across four sites** (`scorer.py:571,656,724`, `sleeves/_fundamentals.py:30`, `canonical_metrics.classify_profile:102`) — all currently agree, but none of the three scoring-mode functions delegate to `classify_profile()`'s own `is_etf` branch; they each re-read the raw flag independently. Same shape as the C6 dual-authority bug even though today's outcome is identical everywhere checked.
- **A second, independent renormalization scheme in the quality sleeve** (`sleeves/_fundamentals.py:54`): `sum(resolved_subscores) / len(resolved_subscores)` — equal-weight average of whichever of 4 categories resolved, discarding `category_weights` entirely. Not the same formula as `scorer.py`'s weighted renormalization (defect #7), so a quality-sleeve score can diverge from the champion's own category blend for an identical snapshot purely from which categories happen to be null. Not measured for materiality this session; flagged alongside #7 for the same ownership decision, since fixing #7 without also addressing this divergent second implementation would leave two inconsistent renormalization schemes live.
- **DSR trial-count discrepancy (201 vs. 50), explained but not resolved.** `public/data/validation/signal_metrics.json`'s `deflated_sharpe` metric independently computes `trials: 201` (`pipeline/signal_metrics.py:997`, reading every row of the raw category-weight optimizer's search space in `optimize_weights_results.json` — mechanical grid/random search iterations, unfiltered, no pre-registration). `pipeline/validation/harness_freeze.json:57-58`'s `dsr_trial_count_used: 50` counts distinct, pre-registered hypothesis families from `hypothesis_log.jsonl`, and is what the promotion criteria and the prospective-clock UI (`src/components/PerformanceMetrics.jsx:223`, `src/pages/portfolio/portfolioAnalyticsModel.js:40`) actually read. **These are two different populations under one word, computed by two uncoordinated code paths, with no cross-check between them anywhere.** The live `signal_metrics.json` honesty panel currently displays the 201-trial deflated Sharpe (0.2377) without noting it is not the promotion-gate figure. This is explicitly a Phase 6 task ("resolve the DSR trial-count discrepancy... do not silently adopt whichever is more favorable") — documented here for completeness, escalated as question 3 in `docs/QUESTIONS-FOR-OWNER.md` because choosing which figure the live UI should surface, or whether both should show labeled, is itself a decision affecting how validation evidence is presented before the freeze.

---

## 4. Cache-overwrite question, answered directly

**Can a failed refresh replace previously valid cached financial data?** Prior to this
session's fix: **yes**, via the mechanism in defect #1 above — not a literal disk-cache
overwrite (the raw statement DataFrames are never written to `DiskCache` at all; the
`"statements"` namespace, `cache.py:55`, is used only for `earnings_surprise`/
`earnings_calendar`), but functionally identical: the **published `advisor.json`** is the
persistent record, and any refreshed-but-not-re-enriched ticker's row was rebuilt without
merging its previously-published statement fields forward. Now fixed (commit `8ec091e4`).

**Confirmed-safe counterpart, unchanged:** `merge_edgar_fallback` only fills fields that
are `None` in the provider result (`edgar_enrichment.py:325-332`, `if result.get(key) is
None and value is not None`) — it never overwrites a resolved value. `enrich()` correctly
refuses to merge an all-null extended dict into the current run's own snapshot
(`fetch_advisor.py:1228`, gated on `extended.get("extended_coverage")`). All disk writes
are atomic (`common.py:163-179`, `cache.py:213-222`, tempfile + `os.replace`) — no
torn-write risk anywhere audited.

---

## 5. Missing-data behavior — defaults that look like data

Systematic search of `scorer.py`, `advisor_engine.py`, `canonical_metrics.py`,
`build_research_evidence.py`, `sleeves/` for `.get()` fallbacks, neutral constants, and
broad exception handlers in scoring paths.

**Confirmed-safe, well-engineered:**
- `NEUTRAL_SCORE = 50.0` (`scorer.py:702`) is the one true neutral constant in these files. It only applies in the non-champion `fixed_feature` mode and is never bare — every imputed metric is recorded in `imputed_metrics` with `normalization[metric]["status"] = "imputed"` (`scorer.py:743-746`) and `imputed_weight_fraction` published alongside (`:772`). This is the A1-NEWS-NEUTRAL failure done correctly.
- `news_intelligence.weighted_sentiment` returns `average: None, coverage: 0.0` rather than a neutral score on zero coverage (`pipeline/news_intelligence.py:178-188`) — confirms the A1 fix generalized beyond news scoring itself.
- `advisor_engine.py:794-806` `_reading()` replaced the exact prior bug (missing interest coverage read as 99x, missing drawdown as 0%) with a strict type check returning `None` on absence; downstream, `advisor_engine.py:905` publishes an explicit `unmeasured_inputs` list.
- No bare `except`/`except Exception` exists in `scorer.py`, `advisor_engine.py`, `canonical_metrics.py`, or `build_research_evidence.py`; the four narrow `except (TypeError, ValueError)` blocks in `canonical_metrics.py` (`:70,85,216,232`) return `None` or route to `invalid_observations` (`:217`), never a numeric default.

**Confirmed defect:** #7 and #8 in §2 above (renormalization; the `newey_west_t_statistic or 0` landmine).

### The renormalization synthetic example (defect #7, escalated)

Using live `profitability` weights from `pipeline/config/settings.json`
(`return_on_invested_capital 0.26, gross_profits_to_assets 0.22, return_on_equity 0.10,
free_cash_flow_yield 0.16, profit_margin 0.10, cash_conversion 0.16`) and the formula at
`scorer.py:159-163`:

Company A and Company B are economically identical on the four metrics both have (ROIC,
gross-profits/assets, ROE, FCF yield — all 80), and both have genuinely weak
profit_margin and cash_conversion (true value 20 on both). Company A's provider returned
all six metrics; Company B's provider simply failed to return profit_margin and
cash_conversion — an unrelated data-vendor gap, not an economic fact.

- **Company A** (6/6 resolved): `(80×.26 + 80×.22 + 80×.10 + 80×.16 + 20×.10 + 20×.16) / 1.00 = 64.4`
- **Company B** (4/6 resolved, missing weight .10+.16=.26): `(80×.26 + 80×.22 + 80×.10 + 80×.16) / 0.74 = 80.0`

**Company B scores 15.6 points higher (64.4 → 80.0, +24% relative) solely because two
data points are missing, not because it is a better business.** This flows into the
composite largely undamped: `fundamentals` carries 78% of `DEFAULT_RANKING_WEIGHTS`
(`advisor_engine.py:35`), and `build_research` uses the pre-multiplier `raw_score`
(`:1249`, `apply_coverage_multiplier=False`, `:1256`) — the Round 5 multiplier-removal
promotion (`docs/SESSION-HANDOFF.md`) means nothing downstream dampens this. The
existing publication gate (`min_publication_coverage: 0.35`, `data_health.py:1-25`)
does not catch it: Company B's *aggregate* fundamentals coverage stays ≈0.93 (only
6.76% of total weight missing), nowhere near the 0.35 floor that gate was calibrated to
catch gross provider outages, not concentrated single-category dilution.

**This is not an unknown pattern to the team** — `scorer.py:706-719`'s own comment cites
Round 4 measuring `Spearman(coverage, score) = +0.44` from exactly this construction, and
built `fixed_feature` mode (imputation at the neutral percentile instead of
renormalization, `scorer.py:705-784`) as the fix. But `SETTINGS["normalization_mode"]` is
`"bands"` — **the renormalizing method is the production champion; the imputation fix is
a challenger only** (`advisor_engine.py:1044-1079`). See
`docs/QUESTIONS-FOR-OWNER.md` question 2.

### Applicability — one authority?

**Yes, one authority**, with one narrow, disclosed exception. `canonical_metrics.
applicability_for()` (`canonical_metrics.py:158-171`, backed by
`applicability_matrix.json`) is the single source both the legacy champion path
(`scorer.suppressed_metrics()` → `applicability_for()`, `canonical_metrics.py:174-191`,
called from `scorer.py:243-260`) and the v2 path (`scoring_v2.py:102`) delegate to. The
old dual-authority bug that produced the C6 insurer/CRUS incident (`FINANCIAL_EXEMPT`, a
retired second `TANGIBLE_BOOK_SECTORS`-for-suppression list) is explicitly documented as
fixed (`scorer.py:166-179`). The one residual second site is the narrower
`TANGIBLE_BOOK_SECTORS` question noted in §3 (economic meaningfulness, not applicability
— a defensible distinction, flagged only as a drift risk).

---

## 6. Coverage semantics

`weighted_coverage()`/`category_coverage()` (`scorer.py:496-539`) compute **resolved ÷
applicable**, not resolved ÷ attempted: a metric suppressed for a company's profile is
removed from both sides (correct), but a metric simply never fetched (outside the
enrichment shortlist) looks identical to one fetched-and-failed — both are `None`,
counting against the numerator only, with no "attempted" bit anywhere.
`data_coverage_scalar()` (`advisor_engine.py:921-937`) is a fixed blend of three such
component coverages and inherits the same conflation; its own docstring (`:924-930`)
already warns it is "a completeness ratio and nothing more," not a reliability signal.

**No literal `evidence_resolution_pct` or `coverage_tier` field exists anywhere in the
repo** (grepped `pipeline/`, `src/`, `public/data/` for both strings, zero hits). What the
brief's "85-89% vs. 39-45%" language maps to is the theme screen's `research_coverage`
field (`themes.py:817`, republishing `data_coverage_scalar()`) alongside
`statements_available` (`:818`, `= bool(row.get("extended_coverage"))`).

**Verified directly against the committed `public/data/advisor.json`:**

| `candidate_source` | n | `research_coverage` range | mean | `statements_available=True` |
|---|---|---|---|---|
| `published_leader` | 13 | 0.69-0.89 | 0.872 | 13/13 |
| `portfolio` | 65 | 0.61-0.89 | 0.85 | 65/65 |
| `sector_peer` | 37 | 0.39-0.89 | 0.56 | 12/37 |

Isolating `sector_peer` rows individually shows a clean break: every row scoring
0.39-0.45 has `statements_available=False` (CRWD 0.39, CMC 0.40, DCI 0.40, CRDO 0.43, CSL
0.44, CMI 0.44, CR 0.44, CLH 0.44, WFRD 0.45, FANG 0.45); every row that *was* enrolled
scores 0.52-0.89 (ALLY 0.52, CACC 0.84, CXT 0.86, CHRD 0.87, PR 0.87, CARR 0.88, TXN
0.89), overlapping the leader/portfolio range entirely.

**Verdict: the 39-45% cluster is 100% explained by "never enrolled in statement
enrichment," not "attempted and genuinely failed."** This directly confirms A3's
mechanism is still live in practice today, even though (per §0) it is no longer
structurally permanent — it is a rotation-cadence lag, not a closed loop.

---

## 7. Peer-sample bug — diagnosis

**Root cause: a hardcoded stub, not the deliberate `n≥30` gate operating as designed.**
`pipeline/live_v2_validation.py:113-115` (pre-fix) wrote literal constants
`total_peer_count: 0, valid_peer_count: 0, percentile_status: "INSUFFICIENT_VALID_PEERS"`
into every result row, unconditionally, for all 10 tickers in `REPRESENTATIVE_UNIVERSE`
(`:19`). The module never imported or called `peer_groups.canonical_percentiles()` — the
real, correctly-designed peer-ranking function, with its genuine `MINIMUM_VALID_PEERS=30`
gate (`peer_groups.py:36`) — at all. The companion self-check
`invalid_peer_sample_no_percentile: True` (`:61`) was likewise a bare literal with no
condition attached, so it could never fail regardless of what the (nonexistent) peer
computation would have produced.

This is **not** (a) an empty source universe, (b) a mismatched join key, or (c) an
overly strict filter working as intended — those all presuppose a computation that runs
and returns nothing. Here, no computation ran at all; it is a straightforward
integration gap. **Fixed this session** (commit `0ee5f5f8`) by building each ticker's
peer pool from the committed production universe's own published
`fundamental_detail.categories.valuation` values (the same cross-section production's own
`canonical_percentiles()` call already uses, `fetch_advisor.py:1754-1758`) and calling
the real function.

For context: the *production* peer-percentile path (`peer_groups.py`, used in the actual
`advisor.json` build) was never broken this way — its `n≥30` gate is a deliberate,
documented, tested design choice (`research/audit_peer_coverage.py:1-27`,
`pipeline/tests/test_peer_coverage_audit.py`) that does legitimately strand ~17
precisely-classified profile groups averaging ~4 members each. That is a real, separate,
consciously-accepted limitation tracing to the same A3 root cause (thin statement-derived
coverage), not a bug, and this fix does not touch it.

---

## 8. Historical evidence — flicker verdict

### WO-5's 96.7% finding, re-examined

**Methodology confirmed as direct observation, not statistical inference.**
`pipeline/stability_report.py:105-131`'s `decompose_score_delta()` (reused verbatim by
`pipeline/p0_q2_turnover_attribution.py:120`) compares each metric's presence in
`normalized_metric_scores` between two consecutive `pit_store` refreshes directly: `if
(before is None) != (after is None): availability_changes.append(metric)`
(`stability_report.py:114-117`). This is a literal per-(ticker, metric) presence-flag
diff, not an inference from aggregates. The 96.72%/0.42% split
(`pipeline/reports/turnover_attribution.json`, cited at `docs/P0-Q2-TURNOVER.md:41-47`)
is the aggregate over 4 transitions / 5 refreshes: availability flicker 4,426 events
(96.72%), genuine change 131 (2.86%), band crossing 19 (0.42%).

**Verdict: SUPPORTED as a phenomenon, OPEN as to root cause — both true simultaneously,
and this audit narrows the open part.** The original analysis explicitly measured the
proximate mechanism (a presence flag flipping between refreshes) without establishing
*why* it flips — its own docstring names three candidate causes ("provider error vs.
cache staleness vs. enrichment-shortlist exclusion," `docs/P0-VERDICT.md:38-39`) and
states plainly it did not adjudicate between them. **This audit's own §6 finding closes
most of that gap**: the theme-screen coverage analysis shows a clean, deterministic break
between "enrolled in statement enrichment" (`research_coverage` 0.52-0.89) and "not"
(0.39-0.45), with zero ambiguous middle ground across 37 real rows. Combined with defect
#1 (pre-fix: any refreshed-but-not-re-enriched ticker silently lost its statement fields
every cycle it wasn't re-enriched), the dominant proximate cause of "flicker" was very
likely **enrichment-shortlist gating interacting with the pre-fix carry-forward gap** —
not pure provider unreliability. This is now partially mitigated by defect #1's fix
(statement fields no longer vanish on a not-re-enriched cycle), which should measurably
reduce flicker on the next several refreshes — see the recommended Phase 4 comparison
below. **Root cause remains formally OPEN** pending the `enrichment_attempts.jsonl`
instrumentation (§2's Phase 2 deliverable, not built this session) actually distinguishing
provider failure from shortlist exclusion in real time, but this audit narrows "OPEN" from
three undifferentiated candidate causes to one now-partially-fixed leading candidate.

Also note two caveats the original analysis already carried, worth preserving: it
measured 2-day-deep, 4-transition **live intraday refresh churn** (~400-name universe),
not the 5-year monthly backtest's turnover the WO-5 brief actually targeted (that
attribution was never run — network-blocked at the time); and the published 64.9%
backtest turnover figure is itself unreconciled against a later-measured 54.7-54.6%
champion turnover once the backtest cache was committed (`docs/ALGORITHM-RESEARCH-
RESULTS.md:323`) — a separate, undisclosed discrepancy this audit surfaces but does not
resolve.

### "0.891 autocorrelation vs. 50.8% turnover" — not a real connection

Both numbers exist but are **not measuring the same thing and are not connected by any
existing analysis**. `0.891` is `score_autocorrelation`
(`evaluation.rank_autocorrelation`, `pipeline/evaluation.py:704-726`,
`signal_metrics.py:470-474`, published at `public/data/validation/signal_metrics.json:
852-857`) — a weekly rank-persistence measure of the score itself on the backtest panel.
`50.8%` is the backtest's realized mean monthly turnover (`docs/MODEL-CARD.md:96`). **No
file in the repository measures "how many points does a name's score move when its
coverage tier flips."** This is genuinely unmeasured, not merely undocumented — it
requires the new observability instrumentation the work order's Phase 2 specifies
(`enrichment_attempts.jsonl`'s `coverage_tier_before`/`coverage_tier_after` fields would
make this directly computable) but that instrumentation was not built this session (see
§9/Recommendations).

---

## 9. A3, final answer

**Under the default production path (`FULL_UNIVERSE_RESEARCH` off), a company the
preliminary price-multiples model never ranks in the top ~20-25 is not structurally
locked out of statement enrichment.** `enrichment_rotation()` (§0, §1.1) admits it on
roughly a 3-month cycle at the default rotation size (15/run × one guaranteed full sweep
per weekday ≈ 61 trading days to cycle the ~910-name universe), independent of
preliminary rank, plus unconditional enrichment for the 21 portfolio holdings and any
explicit re-rank request. Once rotated in, a name's statement metrics now persist across
future cycles via defect #1's fix rather than vanishing on the next non-enrichment cycle.

This closes A3 as **PROMOTE** in the sense the work order's Phase 4 asks — a real,
tested, currently-live fix exists — but the fix predates this audit and its
documentation (`docs/ENRICHMENT-BIAS-ANALYSIS.md`, `experiment_registry.py`'s A3 entry)
is stale and should be updated to describe the rotation mechanism rather than the
pre-rotation closed loop. See `docs/QUESTIONS-FOR-OWNER.md` question 1 for whether
*expanding* that rotation (Phase 5's specific ladder design) resets the clock — a
distinct question from whether A3 is fixed.

---

## 10. What Phase 1/2 did not cover this session

For transparency, matching the work order's "no silent caps" principle:

- **`enrichment_attempts.jsonl` observability logging** (Phase 2's structured per-attempt
  schema) — not built. This is real, scoped new infrastructure, not a defect repair, and
  the work order's own phase ordering puts it after the defect-repair priority list. The
  three fixes in this session materially reduce what that instrumentation would need to
  explain (defect #1 removes the dominant silent-drop mechanism; the two logging fixes
  make two previously-invisible failure modes visible in text logs), but the structured
  JSONL schema itself remains future work.
- **Retry/backoff for Yahoo statements and Alpha Vantage** (defect #4) and **AV daily
  quota tracking** (defect #5/#6) — diagnosed, not fixed. Both are real, scoped,
  autonomous-eligible repairs under §2's list; deferred here in favor of completing the
  Phase 1 documentation deliverable within this session's time.
- **Phase 3's five clean trading days** — cannot be executed inside a single session;
  requires the repaired system to actually run in production across real calendar days.
- **Phase 4's failure report and Phase 5's ladder** — gated on Phase 3's data and on the
  §1 clock question being answered by the owner, respectively.
- **Phase 6's post-freeze infrastructure** (challenger registration, shadow portfolios,
  execution journal, Truth Dashboard, DSR resolution) — explicitly gated on the freeze
  date (2026-09-01) and is out of scope for a pre-freeze session.
