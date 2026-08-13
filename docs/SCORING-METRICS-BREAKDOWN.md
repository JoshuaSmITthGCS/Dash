# Scoring Metrics Breakdown — Every Score in ValueSignal, Explained and Distinguished

This document exists because the app computes **nine functionally different scores** under
names that sound similar (`score`, `momentum_12_1`, "Momentum" screen, `structural`,
`tactical`, `quality_score`...). None of them are interchangeable, none of them share a
formula, and several are deliberately kept from ever touching each other. This is the single
place that says, precisely, what each one is, how it is computed, what feeds it, and how it
differs from the others — with exact weights and file:line references into `pipeline/`.

Companion documents: `docs/APP-BREAKDOWN-AUDIT.md` (whole product), `docs/MOBILE-BREAKDOWN-AUDIT.md`,
`docs/DESKTOP-BREAKDOWN-AUDIT.md`. The in-app page closest to this one is `/methodology`
(`src/pages/Methodology.jsx`), which explains the champion research score to end users in
plain language; this document goes deeper and covers every score, not just that one.

## Quick reference — which score is which

| Score | Universe | Computed in | Published to | Answers |
|---|---|---|---|---|
| **Research score** (`score`) | Individual stocks | `pipeline/advisor_engine.py::build_research` | `public/data/advisor.json`, `/research`, stock detail sheets | "How strong is the evidence for this company overall?" |
| **Structural / Timeliness** (`analysis_v2`) | Individual stocks | `pipeline/scoring_v2.py::build_v2_analysis` | `advisor.json.research[].analysis_v2` (shadow field) | "Is this a durable business, and are near-term estimates moving in its favor?" — kept deliberately separate from the research score |
| **Momentum screen score** | Cross-sectional universe | `pipeline/research_screens_v2.py::momentum_scores` | `public/data/screens/momentum.json`, `/screens/momentum` | "Which names have the strongest price-momentum evidence *relative to the current universe*, this month?" |
| **Tactical score** | Cross-sectional universe | `pipeline/research_screens_v2.py::tactical_score` | `public/data/screens/earnings-timeliness.json`, `/screens/earnings` | "Is the 1–3 month earnings-revision and surprise picture improving?" |
| **Quality-value screen** | Cross-sectional universe | `pipeline/research_screens_v2.py::robust_value_score` + `classify_quality_value` | `public/data/screens/quality-value.json`, `/screens/quality-value` | "Is this cheap *against its own history*, and is the business still good?" |
| **Political / congressional score** | Individual stocks | `pipeline/scorer.py::run` (`score_track_record`, `score_committee`, ...) | `public/data/signals.json`, `/screens/politics` | "How strong is the congressional-trading signal on this ticker?" — carries **no** fundamental or price input |
| **ETF composite score** | Funds | `pipeline/fetch_etfs.py::score_etf_universe` | `public/data/etfs.json`, ETF comparison views | "How does this fund rank against funds doing the same job?" — completely separate model from the stock score |
| **Watchlist quality score** | Watchlist entries | `pipeline/config/settings.json::watchlist_setup` (consumed by watchlist scoring code) | `/watchlist` | "Given thesis, research score, confidence, and guidance, is this name still workable?" |
| **Confidence** (`confidence`, 0–1) | Individual stocks | `blend_research_components` / `shrink_research_components` in `advisor_engine.py` | Every research row | Not a score — a *reliability multiplier* on the research score, driven by data coverage |

The single most common confusion this document exists to resolve: **`momentum_12_1` is a
12-month, skip-month price-return number that feeds two completely different places** — as an
~5.4%-of-total sub-signal inside the research score's market-behavior component, and as the
single largest input (40%) to the entirely separate, cross-sectional Momentum screen score.
Same underlying arithmetic (`pipeline/risk_metrics.py::momentum_12_1`), two unrelated scores
built on top of it. See §2 and §4 below.

---

## 1. The research score (the number shown everywhere as "the score")

Entry point: `build_research()`, `pipeline/advisor_engine.py:818-861`.

The research score blends three independently-scored components, weighted, confidence-adjusted,
then nudged by bounded modifiers:

```
raw   = Σ(component_i · weight_i) / Σ(weight_i)     — only over components that resolved
base  = raw · (0.8 + 0.2 · confidence)               — confidence pulls toward 80% of raw, never below it
score = clamp(base + modifier_points, 0, 100)
```

