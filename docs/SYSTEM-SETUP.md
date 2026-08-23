# System Setup — ValueSignal / Dash

An in-depth description of what this system actually is and does, as of commit `c485cc5`
(2026-08-07). Written to be read by someone who has never seen the repo and needs to reason
about the algorithm without reading 40k lines of Python.

Where this document states a number, it was measured from the committed artifacts in this tree,
not copied from another document. Where the implementation and the documentation disagree, this
file follows the implementation and says so.

Companion documents: `docs/CONSOLIDATED-ASSESSMENT.md` (the reconciled rating and the sequenced
plan — start here), `docs/ALGORITHM-RATING-2026-08-07.md` (what's working and what isn't),
`docs/RESEARCH-PROMPT.md` (the open research questions), `docs/FEEDBACK-SOURCE-CONSOLIDATED.md`
(the design-level review that fed the reconciliation), `docs/LIMITATIONS.md` (the repo's own
honest gap list).

---

## 1. What the system is

A static React dashboard served from committed JSON, backed by a Python batch pipeline that runs
on GitHub Actions three times a trading day. The pipeline ranks a configured 910-name US equity
universe by a 0–100 "research score" and publishes the top 40, plus a 374-name screen universe,
a separately-modelled 126-fund ETF watchlist, and a set of thematic and factor screens.

There is no server, no database, and no query API. `public/data/advisor.json` (roughly 400k lines)
is the product. The browser fetches it as a static asset. Firebase provides auth, the user's
portfolio, and the watchlist; everything else is precomputed.

The score is explicitly **not** a return forecast. `docs/MODEL-CARD.md` calls it "a cross-sectional
rank of companies by evidence quality." That framing matters for how it should be judged, and it
is the framing this document uses.

---

## 2. Repository topology

```
pipeline/                Python batch pipeline — the algorithm lives here
  config/                All tunable knobs (18 JSON files, settings.json is 36 KB)
  sleeves/               Independently testable alpha ideas (3 of 14 built)
  themes/                Growth-chain declarations (11 YAML present)
  validation/            IC harness
  schemas/               JSON Schema draft 2020-12 contracts for every published artifact
  tests/                 ~100 test modules
  pit_store/             Point-in-time observation log (JSONL, 2 days)
  shadow_store/          Shadow strategy NAV history (4 strategies, 5 days)
  reports/               Diagnostic artifacts (stability, normalization, bias, signal diff)
src/                     React app — components, pages, lib (client-side portfolio math)
netlify/functions/       3 server-side functions (refresh dispatch, prices, alert push)
public/data/             The published product: advisor.json, etf data, news
.github/workflows/       5 workflows; refresh-advisor.yml is the one that matters
docs/                    22 design/audit/contract documents
```

Root-level `*.md` files (`ACTION-PLAN.md`, `UPGRADE-REPORT*.md`, `V2-*.md`, `PLATFORM_DESIGN_REVIEW.md`,
etc.) are historical snapshots from earlier phases. Several are explicitly stale — `PLATFORM_DESIGN_REVIEW.md`
carries its own "historical snapshot, not current status" banner. Treat `docs/` as authoritative
and the root files as archaeology.

---

## 3. Data sources

| Source | What it supplies | Constraint |
|---|---|---|
| **Yahoo Finance** | Full-universe quotes, price history, financial statements | Unofficial API; the deep-fundamentals backbone. No as-reported history — restated statements only |
| **Alpha Vantage** | Company overview, earnings, insider transactions, macro | Free tier: 25 calls/day, 1 req/sec. Hard-capped at **5 symbols** per refresh (`ALPHA_ENRICH_LIMIT`) |
| **Marketaux** | Entity-level news sentiment | Scoped to the Alpha-enrich shortlist plus a discovery feed |
| **FRED** | Six macro series → a sector-sensitive regime modifier | Raw observations never published or cached |
| **SEC EDGAR** | Form 4 insider transactions, theme signals from filings | Requires `SEC_USER_AGENT`; **currently unset, so this layer is dark** |
| **Financial Modeling Prep** | Congressional disclosures (optional: needs a plan covering the Congressional endpoints, and adds the price-performance column) | Weekly, separate workflow |
| **Senate eFD** | Senate STOCK Act disclosures, keyless and authoritative; electronically filed periodic transaction reports only (paper filings are scanned PDFs with no machine-readable trades) | Weekly, same workflow |
| **House/Senate stock-watcher datasets** | Congressional disclosures, keyless — **withdrawn: both buckets now answer HTTP 403 AccessDenied.** Point `CONGRESS_HOUSE_DATASET_URL` / `CONGRESS_SENATE_DATASET_URL` at a live mirror to restore House coverage | Weekly, same workflow |
| **OpenFIGI** | CUSIP → ticker for 13F holdings. Keyless works but caps a request at **10** CUSIPs (a key raises it to 100); answers are cached in `pipeline/data/institutional_13f/cusip_tickers.json` | Monthly, 13F workflow |
| **Marketstack** | Pre-market screens | Separate workflow |

