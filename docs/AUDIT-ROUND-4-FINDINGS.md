# Audit Round 4: Reconciliation, Withdrawals, and the Imputation Redesign

Every number in this document is scoped to the following pinned state unless a row says
otherwise.

| Pin | Value |
|---|---|
| Pit refresh id | `advisor-2026-08-10T17:22:04.440901+00:00` |
| Pit file sha256 | `54f86b3e9bf861a4...` |
| Price cache tree sha256 | `9b41dfbfef494699...` (860 tickers) |
| settings.json sha256 | `43b83641fdd479ec...` (pre-remediation state used for scoring runs) |
| Factor files sha256 | ff5 `cbc3724812132654...`, momentum `f405ee2d47a5c75c...`, vintage through 2026-06 |
| Universe size | 880 rows, 875 to 879 usable depending on measurement |
| Mean fundamentals coverage | 0.39 as published, 0.82 after the EDGAR batch enrichment of section 5 |

The committed alpha comparison additionally references the 2026-08-03 cache state frozen
inside `pipeline/backtest_monthly_results.json`, which is itself the pinned artifact for
that side of the reconciliation. Measurement scripts are committed under
`research/audit/round4/` and each section names its producer. Experiment manifests
(git commit, config hash, universe hash, cache tree hash, calendar hash, cost model hash,
SHA-256 throughout) now attach to every backtest artifact via
`pipeline/validation/experiment_manifest.py`, wired into `backtest_monthly.py`.

---

## 1. Task 1: the alpha and turnover reconciliation

Producer: `research/audit/round4/task1_alpha_reconciliation.py`.

The published -2.57% was produced by `pipeline/p0_q1_benchmark_factor_report.py` from the
committed `pipeline/backtest_monthly_results.json` (generated 2026-08-03). Its construction:
month-end resamples of the daily portfolio value series, net of 10bps per-rebalance costs,
including cash drag and 12 missing-holding-price days, regressed on the french.json factor
vintage with Bartlett HAC at 3 lags and geometric annualization. Round 3's +0.43% used gross
locked-pick returns re-priced from the cache, statsmodels HAC at 6 lags, arithmetic
annualization, and the 2026-08-10 cache.

The bridge, changing one thing at a time:

| Step | Construction | Alpha (ann.) | t | n |
|---|---|---|---|---|
| A | Committed artifact, value series net of costs, HAC3, geometric | **-2.57%** | -0.44 | 58 |
| B | Same returns, HAC6, arithmetic, zip factor files | -2.60% | -0.52 | 58 |
| C | Same committed artifact, locked picks re-priced gross | -0.63% | -0.12 | 59 |
| D | 2026-08-10 cache rerun, locked picks gross | **+0.43%** | +0.09 | 58 |

| Difference | Contribution to the 3.00pp swing |
|---|---|
| Estimator (HAC lag count, annualization, factor file format) | **-0.03pp** |
| Return construction (10bps costs, cash drag, missing-price handling, value-path compounding) | **+1.97pp** |
| Cache state (restated fundamentals and prices, 2026-08-03 vs 2026-08-10) | **+1.06pp** |

Month-level check on the same artifact: the two return paths differ by mean 141bps, median
112bps, max 505bps (2022-09).

**Verdict.** The published -2.57% reproduces to the digit and is NOT retracted. Both numbers
are correct for different defined constructions. Step A measures what a costed portfolio
value path earned. Step D measures the gross signal. Neither is statistically
distinguishable from zero (|t| max 0.52 across all four constructions). The model card now
carries this reconciliation and labels every historical alpha as construction- and
cache-pinned (diffs in section 7).

**Turnover.** Same treatment. Published 64.9% reproduces from the committed 2026-08-03
artifact (measured 64.3% mean over rebalances 2 to 60). The identical script and flags on
the 2026-08-10 cache give 50.6%. The gap is pure cache state: across 59 common rebalance
dates the two runs' pick sets overlap 68% on average, and the FIRST rebalance
(2021-08-31) already overlaps only 45%. A provider serving restated data rewrites
five-year-old picks between two pulls a week apart. This single number is the entire case
for experiment manifests and the EDGAR point-in-time spine, and both are now implemented.

No result below this line was accepted until this section closed.

---

