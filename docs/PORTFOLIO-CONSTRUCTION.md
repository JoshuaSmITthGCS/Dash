# Portfolio Construction

Status of the 6 construction methods the research contract specifies (brief section 12).

| Method | Status | Implementation |
|---|---|---|
| Score-weighted top-N | Built | `src/lib/fundsAllocation.js allocateFunds()` — weight ∝ score^2, configurable power |
| Equal-weight top-N | Not built | `allocateFunds()` always applies score-power weighting; no equal-weight mode exists |
| Liquidity-weighted | Not built | — |
| Volatility-scaled | Not built | Volatility itself is computed (`portfolioAnalytics.js annualizedVolatility`), but no construction method weights by it |
| Benchmark-aware constrained | Not built | — |
| Turnover-penalized optimized | Not built | — |

Only 1 of 6 exists. This was scoped down in this pass to make room for the two explicitly
requested features (portfolio move explanation, watchlist price targets) — building four more
optimizer-grade construction methods with real constraint handling is substantial standalone
work, not attempted here under time pressure.

**What was added this pass:** `src/lib/portfolioAnalytics.js shrinkCovarianceMatrix()` —
Ledoit-Wolf-style shrinkage of the existing sample covariance matrix
(`correlationDiversification`'s `covarianceMatrix`) toward a diagonal target. The raw sample
covariance is noisy for a portfolio with more holdings than return observations, which is
exactly the regime any of the above optimizer-based methods (benchmark-aware constrained,
turnover-penalized) would need a stable matrix for. Fixed intensity (default 0.2), not a
data-driven optimal intensity — that needs more return history than a typical portfolio-sized
problem has to estimate reliably. This is a prerequisite utility, not a construction method
itself; none of the methods above call it yet.

Research defaults for constraints (30 min holdings, 3% max single-name weight, ±5pp sector
active weight, beta 0.90-1.10, 20% one-way turnover cap, 2% ADV participation cap per
`pipeline/costs.py max_trade_for_adv_participation`) are cited in
`docs/RESEARCH-CONTRACT.md` but are not enforced by any construction method yet, since none
of the constrained methods are built.
