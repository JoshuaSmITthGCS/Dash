# Production hardening phase report

Run date: 2026-08-03  
Mode: legacy production retained; v2 remains side-by-side/shadow  
Outperformance claims: none

## Current-state map

| State | Evidence-backed status |
|---|---|
| Implemented and production-safe | Canonical observation envelope; suppression/no-denominator controls; confidence shrinkage and gates; independent company/portfolio/position layers; severity-based trim math; stop/thesis separation; append-only snapshot primitives; proxy-safe ETF labels; schema/config JSON introduced here; deterministic backend tests. These controls are safe as shadow outputs, not as a production cutover. |
| Implemented but experimental | Live v2 validation view; sector replacement contracts; ATR/volatility stop profiles; momentum correlation cap; extended validation statistics; daily Yahoo estimate collector; cross-asset ETF diagnostics; nine shadow strategy specifications. |
| Partially implemented | Provider adapters populate only a small subset of replacement metrics; historical backtest has statistics but insufficient point-in-time inputs; shadow construction is specified but has no performance depth; frontend is implemented but could not be executed in this environment because Node/npm are unavailable; risk-free handling accepts a stored series but the production evaluator is not yet wired to fetch and persist the configured FRED series. |
| Missing | Controlled valid-peer cross sections for the representative live run; actual index return feeds for most ETFs; normalized guidance and post-earnings-drift observations; delisting/corporate-action integration tests against real events; prospective months of estimates and shadow returns. |
| Blocked by unavailable data/state | Insurer statutory/underwriting data, bank regulatory/credit data, REIT FFO/AFFO/debt maturity, utility rate-base/regulatory data, commodity mid-cycle inputs, biotech pipeline/binary-event inputs, 7/30/90-day revision history, and adequate peer samples. `public/data/advisor.json` is committed with merge markers and is invalid JSON, so all-public-contract validation and production cutover are blocked. |

## Controlled fresh-data validation

Artifact: `public/data/validation/live_v2_validation.json`. Raw Yahoo payloads were retained privately under `pipeline/data/staging/raw_provider/`; the public artifact contains normalized observations and hashes, not raw redistribution. Production outputs were not replaced.

| Ticker | Profile | Status | Structural effective / confidence | Timeliness effective / confidence | Company action | Critical gaps |
|---|---|---:|---:|---:|---|---:|
| HIG | diversified insurer | PASS | 52.9 / 0.06 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 3 |
| JPM | bank | PASS | 51.3 / 0.04 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 3 |
| O | REIT | PASS | 50.0 / 0.00 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 3 |
| NEE | utility | PASS | 50.7 / 0.07 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 3 |
| BSX | general/medical device peer group | PASS | 52.0 / 0.06 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 1 |
| MSFT | general | PASS | 51.7 / 0.07 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 1 |
| XOM | commodity producer | PASS | 52.5 / 0.07 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 3 |
| MRNA | pre-profit biotechnology | PASS | 50.8 / 0.04 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 4 |
| VTI | ETF | PASS | 50.0 / 0.00 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 2 |
| TLT | ETF | PASS | 50.0 / 0.00 | 50.0 / 0.00 | INSUFFICIENT EVIDENCE | 2 |

PASS means the hard invariants passed; it does not mean the ticker has enough evidence for an investment action. HIG's PEG/current ratio/ROIC/industrial FCF cannot score. No percentile language was emitted because the controlled run had zero valid peers. BSX trailing context remains separate from unavailable forward revisions.

## Business profiles and applicability

Profiles now declare their critical and replacement metrics for P&C, life and diversified insurers; banks; REITs; utilities; commodity producers; profitable biotech; pre-profit biotech; general companies; and ETFs. Each v2 result emits applied, suppressed, replacement, unavailable replacement, profile confidence, and critical gaps. Missing replacements reduce profile confidence; they are never imputed or scored neutrally.

## Recommendation, trim, and stops

The state machine retains four independent layers and emits canonical display labels while preserving stable internal identifiers. All company classifications use confidence-adjusted scores. Confidence below 0.40 permits only insufficient evidence/watch behavior; below 0.60 it prevents high-conviction buy, accumulate, trim from company deterioration, or sell-thesis actions. Verified thesis breaks require source, timestamp, explanation, confidence, materiality, and an allowed reason code.

Trim size uses flag count × severity × confidence × concentration × liquidity × tax-cost multipliers, clips to configured bounds, rounds fractional shares, checks minimum trade value/portfolio impact/transaction costs, and emits review for immaterial trades. Stops include fixed, ATR, volatility-adjusted, trailing, disabled, broad ETF, leveraged ETF, and biotech profiles. Stop diagnostics include threshold, high-water mark, current price, breach amount/percentage, first breach, confirmation, persistence, action, and discretionary status. Stops never become thesis factors.

## Momentum safeguards

`momentum_boundary_diagnostics` publishes formation date, exact starting/ending month ends, skipped months, and included return months for 12–1, 12–7 and 6–1. Industry relative momentum uses a minimum-sampled leave-one-out median/equal-weight return. Cross-sectional correlation output includes a matrix, average absolute pairwise correlation, effective factor count, concentration state, and enforced family cap. Existing hysteresis, minimum history, liquidity, ATR sizing and sleeve volatility controls remain separate.

