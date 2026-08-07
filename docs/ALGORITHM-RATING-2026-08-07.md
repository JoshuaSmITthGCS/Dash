# Trading Algorithm Rating — 2026-08-07

Re-rate of the ValueSignal research score as it stands on `claude/trading-algorithm-rerate-79t01v`,
at commit `c485cc5`. The previous assessment of record is `PLATFORM_DESIGN_REVIEW.md` (3 August),
which rated architecture and process and returned a blocked launch verdict. This pass rates the
same system but leads with a question that review did not answer: **does the score have an edge?**

**Overall: 5.0 / 10.** The engineering, the data integrity, and the intellectual honesty have all
improved materially since the last review. The signal itself has not been shown to work, and the
one long-horizon test in the repository says it underperforms buying SPY.

---

## 1. The finding that dominates the rating

`pipeline/backtest_monthly_results.json` is the most credible artifact here: 60 monthly rebalances,
2021-08-02 → 2026-07-31, top 20 by score, score-weighted, executed at the next close after signal,
10bps one-way costs, 860 usable names.

| | Strategy | SPY |
|---|---:|---:|
| CAGR | 11.14% | **12.80%** |
| Annualized volatility | 19.43% | **17.18%** |
| Maximum drawdown | −27.03% | **−24.50%** |
| Sharpe (zero rate) | 0.644 | **0.791** |

It loses on all four. Not by a lot, but it loses on return *and* on all three risk measures
simultaneously, which is the hard version of losing — there is no risk-adjusted reading that
rescues it.

Decomposing the daily series against SPY (my calculation, from the published history):

- **Beta 0.70**, correlation 0.62
- **Annualized CAPM alpha +2.99%, t-statistic 0.44**
- Residual volatility 15.2% annualized; tracking error 16.1%
- Information ratio vs. SPY **−0.066**

The alpha is positive and completely insignificant. A t-stat of 0.44 over five years is the number
you get from noise. Meanwhile 15.2% of residual volatility is being carried to produce it — the
portfolio takes a very large idiosyncratic bet and is not paid for it.

Two things make this result *better* than it looks, and both need saying: the strategy runs at beta
0.70 through a strongly rising market, so some of the return shortfall is de-risking rather than bad
selection; and the score is not designed as a return forecast (`docs/MODEL-CARD.md` says so
explicitly). Two things make it *worse*: the backtest's own
`bias_disclosures.survivorship_bias` is `true` — the universe is today's candidate list, so the
test is run on names that survived to be listed today, which flatters the strategy and not SPY —
and filing dates are approximated at quarter-end + 45 days.

### The 52-week backtest does not rescue it

`backtest_historical_results.json` is the number that gets quoted: 13.89% vs SPY's 8.42% over 52
weeks. But it ran on a 120-name universe, and in that same file **IWM returned 14.78%** — the
strategy lost to the size-matched benchmark. The apparent edge over SPY is a small/mid-cap tilt,
and it disappears when you benchmark the tilt. That is a one-year window on a universe an eighth
the size of production; it should not be cited as evidence of anything.

---

## 2. What genuinely improved since the last review

Verified against the current tree, not taken from the docs:

- **The published payload is valid.** `public/data/advisor.json` parses. The merge markers that
  alone blocked the last launch gate are gone.
- **The enrichment collapse is fixed.** Statement enrichment now runs 124 of 126 attempted, against
  0 of 394 at `docs/BASELINE-2026-08-06.md`. Fundamental coverage moved from 0.21–0.35 to
  **0.69–0.98**; confidence from 0.39–0.48 to **0.70–0.89**. This was the single largest defect in
  the system and it is genuinely repaired.
- **Score spread recovered.** Published rows span 71.4–83.4 (was 51.5–57.6). Across the wider
  374-name screen universe the spread is 20.1–71.3, sd 10.67 — enough separation that ordinary
  refresh noise no longer reorders the list.
- **Route splitting exists.** `vite.config.js` now defines explicit chunk groups.
- **The stated weights are the realized weights.** Measuring tie-aware Spearman of each driver
  against the final score across 374 names: fundamentals **+0.944**, market behavior **+0.226**.
  A model that claims to be fundamentals-first is in fact fundamentals-first. Within fundamentals
  the category influence ordering (valuation +0.440, profitability +0.398, financial health +0.359,
  accounting +0.355, capital allocation +0.240, growth +0.221) tracks the stated weights
  sensibly. This is worth saying plainly because it is the part most systems get wrong.