The client enforces 1.1s between uncached Alpha Vantage requests. Raw provider responses are cached
locally with atomic writes, TTLs, stale-on-error fallback, and provenance envelopes; they are never
published. Cache validity is keyed on **fetch age**, not on source effective date, filing revision,
or corporate action.

---

## 4. The refresh pipeline, stage by stage

`pipeline/fetch_advisor.py::run()` is the orchestrator. The full sweep:

```
1.  Load universe (910 symbols) + portfolio symbols (21)
2.  Batch-fetch quotes and price history from Yahoo         → ~910 contexts
3.  Fetch news (Marketaux discovery feed)
4.  PRELIMINARY SCORE every context on shallow metrics only
5.  Sort by preliminary score
6.  select_enrichment_priority():
       20 incumbents (previous published top)
     +  5 challengers (best non-incumbents by preliminary rank)
     +  20 rotation slice (statement-starved names, theme-flagged ones first, then
        oldest-unenriched -- see enrichment_rotation)
     + 140 non-financial/non-real-estate expansion slice (never-enriched names,
        theme-flagged ones first -- see enrichment_expansion)
     + 130 financial/real-estate expansion slice (bank/insurer/REIT profiles only,
        same never-enriched, theme-first ordering -- see
        enrichment_expansion_financial_real_estate)
     +  portfolio symbols
     → priority queue, then fill to extended_limit = 400
7.  enrich(): multi-request financial-statement fetch for the shortlist only
       → derives ~15 statement metrics (EV/EBITDA, ROIC, Altman Z, Piotroski, ...)
8.  Alpha Vantage enrichment for up to 5 symbols on weekday intraday refreshes, up to
       25 (its free-tier daily ceiling) on the once-daily weekend refresh
9.  SEC Form 4 insider scoring for the shortlist (currently no-op)
10. FRED macro regime
11. FINAL SCORE with full metric set
12. Apply bounded modifiers
13. Build v2 shadow analysis + v2 shadow recommendation + 5 challenger score variants
14. Rank, publish top 40 + 374-name screen universe + portfolio coverage
15. Theme layer, ETF comparisons, run manifest, PIT store append, shadow store append
16. validate_data.py → JSON Schema + contract checks
17. Commit the JSON back to main
```

### 4.1 The structural consequence of stages 4–7

This is the single most important architectural fact about the algorithm, and it is not stated in
the README.

**The metrics that carry most of the model's weight are only computed for names that a thinner
model already ranked highly.**

The final score is 78% fundamentals, and within fundamentals the heaviest metrics (EV/EBITDA at 27%
of valuation, ROIC at 26% of profitability, interest coverage at 30% of financial health, Piotroski
F at 45% of accounting quality) all require financial statements. Statements are only fetched for
the top 150 of 910, and that top 150 is chosen by a preliminary score computed **without** those
statements — on trailing P/E, price-to-book, price-to-sales, margins, and price behavior.

Two consequences follow:

- **Selection bootstrapping.** A company with an unattractive trailing multiple but excellent
  returns on capital, a fortress balance sheet, and clean accruals cannot surface. It never enters
  the shortlist, so its best metrics are never computed, so it never scores well. The full model is
  only ever applied to candidates pre-filtered by a materially different and weaker model.
- **Incumbency.** `select_enrichment_priority()` seeds the queue with the previous refresh's top 20
  and admits only 5 new challengers per refresh. Today's ranking is partly a function of yesterday's
  ranking rather than of today's evidence.

Measured effect in the current published data: `capital_allocation` and `accounting_quality` are
scored for **84 of 374** names in the screen universe. Those two categories are 20% of the stated
fundamental weight. For the other 290 names that weight is silently redistributed across the
remaining categories by the within-category reweighting rule, so most of the universe is ranked by
a different effective model than the documented one.

