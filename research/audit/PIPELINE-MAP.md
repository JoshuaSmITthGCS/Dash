# ValueSignal — Pipeline Map

Reconstructed from source, no edits. Every path is repo-relative. Reference artifact:
`public/data/advisor.json`, generated `2026-08-09T09:09:35Z`, `schema_version 5`,
`model_version 3.2.0`, universe 926, scored rows 877, published rows 40.

---

## 1. Entry point and run shape

`pipeline/fetch_advisor.py :: run()` (line 1207) is the whole research pipeline. It is one
function, ~780 lines, and it is the only thing that writes `advisor.json`.

Two run modes, chosen by `ADVISOR_UNIVERSE_MODE` (default `full`):

| Mode | Symbols polled | Behaviour |
|---|---|---|
| `full` | all 910 configured + portfolio | fits `CrossSectionalNormalizer` fresh |
| `fast` | prior top `ADVISOR_FAST_UNIVERSE_SIZE` (100) + portfolio + `ADVISOR_FAST_ROTATION_SIZE` (120) stalest | reuses the *previous* published normalization distributions (`CrossSectionalNormalizer.from_published`) |

Unpolled symbols are carried forward from the previous payload with
`stale_carryforward: True` (`carry_forward_rows`, line 1098) and may only enter
`screen_universe`, never `research`.

Outputs written by `common.save_json`:

| File | Writer | Size in repo |
|---|---|---|
| `public/data/advisor.json` | `fetch_advisor.run` line 1978 | 26.4 MB |
| `public/data/report.json` | `report_snapshot()` line 126 | 8.7 MB |
| `public/data/diagnostics.json` | `observability.diagnostics_payload` | 3.8 MB |
| `public/data/score-history.json` | line 1953 | 16.8 MB |
| `pipeline/data/pit/*.jsonl` | `pit_store.append_snapshot` | 14.7 MB |

---

## 2. Raw data sources and every external request

Endpoints found by exhaustive grep of `pipeline/**.py`:

| Provider | Endpoint | Module | Used for |
|---|---|---|---|
| Yahoo (yfinance) | undocumented, via `yfinance` | `fetch_advisor`, `providers.py`, `fetch_prices.py` | price history, quote snapshot, `.info`, income/balance/cashflow frames, option chains, company news |
| Alpha Vantage | `https://www.alphavantage.co/query` | `alpha_vantage.py` | `OVERVIEW`, `TIME_SERIES_DAILY`, `NEWS_SENTIMENT`, `INSIDER_TRANSACTIONS`, `MARKET_STATUS`, `TREASURY_YIELD`, `FEDERAL_FUNDS_RATE`, `INFLATION` |
| Marketaux | `https://api.marketaux.com/v1/news/all` | `marketaux.py` | entity-level news sentiment |
| FRED | `https://api.stlouisfed.org/fred/series/observations` | `fred.py` | macro regime (6 series) |
| SEC EDGAR | `https://data.sec.gov`, `https://www.sec.gov`, `https://efts.sec.gov/LATEST/search-index` | `sec_edgar.py`, `theme_signals.py`, `xbrl_dimensions.py` | Form 4, 10-K documents, submissions, dimensional XBRL |
| FMP | `https://financialmodelingprep.com/stable` | `congress_trades.py` | Congressional disclosures |
| Marketstack | `https://api.marketstack.com/v2` | `marketstack.py` | prices (secondary) |
| OpenFIGI | `https://api.openfigi.com/v3/mapping` | `openfigi_client.py` | CUSIP → ticker for 13F |
| Senate eFD / House & Senate stock watcher | S3 JSON + `efdsearch.senate.gov` | `congress_trades.py` | STOCK Act filings |
| RSS (Politico, MarketWatch, BBC, WSJ, Yahoo) | various | `fetch_news.py` | market news |

### Per-symbol request budget (full refresh)

Cheap pass, every polled symbol — `collect()` line 927:
1. `yf.Ticker(symbol)` construct
2. `yahoo_snapshot` → 1 quote request (cached 900 s)
3. `yahoo_history` → 1 price request (cached 6 h), pre-warmed in batches of 60 by
   `prefetch_histories` line 340
4. `fetch_company_news` → 1 Yahoo news request (cached 1800 s)