- **Fundamentals and market behavior are orthogonal** (Spearman **+0.011**). The 18% market sleeve
  is adding independent information rather than restating the fundamental score. That is good
  design, deliberate or not.

The documentation deserves specific credit. `docs/LIMITATIONS.md`, `docs/MODEL-CARD.md`, and the
backtest's own `bias_disclosures` block state the weaknesses of this system more accurately than
this rating does. "No promotion has occurred" and "0 of 24 eligible IC periods" are in the model
card, unhedged. Most retail quant projects bury that; this one leads with it.

---

## 3. New defects found in this pass

### 3.1 The run manifest certifies the wrong model — `pipeline/observability.py:30`

```python
scores = [row.get("analysis_v2", {}).get("structural", {}).get("effective_score") for row in rows]
```

`run_manifest.score_distribution` is built from the **shadow v2** score. The score actually
published, ranked, and shown to users is the champion `row["score"]`. They are different numbers
from different models:

| | min | max | mean |
|---|---:|---:|---:|
| Manifest reports | 60.0 | 77.8 | 68.85 |
| Champion (published) | 71.4 | 83.4 | 75.05 |

Spearman between the two rankings on the published rows is **+0.451** — they disagree about roughly
half the ordering, so this is not a cosmetic offset.

Two consequences. First, the release manifest is the artifact that is supposed to tie an output to
the model that produced it; right now it describes a model that is not in production. Second, and
worse: `docs/BASELINE-2026-08-06.md` diagnosed the rank-churn root cause ("count 40, min 51.5, max
57.6 … a 6.1-point spread") **from this field**. That headline diagnosis was made on the shadow
model's numbers, not the champion's. The remediation that followed appears to have worked anyway,
but the reasoning that justified it was reading the wrong column.

### 3.2 The news sentiment component is inert

Of 374 scored names, **373 have `news_sentiment` = 50.0** (neutral). Exactly one has a real value.
The component is weighted 4% and contributes essentially nothing to the ranking (Spearman +0.078,
two distinct values in the whole cross-section). This follows directly from Marketaux being scoped
to the five-symbol Alpha enrichment shortlist. It is not harmful, but 4% of the model is currently
decorative, and the README describes it as though it were operating.

### 3.3 Two fundamental categories are absent for most of the universe

`capital_allocation` and `accounting_quality` are scored for **84 of 374** names. Together they are
20% of the stated fundamental weight. For the other 290 names that weight is silently redistributed
across the remaining categories by the within-category reweighting rule. The mechanism is correct —
reweighting beats imputing neutral — but it means most of the universe is being ranked by a
materially different model than the one documented, and the Piotroski F-score, which the README
calls the lead accounting-quality metric, is absent for 78% of names.

### 3.4 Turnover is inconsistent with the model's own thesis

The backtest rebalances **64.9% of the portfolio every month** (median 65.3%, one month at 100%).
Month-over-month name retention is **36%**; 397 unique tickers passed through a 20-name portfolio in
five years.

A model that is 78% fundamentals — inputs that update once a quarter and lag the fiscal period by
one to three months — should not be replacing two-thirds of its holdings monthly. Something with a
much shorter half-life is driving the ranking. The likely mechanism is the step-function band
scoring (`scorer.py:90-153`): metrics are mapped to 0–100 through discrete thresholds, so a name
sitting near a band edge flips several points on a trivial input change, and enough of those
compound into a rank change. The prior review flagged bands as discarding cross-sectional
information; this quantifies the cost.

At 10bps one-way this costs ~78bps/year, which the backtest already absorbs. The real problem is
diagnostic, not arithmetic: 65% monthly turnover means the score is not measuring what it claims to
measure.

### 3.5 Insider layer still dark

`sec_form4` reports `unavailable` — `SEC_USER_AGENT` remains unset, so 0 symbols are scored. The
insider modifier (+5/−3) is one of the better-evidenced signals in the design and it has never run
in production. This is an environment variable, not an engineering problem.

---

## 4. Validation state

Unchanged and still the binding constraint:

- IC harness: **0 of 24** required prospective periods.
- Shadow store: **5 daily observations** across 4 strategies.
- Point-in-time store: 2 days of JSONL.
- No promotion has occurred; five challengers are published in `score_variants` and none has been
  evaluated against the gates in `docs/RESEARCH-CONTRACT.md`.
- `pipeline/costs.py` exists and is tested but is **not wired into** `ic_harness.py`, which still
  applies a flat 10bps.

So the honest position is: the only forward-looking evidence about this model is a 5-year
survivorship-biased backtest that says it loses to SPY, and a prospective harness that will not
produce its first statistic for roughly two years at the current accumulation rate.

---

## 5. Scorecard

| Dimension | Score | Basis |
|---|---:|---|
| Evidence of edge | **3.0** | Underperforms SPY on return, vol, drawdown, and Sharpe. Alpha t-stat 0.44. No prospective validation exists. |
| Model design & economic reasoning | **7.5** | Weight choices are defensible and evidence-linked; 12-1 momentum, opportunistic-vs-routine insider split, sector-fitted Altman Z, peer-group ETF percentiles, and refusing to fold themes into the score are all correct calls. Realized weights match stated weights. |
| Validation methodology | **6.5** | Rank IC / ICIR / quantile monotonicity / deflated Sharpe / PBO is the right framework, and the promotion gate is real. It has produced zero results and the cost model is not connected to it. |
| Data integrity & coverage | **6.0** | Enrichment collapse fixed, coverage 0.69–0.98. But two fundamental categories are missing for 78% of names, news sentiment is inert, and the insider layer is dark. |
| Turnover & cost realism | **4.0** | 65% monthly turnover from a quarterly-updating signal. Cost model is a labeled proxy and isn't wired to the harness. |
| Release integrity & observability | **4.5** | Manifest describes the wrong model, and that error propagated into a root-cause document. Otherwise the manifest/hash/lineage design is sound. |
| Documentation honesty | **9.0** | States its own weaknesses more accurately than most institutional model documentation. |
| **Overall** | **5.0** | Weighted toward evidence of edge, because that is what a trading algorithm is for. |

Against the last review this is roughly flat overall — the engineering categories rose, and a new
category that had never been scored came in low enough to offset them. The system moved from
"blocked by a broken payload" to "shipping cleanly, and now we can see it doesn't beat the index."
That is progress: you cannot find this problem until the plumbing works.

---

## 6. What would move the rating

Ordered by how much each would change the number.

1. **Re-run the monthly backtest against a size- and sector-matched benchmark, not SPY.** The
   strategy runs beta 0.70 with a small/mid tilt. Comparing it to SPY measures the tilt, not the
   score. If it beats an equal-weight or IWM-blend benchmark, the picture changes completely, and
   the 52-week file already hints that it will not. This is the highest-value single experiment
   available and it needs no new data.
2. **Fix `observability.py:30`** to read the champion score, and re-check any conclusion previously
   drawn from `score_distribution`.
3. **Diagnose the 65% monthly turnover.** Attribute rank changes to band crossings vs. genuine
   input changes. If bands are the cause, the `cross_sectional_normalization` challenger already in
   the repo is the fix and can be evaluated directly.
4. **Set `SEC_USER_AGENT`.** One variable turns on the insider layer.
5. **Backfill `capital_allocation` and `accounting_quality`,** or state the effective per-name
   weights in the published output so the reweighting is visible rather than silent.
6. **Wire `costs.py` into `ic_harness.py`** so net-of-cost results reflect a 65%-turnover portfolio
   in thin names rather than a flat 10bps.
7. **Either wire real news coverage or drop the 4% component** and redistribute it. It is currently
   a constant.

---

## 7. Limits of this rating

Stated so they are not left implicit, in the style the repo already uses:

- **I did not run either test suite.** `pytest` could not be installed in this sandbox and
  `node_modules` is absent. Every test-count claim in the repo's docs is unverified by me.
- **The driver-influence figures are one cross-section, one date.** They are tie-aware Spearman
  correlations across the 374-name screen universe from the 2026-08-06T22:50 refresh. They describe
  what separates names in that snapshot, not average behavior over time.
- **The alpha t-statistic uses daily returns over five years** with no Newey-West adjustment and a
  zero risk-free rate, matching the backtest's own convention. It is a rough significance check,
  not a formal test — but 0.44 is far enough from 2.0 that a more careful treatment would not
  change the conclusion.
- **I did not run the live pipeline.** All findings come from the committed artifacts and source,
  same constraint `docs/LIMITATIONS.md` records.
- **This is a research-quality assessment, not investment advice**, and nothing here says the
  underlying businesses are badly chosen — only that the ranking has not been shown to predict
  returns.