### 4.2 Refresh modes

| Mode | Trigger | Scope |
|---|---|---|
| `full-alpha` | 07:00 ET weekdays | All 910 names, spends Alpha Vantage quota |
| `data-only` | 12:00 and 15:00 ET weekdays | Prior top 100 + portfolio/watchlist symbols; other names carried forward |
| `rescore-only` | Manual | Re-runs scoring over the last `advisor.json` with zero network calls |

Cron fires at UTC times covering both EDT and EST, then gates on `America/New_York` so DST does not
shift the local schedule. Concurrency group `scheduled-data-push-main`, three push retries,
90-minute timeout. Authenticated users can dispatch a `data-only` run from the Overview page via
`netlify/functions/refresh-data.mjs`, which verifies a Firebase ID token server-side and refuses
duplicate runs.

---

## 5. The scoring model

### 5.1 Composite

```
raw_score  = 0.78 · fundamentals + 0.18 · market_behavior + 0.04 · news_sentiment
             (each component reweighted by its own coverage)
base_score = coverage-shrunk raw_score
score      = base_score + Σ modifiers        (modifiers hard-capped at ±15)
```

Implemented in `advisor_engine.py::build_research()` → `blend_research_components()` →
`apply_modifiers()`. Weights live in `settings.json ranking_weights`.

**Measured realized influence** (tie-aware Spearman against the final score, 374-name screen
universe, single refresh): fundamentals **+0.944**, market behavior **+0.226**, news **+0.078**.
The stated weights are the operative weights — this is the part of the system that most clearly
does what it says. Fundamentals and market behavior are near-orthogonal (Spearman **+0.011**), so
the market sleeve genuinely adds independent information rather than restating the fundamental view.

### 5.2 Fundamentals (78% of composite)

Category weights (`settings.json fundamentals.category_weights`) and, inside each, metric weights
(`fundamentals.metric_weights`):

| Category | Weight | Metrics (weight within category) |
|---|---:|---|
| **Valuation** | 28% | ev_to_ebitda 0.27, ev_to_fcf 0.18, forward_pe 0.15, ev_to_ebit 0.12, peg 0.09, sales_multiple 0.09, price_to_book 0.05, price_to_tangible_book 0.05 |
| **Profitability** | 26% | roic 0.26, gross_profits_to_assets 0.22, fcf_yield 0.16, cash_conversion 0.16, roe 0.10, profit_margin 0.10 |
| **Financial health** | 15% | interest_coverage 0.30, net_debt_to_ebitda 0.24, debt_to_equity 0.18, altman_z 0.18, current_ratio 0.10 |
| **Growth** | 11% | revenue_growth 0.26, fcf_growth_3y 0.22, earnings_growth 0.20, operating_margin_trend 0.16, earnings_surprise 0.16 |
| **Capital allocation** | 10% | net_buyback_yield 0.34, stock_comp_to_revenue 0.28, asset_growth 0.22, capex_to_depreciation 0.16 |
| **Accounting quality** | 10% | piotroski_f 0.45, accruals_ratio 0.22, dso_trend 0.17, inventory_days_trend 0.16 |

Sector awareness is real, not cosmetic: `forward_pe_by_sector` and `price_to_sales_by_sector` carry
per-sector bands; Altman Z is computed with the variant fitted for the filer's sector and suppressed
entirely for financials; price-to-tangible-book is scored only in sectors it describes.

Measured category influence on the final ranking: valuation **+0.440**, profitability **+0.398**,
financial health **+0.359**, accounting quality **+0.355**, capital allocation **+0.240**, growth
**+0.221**. The ordering broadly tracks the stated weights.

### 5.3 Band scoring — the core mechanic, and its cost

Every metric is mapped to 0–100 through **discrete threshold bands**, not a continuous transform.
`scorer.py:90–157` implements five variants: `band_score`, `higher_is_better_score`,
`lower_is_better_score`, `range_score` (ideal/acceptable windows), and `multiple_score`
(cheap/healthy/elevated/expensive, with a `suspicious_below` value-trap trip).

This is `normalization_mode: "bands"`, the production champion, named `bands_champion`.