Alpha Vantage extras, **only for `alpha_symbols`, capped at 5 names per refresh**
(`ALPHA_ENRICH_LIMIT`, line 1237): `OVERVIEW`, `TIME_SERIES_DAILY`, `NEWS_SENTIMENT`,
`INSIDER_TRANSACTIONS`.

Statement enrichment, `enrich()` line 996 — shortlist only, `extended_limit` default
`publish_limit * 3`:
- `extended_inputs(ticker_obj)` → income/balance/cashflow frames (annual + quarterly)
- `ticker_obj.info` → quoteSummary
- optional earnings surprises (`ENABLE_EARNINGS_SURPRISE`, off), option chain
  (`ENABLE_OPTIONS_VOLATILITY`, off)

SEC pass, shortlist only (`SEC_FORM4_LIMIT`, default `publish_limit`):
- `collect_insider_signals` line 693 → Form 4, 4 workers
- `collect_filing_risk_signals` line 752 → latest 10-K document, 4 workers

Screen reads (no live calls in this path):
- `collect_institutional_signals` line 810 reads `public/data/screens/institutional-13f.json`
- `collect_congressional_signals` line 860 reads `public/data/screens/congress-trades.json`

### Caching, rate limiting, staleness

`pipeline/cache.py`. On-disk cache under `pipeline/data/cache`, keyed `(namespace, key)`,
each entry stamped with fetch time and source. Per-provider token buckets
(`DEFAULT_RATE_LIMITS`): alpha_vantage 5/min, sec_edgar 540/min (9/s, deliberately under the
published 10/s), yahoo 240/min (a *guess* — Yahoo publishes no limit), fred 120, marketaux 60.
TTLs (`DEFAULT_TTLS`): price_history 6 h, quote 15 min, statements 7 d, sec_submissions 24 h,
sec_document 30 d, news 30 min, default 1 h. `retry_with_backoff` and `parallel_map` wrap
provider calls.

Staleness is **surfaced, never enforced**: `pit_store.freshness_report` publishes
`data_freshness` and `DEFAULT_FIELD_TTL_HOURS` flags fields past TTL, but nothing in the
scoring path consults it. A stale value scores identically to a fresh one.

### Fallback behaviour

- `yahoo_history` failure → `EMPTY_HISTORY`, symbol later fails the `len(closes) < 21` guard
  in `collect()` and is dropped with a logged error.
- `.info` failure and statement-frame failure are caught **separately** (`yahoo_extended`
  line 462) so a company can enrich on half its data.
- `merge_snapshots` line 594 fills Alpha Vantage gaps from the Yahoo snapshot, first non-null
  wins, no provenance recorded on the merge.
- Alpha Vantage history replaces Yahoo history only if longer (line 975).
- Provider failure lists are published in `source_status`.

---

## 3. Metric derivation

`pipeline/fundamentals_extended.py :: derive_extended()` turns statement frames + `.info` +
price series into ~40 derived fields: EV multiples, ROIC, FCF yield, cash conversion,
accruals, Piotroski F, Altman Z (variant-aware), buyback yield, stock comp, capex/dep,
asset growth, DSO and inventory trends, incremental margin, 52-week position, dollar volume,
short interest, beta, analyst fields.

`pipeline/canonical_metrics.py` is the v2 layer: `Observation` dataclass (value, unit, source,
source_field, period_start/end, available_at, observed_at, fetched_at, fiscal_period, is_ttm,
is_forward, quality_flags, transform_version), `reconcile()` for multi-source arbitration by
configured precedence, `classify_profile()` for business-profile assignment, `calculate_peg()`.

**Critical structural fact:** the `Observation`/provenance machinery exists but is *parallel to*
the scoring path, not underneath it. The live score reads flat scalars off `snapshot`
(`scorer._band_valuation_score`). Observations are consumed only by `scoring_v2.build_v2_analysis`,
which is shadow.

---

## 4. Normalization

Two modes, selected by `settings.normalization_mode` (production: `bands`).

