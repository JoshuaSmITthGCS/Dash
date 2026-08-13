# Survivorship Reconstruction at Zero Cost

The deliverable is a sized bias, not a closed one. Every table below marks each value
as **measured**, **imputed**, or **unavailable**. Producers are committed under
`research/audit/survivorship/`. Pins: price cache tree `9b41dfbfef494699...` (survivor
side, never mutated, dead-name prices live in a separate merged directory), EDGAR PIT
store as of the Round 6 re-ingest plus this round's dead-cohort ingest, backtest path
`research/audit/round6/asfiled_ttm_backtest.py` (as-filed TTM quarterly, the corrected
spine), survivor baseline `bt_q_base` from Round 6 section 1.

Round 6 section 7 scoped survivorship as a $1,000 to $1,400 per year purchase. This
round executes the free path first, which is larger than that table implied, because
EDGAR supplies not only fundamentals for dead issuers but the delisting event log
itself.

---

## 1. The delisting event log (measured)

Producer: `build_delisting_log.py`. Sources: EDGAR quarterly form indexes
(`edgar/full-index/{year}/QTR{q}/form.idx`, 2020Q1 through 2026Q3, cached) and the
per-CIK submissions JSON. Forms kept: 25 and 25-NSE (removal from listing), the Form 15
family (termination of registration). Classification uses the filer's own 8-K item
history: item 1.03 within a year before the event marks bankruptcy, item 2.01 within
180 days (or DEFM14A/S-4 within a year before) marks a completed acquisition, a
25-NSE with neither marks exchange-rule removal (the performance-related bucket),
Form 15 with no Form 25 marks voluntary deregistration.

| Measurement | Value | Status |
|---|---|---|
| Index rows kept (Forms 25, 25-NSE, 15 family, 2020Q1-2026Q3) | 18,714 | measured |
| Distinct CIKs | 6,388 | measured |
| Log entries after per-CIK collapse | 6,387 | measured |
| Operating companies (10-K/10-Q/20-F filed since 2019) | 5,120 | measured |
| Exchange-rule removal (performance bucket) | 1,434 | measured |
| Merger / acquisition | 1,976 | measured |
| Bankruptcy (8-K item 1.03) | 275 | measured |
| Voluntary deregistration (Form 15 path, plus unclassified Form 25) | 1,435 | measured |
| Date range | 2020-01-02 to 2026-08-10 | measured |
| Events with a recoverable ticker in submissions JSON | **1,331 / 5,120 (26%)** | measured |

One refinement the reconstruction itself surfaced: Form 25 is also filed for exchange
TRANSFERS and ticker renames, not only true delistings. The two "dead" names the
backtest ever selected (EEFT, RVTY) are exactly such artifacts, identified because
their prices continue past the event, which is also why zero delisting exits fired.
The classification buckets above therefore overcount true deaths by the transfer
fraction, and a name whose prices continue is treated as alive by construction.

The weak link the brief predicted is measured below: the fraction of dead issuers
whose ticker survives in their submissions JSON. A CIK without a recoverable ticker
cannot be priced by any free source and drops to the residual in section 6.

## 2. Dead-cohort fundamentals (measured)

Producer: `ingest_dead_cohort.py`. The entity map's current-tickers filter
(`pipeline/data/pit/entity_map.json`, built from SEC `company_tickers.json`, which
drops deregistered issuers) is bypassed by fetching companyfacts per CIK from the
delisting log directly. Every observation flows through the identical tag-union
extraction (`edgar_facts.company_observations`) and the identical idempotent,
amendment-preserving store (`pit_fundamentals_store.ShardedStore`), so the
point-in-time visibility rules hold for the dead cohort by construction, and
`pipeline/tests/test_dead_cohort_pit.py` proves it end to end: a dead issuer's final
10-K/A becomes visible on its own filing date, never rewrites the earlier view, and
the last visible state persists after deregistration.

| Measurement | Value | Status |
|---|---|---|
| CIKs fetched with XBRL facts | 3,178 of 5,120 (1,942 have no companyfacts at all) | measured |
| New observations written to the PIT store | **2,931,458** (store grew from 1.75M to ~4.7M rows) | measured |
| EntityPublicFloat recovered | 2,847 CIKs, of which 1,184 at or above $1B | measured |

Dead-cohort as-filed coverage by year (producer `dead_coverage.py`, n=5,120), against
the survivor table in Round 6 section 1:

