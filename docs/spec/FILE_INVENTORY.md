# ValueSignal — File Inventory

Code-grounded inventory of every significant source file in the repository. Each line was
written after opening the file (docstring/header + `def`/`class`/`export` signatures), not
guessed from the filename. This is an inventory, not a full spec — it does not attempt to
capture every internal helper.

---

## Runtime topology

**package.json scripts** (`npm run <script>`):
- `dev` → `vite` — local dev server.
- `build` → `vite build` — production build (custom Rolldown code-splitting config in
  `vite.config.js`, see below).
- `preview` → `vite preview`.
- `test` → `vitest run` — the JS/JSX unit-test suite (Vitest + jsdom + Testing Library).
- `lint` → `eslint .`.
- `docs:breakdown` → `node scripts/generate-app-breakdown.mjs` — regenerates
  `APP-COMPLETE-BREAKDOWN.md` from `package.json`, `public/data/advisor.json`,
  `public/data/etfs.json`, factor data, `src/App.jsx` routes, and PIT-store row counts.
- `screenshots:mobile` → `node scripts/mobile-screenshots.mjs` — Playwright mobile screenshot
  capture of key pages/themes into `docs/mobile-screenshots/`.
- `evidence:factors` → `node scripts/factor-regression-evidence.mjs` — six-factor regression
  evidence artifact.
- `evidence:hygiene` → `node scripts/hygiene-evidence.mjs` — bundle-size / `npm audit` hygiene
  report from `dist/`.
- `evidence:projection` → `node scripts/projection-spread-evidence.mjs` — before/after
  evidence for the sparse-portfolio-history projection fix.

The Python pipeline (`pipeline/*.py`) is invoked directly as `python pipeline/<script>.py`
from GitHub Actions workflows, not via `npm`/`package.json`.

**GitHub Actions workflows** relevant to refresh/scoring, and their schedule
(`.github/workflows/*.yml`, cron in UTC):
- `refresh-advisor.yml` — **the main hourly research refresh.** `workflow_dispatch` (modes:
  `data-only` / `full-alpha` / `rescore-only`) plus `schedule: cron: '7 11,12,16,17,19,20 * * 1-5'`
  (weekdays, ET-market-hours-aligned, ~6x/day). Runs `fetch_advisor.py` → the options-strategy
  screen builders → `run_strategy_backtests.py` → `fetch_etfs.py` /
  `build_etf_comparisons.py` / `fetch_factors.py` → `rescore.py` →
  `build_quality_value_screen.py` → `build_tactical_screens.py` → `shadow_portfolios.py` →
  `validate_data.py` → `stability_report.py` → `evaluate_alerts.py`, then commits published
  `public/data/*.json`.
- `congress-trades.yml` — weekly Congressional (STOCK Act) disclosure collection,
  `cron: '0 13 * * 1'` (Monday), `workflow_dispatch` also available.
- `institutional-13f.yml` — monthly 13F institutional-ownership collection,
  `cron: '0 13 1 * *'` (1st of month).
- `marketstack-premarket.yml` — twice-daily Marketstack premarket/after-hours collection,
  `cron: '35 20,21 * * 1-5'` and `'5 12,13 * * 1-5'` (after-close backfill + pre-open forward
  collection, ET-DST-aware pair of UTC candidates).
- `backfill-pit-fundamentals.yml` — point-in-time SEC EDGAR XBRL fundamentals backfill,
  `workflow_dispatch` (scope: audit-only/sample/full) plus monthly `cron: '11 6 3 * *'`.
- `measure-survivorship.yml` — quarterly survivorship/attrition measurement via SEC quarterly
  filing indexes, `cron: '23 7 15 1,4,7,10 *'`, `workflow_dispatch`.
- `demo-data.yml` — `workflow_dispatch` only; regenerates mock demo data via
  `seed_mock_data.py`.
- `ci.yml` — on push/PR to `main`: `python -m compileall`, `check_ui_weights.py`,
  `pytest pipeline/tests`, `ic_harness.py --snapshot`, `validate_data.py`.

