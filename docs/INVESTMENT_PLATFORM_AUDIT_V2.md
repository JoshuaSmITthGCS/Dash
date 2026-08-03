# Investment research correctness audit — model/schema v2

Audit date: 2026-08-02  
Evidence baseline: checked-in `public/data/advisor.json`, generated 2026-07-31, and the code paths at the current commit.  
Scope: provider adapters → normalized snapshot → scores/modifiers → JSON → React. No external values were assumed correct.

## Executive conclusion

The legacy model is not sufficiently auditable for prescriptive use. It retains provider scalars without source field, unit, fiscal period, observation/publication date, or raw response. Several computations are internally deterministic but semantically invalid for particular business models. The most serious defects are the ambiguous provider PEG, broad financial-sector routing, non-reproducible percentile copy, availability/reliability conflation, and position rules overwriting the displayed action.

The v2 layer is shipped alongside the legacy fields. It does not silently reinterpret historical values. Where lineage or a required estimate is absent, v2 says unavailable or insufficient evidence.

## Root causes ranked by severity

| Severity | Root cause | Evidence | Corrective control |
|---|---|---|---|
| Critical | Provider PEG was treated as canonical although its growth definition/horizon was unknown. | `fetch_prices.py` selected Yahoo `trailingPegRatio`/`pegRatio`; HIG serialized `0.12`; `scorer.py` gave it 100/100. No matching forward-growth input existed. | `peg.v2` calculates only from canonical forward P/E and declared forward growth. Unknown horizon, mismatched periods, or nonpositive growth returns unavailable. |
| Critical | Broad sector was used as a business-model profile. | HIG had only `sector=Financial Services`; insurer-inappropriate ROIC, cash conversion, FCF yield, Piotroski, capex/depreciation and DSO boosted categories. | Ten applicability profiles plus auditable ticker overrides. HIG routes to `diversified_insurer`; inapplicable metrics leave the coverage denominator and disclose replacements. |
| High | Percentile had two display values and insufficient provenance. | The stored HIG percentile was 90.2, while the modifier transformed it into “cheaper than 80%.” `sector_percentiles` provided no peer IDs, values, dates or confidence. | One canonical percentile object, inclusive-rank method, minimum peer count, top/bottom values, sample label/date, display cap of 99, and schema invariant. |
| High | Confidence was coverage in disguise and score adjustment moved toward zero. | `confidence = weighted coverage`; `base = raw * (0.8 + confidence*0.2)`. This does not implement `50 + confidence*(raw-50)`. | Separate coverage and reliability confidence; v2 shrinks toward 50 and gates action below 0.60 confidence. |
| High | Trailing growth was labeled generically and no forward revision series existed. | Yahoo `earningsGrowth` and Alpha Vantage `QuarterlyEarningsGrowthYOY` fed one `earnings_growth` score. Capability status admitted point-in-time revisions were unavailable. | Structural trailing growth and forward timeliness are separate. Missing 7/30/90-day revisions remain visibly unavailable. |
| High | A position stop replaced the headline company action. | `withStopLoss` overwrote `action` with SELL/100%. | The merged object now retains `companyRecommendation` and an independent `positionAction` with a reason code; UI renders the distinction. |
| Medium | Provider disagreement could not be diagnosed. | Snapshot merge filled missing scalars and discarded alternative observations. | Capability protocols, normalized observation envelope, configured precedence/tolerance, preserved observations and conflict penalties. |
| Medium | Static JSON lacked a reproducible run identity. | Legacy payload had `generated_at` only. | v2 run manifest adds commit/config/universe hashes, versions, provider status, counters and score summary. Cache hit/miss remains explicitly uninstrumented. |
| Medium | UI rendered raw values even when scoring suppressed them. | `MetricSections` and stock views read scalar fields directly. | v2 metric status filters suppressed/replaced/unavailable values and lists every exception with a reason. |

## Data lineage

The checked-in legacy JSON has no retained Yahoo raw response and the Alpha cache files cannot be tied to HIG or BSX. Therefore a source response sample, filing date and observation date cannot be reconstructed honestly. “Not retained” below is a finding, not a blank to infer.