| Year | revenue | net income | assets | equity | OCF | retained earnings | any fact | survivors' revenue, for scale |
|---|---|---|---|---|---|---|---|---|
| 2011 | 0.03 | 0.04 | 0.08 | 0.08 | 0.04 | 0.07 | 0.08 | 0.27 |
| 2014 | 0.24 | 0.31 | 0.34 | 0.32 | 0.31 | 0.29 | 0.34 | 0.68 |
| 2017 | 0.31 | 0.40 | 0.42 | 0.41 | 0.40 | 0.39 | 0.43 | 0.76 |
| 2020 | 0.42 | 0.52 | 0.55 | 0.50 | 0.48 | 0.48 | 0.55 | 0.89 |
| 2023 | 0.49 | 0.60 | 0.61 | 0.56 | 0.56 | 0.54 | 0.61 | 0.95 |

The usable fundamentals window for the dead cohort is roughly 2014 onward at one-third
to two-thirds coverage. Pre-2011 is absent by XBRL physics, as the brief predicted.
Dead-cohort coverage runs about half the survivors' because deregistered issuers skew
small, foreign, and SPAC-shaped, and 38% never filed XBRL at all.

## 3. Price recovery (measured)

Producer: `price_recovery_audit.py`. One pass per ticker against the stack's price
provider, cached, no indefinite retries. A hit is at least 60 trading days of history
ending within 120 days of the delisting event. Prices up to but not through the
delisting date are sufficient, because the Shumway treatment supplies the final
return.

| Delisting year | Hit rate | Status |
|---|---|---|
| 2020 | 0 / 94 (0%) | measured |
| 2021 | 0 / 176 (0%) | measured |
| 2022 | 0 / 123 (0%) | measured |
| 2023 | 0 / 167 (0%) | measured |
| 2024 | 0 / 203 (0%) | measured |
| 2025 | 0 / 270 (0%) | measured |
| 2026 | 146 / 298 (49%) | measured |

| Classification | Hit rate |
|---|---|
| Bankruptcy | 8 / 34 (24%) |
| Exchange-rule removal | 90 / 640 (14%) |
| Merger / acquisition | 29 / 386 (8%) |
| Voluntary | 19 / 271 (7%) |
| **Overall** | **146 / 1,331 (11%)** |

This is the round's sharpest measurement and the free path's binding constraint: the
stack's price provider serves history for recently delisted tickers only, and purges
them within roughly a year. Prices for 2021 through 2025 deaths are not free. The
recovery-by-classification gradient the brief predicted (worst for the cohort that
matters) is visible but second-order next to the by-year cliff.

## 4. The Shumway treatment (imputed, by convention)

Shumway (Journal of Finance 52(1), 1997) documents that omitting delisting returns
biases measured performance upward and that performance-related delistings carry a
mean delisting return near -30 percent. Application here, by classification:

| Classification | Exit treatment | Status |
|---|---|---|
| Exchange-rule removal | last trade times (1 - 0.30), sensitivity -20/-30/-40 | **imputed** |
| Bankruptcy | same imputation band | **imputed** |
| Merger / acquisition | last trade stands (price converges to deal value) | measured proxy |
| Voluntary deregistration | last trade stands, counted separately | measured proxy, flagged |

The imputation is a documented convention standing in for data this round does not
have. It never appears in a measured column without this marker.

## 5. The reconstruction attempt and its null (retitled in round 2)

**This section reports an empty sample, not a small measured bias.** Every price hit
is a 2026 delisting inside a 2021-2026 window, so every admitted name was alive for
essentially the whole backtest and the reconstruction was structurally incapable of
producing a delisting exit. The zero below is the null of a test that could not run,
and docs/SURVIVORSHIP-RECONSTRUCTION-2.md runs the test that does not need prices.

Producer: `reconstruction_backtest.py`. Universe at each rebalance: the 860 survivors
plus every dead-cohort name live on that date (as-filed facts visible, price present,
EntityPublicFloat at least $1B at its last 10-K). That last clause is the universe
definition and it is a **size proxy, not an index-membership series**. Selection runs
through the unchanged Round 6 quarterly path. Dead names stop being selectable the
month their prices end, automatically, by the same visibility rules as everything
else.

### Deterministic findings first (measured)

| Count | Value |
|---|---|
| Dead-cohort names admitted to the reconstructed universe | 18 (hit, float >= $1B, event after 2021-06), of 878 usable |
| Dead names the strategy ever selected | **2, both exchange-transfer artifacts (CE, RVTY on the clean re-run), not deaths** |
| Delisting exits triggered across 60 rebalances | **0** |
| Position-months the survivor-only run held that the reconstruction replaces | **10 of ~1,200 (0.8%), clean re-run after the symlink postmortem** |
| Position-months the reconstruction holds that survivor-only never offered | **10** |
| Pick overlap | 0.99 over 60 rebalances |

