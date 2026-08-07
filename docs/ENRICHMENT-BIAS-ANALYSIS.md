# Enrichment Bias — how much does shortlist gating shape the ranking?

Reproducible by: `python pipeline/enrichment_bias.py` (no network access). Output:
`pipeline/reports/enrichment_bias.json`.

## The defect

`fetch_advisor.select_enrichment_priority()` builds the statement-enrichment queue from the
previous refresh's top 20 (`INCUMBENT_ENRICH_LIMIT`) plus five new candidates
(`CHALLENGER_ENRICH_LIMIT`). Statement enrichment is what produces EV/EBITDA (27% of
valuation), ROIC (26% of profitability), interest coverage (30% of financial health),
Piotroski F (45% of accounting quality), and the whole of `capital_allocation` and
`accounting_quality`.

So the evidence carrying most of the model's weight is computed almost exclusively for
companies a *preliminary* score — one that does not contain that evidence — already ranked
highly. And because the queue is seeded from the last refresh, today's leaders are drawn from
yesterday's leaders.

## Choosing a measurement source

The last published refresh is a **fast** intraday refresh: it re-polls ~111 of 921 names and
carries every other row forward stale. Measured on that artifact, 288 of 290 unenriched rows
are carry-forwards, so "not statement-enriched" would mostly mean "not re-polled this cycle" —
a different thing entirely, and one that inflates the apparent gate footprint.

This analysis therefore runs against the most recent clean **full-universe** refresh
(`2026-08-06T00:23:32Z`, 920 polled, 150 statement-enriched, zero carry-forwards), field-
trimmed and committed at
`pipeline/data/full_refresh_snapshots/advisor-2026-08-06T002332-full.json` so the result
reproduces without network access. `enrichment_bias.py` refuses to score any payload whose
rows are more than 5% carry-forwards rather than reporting a confounded number.

## What the gate leaves behind

378 published/screened names, 150 statement-enriched (39.7%).

| Category | Scored for | Coverage |
|---|---:|---:|
| valuation | 378 / 378 | 100% |
| profitability | 378 / 378 | 100% |
| growth | 378 / 378 | 100% |
| financial_health | 345 / 378 | 91% |
| **capital_allocation** | **150 / 378** | **40%** |
| **accounting_quality** | **149 / 378** | **39%** |

### The structural finding

| Rank band | Statement-enriched |
|---|---:|
| Top 10 | 10 / 10 (100%) |
| Top 20 | 20 / 20 (100%) |
| Top 40 | 40 / 40 (100%) |
| Top 100 | 100 / 100 (100%) |
| Whole sample | 150 / 378 (39.7%) |

**No unenriched name reaches the top 100.** Not a low rate — zero, out of 228 unenriched names.
`capital_allocation` and `accounting_quality` are 20% of the fundamental weight, and for 60% of
the published universe they cannot contribute at all. Those names are ranked on a strictly
smaller evidence base than the names they are ranked against.

### What the score gap does *not* prove

Enriched names average **+25.29** score points over unenriched ones. That number is real but it
is mostly circular, and reporting it as the cost of the defect would overstate the case.
Enrichment is targeted at names the preliminary model already liked, so those names should look
better on the categories that need no enrichment at all — and they do:

| Category (needs no enrichment) | Enriched | Not enriched | Gap |
|---|---:|---:|---:|
| financial_health | 77.4 | 57.6 | +19.8 |
| profitability | 73.5 | 54.2 | +19.3 |
| growth | 69.1 | 56.5 | +12.6 |
| valuation | 72.5 | 60.8 | +11.8 |

Most of the headline gap is selection, not suppression. The defect is real and structural; this
particular statistic is not the evidence for it.

Enrichment rate also varies sharply by sector — Energy 71%, Financial Services 67%, Basic
Materials 19%, Consumer Defensive 17% — so the gate tilts sector composition as well as rank.

## What remains blocked

The decisive comparison — run the universe unseeded, then measure top-40 and top-100 overlap,
Spearman rank correlation, which unconstrained top-40 names never entered the production
shortlist, and their forward returns — needs a live enrichment pass over ~900 names. This
environment has no route to any market-data provider.

```bash
FULL_UNIVERSE_RESEARCH=true python pipeline/fetch_advisor.py
python pipeline/enrichment_bias.py   # re-run to populate unconstrained_comparison
```

`FULL_UNIVERSE_RESEARCH=true` is implemented and tested this session: it ignores the previous
ranking entirely, lifts the challenger cap, and sets the statement budget to the universe size
(`ADVISOR_EXTENDED_LIMIT` still wins if set, so the run can be sliced across several jobs to
fit the Actions budget). The test suite asserts that a populated `previous_top` and an empty
one produce byte-identical selections in research mode — the bias cannot leak in by
construction, not merely by convention. It is not the default production path.

## How much this matters

Less than it would have before `docs/P0-Q1-BENCHMARK.md`. That regression found no residual
alpha after controlling for the six factors this model targets (annualized alpha −2.57%,
Newey-West |t| = 0.437). A gate that starves an alpha-generating process of its best inputs is
a serious defect; a gate that starves a process not yet shown to generate alpha is a
correctness problem whose payoff is unproven. Fix it because the ranking should mean what it
claims to mean, not because there is a demonstrated edge waiting behind it.