**`bands`** — `scorer._band_valuation_score` line 504. Each metric mapped to a discrete
0/5/10/15/25/45/50/55/65/75/80/100 by hand-set cutoffs in `settings.fundamentals`:
`band_score`, `higher_is_better_score`, `lower_is_better_score`, `range_score`,
`multiple_score`, `altman_score`. No winsorization. No cross-sectional reference. A metric's
score depends only on absolute thresholds, so it is not comparable across regimes.

**`cross_sectional`** — `scorer.CrossSectionalNormalizer` line 296, challenger only.
Winsorize at 1st/99th percentile of the full refresh universe, then percentile-rank within
sector when `len(sector_values) >= sector_minimum` (8) else universe; ties averaged;
lower-is-better and range metrics flipped via `100 - percentile`. Range metrics first mapped
to distance from ideal band (`_range_distance`). Reproducible: exact sorted distributions are
published in `normalization_distributions` and restorable via `from_published`.

**Own-history percentile** (`_own_history_detail`) exists for valuation multiples but is gated
at `own_history_minimum_observations` and currently reports `status: accumulating` for
everything — see §7 of the audit.

### Sector / market-relative ranking

Three distinct and inconsistent mechanisms:
1. `raw_fundamental_metrics` hard-nulls metrics by sector (`is_financial`, `TANGIBLE_BOOK_SECTORS`).
2. `CrossSectionalNormalizer.score` chooses sector vs universe distribution per metric.
3. `peer_groups.canonical_percentiles` groups by *business profile*, not sector.

These three do not agree on what a peer is.

---

## 5. Missing-data handling and suppression

| Mechanism | Location | Effect |
|---|---|---|
| `weighted_available` | `scorer.py:158` | drops missing metrics, renormalizes remaining weights within the category |
| `FINANCIAL_EXEMPT` | `scorer.py:167` | 10 metrics removed from the coverage *denominator* for financials |
| `TANGIBLE_BOOK_SECTORS` | `scorer.py:175` | P/TBV scored only in 9 sectors |
| `weighted_coverage` | `scorer.py:485` | coverage = answered weight / total weight, exempt metrics excluded |
| `applicability_matrix.json` | config | v2 only: per-profile `suppressed` / `replaced` rules |
| `METRIC_REGISTRY.applicability_profiles` | config | v2 only: suppress if profile not declared |

Renormalization is **silent**: nothing records that a category was computed from 2 of 8 metrics.

---

## 6. Scores produced

### Live (champion) path — `advisor_engine.build_research` line 1010

```
fundamentals      = scorer.valuation_score(snapshot)          # 0-100, bands
market_behavior   = advisor_engine.technical_factors(...)     # 0-100
news_sentiment    = advisor_engine.sentiment_score(...)       # 0-100 or None
```

`blend_research_components` line 758:
```
raw        = Σ(score_i · w_i) / Σ(w_i)        over available components
             w = {fundamentals 0.78, market_behavior 0.18, news_sentiment 0.04}
confidence = 0.65·cov_fund + 0.25·cov_tech + 0.10·cov_news
base       = raw · (0.8 + 0.2·confidence)
score      = clamp(base + modifier_points, 0, 100)
```

Fundamentals themselves are already coverage-shrunk inside `_band_valuation_score`:
`total = raw · (0.65 + 0.35·coverage)`. **Coverage therefore enters the composite twice.**

Category weights and metric weights: `settings.fundamentals.category_weights` /
`metric_weights` (6 categories, 33 metrics).

Market behaviour sub-weights (`TECHNICAL_WEIGHTS`): momentum_12_1 0.30, risk_adjusted 0.26,
relative_strength 0.16, drawdown_resilience 0.14, volume_confirmation 0.08, low_beta 0.06,
technical_extended 0.06.

Post-blend modifiers (`apply_modifiers` line 502), each bounded, sum clamped to ±15:
`sector_valuation` (±3), `short_interest` (−6), `liquidity` (−3), `expectations` (±3),
`macro_regime` (±3), `insider_activity` (+5/−3), `institutional_13f` (+3/−2),
`congressional_buying` (+4, reward-only).

Shadow-only modifiers, challenger variants only: `customer_concentration_risk`,
`geographic_concentration`.

`stance_for` line 746: `< 0.45 confidence → INSUFFICIENT DATA`; else ≥75 ATTRACTIVE,
≥60 PROMISING, ≥45 MIXED, else CAUTION.

