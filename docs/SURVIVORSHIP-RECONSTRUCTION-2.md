# Survivorship Reconstruction, Round 2: The Ranking Probe

Round 1 (docs/SURVIVORSHIP-RECONSTRUCTION.md) produced an empty sample where it wanted a
sized bias, and this round's reframing edits mark that in place. This document runs the
test that needs no prices, quantifies the transfer contamination round 1 discovered from
two names, and closes the price gap forward permanently. Producers under
`research/audit/survivorship/round2/`. Pins unchanged from round 1, plus the price
archive manifest (`pipeline/data/price_archive/archive_manifest.json`).

Every value is marked measured, imputed, or unavailable. Sample sizes on every statistic.

---

## 1. The ranking probe (measured, the round's main event)

Producers: `ranking_probe.py`, `probe_analysis.py`. Method: at each of the 60 rebalance
dates, every dead-cohort CIK with as-filed facts visible on that date is scored through
the identical as-filed statement path and band scorer on the **price-free composite**:
profitability, financial health, growth, capital allocation, accounting quality,
weights renormalized over the five. Valuation and technical need prices and are
excluded, stated plainly. The excluded half is not the half whose job is avoiding
deaths. Survivor baseline: the 851 cache names scored identically at the same dates,
giving every dead name a same-day percentile. Names whose latest visible annual period
is older than 548 days count as unscored-stale, never silently excluded.

Scale: 88,739 name-date rows, 48,094 scored, 46% unscored. The unscored fraction runs
40 to 49% in every rebalance year, and it is itself a signal: a name that stopped
filing before it died is a coverage collapse the live publication gate
(`pipeline/data_health.py`) withholds from ranking.

### The cohort, corrected twice before use

The naive probe cohort (bankruptcy plus exchange-rule removal, stopped filing within 12
months) contained a right-censoring defect this round caught by enumerating its own
tail: events within 12 months of the snapshot cannot show post-event filings, so recent
ADR withdrawals by healthy foreign giants (HSBC, Lloyds, Barclays, BAT, TotalEnergies)
entered as deaths. The corrected cohort censors events after 2025-08-11: **984
true-death CIKs, of which 317 were scoreable on at least one rebalance date** (315
right-censored events excluded, reported, not discarded silently).

### Where dying names ranked (measured, censored cohort, n=8,845 name-months)

| Statistic | Value |
|---|---|
| Median percentile vs survivors | **8.3** |
| Top-decile share | 3.9% |
| Top-quintile share | 5.5% |
| Selection-proxy share (top 2.3%, the top-20-of-878 cutoff) | **2.74% vs 2.3% base rate** |
| Composite AUC (probability a dying name scores below a survivor) | **0.812** |
| Within 12 months of death (n=3,327) | median 4.4, AUC **0.833** |

Time-to-death gradient on the full uncensored true-death rows (n=18,657, includes the
contaminated tail, so these are the conservative bounds): median percentile 9.1 under
6 months, 9.1 at 6-12, 10.5 at 12-24, 18.5 beyond 24. The score demotes names harder as
death approaches, which is the direction the screens claim.

### Component discrimination (measured, first outcome test in eight rounds)

| Component | Dying-name median | Reading |
|---|---|---|
| Financial health block | **10.0** (n 13,662) | Earns its stated distress purpose |
| Altman Z (raw) | **-1.10** vs +1.13 for the acquisition cohort (Mann-Whitney p 2e-305, n 13,399/22,713) | The Round 6 retained-earnings ingest bought a working distress input |
| Profitability block | 42.1 (n 14,516) | Moderate discrimination |
| Accounting quality block | 59.5 (n 14,423) | **Does not discriminate deaths.** Piotroski and accruals read near-normal on dying names. The block screens earnings quality, not survival, and its 10% weight should not be described as a distress screen |

### The residual tail, enumerated rather than headline-ized

27 of 317 censored true-death names ever entered the selection proxy tail. Hand
inspection of the top tail names finds the residue is classification noise, not score
failure: foreign parents and financing subsidiaries whose US filing obligations ended
through channels the 12-month filter cannot see (Deutsche Bank, GSK, Lloyds Bank plc
the subsidiary), and take-privates mislabeled as exchange-rule removals (Atlantica,
GasLog). Genuine performance deaths that scored into the tail exist (IMV Inc.) and are
rare. The uncensored headline earlier in the analysis (5.84% tail share) is reported in
the committed logs and is a measurement of the classification's contamination, not of
the score.

### What the probe settles

The claim round 1 wanted, now measured on 317 names instead of inferred from 18: the
price-free score systematically demotes genuinely dying names (AUC 0.81, strengthening
to 0.83 as death approaches), the financial-health block and Altman Z do the work their
citations claim, the accounting-quality block does not, and admission of dying names
into the selection set is at or below base rate once classification noise is removed.
Survivorship bias in ranking terms is bounded small for this construction. The
return-stream magnitude for 2021-2025 remains unavailable at $0, and the probe cannot
speak to the valuation and technical components.