The tradeoff: bands are interpretable and stable against outliers, but they discard cross-sectional
information. Two companies at 8.1× and 14.9× EV/EBITDA can score identically if both sit in the same
band, while 14.9× and 15.1× can differ by several points. A name near a band edge flips on a trivial
input change. This is the leading hypothesis for the backtest's **64.9% monthly turnover and 36%
month-over-month name retention** — a 78%-fundamentals model reading quarterly-updating inputs
should not replace two-thirds of its holdings every month.

The alternative is already in the repo: `CrossSectionalNormalizer` (`scorer.py:296`) with
`normalization_mode: "cross_sectional"`, running as a shadow challenger.

### 5.4 Market behavior (18% of composite)

`settings.json market_behavior.weights`, computed in `advisor_engine.py::technical_factors()`:

| Factor | Weight | Note |
|---|---:|---|
| momentum_12_1 | 0.30 | 12-month return skipping the most recent month (Jegadeesh–Titman) |
| risk_adjusted | 0.26 | Sortino and Sharpe on the stock's own returns, shared `risk_metrics` code with the ETF model |
| relative_strength | 0.16 | 20-day vs SPY |
| drawdown_resilience | 0.14 | 1-year maximum drawdown |
| volume_confirmation | 0.08 | |
| low_beta | 0.06 | Rewards defensive names (betting-against-beta) rather than penalizing volatility with a constant |
| technical_extended | 0.06 | MA slope, RSI, Bollinger %B, OBV slope — deliberately ~1% of the total composite |

### 5.5 News sentiment (4% of composite)

7-day window, 3-day recency half-life, entity-confidence filtering, title-similarity dedup at 0.82,
source-quality tiers (regulatory 1.5× / established press 1.2× / aggregator 0.65×), filing-vs-
commentary weighting at 1.35× / 1.0×.

**Currently inert.** 373 of 374 scored names sit at the neutral 50.0. Marketaux coverage is scoped
to the five-symbol Alpha shortlist, so 4% of the model is decorative in production.

### 5.6 Modifiers (post-blend, capped at ±15 combined)

| Modifier | Range | Basis |
|---|---|---|
| `sector_valuation_percentile` | ±3 | Valuation percentile against sector peers |
| `short_interest` | up to −6 | Float % (8% warn / 15% severe) and days-to-cover |
| `insider_activity` | +5 / −3 | Form 4 open-market trades, routine-vs-opportunistic split per Cohen–Malloy–Pomorski (JF 2012). Routine calendar-scheduled trades score zero. Cluster bonus for independent buyers. **Currently scoring 0 symbols** |
| `liquidity` | −3 | Below $25M thin, below $5M illiquid |
| `expectations` | ±3 | Analyst target upside and consensus rating |
| `macro_regime` | ±3 | FRED six-series regime, weighted per sector (e.g. Financials 55% yield-curve, Real Estate 55% rates) |

### 5.7 Coverage and confidence

Missing metrics are **reweighted within their category**, never imputed to neutral. Metrics that do
not apply to a sector leave the coverage denominator rather than counting as missing evidence
(`applicability_matrix.json`). Residual missing coverage then shrinks the final confidence.

`pipeline/confidence.py` publishes a decomposition alongside the scalar: completeness, freshness,
source_reliability, peer_sample, model_agreement, historical_calibration.
`historical_calibration` is **always null** — it requires 24 eligible IC periods and none exist.

Current published state: coverage **0.69–0.98**, confidence **0.70–0.89**. Both recovered from a
severe collapse (0.21–0.35 and 0.39–0.48) caused by a statement-fetch bug fixed at `688c08a`.

---

## 6. Champion / challenger governance

**Champion:** `bands_champion` — in production, and the only score the UI shows.

**Challengers**, all shadow-only, published per-row in `score_variants`:
`cross_sectional_normalization`, and the `signal_corrections` family (`normalization`,
`short_horizon`, `confidence_shrinkage`, `modifier_recalibration`, and a cumulative variant).

**No promotion has ever occurred**, and none has been evaluated against the gates in
`docs/RESEARCH-CONTRACT.md`, because the IC harness has not reached minimum history.

There is a parallel **v2 canonical stack** — `analysis_v2` (canonical metrics + applicability +
provider reconciliation) and `recommendation_v2` (a two-axis company/position decision matrix with
confidence gates and a thesis-break namespace). It is architecturally the safer path and it is
shadow-only. On the current published rows the v2 structural score and the champion score agree at
Spearman **+0.451** — they are genuinely different models.