## 2. Withdrawn and revised Round 3 conclusions (Tasks 2, 4, 5)

Producers: `task2_collinearity_psd.py`, `task4_clean_pairs.py`,
`task5_characteristic_tilts.py`.

| Round 3 claim | Why it does not hold | Replacement |
|---|---|---|
| Challenger valuation first-eigenvalue share 0.475 (pairwise-complete) | The pairwise-complete challenger matrix is not positive semi-definite: minimum eigenvalue **-0.086**. Eigenvalue shares of an indefinite matrix are meaningless. | **Withdrawn.** The champion pairwise matrix happens to be PSD (min eig +0.039, share 0.431) and stands with that caveat. Complete cases number 20 of 880, too few for any eigenvalue claim (per-cell n runs 34 to 732, EV-multiple cells 130 to 170). |
| "The auditor's location prediction failed" (quantization in accounting quality, not valuation) | The valuation block resolves for 15% of names at the pinned coverage state. A block that mostly does not resolve cannot be adjudicated against blocks that do. | **Revised to unmeasurable.** What the current state supports: EV/EBITDA vs EV/EBIT correlate 0.83 to 0.87 on n around 160, per-metric quantization (5 distinct values, modal mass up to 0.70) is real wherever measured. Block-level location comparisons wait for enrichment. The neutral-imputed correlation matrix (n=873, PSD, min eig +0.16 to +0.20, first-eig share 0.32 to 0.35) understates correlation mechanically because imputed constants attenuate it, and is reported for the imputation challenger's design only. |
| "Bands are the turnover-stabilizing normalizer" (daily 0.239 vs 0.374) | Pre-stated stability rule (universe churn < 0.02 AND mean coverage delta < 0.02): **0 of 5 daily pairs qualify**. Coverage drifted 3.6 to 7.4pp per day through the enrichment recovery. A direction claim from zero clean observations is withdrawn, and the two least-contaminated pairs pointed the other way (champion 0.253 and 0.264 vs challenger 0.161 and 0.207). | **Withdrawn at daily frequency, answered at monthly.** The uncontaminated monthly backtest (same frozen cache, per-month refit of the production `CrossSectionalNormalizer`, producer `bt_variant.py` variant `cross_sectional`): bands 50.6%, cross-sectional 49.4% mean monthly turnover. **Normalization mode does not materially move turnover.** The technical sleeve does (37.1pp). Cross-sectional CAGR 11.61% vs bands 12.59%, same -19.0% drawdown. |
| Item 3 carried by "CMA +0.017, growth-zeroed +0.025" | A null with se 0.300 detects nothing below 0.59 (50% power) or 0.84 (80% power) at 58 months. Evidence of absence was overstated. | **Re-led by the characteristic test.** Spearman(score, raw asset growth) = -0.030 (p 0.51, n 488). The regression stays as a consistency check with its MDE stated. The substantive conclusion survives: no aggressive-investment tilt exists, and the fundamentals-only sleeve's CMA +0.339 (se 0.146, t 2.32) remains the highest-powered regression finding. |

### The characteristic-tilt battery that replaces the regression as the primary diagnostic

Champion score vs raw characteristics, pinned snapshot:

| Characteristic | Spearman | p | n |
|---|---|---|---|
| log market cap | +0.013 | 0.71 | 876 |
| book-to-market (1/PB) | +0.152 | 1e-5 | 830 |
| gross profits / assets | +0.152 | 2e-3 | 400 |
| profit margin | +0.270 | 4e-16 | 874 |
| asset growth (investment) | -0.030 | 0.51 | 488 |
| prior 12-1 return | +0.253 | 5e-14 | 859 |

The score is a mild value, profitability, and momentum tilt with no size and no investment
exposure, measured at 8 to 15 times the regression's effective sample.

---

## 3. Task 3: the imputation redesign

Producer: `task3_imputation_measurement.py`. Implementation:
`scorer.py::_fixed_feature_valuation_score` (mode `fixed_feature` in `valuation_score`),
`advisor_engine.py::fixed_feature_challenger`, published per row under
`score_variants.fixed_feature`.

### Specification

