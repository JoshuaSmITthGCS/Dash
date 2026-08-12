# Pre-Freeze Construction Round: Five Signals, Five Specifications, Five Runs

The harness freezes 2026-09-01. This round builds the six never-started recommendations
from the original audit to their published specifications and enters them as
challengers. Hard rule honored: one specification per signal, one backtest run per
signal, parameters from the papers. No variant of any signal was compared against
another variant of itself.

Pins: as-filed TTM quarterly spine (round 6), price cache tree `9b41dfbfef494699...`,
EDGAR PIT store at 4,867,491 observations (post R&D/SG&A ingest, log committed),
factor vintage 2026-06, driver `research/audit/preFreeze/preFreeze_backtests.py`
(sha256 in the freeze file). Every backtest row below is **Class B** (different books,
MDE stated beside each paired difference) and none of it promotes anything. These
signals exist to enter the harness, not to win a backtest.

---

## The single-run table

Producer: `preFreeze_analysis.py`. Incumbent row for scale only.

| Variant | TO/mo | CAGR | Max DD | Six-factor alpha (t) | HML (t) | RMW (t) | paired dCAGR / MDE |
|---|---|---|---|---|---|---|---|
| Incumbent (as-filed Q base) | 24.3% | 20.06% | -28.2% | +8.44 (2.54) | -0.04 (-0.6) | +0.31 (2.1) | |
| Orthogonal value-quality | 25.0% | 19.85% | -27.1% | +8.38 (2.54) | -0.04 (-0.6) | **+0.39 (2.6)** | -0.19 / 2.34 noise |
| MAX exclusion screen | 30.6% | 20.78% | **-25.8%** | +9.68 (2.70) | +0.00 (0.1) | +0.30 (2.0) | +0.60 / 3.35 noise |
| Net issuance | 24.5% | 21.51% | -25.3% | +10.23 (3.31) | -0.04 (-0.5) | +0.31 (2.2) | +1.34 / 2.63 noise |
| Parsimony 1/N (6 signals) | 31.1% | 16.25% | -30.2% | +5.33 (1.11) | +0.09 (0.8) | +0.23 (2.0) | -3.67 / 7.55 noise |
| Intangible-adjusted book | 24.4% | 19.68% | -27.8% | +8.89 (2.71) | -0.04 (-0.5) | +0.30 (2.0) | -0.49 / 2.00 noise |

Every paired difference sits inside its threshold. The net-issuance alpha t of 3.31 is
one draw from an N=50 search family on a survivorship-biased five-year window and is
reported, not celebrated. The harness adjudicates all of it from 2026-09-01.

---

## Task 1: value-quality orthogonalization

**Specification.** Asness, Frazzini, and Pedersen, Review of Accounting Studies 24(1),
2019: construct quality exposure independent of value. Implementation: at each
rebalance, the profitability, growth, and financial-health category scores are
regressed cross-sectionally on log book-to-market, the residual is rescaled to the
original category distribution, and the fundamentals composite is rebuilt from the
adjusted categories with the production coverage multiplier. Book-to-market is the
conditioning characteristic. EBITDA/EV appears as a diagnostic only.

**Exposure table, section 3.3 format** (producer `task1_exposure_table.py`, pinned
2026-08-10 EDGAR-augmented snapshot):

| Category | Weight | Before (vs B/M) | After |
|---|---|---|---|
| Valuation | 0.28 | +0.508 (n 828) | +0.508 (n 828) |
| Profitability | 0.26 | -0.362 (n 828) | **-0.070** (n 828) |
| Growth | 0.11 | -0.342 (n 827) | **-0.084** (n 827) |
| Financial health | 0.15 | -0.220 (n 785) | **-0.099** (n 785) |
| Capital allocation | 0.10 | +0.052 | +0.052 |
| Accounting quality | 0.10 | -0.025 | -0.025 |
| **Composite** | | **-0.115** | **+0.087** |

Rank correlation before vs after: 0.971. Diagnostic: after-composite vs EBITDA/EV
+0.592 (n 403). Backtest: RMW loading rises from +0.31 to +0.39 (t 2.6) with alpha
unchanged, which is the construction doing what the paper says it does.

**Verdict: construction fix. The QARP-versus-value framing dissolves.** Both exposures
survive in one composite: the valuation block keeps its full +0.508 value content and
the quality half keeps its quality content with the value short removed. The
methodology page does not need a QARP declaration. It needs this challenger to clear
the harness.

## Task 2: the MAX exclusion screen

**Specification.** Bali, Cakici, and Whitelaw, Journal of Financial Economics 99(2),
2011: MAX = mean of the five highest daily returns in the prior month (21 sessions).
Implementation: names in the top cross-sectional MAX decile are removed from the
ranked selection set. Exclusion screen, not a scored factor. No alternative windows or
top-k definitions were tested.

**Row reading.** Drawdown improves 2.4pp (-28.2 to -25.8), the lottery-name exclusion
costs nothing measurable in CAGR (+0.60 inside a 3.35 MDE), and turnover rises 6.3pp
because names near the decile boundary cycle in and out of eligibility. The turnover
cost is the screen's real price and the buffer layer absorbs part of it in the full
stack.

## Task 3: net issuance

