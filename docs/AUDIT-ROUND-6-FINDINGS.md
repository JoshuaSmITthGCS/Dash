# Audit Round 6: The Corrected Spine, the Valuation Question, and the Deflated Estimate

Every number is scoped to these pins unless a row states otherwise.

| Pin | Value |
|---|---|
| Pit refresh id | `advisor-2026-08-10T17:22:04.440901+00:00` (sha256 `54f86b3e9bf861a4...`) |
| Price cache tree | `9b41dfbfef494699...` (860 tickers, unchanged since Round 4, never mutated) |
| EDGAR PIT store | pre-round 1,448,995 facts. Round 6 tag-union re-ingest (producer `pipeline/build_pit_fundamentals.py`, log committed) rebuilt it under the fixed `observations_for_concept`. Post-ingest row count in section 1 |
| OHLC cache | new `pipeline/data/ohlc_cache` (120-name sample, separate directory, pinned cache untouched) |
| costs.py | canonical square-root law is now the base scenario (coefficient 630), old base retained as labeled optimistic |
| Harness freeze | `pipeline/validation/harness_freeze.json`, decision status recorded |
| Noise standard | paired monthly difference vs 2 SE, now annotated with minimum detectable effects (section 6) |

Producers committed under `research/audit/round6/`.

---

## 1. Task 1: the corrected spine

PLACEHOLDER_SECTION_1

---

## 2. Task 2: re-runs on the corrected spine, and what happens to Round 5

PLACEHOLDER_SECTION_2

---

## 3. Task 3: the valuation block, reopened

PLACEHOLDER_SECTION_3

---

## 4. Task 4: the cost model correction

Producers: `task4_netcost.py`, `fetch_ohlc_and_spreads.py`. Code:
`pipeline/costs.py::IMPACT_SCENARIOS`.

### The default is now the canonical law

The base impact coefficient moves from 15 to 630 (the canonical square-root form, impact
of order daily volatility times the square root of participation, with volatility
supplied annualized: 1e4 divided by sqrt(252)). The old base of 15 survives only as the
clearly labeled optimistic scenario, because Rounds 3 through 5 published net-of-cost
figures under it and comparability requires it to stay computable. Stress is 2x
canonical. All 39 cost-model tests pass unchanged.

### Every net-of-cost figure, re-run

Annualized modeled drag from each run's actual trades, and net CAGR under the corrected
base:

| Run | AUM | Old model | Canonical | Stress | Net CAGR (canonical) |
|---|---|---|---|---|---|
| Restated baseline (TO 50.6%) | $100k | 8bp | 32bp | 65bp | 12.27% |
| Restated baseline | $10M | 12bp | 185bp | 370bp | 10.74% |
| Restated buffer 1.5 (TO 39.5%) | $100k | 6bp | 26bp | 51bp | 12.34% |
| Restated buffer 1.5 | $10M | 9bp | 146bp | 293bp | 11.14% |
| As-filed annual base (TO 22.2%) | $100k | 3bp | 14bp | 28bp | 19.56% |
| As-filed annual base | $10M | 5bp | 87bp | 175bp | 18.83% |
| As-filed stack 1.5 (TO 12.3%) | $100k | 2bp | 7bp | 15bp | 20.63% |
| As-filed stack 1.5 | $10M | 3bp | 45bp | 91bp | 20.25% |

Which conclusions change: none reverse at $100k, where drag stays under 32bp everywhere.
At $10M the ranking economics change materially: the buffer's cost case strengthens 13x
(it saves 39bp/yr at canonical versus 3bp under the old model on the restated book), and
the high-turnover restated champion loses 1.85pp/yr to modeled costs. Round 3's
"78bps/yr, 7.0% of gross return" statement was an optimistic-scenario number and the
model card note now says so.

### Spread measurement: unblocked, attempted, and honestly still open

OHLC now caches to a separate directory (never mutating the pinned price cache), and the
Corwin-Schultz estimator (Journal of Finance 67(2), 2012) runs against it. Result on the
120-name sample: median estimated full spread 65.7bps for liquid names (n 118, IQR 55.5
to 80.3) against the 2.0bps labeled proxy. That is not a measurement of effective
spread. Daily-frequency Corwin-Schultz is dominated by intraday volatility range, a
sensitivity the original paper documents, and TAQ-based effective spreads for liquid US
large caps run single-digit basis points. The honest state: the proxy remains a labeled
proxy, the CS machinery and OHLC schema now exist, and a measured effective spread
requires intraday quote data no current provider in the stack serves. The capacity
statement in the model card carries the canonical-law numbers, which are impact-driven
and do not depend on the spread floor.

### Model card

`docs/MASTER-METHODOLOGY.md` section 9 now states capacity next to alpha: roughly $13M
at a 50bps/yr impact budget, $50M at 100bps, $200M at 200bps under the canonical law on
the buffered as-filed book. A strategy with that profile is a personal-account
instrument, stated as such.

---

## 5. Task 5: the deflated estimate

Producer: `task5_dsr_pbo.py`. Inputs: the actual monthly return matrix of 20 backtest
variants produced across Rounds 3 through 5 (T=59 months), tested at both the available
N=20 and the frozen N=40 trial count.

| Instrument | Result | Threshold | Verdict |
|---|---|---|---|
| Observed Sharpe, as-filed base | 1.00 annualized (monthly 0.289, skew +0.01, kurtosis 2.37) | | |
| Expected max Sharpe of N unskilled trials | 0.20 ann (N=20), 0.23 ann (N=40) | | |
| Deflated Sharpe Ratio (Bailey and Lopez de Prado, JPM 40(5), 2014) | **0.958 (N=20), 0.952 (N=40)** | >= 0.95 | Marginal pass |
| PBO, CSCV 8 blocks, 70 splits (Bailey, Borwein, Lopez de Prado, Zhu, Notices AMS 61(5), 2014) | **0.69** | <= 0.50 frozen | **Fail** |
| Harvey, Liu, Zhu hurdle (RFS 29(1), 2016) | alpha t = 1.93 | \|t\| > 3 | **Fail** |