Round 3's remediation item 2 prescribed deleting the coverage multipliers. Round 4 rejects
that: deletion without imputation scores a 17%-coverage name on a renormalized subset
measuring something different from a 91%-coverage name and calls them comparable. The
implemented construction:

1. Every applicable metric carries its full intended weight for every name. The
   within-block renormalization over resolved metrics is gone in this mode.
2. An applicable-but-missing metric is imputed at the neutral cross-sectional value. On
   the winsorized percentile scale the neutral value is the distribution center by
   construction, and the normalizer is already sector-conditional where at least 8 peers
   exist (`scorer.py::CrossSectionalNormalizer.score`), which implements the
   sector-conditional imputation hierarchy without a second estimator.
3. Suppressed metrics (economically inapplicable, via `canonical_metrics`) leave the
   vector entirely and are never imputed. Nonpositive valuation denominators stay
   suppressed, not imputed.
4. No completeness multiplier touches the score. Every row publishes
   `observed_weight_fraction`, `imputed_weight_fraction`, `suppressed_weight_fraction`,
   and per-metric status (`observed`, `imputed`, `suppressed_not_applicable`).
5. Coverage survives as a diagnostic and as the publication-gate input, never as a score
   multiplier.

Literature basis: Jensen, Kelly, and Pedersen (Journal of Finance 78(5), 2023) rank
characteristics cross-sectionally and impute missing values at the neutral cross-sectional
value. Freyberger, Hoeppner, Neuhierl, and Weber (Review of Financial Studies 38(3), 2025)
show conditional-mean imputation with weighted least squares yields valid inference and
better out-of-sample predictability. Chen and McCoy (Journal of Financial Economics 153,
2024) show simple cross-sectional imputation performs close to EM approaches for portfolio
construction, which is why this implements the simple conditional form rather than the full
GMM machinery. Bryzgalova, Lerner, Lettau, and Pelger (Review of Financial Studies 38(3),
2025) document that fundamentals missingness is systematic, which is exactly the
provider-driven, sector-correlated pattern measured here.

### Before and after, identical EDGAR-augmented snapshot, n=875

| Measurement | Production (bands + 2 multipliers) | Fixed-feature | FF + shrink to 50 | FF + shrink to sector mean |
|---|---|---|---|---|
| Spearman(coverage, score) | **+0.514** (p 5e-60) | **+0.186** (p 3e-8) | +0.168 | +0.165 |
| Financials vs rest | +2.8 pts (p 0.032) | +0.3 (p 0.64) | | +0.2 (p 0.48) |

Rank correlation production vs fixed-feature: 0.782. Mean absolute rank shift 125. Names
moving more than 50 ranks: 599 of 875. The ten largest movers are utilities and REITs the
production coverage stack was crushing (OGE 759 to 159, EIX 515 to 18, UGI 507 to 25) plus
one name the redesign correctly demotes (WTW 271 to 777 once imputation stops rewarding a
thin favorable subset). The residual +0.17 to +0.19 correlation is not forced to zero:
coverage co-varies with real characteristics, and the success criterion was minimal direct
penalization, not orthogonality by fiat.

### The shrinkage promotion, re-evaluated

Once imputation removes the upstream penalties, the neutral-target shrink changes the
coverage-score correlation by only -0.018 (constant-50 prior) or -0.021 (sector-mean
prior), and the two priors differ by 0.003. Round 3 ranked the shrinkage promotion second
in its remediation order. That ranking was wrong. The binding fix is fixed-feature
imputation plus multiplier removal. The shrink stays in the challenger
(`shrink_research_components`, `advisor_engine.py:870-895`) as the single remaining
coverage-aware transform because it is directionally correct (James and Stein 1961, Efron
and Morris, JASA 70(350), 1975), but it is a refinement, not the fix. Prior choice is
immaterial at current dispersion.

---

## 4. Task 4 supplement: what the monthly evidence now supports

Full variant table, one frozen cache, identical calendar, manifests attached
(producer `bt_variant.py` plus `backtest_monthly.py --rank-buffer`):