| Displayed label | Provider / field | Source response sample | Raw value / unit | Canonical value / unit | Fiscal period / designation | Dates (observed, available, fetched) | Transformation | Profile | Score / modifier | JSON path | React consumer | Quality flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HIG PEG | Yahoo `trailingPegRatio` (fallback `pegRatio`) | Not retained | 0.12 / multiple | unavailable / multiple | Unknown / provider calls it trailing; model expected forward | Not retained | Legacy identity; v2 `calculate_peg` rejects it | diversified insurer | Legacy 100; v2 suppressed | `research[].peg`, `analysis_v2.canonical_metrics.peg` | `StockDetailModal` → `MetricSections` | unknown growth definition/horizon; missing lineage |
| HIG current ratio | Yahoo `currentRatio` | Not retained | 1.77 / multiple | retained for diagnostics, not applied | Period not supplied / trailing | Not retained | Identity | diversified insurer | Legacy scalar; v2 suppressed, replace with statutory capital/liquidity | `research[].current_ratio`, `analysis_v2.metric_status.current_ratio` | `MetricSections` | inapplicable; missing period/date |
| HIG FCF yield | Yahoo `freeCashflow / marketCap` | Not retained | 5.5075bn / USD and 39.214bn / USD; result 0.1404 / decimal | retained for diagnostics, not applied | Claimed TTM over point-in-time cap; exact alignment absent | Not retained | Division in `fetch_snapshot` | diversified insurer | Legacy 100; v2 suppressed, replace with capital-return yield | `research[].free_cash_flow_yield` | `MetricSections` | insurer cash-flow semantics; date mismatch untestable |
| HIG valuation percentile | Derived from legacy valuation category | N/A | 92.6 / score | unavailable | Run-level cross-section | constructed 2026-07-31 | inclusive rank within diversified insurers | diversified insurer | Modifier disabled because only 2 valid peers (<4) | `research[].valuation_percentile` | `StockDetailModal` | insufficient valid peers |
| BSX valuation | Yahoo statement/quote scalars | Not retained | Fwd P/E 13.27, P/S 3.26, EV/EBITDA 15.26, EV/FCF 22.87 | PEG unavailable; remaining values retained with low provenance | Mixed point-in-time/TTM/forward | Not retained | Profile bands, weighted available inputs, neutral shrinkage | general | v2 structural effective 62.3, confidence 0.46 → watch | `analysis_v2.structural` | `AnalysisLayers` | missing provider periods/dates; no canonical PEG |
| BSX growth / timing | Yahoo `revenueGrowth`, `earningsGrowth`; no estimate-history provider | Not retained | 0.075 and 0.15 / decimals | trailing fields only; forward revisions unavailable | Provider period unclear / trailing vs forward separated | Not retained | Trailing fields cannot populate timeliness | general | Timeliness insufficient evidence | `analysis_v2.timeliness` | `AnalysisLayers` | forward 7/30/90-day revisions unavailable |
| Confidence and coverage | Derived | N/A | Legacy coverage 0.89 and composite confidence | coverage 0.84; confidence 0.46 | Run-level | generated 2026-07-31; migrated 2026-08-02 | `50 + confidence*(raw-50)` | general | action limited to watch/review below 0.60 | `analysis_v2.structural` | `AnalysisLayers`, `recommendation.js` | legacy values missing complete lineage |
| Position stop | Browser position data + price history | User cost basis and checked-in closes | Percent drawdown / percentage points | independent position action | Since purchase / tactical | Purchase and quote dates | cost and trailing-stop thresholds | position-specific | Does not overwrite company recommendation object | client state `positionAction` | `ActionGuidance` | client-side; depends on brokerage inputs |

The complete machine-readable per-ticker route is `public/data/diagnostics.json`. New provider observations use the required envelope (`value`, `unit`, source/field, period dates, availability/observation/fetch dates, fiscal period, TTM/forward flags, quality flags, transform version). Missing provider metadata is explicitly null/flagged.

## HIG before and after

| Concern | Legacy | v2 |
|---|---|---|
| PEG | 0.12, score contribution 100 | Canonical PEG unavailable; insurer profile suppresses PEG. The raw scalar remains only for migration diagnostics. |
| Business model | Broad Financial Services exemption skipped a few metrics | `diversified_insurer`; generic PEG, current ratio, ROIC, FCF yield, cash conversion, EV/EBITDA, EV/FCF, net debt/EBITDA, Altman, Piotroski, capex/depreciation and DSO are suppressed/replaced. |
| Percentile | 90.2 in a field and “80%” in modifier text | No claim: 2 valid diversified-insurer peers is below minimum 4. Underlying peers are exposed. |
| Growth | Quarterly revenue/EPS growth raised structural score | Retained as trailing context only. Forward timeliness is insufficient evidence because revision history is unavailable. |
| Advice | Legacy 82 ATTRACTIVE at 85% confidence | Canonical layer is confidence-gated; absent lineage and insurer-specific inputs prevent prescriptive classification. |

