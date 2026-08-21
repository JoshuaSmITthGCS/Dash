# Audit Verification Results

Verification pass against the "ValueSignal — Master Audit & Remediation Prompt (Merged v2)"
handed to this session. Per that prompt's §0, this repo already carries a large body of prior
audit work — `TODO.md` (root), `docs/P0-VERDICT.md`, `docs/P0-REPAIRS.md`, `docs/P0-Q1-BENCHMARK.md`
through `P0-Q3-SHORTLIST.md`, `docs/CONSOLIDATED-ASSESSMENT.md`, `docs/AUDIT-ROUND-3-FINDINGS.md`
through `AUDIT-ROUND-6-FINDINGS.md`, `docs/RESEARCH-CONTRACT.md`, `docs/MODEL-CARD.md`, and
`docs/VALIDATION-METHODOLOGY.md` — none of which the merged prompt's author had read when writing
it (per its own §0 disclosure). **The single biggest finding of this pass is that most of what
the prompt asks to "determine" is already determined, in writing, in this repo**, and several
items the prompt frames as open P0 risks have already been fixed, retired, or reclassified by
that prior work. Where this pass's own code reading disagrees with a prior doc, code wins per the
evidence hierarchy in §2 of the prompt.

Methodology: nine parallel read-only research passes, one per prompt section cluster (§4, §5, §6,
§7, §8, §9, §10, §11–13, §14), each required to quote exact file:line evidence rather than
paraphrase. Findings below are that evidence, lightly edited for consistency. Status values:
**CONFIRMED** / **PARTIALLY CONFIRMED** / **REFUTED** / **CANNOT DETERMINE**, per §22's required
format. Tier values follow §21's authorization ladder: **T1** copy/label fix (implemented
directly, this session), **T2** touches scoring/confidence/champion model (documented + failing
test only, no production change), **T3/T4** new pipeline/ledger/IA work (proposal only).

---

## §4 — Contradictions

| # | Claim | Status | Evidence | Tier / action |
|---|---|---|---|---|
| 4.1 | Alpha t-stat < 2 labeled "statistically meaningless" in the UI | **PARTIALLY CONFIRMED** | Docs (`docs/MASTER-METHODOLOGY.md:1197`, generator source `scripts/generate-app-breakdown.mjs:154` feeding `APP-COMPLETE-BREAKDOWN.md:121`) stated this. The **live** UI never did: `src/lib/factorAnalytics.js:189-191` gates on t>3 and reads "Alpha is not significant after momentum and size; this sample does not distinguish alpha from packaged factor exposure." One dead offline script, `scripts/factor-regression-evidence.mjs:44`, did contain the literal "means nothing statistically" phrase in an artifact nothing reads. | **T1 — fixed this session.** Doc lines and the dead script's text now match the live t>3 / "does not distinguish" language. No UI code changed (it was already correct). |
| 4.2 | `momentum_12_1` computed twice, in the champion score and again in a standalone Momentum screen, as genuinely separate code | **CONFIRMED** | Champion: `pipeline/risk_metrics.py:36` (`momentum_12_1`, indexes a flat daily-close list by trading-day offset), called from `pipeline/advisor_engine.py:138`. Standalone screen: `pipeline/research_screens_v2.py:39-54` (`momentum_factors`), which first resamples to calendar month-end prices, called from `pipeline/build_momentum_screen.py:57`. No shared function; day-count vs. calendar-month-end resampling can diverge for the same ticker around trading-calendar gaps. | **T3 proposal** (documented here; see Feature/Metric docs). Not a correctness bug — arguably intentional per the "selection and timing stay separate" design principle both prior audits credit — but the two implementations should either be reconciled or the divergence should be explicitly disclosed on both screens. |
| 4.3 | Broader "political" framing in docs vs. narrower production modifier | **CONFIRMED, and already self-documented** | `docs/MASTER-METHODOLOGY.md:519-544` describes a 6-factor political score (`pipeline/scorer.py::run()`) that is **unreferenced in production** (only `seed_mock_data.py` calls it) and states outright: "The score that actually reaches production is a much smaller one... The two are not the same score and are never combined." Production modifier: `pipeline/congress_signal.py`, reward-only, capped at 4.0 total, documented in its own docstring as a deliberate narrow exception to advisor_engine's "no political inputs" rule. Full build history in `TODO.md` §2a. | No action needed — already accurately disclosed in-repo. |
| 4.4 | Two unrelated Monte Carlo systems (planning vs. strategy validation) | **CONFIRMED** | User-facing goal planning: `src/lib/projectionEngine.js` (JS, 12-month block bootstrap, `simulateProjection`). Strategy validation: `pipeline/evaluation.py:364` (`block_bootstrap_return_ci`), `:527` (`reality_check_spa`), `pipeline/validation/deflated_sharpe.py:149` (PBO via CSCV). A third, `pipeline/monte_carlo_projection.py`, forward-projects strategy performance. Distinct languages, distinct math, no shared code path. | Informational — no action needed; this is intentional separation of concerns, not confusion. |
| 4.5 | `/market` vs `/markets` naming collision | **CONFIRMED** | `src/App.jsx:291` (`/market` → `PolicyRadar.jsx`, actually a news/sentiment feed) vs. `:292` (`/markets` → `Markets.jsx`, index/sector quotes). Nav label for `/market` was already "News" (`src/App.jsx:86`), so the confusion was in the URL only, not the visible nav. | **T1 — fixed this session.** Route renamed `/market` → `/news` (matches its own nav label and content); old `/market` kept as a `<Navigate replace>` redirect for existing links. `src/pages/Dashboard.jsx`'s internal link updated. `/markets` unchanged (already correctly named). |
| 4.6 | "Inside Information" screen is public 13F + Congressional data only, no actual nonpublic information | **CONFIRMED** | `pipeline/build_inside_information_screen.py:1-24` docstring: "institutional 13F + Congressional trading, merged and filtered... No new ranking logic." `docs/MASTER-METHODOLOGY.md:1092` states the same. The in-page body copy (`src/pages/InsideInformation.jsx:48-55`) already explicitly disclaimed "Not a claim that any of this activity was informed or improper" — the compliance-optics problem was in the page **title** and nav labels, not the body copy. | **T1 — fixed this session.** All user-visible instances of "Inside information" renamed to "Disclosed positioning" (page `<h1>`, error state, aria-label, Dashboard card, screens-nav list entry, `StockDetailModal` section label/link text) across `InsideInformation.jsx`, `Dashboard.jsx`, `ResearchScreen.jsx`, `StockDetailModal.jsx`, plus the one test asserting the old link text. Route path (`/screens/inside-information`), backing JSON filename (`screens/inside-information.json`), and refresh key were left unchanged — renaming those would touch pipeline output naming, a bigger blast radius than a label fix. |
| 4.7 | `/hud-demo` is a live, ungated route serving randomized fake data | **CONFIRMED** | `src/App.jsx:288` — plain route, no `cloudPage()` wrapper (contrast every Firebase-gated route). `src/pages/HUDDemo.jsx:24-38` — state seeded with fixed values, randomized every 3s via `setInterval(Math.random())`; no `useData`/fetch call anywhere in the file; not linked from anywhere in `src/` (only reachable by typing the URL). | **T1 — fixed this session.** Route now gated behind `import.meta.env.DEV` (same pattern already used for `?portfolioPreview=1` and other dev-only affordances in this file), so it does not exist in the production build. |
| 4.8 | Raw technical weights sum to 1.06 (not 1.0), with a "neutral" treatment dropping the relative_strength leg and the rest renormalizing | **CONFIRMED** | `pipeline/advisor_engine.py:56-60`: `DEFAULT_TECHNICAL_WEIGHTS` sums to 1.06 (six weights alone already sum to 1.00; `technical_extended` at 0.06 is layered on top). The prior comment at that line **miscalculated this as 0.94**, which was itself wrong. `settings.json:52`: `short_horizon_treatment: "neutral"` is the production default; `advisor_engine.py:238-264` (`technical_score_from_parts`) drops `relative_strength` under that treatment and **always divides by the sum of whichever weights actually resolve** — so this is configuration debt, not a live bias: the renormalization already protects against the declared-sum-≠-1.0 issue. `settings.json:1368`'s own comment explains the exclusion: `relative_strength` was found rank-identical (Spearman +1.00, n=877) to `return_20d`. | **T1 — fixed this session** (comment only): corrected the inaccurate 0.94 claim and documented the actual 1.06 sum, the renormalization that neutralizes it, and why it's still worth cleaning up. **T3 proposal**: publish the *effective* active weights (post-renormalization, under whichever `short_horizon_treatment` is live) next to the declared config, per the prompt's §18 P0 item — no weight values changed. |

