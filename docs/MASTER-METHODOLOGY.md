# Master Methodology — Data Sources, Metrics, Weights, and Scoring

Single consolidated reference for every score the app computes, every metric that feeds it,
every data provider behind those metrics, and the exact weight each piece carries. This
document merges and supersedes-for-reading-purposes (but does not replace as source of truth)
`docs/SCORING-METRICS-BREAKDOWN.md`, `docs/DATA-LINEAGE.md`, `docs/MODEL-CARD.md`, and
`docs/FEATURE-REGISTRY.md`. Every number below is read from the live config
(`pipeline/config/settings.json`, `pipeline/config/metric_registry.json`,
`pipeline/config/universe.json`) or the scoring code itself
(`pipeline/advisor_engine.py`, `pipeline/scorer.py`, `pipeline/fundamentals_extended.py`,
`pipeline/research_screens_v2.py`, `pipeline/fetch_etfs.py`), not restated from memory — file:line
references are given throughout so any number here can be re-verified against the code that
produces it.

No score in this app is a probability, a price target, or investment advice. See "Validation
state" (§9) before treating any number here as predictive.

---

## Table of contents

1. [Data sources](#1-data-sources)
2. [Point-in-time data stores](#2-point-in-time-data-stores)
3. [The research score — full weight tree](#3-the-research-score--full-weight-tree)
4. [Every fundamentals metric — formula, direction, weight](#4-every-fundamentals-metric--formula-direction-weight)
5. [Market behavior (technical) component](#5-market-behavior-technical-component)
6. [News sentiment component](#6-news-sentiment-component)
7. [Confidence — the reliability multiplier](#7-confidence--the-reliability-multiplier)
8. [Modifiers — bounded post-blend adjustments](#8-modifiers--bounded-post-blend-adjustments)
9. [Validation state — what has and hasn't been proven](#9-validation-state--what-has-and-hasnt-been-proven)
10. [Every other score in the app](#10-every-other-score-in-the-app)
    - 10.1 [Structural / Timeliness (v2 shadow model)](#101-structural--timeliness-v2-shadow-model)
    - 10.2 [Political / congressional trade score](#102-political--congressional-trade-score)
    - 10.3 [Momentum screen score](#103-momentum-screen-score)
    - 10.4 [Tactical (earnings-timeliness) screen score](#104-tactical-earnings-timeliness-screen-score)
    - 10.5 [Quality-value screen score](#105-quality-value-screen-score)
    - 10.6 [ETF composite score](#106-etf-composite-score)
    - 10.7 [Swing-horizon composite (2 trading days – 8 weeks)](#107-swing-horizon-composite-2-trading-days--8-weeks)
    - 10.8 [Watchlist quality score](#108-watchlist-quality-score)
11. [MarketPulse — the macro backdrop](#11-marketpulse--the-macro-backdrop)
12. [Stance, guidance, and recommendation policy](#12-stance-guidance-and-recommendation-policy)
13. [Where every score is displayed in the app](#13-where-every-score-is-displayed-in-the-app)
14. [Research report screens (`/screens/*`)](#14-research-report-screens-screens)
15. [Options screens — ranking weights per strategy](#15-options-screens--ranking-weights-per-strategy)
16. [Portfolio, planning, and finances screens](#16-portfolio-planning-and-finances-screens)
17. [Remaining routes](#17-remaining-routes)

---

## 1. Data sources

| Provider | What it supplies | Key required | Status / cadence |
|---|---|---|---|
| **Yahoo Finance** (`yfinance`) | Price/quote history, financial statements, analyst estimate revisions (EPS revision counts, EPS trend, upgrade/downgrade history, price targets — `yahoo_estimates.py`), per-symbol company news (`yahoo_news.py`) | none | Primary provider for price and statements; restated only — no as-reported (as-originally-filed) history |
| **SEC EDGAR** | Form 4 insider transactions (feeds the insider-activity modifier), XBRL theme signals, canonical fundamentals fallback, and — since the Inside Information screen — DEF 14A/DEFC14A/DEFA14A proxy tracking, 8-K item-code materiality, and 10-K/10-Q/NT 10-K/NT 10-Q late-filing tracking (`build_filings_screen.py`, `edgar_filing_signals.py`), all read from the same submissions API (`data.sec.gov/submissions/CIK{cik}.json`, `sec_edgar.py:247-252`) already used for Form 4 | `SEC_USER_AGENT` header (SEC fair-access policy) | Free; used as a `preferred_providers` source for statement metrics (`sec_xbrl`, see `metric_registry.json`), as the insider-trading feed, and (every 3 days) as the filings tracker. A full-text-search client (`efts.sec.gov`) and XBRL `frames`/`companyconcept` endpoints also exist in `sec_edgar.py` for theme work but are not part of the filings tracker |
| **Alpha Vantage** | Company overview, earnings, forward estimates, macro | `ALPHA_VANTAGE_API_KEY` | Max 5 symbols per refresh (quota-limited) |
| **Marketaux** | Entity-level news sentiment | `MARKETAUX_API_TOKEN` | Optional — feeds the 4%-weight news sentiment component (§6) |
| **FRED** (Federal Reserve Economic Data) | Macro regime: rates, inflation, labor, yield curve (6 series feed the modifier), plus VIX-derived volatility (7th series, published informationally, not yet in the modifier) | `FRED_API_KEY` | Optional — feeds the MarketPulse backdrop (§11) and the macro-regime modifier (§8) |
| **Marketstack** (apilayer) | Premarket/intraday and end-of-day price bars for the top-100 published tickers; re-sorts the Stocks (movers) and Reversal screens from accumulated closes (`marketstack.py`, `collect_marketstack.py`, `resort_marketstack_screens.py`) | `MARKETSTACK_API_KEY` | Optional — two batched runs/day on a schedule (`.github/workflows/marketstack-premarket.yml`); falls back from intraday to `eod_latest` on plan restriction; the Reversal screen reports "accumulating" until 60 sessions are collected |
| **Financial Modeling Prep** | Congressional STOCK Act disclosures (Senate/House "latest" endpoints), "since purchase" price history on the Congress trades screen | Plan covering Congressional endpoints (HTTP 402 without it) | Weekly; the screen still builds without this key via the keyless Senate eFD and House/Senate-dataset fallbacks below |
| **Senate eFD** | Senate STOCK Act disclosures, direct from the Senate's own system | none (keyless) | Weekly |
| **House/Senate stock-watcher datasets** | Third-party mirrors of congressional disclosures. The House default now points to a live, actively-maintained mirror (`kadoa-org/congress-trading-monitor`); the Senate default mirror (a stock-watcher S3 bucket) is withdrawn (HTTP 403), which is immaterial since Senate eFD already covers that side directly. Both overridable via `CONGRESS_HOUSE_DATASET_URL` / `CONGRESS_SENATE_DATASET_URL` | none | Weekly |
| **OpenFIGI** | CUSIP → ticker mapping for 13F institutional holdings | `OPENFIGI_API_KEY` (optional; without it, 10 CUSIPs per request instead of 100) | Monthly |

**Provider preference order for canonical statement metrics** (`metric_registry.json`
`declaration_defaults.preferred_providers`): `sec_xbrl` → `alpha_vantage` → `yahoo`. Individual
metrics can override this — e.g., forward-looking metrics (`forward_pe`, PEG) prefer
`alpha_vantage`/`yahoo` directly since SEC filings don't carry consensus estimates.

`pipeline/providers.py`'s `REGISTRY` and `pipeline/provider_interfaces.py` are a ports/adapters
abstraction used by parts of the scoring core, not a complete provider list — `REGISTRY` names
only `yahoo`, `alpha_vantage`, `sec_edgar`, and `fake`. Marketaux, FRED, Marketstack, Financial
Modeling Prep, Senate eFD, the stock-watcher datasets, and OpenFIGI are each fetched by their own
standalone client module outside this abstraction and never appear in it; this table, not
`REGISTRY`, is the authoritative provider list.

**Availability lag:**
- Statement-derived metrics: typically 1–3 months after fiscal period end (provider-restated,
  not as-filed).
- Price/quote data: same session.
- Congressional disclosures: STOCK Act allows up to 45 days between transaction and disclosure
  — screens rank on *disclosure* date, not transaction date, for this reason
  (`docs/SCREEN-PRESETS.md`).
- 13F institutional filings: disclosed up to 45 days after quarter-end; the `institutional_13f`
  modifier (§8) treats a filing older than 135 days as fully stale and scores it zero.

**Corporate actions:** handled entirely at the provider layer via Yahoo-adjusted price series.
No independent corporate-action event log exists in this pipeline.

---

## 2. Point-in-time data stores

Three separate append-only stores, all committed to the repository (not gitignored — the
scheduled runner is ephemeral and providers only ever serve today's restated numbers, so history
only exists if every run appends to it):

1. **Raw fundamentals PIT** — `pipeline/data/pit/observations.jsonl`, `revisions.jsonl`,
   `universe.jsonl`. Every observed value, its source, and observation timestamp; a restatement
   log; a universe-membership log (survivorship defense). `as_of()` never returns a value
   observed after a given cutoff.
2. **Scored validation PIT** — `pipeline/pit_store/YYYY-MM-DD.jsonl`. One immutable row per
   (refresh, ticker): champion + challenger scores, `config_hash`, realized forward returns once
   the horizon elapses. Read by `pipeline/stability_report.py` and
   `pipeline/validation/ic_harness.py`.
3. **Shadow portfolios** — `pipeline/shadow_store/{strategy}/YYYY-MM-DD-<sha12>.json`.
   Content-addressed; refuses a duplicate snapshot for the same strategy/date.

Every observation carries `observed_at`, `observation_date`, `source`; scored rows additionally
carry `recorded_at`, `data_as_of`, `model_version`, `config_hash`, `universe_membership`,
`published_research` (bool), `quality_flags`.

---

## 3. The research score — full weight tree

Entry point: `build_research()`, `pipeline/advisor_engine.py:818-861`. This is "the score" shown
everywhere in the app (Dashboard, `/research`, stock detail sheets).

```
raw   = Σ(component_i · weight_i) / Σ(weight_i)      — only over components that resolved
base  = raw · (0.8 + 0.2 · confidence)                — confidence pulls toward 80% of raw, never below it
score = clamp(base + modifier_points, 0, 100)         — modifier_points capped to ±15 total
```
(`blend_research_components`, `advisor_engine.py:570-596`)

### Top-level component weights (`ranking_weights`, `settings.json`)

| Component | Weight | Section |
|---|---:|---|
| **Fundamentals** | **78%** | §4 |
| **Market behavior** (technical) | **18%** | §5 |
| **News sentiment** | **4%** | §6 |

### Full tree, weight compounded down to a percent of the total score

```
RESEARCH SCORE (0–100)
│
├── Fundamentals ............................. 78%
│   ├── Valuation .............................. 28% of 78%  = 21.84% of total
│   │   ├── EV/EBITDA ............ 27% of category = 5.90% of total
│   │   ├── EV/FCF ............... 18% of category = 3.93% of total
│   │   ├── Forward P/E .......... 15% of category = 3.28% of total
│   │   ├── EV/EBIT .............. 12% of category = 2.62% of total
│   │   ├── PEG ................... 9% of category = 1.97% of total
│   │   ├── Sales multiple (EV/Sales or P/S) .. 9% = 1.97% of total
│   │   ├── Price/Book ............ 5% of category = 1.09% of total
│   │   └── Price/Tangible Book ... 5% of category = 1.09% of total
│   ├── Profitability + cash ................... 26% of 78%  = 20.28% of total
│   │   ├── ROIC .................. 26% of category = 5.27% of total
│   │   ├── Gross profits/assets .. 22% of category = 4.46% of total
│   │   ├── FCF yield ............. 16% of category = 3.24% of total
│   │   ├── Cash conversion ....... 16% of category = 3.24% of total
│   │   ├── ROE .................... 10% of category = 2.03% of total
│   │   └── Profit margin .......... 10% of category = 2.03% of total
│   ├── Financial health ........................ 15% of 78%  = 11.70% of total
│   │   ├── Interest coverage ..... 30% of category = 3.51% of total
│   │   ├── Net debt/EBITDA ....... 24% of category = 2.81% of total
│   │   ├── Altman Z .............. 18% of category = 2.11% of total
│   │   ├── Debt/Equity ........... 18% of category = 2.11% of total
│   │   └── Current ratio ......... 10% of category = 1.17% of total
│   ├── Growth ................................... 11% of 78%  =  8.58% of total
│   │   ├── Revenue growth ........ 26% of category = 2.23% of total
│   │   ├── FCF growth (3y CAGR) .. 22% of category = 1.89% of total
│   │   ├── Earnings growth ....... 20% of category = 1.72% of total
│   │   ├── Operating margin trend  16% of category = 1.37% of total
│   │   └── Earnings surprise ..... 16% of category = 1.37% of total
│   ├── Capital allocation ....................... 10% of 78%  =  7.80% of total
│   │   ├── Net buyback yield ..... 34% of category = 2.65% of total
│   │   ├── Stock comp/revenue .... 28% of category = 2.18% of total
│   │   ├── Asset growth .......... 22% of category = 1.72% of total
│   │   └── Capex/depreciation .... 16% of category = 1.25% of total
│   └── Accounting quality ....................... 10% of 78%  =  7.80% of total
│       ├── Piotroski F-score ..... 45% of category = 3.51% of total
│       ├── Accruals ratio ........ 22% of category = 1.72% of total
│       ├── DSO trend ............. 17% of category = 1.33% of total
│       └── Inventory-days trend .. 16% of category = 1.25% of total
│
├── Market behavior (technical) .............. 18%          — see §5 for full sub-tree
│   │   (raw sub-weights sum to 1.06, not 1.00 — technical_score_from_parts() divides by the
│   │    actual sum, so effective shares below are the raw weight ÷ 1.06 × 18%, not raw × 18%)
│   ├── momentum_12_1 ............. 30% raw (28.3% normalized) = 5.09% of total
│   ├── risk_adjusted (Sortino/Sharpe) 26% raw (24.5% normalized) = 4.42% of total
│   ├── relative_strength (vs SPY)  16% raw (15.1% normalized) = 2.72% of total
│   ├── drawdown_resilience ....... 14% raw (13.2% normalized) = 2.38% of total
│   ├── volume_confirmation ........ 8% raw ( 7.5% normalized) = 1.36% of total
│   ├── low_beta .................... 6% raw ( 5.7% normalized) = 1.02% of total
│   └── technical_extended .......... 6% raw ( 5.7% normalized) = 1.02% of total (4 sub-indicators, ~0.25% each)
│
└── News sentiment ............................ 4%          — see §6
```

Then, after the blend, **bounded modifiers** (§8) nudge the result by at most ±15 points total.

---

## 4. Every fundamentals metric — formula, direction, weight

Formulas are read from `pipeline/config/metric_registry.json` (`metric_inventory` and `metrics`
blocks) where declared, and from `pipeline/fundamentals_extended.py` / `pipeline/scorer.py` where
the registry doesn't yet carry a formal declaration (noted below). "Direction" is `higher_is_better`,
`lower_is_better`, `ideal_range` (a target band, not a monotonic direction), or `range_score`
(multiple regime bands).

### Valuation (28% of fundamentals)

| Metric | Weight in category | Direction | Formula |
|---|---:|---|---|
| EV/EBITDA | 27% | lower is better | Enterprise value ÷ positive TTM EBITDA |
| EV/FCF | 18% | lower is better | Enterprise value ÷ positive TTM free cash flow |
| Forward P/E | 15% | lower is better | Price ÷ next-fiscal-year consensus diluted EPS |
| EV/EBIT | 12% | lower is better | Enterprise value ÷ TTM EBIT |
| PEG | 9% | lower is better | Forward P/E ÷ expected annual EPS growth (percentage points) |
| Sales multiple | 9% | lower is better | EV/Sales when a balance sheet is available (`scorer.py:212-223`, preferred — capital-structure neutral); falls back to Price/Sales for names without enriched balance-sheet data |
| Price/Book | 5% | lower is better | Market cap ÷ common shareholders' equity (latest filing) |
| Price/Tangible Book | 5% | lower is better | Market cap ÷ tangible common equity |

*Why EV/EBITDA leads (not P/E): enterprise multiples are capital-structure neutral — a levered
company can't look cheap by borrowing. PEG carries only 9%: it ignores time value of money and
risk and its predictive record is thin, so it's a sanity check, not the anchor.*

### Profitability + cash (26% of fundamentals)

| Metric | Weight in category | Direction | Formula |
|---|---:|---|---|
| **ROIC** | 26% | higher is better | `NOPAT ÷ average invested capital`, where `NOPAT = EBIT × (1 − effective tax rate)` and `invested capital = total debt + equity − cash` (averaged current vs. prior period) — `derive_roic`, `pipeline/fundamentals_extended.py:168-184` |
| Gross profits/assets | 22% | higher is better | Gross profit ÷ average total assets (Novy-Marx, JFE 2013) — `derive_gross_profits_to_assets`, `fundamentals_extended.py:341-357` |
| **FCF yield** | 16% | higher is better | TTM free cash flow ÷ point-in-time market cap |
| Cash conversion | 16% | higher is better | TTM free cash flow ÷ positive TTM net income — `derive_cash_conversion`, `fundamentals_extended.py:187-193` |
| ROE | 10% | higher is better | Net income available to common shareholders ÷ average common equity |
| Profit margin | 10% | higher is better | TTM net income ÷ TTM revenue |

*Why ROIC leads (not ROE): leverage inflates ROE but cannot inflate ROIC — same capital-structure-neutral
logic as EV/EBITDA above. Free cash flow itself, where not directly reported, is derived as
`operating cash flow − |capex|` (`fundamentals_extended.py:187-192`).*

### Financial health (15% of fundamentals)

| Metric | Weight in category | Direction | Formula |
|---|---:|---|---|
| Interest coverage | 30% | higher is better | Operating income ÷ interest expense (matched period) |
| Net debt/EBITDA | 24% | lower is better | (Debt − cash) ÷ positive TTM EBITDA |
| Altman Z | 18% | higher is better | Declared Altman model, matched annual inputs |
| Debt/Equity | 18% | lower is better | Interest-bearing debt ÷ common equity |
| Current ratio | 10% | higher is better | Current assets ÷ current liabilities (same filing period) |

### Growth (11% of fundamentals)

| Metric | Weight in category | Direction | Formula |
|---|---:|---|---|
| Revenue growth | 26% | higher is better | Latest TTM revenue vs. preceding TTM revenue |
| FCF growth (3y) | 22% | higher is better | 3-year compound annual growth in fiscal-year free cash flow |
| Earnings growth | 20% | higher is better | Latest TTM diluted EPS vs. preceding TTM diluted EPS |
| Operating margin trend | 16% | higher is better | Current operating margin − comparable prior-period margin |
| Earnings surprise | 16% | higher is better | Reported EPS vs. consensus estimate, most recent quarter — `derive_earnings_surprise`, `fundamentals_extended.py:519` |

### Capital allocation (10% of fundamentals)

| Metric | Weight in category | Direction | Formula |
|---|---:|---|---|
| Net buyback yield | 34% | higher is better | Reduction in diluted share count ÷ beginning diluted share count |
| Stock comp/revenue | 28% | lower is better | Stock-based compensation ÷ matched-period revenue |
| Asset growth | 22% | ideal range (penalizes aggressive growth) | Year-over-year total assets growth — `derive_asset_growth`, `fundamentals_extended.py:360-371` (Fama-French investment factor: aggressive asset growth predicts *lower* subsequent returns) |
| Capex/depreciation | 16% | ideal range | Capital expenditures ÷ depreciation & amortization (matched period) |

### Accounting quality (10% of fundamentals)

| Metric | Weight in category | Direction | Formula |
|---|---:|---|---|
| Piotroski F-score | 45% | higher is better | Count of applicable Piotroski binary tests, with declared coverage |
| Accruals ratio | 22% | lower is better | (Net income − operating cash flow) ÷ average total assets |
| DSO trend | 17% | lower is better | Comparable-period change in receivable days |
| Inventory-days trend | 16% | lower is better | Comparable-period change in inventory days |

*Piotroski F leads accounting quality; the accruals-ratio anomaly has decayed in US data since
2002, so it's a minor input, not the bucket.*

### Coverage weighting and confidence penalty within fundamentals

`weighted_coverage()` (`scorer.py:485-501`) computes the fraction of total metric *weight*
actually answered for a given company — a missing headline metric (e.g., ROIC) costs far more
confidence than a missing minor one (e.g., DSO trend). The fundamentals score itself is then
shrunk by its own coverage: `raw · (0.65 + 0.35 · coverage)` (`scorer.py:583-584`).

**Financial-sector exemption:** bank/insurer snapshots skip 12 metrics that don't apply to their
balance sheets (`FINANCIAL_EXEMPT`, `scorer.py:167-170`) — those leave the coverage denominator
entirely rather than counting as missing evidence.

**ETFs are never scored here** — `valuation_score()` returns `None, {}` for `is_etf` snapshots
(`scorer.py:510`). See §10.6 for the separate ETF model.

### Two interchangeable scoring engines

Both produce the same six category scores above from different normalization strategies,
selected by `settings.json::normalization_mode` (currently `"bands"`, champion):

- **Band mode** (champion, in production) — every raw metric mapped to 0–100 through fixed,
  hand-set bands (`scorer.py:90-155`), configured per-sector in `settings.json::fundamentals`.
- **Cross-sectional mode** (challenger, shadow-only) — every metric scored as a winsorized
  percentile against the *current refresh's own universe* (sector distribution if ≥8 peers, else
  the full universe), via `CrossSectionalNormalizer` (`scorer.py:296-450`). Published beside the
  champion for comparison, never swapped in silently.

---

## 5. Market behavior (technical) component

`technical_factors()`, `pipeline/advisor_engine.py:83-192`. Seven weighted sub-signals
(`TECHNICAL_WEIGHTS`, `advisor_engine.py:41-47`), combined in `technical_score_from_parts()`
(`advisor_engine.py:207-234`) as `Σ(value·weight) / Σ(weight of resolved signals)` — i.e. the
raw weights below are divided by their **actual sum (1.06, not 1.00)** when all seven resolve,
which is why "effective % of total" isn't simply raw weight × 18%:

| Sub-signal | Raw weight | Normalized weight (÷1.06) | Effective % of total score | Formula |
|---|---:|---:|---:|---|
| `momentum_12_1` | 30% | 28.3% | ≈5.09% | 12-month return skipping the most recent month (`risk_metrics.py::momentum_12_1`, lookback=252, skip=21), mapped `50 + pct_return·1.2` |
| `risk_adjusted` | 26% | 24.5% | ≈4.42% | `0.65 · Sortino + 0.35 · Sharpe` on the stock's own daily returns, mapped through `ratio_to_score` |
| `relative_strength` | 16% | 15.1% | ≈2.72% | 20-day return vs. SPY, mapped `50 + relative·3` |
| `drawdown_resilience` | 14% | 13.2% | ≈2.38% | Score of the deeper of a 60-day or 252-day max drawdown |
| `volume_confirmation` | 8% | 7.5% | ≈1.36% | Ratio of up-day to down-day volume over 60 sessions |
| `low_beta` | 6% | 5.7% | ≈1.02% | Distance from an ideal beta of 0.85 (betting-against-beta, Frazzini-Pedersen 2014) |
| `technical_extended` | 6% | 5.7% | ≈1.02% | Equal blend of 4 indicators from 4 distinct families (below) |

**`technical_extended`** (`pipeline/technical_indicators.py`) is an equally-weighted blend
(~0.25% of total score each) of one indicator per economic family, chosen specifically not to
duplicate the six signals above: `moving_average_slope` (trend), `relative_strength_index`
(oscillator), `bollinger_percent_b` (volatility), `on_balance_volume_slope` (volume). Capped
deliberately at four signals — the module docstring notes most published "technical indicator
zoos" are data-snooping.

**Why 12-1, not raw 12-month:** Jegadeesh & Titman (1993) document a short-term reversal in the
most recent month that runs *against* momentum; the skip-month removes it. A fallback to the
60-day return (reduced coverage) applies for names without a full year of history.

Configurable treatment of `relative_strength` (`short_horizon_treatment`, currently
**`neutral` in production** — the live champion drops `relative_strength` entirely and
renormalizes the remaining six weights, so the 16% raw weight in the table above never
reaches the effective score; verified against `settings.json` in Round 5 after an
ablation dropping the signal proved byte-identical to the baseline): `legacy_momentum`
(keep as-is), `neutral` (drop and renormalize, champion), `reversal` (invert at reduced
weight, challenger).

---

## 6. News sentiment component

`sentiment_score()`, `advisor_engine.py:225-237` → `pipeline/news_intelligence.py::weighted_sentiment`.
Rolling 7-day window, exponential recency decay (3-day half-life), source-quality weighting
(regulatory filings and wire services weighted above aggregator-syndicated copies),
title-similarity deduplication (0.82 threshold), minimum entity-confidence floor (0.25 — low-confidence
ticker matches are discarded, not scored).

Deliberately capped at 4% of the total score — Tetlock (2007) finds media pessimism's price
effect "followed by a reversion to fundamentals" within days; a headline snapshot is a tilt, not
a tenth of the thesis it was cut from (originally 10%, cut to 4%; the freed 6 points moved to
market behavior).

---

## 7. Confidence — the reliability multiplier

Confidence is **not a score** — it never adds evidence, only shrinks the blended score toward
(never past) 80% of its raw value when data is thin, and gates the `INSUFFICIENT DATA` stance
below 0.45.

```
confidence = 0.65 · fundamentals_coverage + 0.25 · market_behavior_coverage + 0.10 · news_sentiment_coverage
base       = raw · (0.8 + 0.2 · confidence)
```

Each component reports its own *coverage* — the fraction of that component's underlying data
that actually resolved — not its score. `pipeline/confidence.py` further decomposes the scalar
into named sub-components for the UI's "why is this confidence low" surface: `completeness`,
`freshness`, `source_reliability`, `peer_sample`, `model_agreement`. The UI labels this
"Evidence confidence" specifically because it measures reliability of the evidence, never the
probability of a price move.

---

## 8. Modifiers — bounded post-blend adjustments

`apply_modifiers()`, `advisor_engine.py:373-396`. Each modifier is independently capped; the
**combined total is then clamped to ±15 points** before being added to the blended base score.
All values below are read live from `settings.json::modifiers`.

| Modifier | Cap | Trigger / mechanics |
|---|---|---|
| Sector valuation percentile | ±3.0 | Cheap/rich vs. sector peers, not absolute multiples |
| Short interest | −6.0 max penalty | Warning at ≥8% of float short, severe at ≥15%; +1.5 add-on for high days-to-cover (≥5.0 days) — Boehmer, Jones & Zhang (2008): heavily shorted names underperform ~1.16% risk-adjusted over 20 sessions |
| Liquidity | −3.0 max | Illiquid below $5M/day median dollar volume; thin below $25M/day |
| Analyst expectations | ±3.0 | Only applied with ≥3 covering analysts; strong upside ≥20% adds, weak upside ≤−5% subtracts, bullish/bearish consensus rating also weighed |
| Macro regime | ±3.0 | FRED rates/inflation/labor/yield-curve, requires ≥70% data coverage, weighted by **sector sensitivity** — e.g. Real Estate weights `rates` at 0.55, Financials weights `yield_curve` at 0.55, Technology weights `rates` at 0.50 (full table in §11) |
| Insider activity | +5.0 / −3.0 | SEC Form 4 opportunistic-cluster buys/sells, Cohen-Malloy-Pomorski (JF 2012) routine-vs-opportunistic split; routine scheduled trades score exactly zero; minimum trade value $25,000; +1.0 cluster bonus |
| Institutional 13F | +3.0 / −2.0 | Breadth of active-only asset managers' QoQ position change; needs ≥2 net movers on one side; half-life 45 days, fully stale at 135 days |
| Congressional buying | +4.0 | Disclosed congressional purchases, reward-only, min trade value $15,000, +2.0 bonus for a member's first-ever trade in a sub-$2B company (Ziobrowski et al., JFQA 2004 / 2011 House study — untested post-STOCK-Act) |
| Customer concentration risk | −3.0 max | ASC 280 XBRL-tagged customer concentration; warning at ≥15% share, severe at ≥30% — a row whose filing could not be read is scored nothing (`measured: False`), never credited with safety it hasn't demonstrated |
| 8-K materiality | −4.0 max | Fixed Item-code lookup on the freshest qualifying 8-K only (bankruptcy 1.03, restatement 4.02, delisting 3.01, impairment 2.06, ...) — never a read of the filing's own text, and penalty-only: no Item code reliably means "good news" the way bankruptcy reliably means bad. Half-life 30 days, stale at 90 days. `edgar_filing_signals.score_8k_activity` |
| Proxy signal | −2.0 max | Only a contested proxy election (DEFC14A) scores; additional soliciting material (DEFA14A) is a flag only. Half-life 45 days, stale at 180 days. `edgar_filing_signals.score_proxy_activity` |
| Filing integrity | −3.0 max | Only a fresh NT 10-K/NT 10-Q late-filing notice scores; an on-time 10-K/10-Q carries no signal by itself. Half-life 30 days, stale at 120 days. `edgar_filing_signals.score_filing_integrity` |
| Geographic concentration (shadow only) | −2.0 max | Single non-domestic country revenue concentration; warning at ≥30%, severe at ≥50% |

Institutional 13F, congressional buying, customer concentration risk, and the three filing
modifiers (8-K/proxy/filing integrity) are all in the **production champion path** —
`apply_modifiers()` calls each one directly and its points count toward the same ±15-point
stack as every row above it (`advisor_engine.py:373-421`, modifier functions at
`advisor_engine.py:602-663`). The three filing modifiers read
`pipeline/build_filings_screen.py`'s published DEF 14A/DEFC14A/DEFA14A, 8-K, and NT 10-K/NT 10-Q
classifications (§1's SEC EDGAR row), refreshed every 3 days and covering only the currently
scored shortlist, not the full universe. Institutional 13F and congressional buying are *also*
recomputed inside the shadow/challenger stack below for comparability, but their champion-path
values are what actually move the published score.

**Geographic concentration is the one modifier that remains challenger-only**, computed via
`apply_challenger_modifiers()` (`advisor_engine.py:654-793`) and **not** part of the production
±15-point stack — it allocates as a fraction of one configurable combined cap (default 20
points, `challengers.signal_corrections.modifier_cap`) instead of stacking an independent cap,
so adjusting one shadow modifier's share never silently changes another's implicit scale. It
stays shadow-only for a correctness reason, not a coverage one: revenue tagged by geography
often reflects shipping destination or contracting entity rather than end demand
(`geographic_concentration_modifier` docstring, `advisor_engine.py`).

---

## 9. Validation state — what has and hasn't been proven

**No signal has been promoted.** The IC (information coefficient) harness has observed 0 of the
24 eligible periods `minimum_icir_periods` requires. No IC, Sharpe, drawdown, or hit-rate
statistic anywhere in this repository should be read as a validated result.

What *has* been measured, from a survivorship-biased five-year backtest using approximated
filing timestamps and raw (not sector-residual) returns (`docs/ALGORITHM-RESEARCH-RESULTS.md`):

- Latest committed six-factor regression (Newey-West, 57 months): annualized alpha **+3.06%**,
  |t| = 0.680 and therefore still insignificant. Significant loadings are market (8.32),
  size (3.85), momentum (2.92) — **not** the value and
  profitability the score is mostly built from.
  **Reproducibility status (Round 4, docs/AUDIT-ROUND-4-FINDINGS.md):** this estimate is
  reproducible to the digit, but it is a statement about one construction on one cache
  state (net-of-cost portfolio value path, 2026-08-03 price cache). The same strategy
  re-measured as gross locked-pick returns on the 2026-08-10 cache gives **+0.43%**
  (t 0.09). The three-point gap decomposes as +1.97pp return construction (costs plus
  cash drag) and +1.06pp cache state. Historical alpha is currently under reproducibility
  reconciliation: nominally comparable runs produce materially different point estimates,
  neither statistically distinguishable from zero. No historical alpha figure from this
  repository is authoritative without its experiment manifest
  (`pipeline/validation/experiment_manifest.py`).
- Against 14 tradeable style/size ETF legs: all are beaten on CAGR and six smaller-cap/breadth
  legs are beaten with significant single-benchmark alpha; alpha remains insignificant against
  SPY, VTV, the fixed size/value blend, and the six-factor model.
- Regime-dependent: **+11.1pp** annualized vs. SPY in bear markets, **+9.6pp** in falling rates,
  and **−6.7pp** in rising rates.

**Current classification: B — a transparent factor tilt with no demonstrated residual alpha.**
Do not present SPY outperformance as this model's objective.

**Capacity (Round 6):** under the canonical square-root impact law (now the base
scenario of `pipeline/costs.py`), the buffered strategy carries roughly **$13M at a
50bps/yr impact budget, $50M at 100bps, and $200M at 200bps**. The pre-Round-6 cost
model understated impact by more than an order of magnitude at scale and survives only
as the labeled optimistic scenario. This is a personal-account-scale instrument and the
retrospective multiple-testing battery (deflated Sharpe 0.95 marginal, PBO 0.69, HLZ
t>3 failed, docs/AUDIT-ROUND-6-FINDINGS.md section 5) means its one positive alpha
estimate is not evidence of alpha after accounting for the search that produced it.

**Ranking-integrity disclosure (Round 5):** restoring statement enrichment alone, with no
methodology change, reordered the published board at rank correlation 0.820 with a mean
absolute shift of 114 ranks (Round 4, pinned refresh `advisor-2026-08-10T17:22:04`).
Every ranking published between 2026-08-06 and the enrichment recovery was substantially
a map of data availability, not of the methodology. The publication coverage floor and
statement-health states (`pipeline/data_health.py`) exist to make any recurrence visible
and non-publishable.

**Transaction costs** (`pipeline/costs.py`, `docs/TRANSACTION-COSTS.md`): `half_spread + fees +
volatility_scaled_impact`, three scenarios, labeled (not measured) spread proxy. At the realized
64.9% monthly turnover, the published 10bps flat cost model costs 78bps/year — 7.0% of gross
return.
**Reproducibility status (Round 4):** the 64.9% figure is pinned to the 2026-08-03 cache.
The identical script and flags on the 2026-08-10 cache produce 50.6%, and the two runs'
picks diverge 55% at the very first rebalance, because the provider serves restated data
keyed to today. Treat any turnover figure as cache-pinned. Round 4's decomposition on the
2026-08-10 cache: fundamentals only 12.2pp, technical component +37.1pp, modifiers +1.3pp,
news 0.0pp.

**Portfolio construction methodology, as a variable:** `pipeline/backtest_monthly.py` supports an
offline `--construction-method` flag (default `appeal`, the score-proportional weighting used for
every historical result above — unchanged in behavior). A second method, `inverse_volatility`,
weights each selected name inversely to its own trailing 60-day realized volatility, computed
only from prices as of the rebalance date (no look-ahead) — explicitly **not** true risk parity,
since it ignores cross-name correlation. This is a manually-run backtest/challenger-strategy
experiment, not part of the live research pipeline or any published screen; its results are
tagged with `construction_method` in whichever backtest manifest used it and have not themselves
been through the validation battery above.

Full detail: `docs/MODEL-CARD.md`, `docs/LIMITATIONS.md`, `docs/VALIDATION-METHODOLOGY.md`.

---

## 10. Every other score in the app

### 10.1 Structural / Timeliness (v2 shadow model)

`pipeline/scoring_v2.py::build_v2_analysis` (lines 65-242), surfaced as `analysis_v2` on every
research row but **not** blended into the production score — `MODEL_VERSION =
"structural-timeliness-2.0.0"`, pending its own prospective validation.

- **Structural** — reuses the same six fundamental categories/weights as §4, but every metric
  first passes an applicability/provenance layer (`canonical_metrics.py`): `applied`,
  `suppressed` (doesn't apply to this business profile), `unavailable` (applicable but missing),
  or flagged `stale_observation` / `provider_conflict`. `effective = 50 + confidence · (raw − 50)`
  — low-confidence reads shrink toward neutral rather than reporting at face value.
- **Timeliness** — 70% forward EPS-revision (30-day) + 30% earnings surprise, each mapped
  `50 + value·multiplier`. Classified `improving` (≥60) / `stable` / `weakening` (<45), or
  `insufficient_evidence` below 0.40 confidence.

Never summed into one number — that split is the entire point (see §10.4's structural/tactical
matrix, which cross-tabulates this structural score against a separate tactical score).

### 10.2 Political / congressional trade score

`pipeline/scorer.py::run()` (lines 831-943; the earlier "678-790" reference in this doc had
drifted out of date as the file grew). Six independent weighted factors, summed and capped
per-factor (`signal_weights`, `settings.json`):

| Factor | Weight |
|---|---:|
| Track record | 25 |
| Committee relevance | 20 |
| Cluster detection | 20 |
| Trade size | 15 |
| Direction/recency | 10 |
| Policy catalyst | 10 |

Carries **zero** fundamental or price input — purely who in Congress traded what, in what
committee, in what size, how recently, and whether other members clustered on the same name
within 30 days. Writes `signals.json`, not `advisor.json` — nothing in the CI pipeline currently
calls `scorer.run()` outside `seed_mock_data.py`/`demo-data.yml`, so treat this section as
describing the model this score *would* compute in production, not one presently published
alongside real Congressional data. The score that actually reaches production is a much smaller
one: `pipeline/congress_signal.py::score_congressional_buying`, called from
`fetch_advisor.collect_congressional_signals()` and folded into the research score as a capped,
champion-path modifier (§8's "Congressional buying" row), reading the real, live
`screens/congress-trades.json` this doc's §7 (data flow) and `docs/DATA-LINEAGE.md` describe. The
two are not the same score and are never combined with each other.

**"Since purchase" price performance** on `/screens/politics` normally comes from Financial
Modeling Prep's `historical-price-eod` endpoint (`pipeline/build_congress_screen.py`,
`compute_price_performance()` → `client.price_history()`); when FMP has no client, no
entitlement, or simply misses a symbol, it falls back to `yahoo_history()` (imported from
`fetch_advisor` to avoid a circular import) so the column doesn't silently disappear for the
~4% of rows FMP doesn't cover. Each priced row is tagged `price_source: "fmp"` or `"yahoo"`.

### 10.3 Momentum screen score

`pipeline/research_screens_v2.py::momentum_scores` (lines 169-206) → `/screens/momentum`. **Not**
the same number as `momentum_12_1` inside the research score (§5) — same underlying return math,
structurally unrelated score.

| Factor | Weight |
|---|---:|
| `momentum_12_1` | 40% |
| `momentum_12_7` | 20% |
| `momentum_6_1` | 15% |
| `high_52w_proximity` | 15% |
| `industry_relative_momentum` | 10% |

Every factor is winsorized then standardized (z-score, mean 0 / sd 1) against the **current
universe** before weighting — cross-sectional, not absolute like the research score's version.
Eligibility gates: $5 min price, $300M min market cap, $2M min 60-day median dollar volume, 253
min history sessions, binary-event/stale-price exclusions. Entry/exit hysteresis (enter ≥90th
percentile, exit only below 75th) prevents flicker. Point-in-time integrity enforced via
`month_end_prices()` — formation-month data never leaks into the signal.

### 10.4 Tactical (earnings-timeliness) screen score

`pipeline/research_screens_v2.py::tactical_score` (lines 209-221) → `/screens/earnings`,
cross-tabulated against the structural score (§10.1) at `/screens/matrix`.

| Factor | Weight |
|---|---:|
| Revision magnitude | 15% |
| Revision agreement | 12% |
| Industry revision breadth | 10% |
| EPS surprise | 8% |
| `momentum_12_1` (carry-over) | 8% |
| Revision acceleration | 8% |
| Fresh estimate delta | 5% |
| Dispersion trend | 5% |
| Post-earnings drift | 5% |
| Risk/tradability | 5% |
| `momentum_6_1` (carry-over) | 4% |
| Surprise consistency | 4% |
| `high_52w_proximity` (carry-over) | 4% |
| `industry_relative_momentum` (carry-over) | 4% |
| Revenue surprise | 3% |

2×2 classification (`high-conviction candidate` / `quality company, wait` / `tactical-only
candidate` / `avoid`) requires **both** structural ≥65 *and* tactical ≥60 for the top label.

### 10.5 Quality-value screen score

`pipeline/research_screens_v2.py::robust_value_score` + `classify_quality_value` →
`/screens/quality-value`. Cheapness = weighted median of each metric's own-history percentile —
"cheap for this company vs. its own multi-year range," distinct from "cheap vs. sector" (§4's
modifier) or "cheap vs. universe" (§4's cross-sectional challenger mode). Final classification
requires cheapness (≥70th own-history percentile) **and** quality (≥65 structural-style score),
and screens out severe forward-estimate deterioration/distress — a cheap, high-quality name can
still be flagged `cheap but deteriorating`.

### 10.6 ETF composite score

`pipeline/fetch_etfs.py::score_etf_universe` → `public/data/etfs.json`. A **fully separate
model** from the stock score — stocks are never scored by this model, funds are never scored by
§4's model. Percentiles computed within each fund's own peer group
(`peer_groups`, `pipeline/config/universe.json`).

| Bucket | Weight | Inputs |
|---|---:|---|
| Performance | 28% | Trailing returns across every published window, percentile-ranked within peer group |
| Risk | 27% | Sortino, Sharpe, max drawdown (same `risk_metrics.py` functions the stock model uses), beta (low-beta scores well) |
| Cost | 17% | Expense ratio, 1-year tracking difference (signed), absolute premium/discount to NAV |
| Liquidity | 16% | Average dollar volume, bid-ask spread |
| Quality | 12% | `structural_quality()` — issuer reputation adjusted for AUM, leverage/inverse structure (−25), synthetic replication (−10), aggressive securities lending (−5) |

Peer groups: broad-market/growth/value/small-cap/mid-cap all share `equity_broad`; dividend →
`equity_income`; international → `equity_international`; sector → `equity_sector`; thematic →
`equity_thematic`; bonds → `fixed_income`; commodity/crypto get their own groups. Ties share a
percentile rank; a missing metric leaves a fund at a neutral 50 rather than penalizing it.

### 10.7 Swing-horizon composite (2 trading days – 8 weeks)

`pipeline/swing_signals.py::swing_scores` + `pipeline/build_swing_screen.py` →
`/screens/swing`, and the same five legs and weights as the `swing` ranking model in
`src/lib/rankingModels.js` (surfaced on `/research` as *Model: Swing setup*). Every leg is
standardized cross-sectionally — winsorized and z-scored, except the earnings surprise, which
is rank-normalized (see rule 4 below); the composite is the weighted sum at declared weights,
with an unresolved leg contributing zero rather than rescaling the legs that did resolve.

| Leg | Weight | Direction | Evidence |
|---|---:|---|---|
| Post-earnings drift (SUE) | 30% | Continuation of the surprise | Bernard & Thomas (*JAR* 1989; *JAE* 1990) — drift over ~60 trading days, monotone in SUE |
| Analyst revision (change, not level) | 25% | Direction of the revision | Jegadeesh, Kim, Krische & Lee (*JF* 2004); Womack (*JF* 1996) |
| High-volume return premium | 20% | Continuation | Gervais, Kaniel & Mingelgrin (*JF* 2001) |
| 52-week-high proximity | 15% | Continuation | George & Hwang (*JF* 2004) — scored in the name's own volatility, see rule 4 |
| Prior-week reversal | 10% | Contrarian | Jegadeesh (*JF* 1990); Da, Liu & Schaumburg (*MS* 2014) |

Five design rules, all enforced in code and covered by
`pipeline/tests/test_build_swing_screen.py` and `pipeline/tests/test_edgar_sue.py`:

1. **The sign flip is handled explicitly.** The same raw trailing return predicts reversal at
   2-10 days and continuation at 3-12 months, so the contrarian leg reads only `return_5d`,
   the continuation leg is 52-week-high proximity (a price/high ratio carrying no recent-month
   return), and no trailing return is read by two legs. A single "past return" factor spanning
   the whole window would average to noise.
2. **Cost gating is part of the model.** The reversal leg is not scored at all below $25M
   median daily dollar volume (reason code `REVERSAL_LEG_COST_GATED`) — it is a
   liquidity-provision premium and the most capacity-constrained of the five.
3. **Short interest is a negative screen, never a leg.** Boehmer, Jones & Zhang (*JF* 2008) is
   a top-decile *level* result, so suppression requires ≥10% of float short **and** top-decile
   standing in the current cross-section (`SHORT_INTEREST_SUPPRESSED`). Days to cover is short
   interest over average volume, so an absolute threshold on it selects low-turnover names
   rather than heavily-shorted ones — measured on this universe, a 5-day line suppressed 20
   names whose float short was 3-7%, a liquidity screen wired in backwards. It now corroborates
   and never suppresses alone. Suppressed names stay published and ranked so the screen is
   visible rather than silent; a long-only book cannot harvest the short leg.
4. **The 52-week-high leg is measured in the name's own volatility, and SUE is ranked.** Raw
   price/52-week-high is mechanically higher for a quiet stock — measured at −0.49 against
   60-day realized volatility across this universe, with median proximity falling monotonically
   from 0.94 in the quietest volatility quintile to 0.73 in the loudest — so scoring it raw
   imports an undeclared low-volatility and sector tilt. The scored subfactor is the log
   drawdown from the high divided by annualized volatility. Separately, the seasonal-difference
   SUE is heavy-tailed by construction, so it is rank-normalized rather than winsorized: at a
   5%/95% clip on a 30%-weight leg, 5% of the universe shared one identical value and 12 of the
   top 15 rows sat on it. Bernard & Thomas report drift monotone in the SUE *decile*, so
   ranking is also closer to the published construct.
5. **A missing leg rescales the legs that resolved, and a row too thin to rescale is
   excluded.** Amended 2026-08-12 (`SA-2026-08-12-04`), reversing the previous rule. Scoring an
   unresolved leg as 0 and dividing by the declared total pulls every thin row toward the
   cross-sectional mean, and thinness is not random: coverage tracks size and liquidity, so the
   rule muted exactly the high-idiosyncratic-volatility, low-liquidity names where McLean &
   Pontiff (*JF* 2016) measure decay to be worst. That is an undeclared size and liquidity tilt
   inside a rule that presented itself as conservative. Declared weights are now renormalized
   across the legs that resolved. The wider-scale problem the old rule was written against is
   handled by a floor instead: a row resolving fewer than three of five legs is excluded from
   the ranked output entirely rather than scored near neutral and left in. `swing.json`
   publishes `legs_resolved` beside `coverage`, and the superseded zero-filled value as
   `composite_z_zero_filled`. This reverses the direction Round 4 took on the research score
   (`scorer.py` mode `fixed_feature`), and the two are compatible only because this one is
   paired with a hard floor; the tension is recorded in the freeze file rather than left to be
   rediscovered. `pipeline/diagnostics/renormalization_shift.py` measures the resulting size
   and liquidity shift in the top decile.
6. **The ranked book carries a declared sector cap.** Amended 2026-08-12
   (`SA-2026-08-12-07`). Four of the five legs are continuation signals and continuation
   clusters by sector, so without a cap the head of the ranking is a mega-cap technology and
   communication-services bet wearing a five-leg label. A configurable cap, defaulting to 30%
   of the ranked book per GICS sector, is applied after ranking by trimming the lowest-scoring
   names in the over-represented sector, so the constraint costs the book its weakest
   expressions of the crowded view rather than reshuffling the ranking. Every trim is logged
   and trimmed rows stay published with `SECTOR_CONCENTRATION_CAP` attached.

The PEAD leg reads standardized unexpected earnings from the EDGAR point-in-time store
(`pipeline/edgar_sue.py`), not the advisor snapshot's `earnings_surprise`. That field was
0/839 populated — it depends on yfinance's `earnings_dates` scrape — and is in any case a
four-quarter weighted average of *percent* surprise built for fundamental momentum, not the
most-recent standardized surprise PEAD is a claim about. The replacement is the seasonal
random walk with drift (Foster 1977; Foster, Olsen & Shevlin 1984), computed from as-filed
quarterly net income (split-immune, unlike as-filed EPS) and standardized by the firm's own
prior eight seasonal differences. The drift term is published per row, so the with-drift form
is verifiable from the output rather than asserted. Drift windows are anchored on the earnings
*release* datetime from Form 8-K Item 2.02 (`SA-2026-08-12-02`), which is a different filing
from the 10-Q and arrives on the release day; the filing-date anchor it replaces understated
window age in one direction every time. A period with no resolvable release datetime scores
nothing on this leg and is never carried on the filing date, and the coverage that costs is
published per run as `pead_anchor_diagnostic` with the delta against the pre-amendment 84.7%
surfaced explicitly. Leg coverage went 0% → 84.7% when the store replaced the advisor field,
and the re-anchoring can only lower it from there.

Eligibility gates otherwise mirror the momentum screen ($5 price, $300M cap, $2M 60-day median
dollar volume, 253 sessions) plus a 35% minimum signal coverage, and membership uses the same
90/75 entry/exit hysteresis. The published file carries the weights, per-leg citations and
gross effect sizes, per-leg coverage across the universe, the applied thresholds, the
McLean & Pontiff (*JF* 2016) 26%/58% decay haircut applied to all five legs, and a `cost_model`
block giving the median round-trip cost **per position** at several **book** sizes under the
canonical square-root impact law (`costs.py`). The two sizes are labelled separately because
the capacity conclusion is the ratio between them. A participation cap of at most 10% of
trailing 20-day ADV per round trip, defaulting to 5%, rejects positions it cannot price rather
than quoting them (`SA-2026-08-12-06`), and the published points are checked against the
square-root law rather than trusted because one function produced them. The spread term is a
liquidity-tiered proxy, not a measured quoted spread and not an effective spread. Annual drag
is the round-trip cost times the number of round trips a year, which no backtest has yet
produced. The weights are frozen starting priors ordered by evidence quality,
not measured optima — no rank-IC, quantile-spread or deflated Sharpe result backs this
composite yet. It is registered in `pipeline/validation/harness_freeze.json` under
`additional_models` on a prospective clock starting 2026-09-01, and until that clock reports it
is a research filter rather than a screen with a record: by effective weight it is 45%
technical, and Rounds 5-6 found no technical sub-signal clearing the noise standard on the
as-filed spine. The freeze entry also records the open questions the clock must answer. Two of
them were turned into registered comparisons on 2026-08-12 rather than left open: the
short-term reversal leg now runs as three variants (`A` frozen baseline, `B` reversal removed
with its 10% redistributed proportionally, `C` reversal residualized against the industry
return and the other four legs), and the sector tilt is now bounded by a declared 30% cap. All
three reversal variants run forward from 2026-09-01 and none is chosen on historical data.

An **entry-timing overlay** (`pipeline/overlay/entry_timing.py`) sits beside the composite and
is off by default. It gates names the composite has already selected and never influences a
score or a rank: RSI and MACD appear nowhere in `swing_signals.py`. Its momentum toggles are
mutually exclusive, because RSI, MACD and moving-average slope are transforms of the same
recent price series and reading them as independent confirmations triple-counts one factor. The
registered ablation is five cells (`O-0` through `O-4`) and that is the entire test budget. The
acceptance rule was written into the freeze file on 2026-08-12, before any result existed: a
variant is adopted only if it improves net-of-cost deflated Sharpe over the control by at least
0.10 **and** clears t > 3.0 (Harvey, Liu & Zhu, *RFS* 29(1), 2016), the hurdle raised from the
usual 2.0 because Sullivan, Timmermann & White (*JF* 1999) show the best in-sample technical
rule loses its significance once the universe of rules tried is corrected for. Otherwise the
overlay stays off permanently and the momentum-turn code is deleted rather than left dormant.

Deliberately absent, because they do not survive data-snooping correction and costs in US
single-stock data: RSI 70/30 thresholds, MACD crossovers, Bollinger-band signals as standalone
alpha, VWAP as multi-day alpha, OBV, and candlestick/chart patterns (Sullivan, Timmermann &
White *JF* 1999; Bajgrowicz & Scaillet *JFE* 2012; Marshall, Young & Rose *JBF* 2006).

### 10.8 Watchlist quality score

`pipeline/config/settings.json::watchlist_setup`. Weighted blend of four continuous subscores,
using smooth sigmoid transitions around configured centers (not hard cutoffs):

| Subscore | Weight |
|---|---:|
| Thesis | 30% |
| Research score (reuses §3's number as one input, not a rename of it) | 30% |
| Data coverage | 20% |
| Published guidance | 20% (HOLD=1.0, WATCH=0.6, TRIM=0.15, SELL=0.0) |

A hard confidence/coverage floor (0.45) or a published SELL guidance blocks position sizing
regardless of the blended quality number; everything else is soft.

---

## 11. MarketPulse — the macro backdrop

"Market Pulse" is the app's name for the macro-context feature — a preview card on the Home
report (`MarketPulsePreview`, `src/pages/Dashboard.jsx:121-136`) and the full `/market` page
(news feed with filing/commentary labels, `APP-COMPLETE-BREAKDOWN.md`'s route map). It is **not**
a scoring model on its own — it's a data display plus a feeder into one modifier.

**What it shows** (from `advisor.json.market.macro`, sourced from FRED):

| Field | Meaning |
|---|---|
| FRED regime score | 0–100 composite regime read, with a plain-language label |
| 10Y Treasury | Latest yield, as of its data date |
| Fed funds rate | Latest effective rate |
| Inflation | Latest reading |

**How it feeds the research score:** the same FRED-derived regime data powers the **macro regime
modifier** (§8, ±3.0 points), which is **sector-sensitive** — it does not apply the same weight
to every stock. Full sector-weight table (`modifiers.macro_regime.sector_weights`,
`settings.json`):

| Sector | rates | inflation | labor | yield_curve |
|---|---:|---:|---:|---:|
| Technology | 0.50 | 0.15 | 0.20 | 0.15 |
| Communication Services | 0.40 | 0.15 | 0.25 | 0.20 |
| Financial Services / Financials | 0.10 | 0.10 | 0.25 | 0.55 |
| Consumer Cyclical | 0.20 | 0.30 | 0.35 | 0.15 |
| Real Estate | 0.55 | 0.15 | 0.15 | 0.15 |
| Default (all other sectors) | 0.30 | 0.25 | 0.25 | 0.20 |

A 7th FRED series, VIX-derived volatility (`pipeline/fred.py::derive_regime`, published as
`factors.volatility`), is collected and published in `advisor.json.market.macro` alongside the
four above but is **not** part of the weighted composite regime score and has no sector-weight
column here or in `settings.json` — folding it into either is an explicit, un-made
recalibration decision (see §1). It is not currently surfaced on the `/market` page or the Home
preview card.

The modifier requires ≥70% coverage of the underlying FRED series before it fires at all
(`min_coverage: 0.7`). This is deliberately a *context* modifier, never a primary ranking
factor — it can move a score at most ±3 points out of the ±15-point combined modifier cap.

---

## 12. Stance, guidance, and recommendation policy

`stance_for()` (`advisor_engine.py:558-567`): below 0.45 confidence → `INSUFFICIENT DATA`,
regardless of score. Otherwise: **ATTRACTIVE** (≥75) / **PROMISING** (≥60) / **MIXED** (≥45) /
**CAUTION** (below 45).

`action_for()` (`advisor_engine.py:492-555`) is the production recommendation policy: requires
**agreement across at least two independent factor groups** (fundamentals, market behavior,
positioning/sentiment) before recommending SELL or TRIM — a single bad headline or one weak
quarter is never sufficient on its own.

A shadow **v2 policy** (`pipeline/recommendation_policy_v2.py`, surfaced as `recommendation_v2`,
does **not** control production actions) separates company thesis from 1–3 month timeliness,
portfolio fit, and user-specific position rules, and shrinks company scores toward neutral under
low confidence.

---

## 13. Where every score is displayed in the app

| Score | Route(s) | Component(s) |
|---|---|---|
| Research score | `/`, `/research`, `/search`, stock detail sheets | `Dashboard.jsx`, `Picks.jsx`, `ScoreExplainability.jsx` (waterfall attribution via `pipeline/explainability.py`), `ScoreBandView.jsx`, `ResearchRadarChart.jsx` |
| Structural / Timeliness (v2) | `/screens/validation` (shadow diagnostics) | `LiveValidation.jsx` |
| Momentum screen | `/screens/momentum` | `ResearchScreen.jsx` |
| Swing-horizon composite | `/screens/swing`, and as the *Swing setup* ranking model on `/research` | `SwingScreen.jsx`, `Picks.jsx` (`rankingModels.js`) |
| Tactical / structural-tactical matrix | `/screens/earnings`, `/screens/matrix` | `ResearchScreen.jsx` |
| Quality-value screen | `/screens/quality-value` | `ResearchScreen.jsx` |
| Political score | `/screens/politics` | `CongressTrades.jsx` |
| ETF composite | ETF comparison views inside `/research`, `/portfolio` | `Picks.jsx`, ETF comparison components |
| Watchlist quality | `/watchlist` | `Watchlist.jsx` |
| MarketPulse (macro backdrop) | Home report preview, `/market` | `MarketPulsePreview` (`Dashboard.jsx`), `/market` page |
| Inside information (institutional 13F + Congress, merged) | `/screens/inside-information`, Home dashboard card | `InsideInformation.jsx`, `Dashboard.jsx` |
| SEC filing modifiers (8-K / proxy / filing integrity) | Stock detail sheet panel (§8) | `StockDetailModal.jsx` |
| Methodology (plain-language, research score only) | `/methodology` | `Methodology.jsx` (reads live weights from `advisor.json.methodology` — cannot drift from the config that produced them) |

---

## 14. Research report screens (`/screens/*`)

These are cross-sectional screens over the configured screen universe (926 names) — distinct
from the per-stock research score (§3). Top-level navigation order (`SCREEN_NAV`,
`src/pages/ResearchScreen.jsx`): Swing signals, Fast growth, Options, Momentum, Quality at
valuation lows, Earnings timeliness, Structural vs tactical, Early session, Shadow portfolios,
Live validation, Politics trade alert, Institutional accumulation, Inside information, Theme
exposure, Backtest comparison. The `Screens` entry in the primary nav lands on `/screens/swing`.

| Route | Data file | What it ranks |
|---|---|---|
| `/screens/swing` | `screens/swing.json` | §10.7 — the swing-horizon composite (2 trading days to 8 weeks) |
| `/screens/fast-growth` | `report.json` (client-computed, see below) | Two client-side sub-screens: Breakouts and Emerging growth |
| `/screens/options` and 7 sub-strategies | `screens/options.json` + 6 more, see §15 | Multi-day options ideas per mechanism |
| `/screens/momentum` | `screens/momentum.json` | §10.3 — 12-1/12-7/6-1 momentum, 52w proximity, industry-relative momentum |
| `/screens/quality-value` | `screens/quality-value.json` | §10.5 — own-history valuation percentile + quality + distress/revision gates |
| `/screens/earnings` | `screens/earnings-timeliness.json` | §10.4 — revision/surprise tactical score |
| `/screens/matrix` | `screens/structural-tactical.json` | §10.1 × §10.4 — 2×2 structural/tactical classification |
| `/screens/early-session` | `screens/early-session.json` | Early-session reversal research, shadow-mode/capability-gated |
| `/screens/shadow` | `screens/shadow-portfolios.json` | Immutable, net-of-cost prospective strategy performance — "no strategy is promoted from implementation alone" |
| `/screens/validation` | `validation/live_v2_validation.json`, `validation/ic_validation.json`, `validation/research_evidence.json`, `validation/monte_carlo_projection.json` | Champion-vs-challenger prospective evidence (the IC harness, §9) and the strategy's own 10,000-path Monte Carlo projection (`pipeline/monte_carlo_projection.py` — unrelated to the `/planning` simulator in §16) |
| `/screens/politics` | `screens/congress-trades.json` | §10.2 — STOCK Act disclosures, filterable by chamber/committee/trade size |
| `/screens/institutional` | `screens/institutional-13f.json` | SEC Form 13F-HR accumulation/distribution — the same data source that feeds the `institutional_13f` modifier (§8), but shown here as a factual, disclaimed screen (descriptive flags, not points) rather than folded into any score |
| `/screens/inside-information` | `screens/inside-information.json` | Below — institutional 13F + Congressional trading, merged and filtered to only the notable subset of each |
| `/screens/themes` | `advisor.json` (`theme_exposure_score` per name) | §14.1 below |
| `/screens/backtests` | `screens/backtest-comparison.json` | Below — a meta-comparison of every backtest result file in the repo, not a scored screen of its own |

### Institutional 13F — resolving a manager name to the filer that actually files

A manager's own ticker CIK is frequently the wrong filer: it's often the public holding
company, while a separate operating/advisor subsidiary is the entity that actually files
13F-HR (e.g. T. Rowe Price's ticker CIK belongs to the holding company; the 2022-spun-out
"T Rowe Price Investment Management" adviser subsidiary is the real filer). `resolve_filer_ciks`
(`pipeline/build_institutional_screen.py:327`) tries the ticker CIK first, then searches EDGAR
by name, and keeps only entities whose EDGAR conformed name matches the manager's declared name
or one of its `filer_aliases` **and** that actually file 13F-HR — every alias candidate is
still verified against live EDGAR before being trusted, never assumed. Aliases are declared per
manager in `pipeline/config/institutional_managers.json` (`filer_aliases`), covering T. Rowe
Price, AllianceBernstein, Janus Henderson, and Artisan Partners; AMG and Virtus are documented
there as **not fixable via aliases** — genuine multi-affiliate structures (e.g. AQR, Pzena,
Kayne Anderson Rudnick) where the affiliates that actually file have no ticker of their own, so
their 13F coverage stays incomplete by design rather than guessed at.

### Fast growth — the two sub-screens, exact formulas

Client-computed in `src/lib/researchScreens.js`, not a published pipeline artifact.

**Breakouts** (`rankBreakoutInProgress`) — sharp recent acceleration, already validated by
price action. Requires 5-day return > 2% and 20-day return > 0%, and that momentum is
*accelerating* (5-day pace exceeds the pace implied by the preceding 15 days of the 20-day
window). Rank score: `burst·0.4 + acceleration·0.3 + trend·0.2 + volume·0.1`, where each term
is a `clamp(50 + raw·multiplier)` mapping of weekly return, acceleration, monthly return, and
60-day volume ratio respectively.

**Emerging growth** (`rankEmergingGrowth`) — explicitly labeled `research_status:
"prospective_unvalidated"` in the output; nothing in this codebase has tested whether this
combination predicts a subsequent move. Deliberately excludes anything the Breakouts screen
already caught (requires 5-day return ≤ 2%, the opposite gate). Requires revenue growth > 5%
and positive 20-day relative strength. Rank score, weights renormalized over whichever terms
resolve:

| Term | Weight | Formula |
|---|---:|---|
| Growth score | 35% | `clamp(50 + revenue_growth·150)` |
| Margin score | 20% | `clamp(50 + operating_margin_trend·300)`, defaults to 50 if trend is missing |
| Relative-strength score | 20% | `clamp(50 + relative_strength_20d·4)` |
| Volatility-contraction score | 15% | 70 if 10-day realized vol < 85% of 60-day realized vol, else 40, else 50 if indeterminate |
| Estimate-revision breadth | 10% | `clamp(50 + revision_breadth·50)`, only included when present (small ticker subset today) |

### Theme exposure — `/screens/themes`

`pipeline/themes.py` + `pipeline/theme_signals.py`. Answers "how exposed is this company to a
multi-year structural demand driver (e.g. AI infrastructure), independent of whether its price
has already moved?" — a deliberately *leading*, not momentum-chasing, measure. The design rule
is hardcoded, not configurable: **price momentum contributes exactly zero weight** to theme
exposure, because Ben-David, Franzoni, Kim & Moussawi (*Review of Financial Studies* 2023) find
thematic ETFs lose ~30% risk-adjusted over their first five years, driven by launching near
valuation peaks in already-hyped names. A name in the top valuation decile is excluded or
flagged rather than scored as an opportunity.

Up to six signal families per theme (each theme declares its own subset and weights,
normalized to sum to 1): `segment_revenue_share` (ASC 280 XBRL segment reporting),
`filing_keyword_density_trend` (change in how much of a 10-K Item 1 discusses the theme),
`transcript_theme_salience` (same measurement on earnings-call transcripts filed via 8-K),
`customer_concentration_to_spenders` (ASC 280 named customers matched against confirmed theme
spenders), `spender_capex_growth` (spelled `hyperscaler_capex_growth` in the AI theme that
introduced it — same measurement, named for that theme's cheque-writers), `backlog_growth`.
Each signal's raw reading is mapped to
0–100 on its own natural scale (e.g. `segment_revenue_share` at value·200, capped 100; capex/backlog
growth at `50 + value·165`). A theme requires **at least 2 resolved signals**
(`min_signals_required`) before it publishes a score at all — a single segment-revenue data
point is never allowed to carry a theme alone.

Two scoping rules keep filing language from standing in for exposure:

- **Theme-level vs company-specific signals.** A signal declaring a `universe` (the capex
  pull-through) is measured on the spenders, so every candidate receives the identical reading.
  It contributes to the score and describes the demand driver, but it cannot satisfy
  `require_leading_signal_confirmation` — a constant has no cross-sectional information, and
  accepting it as confirmation confirmed every company at once.
- **Scope, at two grains.** Each theme declares `sectors` (the outer bound) and `industries`
  (the supply chain itself, matched as case-insensitive substrings against the row's Yahoo
  industry — `semiconductor` matches both `Semiconductors` and `Semiconductor Equipment &
  Materials`). Both must pass. Sector alone was not enough: it cannot separate a chip-equipment
  maker from a trucking company, since both are "Industrials". A row whose industry never
  resolved falls back to the sector bound, and a theme's own `seed_tickers` are always in scope
  — a vendor taxonomy built for the whole market understates some anchors (Eaton's data-center
  power business is filed under "Specialty Industrial Machinery"), and naming the anchor is
  narrower than admitting its whole industry. Out-of-scope names are not scored and never
  trigger a filing fetch. Without any of this, banks and insurers ranked as top exposure to the
  AI hardware buildout on the strength of describing their own data centers.
  `themes.report_scope` logs what each level admits and warns when an industry list admits
  nobody, so a renamed vendor classification cannot empty a theme silently.

Eleven themes ship, each tagged to a top-level growth chain: `ai_infrastructure`
(AI_COMPUTE_AND_DATA), `automation_and_robotics`, `grid_electrification`,
`reshoring_industrial_capacity`, `defense_rearmament` (DEFENSE_AEROSPACE_AND_SPACE),
`energy_security`, `cybersecurity`, `digital_payments`, `obesity_care_supply_chain` and
`aging_demographics` (HEALTHTECH_AND_BIOTECH / DEMOGRAPHICS_AND_AGING), and
`water_infrastructure` (CLIMATE_ADAPTATION_AND_WATER). Each publishes up to 20 rows per
candidate group (leaders, sector-connected) with the pre-truncation group sizes alongside, and
`by_ticker` indexes every scored name across every theme it clears — the screen's cross-theme
view is built from that index. Sector-peer expansion draws on a **shared budget of 120
candidates per run**, spent round-robin, so the cost of the layer does not grow with the number
of themes declared (each candidate can cost two multi-megabyte filings).

Every theme declares its **chain** — root driver, first-order winners, second-order winners,
and the disconfirming evidence that would say the thesis is weakening — and a **role** per
company (`root`, `enabler`, `supplier`, `infrastructure`, `service`), assigned by industry with
per-ticker overrides. Roles are declared per theme because a role is a property of the
relationship: a utility is the root of an electrification chain and infrastructure in an AI one.

### Theme trend evaluation — `pipeline/theme_trend.py`

A separate question from exposure, and the one place in the theme layer that reads price on
purpose: *is this trend actually moving, is the move shared, and has the market already paid
for it?* Exposure answers "does this company build any of this" and is forbidden from reading
price; the trend block reads price about **the theme**, never about a company's exposure, and
`validate_data` enforces the separation — the block must publish
`contributes_to_exposure: false`, and an exposure row carrying any price field is a hard error.

Measured across each theme's scored members, from fields the research score already computes:

| Reading | What it answers |
|---|---|
| Direction | median member relative strength vs benchmark, plus acceleration |
| Breadth | share of members above their own 20- and 50-day averages, and share outperforming |
| Leadership | whether the group's strength survives removing its largest member |
| Fundamental confirmation | share with rising 30-day EPS estimates; median volume ratio |
| Crowding | median member expensiveness percentile (≥67 ⇒ "already priced") |
| Role rotation | the same readings per chain role, which is what makes a rotation legible |
| Chain confirmation | whether suppliers/infrastructure participate or only the root moved |

These combine into one of six verdicts by stated rule, not fitted weights: `broadening`,
`narrow leadership`, `strong but already priced`, `cooling`, `mixed`, `unmeasured` (fewer than
5 members resolved). Crowding is checked **before** strength is celebrated, so a real trend
that is already expensive — the documented failure mode of thematic products — can never be
reported as a clean signal. No threshold here is optimized against returns; a parameter tuned
on the same history it is judged against would be a backtest result presented as a measurement.

Each theme also publishes `biggest_players`: its largest members by market capitalization with
their exposure and role, ranked by size rather than by the exposure leaderboard, because the
companies most identified with a trend are frequently not the ones the evidence ranks first.

### Re-ranking one screen, and hiding what you own

The theme screen can re-run itself: a button dispatches a refresh whose `focus_symbols` are
exactly the companies that screen scored (`theme_screen.by_ticker`), and the pipeline then polls
and re-ranks that set alone — every other name carries its last published row forward. Focus
symbols also take the front of the statement-enrichment queue, since a re-ranking request that
gave its statement budget to yesterday's leaders would return the ranking it was asked to
revisit. This is deliberately *not* routed through `ADVISOR_PORTFOLIO_SYMBOLS`, the pre-existing
way to force a symbol into a refresh: that list means "the user owns this" and feeds portfolio
coverage and the theme layer's "Your holding" tag, so re-ranking a screen through it would
relabel every name on it.

A "hide my holdings" toggle filters the ranked lists client-side. It deliberately does **not**
touch a theme's trend evaluation: breadth, leadership concentration and crowding are properties
of the whole group, and recomputing them over the subset one reader chose to hide would report a
different theme under the same name.

### Why each company is on the list

Every published row carries a `why`: an ordered list of clauses generated by
`themes.explain_exposure` from the same scoring result the row publishes, so the explanation
cannot drift from the score. The order is what a sceptical reader needs — how the company
entered the section (published leader / holding / peer-group neighbour), its role in the chain,
what its **own** filings said with the reading stated (`"its latest 10-K devotes 96% more of its
language to this theme than the prior year's"`, `"42% of its reported revenue comes from the
theme's segment"`), which readings are theme-wide and therefore *not* about it, what flagged it
if it is ineligible, and how much of the theme's declared signal weight actually resolved. A row
whose own signals all missed says so outright rather than implying confirmation. "2 leading
signals" tells a reader nothing they can check; the point of publishing evidence is that they
can disagree with it.

### Ranking within a theme group — the opportunity score

Rows within a theme's leaders/sector-connected groups are ordered by an `opportunity_score`
(`pipeline/themes.py`): `exposure_score·0.45 + fundamental_score·0.35 + cheapness·0.20`, where
`cheapness` is a peer-group valuation **tier midpoint** (16.7 / 50 / 83.3), not a true
percentile — the UI renders it as a tier for this reason rather than implying a precision the
number doesn't have. The top 5 rows in each group also carry a `rank_reason`
(`themes.explain_rank`): which of the three legs separated a row from the one directly below it,
stated honestly even when the widest gap runs *against* the row (e.g. "ranks above EME despite
losing to it on valuation"), and what the business-quality leg rests on when statement data is
missing. Rows beyond the top 5 are not decomposed this way. A per-signal `DotPlot` chart on the
Leaders group (gated on more than one resolved signal) shows each declared signal's **mean
resolved score across the group's leaders only** — never averaged in unscreened sector-peer
candidates, which would let noise drag the reading around — answering "which of this theme's
declared signals is actually carrying the ranking," a question the signal-count alone can't
answer.

### Inside information — `/screens/inside-information`

`pipeline/build_inside_information_screen.py`. Despite the name, this merges two
**already-published** screens — institutional 13F and Congressional STOCK Act trading — into one
ranked view, filtered to only the subset each upstream screen already flagged as statistically
notable: institutional cluster accumulation/distribution, or an extraordinary, cluster, or
buy-sell-flip Congressional trade. It performs no new fetch and no new scoring math; it reuses
`political_institutional.rank_disclosed_trades` (previously a backtest-only function), whose
combined score is `political_points + institutional_points` at native scale — political points
from `congress_signal.score_congressional_buying` (capped at 4.0), institutional points from the
13F `undecayed_magnitude` times its own lag-decay function (clamped to [-2.0, +3.0]). Point-in-time
visibility gating applies here too: only rows visible as of their disclosure/filing date are
used, never transaction date, to prevent lookahead. Runs every 3 days
(`.github/workflows/inside-information.yml`); reachable from a Home dashboard card, not the
primary screens nav. It carries the same evidentiary caveats as its two source screens (§10.2,
§1's 13F-filing-lag note) plus one of its own: this is a filtered union, not an independently
validated signal.

This is unrelated to the SEC filing-tracking modifiers (DEF 14A/8-K/10-K/10-Q, §8) added in the
same commit — those feed the champion research score directly and have no page of their own;
"inside information" here refers only to the institutional-plus-Congressional merge.

### Backtest comparison — `/screens/backtests`

`pipeline/build_backtest_comparison.py`. A meta-comparison view that normalizes and lays every
backtest result file in the repo side by side — 13 methods across three families (held
portfolio, options trades, pure ranking quality) — rather than computing anything new itself; it
only reads already-written result files. Because "success rate" means three different things
depending on the method, every row is tagged with one of three bases and a comparable-group so
sorting only ever happens within like-for-like methods: `rebalance_periods_positive` (share of
held rebalance periods that were profitable — held-portfolio methods, including the champion
research score rebalanced monthly, the swing screen traded as a weekly-rebalanced book, and the
emerging-growth and political/institutional strategies), `trades_profitable` (share of individual
option trades that closed green — the 9 options-strategy backtests), and
`periods_with_positive_ic` (share of periods where the swing composite's rank correlated
positively with forward returns — a ranking diagnostic, not a portfolio return, kept separate
from the swing screen traded as a portfolio). A "feature rollup" averages success rates across
methods sharing a declared input and is explicitly labeled co-occurrence, not causal attribution.
A source file that's missing or unreadable is published as a `status: "unavailable"` row rather
than silently omitted.

---

## 15. Options screens — ranking weights per strategy

All options screens are opt-in (gated behind `ENABLE_MULTIDAY_OPTIONS_SCREEN` /
`ENABLE_ADVANCED_OPTIONS_SCREEN` — an extra options-chain fetch per ticker). Every screen is
explicitly a **research screen, not a trade instruction** — nothing in this codebase places
option orders or talks to a brokerage. `build_options_strategies.py` fetches one option chain
per ticker and derives the multi-day, covered-call, and cash-secured-put screens from it
(previously three redundant fetches); Protective put, Collar, Vertical spread, and Advanced
strategies each still fetch independently.

| Route | Mechanism | Window | Weights |
|---|---|---|---|
| `/screens/options` (Multi-day) | Buy call or put, near-the-money, trend-directional | 2–14 days (target 7) | `iv_value` 25%, `liquidity` 35%, `trend_strength` 25%, `news_sentiment` 8%, `research_confidence` 7% |
| `/screens/options/short-term-trades` | Whichever of buy-call/buy-put/sell-covered-call/sell-cash-secured-put ranks highest *within its own mechanism's cross-sectional population* — one idea per ticker | 1–14 days | Reuses each mechanism's own weights above |
| `/screens/options/covered-call` | Sell a covered call against a long position | Shared 1–14 day window | `expected_value_pct` 38%, `liquidity` 25%, `cushion` 21%, `research_confidence` 10%, `news_sentiment` 6% |
| `/screens/options/cash-secured-put` | Sell a cash-secured put | Shared 1–14 day window | `expected_value_pct` 33%, `probability_otm` 25%, `liquidity` 25%, `research_confidence` 10%, `news_sentiment` 7% |
| `/screens/options/protective-put` | Buy a protective put against a long position | Independent window | `liquidity` 33%, `iv_value` 28%, `cost_efficiency` 26%, `research_confidence` 8%, `news_sentiment` 5% |
| `/screens/options/collar` | Long stock + protective put + covered call | Independent window | `cost_efficiency` 35%, `range_width` 26%, `liquidity` 26%, `research_confidence` 8%, `news_sentiment` 5% |
| `/screens/options/vertical-spread` | Directional call or put spread | Independent window | `risk_reward` 34%, `liquidity` 26%, `trend_strength` 25%, `news_sentiment` 8%, `research_confidence` 7% |
| `/screens/options/advanced-strategies` — iron condor | Sell call spread + sell put spread (range-bound income) | 15–45 days | `credit_efficiency` 34%, `probability_in_range` 30%, `liquidity` 21%, remainder split across sentiment/confidence-style terms |
| `/screens/options/advanced-strategies` — straddle | Buy call + buy put, same near-the-money strike (cheap-volatility, big-move bet) | 15–45 days (shared with iron condor, not catalyst-timed — no earnings-calendar source is wired in, so straddle candidates are best read as "cheap relative-volatility ideas," IV/RV ratio < 1, not catalyst plays) | `probability_of_profit` 31%, `liquidity` 31%, `iv_value` 25%, `news_sentiment` 8%, `research_confidence` 5% |

`news_sentiment`/`research_confidence` in every directional screen are **sign-aligned** with
the chosen side (call=+1, put=−1): agreement with the trade's own direction is treated as a
conviction-confirmation signal, not an independent one — this is a smaller, differently-scoped
role for sentiment than the 4%-of-research-score component in §6.

---

## 16. Portfolio, planning, and finances screens

Requires sign-in (Firebase Auth); Firestore holds portfolio, transaction, snapshot, pool, goal,
preference, and alert-rule data.

### `/portfolio` — three views on one page (`src/pages/Portfolio.jsx`, `view` prop)

- **`/portfolio` (Summary, default)** — Holdings table, performance vs. benchmark, uninvested
  cash by account, and (in an expandable "Data actions" panel) manual refresh/re-scoring
  controls. Position-level detail includes recent return sparkline and stop-loss distance where
  configured.
- **`/portfolio/performance`** — a single benchmark-comparison chart (time-weighted return vs.
  the selected benchmark, indexed-to-100 growth) plus an expandable "opportunity cost"
  comparison: actual holdings vs. the same cost basis held in the S&P 500 instead, vs. the same
  cost basis held flat in cash, each dated from every position's own recorded purchase date.
  Always reads full holdings history, unaffected by the Data overview scope selector below.
- **`/portfolio/data-overview`** — the full quantitative-evidence panel: a move-attribution
  explanation of the portfolio's recent move vs. the S&P 500 (`portfolioAttribution.js`), the
  scenario sensitivity panel (below), and the complete performance-metrics suite (Sharpe,
  Sortino, drawdown, factor exposure, capture ratios, Monte Carlo, and more), evaluated over a
  selectable analytics scope. By far the most expensive derivation on the page — it's computed
  only when this view is active, not on Summary or Performance.

**Scenario sensitivity** (Data overview only): a book-level projection (`pipeline/stress_scenarios.py`
— named historical windows: 2008 GFC, COVID 2020, the 2022 rate-hike drawdown; plus hypothetical
parametric shocks, a −30% SPY move and a +200bp rate shock) is joined against each holding's own
published equity beta to rank which holdings would take the largest hit under each scenario, then
rolled up into a value-weighted whole-portfolio estimate (`src/lib/scenarioSensitivity.js`,
`ScenarioSensitivityPanel.jsx`). The hypothetical rate shock is excluded from the per-holding
view since no per-holding rate beta is published to project a basis-point shock through an
equity beta — only the market-shock scenarios get a holdings breakdown.

### `/portfolio/diversification` — Concentration, correlation, factor and theme exposure

`src/pages/Diversification.jsx`, backed by portfolio-weight math from `APP-COMPLETE-BREAKDOWN.md`'s
"Portfolio concentration and risk" section:

- **Concentration**: `HHI = Σ(weight_i²)`, `effective holdings = 1 / HHI`. Section: "Position
  concentration — Holdings by allocation."
- **Correlation**: pairwise correlation matrix from up to 252 trailing daily returns, requires
  ≥60 common observations. Section: "Trailing daily returns — Pairwise correlation matrix."
- **Risk decomposition**: the covariance matrix produces marginal and percent contribution to
  portfolio risk (percent contributions reconcile to 100%); **effective bets** are the
  reciprocal concentration of eigenvalues of the weighted correlation matrix; the
  **diversification ratio** is weighted standalone volatility ÷ portfolio volatility. Section:
  "Covariance decomposition — What carries the risk."
- **Look-through**: ETF holdings are decomposed using published sector weights and top
  holdings, exposing overlap between direct positions and ETF constituents; unresolved
  exposure is shown explicitly with its dollar value rather than silently dropped.
- **Factor exposure**: monthly portfolio excess returns regressed (OLS) against the Kenneth R.
  French five factors plus momentum (market, size, value, profitability, investment,
  momentum) — refreshed monthly from the French Data Library. Requires ≥24 monthly
  observations; publishes loadings, standard errors, annualized alpha, alpha t-statistic,
  R². An alpha t-statistic under 2 in absolute value is labeled statistically meaningless (the
  same honesty standard as §9's model-level validation). Section: "Five factors plus momentum
  — Portfolio factor exposure."
- **Theme exposure**: aggregated separately by portfolio weight, reusing the same
  `theme_exposure_score` as §14.1, and **never enters the research score**. Section:
  "Independent lens — Theme exposure."
- **Historical expected shortfall**: worst 5% of daily portfolio returns. **Tracking error**
  vs. the selected benchmark. **Active share** appears only when benchmark constituent
  weights exist and portfolio look-through coverage reaches 80%.

### `/portfolio/insights` — Tracked activity and behavioral insights

`src/pages/Insights.jsx`. "You vs. [benchmark]" (same-dollar comparison), "Holdings vs.
[benchmark]" since each position's purchase date, trading-behavior stats ("As a trader"),
purchase-timing analysis, and milestone tracking.

### `/finances` — Income, spending, pools, accounts

Income, spending, savings "pools," linked accounts, and contribution-room tracking (e.g.
tax-advantaged account limits). Goals reuse this same pool structure and feed the Planning
probability engine below.

### `/planning` — Retirement and goal probability simulator

Leads with **the probability that a balance survives to the target age** under the configured
withdrawal assumption; gauge verdict bands are config-driven, not hardcoded. Live levers
(annual return target, monthly contribution, retirement age, real annual withdrawal, allocation
aggressiveness) resimulate in a Web Worker within a 400ms interaction budget.

**Engine**: a 5,000-path block-bootstrap simulation with 12-month blocks publishes the 10th /
25th / 50th / 75th / 90th percentile paths on a touch/pointer-scrubbable fan chart (dotted
line = projected). What feeds the bootstrap depends on how much of the user's own history is
available, checked in this order (`src/lib/projectionEngine.js::selectProjectionReturnSource`):

1. **≥20 daily portfolio returns since the live-tracking start** (`performance_minimum_observations:
   20`, `portfolio_analytics.performance_minimum_observations`) — the same gate and the same
   since-live-tracking window (`LIVE_TRACKING_START`) the Portfolio Overview panel's own
   Sharpe/Sortino/Calmar tile uses. Above this gate the engine switches to a **parametrically
   calibrated** return source instead of resampling observed history.
   `src/lib/monteCarloRiskProfile.js` derives a risk profile — annualized return, Sortino-implied
   downside volatility, Sharpe-implied upside volatility, all computed with the same risk-free
   rate (`portfolio_analytics.risk_free_series`) and formulas as the Overview tile — and
   `parametricMonthlyReturns()` draws `parametric_calibration.synthetic_months` (600, i.e. 50
   years) of synthetic monthly returns from a two-piece (asymmetric) normal distribution in
   log-return space: a different standard deviation above versus below the mean, centered on the
   risk profile's annualized return and bias-corrected for that asymmetry. Downside volatility is
   floored at `minimum_annual_volatility_pct` (3.0% annualized) and upside volatility is floored
   at `upside_volatility_floor_ratio` (30%) of that downside figure, so a short or lucky track
   record can't collapse the fan chart into a falsely narrow, falsely confident band. These
   synthetic months then feed the *same* 12-month block bootstrap used by every tier below — the
   parametric mode changes only the input return series, never the resampling mechanic. The
   calibration itself runs on the main thread (not inside the Web Worker, which only runs the
   block-bootstrap path simulation once the return source is decided) and is cached in Firestore
   at `portfolios/{uid}/planning/monteCarloRiskProfile`, refreshed weekly at Friday 4pm
   America/New_York market close or immediately on new deposit-like activity, whichever comes
   first (`parametric_calibration.refresh_weekday/refresh_hour/refresh_timezone`,
   `src/lib/marketCalendar.js`, `src/lib/usePortfolioMonteCarloCalibration.js`). There is no
   server-side job computing it — a signed-in user's own browser recalculates and re-caches it.
2. **Fewer than 20 daily observations but at least 36 months (`portfolio_minimum_history_months`)
   of monthly portfolio history** — the bootstrap draws directly from the user's own observed
   monthly returns.
3. **Under 36 months of history** — the engine instead samples the selected benchmark's long
   history — preserving volatility and return ordering, never repeating or synthesizing observed
   months — before recentering on the selected target.

The dotted median centers on an adjustable annual return target (default 15%) — a supplied
brokerage snapshot (e.g. Fidelity) sets an evidence-based slider range from its year-to-date and
trailing one-year returns, but the *saved target*, not the brokerage return, controls the actual
projection center. Retirement can begin one configured year after the current age (not
artificially floored at 50).

This retirement/goal simulation is unrelated to `pipeline/monte_carlo_projection.py`, a separate
server-side block-bootstrap (10,000 paths, 21-day blocks) over the scoring strategy's own
backtest-plus-live-shadow returns that publishes `public/data/validation/monte_carlo_projection.json`
for `/screens/validation` (§9, §14). The two share no code, no config, and no Firestore document —
"Monte Carlo" names two independent simulations in this app.

Goals (from `/finances`) use the identical probability engine — retirement is the default
goal, not a separately-implemented calculation path.

---

## 17. Remaining routes

| Route | Purpose |
|---|---|
| `/` | Home / Financial Report — portfolio value, daily change, Planning success probability, action-needed count, plus the MarketPulse preview (§11) and focused screen cards |
| `/research` | Stock and ETF research library — the research score (§3) and ETF composite (§10.6) in one browsable/filterable library |
| `/search` | Cross-dataset ticker/company discovery across portfolio, published research, watchlist, and the covered universe |
| `/market` | MarketPulse news feed — company news/sentiment plus filing labels; see §11. Explicitly framed as "supporting evidence – not a substitute for earnings, cash flow, or balance-sheet quality" |
| `/markets` | Live market-data dashboard — index performance (SPY/QQQ/DIA/IWM), sector and stock daily leaders/laggards, and a ticker/company lookup. Descriptive only: no score, no ranking model, no weights. Distinct from `/market` (the news reader) |
| `/watchlist` | §10.8 — watchlist quality score and setup-aware guidance |
| `/methodology` | Plain-language explanation of the research score, reading live weights from `advisor.json.methodology` so it cannot drift from the config that actually produced them |
| `/glossary` | Product and model terminology reference |
| `/settings` | Theme, motion, privacy, benchmark, and planning preferences |
| `/alerts` | Signed-in alert rules (capped per user) and delivery/event history |

`/hud-demo` is not a real feature and is intentionally excluded from the table above — it's an
unlinked, internal component showcase (`src/pages/HUDDemo.jsx`, header comment: "HUD Demo Page -
Phase 2 Showcase") for HUD-styled visual widgets, driven by `Math.random()`-perturbed local state
rather than any published data. It has a route (reachable only by typing the URL directly) but no
nav entry anywhere in the app.

---

*Source of truth for every figure above is the live config and code, not this document. If a
weight changes in `settings.json`, `universe.json`, or the scoring modules, this file needs a
manual refresh — regenerate `docs/FEATURE-REGISTRY.md`'s machine-readable counterpart with
`python pipeline/build_feature_registry.py` and re-derive the compounded percentages in §3 if any
top-level or category weight moves. Route-level detail in §14–§17 is cross-checked against
`APP-COMPLETE-BREAKDOWN.md` (regenerable via `scripts/generate-app-breakdown.mjs`) and the
route table in `src/App.jsx` — re-verify against those if a screen is added, renamed, or
re-weighted.*