Insurer replacements (combined ratio, underlying combined ratio, reserve development, loss/expense ratio, statutory capital, RBC, normalized/core ROE, book/tangible-book growth, capital-return yield) remain unavailable because current providers/adapters do not supply defensible normalized observations. They are not imputed.

## BSX before and after

| Concern | Legacy | v2 |
|---|---|---|
| Valuation | Category 79.8 and composite score 78.4; provider PEG 0.57 received 100 | PEG is unavailable without declared forward growth. Structural effective score is 62.3 at 46% confidence and classification is watch. |
| Percentile | Legacy field and modifier could diverge | One medical-device peer object; 80.0 among 6 valid peers with low 0.30 percentile confidence, exact peers shown. |
| Growth | Generic trailing earnings growth could read as “growth” | Trailing revenue/EPS are shown separately; forward revision fields do not exist in the historical artifact and timeliness says insufficient evidence. The deterministic negative-revision fixture produces weakening. |
| Coverage/confidence | Similar concepts appeared together without semantics | Coverage is answered applicable weight; confidence is reliability. Both are labeled independently, with threshold explanation. |
| Position stop | Could replace company action | Company recommendation and position action are separately retained and displayed. |

## Versioning and migration

- Schema: advisor v2. Legacy scalar fields remain for compatibility.
- Model: `structural-timeliness-2.0.0`.
- Config: `canonical-metrics-2.0.0`.
- Migration: `python pipeline/migrate_advisor_v2.py`.
- Trace command: `python pipeline/audit_ticker.py HIG --as-of 2026-08-02` or `python -m pipeline.audit_ticker HIG --as-of 2026-08-02` from a configured package environment.
- Production refresh writes both `advisor.json` and `diagnostics.json`, plus a run manifest embedded in advisor data.

## Exact files introduced or intentionally changed by this audit

Backend/config: `canonical_metrics.py`, `provider_interfaces.py`, `peer_groups.py`, `scoring_v2.py`, `observability.py`, `audit_ticker.py`, `migrate_advisor_v2.py`, `fetch_prices.py`, `fetch_advisor.py`, `advisor_engine.py`, `validate_data.py`, `metric_registry.json`, `applicability_matrix.json`, `business_profiles.json`, `provider_reconciliation.json`, and `advisor.schema.json`.

Frontend: `AnalysisLayers.jsx`, `StockDetailModal.jsx`, `MetricSections.jsx`, `ActionGuidance.jsx`, `recommendation.js`, `positionRisk.js`, and `global.css`.

Tests/fixtures: `test_canonical_v2.py`, `regression_cases.json`, `AnalysisLayers.test.jsx`, `recommendation.test.js`, and `positionRisk.test.js`.

Artifacts/docs: `public/data/advisor.json` (v2 migration), `public/data/diagnostics.json`, and this report.

## Remaining unavailable or potentially unreliable metrics

The following are explicitly unreliable in the migrated historical artifact until a fresh v2 provider run records lineage: every legacy Yahoo/Alpha fundamental scalar lacking source period and dates; provider PEG; Yahoo/Alpha generic quarterly growth labels; market-cap/share-count alignment; TTM-versus-fiscal-year alignment; GAAP-versus-adjusted earnings identity; and any legacy derived statement metric whose filing/publication dates were not retained.

Still unavailable by capability: 7/30/90-day point-in-time estimate revisions, revision acceleration, estimate dispersion history, normalized guidance direction, normalized earnings/revenue surprise history, insurer underwriting/reserve/statutory-capital metrics, bank regulatory capital/liquidity metrics, REIT FFO/AFFO and debt-maturity metrics, utility regulated-asset/recovery metrics, commodity mid-cycle normalization, biotech pipeline probability and cash runway, institutional 13F changes with reliable CUSIP mapping, and issuer-normalized FX/backlog data.

Percentiles remain low confidence or invalid when business-profile classification relies on configured ticker overrides, the universe is incomplete, or fewer than four valid peers exist. Cache hit/miss counts are not yet instrumented and the manifest says so. No unavailable field is assigned a neutral 50 and counted as covered.
