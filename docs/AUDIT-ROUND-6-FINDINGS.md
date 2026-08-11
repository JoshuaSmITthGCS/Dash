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

Producers: `pipeline/build_pit_fundamentals.py` (re-ingest under the fixed
`observations_for_concept`), `task1_coverage_after.py`, `asfiled_ttm_backtest.py`,
`pipeline/tests/test_asfiled_backtest.py` (seven tests, including TTM visibility).

### The re-ingest

The tag-union re-ingest processed all 861 mapped CIKs in 34 minutes and grew the store
from 1,448,995 to **1,751,058 rows on disk (+302,063)**, logging 70,514 restatements,
with periods reaching back to 1980. The added rows are exactly the history the first-tag
defect had discarded, plus the newly ingested retained-earnings concept (49,798 rows).

### Coverage by year, republished (share of 859 mapped names, visible each Jan 1)

| Year | revenue | net income | op income | assets | equity | OCF | capex | D&A | retained earnings |
|---|---|---|---|---|---|---|---|---|---|
| 2011 | 0.27 (was 0.01) | 0.32 | 0.22 | 0.59 | 0.59 | 0.32 | 0.27 | 0.22 | 0.56 |
| 2014 | 0.68 (was 0.10) | 0.76 | 0.59 | 0.80 | 0.80 | 0.77 | 0.68 | 0.64 | 0.76 |
| 2017 | 0.76 (was 0.11) | 0.85 | 0.68 | 0.87 | 0.87 | 0.85 | 0.77 | 0.73 | 0.84 |
| 2020 | 0.89 | 0.92 | 0.75 | 0.93 | 0.93 | 0.91 | 0.84 | 0.80 | 0.90 |
| 2023 | 0.95 | 0.98 | 0.80 | 0.98 | 0.98 | 0.97 | 0.90 | 0.86 | 0.95 |
| 2026 | 0.97 | 1.00 | 0.83 | 1.00 | 0.99 | 0.99 | 0.91 | 0.89 | 0.97 |

The income columns now track the balance-column baseline instead of sitting an order of
magnitude below it. The residual 2011-2014 thinness is the genuine XBRL tagging era, not
the defect. The usable as-filed window widens from 2021-2026 to roughly 2015-2026 for
income-derived metrics.

**Retained earnings and Altman.** Post-ingest, Altman Z resolves for **701 of 876 names
(80%)** on the pinned snapshot, against the 66% cap Round 5 recorded. The remaining gap
is names lacking the tag or a compatible variant's inputs, not a missing concept.

### The cadence-constant comparison

Producer: `task2_analysis.py`. Same cache, same calendar, same estimator (HAC6,
arithmetic, n 58) on every row.

| Run | TO/mo | CAGR | Max DD | Six-factor alpha | RMW | MOM |
|---|---|---|---|---|---|---|
| Restated TTM quarterly (R4 baseline) | 50.6% | 12.59% | -19.0% | +0.43%/yr (t 0.09) | +0.22 (t 1.1) | +0.32 (t 2.0) |
| **As-filed TTM quarterly (corrected spine)** | **24.3%** | **20.06%** | **-28.2%** | **+8.44%/yr (t 2.54)** | +0.31 (t 2.1) | +0.02 (t 0.2) |
| As-filed annual (corrected store) | 22.4% | 16.86% | -28.4% | +6.14%/yr (t 1.78) | +0.51 (t 3.4) | -0.04 (t -0.3) |
| As-filed annual (R5, pre-correction, withdrawn) | 22.2% | 19.70% | -27.8% | +9.09%/yr (t 1.93) | +0.40 (t 2.5) | -0.04 (t -0.3) |

Which delta is which:

1. **Restatement bias, isolated** (row 1 vs row 2, cadence constant): +7.61pp paired
   CAGR (2 SE threshold 12.85pp, a Class B power row), alpha +0.43 to +8.44%/yr with
   the t-statistic moving from 0.09 to 2.54, turnover halving from 50.6% to 24.3%, and
   mean pick overlap of **10 percent**. The restated and as-filed systems hold
   different portfolios almost everywhere, and the restated system's extra 26pp of
   monthly turnover is restatement-and-availability churn, not signal.
2. **Cadence, isolated** (row 2 vs row 3, spine constant): quarterly adds 1.9pp of
   turnover and +3.20pp CAGR against annual. Round 6's premise that cadence carried
   much of Round 5's delta is measured small on the turnover axis and material on the
   return axis.
3. **The tag-union correction, isolated** (row 3 vs row 4): Round 5's annual headline
   falls from 19.70% to 16.86% CAGR and its alpha from +9.09 (t 1.93) to +6.14
   (t 1.78) on the corrected store. Round 5 section 1 numbers are **withdrawn and
   replaced** by rows 2 and 3 of this table. Its provisionality flag was correct.

The three-way table's own caveats stand on every row: survivorship-biased universe,
one five-year window, and the multiple-testing battery of section 5 applies to row 2's
alpha exactly as it did to Round 5's.

---

## 2. Task 2: re-runs on the corrected spine, and what happens to Round 5