---

## 2. Transfer contamination, quantified (measured)

Producer: `transfer_contamination.py`. Round 1 found the Form 25 transfer problem from
two names. Two independent checks size it:

1. **Price continuation** (priced subsample, n=1,242): 88% trade more than 120 days
   past their event. This subsample is selection-biased toward transfers by
   construction (the provider only serves living tickers), so it bounds the
   contamination of the priced slice, not of the log.
2. **Filing continuation** (all 5,120 operating companies, right-censored events
   reported separately): still filing periodic reports 12 months after the event:
   bankruptcy 7%, exchange-rule removal **34%**, merger 17%, voluntary 9%.

Republished classification table (12-month filing-continuation basis):

| Classification | Raw count | Measured-dead rate | Adjusted deaths | Status |
|---|---|---|---|---|
| Bankruptcy | 275 | 0.93 | ~257 | measured |
| Exchange-rule removal | 1,434 | 0.66 | **~941** | measured |
| Merger / acquisition | 1,976 | 0.83 | ~1,646 (absorbed, not failed) | measured |
| Voluntary deregistration | 1,155 | 0.91 | ~1,055 | measured |
| Unclassified Form 25 | 280 | 0.58 | ~162 | measured |

The performance-death cohort 2020-2026 is roughly **1,198 names (257 bankruptcies plus
941 removals)**, a third smaller than round 1's raw bucket. The filing check still
overcounts deaths for foreign issuers who continue reporting through non-periodic
channels, as the probe's tail enumeration showed, so the adjusted counts are an upper
bound on true deaths.

---

## 3. The forward price archive (implemented, the permanent fix)

Producer: `pipeline/price_archive.py`, tests `pipeline/tests/test_price_archive.py`.

| Property | Value |
|---|---|
| Store | one JSON per ticker, date-keyed, **append-only, first write wins**, conflicting restatements logged to conflicts.jsonl instead of overwriting |
| Seeded | **2,151 tickers, 7,111,402 daily rows**, zero network (backtest cache plus the round 1 dead-price captures, taken before the provider purge) |
| Manifest | per-run counts plus a SHA-256 tree hash, same discipline as experiment manifests |
| Monitoring | `archive_health()` goes critical when the newest run is older than 4 days, surfaced beside statement health |
| Schedule | run `python pipeline/price_archive.py seed` after each daily refresh (the scheduled runner's job list gains one line) |
| **Archive start date** | **2026-08-11** |

The model-card statement this earns: survivorship bias in this repository is bounded
and shrinking from 2026-08-11 forward, because every name in the universe on any date
after the start is archived while alive. It is permanently unmeasurable at zero cost
for deaths between 2011 and 2025, and the 2026 delisting cohort was captured at the 49%
rate round 1 measured, before the purge reached it.

---

## 3a. Postmortem: the symlink clobber this round caught and fixed

The round 1 merged-cache builder wrote dead-name payloads through existing symlinks for
the 16 tickers that appear in both the survivor cache and the delisting log (live names
whose Form 25 covered a transfer or a debt delisting: AMT, LLY, PEP, PG, V, EEFT, RVTY
and nine others). That overwrote the pinned survivor cache files with statement-free
yfinance payloads, which is also the mechanical origin of round 1's two "dead" picks.
Fixed this round: the builder now refuses to write where a survivor entry exists
(`reconstruction_backtest.py` guard), the 16 files are restored from git, the price
archive entries seeded from the corrupted files were purged and re-seeded clean with
zero conflicts, and the reconstruction was re-run on the repaired merged cache. The
re-run's numbers replace round 1's in the record. The pinned-cache-tree hash check that
would have caught this immediately now has its use case documented: run it after any
job that touches a cache directory.

## 4. The corrected framing (applied to round 1's document)

Round 1's section 5 is retitled "The reconstruction attempt and its null" with the
empty-sample mechanism stated in the section head. The verdict is restated: the
return-stream bias is unmeasurable at zero cost, not measured-small, and the purchase
does not bind until real capital enters. The EntityPublicFloat staleness is now
explicit: float at the last 10-K can be years stale for a dying company, which admits
more dead names, which is conservative for the purpose.

## 5. What the ranking probe changes about the purchase decision

Before the probe, the free path had an empty sample and the purchase bought an unknown.
After the probe, the free path has: a measured AUC of 0.81 against 317 real deaths, a
measured tail admission at or below base rate after declassification, a measured
component table showing which blocks earn their distress claims, and an archive that
caps the problem going forward. What the ~$600-900/yr purchase now buys is narrower and
nameable: the 2021-2025 return-stream magnitude for a bias the ranking evidence bounds
small, plus clean delisting returns to retire the Shumway convention, plus dated index
membership. The recommendation stands with better justification: buy it when real
capital enters, not before, and re-run the reconstruction with real prices as the
acceptance test of the purchase itself.