### Shadow path — `scoring_v2.build_v2_analysis` line 65

Produces `analysis_v2 = {structural, timeliness, metric_status, applicability}`.

```
structural.coverage    = available_weight / applicable_weight
structural.confidence  = coverage · provenance_reliability − conflict_penalty − stale_penalty
                         provenance_reliability = 0.72 if observations else 0.55
structural.effective   = 50 + confidence · (raw − 50)

timeliness.raw         = weighted(forward_eps_revision_30d 0.7, earnings_surprise 0.3)
timeliness.effective   = 50 + confidence · (raw_or_50 − 50)
```

### Shadow policy — `recommendation_policy_v2.build_recommendation_v2` line ~470

`two_axis_classification(structural_effective, timeliness_effective, score_matrix)` →
company action; `classify_portfolio_fit` → portfolio state; `_stop_state` → stop rules;
`_trim_percent` → sized reduction; `evaluate_entry_rules` → entry/add/re-entry.

### Frontend derived scores

- `src/lib/watchlistGuidance.js` — **Setup Quality**: weighted geometric mean of
  `{thesis 0.30, research 0.30, confidence 0.20, guidance 0.20}` sub-scores, each a logistic
  of a raw input, ×100, rounded to 0.1.
- `src/lib/bullBearScore.js` — thesis score.
- `src/lib/confidenceGate.js` — bands the same `confidence` scalar into
  low/moderate/high labels at 60 / 75.
- `src/lib/researchRating.js` — multiplies rating by `confidence`.

---

## 7. Guidance and position logic

### Live — `advisor_engine.action_for` line 680 ("2-of-3")

Three concern groups:

| Group | Triggers |
|---|---|
| `fundamentals` | any of profitability / financial_health / accounting_quality / growth category < 45; interest coverage < 2×; accruals ratio > 0.10 |
| `market_behavior` | 252-day max drawdown < −30%; 20-day relative strength < −10; (60-day return < −15% AND 20-day return < 0) |
| `positioning` | ≥3 articles averaging < −0.15 sentiment; short interest ≥ 15% of float |

```
agreement = number of groups with ≥1 trigger
agreement ≥ 2 and score < 45  → SELL,  trim 100, "high"
agreement ≥ 2                 → TRIM,  trim 33 (2 groups) / 50 (3 groups), "moderate"
agreement == 1                → WATCH, trim 0
else                          → HOLD
```

There is no stop-loss, no trailing stop, no ATR rule, no time stop and no re-entry rule in
the live path. `suggested_trim_pct` is a constant per branch.

### Shadow — `recommendation_policy_v2.py`

Has the machinery the live path lacks: `_stop_state` with named stop profiles
(`hard_cost_basis_stop`, high-water-mark rules), `_trim_percent` with severity × confidence ×
concentration × liquidity × tax multipliers, `_economic_trade` materiality test,
`evaluate_entry_rules` with earnings blackout and averaging-down control. None of it reaches
the user: see audit §4.

### Frontend position logic

`src/lib/positionRisk.js`, `src/lib/sellWatchLogic.js`, `src/lib/portfolioPosition.js`,
`src/lib/dipWatch.js` compute recovery levels, floors and sell-watch states client-side from
the published row. These are a fourth guidance implementation, independent of the three above.

---

## 8. Dependency graph