## ETF validation

Artifact: `public/data/validation/live_etf_validation.json`. Eight live cases passed: international equity (VXUS), bond (TLT), commodity (GLD), leveraged (TQQQ), young (AVUV), currency hedged (HEFA), sparse/young history (SGOV), and proxy benchmark (VTI). Proxy contracts omit tracking difference/error and expose relative return, beta and correlation; tracking metrics require an actual index or an explicitly approved equivalent. Capture ratios expose sample counts and remain unavailable below the configured minimum. A quadratic maximum-history calculation found during the live run was reduced to linear time.

## Estimate collection

The scheduled collector is configured for the eight operating-company representatives and succeeded for all eight on the audit run. Snapshots declare current/next quarter and current/next year EPS/revenue consensus, analyst count, revision counts, high/low, dispersion, provider and freshness where Yahoo supplies them. Status remains `FORWARD_COLLECTION_ONLY`; no 7/30/90-day values were backfilled. Normalized earnings-event storage is prepared, with standardized surprise and post-earnings drift left null until real observations exist.

## Backtest and shadow portfolios

The validation framework now contains monthly Spearman rank IC, IC information ratio, quantile monotonicity, top-minus-bottom spread, hit rate, matched net-of-cost performance, configurable matched risk-free series, Sharpe, Sortino, drawdown, Calmar, beta/alpha, grouped attribution, block bootstrap, Deflated Sharpe approximation, append-only multiple-testing log, untouched holdout isolation and walk-forward splits. Tests with unavailable point-in-time fundamentals must remain unavailable.

`pipeline/config/shadow_strategies.json` defines legacy, v2 structural, structural+timeliness, momentum, quality-value, combined, SPY, equal-weight universe and manual external-ranking strategies, plus signal-only and full-strategy comparison modes. No performance conclusion is available because prospective observations have not accumulated.

## Frontend and schema

The dashboard adds a live validation route with explicit provider errors, applicability/lineage details, confidence/coverage, peer status, conflicts, and separate company/position actions. ETF/shadow/research empty states remain explicit. The advisor schema conflict was mechanically reconciled in source, but the checked-in production payload itself remains invalid and prevents contract validation. No migration replaces legacy values; v2 stays additive and shadow-only.

## Tests and blockers

- Python: 392 passed; one local LibreSSL/urllib3 compatibility warning.
- Targeted hardening: 63 passed before the full run.
- Live company validation: 10/10 invariant sets passed.
- Live ETF validation: 8/8 cases passed.
- JSON configs and staging artifacts: parsed with `allow_nan=False` writers.
- Frontend tests/build: not run; Node/npm are unavailable in this environment.
- All-public contract validation: blocked before schema evaluation because `public/data/advisor.json` contains committed merge markers at line 3 and many later locations.

## Safe rollout and rollback

Safe now: deploy reader/schema/config additions only with v2 shadow mode retained; run estimate and validation collectors; observe staging diagnostics. Experimental only: recommendation promotion, profile replacement scores, momentum sleeve allocation, ETF tracking against non-actual benchmarks, backtest claims, and shadow performance.

Cutover is blocked until the production JSON conflict is deliberately regenerated from a clean provider run, all public contracts validate, frontend tests/build pass, representative peer/profile tests have real valid samples, scheduled refresh succeeds, and prospective estimate/shadow depth is adequate.

Rollback: keep `shadow_mode: true`; disable the estimate/ETF validation workflow steps if providers degrade; remove the new validation route/artifacts without changing legacy consumers; after changes are committed, use a normal `git revert <hardening-commit>` to restore the prior code/config state. Do not restore or choose a side of the conflicted generated advisor payload manually—regenerate it from a controlled clean run after preserving the current file for audit.

## Files changed in this phase

Backend/config: `.gitignore`, `.github/workflows/refresh-advisor.yml`, `pipeline/canonical_metrics.py`, `pipeline/collect_estimates.py`, `pipeline/estimate_snapshots.py`, `pipeline/etf_comparison.py`, `pipeline/fetch_advisor.py`, `pipeline/live_etf_validation.py`, `pipeline/live_v2_validation.py`, `pipeline/recommendation_policy_v2.py`, `pipeline/research_screens_v2.py`, `pipeline/scoring_v2.py`, `pipeline/validation_framework.py`, `pipeline/requirements.txt`, `pipeline/config/applicability_matrix.json`, `business_profiles.json`, `estimate_collection.json`, `etf_benchmarks.json`, `metric_registry.json`, `recommendation_policy_v2.json`, `shadow_strategies.json`, and `pipeline/schemas/advisor.schema.json`.

Frontend: `src/App.jsx`, `src/pages/ResearchScreen.jsx`, `src/pages/LiveValidation.jsx`, and `src/styles/global.css`.

Tests/artifacts/docs: `pipeline/tests/test_canonical_v2.py`, `test_etf_comparison.py`, `test_production_hardening_v2.py`, append-only `pipeline/data/estimates/`, private `pipeline/data/staging/raw_provider/`, `public/data/validation/live_v2_validation.json`, `live_etf_validation.json`, and this report.