> **Bug:** `pipeline/observability.py:30` builds `run_manifest.score_distribution` from the v2
> shadow `effective_score`, not the published champion `score`. The manifest reports 60.0–77.8
> while the published scores are 71.4–83.4. The release manifest currently certifies a model that
> is not in production, and `docs/BASELINE-2026-08-06.md` diagnosed rank churn from this field.

---

## 7. Screens, sleeves, and presets

**Sleeves** (`pipeline/sleeves/`) wrap one independently testable alpha idea behind a common return
shape — `raw_features`, `normalized_features`, `subscores`, `raw_score`, `confidence`, `eligibility`,
`warnings`, `explanation`, `as_of`, `config_hash`. ETFs are structurally ineligible for stock
sleeves (reason code `unsupported_security_type`).

**3 of 14 built**: value, quality, growth. The other 11 (short/long reversal, mean reversion, GARP,
catalyst, dividend, low-volatility, trend, insider/political, multi-factor composite, momentum as a
formal sleeve) are not built.

**Screen presets** (`pipeline/config/screen_presets.json`): all 16 declared, **7 wired**:

| Wired | Implementation |
|---|---|
| Deep Value | `sleeves/value.py` |
| Quality Value | `sleeves/value.py` + `quality.py` |
| Momentum Leaders | `research_screens_v2.py momentum_scores()` |
| Oversold Reversal | `src/lib/researchScreens.js rankReversal()` — client-side |
| Durable Growth | `sleeves/growth.py` |
| Insider Cluster Buying | `insider_signal.py` |
| Congressional Disclosure Activity | `build_congress_screen.py` |

**9 specification-only**: Emerging Momentum, High-Quality Recovery, Mean-Reversion Setup, GARP,
Shareholder Yield, Defensive Compounders, Trend Following, Earnings Revision Leaders, Balanced
Multi-Factor. Each declares `implementation_status` honestly.

Eligibility gates enforced in the momentum screen: $5 minimum price, $300M minimum market cap, $2M
minimum 60-day median dollar volume, 253 minimum trading sessions. No IPO-seasoning window, no
delisted-security replay.

---

## 8. Adjacent models

**ETFs** (`fetch_etfs.py`, 126 funds). Entirely separate model: performance, risk, total cost of
ownership, liquidity, structure. Percentiles are computed **within peer groups** (broad equity,
sector, thematic, fixed income, commodity, crypto) rather than across the batch. Cost includes
tracking difference against an index proxy and NAV premium/discount, not just expense ratio; where
a fund declares a Rule 6c-11 endpoint, the mandated median 30-day bid-ask spread is used instead of
an estimate. ETFs are ineligible for every stock sleeve.

**Themes** (`pipeline/themes/*.yaml`). Exposure measured from segment revenue, self-description
trend in filings, disclosed customer ties, and the capex of confirmed spenders. Two guardrails
enforced in code and re-checked by `validate_data.py`: price momentum contributes **exactly zero**,
and names already in the top valuation decile of their sector are flagged rather than promoted.
Published as an independent screen, never folded into the research score. Eleven themes ship,
each declared as a growth chain (root driver → first-order → second-order, plus the evidence
that would disconfirm it) with a role per company: AI infrastructure, automation & robotics,
grid & electrification, reshoring capacity, allied rearmament, energy security, cybersecurity,
digital payments, metabolic-care supply chain, aging demographics, and water infrastructure.

A separate `trend` block per theme (`pipeline/theme_trend.py`) answers whether the trend is
actually moving — direction, breadth above 20/50-day averages, leadership concentration,
revision confirmation, crowding, and role rotation — and resolves to one of six verdicts. It
reads price deliberately and is walled off from exposure: the block publishes
`contributes_to_exposure: false` and `validate_data` fails the run if an exposure row carries
any price field.

Two further scoping rules, both added when the single-theme screen was widened: a signal
declaring a `universe` is measured on the spenders rather than the candidate, so it describes
the demand driver but cannot confirm that any particular company is exposed; and each theme
declares both the `sectors` and the `industries` its supply chain is built by, matched against
the Yahoo classification carried on every scored row, so filing language alone cannot rank a
bank as top exposure to a hardware buildout and a sector cannot pass a trucking company off as
one. Seed tickers are always in scope, and `themes.report_scope` warns when an industry list
admits nobody. **Coverage caveat:** with no curated segment or
named-customer maps wired in and no transcript source, the only signals that resolve broadly in
production are the filing-keyword trend and the spenders' capex, so most published rows rest on
roughly a third of their theme's declared signal weight — the `confidence` field on each row
reports exactly how much answered.