### Estimated findings second (power-annotated)

| | Survivor-only (Round 6 base) | Reconstructed | Delta |
|---|---|---|---|
| CAGR (locked-picks gross) | 20.06% | 20.37% | paired **+0.16pp, MDE 0.64pp, n 59 (clean re-run): noise on an empty sample** |
| Six-factor alpha | +8.44%/yr (t 2.54) | +8.63%/yr (t 2.69, clean re-run) | inside noise |
| Sharpe | ~1.0 | 1.00 | |
| Shumway sensitivity (-20 / -30 / -40) | | **identical at all three values** | the imputation never fires because no held name died |

The Shumway machinery is built, tested against the classification table, and
measured-idle on this window: with zero delisting exits among held names, the -20/-30/
-40 band produces byte-identical results. The imputation is live code waiting for the
first held death, not a driver of any number above.

### What the zero means and does not mean

It means: on the recoverable slice of the dead cohort (which the price audit shows is
essentially the 2026 delistings), this strategy's large-cap floor, quality gates, and
momentum screens did not select names that subsequently died, and adding those names
back changes 1.2% of position-months and -0.07pp of paired CAGR. The strategy's
survivor-only backtest is not materially flattered by the recoverable dead.

It does not mean: the bias is measured zero for 2021 through 2025, whose dead names
have no free prices. Their as-filed fundamentals are now in the store, so a
fundamentals-only ranking probe (no prices needed) is the next free increment, but the
return-stream bias for those years is unmeasurable at $0 and says so in section 6.

## 6. What remains open at $0

| Residual | Status at $0 | What paid adds | Price |
|---|---|---|---|
| Index membership dates | Open. The reconstruction's universe is "filed XBRL, had a price, float >= $1B," a proxy named as such. True R1000-style membership dates are not free | Norgate historical index constituency | ~$300-500/yr |
| Pre-2011 delistings | Open by physics. XBRL phased in 2009-2011, and the Round 6 coverage table shows the era's floor. Irrelevant to the 2021-2026 backtest window, binding for any longer window | CRSP/Sharadar history to 1998 or earlier | ~$600-900/yr (Sharadar), institutional (CRSP) |
| Actual delisting returns | Replaced by the Shumway convention with a stated sensitivity band | CRSP delisting-return file, the measurement itself | institutional |
| Dead issuers without recoverable tickers | Dropped and counted in section 1. Their facts are ingested, their prices are not linkable | Vendor ticker-CIK history mapping | bundled with the above |

### The verdict, restated in round 2

The original verdict below overstated what the zero meant. Corrected: the return-stream
bias is **unmeasurable at zero cost**, not measured-small, because no recoverable slice
contains a death. What bounds it for free is the ranking probe
(docs/SURVIVORSHIP-RECONSTRUCTION-2.md): dying names' as-filed fundamentals are in the
store, and whether the score would have SELECTED them needs no prices. The purchase
timing conclusion is unchanged with the corrected justification: it does not bind until
real capital enters.

One universe-definition caveat made explicit: EntityPublicFloat is measured at the last
10-K, which for a dying company can be years stale, so a name that shrank from $3B to
$200M before dying still clears the $1B gate. That admits more dead names, which is
conservative for this purpose, and it is a property of the gate, not an accident.

### The original verdict (superseded)

The free path fully satisfied: the delisting event log (authoritative, 5,120 operating
companies classified), dead-cohort fundamentals (2.93M as-filed observations through
the same PIT machinery, tested), the transfer-vs-death distinction, and a sized bias
on the recoverable slice (~zero, deterministically and in the paired stream).

Partially satisfied: universe membership (a named float-proxy stands in), delisting
returns (convention, never fired), and the bias itself, sized only where prices
survive.

Open at $0: prices for 2021-2025 deaths, which is exactly the piece Sharadar
(~$600-900/yr) sells. The purchase decision now has a measured baseline instead of
nothing: the recoverable slice shows no bias, the strategy's construction avoids the
dying cohort by design, and the unmeasured slice is bounded by the same selection
mechanics. The honest recommendation: the purchase is not yet justified for backtest
hygiene alone. It becomes justified the day the prospective harness clears and real
capital enters, at which point the 2021-2025 gap should be closed before any
performance claim is published.