(`blend_research_components`, `advisor_engine.py:570-596`)

### 1.1 Component weights (`ranking_weights` in `settings.json`)

| Component | Weight | Why |
|---|---|---|
| Fundamentals | **78%** | Dominates by design — see §1.2 |
| Market behavior | **18%** | Real risk-adjusted math, not invented constants — see §1.3 |
| News sentiment | **4%** | A tilt, not a pillar — headline alpha decays within days (Tetlock 2007) — see §1.4 |

Confidence itself is a weighted blend of each component's own *coverage* (how much of that
component's underlying data actually resolved), not of the scores:

```
confidence = 0.65 · fundamentals_coverage + 0.25 · market_behavior_coverage + 0.10 · news_sentiment_coverage
```

### 1.2 Fundamentals component — `pipeline/scorer.py::valuation_score` (78% of the score)

Two interchangeable engines produce the same six category scores from different normalization
strategies, selected by `settings.json::normalization_mode` (currently `"bands"`, champion):

- **Band mode** (`_band_valuation_score`, `scorer.py:504-588`) — every raw metric (P/E, ROIC,
  debt/EBITDA, etc.) is mapped to 0–100 through fixed, hand-set bands (`band_score`,
  `higher_is_better_score`, `lower_is_better_score`, `range_score`, `multiple_score`,
  `scorer.py:90-155`). Bands live in `settings.json::fundamentals`.
- **Cross-sectional mode** (`_cross_sectional_valuation_score`, `scorer.py:591-636`, challenger
  only, `challengers.cross_sectional_normalization.enabled`) — every metric is instead scored as
  a winsorized percentile against the *current refresh's own universe* (sector distribution if
  ≥8 peers, else the full universe), via `CrossSectionalNormalizer` (`scorer.py:296-450`).
  Published beside the champion for comparison, never swapped in silently.

Both modes score the same six weighted categories (`settings.json::fundamentals.category_weights`):

| Category | Weight | Leading metrics (weight within category) |
|---|---|---|
| Valuation | 28% | EV/EBITDA (27%), EV/FCF (18%), Forward P/E (15%), EV/EBIT (12%), PEG (9%), Sales multiple (9%), P/B (5%), P/tangible-B (5%) |
| Profitability + cash | 26% | ROIC (26%), gross profits/assets (22%), FCF yield (16%), cash conversion (16%), ROE (10%), profit margin (10%) |
| Financial health | 15% | Interest coverage (30%), net debt/EBITDA (24%), Altman Z (18%), debt/equity (18%), current ratio (10%) |
| Growth | 11% | Revenue growth (26%), FCF growth 3y (22%), earnings growth (20%), operating margin trend (16%), earnings surprise (16%) |
| Capital allocation | 10% | Net buyback yield (34%), stock comp/revenue (28%), asset growth (22%), capex/depreciation (16%) |
| Accounting quality | 10% | Piotroski F-score (45%), accruals ratio (22%), DSO trend (17%), inventory-days trend (16%) |

Design notes baked into the code and worth stating explicitly:
- EV/EBITDA leads valuation (not P/E) because enterprise multiples are capital-structure neutral
  — a levered company can't look cheap by borrowing.
- ROIC leads profitability (not ROE) for the same reason — leverage inflates ROE but can't
  inflate ROIC.
- PEG carries only 9% — it ignores time value of money and risk, and its predictive record is
  thin, so it's a sanity check, not the anchor.
- Piotroski F leads accounting quality; the accruals-ratio anomaly has decayed in US data since
  2002, so it's a minor input now, not the bucket.
- Financial-sector names skip 12 metrics that don't apply to bank/insurer balance sheets
  (`FINANCIAL_EXEMPT`, `scorer.py:167-170`) — those leave the coverage denominator entirely
  rather than counting as missing evidence.
- Coverage-weighted confidence: `weighted_coverage()` (`scorer.py:485-501`) computes the
  fraction of total metric *weight* actually answered — a missing headline metric costs far
  more confidence than a missing minor one — and the final fundamentals score is
  `raw · (0.65 + 0.35 · coverage)` (`scorer.py:583-584`).
- ETFs are **never** scored here — `valuation_score` returns `None, {}` for `is_etf` snapshots
  (`scorer.py:510`). See §5 for the completely separate ETF model.