**Congressional trading** (`build_congress_screen.py`, weekly). A separate screen with its own
6-factor weighting (track record 25, committee relevance 20, cluster detection 20, trade size 15,
direction/recency 10, policy catalyst 10). **Not an input to the research score.**

---

## 9. Validation and evidence infrastructure

The framework is well-specified. It has produced no results.

**`pipeline/evaluation.py`** — the promotion methodology: cross-sectional rank information
coefficient and ICIR, quantile spread and monotonicity, deflated Sharpe ratio (adjusting for the
number of configurations tried), and probability of backtest overfitting via combinatorially-
symmetric cross-validation. A change is supposed to ship only if it improves out-of-sample IC after
deflation.

**`pipeline/validation/ic_harness.py`** — the prospective harness. Requires 24 eligible periods
(`minimum_icir_periods`); has observed **0**. Computes raw forward return over **calendar-day**
horizons (30/91/182/365), not the contract's specified 63-trading-day sector-residual target. Uses
a flat 10bps cost.

**`pipeline/costs.py`** — `half_spread + fees + volatility_scaled_impact` across optimistic/base/
stress scenarios, with a square-root market-impact form and an ADV participation cap of 2%. Spread
is a **labeled proxy** (2/8/25 bps by liquidity tier) because no provider serves quoted spreads;
every result carries `spread_source: "liquidity_tiered_proxy_not_measured"`. **Not wired into the
harness.**

**`pipeline/pit_store.py`** — appends a timestamped observation of every tracked metric per run,
with restatements in a separate revision log, plus point-in-time universe membership including
departed names. Committed to git because runners are ephemeral. **Currently 2 days deep.**

**`pipeline/shadow_portfolios.py`** — 4 strategies (production, momentum, eligible-universe
equal-weight, SPY) tracked as NAV series. **5 daily observations.**

### 9.1 The two backtests

**`backtest_monthly_results.json`** — the credible one. 60 monthly rebalances, 2021-08 → 2026-07,
top 20 score-weighted, executed at the next close after signal, 10bps one-way, 860 usable names.

| | Strategy | SPY |
|---|---:|---:|
| CAGR | 11.14% | 12.80% |
| Volatility | 19.43% | 17.18% |
| Max drawdown | −27.03% | −24.50% |
| Sharpe (zero rate) | 0.644 | 0.791 |

Decomposed: beta 0.70, correlation 0.62, annualized CAPM alpha +2.99% at **t = 0.44**, residual
volatility 15.2%, tracking error 16.1%, information ratio −0.066. Turnover 64.9%/month, 397 unique
tickers through a 20-name portfolio.