```
                    ┌─────────────────────────────────────────────┐
raw providers ──────▶ cache.py (TTL, token bucket, retry)         │
 yahoo / alpha /    └──────────────┬──────────────────────────────┘
 marketaux / fred /                │
 sec / fmp                         ▼
                        fetch_advisor.collect()
                        ├─ snapshot  (quote + OVERVIEW, merge_snapshots)
                        ├─ history   (dates, closes, volumes)
                        └─ news      (yahoo + marketaux/alpha)
                                   │
                                   ▼
                        fetch_advisor.enrich()  ── shortlist only ──▶ fundamentals_extended.derive_extended
                                   │                                          │
                                   │                                          ├─▶ flat scalars merged onto snapshot
                                   │                                          └─▶ extended_observations() → snapshot["observations"]
                                   ▼
        ┌──────────────────────────┴───────────────────────────────┐
        ▼                                                          ▼
scorer.valuation_score(snapshot)                     canonical_metrics / scoring_v2
  raw_fundamental_metrics  (sector nulling)            classify_profile
  band_score / multiple_score / range_score ...        applicability_for (registry)
  weighted_available → 6 categories                    reconcile (provider arbitration)
  weighted_available → raw                             → structural  ─┐
  × (0.65 + 0.35·coverage)                             → timeliness  ─┤ SHADOW
        │                                                            │
        │  advisor_engine.technical_factors(closes, bench, volumes)  │
        │    momentum_12_1 / risk_adjusted / relative_strength /     │
        │    drawdown_resilience / volume_confirmation / low_beta /  │
        │    technical_extended                                      │
        │                                                            │
        │  advisor_engine.sentiment_score(news)                      │
        ▼                                                            │
blend_research_components  →  raw_score, confidence, base_score      │
        │                                                            │
        ▼                                                            │
apply_modifiers  (8 bounded modifiers, ±15 cap)                      │
        │                                                            │
        ▼                                                            ▼
   row["score"] ──▶ stance_for ──▶ action_for (2-of-3)   recommendation_policy_v2 (SHADOW)
        │                              │                             │
        │                              ▼                             ▼
        │                   row["recommendation"]        row["recommendation_v2"]
        │
        ├──▶ peer_groups.canonical_percentiles ──▶ row["valuation_percentile"]
        ├──▶ confidence.confidence_components ──▶ row["confidence_detail"]
        ├──▶ evidence_events.build_evidence   ──▶ row["evidence"]
        ├──▶ explainability.attach_explainability
        └──▶ pit_store.append_snapshot
                    │
                    ▼
            advisor.json ──▶ React PWA
                              ├─ watchlistGuidance.js  → Setup Quality
                              ├─ confidenceGate.js     → confidence bands
                              ├─ researchRating.js     → rating × confidence
                              ├─ positionRisk.js / sellWatchLogic.js → position guidance
                              └─ rankingModels.js / researchScreens.js → strategy screens
```

### Feedback edges (important, and easy to miss)

1. **`previous_ranked_symbols` → `select_enrichment_priority` → `enrich`.** Statement-derived
   metrics only ever exist for names a *previous* run already ranked highly. A name outside
   the prior top 20 + 5 challengers can never acquire ROIC, EV/EBITDA, Piotroski or Altman,
   so it can never out-rank an incumbent on those metrics. `FULL_UNIVERSE_RESEARCH=1` is the
   documented escape hatch and is not the production path.
2. **Fast refresh → `CrossSectionalNormalizer.from_published`.** A challenger fit is inherited
   from the last full refresh.
3. **`previous_target` → `collect_estimate_detail`.** Target drift is measured against the
   prior published payload — the app is its own only historical estimate source.
4. **`carry_forward_rows`.** A screen row can be arbitrarily old and still be ranked.

---

## 9. Configuration surface

| File | Bytes | Role |
|---|---|---|
| `settings.json` | 48,761 | all weights, bands, modifier caps, UI thresholds |
| `feature_registry.json` | 48,767 | feature declarations |
| `universe.json` | 23,877 | ETFs, retirement core |
| `metric_registry.json` | 13,652 | canonical metric declarations, valid ranges, TTLs |
| `advisor_universe.json` | 11,215 | 910 symbols, publish_limit, portfolio_symbols |
| `screen_presets.json` | 11,142 | screen definitions |
| `research_contract.json` | 8,364 | published contract |
| `business_profiles.json` | 7,041 | replacement/critical metrics, ticker overrides |
| `applicability_matrix.json` | 5,037 | per-profile suppression rules (v2 only) |
| `recommendation_policy_v2.json` | 4,679 | shadow policy thresholds |
| `provider_reconciliation.json` | 1,052 | source precedence, discrepancy tolerance |

---

## 10. Test surface

`pipeline/tests/` — 60+ test modules. `src/**/*.test.{js,jsx}` — ~40 modules. The tests
verify mechanics (does the weight renormalize, does the parser parse) and shape. **No test
asserts that a published claim is true of the world** — nothing checks that a peer-relative
statement matches the peer data, that a layer has cross-sectional variance, or that a
displayed precision is supported.