### 1.3 Market behavior component — `technical_factors()` (18% of the score)

`pipeline/advisor_engine.py:83-192`. This is the component that contains a `momentum_12_1`
sub-signal — **not** the standalone Momentum screen (§4). Seven weighted sub-signals
(`TECHNICAL_WEIGHTS`, `advisor_engine.py:41-47`):

| Sub-signal | Weight (within market behavior) | Effective share of total score | What it is |
|---|---|---|---|
| `momentum_12_1` | 30% | ≈5.4% | 12-month return skipping the most recent month (`risk_metrics.py::momentum_12_1`), mapped `50 + pct·1.2` |
| `risk_adjusted` | 26% | ≈4.7% | 65% Sortino + 35% Sharpe on the stock's own daily returns, mapped through `ratio_to_score` |
| `relative_strength` | 16% | ≈2.9% | 20-day return vs. SPY, mapped `50 + relative·3` |
| `drawdown_resilience` | 14% | ≈2.5% | Score of the deeper of a 60-day or 252-day max drawdown |
| `volume_confirmation` | 8% | ≈1.4% | Ratio of up-day to down-day volume over 60 sessions |
| `low_beta` | 6% | ≈1.1% | Distance from an ideal beta of 0.85 (betting-against-beta, Frazzini-Pedersen 2014) |
| `technical_extended` | 6% | ≈1.1% | Four more indicators, see below |

`technical_extended` (`pipeline/technical_indicators.py`) is itself an equally-weighted blend of
one indicator from four distinct economic families chosen specifically to *not* duplicate the
six signals above: `moving_average_slope` (trend), `relative_strength_index` (oscillator),
`bollinger_percent_b` (volatility), `on_balance_volume_slope` (volume). The module docstring is
explicit that most published "technical indicator zoos" are data-snooping — this stays at four
signals from four families, deliberately capped at 6% of an 18% component (≈1% of the total
score).

**Why 12-1, not raw 12-month:** Jegadeesh & Titman (1993) document a well-established
short-term reversal in the most recent month that runs *against* momentum; including it
contaminates the signal. `momentum_12_1(closes, lookback=252, skip=21)` in
`pipeline/risk_metrics.py:36-49` implements the skip explicitly, and a fallback to the 60-day
return (with reduced coverage) applies for names without a full year of history.

Two configurable treatments alter how `relative_strength` (a short-horizon signal) is folded
in (`technical_score_from_parts`, `advisor_engine.py:195-222`, selected by
`short_horizon_treatment`, currently `legacy_momentum` in production):
- `legacy_momentum` — keep it as-is (current champion).
- `neutral` — drop it and renormalize the remaining six weights to sum to 1 (challenger).
- `reversal` — invert it (`100 - score`) at a reduced configured weight (challenger).

### 1.4 News sentiment component (4% of the score)

`sentiment_score()`, `advisor_engine.py:225-237`, delegates to
`pipeline/news_intelligence.py::weighted_sentiment`. Aggregates a rolling 7-day window
(`news_intelligence.window_days`) rather than a single day's headlines, with exponential
recency decay (3-day half-life), source-quality weighting (regulatory filings and wire
services weighted above aggregator-syndicated copies), title-similarity deduplication (0.82
threshold), and a minimum entity-confidence floor (0.25) so low-confidence ticker matches are
discarded rather than scored. Deliberately capped at 4% because Tetlock (2007) finds media
pessimism's price effect "followed by a reversion to fundamentals" within days — a headline
snapshot is a tilt, not a tenth of the thesis it was cut from (10% → 4%; the freed 6 points
moved to market behavior).

### 1.5 Modifiers — bounded, applied *after* the blend

`apply_modifiers()`, `advisor_engine.py:373-396`. Each modifier is independently capped, then
the **combined** total is clamped to ±15 points before being added to `base`:

| Modifier | Cap | Trigger |
|---|---|---|
| Sector valuation percentile | ±3.0 | Cheap/rich vs. sector peers, not absolute multiples |
| Short interest | −6.0 (severe), −3.0 (warning), +1.5 add-on for high days-to-cover | ≥15%/≥8% of float short (Boehmer, Jones & Zhang 2008: heavily shorted names underperform ~1.16% risk-adjusted over 20 sessions) |
| Insider activity | +5.0 / −3.0 | SEC Form 4 opportunistic-cluster buys/sells (Cohen-Malloy-Pomorski routine/opportunistic split); routine scheduled trades score exactly zero |
| Liquidity | −3.0 (illiquid <$5M/day), −1.5 (thin <$25M/day) | Cost of exiting a position, not a fundamental |
| Analyst expectations | ±3.0 | Only applied with ≥3 covering analysts |
| Macro regime | ±3.0 | FRED rates/inflation/labor/yield-curve, weighted by *sector sensitivity* (e.g., Real Estate weights `rates` at 0.55; Financials weight `yield_curve` at 0.55) |

A **challenger** variant (`apply_challenger_modifiers`, `advisor_engine.py:399-487`) allocates
each modifier as a *fraction* of one configurable combined cap (default 20 points:
`challengers.signal_corrections.modifier_cap`) instead of stacking six independent caps, so
adjusting one modifier's share never silently changes another's implicit scale.

### 1.6 Stance, guidance, and thresholds

`stance_for()` (`advisor_engine.py:558-567`): below 0.45 confidence → `INSUFFICIENT DATA`,
regardless of score; else ATTRACTIVE (≥75) / PROMISING (≥60) / MIXED (≥45) / CAUTION.

`action_for()` (`advisor_engine.py:492-555`) is the production recommendation policy: it
requires **agreement across at least two independent factor groups** (fundamentals, market
behavior, positioning/sentiment) before recommending SELL or TRIM — a single bad headline or
one weak quarter is never enough on its own. A shadow **v2 policy**
(`pipeline/recommendation_policy_v2.py`, surfaced as `recommendation_v2`, does not control
production actions) separates company thesis from 1–3 month timeliness, portfolio fit, and
user-specific position rules, and shrinks company scores toward neutral under low confidence.

---

## 2. Structural / Timeliness score — the "v2" shadow model

`pipeline/scoring_v2.py::build_v2_analysis` (lines 65-242), surfaced as `analysis_v2` on every
research row but **not** blended into the production research score — a shadow model pending
its own prospective validation (`MODEL_VERSION = "structural-timeliness-2.0.0"`).

This is two separate scores, deliberately kept apart because they answer different-horizon
questions:

- **Structural** — "is this a durable, high-quality business?" Reuses the same six fundamental
  categories and metric weights as §1.2, but every metric first passes through a canonical
  applicability/provenance layer (`canonical_metrics.py`): a metric is `applied`, `suppressed`
  (doesn't apply to this business profile — e.g., PEG without a declared forward-growth unit),
  `unavailable` (applicable but missing), or flagged for `stale_observation` /
  `provider_conflict`. Confidence is `coverage · provenance_reliability − stale_penalty − conflict_penalty`,
  and the reported score is `effective = 50 + confidence · (raw − 50)` — i.e., low-confidence
  reads are shrunk toward neutral rather than reported at face value.
- **Timeliness** — "are near-term estimates moving in this company's favor right now?" A
  narrow, two-input blend: 70% forward EPS-revision (30-day), 30% earnings surprise, each
  mapped `50 + value·multiplier`. Classified `improving` (≥60) / `stable` / `weakening` (<45),
  or `insufficient_evidence` below 0.40 confidence.

Structural and timeliness are never summed into one number in this model — that's the entire
point of the split (see `tactical_score` in §4, which explicitly cross-tabulates a structural
score against a *different* tactical score to produce a 2×2 classification).

---

## 3. Political / congressional trade score — entirely separate from the research score

`pipeline/scorer.py::run()` (lines 678-790), six independent weighted factors
(`signal_weights` in `settings.json`): track record (25), committee relevance (20), cluster
detection (20), trade size (15), direction/recency (10), policy catalyst (10) — summed, capped
per-factor, unweighted by any subsequent blend. This score (`political_score`, `/screens/politics`)
carries **zero** fundamental or price input — it is purely a function of who in Congress traded
what, in what committee, in what size, how recently, and whether other members clustered on the
same name within 30 days. It is published alongside `valuation_score` (the same fundamentals
score as §1.2, under its legacy field name) in `signals.json` for context, but the two numbers
are never combined into one.

---

## 4. Momentum screen score — NOT the same thing as `momentum_12_1`

`pipeline/research_screens_v2.py::momentum_scores` (lines 169-206), published to
`public/data/screens/momentum.json`, rendered at `/screens/momentum`
(`pipeline/build_momentum_screen.py` is the runner).

This is the score most likely to be confused with the `momentum_12_1` sub-signal inside the
research score (§1.3). They share underlying return math but are structurally unrelated:

| | Research score's `momentum_12_1` (§1.3) | Standalone Momentum screen (this section) |
|---|---|---|
| Scope | One sub-signal, 30% of an 18%-weight component (~5.4% of one stock's total score) | The entire screen's ranking signal |
| Method | Absolute score: `50 + pct_return · 1.2`, no peer comparison | **Cross-sectional z-score**: every factor is winsorized then standardized (mean 0, sd 1) *against the current universe* before weighting |
| Inputs | One number (12-1 return) | Five weighted factors, `MOMENTUM_WEIGHTS`: `momentum_12_1` (40%), `momentum_12_7` (20%), `momentum_6_1` (15%), `high_52w_proximity` (15%), `industry_relative_momentum` (10%) |
| Eligibility | None — every scored stock gets a market-behavior score | Hard gates: minimum price $5, minimum market cap $300M, minimum 60-day median dollar volume $2M, minimum 253 history sessions, binary-event and stale-price exclusions (`momentum_scores`, `research_screens_v2.py:181-186`) |
| Correlation control | None | `momentum_correlation_diagnostics` computes average pairwise correlation across the five factors and applies a family contribution cap (default 90%, configurable) if they're running too co-linear — prevents five near-duplicate momentum flavors from posing as five independent facts |
| Membership | N/A (not a screen) | Percentile-ranked, with **entry/exit hysteresis** (default enter ≥90th percentile, exit only below 75th) so names don't flicker in and out on noise |
| Point-in-time integrity | N/A | `month_end_prices()` and `momentum_boundary_diagnostics()` enforce that formation-month data never leaks into the signal — auditable start/end month-end boundaries are published per name |

Both computations pull from the same `momentum_12_1` arithmetic (`risk_metrics.py:36-49` for
the research-score version; the screen computes its own month-end variant in
`month_end_prices`/`_return`, `research_screens_v2.py:20-54`, deliberately using exact
calendar-month-end prices rather than trailing-N-session closes, because a screen's rebalance
logic needs month-boundary precision that a daily research refresh doesn't). **The two numbers
will differ for the same stock on the same day, by design.**

---

## 5. Tactical score — the earnings-timeliness screen

`pipeline/research_screens_v2.py::tactical_score` (lines 209-221), published at
`/screens/earnings` and cross-tabulated against the structural score (§2) at `/screens/matrix`.
Fifteen weighted revision/surprise factors (`TACTICAL_WEIGHTS`), led by revision magnitude
(15%), revision agreement (12%), industry revision breadth (10%), EPS surprise (8%), and a
small residual carry-over of `momentum_12_1` (8%) and `momentum_6_1` (4%) — price momentum
appears here too, but at a fraction of its Momentum-screen weight and blended with revision
data the Momentum screen never sees. The resulting 2×2 classification
(`high-conviction candidate` / `quality company, wait` / `tactical-only candidate` / `avoid`)
requires **both** a structural score ≥65 *and* a tactical score ≥60 to earn the top label —
neither score alone is suficient.

---

## 6. Quality-value screen score

`pipeline/research_screens_v2.py::robust_value_score` (lines 231-242) +
`classify_quality_value` (lines 245-258), published at `/screens/quality-value`. Scores
cheapness as a **weighted median of each metric's own-history percentile** (`historical_percentile`,
lines 224-228) rather than a cross-sectional peer comparison — "cheap for this specific company,
right now, versus its own multi-year range" is a different claim than "cheap versus the sector"
(§1.2's sector-percentile modifier) or "cheap versus the universe" (§1.2's cross-sectional
challenger mode). The final classification requires cheapness (≥70th own-history percentile),
quality (≥65 structural-style score), and screens out severe forward-estimate deterioration or
distress before calling anything "actionable value" — a name can be cheap and high-quality and
still get flagged `cheap but deteriorating` if forward revisions have turned sharply negative.

---

## 7. ETF composite score — a fully separate model from the stock score

`pipeline/fetch_etfs.py::score_etf_universe` (line 414 onward), published to
`public/data/etfs.json`. Stocks are never scored by this model and funds are never scored by
§1's model — `valuation_score()` explicitly refuses ETF snapshots (§1.2). Percentiles are
computed **within each fund's own peer group** (`peer_groups` in `pipeline/config/universe.json`
— e.g., broad-market, growth, value, and small-cap funds all share the `equity_broad` peer
group; sector, thematic, bond, commodity, and crypto funds get their own), because ranking a
bond fund's Sharpe ratio against an equity fund's is an artifact of the batch, not a real
comparison.

Five weighted buckets (`etf_scoring.weights`, `pipeline/config/universe.json`):

| Bucket | Weight | Inputs |
|---|---|---|
| Performance | 28% | Trailing returns across every published window, percentile-ranked within peer group |
| Risk | 27% | Sortino, Sharpe, max drawdown (all via the *same* `risk_metrics.py` functions the stock model uses — a Sharpe of 1.2 means the same thing on either screen), and beta (low beta scores well, same betting-against-beta logic as §1.3) |
19| Cost | 17% | Expense ratio, 1-year tracking difference (signed — ahead of the index is genuinely better than behind it), absolute premium/discount to NAV |
| Liquidity | 16% | Average dollar volume, bid-ask spread |
| Quality | 12% | `structural_quality()` — issuer reputation adjusted for AUM, leverage/inverse structure (−25), synthetic replication (−10), and aggressive securities lending (−5); a strong brand doesn't offset real structural risk |

`percentile_scores()` (`fetch_etfs.py:245-270`) is careful to give ties a *shared* percentile
rank and to leave a fund with a missing metric at a neutral 50 rather than punishing it for a
gap in free data.

---

## 8. Watchlist quality score

`pipeline/config/settings.json::watchlist_setup`. A weighted blend of four continuous
subscores — thesis (30%), research score (30%, reusing §1's number as one input among four,
not a rename of it), confidence (20%), and published guidance (20%, HOLD=1.0 down to SELL=0.0)
— using smooth sigmoid transitions around configured centers rather than hard cutoffs, so a
name doesn't flip labels on a one-point wobble. A hard confidence floor (0.45) or a published
SELL guidance can block position sizing regardless of how the blended quality number reads;
everything else is soft.

---

## 9. Confidence — not a score, a reliability multiplier

Every research-score component reports its own *coverage* (fraction of expected data that
actually resolved), and `confidence` is a weighted blend of those coverages (§1, formula
repeated for emphasis): `0.65·fundamentals + 0.25·market_behavior + 0.10·news_sentiment`.
Confidence never adds evidence — it only ever pulls the blended score toward (never past) 80%
of its raw value when data is thin (`base = raw · (0.8 + 0.2·confidence)`), and gates the
`INSUFFICIENT DATA` stance below 0.45. `pipeline/confidence.py` further decomposes this into
named sub-components (completeness, freshness, source_reliability, peer_sample, model_agreement)
for the "why is this confidence low" explainability surface — see `docs/MODEL-CARD.md` for the
full breakdown and its current validation state.

---

## Where every score is displayed in the app

| Score | Route(s) | Component(s) |
|---|---|---|
| Research score | `/`, `/research`, `/search`, stock detail sheets | `Dashboard.jsx`, `Picks.jsx`, `ScoreExplainability.jsx` (waterfall attribution via `pipeline/explainability.py`), `ScoreBandView.jsx`, `ResearchRadarChart.jsx` |
| Structural / Timeliness (v2) | `/screens/validation` (shadow diagnostics) | `LiveValidation.jsx` (`TickerValidation`) |
| Momentum screen | `/screens/momentum` | `ResearchScreen.jsx` |
| Tactical / structural-tactical matrix | `/screens/earnings`, `/screens/matrix` | `ResearchScreen.jsx` |
| Quality-value screen | `/screens/quality-value` | `ResearchScreen.jsx` |
| Political score | `/screens/politics` | `CongressTrades.jsx` |
| ETF composite | ETF comparison views inside `/research`, `/portfolio` | `Picks.jsx`, ETF comparison components |
| Watchlist quality | `/watchlist` | `Watchlist.jsx` |
| Methodology (plain-language, research score only) | `/methodology` | `Methodology.jsx` (reads live weights from `advisor.json.methodology`, cannot drift from the config that produced them) |

General research only. No score on this page is a probability, a price target, or investment
advice — see `docs/MODEL-CARD.md` and `docs/LIMITATIONS.md`.