**netlify/functions/*.mjs** (serverless endpoints, Netlify Functions):
- `refresh-data.mjs` — `handler` dispatches (via GitHub REST API, admin-authenticated) and
  polls the `refresh-advisor.yml` / research-screen workflows from the site's own "Refresh"
  button; exports `SCREEN_WORKFLOWS`, `parseRequestBody`, `workflowProgress`,
  `locateDispatchedRun`.
- `portfolio-prices.mjs` — `handler` authenticates a Firebase ID token then fetches live/
  post-market quotes for a user's held symbols from Yahoo; exports `parseSymbols`,
  `fetchPortfolioQuotes`.
- `alert-push.mjs` — `handler` evaluates quiet-hours and sends grouped Web Push notifications
  for newly written Firestore alert events, using `firebase-admin` + `web-push`; exports
  `isQuietTime`, `buildPushPayload`.

---

## pipeline/ (top-level Python modules)

- `pipeline/advisor_engine.py` — Core explainable scoring engine: technical factors
  (`technical_factors`, `technical_score_from_parts`), sentiment scoring, and every bounded
  "modifier" (insider, institutional, congressional-buying, concentration risk, geographic
  concentration, liquidity, expectations, sector percentile, macro regime) that combines with
  fundamentals into the published research score (`apply_modifiers`,
  `apply_challenger_modifiers`).
- `pipeline/alpha_vantage.py` — Cache-first Alpha Vantage HTTP client (`AlphaVantageClient`)
  plus `.env.local` loader (`load_local_env`); key never logged/cached in output.
- `pipeline/audit_ticker.py` — CLI (`python -m pipeline.audit_ticker TICKER --as-of DATE`)
  that prints one ticker's row from `public/data/diagnostics.json`.
- `pipeline/backtest_common.py` — Shared walk-forward backtest engine for the options-strategy
  screens: synthetic Black-Scholes option chains (`synthetic_chain`), period walking
  (`walk_periods`), and Sharpe-family performance stats including deflated/probabilistic
  Sharpe (`performance_stats`, `deflated_sharpe_ratio`).
- `pipeline/backtest_emerging_growth.py` — Retrospective backtest of the "Emerging growth"
  screen; reuses `backtest_monthly.py`'s machinery, swaps in `rank_emerging_growth.py`'s
  Python port of the frontend's screen logic.
- `pipeline/backtest_historical.py` — Point-in-time historical backtest of the real
  `advisor_engine`/`scorer` scoring logic; reconstructs weekly historical snapshots
  (`build_snapshot`, `rank_week`) and simulates a DCA portfolio against SPY/QQQ/DIA/IWM
  (`simulate_portfolio`, `simulate_benchmark_dca`).
- `pipeline/backtest_monthly.py` — The primary auditable monthly top-N walk-forward backtest
  for the champion appeal score (`build_rebalance_calendar`, `simulate_locked_portfolio`,
  `performance_metrics`); underlies most published research-evidence numbers.
- `pipeline/benchmark_suite.py` — Builds tradeable-ETF-style benchmark comparisons (RSP, IWM,
  etc.) against the monthly backtest, reusing `p0_q1_benchmark_factor_report`'s loaders
  (`build_report`).
- `pipeline/bias_report.py` — Computes score-bias correlations (Pearson/Spearman) between
  score and exposure fields for the legacy vs. challenger scoring paths
  (`build_bias_report`, `write_bias_report`).
- `pipeline/build_advanced_options_screen.py` — Publishes the "Advanced strategies" iron-
  condor + straddle options screen from one shared option-chain fetch per ticker
  (`build_iron_condor_row`, `build_straddle_row`, `run`, `run_backtest`).
- `pipeline/build_benchmark_report.py` — Thin wrapper that calls
  `build_etf_comparisons.publish_benchmark_report()` to rebuild the compact Financial Report
  benchmark payload.
- `pipeline/build_cash_secured_put_screen.py` — Publishes the cash-secured-put income screen
  (30-delta strike, 15-45 DTE); `build_row`, `score_rows`, `run`, `run_backtest`.
- `pipeline/build_collar_screen.py` — Publishes the defined-risk collar screen (long stock +
  protective put + covered call); `build_row`, `score_rows`, `run`, `run_backtest`.
- `pipeline/build_congress_screen.py` — Weekly Congressional STOCK Act disclosure screen:
  fetches/appends new trades point-in-time and computes defensible flags (LATE_FILING,
  CLUSTER_TRADE, BUY_SELL_FLIP, etc.) via `classify`, `relational_flags`.
- `pipeline/build_covered_call_screen.py` — Publishes the covered-call income screen (30-delta
  call against a long 100-share position); `build_row`, `score_rows`, `run`, `run_backtest`.
- `pipeline/build_etf_comparisons.py` — Fetches adjusted ETF histories and publishes versioned
  per-ticker comparison contracts under `public/data/etf/`; also builds the compact benchmark
  report (`publish_benchmark_report`, `build_all`).
- `pipeline/build_feature_registry.py` — Generates `pipeline/config/feature_registry.json`
  from existing metric definitions/weights, adding the usage classification the research
  contract requires (`build_feature_registry`).
- `pipeline/build_filer_cohorts.py` — Measures universe survivorship by comparing SEC
  quarterly filing indexes against the current ticker map (`collect`, `cohorts`); backs the
  `measure-survivorship.yml` workflow.
- `pipeline/build_institutional_screen.py` — Quarterly 13F institutional accumulation/
  distribution screen from curated public managers' filings (`resolve_filer_ciks`,
  `manager_quarters`, `build_results`, `run`); feeds `institutional_ownership_modifier`.
- `pipeline/build_momentum_screen.py` — Publishes the Momentum research screen from cached
  Yahoo price history via `research_screens_v2`'s formulas (`build_rows`, `run`).
- `pipeline/build_normalization_snapshot.py` — Builds the cross-sectional-normalization
  challenger from checked-in observations with no network calls (`main`).
- `pipeline/build_options_screen.py` — Publishes the "Best multi-day options" directional
  screen (2-45 DTE); `build_row`, `score_rows`, `run`, `run_backtest`.
- `pipeline/build_options_strategies.py` — Publishes buy/sell-call/sell-put/"Short-term
  trades" screens from ONE shared option-chain fetch per ticker, replacing the three
  standalone screens' live-data path (`build_rows`, `select_best_per_ticker`, `run`).
- `pipeline/build_pit_fundamentals.py` — Runnable job backfilling point-in-time fundamentals
  from SEC EDGAR XBRL into `pipeline/data/pit/fundamentals.jsonl`, keyed by CIK
  (`collect_company`, `run`, `main`).
- `pipeline/build_protective_put_screen.py` — Publishes the protective-put portfolio-hedge
  screen; `build_row`, `score_rows`, `run`, `run_backtest`.
- `pipeline/build_quality_value_screen.py` — Publishes the "quality at valuation lows" screen
  combining own-history cheapness, peer cheapness, business quality, and forward revisions
  (`build_rows`, `classify_rows`, `run`).
- `pipeline/build_report_snapshot.py` — Rebuilds the compact `report.json` payload from the
  latest complete `advisor.json` (`run`).
- `pipeline/build_research_evidence.py` — Aggregates committed research/report artifacts
  (benchmarks, factors, diagnostics, costs, calibration, experiments, enrichment) into
  `public/data/validation/research_evidence.json` for the `/screens/validation` page
  (`build_report`).
- `pipeline/build_tactical_screens.py` — Publishes earnings-timeliness and structural/
  tactical-matrix screens from one shared tactical-factor pass (`build_rows`,
  `attach_industry_factors`, `run`).
- `pipeline/build_vertical_spread_screen.py` — Publishes the vertical bull-call/bear-put
  spread screen on 20-day trend bias; `build_row`, `score_rows`, `run`, `run_backtest`.
- `pipeline/cache.py` — On-disk caching (`DiskCache`), per-provider token-bucket rate limiting
  (`RateLimiter`, `limiter_for`), and bounded parallel fetching (`parallel_map`,
  `retry_with_backoff`).
- `pipeline/canonical_metrics.py` — Canonical metric normalization/applicability/provider-
  reconciliation layer (v2): `Observation` dataclass, `reconcile`, `applicability_for`,
  `classify_profile`, `yahoo_observations`.
- `pipeline/check_ui_weights.py` — CI check that fails when Methodology/Glossary pages hard-
  code numeric scoring weights instead of describing the published snapshot (`main`).
- `pipeline/collect_estimates.py` — Appends today's normalized consensus estimate snapshot,
  never manufacturing prior history (`collect`).
- `pipeline/collect_marketstack.py` — Collects premarket/intraday price data for the top-100
  published tickers via Marketstack, appended point-in-time (`collect`, `daily_closes`,
  `depth`, `run`).
- `pipeline/common.py` — Shared pipeline utilities: `_Log`, `http_get_json`, `load_json`/
  `save_json` (with config-hash versioning), `update_pipeline_status`, date helpers.
- `pipeline/concentration_risk.py` — Scores customer-concentration risk from ASC 280 XBRL
  dimensional facts (`customer_concentration_percentages`, `score_concentration_risk`).
- `pipeline/congress_signal.py` — Scores Congressional stock purchases as a bounded, reward-
  only modifier (`score_congressional_buying`) — the one explicit exception to the "no
  political inputs" rule, documented in its own docstring.
- `pipeline/congress_trades.py` — Three STOCK Act disclosure clients (`CongressTradesClient`
  for FMP, `SenateEfdClient` for Senate eFD, `StockWatcherClient` for the now-403'd mirror).
- `pipeline/cost_sensitivity.py` — B3 cost-sensitivity report re-pricing the monthly backtest's
  60 rebalances under different flat-bps regimes from already-stored turnover/cost fields, no
  network needed (`reprice_rebalance`, `build_report`).
- `pipeline/costs.py` — Transaction cost model (half-spread + fees + volatility-scaled impact)
  across three scenarios (`estimate_cost_bps`, `cost_scenarios`, `liquidity_tier`).
- `pipeline/data_coverage.py` — Decomposes the single `data_coverage` scalar into named
  completeness/freshness/peer-sample/model-agreement/calibration components
  (`data_coverage_components`).
- `pipeline/early_session_research.py` — Capability-gated early-session (premarket/first-hour)
  research infrastructure; reports real capability status from Marketstack collection depth
  rather than hardcoding availability (`capability_report`, `run`).
- `pipeline/edgar_entities.py` — Canonical ticker→CIK entity resolution with ambiguity as an
  error (`EntityResolver`, `normalize_ticker`), the primary key for the PIT store.
- `pipeline/edgar_facts.py` — SEC XBRL company-facts reader that stamps every observation with
  its actual filing-accepted date, preserving restatements (`observations_for_concept`,
  `company_observations`, `as_of`, `restatements`).
- `pipeline/enrichment_bias.py` — Measures the A3 enrichment-selection defect (statement
  enrichment only reaches the prior refresh's top 20 + 5 challengers) from committed data, no
  network (`enriched_vs_non_enriched`, `build_enrichment_bias_report`).
- `pipeline/estimate_snapshots.py` — Append-only point-in-time analyst-estimate snapshot store
  (`normalize_estimates`, `append_estimate_snapshot`, `estimate_revision_diagnostics`).
- `pipeline/etf_comparison.py` — Canonical, versioned ETF/benchmark comparison contract
  (schema 4): `normalize_prices`, `align_series`, `calculate_metrics`, `build_contract`.
- `pipeline/etf_disclosure.py` — Parses SEC Rule 6c-11 ETF disclosures (NAV premium/discount,
  median 30-day bid-ask spread) via pluggable per-issuer adapters
  (`fetch_disclosure`, `total_cost_of_ownership`).
- `pipeline/evaluate_alerts.py` — Evaluates Firestore alert rules after a scored refresh and
  writes deduplicated events, then requests grouped push delivery (`evaluate_rule`,
  `should_fire`, `main`).
- `pipeline/evaluate_signal.py` — CLI that grades a scoring configuration against the point-
  in-time store: rank IC, ICIR, quantile spread, deflated verdict (`build_periods`, `main`).
- `pipeline/evaluation.py` — Core validation statistics library: rank IC (`rank_ic`),
  `ic_summary`, `quantile_buckets`, `deflated_sharpe_ratio`,
  `probability_of_backtest_overfitting`, `walk_forward`, `evaluate_candidate`.
- `pipeline/evidence_events.py` — Dated evidence-event model with per-event-type recency decay
  for news and insider signals (`decay_weight`, `cluster_articles`, `build_news_events`,
  `news_event_score`, `build_evidence`).
- `pipeline/experiment_registry.py` — Hand-maintained backfill registry of every research
  experiment run (id, hypothesis, metrics, decision) feeding the multiple-testing trial count
  (`REGISTRY`, `backfill_multiple_testing_log`, `build_report`).
- `pipeline/explainability.py` — Deterministic score attribution/anomaly narration:
  `score_attribution`, `metric_explanations`, `factor_bars`, `anomaly_flags`,
  `build_score_history`, `attach_explainability`.
- `pipeline/fetch_advisor.py` — The main orchestrator that builds the public
  `advisor.json` research dataset from Alpha Vantage + Yahoo fundamentals: `yahoo_snapshot`,
  `yahoo_extended`, `yahoo_options_volatility`, `report_snapshot`, `resolve_refresh_symbols`.
- `pipeline/fetch_etfs.py` — Ranks the ETF watchlist within peer groups (broad equity, sector,
  fixed income, etc.) on performance/risk-adjusted return/cost/liquidity/structure
  (`build_etf_row`, `score_etf_universe`, `build_etfs`).
- `pipeline/fetch_factors.py` — Caches and publishes the monthly Fama/French five-factor +
  momentum series (`parse_monthly_csv`, `build_factor_payload`, `refresh_factors`).
- `pipeline/fetch_news.py` — Fetches financial news (Marketaux primary, RSS fallback), flags
  policy sectors/tickers (`fetch_marketaux`, `fetch_rss`, `fetch`).
- `pipeline/fetch_prices.py` — Per-ticker daily-close/valuation/politician-track-record
  snapshot builder, writing `prices.json`/`politicians.json` (`fetch_snapshot`,
  `build_prices`, `build_track_record`).
- `pipeline/fred.py` — Minimal FRED macro-regime client (`FredClient`) deriving a macro
  regime label from Treasury/CPI/unemployment/yield-curve/Sahm series (`derive_regime`).
- `pipeline/fundamentals_extended.py` — Derives quality/capital-allocation/accounting-
  integrity/market-structure metrics from yfinance statements: `derive_roic`,
  `derive_altman_z`, `derive_piotroski`, `derive_asset_growth`, etc.
- `pipeline/geographic_exposure.py` — Scores geographic revenue-concentration risk from ASC
  280/`StatementGeographicalAxis` XBRL facts (`geographic_revenue_shares`,
  `score_geographic_concentration`).
- `pipeline/insider_signal.py` — Scores SEC Form 4 insider trading using the routine-vs-
  opportunistic classification from Cohen/Malloy/Pomorski (`classify_transactions`,
  `cluster_trades`, `score_insider_activity`).
- `pipeline/institutional_ownership.py` — Pure classification of 13F accumulation/
  distribution (`parse_13f_info_table`, `holdings_change`, `score_institutional_ownership`,
  `decay`), consumed by both the screen builder and the advisor-engine modifier.
- `pipeline/layer_health.py` — Weight renormalization (`renormalize`) and the constant-layer
  guard (`assert_layers_vary`) that fails a build if a scoring layer resolves to one constant
  value for the whole universe.
- `pipeline/live_etf_validation.py` — Controlled cross-asset ETF validation run (international
  equity, bond, commodity, leveraged, etc.) writing staging diagnostics only (`run`).
- `pipeline/live_v2_validation.py` — Controlled representative-universe (10-ticker) refresh
  that validates the v2 scoring/recommendation pipeline without touching production outputs
  (`validate_live`, `main`).
- `pipeline/market_history.py` — Pure weekly/daily price-series grid and benchmark-relative
  hypothetical-return arithmetic for the site's line charts (`weekly_grid`, `chart_grid`,
  `hypothetical_vs_benchmark`).
- `pipeline/marketaux.py` — Cached Marketaux news client and provider-shape adapters
  (`MarketauxClient`, `advisor_articles_for_symbols`).
- `pipeline/marketstack.py` — Thin Marketstack (apilayer) client for premarket/intraday price
  data, batching up to 100 symbols per request (`MarketstackClient`).
- `pipeline/migrate_advisor_v2.py` — Re-derives every computed block on a published advisor
  payload with no network calls: schema-version field renames plus full v2/shadow/peer-context
  recomputation (`rescore_row`, `assert_contract`, `migrate`).
- `pipeline/news_fix_impact.py` — Measures and applies the A1 news-availability fix (no
  fabricated neutral-50 sentiment) against the committed champion data with no network
  (`reconstruct_score`, `apply_news_fix`).
- `pipeline/news_intelligence.py` — Deterministic article filtering, novelty/dedup, and
  weighting for research sentiment (`deduplicate_articles`, `classify_event_type`,
  `weighted_sentiment`).
- `pipeline/news_weight_impact.py` — Measures the effect of dropping inert (coverage-0)
  news weight from the champion blend's denominator, reusing production blend code
  (`compare_section`, `build_report`).
- `pipeline/normalization_audit.py` — Generates the normalization ground-truth/point-in-time-
  coverage artifact (`build_normalization_audit`, `write_normalization_audit`).
- `pipeline/normalization_report.py` — Champion-vs-cross-sectional-normalization comparison
  report (`build_normalization_report`, `write_normalization_report`).
- `pipeline/observability.py` — Run manifests and ticker-level reproducibility artifacts
  (`run_manifest`, `diagnostics_payload`).
- `pipeline/openfigi_client.py` — Maps CUSIPs→tickers via OpenFIGI, respecting the anonymous
  10-job vs. keyed 100-job batch-size tiers (`OpenFigiClient`).
- `pipeline/optimize_weights.py` — Monte Carlo empirical search over the ranking-weight and
  fundamentals-category-weight blends, built on `backtest_historical.py`
  (`run_sweep`, `evaluate_holdout`, `main`); exploratory tool, never writes config itself.
- `pipeline/options_common.py` — Shared option-chain math for all strategy screens: Black-
  Scholes pricing/delta/probability (`bs_d1_d2`, `call_price`, `put_price`), expiration
  selection, contract liquidity gating (`contract_liquidity`, `select_contract`).
- `pipeline/p0_q1_benchmark_factor_report.py` — WO-4/Q1: RSP/IWM buy-and-hold benchmark legs
  plus a six-factor Newey-West regression against the monthly backtest (`ols_newey_west`,
  `main`).
- `pipeline/p0_q2_turnover_attribution.py` — WO-5/Q2: attributes refresh-to-refresh rank churn
  in the live PIT-store log into band-crossing / genuine-change / availability-flicker /
  price-driven buckets (`attribute_transition`, `main`).
- `pipeline/peer_groups.py` — Reproducible peer rankings with a minimum-30-peer gate and tie-
  aware tiering, replacing single-percentile point estimates (`peer_group`,
  `canonical_percentiles`).
- `pipeline/pit_derive.py` — Turns point-in-time filed facts into scoreable ratios as of any
  date (TTM construction, ratio derivation) with no lookahead (`trailing_twelve_months`,
  `derive`, `growth`).
- `pipeline/pit_fundamentals_store.py` — Sharded, deduplicated on-disk storage for point-in-
  time fundamentals, keeping the full-universe store under GitHub's file-size limits
  (`ShardedStore`, `dedupe`, `shard_for`).
- `pipeline/pit_market.py` — Point-in-time market data and universe membership; documents and
  corrects prior split/dividend-adjustment reasoning (`PriceHistory`, `universe_as_of`,
  `rebalance_dates`).
- `pipeline/pit_shares.py` — Reconciles filed share counts with the price series' split basis,
  detecting split ratios from repeated filed periods (`canonical_split_ratio`,
  `basis_events`, `shares_as_of`).
- `pipeline/pit_store.py` — Append-only JSON-Lines point-in-time observation/revision/universe
  stores under `pipeline/data/pit/` (`append_snapshot`, `as_of`, `universe_as_of`,
  `freshness_report`).
- `pipeline/plausibility.py` — Fail-loud plausibility screening dropping arithmetically
  impossible provider values (e.g. margin >100%) before they reach the model
  (`field_violations`, `screen`).
- `pipeline/policy_backtest.py` — Exit-policy comparison (stops, trims, thesis-only exits) for
  point-in-time weekly rankings, holding entry signal constant (`simulate_policy`,
  `compare_policies`).
- `pipeline/portfolio_construction.py` — Turnover-control challengers (rank buffer, minimum
  holding period, score smoothing, replacement margin) as pure functions over
  `(previous_holdings, ranked_candidates)` (`apply_controls`, `turnover`).
- `pipeline/provider_interfaces.py` — `typing.Protocol` capability contracts (PriceProvider,
  FundamentalsProvider, EstimateProvider, etc.) so a caller depends only on the capability it
  needs.
- `pipeline/providers.py` — Ports-and-adapters provider abstraction: `AbstractDataProvider`
  port plus `YahooAdapter`/`AlphaVantageAdapter`/`EdgarAdapter`/`FakeProvider` and a
  `CompositeProvider` failover chain (`build_provider`, `build_composite`).
- `pipeline/rank_emerging_growth.py` — Python port of `src/lib/researchScreens.js`'s
  `rankEmergingGrowth` for backtesting the frontend-only "Emerging growth" screen
  (`emerging_growth_score`, `rank_week_emerging_growth`).
- `pipeline/rank_picks.py` — Legacy political/valuation blend into SHORT TERM / LONG TERM /
  RETIREMENT buckets, writing `picks.json` (`composite`, `tier`, `build`).
- `pipeline/recommendation_policy_v2.py` — Shadow-only recommendation policy with independent
  company/position decisions (two-axis structural×timeliness classification, deterioration
  groups, stop-loss/trim rules) (`two_axis_classification`, `build_recommendation_v2`).
- `pipeline/rescore.py` — Re-scores the last published `advisor.json` with zero network calls
  after a scoring-code change (`backfill_row_observations`, `main`).
- `pipeline/research_screens_v2.py` — Point-in-time research-screen formulas: momentum
  factors/scoring (`momentum_factors`, `momentum_scores`), tactical score, robust value score,
  quality-value classification, position sizing (`position_size`).
- `pipeline/resort_marketstack_screens.py` — Re-sorts the "Stocks" (movers) and "Reversal"
  screens from Marketstack's accumulated closes after each collection run (`build_rows`,
  `rank_movers`, `rank_reversal`, `run`).
- `pipeline/risk_metrics.py` — Shared return/risk arithmetic used by both stock and ETF models
  (`daily_returns`, `sharpe_ratio`, `sortino_ratio`, `beta_vs_benchmark`, `max_drawdown`).
- `pipeline/run_strategy_backtests.py` — Orchestrates all seven options-strategy screens' own
  walk-forward backtests in one script (`run`).
- `pipeline/score_calibration.py` — Builds the (currently `insufficient_data`) score-bucket
  historical-calibration table, gated on real closed forward-return observations
  (`adaptive_buckets`, `build_report`).
- `pipeline/scorer.py` — Legacy political/valuation scoring core: band scoring
  (`band_score`, `higher_is_better_score`, `range_score`), Altman Z, and the
  `CrossSectionalNormalizer` challenger class, `sector_percentile_ranks`.
- `pipeline/scoring_v2.py` — Versioned structural/timeliness scoring layer that publishes
  `None` (not a fabricated neutral) when no timeliness inputs resolve (`build_v2_analysis`).
- `pipeline/screen_inputs.py` — Shared, network-free inputs (universe rows, cached price/
  statement history, PIT observations, cross-sectional percentiles) for the three universe-
  wide research screens (`universe_rows`, `backtest_entry`, `cross_sectional_percentiles`).
- `pipeline/sec_edgar.py` — Small SEC EDGAR Form 4 client (`SecEdgarClient`, `parse_form4`,
  `entity_name_matches`).
- `pipeline/seed_mock_data.py` — Generates realistic mock `trades.json`/`prices.json`/
  `news.json`/`politicians.json` for network-free sandbox runs (`make_trades`, `main`).
- `pipeline/shadow_portfolios.py` — Builds the public shadow-portfolio report from immutable,
  dated selections appended over time, net of declared spread/slippage
  (`selections_from_payload`, `append_payload`, `matched_returns`).
- `pipeline/signal_report.py` — Isolated comparison report for the signal-correction
  challenger variants (`build_signal_report`, `write_signal_report`).
- `pipeline/stability_report.py` — Rank-turnover and score-stability diagnostics over the
  scored PIT-store refresh log (`rank_turnover`, `decompose_score_delta`,
  `compute_stability_report`).
- `pipeline/strategy_diagnostics.py` — Strategy-level diagnostics absent elsewhere: expectancy,
  profit factor, R-multiples, regime attribution, from the committed monthly backtest
  (`expectancy`, `profit_factor`, `regime_attribution`, `build_report`).
- `pipeline/technical_indicators.py` — Four deliberately-chosen technical indicators spanning
  distinct economic families (`moving_average_slope`, `relative_strength_index`,
  `bollinger_percent_b`, `on_balance_volume_slope`, `technical_extended_score`).
- `pipeline/theme_signals.py` — Network-facing theme-exposure signal collection from free SEC
  EDGAR data (segment revenue, filing-keyword density, transcript salience, customer overlap,
  hyperscaler capex, backlog growth) (`EdgarThemeSignals`).
- `pipeline/themes.py` — Pure, unit-tested theme-exposure scoring with hardcoded zero-weight
  on price momentum to avoid performance-chasing (`score_theme_exposure`,
  `build_theme_screen`, `expand_theme_candidates`).
- `pipeline/turnover_control_matrix.py` — Measures the turnover-control challengers (from
  `portfolio_construction.py`) against the champion offline, over cached price history
  (`run_variant`, `build_report`).
- `pipeline/validate_data.py` — Validates public JSON artifacts against versioned JSON Schemas
  plus cross-file invariants (theme-screen anti-hype guardrails, enrichment coverage, ETF peer
  groups) (`validate`, `theme_screen_errors`).
- `pipeline/validation_framework.py` — Immutable shadow snapshots and legal manual external-
  ranking imports (`append_immutable_snapshot`, `import_external_rankings`,
  `walk_forward_splits`, `spearman_rank_ic`, `block_bootstrap_excess`).
- `pipeline/valuation_history.py` — Reconstructs each company's own daily valuation-multiple
  history from the backtest cache (price + as-reported statements), reporting-lag-aware
  (`multiple_series`, `point_in_time_fundamentals`).
- `pipeline/xbrl_dimensions.py` — Reads dimensional (segmented) XBRL facts directly from a
  filing document, since `companyfacts`/`companyconcept` drop segment dimensions
  (`parse_contexts`, `dimensional_facts`, `facts_on_axis`).
- `pipeline/yahoo_estimates.py` — Analyst-estimate-change data reduced to what the catalyst/
  conviction models read (revision breadth, EPS trend, upgrade/downgrade net, price-target
  change) (`revision_breadth`, `collect_estimate_detail`).
- `pipeline/yahoo_news.py` — Per-symbol Yahoo company news normalized for the event layer,
  with lexicon-based direction inference and no fabricated neutral reading
  (`normalize_article`, `headline_direction`, `fetch_company_news`).

## pipeline/sleeves/ (research-contract "sleeve" interface)

- `pipeline/sleeves/__init__.py` — Sleeve interface contract (`empty_sleeve`,
  `ineligible_sleeve`); only the value sleeve is implemented, the other 13 specified sleeves
  are intentionally not built.
- `pipeline/sleeves/_fundamentals.py` — Shared wrapper for sleeves built directly from one or
  more `scorer.py` fundamental categories (`score_fundamentals_family_sleeve`); not itself a
  public sleeve.
- `pipeline/sleeves/growth.py` — Growth sleeve wrapping `scorer.py`'s "growth" category
  (`score_growth_sleeve`); growth acceleration/persistence/ROIIC are absent, not approximated.
- `pipeline/sleeves/quality.py` — Quality sleeve wrapping profitability/financial-health/
  capital-allocation/accounting-quality categories (`score_quality_sleeve`).
- `pipeline/sleeves/value.py` — Value sleeve wrapping `scorer.py`'s "valuation" category
  (`score_value_sleeve`), the one worked example proving the sleeve pattern.

## pipeline/validation/ (prospective scoring validation)

- `pipeline/validation/__init__.py` — Package docstring only.
- `pipeline/validation/ic_harness.py` — Prospective full-universe information-coefficient
  validation harness; only grades scores recorded before their forward returns existed
  (`append_refresh`, `read_snapshots`, `sector_residual_returns`, `research_trial_count`).
- `pipeline/validation/trading_calendar.py` — Real trading-session calendar derived from
  committed SPY daily history, replacing calendar-day arithmetic for horizon math
  (`TradingCalendar`, `default_calendar`).

## pipeline/tests/ (111 pytest files)

One-to-one (mostly) coverage of the modules above, run via `PYTHONPATH=pipeline python -m
pytest pipeline/tests -q` in CI. Notable/large suites: `test_advisor_engine.py` (62 tests),
`test_options_common.py` (42), `test_fetch_advisor.py` (46), `test_fetch_etfs.py` (39),
`test_fundamentals_extended.py` (39), `test_scorer.py` (38), `test_themes.py` (34),
`test_portfolio_construction.py` (33), `test_cache_and_providers.py` (33),
`test_canonical_v2.py` (30), `test_build_institutional_screen.py` (29),
`test_evidence_events.py` (29), `test_sec_edgar.py` (27), `test_build_advanced_options_screen.py`
(27), `test_evaluation.py` (27), `test_yahoo_news.py` (25), `test_recommendation_policy_v2.py`
(25), `test_build_vertical_spread_screen.py` (25), `test_plausibility.py` (24). Smaller
targeted suites include `test_edgar_pit.py` (point-in-time filing/amendment/tag-heterogeneity
behavior), `test_filer_cohorts.py` and `test_peer_coverage_audit.py`/
`test_peer_claims_regression.py` (survivorship and peer-claim regression guards),
`test_leaderboard_audit.py` (does the leaderboard rank companies or data volume),
`test_pit_derive.py`/`test_pit_market.py`/`test_pit_shares.py`/`test_pit_store.py`
(point-in-time correctness), `test_sec_edgar_contract.py` and `test_universe_config.py`
(structural/config guards), `test_band_comparison.py` and `test_feature_statistics.py`
(Phase 5/5b research-harness statistics). Every other file is `test_<module>.py` testing the
identically-named `pipeline/<module>.py` file described above.

## pipeline/schemas/ (JSON Schema, read by `validate_data.py`)

`advisor.schema.json`, `etfs.schema.json`, `picks.schema.json`, `trades.schema.json`,
`news.schema.json`, `prices.schema.json`, `status.schema.json`, `signals.schema.json`,
`politicians.schema.json`, `recommendation-v5.schema.json` — Draft 2020-12 JSON Schemas that
`pipeline/validate_data.py` validates the corresponding published `public/data/*.json` file
against, plus cross-file invariant checks layered on top in Python.

## pipeline/config/*.json (configuration, read by pipeline code)

- `settings.json` — The master tunable-config file: model metadata, `normalization_mode`,
  `challengers` (cross-sectional normalization, etc.), `confidence`/`validation` thresholds,
  `position_risk`, `watchlist_setup`/`watchlist_price_targets`, `portfolio_analytics`,
  `factor_data`, `explainability`, `alerts` config — also imported directly by several
  `src/lib/*.js` files as the single source of truth for UI-side thresholds.
- `universe.json` — ETF watchlist, retirement-core fund list, and ETF-scoring config.
- `advisor_universe.json` — The stock research universe: publish/extended limits, portfolio
  symbols, and the full symbol list `fetch_advisor.py` scores.
- `metric_registry.json` — Canonical metric inventory/definitions/units used by
  `canonical_metrics.py`.
- `applicability_matrix.json` — Per-business-profile metric applicability/suppression rules.
- `business_profiles.json` — Business-profile classification rules and per-ticker overrides
  used by `canonical_metrics.classify_profile`/`peer_groups.peer_group`.
- `provider_reconciliation.json` — Cross-provider field reconciliation preference order.
- `feature_registry.json` — Generated (by `build_feature_registry.py`) registry of every
  scoring feature's family/usage classification.
- `recommendation_policy_v2.json` — Full config for `recommendation_policy_v2.py`'s shadow
  policy: score matrix, confidence gates, critical fields, stop profiles, entry rules.
- `research_contract.json` — The research contract itself: universe definition, forecast
  targets, execution assumptions, champion/challenger governance rules.
- `research_models.json` — Momentum/tactical/quality-value model config plus promotion rules.
- `shadow_strategies.json` — Shadow-portfolio strategy definitions and comparison modes for
  `shadow_portfolios.py`.
- `screen_presets.json` — Registry of research-screen presets.
- `estimate_collection.json` — Estimate-collection schedule/history-policy config for
  `collect_estimates.py`.
- `early_session.json` — Gate/universe config for the capability-gated early-session module.
- `etf_benchmarks.json` — Per-ETF benchmark mapping/defaults, used by `live_etf_validation.py`
  and ETF comparison building.
- `institutional_managers.json` — Curated list of public 13F filer managers (style: active/
  passive/alternative) for `build_institutional_screen.py`.
- `committees.json` — Congressional committee-to-politician mapping (legacy `scorer.py`).
- `policy_map.json` — Sector-to-policy-flag mapping for the legacy political-score model.

---

## research/ (ad hoc audit/research harnesses — code)

- `research/audit_leaderboard.py` — Measures whether the published leaderboard ranks
  companies or ranks data-received volume (statement-enrichment correlation with rank)
  (`audit`, `main`); no network, no backtest needed.
- `research/audit_peer_coverage.py` — Measures which companies can never receive a peer claim
  under the 30-peer minimum, and argues the "obvious fix" (widening to sector) is wrong
  (`coverage`, `main`).
- `research/bands.py` — Phase 5b: measures whether band-score cutoffs destroy raw-metric
  information versus the same metric read raw (`infer_direction`, `verdict`, `run`).
- `research/baselines.py` — Phase 4: point-in-time baseline factor returns (value, quality,
  profitability, momentum, low-accruals) before any optimization (`value_score`,
  `quality_score`, `summarise`, `decile_risk`).
- `research/candidate.py` — Phase 6b: a candidate ranking designed on one half of history and
  tested on the untouched other half, with the selection rule fixed before the test half is
  read (`select`, `run`, `_verdict`).
- `research/composite.py` — Phase 6: measures the live ValueSignal composite (real
  `scorer._band_valuation_score`, not a reimplementation) against the Phase 4 baselines
  (`snapshot`, `run`).
- `research/features.py` — Phase 5: per-metric information coefficient, decile ladders
  (return and Sharpe), and correlation clustering across all 32 scored metrics (`run`).
- `research/rank_statistics.py` — Load-bearing rank statistics with no external deps
  (SciPy-free inverse-normal via bisection): `ranks`, `spearman`, `summarise_series`,
  `bonferroni_threshold`.
- `research/audit/CURRENT_MODEL_AUDIT.md` — **PRIOR AUDIT ARTIFACT, not independently
  verified in this pass.** Narrative audit of the current scoring model's defects (referenced
  throughout the pipeline code, e.g. constant-layer and confidence-naming findings).
- `research/audit/PIPELINE-MAP.md` — **PRIOR AUDIT ARTIFACT, not independently verified.**
  Narrative map of the pipeline's data flow.
- `research/STATE.md` — **PRIOR AUDIT ARTIFACT.** Persistent state/context doc "written for a
  future session that has lost all context" — summarizes the audit-and-rebuild engagement.
- `research/results/*.md` (`LIVE-LEADERBOARD-AUDIT.md`, `PHASE4-BASELINES.md`,
  `PHASE5-FEATURES.md`, `PHASE5B-BANDS.md`, `PHASE6-COMPOSITE.md`, `PHASE6B-CANDIDATE.md`,
  `README.md`) — **PRIOR AUDIT ARTIFACTS.** Generated narrative write-ups of each research
  harness's output; each has a matching committed `*.json` result file alongside it.

---

## src/ — frontend (React + Vite)

### src/ root

- `src/App.jsx` — Top-level router: route table, mobile nav (`MOBILE_NAV`), lazy-loaded pages
  (Dashboard eager, everything else `lazy(() => import(...))`).
- `src/main.jsx` — React entry point; wraps `App` in `PreferencesProvider` +
  `BrowserRouter` + `StrictMode`.
- `src/App.test.jsx` — Asserts the mobile nav contract (labels, centered "Report" tab).
- `src/test/setup.js` — Vitest/jsdom global test setup (referenced by `vite.config.js`).

### src/components/ (55 files, ~28 components + their `.test.jsx` siblings)

- `ActionGuidance.jsx` — `ActionPill` chip + `ActionGuidance` panel rendering a
  recommendation's action/reasons.
- `AlertBadge.jsx` — Nav-bar bell icon with unread-alert-count badge, wraps `useAlerts`.
- `AnalysisLayers.jsx` — Renders structural/timeliness layers; explicitly shows "unavailable"
  rather than a fabricated score when a layer has no effective score.
- `AnimatedNumber.jsx` — Counts a displayed number up/down to a new target via
  `requestAnimationFrame` when `value` changes.
- `BacktestSummary.jsx` — Renders a strategy's backtest stats block from a fetched JSON file.
- `Bits.jsx` — Small shared primitives: `Tier`, `RatingBadge`, `ScoreBreakdown`,
  `MetricPills`, `Move`, `Lag`.
- `BuyingTheDipChart.jsx` — 52-week range bar with `dipWatch`'s buy-zone shaded and current
  price marked.
- `CompanyLogo.jsx` — Company logo `<img>` with ticker-initials fallback on load error.
- `DataFreshnessIndicator.jsx` / `DataQualityDebugView.jsx` — Timestamp-staleness badge; debug
  panel listing excluded stocks and exclusion reasons.
- `DataStatus.jsx` — Global data-freshness status; `freshness()` (>=36h stale) and
  `DataStatus()` component.
- `DipWatchBadge.jsx` — Renders `dipWatch()`'s near-floor/in-range/recovering status.
- `ETFComparisonChart.jsx` / `ETFComparisonPanel.jsx` — Growth/relative-strength/drawdown
  chart views over `parseEtfComparison` data, and the data-fetching wrapper around it.
- `ErrorBoundary.jsx` — Class component catching render-time exceptions so one page's crash
  doesn't blank the whole app.
- `FirebaseLoginModal.jsx` — Multi-profile (family-member) sign-in modal using
  `FirebaseAuthContext`.
- `GrowthChart.jsx` — Dollar-value comparison line chart drawn as hand-rolled inline SVG (no
  chart library), theme-token-aware.
- `Icons.jsx` — Inline SVG icon set (`Icon` component, `paths` map).
- `InfoTag.jsx` — `<details>/<summary>`-based "what does this measure" tooltip affordance.
- `MetricSections.jsx` — Grouped extended-metric display config (`SECTIONS`).
- `MobileSheet.jsx` — `MobileSheet` bottom-sheet modal + `ResponsiveControlPanel` wrapper.
- `MobileVirtualList.jsx` — Windowed virtualized list via `@tanstack/react-virtual`.
- `ModelVersionFooter.jsx` — Footer showing published model semantic version/commit/config
  hash.
- `PasswordChangeModal.jsx` — Password-change form using `FirebaseAuthContext`.
- `PerformanceMetrics.jsx` — Renders Sharpe/Sortino/etc. with tone coloring
  (`performanceMetricTone`).
- `PortfolioChartOverlay.jsx` — Period-return summary overlay for portfolio charts
  (`portfolioPeriodCopy`).
- `PortfolioMoveExplanation.jsx` — Per-holding contributor breakdown of a portfolio's daily
  move.
- `PortfolioReturnSummary.jsx` — Strategy (Modified Dietz) vs. simple return summary cards.
- `ProjectionFanChart.jsx` / `ProjectionPanel.jsx` — p10/p25/p50/p75/p90 fan-chart SVG and its
  surrounding panel for the retirement projection.
- `PullToRefreshIndicator.jsx` — Visual indicator for the `usePullToRefresh` gesture.
- `RecommendationShadowPanel.jsx` — Renders the v2 shadow recommendation (legacy + company +
  position states) without collapsing them into one verdict.
- `ResearchEvidence.jsx` — Renders committed research-evidence artifacts (benchmark, factor,
  cost, calibration, experiment, enrichment panels); reports "not generated" rather than
  defaulting.
- `ResearchRadarChart.jsx` — Radar/spider chart of a stock's category scores
  (`radarEntries`), pinned to one model's categories to avoid mixing scales.
- `ResultCards.jsx` — Generic virtualized result-card list renderer for research screens.
- `ScoreBandView.jsx` — Groups stocks into A-E tier bands instead of exact ranks.
- `ScoreExplainability.jsx` — `FactorBars` + attribution waterfall rendering of
  `explainability.py`'s output.
- `SetupQualityBreakdown.jsx` — Renders watchlist setup-quality score/subscores.
- `Sparkline.jsx` — Minimal inline-SVG sparkline (`pathFor`).
- `StockCard.jsx` / `StockCardGrid.jsx` — Mobile-first expandable stock card and its
  card/band-view grid + `ViewModeSwitcher`.
- `StockDetailModal.jsx` — The full stock detail sheet: tabs, KPIs, coverage dial, charts,
  shadow-recommendation panel.
- `WatchlistToggleButton.jsx` — Star toggle adding/removing a ticker from the Firestore
  watchlist, seeding price targets on add.
- (each of the above except `Icons`/`InfoTag`/etc. has a matching `*.test.jsx` unit-test file
  exercising its exported pure functions/render behavior.)

### src/pages/ (24 pages + `.test.jsx` siblings + `screenNavigation.test.jsx`)

- `Alerts.jsx` — Alert-rule management UI (create/list rules, push-notification opt-in) over
  `useAlerts`.
- `CongressTrades.jsx` — Congressional STOCK Act disclosure screen page (flag chips, filters).
- `Dashboard.jsx` — Home/"Financial Report" landing page: portfolio value, daily change,
  Planning success probability, action-needed count.
- `Diversification.jsx` — Sector/factor-tilt breakdown of the current portfolio
  (`factorAnalytics`, `portfolioAnalytics`).
- `EarlySessionResearch.jsx` — Renders early-session capability-gate status per screen
  (Available/Conditional/Unavailable).
- `FastGrowthScreen.jsx` — "Emerging growth"/"Breakout in progress" screen page, deliberately
  labeled `research_status: prospective_unvalidated`.
- `Finances.jsx` — Budget/retirement-account/projection planning page.
- `Glossary.jsx` — Plain-language term definitions, hydrated from `advisor.json` metadata.
- `Insights.jsx` — Portfolio insight cards (streaks, milestones, benchmark comparison).
- `InstitutionalActivity.jsx` — 13F institutional accumulation/distribution screen page.
- `LiveValidation.jsx` — Renders the IC-harness validation status page (periods
  accumulated/required, accumulating vs. eligible).
- `Methodology.jsx` — Written scoring-methodology page; category descriptions read from
  `useData`, guarded by `check_ui_weights.py` against hardcoded weight literals.
- `OptionsScreen.jsx` — Generic options-strategy screen renderer (used across the options
  strategies).
- `Picks.jsx` — Bucket-planner picks page: model selection, sort options, ETF/stock
  normalization (`bucketWhy`, `normalizeEtf`).
- `Planning.jsx` — Retirement-planning simulator page (`SequenceRiskPanel`, success-band
  gauge), driving `useProjectionSimulation`.
- `PolicyRadar.jsx` — News/policy-radar feed page combining research + screen-universe rows.
- `Portfolio.jsx` — Main portfolio holdings table page with recommendations, stop-loss levels,
  growth charts.
- `ResearchScreen.jsx` — Shared research-screen shell: `SCREEN_NAV`/`OPTIONS_NAV` route
  config, `ScreenNavigation`/`OptionsNavigation` sub-nav components.
- `Search.jsx` — Cross-dataset ticker/company search with recent-search history.
- `Settings.jsx` — Theme/accent/widget preference settings page.
- `ShadowPortfolios.jsx` — Renders the shadow-portfolio report (strategy return metrics,
  collection-gate states).
- `StrategyScreen.jsx` — Generic options-strategy-screen page driven by
  `strategyScreenConfigs.js`.
- `ThemeExposureScreen.jsx` — Theme-exposure screen page (`ThemeCard`, `ThemeTable`).
- `Watchlist.jsx` — Watchlist page with price-target editor and inverse-volatility allocation
  suggestions.

### src/lib/ (~90 files: business logic + hooks + matching `.test.js(x)` files)

- `FirebaseAuthContext.jsx` — `AuthProvider`/`useAuth`; multi-profile family auth, password
  change, `FAMILY_THEMES`.
- `PreferencesContext.jsx` — `PreferencesProvider`/`usePreferences`; UI prefs (accent, theme,
  widgets), `validatePreferences`, `formatPreferenceMoney`.
- `afterHoursQuotes.js` — Rolls per-symbol post-market quotes into a portfolio-level after-
  hours move (`afterHoursPortfolioReturn`, `liveTodayPortfolioReturn`).
- `age.js` — Birthdate parsing/age calculation (`calculateAge`, `isValidBirthDate`).
- `alertRules.js` — Alert-rule types/normalization/validation/labeling
  (`normalizeAlertRule`, `validateAlertRule`).
- `bullBearScore.js` — Weighted bull/bear composite from fundamentals/market-behavior/news/
  risk components (`bullBearScore`).
- `confidenceGate.js` — The one rule gating whether a row's evidence is strong enough to carry
  an action label (`confidenceBand`, `isActionable`, `shrinkToConfidence`).
- `dipWatch.js` — Buy-the-dip floor/recovery price-band estimate blending 60-day and 52-week
  reads (`dipWatch`, `weekRange`).
- `entryTiming.js` — Buy-now-or-wait verdict layered on `dipWatch` + stance + coverage
  (`entryTiming`).
- `etfComparison.js` — Parses/validates the ETF comparison schema-4 payload
  (`parseEtfComparison`, `comparisonLines`).
- `evidenceStrength.js` — Legacy "evidence strength" (0-1) calculator distinct from the
  model's own confidence field (`calculateEvidenceStrength`, `getEvidenceBreakdown`).
- `factorAnalytics.js` — Six-factor (Fama/French + momentum) OLS regression and theme-
  exposure aggregation (`factorRegression`, `aggregateThemeExposure`).
- `fidelityConnectorStub.js` — **Unimplemented design doc as code**: Fidelity/Plaid brokerage
  connector architecture, cost estimates; no real integration.
- `financeMigrations.js` — Schema migration for saved finance settings/goals
  (`migrateFinanceSettings`, `migrateFinanceGoal`).
- `financeSplit.js` — Budget income/expense totals and proportional pool splitting
  (`summarizeBudget`, `splitAmount`).
- `firebase.js` — Firebase app/auth/Firestore initialization (persistent local cache).
- `formatters.js` — Shared `money`/`signedPct`/`ratio`/`humanDate` formatters.
- `fundsAllocation.js` — Convex (score^power) allocation of available funds across ranked rows
  (`allocateFunds`).
- `labelDistribution.js` — Percentile-based stance-label distribution calibrated to the
  scored universe (`calculateLabel`, `recalculateLabels`).
- `modeConfidence.js` — Per-ranking-mode confidence computed only from the inputs that mode
  actually reads (`MODE_INPUTS`, `modeConfidence`, `allModeConfidence`).
- `newsSort.js` — News-list sort options/comparator (`sortNews`, `nextNewsSort`).
- `nightlyRefresh.js` — Pure "refresh once a day at/after 9pm local" boundary math
  (`isRefreshDue`, `msUntilNextBoundary`).
- `pipelineGuardrails.js` — Client-side data-quality validation/exclusion-reason reporting
  (`validateStock`, `validateStockBatch`, `formatValidationReport`).
- `portfolioAnalytics.js` — Large analytics module: benchmarks, enrichment, holdings series,
  performance metrics, risk decomposition, correlation diversification (`enrichPortfolio`,
  `performanceMetrics`, `portfolioRiskDecomposition`, `BENCHMARKS`).
- `portfolioAttribution.js` — Single-factor (CAPM-style) daily-move attribution into market vs.
  idiosyncratic components (`explainPortfolioMove`).
- `portfolioExposure.js` — Position/sector concentration threshold checks
  (`assessPortfolioExposure`).
- `portfolioPerformance.js` — Portfolio-vs-benchmark-DCA comparison series
  (`portfolioVsBenchmark`, `benchmarkAlternative`, `selectPortfolioHistorySeries`).
- `portfolioPosition.js` — Builds/merges the ticker→price-data lookup used across pages
  (`buildPortfolioPriceData`, `mergePortfolioQuotes`, `normalizePortfolioPosition`).
- `portfolioSectorTilt.js` — Sector-underweight + peer-relative growth/risk blend for the
  bucket planner's sector-awareness (`sectorOpportunity`, `sectorBoost`).
- `portfolioSort.js` — Portfolio-table sort options/comparator.
- `portfolioStyleTilt.js` — Classifies holdings/candidates into research-vs-catalyst style
  lanes for portfolio-aware fund allocation (`currentStyleTilt`, `styleBoost`).
- `positionRisk.js` — Volatility-scaled stop-loss rules referenced to post-purchase high-water
  mark (`stopLossLevels`, `averageTrueRange`, `withStopLoss`).
- `projectionEngine.js` — Monte-Carlo retirement projection engine: return-target config,
  sparse-history extension, benchmark-centered history correction
  (`simulateProjection` used via the worker, `extendSparsePortfolioHistory`,
  `benchmarkCenteredSparseHistory`).
- `pushNotifications.js` — Web Push subscription registration into Firestore
  (`enablePushNotifications`, `pushCapability`).
- `rankingModels.js` — Nine distinct ranking models (long-term, catalyst, reversal, trend,
  etc.), each declaring its own inputs rather than one score serving all questions
  (`RANKING_MODELS`, `buildPeerIndex`, `moderationScore`, `thesisBreak`).
- `recommendation.js` — Single source of truth for hold/watch/trim/sell guidance, trusting the
  pipeline's own verdict when present (`getRecommendation`, `actionStyle`).
- `referenceCashFlows.js` / `referencePortfolio.js` — Hardcoded user-provided Fidelity cash-
  flow history and brokerage snapshot used as ground truth for reconciliation
  (`fidelityProjectionBaseline`, `planReferencePortfolioSync`).
- `researchRating.js` — Converts the 0-100 score into a -5..+5 percentile-within-pool rating
  (`buildRatingContext`, `researchRating`).
- `researchScreens.js` — Frontend-only research-screen ranking formulas (value turnarounds,
  buying-the-dip, momentum, reversal, breakout, emerging growth)
  (`rankMomentum`, `rankReversal`, `rankEmergingGrowth`, `rankBreakoutInProgress`).
- `retirementLimits.js` — 2026 IRS contribution-limit table and lookup
  (`getAnnualLimit`, `ACCOUNT_TYPES`).
- `schemaMigrations.js` — Read-time additive-only schema migration for pipeline JSON snapshots
  (`migrate`, `datasetFor`, `ADVISOR_SCHEMA_VERSION`).
- `scoreBands.js` — A-E tier-band grouping/labeling utilities (`getScoreBand`,
  `groupByScoreBand`, `getScoreBandDisclaimer`).
- `securityStub.js` — **Unimplemented design doc as code**: security roadmap/checklist/threat
  model for future V2 planning.
- `sellWatchLogic.js` — Two-of-three-factor-agreement sell/watch/trim rule
  (`assessFundamentals`, `assessTechnicals`, `assessSentiment`,
  `getSellWatchRecommendation`).
- `sentimentEngine.js` — News-sentiment categorization (polarity, intensity, persistence,
  source quality, materiality) (`categorizeNews`, `calculateSentimentImpact`).
- `strategyScreenConfigs.js` — Config table (`STRATEGY_SCREENS`) driving the six generic
  options-strategy screen pages.
- `traderInsights.js` — Portfolio-tracking insight helpers: streaks, milestones, trade stats,
  purchase timing signal (`tradeStats`, `valueStreak`, `beatMarketStreak`).
- `useAdvisorRefresh.js` — Hook polling the site's "Refresh" button workflow-dispatch status
  (`useAdvisorRefresh`), with separate timeouts for full vs. rescore-only runs.
- `useAlerts.js` — Firestore-backed alert rules/events hook (`useAlerts`).
- `useBodyScrollLock.js` — Locks body scroll behind an open modal on iOS Safari
  (`useBodyScrollLock`).
- `useData.js` — Core data-fetching hook with localStorage caching and schema migration
  (`useData`, `clearCachedData`, `formatElapsed`).
- `useFirebaseFinances.js` / `useFirebasePortfolio.js` — Firestore-backed finance settings/
  budget and portfolio-position hooks.
- `usePortfolio.js` — Legacy localStorage-backed portfolio hook (references a since-removed
  `AuthContext`; appears superseded by `useFirebasePortfolio`).
- `usePortfolioQuotes.js` — Cached live-quote-fetching hook synced to the nightly-refresh
  boundary (`usePortfolioQuotes`).
- `usePortfolioTracking.js` — Firestore daily-snapshot portfolio-tracking hook
  (`usePortfolioTracking`, `marketDate`).
- `useProjectionSimulation.js` — Runs `simulateProjection` off the main thread via
  `projectionWorker.js` (`useProjectionSimulation`).
- `usePullToRefresh.js` — Custom pull-to-refresh gesture hook with resistance
  (`usePullToRefresh`).
- `useScreenRefresh.js` — Hook for triggering the slower research-screen collector workflows
  (13F, Congress) independently of the main advisor refresh (`useScreenRefresh`).
- `useWatchlist.js` — Firestore-backed watchlist hook with legacy-localStorage migration
  (`useWatchlist`).
- `valueGrowthScore.js` — "Most undervalued" blended sort score for the Picks column sort
  (`buildValueGrowthContext`, `valueGrowthScore`).
- `watchlistGuidance.js` — Watchlist setup-quality scoring and inverse-volatility position
  sizing (`watchlistGuidance`, `inverseVolatilityAllocations`).
- `watchlistPriceTargets.js` — Volatility-scaled dip-buy/good-buy price-target suggestions
  (`suggestDipBuyPrice`, `suggestGoodBuyPrice`, `suggestPriceTargets`).

### src/workers/

- `projectionWorker.js` — Web Worker running `simulateProjection` off the main thread,
  message-driven (`self.onmessage`).

---

## netlify/functions/ (see Runtime topology above for full descriptions)

- `alert-push.mjs`, `portfolio-prices.mjs`, `refresh-data.mjs` — the three serverless
  endpoints.

## tests/functions/ (Vitest unit tests for the Netlify functions, top-level `tests/` dir)

- `tests/functions/alert-push.test.js` — Tests `buildPushPayload` (multi-event grouping) and
  `isQuietTime` (overnight quiet-hours window, timezone-aware) from `alert-push.mjs`.
- `tests/functions/portfolio-prices.test.js` — Tests `parseSymbols`/`fetchPortfolioQuotes`
  from `portfolio-prices.mjs`.
- `tests/functions/refresh-data.test.js` — Tests `parseRequestBody`/`workflowProgress`/
  `locateDispatchedRun` from `refresh-data.mjs`.

## scripts/ (Node maintenance/evidence scripts, run via `npm run ...`)

- `color-accessibility-check.mjs` — Computes WCAG contrast ratios for the light/dark CSS
  color-token pairs in `src/styles/variables.css` (`contrast`, `simulate`, `luminance`).
- `factor-regression-evidence.mjs` — Builds a sample blended-ETF portfolio series and runs it
  through `factorAnalytics.factorRegression` against the committed Fama/French data.
- `generate-app-breakdown.mjs` — Regenerates `APP-COMPLETE-BREAKDOWN.md` from live repo state
  (package.json, advisor/etf/factor data, App.jsx routes, PIT-store row counts, git commit).
- `hygiene-evidence.mjs` — Runs `npm audit --json`, inspects `dist/` bundle chunk sizes, and
  writes a hygiene evidence report.
- `mobile-screenshots.mjs` — Playwright-driven mobile screenshot capture (light/dark, multiple
  widths) of key pages into `docs/mobile-screenshots/`.
- `projection-spread-evidence.mjs` — Before/after comparison of the legacy vs.
  benchmark-centered sparse-portfolio-history projection extension.

---

## .github/workflows/*.yml (refresh/scoring-related; see Runtime topology for schedules)

`refresh-advisor.yml`, `congress-trades.yml`, `institutional-13f.yml`,
`marketstack-premarket.yml`, `backfill-pit-fundamentals.yml`, `measure-survivorship.yml`,
`demo-data.yml`, `ci.yml` — described above.

---

## Top-level configuration

- `package.json` — npm scripts (see Runtime topology) plus React/Vite/Firebase/Vitest
  dependency set.
- `vite.config.js` — Vite + `@vitejs/plugin-react`; custom Rolldown `codeSplitting.groups`
  isolating Firebase submodules (`firestore`, `webchannel`, `auth`) into separate chunks
  (sizes read from `pipeline/config/settings.json`'s `build.firebase_chunk_max_bytes`);
  Vitest config (`jsdom`, `src/test/setup.js`).
- `firebase.json` — Minimal Firebase project config, points `firestore.rules` at the rules
  file below (no Hosting/Functions config — the frontend deploys via Netlify).
- `firestore.rules` — Per-user-UID-scoped read/write rules for `users`, `profiles`,
  `portfolios/{userId}/**`, `finances/{userId}/**`, `alerts/{userId}/**`,
  `watchlists/{userId}/**`, and an auth-gated `backtestSignals` collection.