Self-disclosed biases: `survivorship_bias: true` (the universe is today's candidate list),
`filing_date_approximation: true` (quarter-end + 45 days). Missing historical inputs: point-in-time
analyst estimates, historical news sentiment, actual SEC filing timestamps, pre-window quarterly
fundamentals.

**`backtest_historical_results.json`** — 52 weeks, 120-name universe, weekly re-ranking, top 20.
Reports 13.89% vs SPY 8.42%. In the same file **IWM returned 14.78%** — the strategy lost to the
size-matched benchmark, so its apparent edge over SPY is a size tilt. Should not be cited as
evidence.

---

## 10. Frontend and delivery

React + Vite (Rolldown), deployed on Netlify from the repo root, publishing `dist`. Route/vendor
splitting is configured in `vite.config.js` with explicit chunk groups for firebase-firestore,
firebase-webchannel, firebase-auth, firebase, and vendor.

~49 components, ~30 lib modules. Notable client-side logic: `researchScreens.js` (the Oversold
Reversal preset runs in the browser), `portfolioAttribution.js`, `factorAnalytics.js`,
`alertRules.js`, `dipWatch.js`, `bullBearScore.js`, `financeMigrations.js`.

Three Netlify functions: `refresh-data.mjs` (Firebase-token-gated GitHub Actions dispatch, always
`data-only`, refuses duplicates), `portfolio-prices.mjs`, `alert-push.mjs`. GitHub token and
Firebase service-account credential stay server-side.

The UI exposes provider health and marks research stale after 36 hours.

**Architectural note:** material investment logic lives on both sides. Screen ranking, portfolio
attribution, stop logic, and fallback recommendations exist in JavaScript alongside the Python
pipeline, so the platform has more than one decision authority.

---

## 11. Configuration surface

`settings.json` is 36 KB across 30 top-level sections. Every knob carries a `_comment` explaining
the reasoning, usually with an academic citation. Sections: `model`, `normalization_mode`,
`challengers`, `short_horizon_treatment`, `confidence`, `validation`, `position_risk`,
`watchlist_setup`, `watchlist_price_targets`, `portfolio_analytics`, `etf_lookthrough`,
`factor_data`, `explainability`, `alerts`, `projection`, `interface`, `signal_weights`, `cluster`,
`recency`, `trade_size_bands`, `fundamentals`, `modifiers`, `bucket_weights`, `bucket_limits`,
`build`, `labels`, `feature_flags`, `ranking_weights`, `news_intelligence`, `market_behavior`.

Supporting config: `advisor_universe.json` (910 symbols, publish_limit 40, extended_limit 400,
21 portfolio symbols), `universe.json` (126 ETFs), `metric_registry.json`, `feature_registry.json`
(49 KB), `applicability_matrix.json`, `research_contract.json`, `screen_presets.json`,
`recommendation_policy_v2.json`, `shadow_strategies.json`, `business_profiles.json`,
`peer_groups`, `etf_benchmarks.json`.

Every published artifact carries `model_version` (3.2.0), `schema_version` (5), the producing git
SHA, a full settings hash, and a generation timestamp.

---

## 12. Current measured state

Refresh of 2026-08-06T22:50 (an intraday `data-only` run):

| | |
|---|---|
| Universe configured / polled / published | 921 / 128 / 40 |
| Screen universe rows | 374 |
| Published score range | 71.4 – 83.4 (mean 75.05) |
| Screen universe score range | 20.1 – 71.3 (sd 10.67) |
| Coverage | 0.69 – 0.98 |
| Confidence | 0.70 – 0.89 |
| Statement enrichment | 124 / 126 attempted |
| Provider status | yahoo degraded (2 symbols), marketaux healthy, fred healthy, alpha disabled for intraday, **sec_form4 unavailable** |
| PIT store | 2 days |
| Shadow store | 5 days, 4 strategies |
| IC harness | 0 of 24 required periods |
| Promotions to date | 0 |

---

## 13. Contract vs. implementation — the honest gap table

| The contract says | The code does |
|---|---|
| 63-trading-day sector-residual forward return is the target | Raw forward return over calendar-day horizons |
| Tiered `half_spread + impact` transaction costs in validation | Flat 10bps |
| 16 screen presets | 7 wired, 9 specification-only |
| 14 alpha sleeves | 3 built |
| 6 portfolio-construction methods | 1 (score-weighted top-N) |
| Same-close execution guard | None |
| 32 scored fundamentals metrics formally declared | 20 declared, 12 undeclared in `metric_registry.json` |
| Delisted-security replay in scoring | Membership logged, not replayed |
| IPO-seasoning window | None |
| Independent corporate-action event log | Relies on provider-adjusted prices |
| Measured bid-ask spreads | Labeled liquidity-tiered proxy |
| Theme system | 11 theme YAMLs, 2 of 6 signal families resolving in production |
| `historical_calibration` confidence component | Always null |

Plus the defects found in the 2026-08-07 rating: the run-manifest model mismatch
(`observability.py:30`), the inert news component, the 84/374 coverage of two fundamental
categories, the 65% monthly turnover, the dark insider layer, and the enrichment selection
bootstrapping described in §4.1.

---

## 14. Reproducing a run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
cp .env.example .env.local          # ALPHA_VANTAGE_API_KEY, MARKETAUX_API_TOKEN,
                                    # FRED_API_KEY, SEC_USER_AGENT
python pipeline/fetch_news.py
python pipeline/fetch_advisor.py
python pipeline/build_etf_comparisons.py
python pipeline/validate_data.py

npm ci && npm test && npm run build && npm run dev
```

Quality gates (all run in CI on every push):

```bash
PYTHONPATH=pipeline python -m pytest pipeline/tests -q
python pipeline/validate_data.py
npm run lint && npm test && npm run build
```

`ADVISOR_SYMBOLS` overrides the universe; `ALPHA_ENRICH_LIMIT` caps Alpha Vantage enrichment;
`ADVISOR_EXTENDED_LIMIT` overrides the statement-enrichment shortlist size.