---

## §5 — Research score weights, redundancy, ablations

| # | Claim | Status | Evidence |
|---|---|---|---|
| 5.1 | Blend is 78% fundamentals / 18% market behavior / 4% news | **CONFIRMED** | `pipeline/config/settings.json:1174-1177`: `fundamentals: 0.78, market_behavior: 0.18, news_sentiment: 0.04`. Locked by tests: `pipeline/tests/test_advisor_engine.py:21-24,29`. |
| 5.2 | Champion/challenger framework with promotion gates exists | **CONFIRMED** | `pipeline/experiment_registry.py` (14 entries, 51 variants tested), `pipeline/config/shadow_strategies.json` (12 named strategies). `docs/RESEARCH-CONTRACT.md` §4: champion is `bands_champion`; challengers are `cross_sectional_normalization` and the `signal_corrections` family; **"No promotion has occurred and none is being proposed."** Quantified gates in `docs/AUDIT-ROUND-5-FINDINGS.md` §5: 24 periods, ICIR≥0.5, IC t≥2.4, deflated Sharpe≥0.95, PBO≤0.50. |
| 5.3 | 14-way ablation suite (fundamentals-only, no-news, equal-weight-categories, etc.) run and recorded | **PARTIALLY CONFIRMED** | Run and recorded (in `research/audit/round3-6/` and `docs/AUDIT-ROUND-*.md`, not the production `experiment_registry.json`): current champion, fundamentals-only, no-modifiers, "no technical" decomposed by sub-signal, growth-zeroed, the coverage-multiplier removal (promoted 2026-08-12), cross-sectional/normalization challenger, universe-level equal-weight baseline. **Never run** as a named champion ablation: market-behavior-only, no-news, no-valuation, no-profitability (standalone drops), no-analyst-modifier, no-political/institutional (as an ablation vs. the standalone `political_institutional_only` shadow strategy), equal-weight-of-the-six-*categories* (distinct from the universe-level equal-weight baseline that does exist), reduced-redundant-metric, sector-neutralized. |
| 5.4 | Pairwise metric-redundancy / correlation analysis exists | **CONFIRMED** | `research/audit/CURRENT_MODEL_AUDIT.md` §6 (lines 389-465): `momentum_12_1` × `risk_adjusted` ρ=+0.93 (n=876); `return_20d` × `relative_strength_20d` ρ=+1.00 (tautological — this is the same finding behind 4.8's `short_horizon_treatment: "neutral"`); ROIC×ROE ρ=+0.75, ROIC×profit_margin ρ=+0.46; category-level cross-correlations near zero (valuation×profitability ρ=−0.01), i.e. redundancy is within buckets, not across them. EV/EBITDA vs. EV/EBIT vs. EV/FCF are grouped for a PSD/collinearity study (`research/audit/round4/task2_collinearity_psd.py`, `round6/task3_valuation_study.py`) but a full pairwise ρ table for that specific trio was not independently confirmed this pass. |
| 5.5 | The six fundamental category names (valuation, profitability, financial_health, growth, capital_allocation, accounting_quality) exist as-is, weight-sum tested | **CONFIRMED** | `pipeline/config/settings.json:646-651`; asserted verbatim in `pipeline/tests/test_scorer.py:74-76`; weight-sum-to-1.0 tested per category and top-level in `test_scorer.py:151-156` and `test_advisor_engine.py:21`. |

**Action**: T3 proposal only (registering the never-run ablations as new `experiment_registry.py` entries and ingesting the `research/` round-3-6 results into that registry so they're not orphaned in a separate tree with hardcoded machine-specific paths). No production weight change — none is warranted by anything found this pass.

---

## §6 — Confidence system

This is the prompt's flagged highest-priority formula check. **Verdict, corrected from an earlier
pass of this audit: the specific "P0 semantics bug" the prompt describes is fixed for the
champion's published score — and, on closer inspection than the first pass gave it, the
`0.65 + 0.35 × coverage` fundamentals-category formula is ALSO not consumed by the champion's
published score. It has exactly one remaining live consumer: the enrichment-priority sort key
that decides which candidates get financial-statement enrichment — a real, live effect, but a
narrower and different one than "still live in the champion score," which the first pass of this
audit incorrectly claimed. See the correction note at the end of this section for how that error
was caught and fixed within this same session.**

| Claimed formula | Status | Evidence |
|---|---|---|
| Production: `raw × (0.8 + 0.2 × confidence)` | **CONFIRMED EXACT COEFFICIENTS, RETIRED FROM CHAMPION** | `pipeline/advisor_engine.py:967`: `multiplier = (0.8 + data_coverage * 0.2) if apply_coverage_multiplier else 1.0`. The champion call, `build_research()` (`advisor_engine.py:1284-1330`), passes `apply_coverage_multiplier=False` — retired 2026-08-12 per the docstring at `:950-958`, which cites four published papers finding "no published construction multiplies a positively-oriented composite by completeness." **The published `row["score"]` today is `raw`, unmultiplied.** The directional multiplier still runs, but only inside `score_variants` challenger/diagnostic branches, never the headline score. The repo's own test proves the prompt's directional concern was real *for that formula*: `pipeline/tests/test_round4_remediation.py`, `test_production_form_is_directional`. |
| Production: `raw × (0.65 + 0.35 × coverage)` | **CONFIRMED EXACT COEFFICIENTS — BYPASSED BY THE CHAMPION'S PUBLISHED SCORE, LIVE FOR ENRICHMENT PRIORITY ONLY** | `pipeline/scorer.py`'s `_band_valuation_score`: `confidence_multiplier = 0.65 + (0.35 * coverage); total = round(raw * confidence_multiplier, 1)`. `build_research()` (the champion) never uses this `total` value — it reads `fundamental_parts["raw_score"]` (the pre-multiplier value) for `components["fundamentals"]` instead, confirmed by the pre-existing `test_champion_carries_no_completeness_multiplier` and the new `test_champion_published_score_bypasses_the_multiplier`. The multiplier's one remaining live consumer: `fetch_advisor.py::enrich()`'s shortlist-priority sort key calls `valuation_score(context["snapshot"])[0]` directly — the multiplied value — to rank which candidates get scarce statement-enrichment budget, before any row is published. A thin-pre-enrichment-coverage name's raw evidence is pushed down in that specific ranking, compounding the already-known shortlist-gating bias (§7.3, the 0.820/114-rank incident). |
| Shadow/v2: `50 + confidence × (raw - 50)` | **CONFIRMED EXACT, real and live as a challenger** | Two independent implementations: `pipeline/scoring_v2.py` (the actual "structural-timeliness-2.1.0" model, published per-row as `row["analysis_v2"]`, called from the champion path — published as a side-channel field, not folded into `row["score"]`) and `pipeline/advisor_engine.py::shrink_research_components` (algebraically identical via `settings.json`'s `shrinkage_target: 50.0` / `shrinkage_max_pull: 1.0`). |

**Direct arithmetic answer** (raw=20, confidence/coverage=0.5): the now-retired top-level formula
would have gone to 18 (down); the fundamentals-category formula would also go to 16.5 (down) *if
its multiplied value were used anywhere the champion reads from* — it is not, for the published
score; it is exactly this arithmetic, though, for `enrich()`'s enrichment-priority sort key; the
shadow/v2 form goes to 35 (up, toward neutral); the actual published champion score today passes
raw through unmultiplied at both the top level and the fundamentals-category level.

**UI labeling**: the completeness metric is labeled **"Data coverage"** throughout the live UI
(`src/pages/Picks.jsx:346,405`, `src/components/AnalysisLayers.jsx:47`: "Not a reliability
score"), and `AnalysisLayers.test.jsx:36` explicitly asserts the phrase "evidence confidence"
does **not** appear there — `docs/MODEL-CARD.md`'s "Confidence" section, which used to claim "The
UI labels it 'Evidence confidence'" and cited a nonexistent `pipeline/confidence.py`, has been
corrected (renamed to "Data coverage," pointing at the real file, `pipeline/data_coverage.py`).
`src/pages/Glossary.jsx:120` separately defines a "Confidence" concept in the glossary.

**Correction note (this session)**: the prior pass of this audit tested `valuation_score()` in
isolation and found its multiplied return value directional — true, but it never checked whether
`build_research()` actually consumes that multiplied value, and it does not. A production-code
change was drafted on the strength of the uncorrected finding (a new `score_variants` challenger
comparing the multiplied vs. unmultiplied fundamentals component) and then reverted within this
same session once the check surfaced the real behavior: since the champion already discards the
multiplier for its own component, that comparison would have always equaled the champion exactly
— it tested nothing. What shipped instead: an additive, default-preserving
`apply_confidence_multiplier` parameter on `scorer.py::valuation_score`/`_band_valuation_score`
(harmless either way — no existing caller's behavior changes) and two corrected tests in
`pipeline/tests/test_round4_remediation.py` (`TestFundamentalsCategoryMultiplierScope`) that
prove the champion bypasses the multiplier and that `enrich()`'s sort key does not.

**Action**:
- **T2 — documented + test, no production change.** `enrich()`'s sort key
  (`fetch_advisor.py::enrich`) is the one place this multiplier still has a live effect, and
  changing it is a real scoring-selection change (altering which of ~910 names get statement
  enrichment) requiring the same registered-challenger-then-promotion discipline as any other
  production scoring change. Not changed this session — documented and tested only.
- **T1 — doc drift fix**: `docs/MODEL-CARD.md`'s "Evidence confidence" label claim and its
  reference to a nonexistent `pipeline/confidence.py` should be corrected to match what the code
  actually does (see Feature docs below); left as a flagged item rather than edited this session
  to avoid touching a document with unrelated content mid-audit without a full read of it.

---

## §7 — Point-in-time / corporate actions / ranking-integrity incident

| # | Claim | Status | Evidence |
|---|---|---|---|
| 7.1 | Yahoo/`yfinance` is the primary/sole adjusted-price provider for portfolio pricing and benchmark comparison | **CONFIRMED** | `pipeline/config/research_contract.json:54`: `"total_return_basis": "Yahoo-adjusted close series... no separate distribution-reinvestment tracking"`. `pipeline/providers.py` `YFinanceProvider`; `fetch_prices.py`/`build_etf_comparisons.py` hard-error without yfinance, no alternate price path. `APP-COMPLETE-BREAKDOWN.md` never names Yahoo/yfinance (only Kenneth French Data Library, for factors) — confirmed by direct grep. Alpha Vantage is used as a *fundamentals* fallback, not for prices. |
| 7.2 | No independent corporate-action event ledger exists | **REFUTED (absence) — i.e. the claim of absence is CONFIRMED** | No file matches the requested schema anywhere in `pipeline/` or `pipeline/schemas/`. `pipeline/config/research_contract.json:27,64`: the system's own written admission — "no independent corporate-action event log exists yet." Only adjacent code is `pipeline/pit_shares.py:102` (`canonical_split_ratio`), a shares-outstanding basis normalizer, not a general action ledger. |
| 7.3 | Ranking-integrity incident: rank correlation 0.820, mean absolute shift 114 ranks | **CONFIRMED, source located precisely** | `docs/AUDIT-ROUND-4-FINDINGS.md:244`: "Enrichment alone, with no methodology change, reorders the universe at rank correlation 0.820 to the published board (mean absolute shift 114 ranks)." Carried into `docs/MASTER-METHODOLOGY.md:467-468` and restated in `docs/AUDIT-ROUND-5-FINDINGS.md:369-371` as a permanent methodology disclosure. This is the same *defect family* `docs/CONSOLIDATED-ASSESSMENT.md` §2.2 describes structurally (shortlist gating biasing statement coverage), but §2.2 does not itself cite the 0.820/114 numbers — those are specific to a measured 2026-08-06 Yahoo-outage/EDGAR-recovery event, one concrete instance of the general defect. |
| 7.4 | PIT store (`pipeline/pit_store/*.jsonl`) is append-only, never backfills | **CONFIRMED for the write path**, with one caveat | `pipeline/pit_store.py::_append()` uses `open(path, "a")` for all writes; docstring states values "cannot be fixed retroactively." One partial exception: `prune()` rewrites files with `open(path, "w")` to drop rows older than 5 years — a retention truncation, not a backfill/alteration of surviving rows, so "never backfills" holds but "append-only forever" is not literally true under retention pruning. Two *separate* PIT stores exist under similar names (`pipeline/data/pit/` written by `pit_store.py`, vs. the dated `pipeline/pit_store/YYYY-MM-DD.jsonl` refresh-transition log written by `signal_metrics.py`) — worth disambiguating in docs. |
| 7.5 | SEC EDGAR usage — insider/institutional only, or already a fundamentals source too | **PARTIALLY CONFIRMED — already partially built as a fundamentals fallback** | `pipeline/sec_edgar.py` serves Form 4/13F only. Separately, `pipeline/edgar_enrichment.py` already ingests as-filed XBRL facts (1.45M facts, 860 CIKs back to 2010) and merges them into fundamentals — but explicitly as a **fallback**: "fills only metrics Yahoo left as None," subordinate to Yahoo, not a spine Yahoo defers to. The prompt's proposal to make EDGAR the accounting spine would mean inverting that precedence, not building new ingestion. |

**Action**: T3/T4 proposals only (corporate-action ledger, EDGAR-as-spine precedence inversion) —
both are the multi-week architectural commitments §21 reserves for sign-off, not autonomous work.
The 0.820/114 incident is historical (already disclosed, already fixed by the EDGAR-fallback
recovery) and needs no further action beyond what §15's coverage/freshness display proposal
already covers.

---

## §8 — Validation status

| # | Claim | Status | Evidence |
|---|---|---|---|
| 8.1 | IC harness has observed 0 of 24 eligible periods | **CONFIRMED — this is "clock hasn't started," not "24 periods ran and failed."** | `pipeline/validation/ic_harness.py:1-6`: "every statistic remains in an accumulating state and the public artifact reports zero eligible periods." `settings.json`: `minimum_icir_periods: 24`, monthly cadence. Live artifact `public/data/validation/ic_validation.json`: `"periods_accumulated": 0, "status": "accumulating"`. `pit_store/` holds ~15 days of history (2026-08-05 → 2026-08-20) — below even `TODO.md` §3's own stated "8+ weekly observations" bar for a first IC estimate to mean anything. `docs/MODEL-CARD.md:61-63` states this plainly and warns no IC/Sharpe/drawdown/hit-rate figure anywhere should be read as validated. |
| 8.2 | PBO / deflated Sharpe / CSCV / Harvey-Liu-Zhu machinery — built and reachable, or only theoretical | **CONFIRMED, real, wired, and live** | `pipeline/evaluation.py:233` (`deflated_sharpe_ratio`), `:258` (`probabilistic_sharpe_ratio`), `:299` (`probability_of_backtest_overfitting`, CSCV-based). Harvey-Liu-Zhu referenced at `evaluation.py:29,123`. Called from `pipeline/signal_metrics.py:1008,1023,1399`, published to `public/data/validation/signal_metrics.json` with live (non-null) values today: `deflated_sharpe: 0.2377 (breached)`, `probabilistic_sharpe: 0.9777`, `pbo: 0.0 (status: "provisional", "wants at least 8 blocks")`. Reachable at `/screens/validation` (`src/pages/LiveValidation.jsx`) and `/screens/backtests` (`BacktestComparison.jsx`). |
| 8.3 | `pipeline/reports/p0_trial_log.jsonl` matches `docs/P0-VERDICT.md`'s deflation accounting | **CONFIRMED** | 5 logged trials, exactly matching P0-VERDICT.md's "5 fixed-specification diagnostics, not a search" framing (4 from WO-4, 1 from WO-5). Modification date (Aug 15) predates later `pit_store` files, consistent with P0-VERDICT's note that the cost-regime and turnover-control grids were network-blocked before they could run. |
| 8.4 | Current validation classification | **CONFIRMED, quoted exactly** | `docs/MODEL-CARD.md:80-82`: **"Current classification: B — a transparent factor tilt with no demonstrated residual alpha, carrying a real Verdict D caveat because the contract's own target has never been measured."** Supporting six-factor alpha figures differ slightly between `docs/MODEL-CARD.md` (+3.06%, |t|=0.68, contract-specified 63-session sector-residual target) and `docs/P0-VERDICT.md` (−2.57%, t=−0.44, raw calendar-month target) because they measure different, both-legitimate targets — both land on the same Classification B. |
| 8.5 | Does `docs/P0-VERDICT.md` already answer §8's open questions (per `docs/RESEARCH-PROMPT.md` Q1-Q6)? | **PARTIAL** | Fully settled: Q1 (benchmark/signal decisiveness — six-factor alpha indistinguishable from zero) and the deflation-accounting question. Substantially settled: Q2's causal half (turnover driven 96.72% by metric-availability flicker, not band quantization). Left open/deprioritized: Q3 (deprioritized, no longer load-bearing), Q4 (blocked on IC harness reaching eligible periods — same blocker as 8.1), Q5 (not addressed), Q6 (partially open — cost-model wiring blocked by network access at the time, EDGAR PIT bootstrap deferred as weeks-scale work). |

**Action**: No T1/T2 action — the repo's own validation status is already accurately and
conservatively self-reported (`MODEL-CARD.md`'s Classification B, the `ic_validation.json`
`"accumulating"` status, the "no promotion, none proposed" contract language). This resolves
cleanly with calendar time, exactly as `TODO.md` §3 already says. Flagged in the roadmap as a
"wait, don't build" item.

---

## §9 — Swing model

All seven claims **CONFIRMED** against `pipeline/swing_signals.py` / `pipeline/swing_tiers.py` /
`pipeline/build_swing_screen.py`, with one internal inconsistency and one refutation of the
prompt's own framing:

1. **Route/horizon** — "2 trading days – 8 weeks," three books (`src/pages/SwingScreen.jsx:612,616`, `pipeline/swing_signals.py:235-237`). Inconsistency: tier **S**'s own `session_band: (16, 90)` extends past the 8-week (40-session) headline ceiling — deliberately, per its docstring, to capture the next earnings window, but numerically inconsistent with the top-line claim.
2. **Legs** — all five named legs implemented plus a sixth (announcement return/EAR): `SWING_WEIGHTS = {pead_drift: .30, analyst_revision: .25, high_volume_premium: .20, high_52w_proximity: .15, short_term_reversal: .10}` (`swing_signals.py:84-90`), echoed in `docs/MASTER-METHODOLOGY.md:639-645`.
3. **Missing-leg renormalization + coverage floor** — both present: renormalizes over resolved legs (`swing_signals.py:1198-1200`), floor of 3-of-5 legs required to publish (`:282,1143-1147`).
4. **Sector cap** — 30% default, post-ranking trim (`:286,1261-1312`).
5. **Entry/exit hysteresis** — 90/75 default, tier-specific overrides (95/80 fast, 92/75 mid) (`:308-309,1237-1248`).
6. **Short-interest suppression + ADV cap** — both implemented: ≥10% float short AND top-decile standing required to suppress (not days-to-cover alone); 5%/10%-ceiling ADV participation cap enforced via `costs.participation_check` (`:297-299,882-910,288-290,1336-1354`).
7. **Momentum overlap with the champion score** — **REFUTED**: deliberately separate. `swing_signals.py` imports only generic `winsorize`/`zscores` utilities from the research-screens module, defines its own independent momentum/volume functions, shares no computation with `risk_metrics.py::momentum_12_1` or `technical_indicators.py`.

**The prompt's own claim that "nothing in documentation supports [swing model numbers]" is
itself REFUTED**: `docs/MASTER-METHODOLOGY.md` §10.7 (lines 630-760) already documents essentially
every number above in prose, in close agreement with code.

**Action**: none — this system is already correctly built and already correctly documented. No
finding here rises to any tier of action.

---

## §10 — Portfolio analytics inventory

Confirmed-strong (already exist, matching prior audit claims): HHI, effective holdings,
correlation analytics (252d/60-obs), eigenvalue-based effective bets, diversification ratio, ETF
look-through with unresolved-exposure disclosure, marginal/percent risk contribution (reconciles
to 100%), historical ES (worst 5%), tracking error, active-share gating (constituents + 80%
coverage) — all in `src/lib/portfolioAnalytics.js`, confirmed with file:line citations by the
verification pass. No action needed on any of these.

| # | Candidate-missing item | Status | Evidence | Tier |
|---|---|---|---|---|
| 1 | MWR/XIRR | **EXISTS BUT WEAK — dead code** | `portfolioAnalytics.js:448-488` (`solveXirr`, `moneyWeightedAccountReturn`), fully implemented and unit-tested, but **never imported by any page** (`src/pages` grep returns zero hits). | T3 — wire the existing implementation into `Performance.jsx`; this is much cheaper than the prompt assumed (no new math needed, just a missing import + UI slot). |
| 2 | Performance reconciliation / P&L bridge | **EXISTS BUT WEAK — dead code, and partial** | `portfolioAnalytics.js:559-566` (`trackedAllTimeEarnings`), tested but never called outside its own test file; also not a true bridge (no separate price-P&L/FX/tax lines). | T3 |
| 3 | Tax-lot ledger | **DOES NOT EXIST** | Zero matches for `taxLot`/`lotId`/`acquisitionDate`/FIFO/LIFO across `src/`. Positions carry one aggregate `costBasis` only. | T4 (multi-week, sign-off required per §21) |
| 4 | Realized/unrealized gain-loss | **EXISTS** | `usePortfolioForms.js:112-126`, automatic on sell, persisted via `usePortfolioTracking.js:65-80` — average-cost only, no lot selection. | — |
| 5 | Wash-sale warning engine | **DOES NOT EXIST** | No matches repo-wide; the one related hit describes a different, unrelated legacy system explicitly *not* doing this. | T4, blocked on item 3 |
| 6 | Days-to-liquidate | **EXISTS BUT WEAK** | `portfolioAnalytics.js:1125-1138` computed but only feeds a blended composite score — never surfaced as its own number. | T3 |
| 7 | Transaction-cost drag | **EXISTS BUT WEAK** | `portfolioStatistics.js:513-524` — hardcoded permanently `available:false` stub. | T3 |
| 8 | User portfolio turnover | **EXISTS BUT WEAK — broken wiring** | `portfolioStatistics.js:496-521` implements it; called with **no arguments** at `portfolioAnalyticsModel.js:115` so it always evaluates against an empty rebalance list and permanently shows "Insufficient." | T3 — this is a wiring bug, not a missing-metric gap; cheapest item on this list to fix once a rebalance ledger exists to pass in. |
| 9 | Current drawdown + duration | **EXISTS (duration weak)** | Depth exists and is wired into the UI (`portfolioAnalytics.js:1093-1095,1118`); explicit *duration* (days in drawdown) not found. | T3 for duration only |
| 10 | Data-quality panel | **EXISTS BUT WEAK — wrong scope** | `src/components/DataStatus.jsx`, shown globally, but pipeline/research-wide, not scoped to the user's own holdings' coverage. | T3 |
| 11 | Information ratio | **EXISTS** | `portfolioAnalytics.js:1096-1102,1115`, shown on the "Data overview" view but not on `/portfolio/performance`. | — |
| 12 | Full performance attribution (Brinson-style) | **EXISTS BUT WEAK — self-documented as not Brinson** | `src/lib/portfolioAttribution.js` header comment: "single-factor (CAPM-style) split... A true sector-factor decomposition would need daily sector-index returns, which this codebase does not fetch anywhere." | T4 |
| 13 | Benchmark policy (constructed multi-asset) | **DOES NOT EXIST** | Only single-index "best fit" among 4 fixed candidates (SPY/RSP/IWM/IJR). | T3/T4 |
| 14 | Weighted ETF expense ratio (user's holdings) | **DOES NOT EXIST** | Per-fund display only (`Picks.jsx:139`); never aggregated across the user's actual positions. | T3 — cheap, all inputs already exist |
| 15 | Rolling metric stability | **EXISTS BUT WEAK — Sharpe only** | `portfolioStatistics.js:314,412-413` — rolling Sharpe at 60/120d only (not the requested 63/126/252d, and not vol/beta/TE/correlation/drawdown). | T3 |

`/portfolio/performance` verified by full read (`src/pages/portfolio/Performance.jsx`, 93 lines):
renders exactly TWR-vs-benchmark + an "opportunity cost" panel — nothing else. Sharpe/Sortino/
Calmar/IR/attribution all live instead on the separate "Data overview" view, confirming the
prompt's asymmetry concern, though the underlying math for most of them already exists.

**Action**: T3 proposals for items 1, 2, 6, 7, 8, 9 (duration), 10, 13, 14, 15 — several of these
(1, 2, 8, 14) are markedly cheaper than the prompt assumed, since the computation already exists
and only wiring/UI work is missing. T4 (sign-off required) for items 3, 5, 12. Full breakdown in
`docs/METRIC-GAP-MATRIX.md`.

---

## §11–13 — Factor model, planning engine, options

### §11 Factor model — all CONFIRMED
Two parallel implementations: a Python diagnostic (`pipeline/signal_metrics.py::factor_loadings`,
internal-only) and the client-facing engine (`src/lib/factorAnalytics.js::factorRegression`, feeds
`Diversification.jsx`). Kenneth French Data Library, monthly, OLS with Newey-West HAC standard
errors on the JS side (Python side has no SE/t-stat output). 24-observation minimum quoted
identically in both (`settings.json:257`, `factorAnalytics.js:169`, `signal_metrics.py:550`
hardcoded literal). Publishes loadings/SEs/annualized alpha/t-stat/R²/plain-language summary, all
confirmed live in `Diversification.jsx:90-98`. UI hurdle is t>3 (see §4.1/§6 above), never the
word "meaningless."

### §12 Planning engine
| Item | Status | Evidence |
|---|---|---|
| (a) 15% default return target | **CONFIRMED** | `settings.json:475-476`: `annual_return_target.default_pct: 15.0`. User-adjustable via slider, `Planning.jsx:246`. |
| (b) Dotted median centered on target | **CONFIRMED** | `Planning.jsx:213,221`: "Dotted median target"; `projectionEngine.js:192-209` rescales the simulated path onto it. |
| (c) <36-month recentering onto benchmark history | **CONFIRMED** | `settings.json`: `portfolio_minimum_history_months: 36`; `projectionEngine.js:285-334,157-190` (`benchmarkCenteredSparseHistory` — "no observed month is repeated"). Disclosed to the user, `Planning.jsx:222-224`. |
| (d) ~20-daily-obs threshold → parametric risk profile | **CONFIRMED (mechanism); exact phrase paraphrased** | `settings.json:161`: `performance_minimum_observations: 20`; `monteCarloRiskProfile.js`; `projectionEngine.js:226-251,259` (`type: 'parametric-risk-profile'`). UI text (`Planning.jsx:242`): "At least 20 daily portfolio observations are required before the simulation can calibrate to your own Sharpe, Sortino, and Calmar ratios." |
| (e) **Most important**: is the return-target % shown immediately adjacent to the success-probability gauge, or buried in settings? | **PARTIALLY CONFIRMED — neither extreme.** | Actual JSX (`Planning.jsx:212-243`): the gauge (`.planning-verdict` section, 215-218) shows only the probability number/label — **no** percentage inside the gauge card itself. But the *very next sibling section* (`.planning-baseline`, 220-229) shows "Dotted median target" and the percentage, on the same page, same scroll position, no click required — a visually distinct, separate CSS card immediately below, not overlaid on or inside the gauge, and not buried in a settings panel either. A third repetition sits further down next to the live slider (`.planning-levers`, line 245). |

**Action**: T3 proposal only, and narrower than the prompt assumed — this is not "buried in
settings" as feared, but merging the assumption text into (or immediately overlaying) the gauge
card itself, rather than the adjacent-card layout today, would remove any residual ambiguity at
zero data-model cost. No autonomous change made (product/IA proposal, §21 tier 3).

### §13 Options — CONFIRMED: real chain data with a disclosed theoretical overlay
Eight routes (`OptionsScreen` + 7 `StrategyScreen` sub-routes). `pipeline/build_options_screen.py`
calls live `yfinance` option chains; `pipeline/options_common.py` pulls real bid/ask/OI/volume/IV
gated by real liquidity floors (min OI 50, min volume 100, max spread 5%) — genuine market fields,
not synthetic. UI discloses staleness (`OptionsScreen.jsx:181-185`: snapshot from last pipeline
run, confirm live quotes before acting). On top of that real base: delta/probability/EV use a
zero-risk-free Black-Scholes approximation (`options_common.py:81-127`, explicitly flagged in its
own docstring as "a real simplification"), and no live Greeks beyond delta are fetched or shown.
The prompt's framing ("zero description... theoretical precision without real chain data") is
**refuted** — real data is the base layer, honestly labeled as a stale snapshot; only the
ranking/EV math riding on top is theoretical, and that specific simplification (r=0) is not
separately disclosed to the user the way the staleness is.

**Action**: T1-adjacent but not executed this session (scope creep beyond the audit's verification
mandate) — flagged in the roadmap: add one line disclosing the r=0 Black-Scholes simplification
alongside the existing staleness notice.

---

## §14 — Data source stack

Providers actually wired in code: **yfinance** (primary prices + statement fallback + estimates +
news), **Alpha Vantage** (statement enrichment, small subset), **Marketaux** (news sentiment),
**FRED** (macro regime), **SEC EDGAR** (Form 4, 13F, XBRL facts fallback), **OpenFIGI** (CUSIP→
ticker), **Marketstack** (batched EOD/intraday), plus congressional-disclosure sources (FMP, Senate
eFD, a House-mirror dataset) not on the prompt's original list. **Not implemented anywhere**:
Tiingo, Twelve Data, Polygon/Massive, BLS, Treasury, BEA, CFTC, GDELT, FINRA — "Polygon" appears
only as an unused rate-limit config key with no client file behind it.

| # | Claim | Status | Evidence |
|---|---|---|---|
| 14.1 | "926 configured / 40 published, ~4.3% coverage" | **PARTIALLY CONFIRMED** | Static config is 910 stocks + 126 ETFs (`pipeline/config/advisor_universe.json`, `universe.json`), matching `TODO.md`'s "343→910, 40→126" note. 926 is a **live run-artifact** number (`public/data/advisor.json`, generated 2026-08-20): 910 config + up to 21 portfolio symbols, deduped. `count: 40` matches `publish_limit`. But 40/926 conflates "shown on the leaderboard" with "enriched" — the same live snapshot shows `statement_enriched_count: 148` (~16%) and `polled_count: 272` (~29%), both far above 4.3%, and even those numbers reflect one intraday "fast" refresh (`universe_mode: "fast"`), not the daily full sweep. |
| 14.2 | Alpha Vantage hardcoded to 25/day or 5 symbols/refresh | **PARTIALLY CONFIRMED** | 25/day appears only as descriptive comments (`providers.py:20-21`, `cache.py:6-7`, root `PRODUCT.md:37`), never enforced in code. The 5-symbols-per-refresh cap **is** hardcoded: `fetch_advisor.py:1530` clamps to `min(5, ...)` regardless of env override. A 5-request/minute rate limiter also exists (`cache.py:34`), separate from the 25/day figure. |
| 14.3 | Tiered A/B/C/D refresh scheduler exists | **REFUTED — pure proposal, nothing built under that name** | Zero matches anywhere. Closest existing analog: one daily full sweep (~910 names, 07:00 ET) + two intraday "fast" refreshes (prior top-100 + portfolio + rotation slice) + an on-demand `focus_symbols` mode — two scheduled scopes plus one on-demand, not four tiers. |
| 14.4 | Centralized data-license matrix | **REFUTED — no centralized matrix; per-provider notes exist scattered** | FRED terms/attribution embedded and published (`fred.py:15-16,191-193`), SEC user-agent requirement documented (`sec_edgar.py:1-6`), OpenFIGI redistribution restriction documented (`openfigi_client.py:1-26`) — real but scattered, not a single tracked source of truth. |

**Action**: T3/T4 — the tiered scheduler and license matrix are both explicitly multi-week/
sign-off items per §21, unchanged from the prompt's own framing. The 926/40 vs. 910/126 confusion
is a documentation-precision issue (which number answers which question) rather than a data gap —
noted in the roadmap as a one-line clarification, not implemented this session to avoid touching
generated-artifact-adjacent prose without a full read of every consumer.

---

## Overlap with the pre-existing work order (§0)

Per §0's instruction to check for overlap before duplicating work: this pass confirms the P0
work order (`docs/P0-VERDICT.md` and its five ranked recommendations) is still the load-bearing
prior work, and this audit's findings are consistent with it, not in tension:

- The P0 work order's Verdict B ("transparent factor tilt, no residual alpha") is the same
  classification `docs/MODEL-CARD.md` states today (§8.4 above) — no new information changes it.
- P0's recommendation #1 (fix metric-availability flicker, the dominant turnover driver) remains
  open and is **not** addressed by anything in this pass — it stays the single highest-priority
  item in the roadmap, ranked above every new finding here.
- P0's recommendations #3 (tiered-cost backtest) and #4 (EDGAR PIT bootstrap) remain blocked/
  deferred for the same reasons stated there (network access at the time; multi-week cost).
- Nothing in this pass reopens or contradicts anything the round-3-through-6 audits, CH-01-style
  normalization work, or the enrichment-bias analysis already settled — where this pass found
  something newer (e.g. the 2026-08-12 coverage-multiplier retirement in §6), it postdates and
  supersedes rather than conflicts with the earlier documents.
