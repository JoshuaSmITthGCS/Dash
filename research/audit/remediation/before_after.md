# Remediation before/after, human-readable companion

Machine-readable: `before_after.json`. Pins: pit refresh
`advisor-2026-08-10T17:22:04`, price cache tree `9b41dfbfef494699...`, factor vintage
2026-06. Producers: `research/audit/round4/*.py`.

| Measurement | Before | After | Mechanism |
|---|---|---|---|
| Mean fundamentals coverage | 0.39 | 0.82 | EDGAR PIT batch enrichment |
| Spearman(coverage, final score) | +0.514 | +0.186 (+0.168 with shrink) | Fixed-feature imputation, multipliers removed |
| Financials vs rest score gap | +2.8 pts (p 0.032) | +0.3 (p 0.64) | Same |
| Identical-evidence score ratio from coverage | up to 1.87x | 1.0x by construction | No completeness multiplier in challenger |
| Provider outage visibility | silent | healthy / degraded / critical in payload | data_health.statement_health |
| Sub-floor names in ranked output | published | INSUFFICIENT DATA | publication gate at 0.35 coverage |
| ETFs in ranked stock output | VOO 63.5, VGT 61.6 | refused + gated | fetch_prices guard, coverage gate |
| Backtest reproducibility record | none | SHA-256 experiment manifest per artifact | validation/experiment_manifest.py |
| Monthly turnover (frozen cache) | 50.6% | 33.7 to 44.3% under buffer sweep | rank-buffer challenger, not promoted |
| Alpha bookkeeping | one authoritative -2.57% | pinned pair: -2.57% (net value path, 2026-08-03 cache) and +0.43% (gross picks, 2026-08-10 cache) | Task 1 bridge, model cards corrected |

Score dispersion and quantization, rank stability, sector means, factor loadings, and the
full turnover decomposition are tabulated in `docs/AUDIT-ROUND-4-FINDINGS.md` sections 2
through 5.