Read together, not separately. The Sharpe survives deflation by 0.002 to 0.008, and the
trial variance is estimated from correlated variants, which understates the deflator, so
the marginal pass is fragile in the unfavorable direction. The in-sample winner ranks
below the out-of-sample median in 69 percent of CSCV splits, which is a direct
overfitting signal across the variant family. The alpha t-statistic fails both the
conventional and the search-adjusted hurdle. The model card statement this supports:
the as-filed point estimate is not evidence of alpha after accounting for the search
that produced it. Recomputation on the corrected spine appears in section 2.

---

## 6. Task 6: power, annotated

Producer: arithmetic on the committed noise-standard rows, T months as stated, MDE is
the 2 SE paired threshold, and T* is the months of identical paired data needed for the
observed difference to reach the threshold (T* = T times threshold-over-difference
squared).

### Class A: similar books, genuinely informative comparisons

| Comparison | Observed dCAGR | MDE | Verdict | T* to detect observed |
|---|---|---|---|---|
| drop momentum_12_1 (as-filed annual) | -3.86pp | 3.31pp | **detected** | detected at T=59 |
| drop drawdown_resilience | +0.50pp | 1.42pp | noise, low power | ~476 months (~40y) |
| drop risk_adjusted | +0.27pp | 1.54pp | noise, low power | ~1,900 months |
| drop technical_extended | +0.45pp | 1.04pp | noise | ~315 months (~26y) |
| growth block zeroed (restated) | +0.12pp | 1.15pp | noise | ~5,400 months |
| buffer 1.25 / 1.5 / 2.0 (restated) | +0.30 / +0.16 / -0.32pp | 1.94 / 2.70 / 3.48pp | noise | 41y / 280y / 700y |

### Class B: substantially different books, no power at a five-year window

| Comparison | Observed dCAGR | MDE | T* |
|---|---|---|---|
| As-filed vs restated | +7.13pp | 12.99pp | ~196 months (~16y) |
| Fundamentals-only vs full (restated) | +1.80pp | 13.38pp | ~3,260 months, permanently underpowered |
| Cross-sectional vs bands (restated) | -0.75pp | 2.94pp | ~907 months (~76y) |

Reading: "noise" in Class A rows with T* under ~30 years is a small-difference
statement. Every Class B row is a power statement, and those comparisons are permanently
underpowered at any realistic window. They must be decided on other axes: determinism
(turnover, cost), construction correctness (PIT purity, coverage bias), and prospective
IC, which is exactly what the freeze protocol does. This annotation applies to Round 5's
own headline as much as to earlier rounds: the as-filed CAGR delta is a Class B row, and
Round 5 said "noise" where it should have said "unmeasurable at this window."

---

## 7. Task 7: loose ends

**Promotion decision.** Recorded in `pipeline/validation/harness_freeze.json`:
`HOLD recorded 2026-08-11 pending ownership response`, with the accrued cost per month
of holding stated in the file: one forfeited prospective month if promoted later, plus
one further month of the champion ranking with Spearman(coverage, score) +0.51 and the
1.87x identical-evidence spread. The decision remains an ownership call. The file now
makes its price visible.

**Financials unmasking.** Measured closed by the imputation construction: the gap is
+2.8 (p 0.032) under production, +7.9 (p <0.001) under multiplier removal alone, and
+0.3 (p 0.64) under fixed-feature imputation at restored coverage (Round 5 Task 2 table,
re-verified this round on the re-ingested store in section 2). The fixed-feature
challenger closes it fully. No additional sector-conditional treatment is required
beyond what the sector-conditional normalizer already does. If ownership promotes the
multiplier removal alone without the imputation challenger, the +7.9 gap ships, and the
interim mitigation is the one Round 5 stated: sector-relative screens are unaffected,
cross-sector ranking carries the gap.

**Survivorship, scoped for decision.** What it takes: (a) a dated universe-membership
series, (b) delisted names' fundamentals and prices, (c) delisting-return treatment per
Shumway (Journal of Finance 52(1), 1997), -30% imputation for performance-related
delistings. Options, decision-ready:

| Option | Provides | Cost | Gap left |
|---|---|---|---|
| Sharadar (Nasdaq Data Link) | Fundamentals + prices for ~21,000 active and delisted US tickers to 1998, point-in-time ready | ~$600-900/yr personal license (Round 1 pricing band, current listing at sharadar.com) | Index membership dates |
| Norgate Data | Survivorship-bias-free US prices with historical index membership | ~$300-500/yr US package | Fundamentals for delisted names |
| CRSP (via WRDS, now Morningstar) | The academic standard, delisting returns included | Institutional pricing, typically >$10k/yr | Cost, access model |
| EDGAR alone (free) | Filings of deregistered issuers are retained, so as-filed fundamentals extend to dead companies once the entity map stops filtering to current tickers | $0 plus engineering | No prices, no delisting returns, no membership dates. Cannot close the bias alone |

Recommendation to ownership: Sharadar plus Norgate, roughly $1,000-1,400/yr combined,
closes all three requirements. EDGAR-only closes the fundamentals half at zero dollars
and leaves returns unmeasurable, which is the binding half. Until purchased, every
backtest remains survivorship-biased and section 1 says so on every table.

---

## 8. Grades

PLACEHOLDER_GRADES