**Specification.** Pontiff and Woodgate, Journal of Finance 63(2), 2008 (and Daniel
and Titman, Journal of Finance 61(4), 2006): net share issuance = log change in
split-adjusted shares outstanding over the trailing twelve months, from the as-filed
diluted share counts already in the PIT store.

**Replace, not supplement.** Issuance REPLACES buyback yield in the
capital-allocation block. Justification from the papers rather than a horse race:
Pontiff-Woodgate's measure is total net issuance, of which repurchase is one side.
Buyback yield captures share-count reduction and is blind to dilution from raises,
converts, and stock-financed acquisitions, which is exactly the half the papers show
carries the negative predictive content. Carrying both would double-count repurchases
and still miss nothing issuance misses. The issuance score enters as a cross-sectional
winsorized percentile (lower issuance is better), so no band thresholds were invented.

## Task 4: intangible-adjusted book value

**Specification.** Arnott, Harvey, Kalesnik, and Linnainmaa, Financial Analysts
Journal 77(1), 2021, via the standard Peters-Taylor capitalization: knowledge capital
is perpetual-inventory R&D at 15 percent depreciation, organization capital is 30
percent of SG&A capitalized at 20 percent depreciation, adjusted book = common equity
plus both capitals. Adjusted P/B replaces raw P/B, and Price/Tangible Book retires
(its weight renormalizes). No alternative depreciation rates were run.

**The ingest that made it fit before the freeze.** R&D and SG&A were not among the 31
ingested concepts. `ResearchAndDevelopmentExpense` and
`SellingGeneralAndAdministrativeExpense` were added to CONCEPT_TAGS
(edgar_facts.py) and ingested for all 861 CIKs in 76 minutes: 102,419 new
observations (28,462 R&D rows, 73,957 SG&A rows), store now 4,867,491.

**Row reading.** Near-neutral at the block's weight: the two book metrics carry 10
percent of a 28-percent block, so even a repaired metric moves little. The effect on
the valuation block's value exposure is definitionally the point for the harness: the
adjusted metric prices intangible-heavy names against a book that includes what they
built, which the raw metric calls infinitely expensive.

## Task 5: the parsimony challenger

**Specification.** DeMiguel, Garlappi, and Uppal, Review of Financial Studies 22(5),
2009: equal weights, because they were not chosen. Six signals with the strongest
replication records: EBITDA/EV, gross profits/assets, net issuance, asset growth,
momentum 12-1, Altman Z (the probe validated its distress discrimination at AUC 0.81
in docs/SURVIVORSHIP-RECONSTRUCTION-2.md section 1). Each winsorized at 1/99, ranked
sector-conditionally where at least 8 peers exist, equal-weighted. No modifiers, no
coverage multipliers, no blend, minimum 4 of 6 signals to score.

**Row reading.** The bare 6-signal ranker returns less than the incumbent on this
window (-3.67pp inside a 7.55 MDE, the least-similar book of the round) with higher
turnover and no buffer. That is the honest cost of parsimony on one sample, and
exactly the comparison the harness exists to settle: 35 hand weights versus 6 equal
ones, decided prospectively or not at all.

---

## The freeze entries

`pipeline/validation/harness_freeze.json` now carries **11 challengers**, the five new
entries each recorded with specification citation and the driver hash. Trial
accounting updated in the file: 42 enumerated variants across all rounds (35 through
Round 6, 2 survivorship reconstruction runs, 5 pre-freeze construction runs), and the
**DSR trial count for every future deflated statistic moves from 40 to 50**. The
deflator grew because the family grew, which is the honest direction.

## The six original recommendations, final status

| Recommendation | Status |
|---|---|
| Quality-minus-junk construction | **Built** as the AFP orthogonalization (the QMJ substance is quality-independent-of-value, which is what the residualization delivers) |
| MAX / idiosyncratic-volatility screen | **Half built.** MAX is built to the BCW specification. The idiosyncratic-volatility half is **deferred**: it requires choosing a residualizing factor model, and every candidate choice is a search step this round's rule forbids. It enters the next construction window with a single pre-registered spec (FF3 residuals, per Ang, Hodrick, Xing, Zhang, JF 61(1), 2006) or not at all |
| Net-issuance factor | **Built**, replaces buyback yield |
| Intangible-adjusted book value | **Built**, including its data ingest |
| Value-quality orthogonalization | **Built and verified** on the snapshot (composite -0.115 to +0.087) |
| Collapse to a small orthogonal signal set | **Built** as the 6-signal 1/N challenger |

## Roadmap rescore

| Category | Before | After | Reason |
|---|---|---|---|
| Data integrity | 92 | 93 | R&D/SG&A concepts ingested, store at 4.87M |
| Validation methodology | 85 | 85 | Unchanged, the gate is the gate |
| Cost and turnover | 74 | 74 | Unchanged this round |
| Portfolio construction | 42 | 42 | Untouched by design, this was a signal round |
| Signal construction | 28 | **65** | Five specification-faithful challengers built and entered. Not higher because nothing is promoted and the incumbent still ships |
| Missing factors | 15 | **70** | Five of six recommendations built. Not higher because idiosyncratic volatility is deferred with its reason, and built is not validated |

Nothing failed to land. One sub-item (idiosyncratic volatility) is deferred with its
reason stated above rather than built badly under deadline. The clock starts
2026-09-01 with eleven challengers in the frozen set.