| Variant | Mean monthly TO | CAGR | Max DD | Modeled cost |
|---|---|---|---|---|
| Bands champion (baseline) | 50.6% | 12.59% | -19.0% | $3,715 |
| Cross-sectional (per-month refit) | 49.4% | 11.61% | -19.0% | $3,563 |
| Fundamentals only | 12.2% | 14.17% | -26.7% | lowest |
| No modifiers | 49.3% | 12.46% | -19.0% | |
| Rank buffer 1.25 | 44.3% | 12.85% | -18.9% | $3,294 |
| Rank buffer 1.5 | 39.5% | 12.60% | -18.4% | $3,035 |
| Rank buffer 2.0 | 33.7% | 12.37% | -19.8% | $2,595 |

The buffer frontier is benign across the whole sweep: turnover falls monotonically and
returns stay inside 0.5pp of baseline. This is one five-year sample. The full sweep is
published, no k is declared a winner, and the buffer remains a challenger pending the
prospective gate.

---

## 5. Task 6: enrichment, the pre-committed decision rule, and the result

Producer: `task6_batch_enrichment.py`. Implementation: `pipeline/edgar_enrichment.py`,
wired as an automatic fallback into `fetch_advisor.py::yahoo_extended`.

### The batch mechanism

The repository already held the backfill nobody was using: `pipeline/data/pit/fundamentals`
contains 1,448,995 as-filed XBRL facts for all 860 universe CIKs, 29 concepts, filed
2010-01-28 through 2026-08-07, with accession, form, filed date, period end, and an
amendment-preserving key (`build_pit_fundamentals.py`, which explicitly "does not feed the
live pipeline"). `edgar_enrichment.py` now adapts those facts into the exact statement
shape `fundamentals_extended.derive_extended` consumes, so every existing derivation runs
unchanged on as-filed data. Point-in-time discipline holds: only facts filed on or before
the as-of date are visible, and the latest such filing wins per period, so amendments
appear on their filing date and never rewrite the earlier view. Fidelity check on CRUS:
EDGAR-derived GP/A and accruals match the provider values exactly, ROIC within 0.5pp,
EV/EBITDA within 0.7x.

### Achieved coverage (raw-input presence, n=880)

| Metric | Before | After batch |
|---|---|---|
| EV/EBITDA | 47% | 74% |
| EV/EBIT | 45% | 76% |
| EV/FCF | 50% | 80% |
| ROIC | 49% | 82% |
| Gross profits/assets | 45% | 71% |
| Piotroski F | 55% | 93% |
| Net buyback yield | 56% | 96% |
| Accruals ratio | 55% | 95% |
| Asset growth | 55% | 99% |
| Altman Z | 44% | 66% (retained earnings is not an ingested concept, remaining gap is structural) |

Names with at least one filled metric: 858 of 880. Mean fundamentals coverage 0.39 to 0.82.

### The decision rule, committed before the re-measurement

If Spearman(coverage, final score) stayed above +0.20 at restored coverage, the correlation
is a design defect and the imputation redesign is mandatory. Below +0.10, it was an outage
artifact. Result at 0.82 mean coverage: **+0.438** (p 3e-42, n 875) under the production
construction. The rule fired. The correlation is a design defect. Section 3 is the
mandatory redesign, implemented and measured. Achieved coverage of 0.82 sits below the 85%
stated in the rule's framing, and the margin over threshold (0.438 vs 0.20) is wide enough
that the verdict does not depend on the last three points of coverage.

Enrichment alone, with no methodology change, reorders the universe at rank correlation
0.820 to the published board (mean absolute shift 114 ranks). The published leaderboard was
substantially a map of data availability.

### The publication gate

Implemented regardless of outcome, as specified: `pipeline/data_health.py::publication_gate`
with `settings.json::data_health.min_publication_coverage = 0.35`. A name below the floor
keeps its diagnostics and challenger scores and publishes as INSUFFICIENT DATA, not as a
ranked stance (`fetch_advisor.py` research loop). Justification for 0.35: the outage floor
ran 0.10 to 0.20 and the enriched cohort runs 0.85 to 0.95, so 0.35 separates the two modes
with margin on both sides while leaving legitimately statement-light profiles (financial
applicability suppression raises effective coverage above the floor) publishable. Refresh
health (`statement_health`: healthy, degraded below 0.50, critical below 0.30) ships in the
payload as `statement_health` so a degraded refresh is labeled instead of silently ranked.

---

## 6. Revised remediation order

Round 3's ranking, re-ranked by Round 4 measurement. Items 1 and 2 of Round 3 are now one
project and it is finished at the challenger level.

| # | Change | Status | Measured basis |
|---|---|---|---|
| 1 | EDGAR statement enrichment as automatic fallback | **Done** (`edgar_enrichment.py`, wired) | Coverage 0.39 to 0.82 offline, 858 names filled |
| 2 | Fixed-feature imputation challenger, no completeness multipliers | **Done as challenger** (`score_variants.fixed_feature`) | Coverage-score rho 0.514 to 0.186, financials artifact gone |
| 3 | Coverage publication gate + provider-health states | **Done** (`data_health.py`, settings, payload) | Outage of 2026-08-06 would now label itself critical |
| 4 | Experiment manifests on every backtest artifact | **Done** (`validation/experiment_manifest.py`) | 55% first-month pick divergence between caches a week apart |
| 5 | Rank-buffer hysteresis | Sweep published (1.25 / 1.5 / 2.0), challenger pending prospective gate | TO 50.6% to 44.3 / 39.5 / 33.7%, CAGR within 0.5pp |
| 6 | Technical sleeve ablation and redesign | Next. Unchanged from Round 3 finding | +37.1pp of turnover, dilutes CMA +0.34 to +0.02 |
| 7 | ETF classification fix | **Done** (`fetch_prices.py` guard + gate + tests) | VOO 63.5 and VGT 61.6 ranked on zero fundamentals, PINC suppressed as a fund |
| 8 | Normalization promotion decision | Deprioritized | Monthly turnover is normalization-invariant (50.6 vs 49.4). Decide on comparability grounds after the fixed-feature challenger accumulates IC periods |
| 9 | Valuation-block collapse | Still gated | EV coverage now 74 to 80% raw, but the collinearity verdict was withdrawn as unmeasurable at scale. Re-run Task 2 complete-case at the new coverage first |
| 10 | MAX / idiosyncratic-vol screen, portfolio layer beyond the buffer | Unchanged (P3) | Unmeasured here |

Promotion discipline is unchanged: nothing above is promoted to champion. The fixed-feature
challenger, the shrink, and the buffer all enter the existing 24-period IC harness
(`pipeline/validation/ic_harness.py`, `minimum_icir_periods` verified at 24), and every
variant tested in this round is recorded in the committed artifacts whether it won or lost.

---

## 7. Model card corrections applied

- `docs/MASTER-METHODOLOGY.md` section 9: the -2.57% row now carries the reconciliation
  verdict, the construction and cache pins, the +0.43% counterpart, and the manifest
  requirement. The 64.9% turnover row now carries the cache pin, the 50.6% counterpart,
  the 45% first-rebalance overlap, and the Round 4 component decomposition.
- `docs/ALGORITHM-RESEARCH-RESULTS.md` verdict section: same reconciliation note attached
  to the six-factor regression bullet.

Neither number is retracted. Both are demoted from authoritative to pinned.

---

## Code changed in this round

| File | Change |
|---|---|
| `pipeline/validation/experiment_manifest.py` | New. Deterministic SHA-256 manifests |
| `pipeline/backtest_monthly.py` | Embeds a manifest in every result artifact |
| `pipeline/edgar_enrichment.py` | New. As-filed EDGAR statement adapter + fallback merge |
| `pipeline/fetch_advisor.py` | EDGAR fallback in `yahoo_extended`, per-name publication gate, refresh `statement_health` |
| `pipeline/scorer.py` | New `fixed_feature` scoring mode (imputation, fraction accounting, no multipliers) |
| `pipeline/advisor_engine.py` | `fixed_feature_challenger`, published in `score_variants` |
| `pipeline/data_health.py` | New. Coverage health states + publication gate |
| `pipeline/fetch_prices.py` | ETF quoteType glitch guard |
| `pipeline/config/settings.json` | `data_health` block |
| `pipeline/tests/test_round4_remediation.py` | 14 regression tests. Full suite: 1668 passed |
| `docs/MASTER-METHODOLOGY.md`, `docs/ALGORITHM-RESEARCH-RESULTS.md` | Reconciliation corrections |
| `research/audit/round4/*.py`, `research/audit/remediation/before_after.{json,md}` | All measurement producers and the before/after record |
