# Methodology Remediation Record

One entry per defect measured in audit Rounds 3 and 4. Each entry states the issue, the
evidence, what was implemented, the measured before and after, what remains open, and the
promotion status. Numbers are pinned to the state in the header of
`docs/AUDIT-ROUND-4-FINDINGS.md`. Machine-readable companion:
`research/audit/remediation/before_after.json`.

---

## 1. Historical results were not reproducible

**Issue.** Nominally identical backtests produced -2.57% vs +0.43% alpha and 64.9% vs 50.6%
turnover.

**Evidence.** `research/audit/round4/task1_alpha_reconciliation.py`. The alpha gap
decomposes exactly: -0.03pp estimator, +1.97pp return construction, +1.06pp cache state.
The turnover gap is pure cache state, with first-rebalance pick overlap of 45% between
caches pulled a week apart.

**Implementation.** `pipeline/validation/experiment_manifest.py`: SHA-256 manifests over
git commit, config, universe, ticker list, price-cache tree, factor files, calendar,
execution assumptions, and cost model, embedded in every `backtest_monthly.py` artifact.

**Before/after.** Before: no run recorded its cache state, so the two published numbers
were irreconcilable by inspection. After: every artifact carries `experiment_manifest`
with a single `manifest_hash`, and equal manifests are the reproducibility contract
(tested in `test_round4_remediation.py::TestReproducibility`).

**Remaining limitations.** The manifest fingerprints inputs. It cannot make the mutable
Yahoo cache stable, only detectable. Honest historical re-runs need the EDGAR PIT spine.

**Promotion status.** Shipped. Not a scoring change.

## 2. Statement coverage collapse and silent degradation

**Issue.** After the 2026-08-06 provider outage the intended high-evidence metrics resolved
for 14 to 21% of names and nothing flagged it. Coverage predicted the published score at
Spearman +0.55.

**Evidence.** Round 3 section 7.1, `task6_batch_enrichment.py`, `docs/BASELINE-2026-08-06.md`.

**Implementation.** Two parts. `pipeline/edgar_enrichment.py` adapts the 1.45M-fact
as-filed EDGAR store into `derive_extended`'s statement shape and merges any metric the
provider left missing, automatically, inside `fetch_advisor.py::yahoo_extended`.
`pipeline/data_health.py` adds refresh-level health states (healthy, degraded, critical)
published as `statement_health`, and a per-name publication floor
(`min_publication_coverage: 0.35`) that demotes sub-floor names to INSUFFICIENT DATA.

**Before/after.** Mean fundamentals coverage 0.39 to 0.82 on the pinned refresh, 858 of
880 names gained metrics, EV/EBITDA 47 to 74%, Piotroski 55 to 93%, buyback yield 56 to
96%. A rerun of the 2026-08-06 outage now labels itself critical
(`test_round4_remediation.py::TestDataHealth`).

**Remaining limitations.** Altman Z caps near 66% because retained earnings is not an
ingested EDGAR concept. EDGAR quarterly flow concepts are not yet used for TTM freshness,
so EDGAR-derived values lag Yahoo's by up to one fiscal year for some filers. Ingesting
`retained_earnings` and quarterly aggregation are the natural next backfill increments.

**Promotion status.** Shipped as fallback enrichment plus gates. No score semantics changed
in the champion.

## 3. The score ranked data availability

**Issue.** Weight renormalization over resolved metrics plus two multiplicative
completeness penalties (scorer.py:642-643 and advisor_engine.py:861) made identical
evidence score up to 1.87x apart on coverage alone.

**Evidence.** Round 3 item 4. Round 4 decision rule: at restored 0.82 coverage the
production coverage-score correlation held at +0.514 (threshold +0.20), proving design
defect rather than outage artifact.

**Implementation.** `scorer.py::_fixed_feature_valuation_score` (mode `fixed_feature`):
every applicable metric keeps its full intended weight, applicable-but-missing metrics
impute at the neutral sector-conditional percentile, suppressed metrics never impute, no
completeness multiplier, published observed/imputed/suppressed weight fractions.
`advisor_engine.py::fixed_feature_challenger` blends it with the single neutral-target
shrink and ships per row as `score_variants.fixed_feature`.

**Before/after.** Spearman(coverage, score): +0.514 production to +0.186 fixed-feature
(+0.168 with the shrink). Financials artifact +2.8 points (p 0.032) to +0.3 (p 0.64).
599 of 875 names move more than 50 ranks.

**Remaining limitations.** The residual +0.17 to +0.19 correlation is deliberate
(coverage co-varies with real characteristics). Missingness-invariance holds by test, not
by proof, for the band mode, which keeps its renormalization until the champion is retired.

**Promotion status.** Challenger. Enters the 24-period IC harness. The two production
multipliers stay in the champion so the comparison is attributable, and they are on the
retirement path if the challenger clears the gate.

## 4. Directional confidence shrinkage

**Issue.** `base = raw * (0.8 + 0.2 * coverage)` pushes every thin-data name toward zero,
not toward neutral.

**Evidence.** Round 3 item 5. Round 4 re-evaluation: after imputation removes the upstream
penalties, the shrink form is worth only -0.02 of coverage correlation, and constant-50 vs
sector-mean priors differ by 0.003.

**Implementation.** No new code needed. The correct form already existed
(`shrink_research_components`, advisor_engine.py:870-895) and is the only coverage-aware
transform in the fixed-feature challenger.

**Before/after.** In the challenger the low-confidence pull is toward the prior from both
sides (tested), and the production directional form is documented as a defect in the same
test file.

**Promotion status.** Part of the fixed-feature challenger. Round 3's ranking of this fix
as second priority is corrected: it is a refinement after imputation, not the fix.

## 5. Turnover attribution and hysteresis

**Issue.** 64.9% (now cache-pinned) monthly turnover, attribution disputed for three
rounds.

**Evidence.** Variant backtests on one frozen cache: fundamentals only 12.2%, +technical
+37.1pp, +modifiers +1.3pp, news 0.0pp. Buffer sweep 1.25 / 1.5 / 2.0 cuts turnover to
44.3 / 39.5 / 33.7% with CAGR inside 0.5pp of baseline.

**Implementation.** No new mechanism needed (`portfolio_construction.py::apply_controls`
existed). The full sweep is published with manifests, and the monthly cross-sectional
variant (`bt_variant.py cross_sectional`) settled that normalization does not move
turnover (50.6 vs 49.4%).

**Remaining limitations.** One five-year sample. No k is declared the winner.

**Promotion status.** Challenger, pending prospective evidence. The technical-sleeve
redesign it points at is the next research project.

## 6. ETF and universe classification

**Issue.** VOO and VGT carried ranked stock scores (63.5, 61.6) built purely from
technical renormalization after fundamentals correctly refused them. PINC, an operating
company, was suppressed as an ETF by a provider quoteType glitch.

**Implementation.** `fetch_prices.py`: a row claiming ETF while reporting a company market
cap is reclassified as a stock unless it is in the configured ETF list. The coverage
publication gate independently de-ranks any zero-fundamentals row. Regression tests cover
both directions.

**Promotion status.** Shipped defect fix.