PLACEHOLDER_SECTION_2

---

## 3. Task 3: the valuation block, reopened

Producer: `task3_valuation_study.py` plus the per-category decomposition committed in
the same directory. All on the pinned refresh with EDGAR-augmented raw metrics, post
re-ingest.

### 3.1 The constituents carry value exposure

Raw metric vs value proxies, Spearman (a negative sign for a multiple IS value
exposure, and the -1.00 diagonal cells are the proxy correlating with its own inverse,
reported for scale):

| Metric | vs book-to-market | vs earnings yield | vs EBITDA/EV |
|---|---|---|---|
| ev_to_ebitda | -0.52 (n 636) | -0.65 (n 671) | (own inverse) |
| ev_to_ebit | -0.37 (n 639) | -0.73 (n 676) | -0.87 (n 639) |
| ev_to_fcf | -0.39 (n 691) | -0.56 (n 730) | -0.59 (n 599) |
| forward_pe | -0.53 (n 816) | -0.68 (n 860) | -0.61 (n 670) |
| **peg** | **-0.09 (n 762)** | **-0.07 (n 800)** | **-0.05 (n 627)** |
| price_to_sales | -0.45 (n 825) | -0.47 (n 863) | -0.60 (n 670) |
| price_to_book | (own inverse) | -0.47 (n 820) | -0.52 (n 636) |
| price_to_tangible_book | -0.79 (n 610) | -0.48 (n 604) | -0.52 (n 457) |

Seven of eight metrics carry strong value exposure. PEG carries none, on any proxy,
which independently confirms the config's own skepticism about it.

### 3.2 The aggregation is NOT the defect

Valuation category score vs the proxies:

| Construction | vs B/M | vs earnings yield | vs EBITDA/EV |
|---|---|---|---|
| Band mode category | +0.51 (n 828) | +0.65 (n 865) | +0.88 (n 672) |
| Band mode, sector-demeaned ranks | +0.52 (n 827) | | |
| Fixed-feature category | +0.52 (n 828) | +0.55 (n 865) | +0.82 (n 672) |
| Fixed-feature, complete cases only (imputed weight <= 10%) | +0.58 (n 545) | | |

The category preserves its constituents' exposure under both normalizations. The
imputation-shrinkage attenuation Round 5 characterized is real and small here: +0.58
complete-case against +0.52 overall, roughly 0.06 of rank correlation, nowhere near
enough to explain a missing tilt.

### 3.3 Where the value tilt actually dies: the blend, by design

Category scores vs book-to-market, with category weights:

| Category | Weight | vs B/M |
|---|---|---|
| Valuation | 0.28 | **+0.508** (p 1e-55, n 828) |
| Profitability | 0.26 | **-0.362** (p 4e-27, n 828) |
| Growth | 0.11 | -0.342 (p 4e-24, n 827) |
| Financial health | 0.15 | -0.220 (p 5e-10, n 785) |
| Capital allocation | 0.10 | +0.052 (p 0.10, n 827) |
| Accounting quality | 0.10 | -0.025 (p 0.50, n 823) |
| **Fundamentals composite** | | **-0.114** (p 1e-3, n 828) |

The diagnosis Round 6's brief proposed is refuted, and the finding is larger. The
valuation block works exactly as configured. Its +0.51 value exposure at 28 percent
weight is arithmetically cancelled by the anti-value exposure of the quality half of
the model (profitability, growth, and balance-sheet strength together carry 52 percent
of weight at -0.22 to -0.36 each), which is the classic value-quality anticorrelation
(Novy-Marx, Journal of Financial Economics 108(1), 2013: profitable firms trade at
premium multiples). The composite is not "a profitability tilt wearing a
valuation-weighted config." It is a quality-at-reasonable-price blend whose net value
exposure is slightly negative (-0.11) at full coverage, and no valuation-block redesign
can change that while the category weights stand. The decision this creates is
ownership's, not construction's: if the product intends value exposure, the weights
cannot deliver it. If it intends QARP, the current profile is QARP and the methodology
page should say the words.

### 3.4 Challenger blocks, defined and entered

| Block | vs B/M | vs earnings yield | vs EBITDA/EV |
|---|---|---|---|
| Eight-metric incumbent | +0.57 (n 828) | +0.61 (n 864) | +0.81 (n 672) |
| Two-metric EV block (EBITDA 60 / FCF 40) | +0.41 (n 762) | +0.52 (n 802) | +0.84 (n 672) |
| Single-metric EV/EBITDA | +0.45 (n 636) | +0.54 (n 671) | +0.90 (n 672) |

On pure value-exposure grounds the incumbent block is not weaker than the challengers
(it contains the book metrics directly), and the challengers' case rests on parsimony
and redundancy, not on lost exposure. Both challengers are implemented as backtest
variants (`asfiled_ttm_backtest.py` `_val2` and `_val1`) and their five-year results on
the corrected quarterly spine appear in section 2's table. Neither is promoted. Both
enter the harness set.

PLACEHOLDER_VAL_BACKTESTS

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
