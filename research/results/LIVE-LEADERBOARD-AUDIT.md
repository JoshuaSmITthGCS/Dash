# Audit of the published leaderboard

**The top of the ranking is decided by which companies received a data pull, not by which
companies scored well on the evidence.** Measured on `public/data/advisor.json`, model 3.2.0,
generated 2026-08-09.

This is the most consequential finding in the engagement so far, because unlike the factor
results it does not depend on any nine-year backtest. It is arithmetic on the artifact the site
publishes today, and it determines what the bucket planner allocates real money to.

---

## The finding, in five numbers

| | |
|---|---|
| Companies with `capital_allocation` and `accounting_quality` both resolved | **147 of 874 (16.8%)** |
| Of the top **100** by published score, how many come from that 16.8% | **100 of 100** |
| Best rank achieved by any company lacking those two categories | **#127** |
| Rank correlation between categories-resolved and published score | **+0.44** |
| Of the current top 20, how many were in the previous run's top 20 | **16 (80%)** |

No company outside the enriched 16.8% places anywhere in the top 100. The top 20 is drawn
entirely from the 40-company fully-published cohort — 4.6% of the universe.

---

## Why it happens

Two categories carry 20% of the score between them, and both depend on statement enrichment:

| category | weight | resolves for |
|---|---|---|
| capital_allocation | 10% | 107 / 834 lighter rows (13%) |
| accounting_quality | 10% | 107 / 834 lighter rows (13%) |

Within the lighter cohort, whether those two resolve is worth **20.8 points of median score**:

| lighter rows | n | median score |
|---|---|---|
| with both categories | 107 | **65.2** |
| without them | 727 | **44.4** |

The gap is not only the coverage multiplier. The four categories both cohorts *do* have also
score far higher for the enriched:

| category | published median | lighter median |
|---|---|---|
| valuation | 90.0 | 68.9 |
| profitability | 89.4 | 61.9 |
| financial_health | 98.0 | 67.9 |
| growth | 76.0 | 65.9 |

Enrichment supplies metrics that `weighted_available` then renormalises over. A company with
three of eight valuation inputs is scored on those three; a company with all eight is scored on
all eight. Those are not the same measurement, and they are sorted into one list.

---

## The part that makes it self-reinforcing

`enrichment_selection` in the published artifact:

```json
{"previous_top": ["THG","CRUS","NEM","DECK","HIG","MCY","LOPE","SIGI","GMED","FTDR",
                  "ALGN","COP","GL","PRI","ADBE","MTG","GNTX","PYPL","EOG","EXEL"],
 "challengers": ["JAZZ","WSFS","LYFT","WDC","DINO"], "priority_count": 25}
```

Enrichment priority goes to **the previous run's top 20**. Enrichment resolves the two
categories worth 20 points of median score. So:

1. A company scores well, and is enriched next run.
2. Enrichment resolves two categories worth ~20 points, and lifts the other four.
3. It stays in the top 20, which is what earns it enrichment again.

**16 of the current top 20 were in the previous top 20.** One is a rotated-in challenger. The
Phase 1 `enrichment_rotation` fix reduced this loop — five challengers per refresh do enter,
and DINO reached #13 that way — but it did not break it. At five rotations per refresh against
874 companies, a name outside the priority list waits a long time for the data that would let
it compete.

This is the Phase 0 defect family — coverage read as quality — one level up from where it was
found. There it was a scalar mislabelled `confidence`. Here it is the ranking itself.

---

## What this does and does not mean

**It does not mean the top 20 are bad companies.** They may well be good ones. The claim is
narrower and worse: *the ranking cannot tell you*, because the names it ranks highest are the
names it measured most, and the two are the same set by construction.

**It does not mean the score is broken.** Within the enriched cohort the comparison is sound —
those 147 are measured alike. The defect is the merge: 874 rows sorted into one column when 727
of them were scored on a materially thinner evidence base.

**It does mean the bucket planner is allocating on a biased list.** It splits available funds
across the top 8 by score. All 8 come from a 40-company cohort chosen by last run's ranking.

---

## What would fix it, in order of cost

1. **Rank within comparable cohorts, not across them.** Publish the enriched cohort and the
   lighter cohort as separate ordered lists, or mark the boundary in the merged one. This is a
   presentation change and it removes the false comparison immediately, without touching the
   scoring.
2. **Break the priority loop.** Allocate enrichment by *coverage deficit* rather than by
   previous score — pull the companies that lack the two categories, not the ones that already
   have them. Requires no new provider budget, only a different selection key.
3. **Withhold rather than renormalise for a category defined by absent inputs.** The
   required-for-score gate already does this per category. The same logic applied to the
   *overall* score would leave a thinly-measured company unranked rather than ranked low, which
   is honest and also removes it from the comparison rather than placing it 700th.
4. **Measure the residual.** Once cohorts are comparable, re-run the Phase 5 information
   coefficients within each. If the enriched cohort's score predicts and the lighter one's does
   not, that is a data problem. If neither does, that is the model.

Options 1 and 2 are small, independent of every open factor question, and would change what a
user sees tomorrow. Nothing here requires resolving whether valuation works.

---

## Reproducing

```
PYTHONPATH=pipeline python research/audit_leaderboard.py
```

Reads the published artifact only. No network, no store, no backtest.
