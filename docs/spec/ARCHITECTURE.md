# ValueSignal — Architecture Specification

**Status: draft in progress.** Sections 4, 5, 6, 8, and part of 10 are complete and
independently verified against current code (branch `claude/valuesignal-spec-audit-qf2wni`,
HEAD as of 2026-08-10, working tree matching commit `e312488`). Sections 1–3, 9, and 12 are
pending synthesis from a parallel research pass and are marked accordingly below. Do not treat
this file as finished; it is being assembled incrementally and will be redeployed in place.

Every factual claim below carries a `path/to/file.py:line` citation to code read directly in
this session, not copied from this repository's own internal audit documents
(`research/audit/CURRENT_MODEL_AUDIT.md`, `research/audit/PIPELINE-MAP.md`), which are dated
2026-08-09 and are confirmed to be one or more fix-commits behind current code. Those documents
were used only for orientation — every specific number or line reference from them was
re-verified against the live file before being repeated here.

---

## 0. A note on system state

This system is under active, same-day development. Between the internal audit's date
(2026-08-09) and this document's compilation (2026-08-10), at least the following fix commits
landed (`git log --oneline`, confirmed present in this branch's history):

| Commit | Effect |
|---|---|
| `cb3cc53` | Peer-relative claims now require ≥30 valid peers or publish nothing; alphabetical tie-break removed |
| `ac24342` | Fabricated `timeliness.effective_score = 50.0` deleted; layer now publishes `null` when no input resolves; a guard (`layer_health.assert_layers_vary`) fails the publish path if a layer ever becomes constant across the universe again |
| `cd581b5` | The legacy `confidence` field renamed to `data_coverage` throughout the champion path, to stop the completeness ratio being read as a reliability score |
| `0e0a9ad` | The live scorer's per-sector metric suppression now reads the same `applicability_matrix.json` registry the shadow path reads, replacing two standalone sector-string heuristics (`FINANCIAL_EXEMPT`, `TANGIBLE_BOOK_SECTORS`) that disagreed with it |
| `790d0da` | The live deterioration-guidance rule (`action_for`) no longer treats a missing input as "no concern" (`... or 0`, `... or 99` patterns removed); missing inputs are now reported in an `unmeasured` list instead |

Four defects this task's brief lists as "already-confirmed" — the 14-name peer percentile, the
`EARNINGS_TIMELINESS` 50/100 default, the cross-path confidence disagreement, and insurer DSO
surviving suppression while P/B and D/E are nulled — map directly onto commits `cb3cc53`,
`ac24342`, `cd581b5`, and `0e0a9ad` respectively, and no longer reproduce in their original form
against current code and the current published artifact. Section 10 documents what I verified
instead: the residual, differently-shaped version of the confidence issue, and defects found
independently during this pass. See `docs/spec/TRACE_THG.md` for the full verification trail
against a live example (THG).

---

## 1. System overview

**ValueSignal** is one research module inside a larger personal-finance PWA ("Dash", this
repository) that also covers portfolio tracking, retirement projection, options-strategy
screens, and a Congressional/13F trading tracker. ValueSignal specifically is the module that
scores a universe of equities on a 0-100 "research score" and attaches a HOLD/WATCH/TRIM/SELL
recommendation, published as `public/data/advisor.json` (25.8 MB as committed, confirmed by
direct `wc -c` this session) and rendered across 12+ React pages (`Watchlist.jsx`,
`Dashboard.jsx`, `Picks.jsx`, `Insights.jsx`, `StrategyScreen.jsx`, `PolicyRadar.jsx`,
`Glossary.jsx`, `OptionsScreen.jsx`, `Diversification.jsx`, `ThemeExposureScreen.jsx`,
`Finances.jsx`, `Search.jsx`, `Methodology.jsx` — confirmed by grepping `useData('advisor.json')`
call sites across `src/pages/`).

**Full path from a scheduled run to a rendered number:**

1. A GitHub Actions workflow fires on a cron schedule or manual dispatch — the primary one is
   `.github/workflows/refresh-advisor.yml`, `cron: '7 11,12,16,17,19,20 * * 1-5'` (weekdays,
   ET-market-hours-aligned, ~6×/day), also triggerable via `workflow_dispatch` with modes
   `data-only` / `full-alpha` / `rescore-only` (per `docs/spec/FILE_INVENTORY.md`, "Runtime
   topology" — that document's citations were re-used, not re-derived, since it is already
   code-grounded).
2. The workflow runs `python pipeline/fetch_advisor.py` (entry point `run()`, currently starting
   near line 1313 — this line number shifted once already during this session's investigation of
   an earlier draft, confirming the file is under active modification; do not trust line numbers
   from any document older than this one), which pulls fundamentals/prices/estimates from Alpha
   Vantage and Yahoo, scores every name (`pipeline/scorer.py`, `pipeline/advisor_engine.py`,
   `pipeline/scoring_v2.py`, `pipeline/recommendation_policy_v2.py` — detailed in §4-§8 below),
   then a chain of further scripts (options-strategy screens, `rescore.py`,
   `build_quality_value_screen.py`, `build_tactical_screens.py`, `shadow_portfolios.py`,
   `validate_data.py`, `stability_report.py`, `evaluate_alerts.py`) before the workflow commits
   the refreshed `public/data/*.json` files back to the repository (chain per
   `FILE_INVENTORY.md`'s "Runtime topology" section, itself read from `refresh-advisor.yml`
   directly).
3. Two run modes are selected by the `ADVISOR_UNIVERSE_MODE` environment variable
   (`fetch_advisor.py:1337`, default `"full"`): full mode polls the entire configured universe
   and refits normalization distributions from scratch; fast mode reuses a prior fit and only
   re-polls a rotating subset (exact rotation mechanics: see §3, UNDETERMINED in that section
   whether independently re-verified this pass).
4. Alpha Vantage statement-enrichment calls are capped at 5 symbols per refresh regardless of
   universe size (`fetch_advisor.py:1343`, `ALPHA_ENRICH_LIMIT`, clamped `max(0, min(5, ...))`)
   — which symbols get the scarce enrichment slots is itself a scoring-feedback mechanism, see
   `docs/spec/TRACE_THG.md` §1 (`enrichment_selection.previous_top`).
5. Committing to `main` is the publish step — there is no separate deploy/build trigger observed
   this session beyond Netlify's normal git-push-triggered static rebuild (Netlify config/build
   hooks not independently re-verified this session; UNDETERMINED whether a webhook or polling
   deploy is in use).
6. The React app never talks to a database or API for this data at render time: `src/lib/useData.js`
   (`useData(file)`, confirmed by direct read, fetch call at line 95) does
   `fetch('${BASE_URL}data/${file}?v=${Date.now()}', { cache: 'no-store' })` — a plain static-file
   fetch of the committed, deployed JSON with a cache-busting query parameter, not a live query
   against the pipeline. Every page listed above calls `useData('advisor.json')` and reads fields
   directly out of the fetched object.
7. A logged-in user can also trigger an on-demand refresh from the UI (`src/lib/useAdvisorRefresh.js`,
   read in full this session): this calls the Netlify function `netlify/functions/refresh-data.mjs`,
   which dispatches the same `refresh-advisor.yml` workflow via the GitHub REST API
   (admin-authenticated) and polls its run status; the frontend distinguishes a `full`-scope
   refresh (95-minute timeout, `useAdvisorRefresh.js:10`) from a `fast` one (55 minutes, line 6)
   and a `rescore`-only reanalysis (5 minutes, line 15, since `pipeline/rescore.py` touches no
   network and finishes in under a minute per that file's own inline comment). On success the
   hook calls `reload()`, which re-runs the same static fetch described in point 6 — there is no
   separate "live" data path; a manual refresh is just a way to make the next static fetch see a
   newer file.

**Repo layout, purpose of each significant area** (full detail in `docs/spec/FILE_INVENTORY.md`,
which is already complete and code-grounded — summarized here, not repeated in full):

| Area | Purpose |
|---|---|
| `pipeline/*.py` (~100+ modules) | The Python research/scoring engine: data fetch, canonical-metric normalization, scoring (legacy `scorer.py` + shadow `scoring_v2.py`), recommendation policy, screen builders (options strategies, momentum, quality-value, tactical, institutional/Congressional), backtesting, and a substantial internal validation/audit toolkit (`evaluation.py`, `ic_harness.py`, `score_calibration.py`, `bias_report.py`, `stability_report.py`). |
| `pipeline/sleeves/` | Partial "research contract" sleeve interface — only the value sleeve is implemented; 13 of 14 specified sleeves are intentionally unbuilt (`pipeline/sleeves/__init__.py` docstring, per `FILE_INVENTORY.md`). |
| `pipeline/validation/` | `ic_harness.py` — prospective, look-ahead-safe information-coefficient validation; `trading_calendar.py`. |
| `pipeline/tests/` | 111 pytest files, largely one-to-one with `pipeline/*.py` modules (full inventory in §12). |
| `pipeline/config/*.json` | All tunable configuration: `settings.json` (master weights/thresholds), `advisor_universe.json` (the scored symbol list), `applicability_matrix.json` / `business_profiles.json` (sector suppression rules), `recommendation_policy_v2.json` (shadow policy config), and ~15 more (full list in `FILE_INVENTORY.md`). |
| `pipeline/schemas/` | Draft 2020-12 JSON Schemas that `validate_data.py` checks every published artifact against. |
| `research/` | A substantial ad hoc research/audit engagement (own Phase 4-6 factor-return, band-integrity, and out-of-sample candidate-ranking studies) plus prior narrative audit docs (`research/audit/CURRENT_MODEL_AUDIT.md`, `PIPELINE-MAP.md`, `STATE.md`) explicitly marked in `FILE_INVENTORY.md` as **not independently verified** by this document's own passes — see §12. |
| `public/data/*.json` | The published artifacts the frontend fetches directly: `advisor.json` (this document's primary subject), `etfs.json`, `picks.json`, `trades.json`, `news.json`, `prices.json`, `report.json`, `score-history.json`, `signals.json`, `status.json`, `politicians.json`, plus `etf/`, `factors/`, `screens/`, `validation/` subdirectories. |
| `netlify/functions/*.mjs` | Three serverless endpoints: `refresh-data.mjs` (dispatches/polls the GitHub Actions refresh), `portfolio-prices.mjs` (Firebase-authenticated live portfolio quotes), `alert-push.mjs` (Web Push delivery for Firestore alert events). |
| `src/` | React + Vite PWA: `src/pages/` (24 routed pages), `src/components/` (~28 components), `src/lib/` (data-loading hooks, scoring-adjacent client-side logic such as `dipWatch.js`, `recommendation.js`, `schemaMigrations.js`). |
| `.github/workflows/*.yml` | Eight scheduled/dispatchable workflows: the main hourly-ish research refresh, weekly Congressional-trades collection, monthly 13F collection, twice-daily Marketstack premarket collection, monthly PIT-fundamentals backfill, quarterly survivorship measurement, on-demand mock-data seeding, and CI (`compileall`, `check_ui_weights.py`, `pytest pipeline/tests`, `ic_harness.py --snapshot`, `validate_data.py`). |

The published artifact examined throughout this document, `public/data/advisor.json`, carries
`generated_at: 2026-08-10T05:23:37Z`, `model_version: 3.2.0`, `schema_version: 6`,
`universe_count: 926` (confirmed by direct query against the committed file) — see §3 for why
this figure is much larger than the brief's "~120 names" description and how the two relate.

---

## 2. Data sources

### 2.1 Providers, endpoints, and how each is reached

| # | Provider | Base endpoint(s) actually called |
|---|---|---|
| 1 | **Yahoo Finance** (via `yfinance`) | `yf.Ticker(symbol).info`, `.history()`, `.income_stmt`/`.balance_sheet`/`.cashflow`, `.calendar`/earnings pages, `.news`, `.option_chain()` — no REST URL is constructed directly; everything goes through the `yfinance` library. Batch downloads via `yf.download(chunk, ...)` (`fetch_advisor.py:401`). |
| 2 | **Alpha Vantage** | `GET https://www.alphavantage.co/query` (`alpha_vantage.py:13`), functions `OVERVIEW`, `TIME_SERIES_DAILY`, `NEWS_SENTIMENT`, `INSIDER_TRANSACTIONS` (`fetch_advisor.py:990-1014`). |
| 3 | **Marketaux** | `GET https://api.marketaux.com/v1/news/all` (`marketaux.py:19`). |
| 4 | **Marketstack** (apilayer) | `GET https://api.marketstack.com/v2/eod/latest`, `.../intraday` (`marketstack.py:17,64-73`). |
| 5 | **FRED** (St. Louis Fed) | `GET https://api.stlouisfed.org/fred/series/observations` (`fred.py:14`), six series: `DGS10, DFF, CPIAUCSL, UNRATE, T10Y2Y, SAHMREALTIME` (`fred.py:18-25`). |
| 6 | **SEC EDGAR** | `company_tickers.json`, `/Archives/edgar/data/...` (filings, Form 4 XML), `data.sec.gov/submissions/CIK...json`, `/api/xbrl/companyfacts/...`, `/api/xbrl/companyconcept/...`, `/api/xbrl/frames/...`, `efts.sec.gov/LATEST/search-index` (full-text search) (`sec_edgar.py:18-19, 224-465`). |
| 7 | **Financial Modeling Prep (FMP)** | `GET .../stable/{senate-latest, house-latest, historical-price-eod/light}` (`congress_trades.py:46,139-152`). |
| 8 | **Senate eFD** (Electronic Financial Disclosure) | `efdsearch.senate.gov/search/home/`, `/search/report/data/`, per-report pages — session-cookie + CSRF-token scrape, not a documented API (`congress_trades.py:59-70, 255-422`). |
| 9 | **House/Senate "stock-watcher" S3 mirrors** | `house-stock-watcher-data.s3-us-west-2.amazonaws.com/...`, `senate-stock-watcher-data...` — **both currently answer HTTP 403** (`congress_trades.py:20-25, 51-54, 475-484`), confirmed dead, not merely degraded. |
| 10 | **OpenFIGI** | `POST api.openfigi.com/v3/mapping`, CUSIP→ticker only (`openfigi_client.py:34`). |
| 11 | **Kenneth R. French Data Library** (Dartmouth) | Two static zipped CSVs, URLs from `settings.json.factor_data.{five_factor_url,momentum_url}` (`fetch_factors.py:14-19,108-110`). |

Polygon appears only as an unused rate-limit entry (`cache.py:47`); no Polygon client exists
anywhere in `pipeline/*.py`.

### 2.2 Fields pulled from each endpoint

- **Yahoo `info`**: `currentPrice`/`regularMarketPrice`, `shortName`/`longName`, `sector`,
  `industry`, `marketCap`, `dividendYield`, `priceToSalesTrailing12Months`, `priceToBook`,
  `forwardPE`, `trailingPE`, `trailingPegRatio`/`pegRatio`, `debtToEquity`, `currentRatio`,
  `returnOnEquity`, `profitMargins`, `freeCashflow`, `revenueGrowth`, `earningsGrowth`,
  `shortPercentOfFloat` (`fundamentals_extended.py:586`), plus `income_stmt`/`balance_sheet`/
  `cashflow` statement frames for the enrichment shortlist. Yahoo also supplies 2-year daily
  OHLCV (`yahoo_history`, `fetch_advisor.py:351-376`) and per-symbol company news.
- **Alpha Vantage `OVERVIEW`**: `MarketCapitalization, ForwardPE, PEGRatio, PriceToBookRatio,
  QuarterlyRevenueGrowthYOY, QuarterlyEarningsGrowthYOY, Name, Description, Exchange, Currency,
  Sector, Industry, PriceToSalesRatioTTM, PERatio, ReturnOnEquityTTM, ProfitMargin,
  AnalystTargetPrice, 52WeekHigh, 52WeekLow` (`fetch_advisor.py:579-630`). `NEWS_SENTIMENT` and
  `INSIDER_TRANSACTIONS` are also called but only `NEWS_SENTIMENT` is parsed into published data;
  `INSIDER_TRANSACTIONS`'s result feeds a lightweight diagnostic (`insider_summary`), distinct
  from the SEC-Form-4-sourced `insider_signal.py` scoring path.
- **Marketaux**: `title, url, source, published_at, description/snippet`, per-entity `symbol,
  match_score, sentiment_score`.
- **FRED**: raw `(date, value)` pairs per series, reduced to derived 0-100 regime factor scores,
  never published raw.
- **SEC EDGAR**: `company_tickers.json` (ticker→CIK map), Form 4 ownership XML (`transactionCode,
  transactionShares, transactionPricePerShare, transactionDate`, owner identity/role), XBRL
  company-facts (`val, unit, form, filed, start, end, accn, fy, fp` per concept), 13F info tables
  (`nameOfIssuer, cusip, sshPrnamt, value, putCall`).
- **FMP / Senate eFD / stock-watcher mirrors**: chamber, representative/senator, district/state,
  `symbol`, `assetType`, `assetDescription`, `owner`, `type`, `amount`, `transactionDate`,
  `disclosureDate`, `comment`, `link` — normalized to one common shape across all three sources.
- **OpenFIGI**: CUSIP in, `{ticker}` out only.
- **French Data Library**: monthly `Mkt-RF, SMB, HML, RMW, CMA, RF` (five-factor) and `Mom`
  (momentum), parsed into `market_excess, size, value, profitability, investment, momentum,
  risk_free`.

### 2.3 Authentication

| Provider | Env var | Behavior if absent |
|---|---|---|
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | Client constructor raises `AlphaVantageError` |
| Marketaux | `MARKETAUX_API_TOKEN` | Constructor raises; caught at `fetch_advisor.py:1350-1353`, degrades to the Alpha Vantage `NEWS_SENTIMENT` fallback for the ≤5 enriched symbols only |
| Marketstack | `MARKETSTACK_API_KEY` | Constructor raises `MarketstackError` |
| FRED | `FRED_API_KEY` | Constructor raises; caught at `fetch_advisor.py:1411-1417`, run continues with `fred_regime = None` |
| SEC EDGAR | `SEC_USER_AGENT` (a required contact string per SEC fair-access policy — **not a secret key**) | `.available` is `False`; every request raises `RuntimeError` rather than sending an unidentified request |
| FMP | `FMP_API_KEY` | Constructor raises `CongressTradesError` |
| OpenFIGI | `OPENFIGI_API_KEY` (optional) | No auth required; absence drops to the **anonymous tier** — 10 jobs/request instead of 100, 2.5s pacing instead of 0.3s |
| Yahoo, French Data Library, stock-watcher mirrors, Senate eFD | none | all keyless |

All keys load from the environment or the git-ignored `.env.local` via one shared loader,
`alpha_vantage.load_local_env()`, reused by every other client module. Every client explicitly
excludes its key from cache keys, logs, and published JSON.

### 2.4 Rate limits as implemented

Two distinct mechanisms coexist:

1. **Process-wide token-bucket limiter** (`cache.py:86-117`, `RateLimiter`), applied via
   `limiter_for(provider).acquire()`. Configured defaults (overridable via
   `settings.json.providers.rate_limits_per_minute`, currently **empty**, so these defaults are
   what's actually live): `alpha_vantage` 5/min (`cache.py:34`); `sec_edgar` 540/min = 9/s,
   deliberately under SEC's published 10/s ceiling (`cache.py:35-38`); `yahoo` 240/min = 4/s — the
   module's own comment states this is **not a documented Yahoo limit**, just an empirically-chosen
   guess (`cache.py:39-44`); `fred` 120/min, `marketaux` 60/min, `polygon` 5/min (unused),
   `default` 60/min. SEC EDGAR additionally shares this exact limiter inside `SecEdgarClient._get`
   specifically so N concurrent threads can't jointly exceed the ceiling.
2. **Per-client minimum-interval/explicit sleeps**, independent of the shared limiter: Alpha
   Vantage self-paces at `min_interval=1.1s` (`alpha_vantage.py:36,42,60-62`); Marketstack has no
   client-side pacing (batches instead, up to 100 symbols/request); OpenFIGI paces at 0.3s
   (keyed)/2.5s (anonymous) between batches; Senate eFD paces at a hand-picked 0.5s between
   report-page requests.

`parallel_map` (`cache.py:309-344`) bounds thread-pool concurrency to
`min(8, allowance // 2 or 1)` workers per provider by default.

### 2.5 Retry and backoff — exact parameters, including one docstring/code mismatch

- **Generic HTTP** (`common.http_get_json`): `retries=3`, exponential `backoff ** attempt` with
  `backoff=2.0` → sleeps of 2s, 4s between the 3 attempts (`common.py:50-70`).
- **`cache.retry_with_backoff`** (`cache.py:347-362`), used for Yahoo batch-history downloads:
  default `attempts=4, base_delay=2.0`, delay `base_delay ** attempt`. **CONTRADICTION between
  docstring and code**: the docstring reads "Exponential backoff at 2s, 4s, 8s, 16s"
  (`cache.py:349`), but the loop breaks *before* sleeping on the final (4th) attempt
  (`cache.py:355-358`) — with the default `attempts=4` used at every call site found, only
  **three** sleeps ever occur (2s, 4s, 8s), never a 16s one.
- **SEC EDGAR** (`sec_edgar.py:182-220`): up to 5 attempts, retried only on `{403, 429, 500, 502,
  503, 504}`, backoff `2 ** attempt` (1,2,4,8,16s), then re-raises. Non-retryable errors raise
  immediately.
- **OpenFIGI** (`openfigi_client.py:47-48,90-114`): up to 3 attempts per batch, retried only on
  429/5xx, backoff `5.0 * attempt` (5s, 10s); a non-retryable error abandons the batch, recorded
  in `self.errors`, not retried.
- **Alpha Vantage / Marketaux / Marketstack / FRED / FMP clients** themselves implement **no
  retry loop at all** — a single `requests.get(...)`, then a typed `*Error` exception on any
  non-200. Retry for these five only happens where the call is routed through
  `cache.cached_json`/`retry_with_backoff`, which — based on the code read this session — none of
  them is; **not exhaustively swept across every call site, flagged UNDETERMINED**.
- Senate eFD has **no retry at all** on any of its three request steps.

### 2.6 Caching layer and TTLs (`pipeline/cache.py`)

`DiskCache` (`cache.py:137-276`): JSON-on-disk, one file per `(namespace, key)` under
`pipeline/data/cache/<namespace>/`, keyed by a SHA-256-truncated slug. Every entry stores
`fetched_at`, `source`, and the raw `value`. `enabled` defaults to `True` unless
`PIPELINE_CACHE_DISABLE` is set.

Default TTLs, all overridable via `settings.json.providers.cache_ttl_seconds` (also empty, so
live): `price_history` 6h; `quote` 15 min; `statements` 7 days; `sec_submissions` 24h;
`sec_document` 30 days (a filed document never changes); `sec_xbrl` 24h; `etf_disclosure` 24h;
`etf_full_history` 20h; `news` 30 min; default (unlisted) 1h.

The Alpha Vantage and Marketaux clients each maintain a **separate, independent** file-based
cache (`alpha_vantage.py:14,44-58`; `marketaux.py:20,36-50`), at fixed default ages (20h and 4h
respectively) — a second, parallel cache implementation with its own defaults; neither client
ever calls into `pipeline/cache.py`.

**Staleness policy**: `DiskCache.get(allow_stale=True)` and `.fetch()`'s
`allow_stale_on_error=True` default mean an expired-but-present entry is served whenever the live
producer call raises. The live artifact confirms this machinery ran this refresh:
`cache: {"hits": 1130, "misses": 965, "stale_hits": 1, "hit_rate": 0.539}` (`public/data/
advisor.json`, top-level `cache` field, queried directly).

### 2.7 Failure behavior per provider — silent vs. loud, with live-artifact evidence

| Provider | Failure mode | Evidence from the live artifact |
|---|---|---|
| Yahoo (snapshot) | Per-symbol: caught, logged, excluded from `contexts` this run; the whole run only aborts if `contexts` is empty | `source_status.yahoo_fundamentals: {"status": "degraded", "failed_symbols": [46 tickers]}` — a real, partial, non-fatal degradation |
| Yahoo (price history) | Falls back to `EMPTY_HISTORY` on any exception; a company with <21 closes is excluded entirely | — |
| Yahoo (statement enrichment) | Failure counters recorded per stage, never abort the run | `source_status.yahoo_statement_enrichment: {"attempted": 150, "enriched": 148, ..., "no_statement_data": 2}` |
| Alpha Vantage | Constructor failure is loud but not caught anywhere in `run()` — UNDETERMINED whether a genuinely-absent key aborts production; per-symbol failures inside the enrichment window are caught (`fetch_optional` returns `{}`) and recorded, not raised | `capability_status.alpha_vantage: {"status": "disabled_for_intraday_refresh"}` in this fast-mode run |
| Marketaux | Constructor failure caught, degrades silently to AV `NEWS_SENTIMENT` fallback | `source_status.marketaux: {"status": "healthy"}` |
| FRED | Caught; whole macro-regime modifier degrades to unavailable, not fatal | `source_status.fred: {"status": "healthy", "failed_series": []}` |
| SEC EDGAR (Form 4) | Missing `SEC_USER_AGENT` degrades the source to unavailable rather than sending an anonymous request; per-filing parse failures recorded and skipped | `source_status.sec_form4: {"status": "healthy", "filings_unreadable": 0, "filings_reviewed": 6030}` |
| SEC EDGAR (13F / Congress screens) | **Not fetched live inside `fetch_advisor.py` at all** — reads the last separately-scheduled screen publish, degrades to an empty signal set if missing/failed | — |
| Congressional stock-watcher mirrors | Hard 403 classified specially, raised as a named, non-retried error telling the operator to configure a replacement URL — currently **permanently broken** | — |
| OpenFIGI | Per-batch failures land in `self.errors`, never raised; an unresolved CUSIP is simply omitted | — |
| French Data Library (factors) | Loud at the top: any exception caught once, logs `status: "error"`, returns `None`; the previously-published `factors/french.json` stays in place (stale, not blanked) | — |
| Cross-provider implausible values (margin >100%, cross-source price/cap disagreement) | Neither silent-pass nor run-fatal: the specific field is dropped, the drop is logged with the exact rule and value that fired, run continues | — |

**Overall pattern**: at the symbol level, essentially every provider failure is
**silent-and-recorded** (logged, counted, published in a diagnostics block, run continues), not
run-fatal. Only two things halt a run: zero symbols producing any usable context at all, and a
client constructor that raises for a missing required credential — caught for Marketaux and FRED,
**not caught for Alpha Vantage** (flagged UNDETERMINED above).

### 2.8 Field-level provenance table

| Field | Primary source | Fallback chain | On total failure |
|---|---|---|---|
| `price` | Yahoo `currentPrice`/`regularMarketPrice`, else last daily close | Alpha Vantage's snapshot only wins if its price history is *longer* than Yahoo's, which given Yahoo's 2y vs. AV's 100-session cap essentially never happens | Company excluded from the entire refresh — `collect()` raises if fewer than 21 closes resolve |
| `market_cap`, `forward_pe`, `price_to_book`, `eps`/`earnings_growth`, `revenue_growth` | For the ≤5 Alpha-enriched symbols: **Alpha Vantage wins over Yahoo when both resolve** (`merge_snapshots(primary=overview_snapshot, fallback=yahoo_snapshot)` only fills from `fallback` when `primary` is `None`/`""`). For the remaining ~99%+ of the universe: Yahoo only. | Cross-checked post-hoc by `plausibility.screen`'s cross-source comparison; large disagreement drops the field rather than arbitrating | `null`, excluded from that metric's coverage denominator |
| — **CONTRADICTION** | The **shadow** (`analysis_v2`) path applies the *opposite* precedence for `market_cap`/`price_to_book`: `canonical_metrics.reconcile()` ranks by `provider_reconciliation.json`'s `preferred_sources`, which lists `["yahoo","alpha_vantage"]` for `market_cap` and `["calculated_from_canonical_inputs","yahoo","alpha_vantage"]` for `price_to_book` — **Yahoo preferred over Alpha Vantage in the shadow path, Alpha Vantage preferred over Yahoo in the champion path**, for the identical ≤5-symbol window where both providers can disagree. | | |
| `book_value` (`price_to_tangible_book`) | Derived from Yahoo statement frames only — no Alpha Vantage equivalent field exists | none | `null` |
| `sector`/`industry` | Yahoo, defaulting non-ETF `sector` to `None` if omitted | AV, same AV-wins-when-present merge, ≤5-symbol window only | `None` — feeds `classify_profile`'s fallback path |
| `components.news_sentiment` | Marketaux entity `sentiment_score`, ≤5-symbol Alpha-enriched shortlist only | Alpha Vantage `NEWS_SENTIMENT`, same shortlist, tried only when Marketaux absent/failed; universe-wide, Yahoo per-symbol news supplies **no native sentiment score at all** — direction is inferred from a fixed keyword lexicon, not a model | `null` — confirmed live for THG |
| `insider activity` | SEC EDGAR Form 4 XML, open-market codes `P`/`S` only | none (single source) | Insider modifier contributes 0/unmeasured |
| `institutional_ownership` | **Not fetched live per refresh at all** — reads the last separately-scheduled monthly 13F screen publish and time-decays it | none | `{}` if the screen file is absent/failed |
| `congressional buying` | **Not fetched live per refresh either** — reads the last weekly screen publish (three sources merged upstream, weekly, not per-refresh) | none | `{}` |
| `short_percent_of_float` | Yahoo, extended path only | none | `null` |
| `macro regime` | FRED, 6 series blended, weighted-average over whichever resolved, requires ≥2 series | partial only | Whole `fred_regime = None`; modifier unavailable, not defaulted |
| `analyst estimates/revisions` | Yahoo — the module's own docstring states Yahoo exposes only *today's* view, never as-of a past date, and nothing substitutes for the point-in-time store | none | Component drops, confidence lowers, per stated design |

### 2.9 Point-in-time vs. restated — the single most important determination in this section

**The live/published score is computed from restated (latest-available), not point-in-time,
fundamental data.** Stated directly by the code, not inferred:

- `pipeline/pit_store.py:3-4`: *"Yahoo (and yfinance on top of it) serves **restated** current
  fundamentals with no as-originally-reported history."*
- `pipeline/build_pit_fundamentals.py:12-16`: *"Every fundamental in this repository today comes
  from a provider that serves **restated** figures with no as-reported history, keyed by ticker."*
- `pipeline/build_pit_fundamentals.py:22-24`: *"What it deliberately does not do. It does not
  derive ratios, score anything, or **feed the live pipeline**."*

Verified, not just quoted: the champion score (`scorer._band_valuation_score`) operates on
`snap`/`context["snapshot"]`, built exclusively by `fetch_prices.fetch_snapshot`/
`fetch_advisor.overview_snapshot` — each provider's *current* view, not a filing-dated
observation. `pipeline/pit_store.append_snapshot(research, source="advisor_refresh")`
(`fetch_advisor.py:1723`) runs **after** scoring completes and only **writes** today's
already-computed row into the archive for future backtesting — it is never read back into the
score.

A genuinely point-in-time archive exists but is a separate, parallel system:
`pipeline/edgar_facts.py` stamps every SEC XBRL fact with its filing-`accepted` date (not the
period-end date) and preserves restatements as additional observations rather than overwriting;
populated by the standalone monthly job `build_pit_fundamentals.py`
(`backfill-pit-fundamentals.yml`) into `pipeline/data/pit/fundamentals.jsonl`, keyed by CIK. This
substrate feeds `ic_harness.py`, `evaluate_signal.py`, and (partially, per the internal audit's
C-3 finding, not independently re-verified line-by-line this session) `backtest_historical.py` —
**never** the published `advisor.json` score. The daily `pipeline/data/pit/observations.jsonl`
store is a third, distinct thing again: a forward-only archive of each day's already-restated
row, useful for measuring stability/turnover over time, not a reconstruction of what was knowable
historically.

---

## 3. Universe construction

### 3.1 Where the universe lives, and its actual size

`pipeline/config/advisor_universe.json` (read in full):
- `description`: a prose note that breadth is deliberate ("the information ratio of a signal
  scales with the square root of the number of independent bets") — a stated design rationale,
  not a citation to external validation.
- `publish_limit: 40` — how many ranked rows land in `research[]`, the published leaderboard.
- `extended_limit: 150` — how many highest-priority candidates get statement enrichment per
  refresh.
- `portfolio_symbols`: 21 hand-listed tickers (the maintainer's actual brokerage holdings).
- `symbols`: **910 unique, well-formed tickers** (`len(symbols) == 910 == len(set(symbols))`),
  all 21 `portfolio_symbols` already contained within it.

**The brief's "~120 names" does not describe this universe — it describes a different, smaller
parameter in an unrelated backtest tool.** `pipeline/backtest_historical.py:449` declares a CLI
flag `--universe-limit`, **default 120**, described as *"Candidates to pull from
advisor_universe.json (default 120)"* — this slices `symbols[:120]` for one lighter-weight
standalone historical-backtest run, entirely separate from the live/published pipeline. This is
the most likely origin of the brief's "~120" figure, though the specific causal chain (someone
reading this default and mistaking it for the live universe size) is not proven, only the
best-supported hypothesis.

### 3.2 Static vs. regenerated

No script writes or regenerates `advisor_universe.json`. Every reference to `advisor_universe` in
the repo (`fetch_advisor.py:55`, `build_institutional_screen.py:61`,
`build_pit_fundamentals.py:180`, `backtest_historical.py:65`, `backtest_monthly.py`,
`backtest_emerging_growth.py`, `validate_data.py:210`) is a **reader** — none writes back. This
is a hand-maintained JSON list, confirmed by its git history (§3.5): the one substantive edit
found was made by a human GitHub username, not a bot/generator commit.

**Guard tests** run in CI (`pipeline/tests/test_universe_config.py:73-92`, `StockUniverseTests`):
symbols unique and well-formed (`[A-Z][A-Z0-9.-]{0,9}`); breadth ≥300; `extended_limit <
len(SYMBOLS)/2` and `>= publish_limit`; every `portfolio_symbols` entry must already be inside
`symbols` — i.e., **a holding that isn't in the base list will never be scored** (the exact bug a
prior commit fixed for `VGT`, §3.5).

### 3.3 Inclusion/exclusion criteria

No filtering/screening code decides which tickers belong in `advisor_universe.json` — no
liquidity screen, index-membership check, market-cap floor, or sector-balance rule anywhere in
the pipeline touches this file. It is exactly what its own description says: a hand-curated
"diversified liquid US large- and mid-cap candidate universe," with no code-enforced inclusion
rule beyond the CI guard tests above. The only place a *listed* symbol can still fail to be
scored is downstream, at `collect()`: fewer than 21 valid daily closes or no resolvable snapshot
excludes that symbol from that run's `contexts` — a runtime data-availability gate, not a
universe-construction criterion.

### 3.4 Ticker-to-entity resolution — exists, but not in the live scoring path

Two separate mechanisms:
1. **`pipeline/edgar_entities.EntityResolver`** — the only true ticker→CIK resolver in the repo.
   Resolves against a cached SEC `company_tickers.json` snapshot, **fails loudly on ambiguity**
   (raises rather than guessing), and explicitly treats GOOG/GOOGL-style shared CIKs as
   legitimate. Its only production callers are `build_pit_fundamentals.py` and `sec_edgar.py`'s
   own simpler `ticker_map()` (used for Form 4 lookups — unlike `EntityResolver`, does **not**
   raise on ambiguity). **`fetch_advisor.py`, the module that builds and publishes
   `advisor.json`, never imports `edgar_entities` at all.** The live scoring/publishing path
   carries **no CIK and no rigorous entity resolution** for any published name — a ticker is
   simply the identity key throughout.
2. **Company name/sector/industry/exchange**, as actually captured for the live payload: `name`,
   `sector`, `industry` come from Yahoo's `info` for the whole universe. **`exchange` is captured
   only for the ≤5 Alpha-Vantage-enriched symbols per refresh** — Yahoo's snapshot path never
   reads an exchange field at all. So for ~900+ of ~926 published/tracked names on any given run,
   **no exchange field exists anywhere in the published data.**

### 3.5 Has the universe ever changed — full git history

**Note on git-history reliability**: `git log --follow` on this path produced a false positive,
attaching two unrelated commits from a different branch's history as if they were renames, due to
content-similarity-based rename detection on a large, highly-similar JSON ticker list. Confirmed
and discarded via `git log --all --oneline -- <path>` and `git merge-base --is-ancestor`, the
methodology used below. **This false-positive pattern may affect other git-archaeology claims in
this document that relied on `--follow`; not systematically re-checked elsewhere.**

Canonical incremental history lives on `main` — four commits, same day (2026-08-04), oldest first:
1. `cbc38ff` — creates the file (base ~907-symbol list, no `VGT`/`EXPE`/`CRUS`).
2. `fa11991` (PR #36, human-authored) — adds `VGT` to `portfolio_symbols` **only**. The PR
   description states plainly that VGT wasn't findable because it was never in the pipeline's
   `portfolio_symbols` universe, and that day's `advisor.json` was hand-backfilled with a manual
   price, marked `coverage_status: manual_price_only`, rather than a fabricated score.
3. `5e44311` — adds `EXPE` and `CRUS` to `portfolio_symbols`.
4. `c8e4c6b` — removes a duplicate `DECJ` entry; adds `VGT` to the **base** `symbols` list for
   the first time (it had only ridden along as a "current holding" per §3.6's
   `resolve_refresh_symbols` mechanism since commit 2, not been a first-class scored universe
   member until this commit).

**No change history is recorded anywhere in the running application** — no in-app changelog, no
version field on the file itself. Git commit messages are the only record, and three of the four
(`"css and refresh"`, `"here"`, a generic data-refresh message) do not describe the universe-list
edit they contain at all; only PR #36's message documents its own change.

### 3.6 Resolving the 926-vs-910-vs-120 discrepancy — CONTRADICTION only with the brief's premise, not internally

- Config file base list: **910** unique symbols.
- Published artifact's `universe_count`: **926** (`fetch_advisor.py:1764`,
  `"universe_count": len(symbols)`, where `symbols` is the **runtime-resolved** set from
  `resolve_refresh_symbols()`, not a static re-read of the config array).
- `resolve_refresh_symbols` unions three sources: (a) the config's base `symbols`; (b) config
  `portfolio_symbols` **plus** any ticker present in the *previous* run's published
  `portfolio_coverage` — i.e., the user's actual live brokerage holdings, carried forward
  run-to-run even if never added to the static config file; (c) an optional
  `ADVISOR_PORTFOLIO_SYMBOLS` env-var override, unused in this run.
- Computed directly against the committed artifact: published `universe` (926) minus the config's
  base 910 leaves exactly **16** extra tickers (`AAOI, AMTM, ASTS, AXGN, DECJ, DEO, FISV, IDCC,
  LEU, NBIS, PGY, RIGL, SOLS, TTM, UEC, VRT`), every one present in the same artifact's
  `portfolio_coverage[]`. `910 + 16 = 926`, exact.
- `polled_count: 247` is a **fourth**, still-different number — how many symbols were actually
  re-fetched this specific run (`universe_mode: "fast"`), not the full 926. `count: 40` is the
  `publish_limit`-bounded leaderboard. `research[]` has 40 rows; `screen_universe[]` has 838 more
  (878 total scored/carried this run).

**Verdict**: there is **no** "advisor/research universe of ~120 vs. a broader stock database of
~926" split — that framing does not match anything in the code or data. There is exactly **one**
universe mechanism, and the differing numbers (910 config / 926 published `universe_count` / 247
`polled_count` / 40 published leaderboard / 878 scored-or-carried this run) are five precisely
different quantities inside that one mechanism, not five competing universes. The brief's "~120"
is a CONTRADICTION with the live system, and its most probable source (§3.1) is a
same-day-named-but-unrelated CLI default in a standalone backtest tool.

---

## 4. Metric computation

### 4.1 The live (champion) fundamental score

Formula, in full, as implemented at `pipeline/scorer.py:_band_valuation_score` (lines 538–623),
verified line-by-line this session:

1. **Profile assignment and suppression.** `profile, suppressed = applicability(snap)`
   (`scorer.py:548`). This calls into `pipeline/canonical_metrics.py:classify_profile`
   (lines 95–130), a deterministic text-match over `sector`/`industry` strings, evaluated in a
   fixed priority order: ETF → REIT → bank → insurance subtype (life / property-casualty /
   diversified, by industry substring) → utility → commodity producer (oil/gas/mining/gold/
   copper/steel/coal substrings) → semiconductor → biotech (pre-profit vs. profitable, split on
   `profit_margin < 0`) → other pre-profit (any name with negative margin not otherwise
   classified) → `"general"` fallback. Eleven named profiles are declared in
   `pipeline/config/business_profiles.json` (`general, etf, property_casualty_insurer,
   life_insurer, diversified_insurer, bank, reit, utility, commodity_producer,
   profitable_biotechnology, pre_profit_biotechnology`); two more — `semiconductor` and
   `other_pre_profit` — exist as `classify_profile` return values and have their own entries in
   `pipeline/config/applicability_matrix.json`'s `rules` (confirmed: `rules` dict keys are
   `general, bank, property_casualty_insurer, life_insurer, diversified_insurer, reit, utility,
   commodity_producer, profitable_biotechnology, pre_profit_biotechnology, other_pre_profit,
   semiconductor` — 12 keys, all 13 `classify_profile` outputs except `etf`, which is
   special-cased directly in `applicability_for`, `canonical_metrics.py:142-143) — but are
   **not** listed in `business_profiles.json`'s `profiles` object, so any lookup of
   `profile_contract` (replacement/critical metrics, used in `scoring_v2.py:241-247`) for a
   semiconductor or other-pre-profit name silently returns an empty dict rather than raising.
   Verified for a live example: CRUS (Cirrus Logic, sector "Technology", industry
   "Semiconductors") resolves to `applicability_profile: "semiconductor"` in the published
   artifact, with `capex_to_depreciation` and `inventory_days_trend` both suppressed and scored
   `null` — the applicability rule fires correctly on the live path. Whether `CRUS`'s
   `scoring_v2` applicability block (which reads `business_profiles.json`, not
   `applicability_matrix.json`) silently degrades because `"semiconductor"` is absent from that
   file's `profiles` object is UNDETERMINED — not traced this session.
2. **Per-metric suppression.** For each of the (up to) 29 fundamental metrics, if its ID is in
   the `suppressed` set returned by `applicability`, its value is forced to `None`
   (`scorer.py:607`) before any scoring or coverage computation. `applicability_for`
   (`canonical_metrics.py:141-150`) resolves a metric's status by: (a) checking a per-profile
   rule table (`profile_rules`, which supports single-level inheritance via a `$inherits` key,
   `canonical_metrics.py:133-138`); (b) if no explicit rule, checking whether the profile is
   listed in the metric's `applicability_profiles` declaration in
   `pipeline/config/metric_registry.json`; a profile not listed there is suppressed by default
   with the reason `"Metric registry does not declare this profile applicable."`; (c) otherwise
   `"applied"`.
3. **Per-metric scoring function.** Each metric's raw value is mapped to a discrete score by one
   of six functions in `scorer.py` (`band_score`, `multiple_score`, `higher_is_better_score`,
   `lower_is_better_score`, `range_score`, `altman_score` — cutoffs read from
   `settings.json.fundamentals.<metric_name>` per metric). This mapping is table-driven, not
   continuous: the internal audit's characterization of ~12 discrete output levels (0/5/10/15/
   25/45/50/55/65/75/80/100) was not independently re-verified against every band table this
   session, but `_band_valuation_score`'s output for THG (`fundamental_detail` in
   `docs/spec/SAMPLE_OUTPUT.json`) shows exactly this pattern: every populated metric scores one
   of `{55.0, 75.0, 80.0, 100.0}`.
4. **Category aggregation with a required-metric gate.**
   `_categories_with_required_gate(metrics, cfg, profile)` (`scorer.py:515-535`) is **not** a
   simple reweighting. For each category, it first checks `required_for_score(profile,
   category)` (`canonical_metrics.py:174-182`, reading `applicability_matrix.json`'s
   `required_for_score` block — declared for 5 profiles only: `property_casualty_insurer,
   life_insurer, diversified_insurer, bank, reit`). If any metric named as required for that
   category is missing (`None`) for this profile, **the entire category is withheld** — set to
   `None` rather than computed from whatever metrics did resolve — and the withheld category
   plus its missing required metrics are recorded in a `categories_withheld` map. Only if no
   required metric is missing does the category fall through to
   `weighted_available(metrics, weights)` (`scorer.py:159-163`): a simple weight-renormalized
   average over whatever metrics in that category are non-`None`. **This means missing-value
   handling is not uniform across metrics**: a required metric's absence zeroes an entire
   category; a non-required metric's absence is silently renormalized away within the category,
   with no marker in the payload distinguishing "this 90.0 valuation score came from 8 of 8
   metrics" from "this 90.0 came from 2 of 8." (`weighted_available` records only the resulting
   value, not the count or share of metrics used — confirmed by reading its 5-line body.)
5. **Coverage.** `weighted_coverage(metrics, cfg, exempt=suppressed)` (`scorer.py:496-512`):
   the fraction of total *metric weight* (not metric count) that resolved to a non-`None` value,
   with suppressed metrics excluded from both numerator and denominator entirely — so
   suppressing a metric cannot lower measured coverage, and previously could artificially raise
   it under the retired `FINANCIAL_EXEMPT` scheme (see §0 above; this exemption pathway is gone,
   but the same mathematical property — suppressed metrics leaving the denominator — persists
   under the new, code-correct suppression mechanism, and is a deliberate design choice per the
   function's docstring, not a bug).
6. **Coverage-based shrinkage (first of two).**
   `confidence_multiplier = 0.65 + 0.35 * coverage` (`scorer.py:615`); `total = raw *
   confidence_multiplier` (`scorer.py:616`). Verified exactly against THG: `raw_score: 89.0`,
   `coverage: 0.96` → `89.0 * (0.65 + 0.35*0.96) = 89.0 * 0.986 = 87.75` → rounds to the
   published `components.fundamentals: 87.7`. This is an **arithmetic match**, not an inferred
   formula.

### 4.2 The composite blend (second coverage shrink)

`pipeline/advisor_engine.py:blend_research_components` (lines 846-867):

```
raw          = Σ(component_i · weight_i) / Σ(weight_i)     over available components
weight       = RANKING_WEIGHTS = {fundamentals: 0.78, market_behavior: 0.18, news_sentiment: 0.04}
                 (advisor_engine.py:32, 42; settings.json key "ranking_weights" overrides via
                 advisor_engine.py:35-39's _weights() merge, confirmed the merge only accepts
                 numeric, non-"_"-prefixed keys)
data_coverage = data_coverage_scalar(coverage)
              = 0.65·coverage[fundamentals] + 0.25·coverage[market_behavior] + 0.10·coverage[news_sentiment]
                 (advisor_engine.py:827-843)
base         = round(raw · (0.8 + 0.2·data_coverage), 1)                        (advisor_engine.py:861)
score        = round(clamp(base + modifier_points, 0, 100), 1)
```

**This is a confirmed, currently-live double coverage-shrink**, structurally unchanged from
what the internal (stale) audit described, just renamed: the `fundamentals` component entering
this formula is *already* shrunk once by its own internal `coverage` term (§4.1 step 6) before
`data_coverage_scalar` shrinks the composite a second time using a *different* coverage figure
(a 0.65/0.25/0.10 blend across all three components, of which fundamentals' own coverage is one
input at 65% weight). The two shrink events use the same underlying completeness concept applied
at two different levels of the score tree, both derived from `weighted_coverage`. Verified
against THG: `raw_score: 85.1`, modifiers `total: -1.57` → `base_score` should be
`clamp(85.1·(0.8+0.2·0.87)) = 85.1·0.974 = 82.88 ≈ 82.9`, matching the published `base_score:
82.9` exactly; `82.9 - 1.57 = 81.33 → 81.3`, matching the published `score: 81.3` exactly. Both
arithmetic steps verified against the live artifact.

The function's own docstring (`advisor_engine.py:847-852`) states the formula plainly and does
not claim this avoids double-counting — it is presented as the intended design, not a bug being
hidden. Whether double-shrinking coverage is *methodologically* sound (as opposed to internally
consistent) is a judgment call for the external reviewer; I flag the mechanism precisely rather
than pre-judging it.

### 4.3 Units, periods, adjustments

UNDETERMINED this session: split/dividend adjustment handling in price history
(`pipeline/fetch_prices.py`, not yet read), and a systematic TTM-vs-annual-vs-quarterly audit
across all ~29 fundamental metrics. Partial evidence: `canonical_metrics.Observation`
(lines 43-58) carries `is_ttm: bool = False` and `is_forward: bool = False` fields with
default-`False` values, and both v2 call sites that construct observations
(`overview_snapshot`, `yahoo_observations` — not yet opened this session) are reported by the
internal audit to construct observations without ever setting these fields, compensating with a
`provider_period_not_supplied` quality flag that (per the same source) nothing in the live
scoring path reads. **This specific claim is NOT independently re-verified this session** — it
is repeated from the internal audit with an explicit UNDETERMINED flag, not asserted as
confirmed current fact. Follow-up needed: open `overview_snapshot`/`yahoo_observations` in
`canonical_metrics.py` directly.

### 4.4 Winsorization and normalization — two live modes

Selected by `settings.normalization_mode` (confirmed value: `"bands"` is the champion/published
mode — every `SAMPLE_OUTPUT.json` field under `fundamental_detail` and `fundamental_categories`
is produced this way).

- **`bands`** (champion): `pipeline/scorer.py:_band_valuation_score`, described fully in §4.1.
  No winsorization. No cross-sectional reference population — each metric's score depends only
  on fixed absolute thresholds in `settings.json`, so (as the internal audit correctly notes,
  and this remains true in current code) a metric's score is not regime-relative.
- **`cross_sectional`** (challenger, published alongside the champion in
  `score_variants.normalization` — confirmed present in THG's live row):
  `scorer.py:CrossSectionalNormalizer` (class located at line 296 per earlier reading this
  session; internals — winsorization percentile, sector-vs-universe selection logic, tie
  handling — not yet re-read line-by-line this session; UNDETERMINED pending follow-up, though
  the *behavior* is directly visible in THG's published `score_variants.normalization.
  fundamental_detail.normalization` block: e.g. `forward_pe` scored at `normalization_scope:
  "sector"`, `peer_count: 123`, `raw_percentile: 50.8`, `desirability_percentile: 49.2`
  (multiple mapped via `direction: "lower_is_better"` as `100 - raw_percentile` for
  `forward_pe`, consistent with a percentile-rank-then-flip scheme); `price_to_book` scored at
  `normalization_scope: "universe"` with `peer_count: 693`. This confirms a per-metric,
  per-row choice between sector and universe reference populations is actually exercised in the
  published challenger data, not merely described in a docstring.
- **Own-history percentile**: every metric's normalization block in the challenger variant
  carries `own_history_percentile: null`, `own_history_status: "accumulating"`,
  `own_history_observations: 3` (THG, confirmed in `SAMPLE_OUTPUT.json`). This mechanism exists
  and is wired into the payload but is not yet populated for any metric in the live artifact —
  confirmed by direct inspection, not inferred.

### 4.5 Missing-value handling — exhaustive list of imputation/default sites found this session

This list combines defaults found through direct reading this session. It is **not yet
cross-checked against the exhaustive mechanical grep** the parallel METRIC_REGISTRY.md-building
pass is performing over all of `pipeline/*.py` — that pass's `registry.json` `defaults` array
should be treated as the authoritative, more complete version of this list once merged in.

| Location | Trigger | Default/behavior | Feeds a score/decision? |
|---|---|---|---|
| `scorer.py:159-163` (`weighted_available`) | any metric in a category is `None` | dropped, remaining weights renormalized to sum 1 within the category | Yes — category score |
| `scorer.py:515-535` (`_categories_with_required_gate`) | a *required* metric (per `required_for_score`) is `None` | entire category → `None`, recorded in `categories_withheld` | Yes — zeroes a whole category rather than reweighting |
| `scorer.py:496-512` (`weighted_coverage`) | metric suppressed for profile | excluded from coverage denominator entirely (not counted as missing) | Yes — coverage, which feeds the shrink in §4.1 step 6 |
| `advisor_engine.py:846-867` (`blend_research_components`) | a whole component (fundamentals/market_behavior/news_sentiment) is `None` | dropped from the weighted average, remaining weights renormalized | Yes — composite raw score |
| `advisor_engine.py:870-895` (`shrink_research_components`, challenger only) | no component available at all | `raw` defaults to `config["shrinkage_target"]` (a configured neutral, not a hardcoded literal in code) | Yes, challenger score only |
| `scoring_v2.py` `_weighted` (lines 22-26) | no value in a weighted set resolves | returns `None` (not a neutral number) — confirmed this is the *fixed* behavior, contrast with the retired pattern in §0 | Publishes `null`, does not fabricate |
| `recommendation_policy_v2.py:40-43` (`effective_score`) | `raw_score` is not a number | `raw = _number(raw_score, 50.0)` — **a literal 50.0 default still exists here** | Yes, but only reached when `raw_score` itself is malformed/non-numeric, not merely absent — a distinct condition from the timeliness-layer case discussed in §0, which now short-circuits *before* this function is called when the layer's `raw_score` is legitimately `None` per `_score_layer` (`recommendation_policy_v2.py:46-62`, which passes `raw = None` through and this function is never invoked with `raw_score=None` for an unresolved layer — confirmed by reading `_score_layer`'s `"effective_score": None if raw is None else effective_score(raw, confidence)` at line 59). **Practical implication: this 50.0 default appears to be dead code for the timeliness/structural layers as currently wired, but I have not proven no other call site passes a non-numeric `raw_score` into it. Flagged as needing a full call-site audit, not resolved this session.** |
| `recommendation_policy_v2.py:289-291` (`classify_portfolio_fit`) | no `portfolio` supplied | `current_weight → 0.0`, `target_weight → config.default_target_weight (0.03)`, `maximum_weight → config.default_max_weight (0.05)` | Yes — with `current(0.0) < target(0.03)·0.75`, this is always true with no portfolio context supplied, so `classification` is always `"below_target"` for any position-free evaluation. Confirmed still present and confirmed still producing `below_target` for THG (`portfolio_fit_state.classification: "below_target"`), which has no portfolio position. This matches the internal audit's finding and **is not fixed** — this remains a constant for every unpositioned name. |
| `pipeline/canonical_metrics.py:81-92` (`calculate_peg`) | forward PE, growth, unit, or period-match/definition-known flags fail validation | returns `None` (rejects rather than substitutes) | No default — explicit rejection, confirmed the "opposite of a silent default" pattern |

**Section 4 is not fully exhaustive yet.** The mechanical sweep in progress (parallel research
pass) will supersede this table with a fuller one; this table should not be read as the final
word on silent defaults.

---

## 5. Suppression and applicability

**Classification scheme**: `pipeline/canonical_metrics.py:classify_profile` (lines 95-130),
described in full in §4.1 step 1. Source of truth for per-profile metric rules:
`pipeline/config/applicability_matrix.json` (`rules` object, 12 profile keys, confirmed by
direct read this session) plus `pipeline/config/metric_registry.json`'s per-metric
`applicability_profiles` declaration as the fallback when no explicit rule exists
(`canonical_metrics.py:147-149`).

**`suppressed` vs. `replaced` vs. `unavailable`** — three distinct status strings appear in
`metric_status` entries (confirmed against THG's live `analysis_v2.metric_status` block in
`SAMPLE_OUTPUT.json`):
- `"suppressed"`: the applicability registry has an explicit rule saying this metric does not
  apply to this profile (e.g. THG's `ev_to_ebitda`: `"EV/EBITDA is not an insurer-standard
  valuation measure."`, `replaced_by: "price_to_book"`). Excluded from both score and coverage
  denominator (§4.1 steps 2 and 5).
- `"replaced"`: appears as a possible status value in `suppressed_metrics()`
  (`canonical_metrics.py:169`, checked alongside `"suppressed"`) but was not observed as a
  distinct status string in THG's actual `metric_status` output — every suppressed entry in the
  live example carries status `"suppressed"` with a `replaced_by` field pointing at the
  substitute metric, rather than the substitute itself carrying a `"replaced"` status.
  UNDETERMINED whether `"replaced"` is ever actually assigned as a metric's own status anywhere
  in the current codebase, or whether it exists in the code as a dead branch alongside
  `"suppressed"` at `scoring_v2.py:127` (`if status in ("suppressed", "replaced"):`). Needs a
  grep across all producers of `metric_status` to confirm.
- `"unavailable"`: the metric is applicable to this profile (not suppressed) but its value is
  simply missing this run — e.g. THG's `price_to_sales`: `status: "unavailable"`, no
  applicability reason given (`reason: null`). This is a data-completeness gap, not a
  methodology decision.

**Effect on the parent score — traced precisely (§4.1 steps 2-4):**
- A **suppressed** metric is removed from its category's weight base entirely; `
  weighted_available` renormalizes the remaining metrics' weights to sum to 1 within the
  category. It does **not** contribute a zero, and it does **not** reduce coverage (it leaves
  the coverage denominator too). Net effect: a category with several suppressed metrics is
  scored purely on whatever remains, at full renormalized weight, and reads as if the
  suppressed metrics never existed as an evaluation criterion for this profile.
- If a suppressed (or merely unavailable) metric happens to be in that profile's short
  `required_for_score` list for its category (declared for only 5 of 12 profiles — the
  insurers, banks, and REITs), the *entire category* is withheld (`None`) instead of being
  renormalized. This is a materially different and more severe consequence than ordinary
  suppression, and it is profile-specific: the same missing metric is "renormalize and move on"
  for a general/tech name and "withhold the whole category" for an insurer.
- Replacement metrics named in a profile's rule (e.g. insurer `ev_to_ebitda → price_to_book`) are
  **descriptive only in the payload** (`replaced_by` field) — I did not find code this session
  that actually substitutes the replacement metric's *value* into the suppressed metric's weight
  slot. The category's weight base is renormalized over the metrics that remain scoreable, which
  for an insurer includes `price_to_book` and `price_to_tangible_book` as their own weighted
  entries in the `valuation` category (weights 0.05 each, per §6) — not as a substitute carrying
  `ev_to_ebitda`'s 0.27 weight. **This means a metric named as a "replacement" does not inherit
  the suppressed metric's weight; it only contributes its own, normally much smaller, configured
  weight**, and the suppressed weight is redistributed proportionally across *all* remaining
  valuation metrics via `weighted_available`'s renormalization, not specifically routed to the
  named replacement. Verified by the numbers: THG's applied valuation metrics are `forward_pe
  (0.15), price_to_book (0.05), price_to_tangible_book (0.05)`; after renormalizing to sum to 1,
  their effective within-category shares become `0.15/0.25=0.60`, `0.05/0.25=0.20`,
  `0.05/0.25=0.20` — `forward_pe` dominates at 60% of the category, not the "replacement"
  metrics `price_to_book`/`price_to_tangible_book` the applicability rule names as the intended
  substitutes for the suppressed enterprise-value multiples. **This is a real, currently-live
  gap between what the applicability rule's `replaced_by` field claims and what the weighting
  arithmetic actually does — flagged as a finding for Section 10, not previously identified in
  the internal audit.**

**Business-profiles.json vs. applicability_matrix.json — two registries, confirmed still
separate.** `scoring_v2.py`'s `applicability` block (payload key `applicability`, distinct from
`metric_status`) reads `BUSINESS_PROFILES` (`business_profiles.json`) for `replacement_metrics`
and `critical_metrics` per profile (`scoring_v2.py:241-247`) — a second, independent list from
`applicability_matrix.json`'s `rules`. For THG these mostly overlap in spirit (both name
insurer-specific replacement concepts) but are declared in different files with no cross-check
enforced in code that I found this session; UNDETERMINED whether they can drift out of sync
undetected.

---

## 6. Scoring architecture — the weights

**Full hierarchy, verified against `pipeline/config/settings.json` directly (not copied from
any prior audit) and against the code that reads each block:**

### 6.1 Composite level

| Component | Weight | Defined at | Read at |
|---|---|---|---|
| fundamentals | 0.78 | `settings.json` key `ranking_weights.fundamentals`, or `DEFAULT_RANKING_WEIGHTS` (`advisor_engine.py:32`) if absent from config | `advisor_engine.py:42`, `RANKING_WEIGHTS = _weights(SETTINGS.get("ranking_weights"), DEFAULT_RANKING_WEIGHTS)` |
| market_behavior | 0.18 | same | same |
| news_sentiment | 0.04 | same | same |

Sums to 1.0 exactly. `_weights()` (`advisor_engine.py:35-39`) merges config over defaults,
accepting only numeric, non-underscore-prefixed keys — so a malformed config entry is silently
dropped back to the hardcoded default rather than raising. **This is config-driven with a
code-level fallback, confirmed still present** — verifying whether `settings.json` actually
overrides these three values or the code defaults are what's live requires comparing the
config file's `ranking_weights` block against `DEFAULT_RANKING_WEIGHTS`; not yet done this
session (UNDETERMINED whether config or default is the operative source for these three
specific numbers, though they are identical either way per the values found in `settings.json`
fundamentals earlier in this session — full `ranking_weights` block not yet read directly).

### 6.2 Fundamentals: category level

`settings.json.fundamentals.category_weights` (queried directly this session):

| Category | Weight |
|---|---|
| valuation | 0.28 |
| profitability | 0.26 |
| financial_health | 0.15 |
| growth | 0.11 |
| capital_allocation | 0.10 |
| accounting_quality | 0.10 |

Sum: `1.0000000000000002` — a floating-point rounding artifact from summing six decimal
literals in Python, confirmed by direct computation this session, not a configuration error. Not
a defect worth flagging beyond noting it exists.

### 6.3 Fundamentals: metric level within category

`settings.json.fundamentals.metric_weights`, each category's weights summing to exactly 1.0
(verified by direct computation this session):

| Category | Metric | Weight in factor |
|---|---|---|
| valuation | ev_to_ebitda | 0.27 |
| valuation | ev_to_fcf | 0.18 |
| valuation | forward_pe | 0.15 |
| valuation | ev_to_ebit | 0.12 |
| valuation | peg | 0.09 |
| valuation | sales_multiple | 0.09 |
| valuation | price_to_book | 0.05 |
| valuation | price_to_tangible_book | 0.05 |
| profitability | return_on_invested_capital | 0.26 |
| profitability | gross_profits_to_assets | 0.22 |
| profitability | free_cash_flow_yield | 0.16 |
| profitability | cash_conversion | 0.16 |
| profitability | return_on_equity | 0.10 |
| profitability | profit_margin | 0.10 |
| financial_health | interest_coverage | 0.30 |
| financial_health | net_debt_to_ebitda | 0.24 |
| financial_health | debt_to_equity | 0.18 |
| financial_health | altman_z | 0.18 |
| financial_health | current_ratio | 0.10 |
| growth | revenue_growth | 0.26 |
| growth | fcf_growth_3y | 0.22 |
| growth | earnings_growth | 0.20 |
| growth | operating_margin_trend | 0.16 |
| growth | earnings_surprise | 0.16 |
| capital_allocation | net_buyback_yield | 0.34 |
| capital_allocation | stock_comp_to_revenue | 0.28 |
| capital_allocation | asset_growth | 0.22 |
| capital_allocation | capex_to_depreciation | 0.16 |
| accounting_quality | piotroski_f | 0.45 |
| accounting_quality | accruals_ratio | 0.22 |
| accounting_quality | days_sales_outstanding_trend | 0.17 |
| accounting_quality | inventory_days_trend | 0.16 |

**Effective weight in composite** = `0.78 (fundamentals) × category_weight × metric_weight`.
Example: `ev_to_ebitda` = `0.78 × 0.28 × 0.27 = 0.05896`, i.e. ~5.9% of the full composite score
before any suppression, coverage shrink, or modifier is applied — and 0% for any name where it
is suppressed (all insurers, confirmed for THG). The full one-row-per-metric table with every
metric's effective composite weight is being built as `docs/spec/METRIC_REGISTRY.md` in
parallel; it is not reproduced in full here to avoid duplication and drift between the two
documents.

### 6.4 Market behavior: sub-weights

`advisor_engine.py:53-59` (`DEFAULT_TECHNICAL_WEIGHTS`, overridable via
`settings.json.market_behavior.weights`):

| Sub-metric | Weight |
|---|---|
| momentum_12_1 | 0.30 |
| risk_adjusted | 0.26 |
| relative_strength | 0.16 |
| drawdown_resilience | 0.14 |
| volume_confirmation | 0.08 |
| low_beta | 0.06 |
| technical_extended | 0.06 |

Sums to 1.0. Effective composite weight of e.g. `momentum_12_1` = `0.18 × 0.30 = 0.054`, ~5.4%
of the full composite before shrink/modifiers.

A module comment (`advisor_engine.py:45-52`, attached directly to this weight table) explicitly
argues `technical_extended`'s small weight is deliberate given "the literature behind adding
many technical indicators mostly shows data-snooping" — this is the closest thing to a stated
methodological justification for a specific weight value found anywhere in this codebase this
session. It is a comment, not a citation to an external validation result; treated here as a
design rationale, not evidence of fitting.

### 6.5 Bounded post-blend modifiers

`pipeline/advisor_engine.py:apply_modifiers` (lines 515-557), champion path:

| Modifier | Bound | Source function |
|---|---|---|
| sector_valuation | ±3 (per internal-audit orientation, not re-verified numerically this session) | `sector_percentile_modifier` |
| short_interest | up to −6 | `short_interest_modifier` |
| liquidity | −3 | `liquidity_modifier` |
| expectations | ±3 | `expectations_modifier` |
| macro_regime | ±3 | `macro_regime_modifier` |
| insider_activity | +5 / −3 | `insider_modifier` |
| institutional_13f | — (in champion path per Phase 3.3, per docstring) | `institutional_ownership_modifier` |
| congressional_buying | reward-only, up to +4 per prior orientation | `congressional_buying_modifier` |
| customer_concentration_risk | — (added to champion path per Phase 3.3) | `concentration_risk_modifier` |

**Combined cap, confirmed by direct read**: `total = round(max(-15.0, min(15.0,
uncapped_total)), 2)` (`advisor_engine.py:552`) — a hard ±15-point cap on the summed modifiers,
confirmed as a literal in the function body, not a config value. `geographic_concentration`
remains challenger-only (`apply_challenger_modifiers`, a separate function starting at line
560), per that function's docstring, for a stated correctness reason (geography-tagged revenue
often reflects shipping/contracting entity rather than end demand) rather than a coverage
reason. Individual per-modifier point caps (the ±3/±6/etc. figures in the table above) were
sourced from the internal audit's orientation and **not independently re-derived from each
modifier function's body this session** — flagged UNDETERMINED for the exact current numeric
caps on each of the nine modifiers; only the combined ±15 cap is independently confirmed by
direct code read.

A separate challenger variant (`score_variants.modifier_recalibration`, confirmed present in
THG's live row) uses a **different combined cap of 20.0** and allocates each modifier a
*fraction* of that cap (`fractions` object in `SAMPLE_OUTPUT.json`, e.g. `short_interest_penalty:
0.3` of the 20-point cap = 6 points max) — this is a distinct, non-champion scoring path; do not
conflate its ±20 cap with the champion's ±15 cap.

### 6.6 Weight provenance

`git log --oneline -- pipeline/config/settings.json` (run directly this session): **9 commits
total** touch this file across its history. None of their messages reference fitting, IC
optimization, backtesting, or calibration against outcome data — they read as feature additions
(`"Wire customer-concentration, geographic-concentration, and 13F risk into the live score"`,
`"Add a reward-only Congressional-buying modifier"`) and periodic data refreshes. `git log -S`
on a specific weight literal (`ev_to_ebitda: 0.27`) returned only a data-refresh commit, meaning
that value has not changed since before the searchable history window used this session (or was
present from the file's current form onward without a weight-specific commit isolating its
introduction — the search does not distinguish these two cases without deeper history spelunking
not performed this session).

**Direct answer to the brief's question: no evidence was found, in either the current code or
its git history, that any weight in this system has been fitted to or validated against
outcome data.** This is corroborated from a second angle: `pipeline/advisor_engine.py:
data_coverage_scalar`'s docstring (lines 830-836) states outright that "a real confidence
metric, validated against realised prediction error, is Phase 8 work and does not exist yet,"
and the live artifact's `historical_calibration` component is `null` for every row (confirmed
for THG in `SAMPLE_OUTPUT.json`'s `data_coverage_detail.components.historical_calibration`),
with the gating explanation `"insufficient prospective calibration history (requires 24
eligible IC periods)"`. `pipeline/score_calibration.py` exists and implements a gate for this,
but the gate has apparently never opened. See §12 (pending) for the fuller test/validation
inventory.

---

## 7. Confidence and coverage

**Not one formula — at minimum four distinctly-named, distinctly-defined scalars publish on the
same row, all descending from the same underlying "how much intended evidence resolved"
concept, none validated against outcomes:**

1. **`row["data_coverage"]`** (top-level, legacy/champion path) = `data_coverage_scalar(coverage)`
   = `0.65·coverage[fundamentals] + 0.25·coverage[market_behavior] + 0.10·coverage[news_sentiment]`
   (`advisor_engine.py:827-843`). THG: `0.87`.
2. **`analysis_v2.structural.coverage`** (shadow path) = `available_weight / applicable_weight`
   over the fundamentals category weights specifically, computed inside
   `scoring_v2.build_v2_analysis` (verified against current file, lines 84-159 read in full
   earlier this session). THG: `0.84`. This is a *different population* from #1 (fundamentals
   only, not blended with market/news) computed by *different code* (`scoring_v2.py`, not
   `advisor_engine.py`) reading a *different data structure* (`observations`, the v2 provenance
   layer, not the flat scalar snapshot `scorer.py` reads) — not simply a relabeling of #1.
3. **`analysis_v2.structural.evidence_weight_resolved`** = `coverage × provenance_reliability −
   conflict_penalty − stale_penalty`, where `provenance_reliability` is a **hardcoded literal**:
   `0.72 if observations else 0.55` (`scoring_v2.py:162`, confirmed present, no derivation or
   config reference given for either constant). THG: `0.61`.
4. **`analysis_v2.timeliness.coverage`** = `0.0` for THG — the timeliness layer's own coverage,
   confirmed `0.0` because neither of its two inputs (`forward_eps_revision_30d`,
   `earnings_surprise`) resolved. This is correctly a *different number for a different layer*,
   not a bug, but it is a fifth-ish scalar in the same conceptual family appearing in the same
   payload.
5. `data_coverage_detail.components` (published via `pipeline/data_coverage.py`,
   `data_coverage_components`, read in full this session) breaks #1 into five named components
   — `completeness` (recomputes the *identical* #1 formula, by the module's own docstring
   confirmation: "Identical to the blend the champion's scalar already computes ... reused, not
   rewritten, so this component and the scalar can never silently disagree",
   `data_coverage.py:43-51`), `freshness` (linear decay, `null` if `data_fetched_at` is absent —
   `null` for THG), `source_reliability` (run-wide, not per-ticker — fraction of *configured*
   providers healthy this run; THG: `0.92`), `peer_sample` (peer count ÷ a configured
   full-strength target of 20; THG: `0.35`, from 7 valid P&C-insurer peers ÷ 20), and
   `model_agreement` (1 − stdev-of-challenger-scores/15-point scale; THG: `0.25`, meaning the
   champion and its challenger variants disagree by roughly `15×(1-0.25)≈11.25` points of
   standard deviation across variants — consistent with the champion (81.3) vs.
   cross-sectional-challenger (56.8) spread visible in THG's `score_variants`).

**Why they disagree, precisely**: #1 and #3 both claim to measure "how much evidence resolved"
but are computed from different code, different data structures, and in #3's case, an explicit
hardcoded reliability discount (`0.72`/`0.55`) that #1 does not apply at all. #2 restricts the
population to fundamentals only; #1 blends three components. None of the five numbers is a
statistical property of the signal (dispersion, realized error, hit rate) — this is stated
explicitly and repeatedly in the code's own docstrings (`data_coverage.py:10-15`,
`advisor_engine.py:830-836`), which independently corroborates §6.6's conclusion that no
validated confidence metric exists in this system.

**Verdict relative to the brief's framing**: the brief asks for "the legacy path and the shadow
path" producing "different numbers for the same name" — true, but the actual shape is not two
numbers, it is at least four to five, spread across two top-level paths and one decomposition
module, and as of `cd581b5` they are distinctly named rather than all called "confidence." I
judge this an improvement in transparency (a reader can no longer mistake one number for
"the" confidence) without being a resolution of the underlying multiplicity, and I'm stating
that judgment explicitly rather than letting the renaming read as a fix on its own.

---

## 8. Guidance and policy

### 8.1 Live (authoritative) — `advisor_engine.action_for`

Full "2-of-3" rule, `advisor_engine.py:715-799`, verified in full this session:

Three concern groups, each independently evaluated with an explicit `None`-safe check before
any threshold comparison (via a `_reading()` helper — the fail-open pattern the internal audit
flagged, `... or 0`/`... or 99`, is confirmed **absent** from the current function body):

| Group | Triggers (all thresholds are literals in the function body, confirmed by direct read) |
|---|---|
| `fundamentals` | any of `profitability`/`financial_health`/`accounting_quality`/`growth` category `< 45`; `interest_coverage < 2`; `accruals_ratio > 0.10` |
| `market_behavior` | `max_drawdown_252d < -30`; `relative_strength_20d < -10`; (`return_60d < -15` AND `return_20d < 0`) |
| `positioning` | ≥3 articles averaging sentiment `< -0.15`; `short_percent_of_float >= 0.15` |

```
agreement = count of groups with ≥1 triggered concern
agreement ≥ 2 and score < 45  → SELL,  trim 100%, strength "high"
agreement ≥ 2                 → TRIM,  trim 33% (2 groups) / 50% (3 groups), strength "moderate"
agreement == 1                → WATCH, trim 0%
stance in (ATTRACTIVE, PROMISING) and agreement == 0 → HOLD, strength "high"
else                           → HOLD, strength "moderate"
```

Every input that could not be evaluated is appended to an `unmeasured` list rather than
defaulting to "no concern" or "concern" — confirmed structurally: each check is
`if value is None: unmeasured.append(...) elif <threshold>: concerns[...].append(...)`, so a
missing input contributes to neither branch. Verified against THG: one unmeasured input
(`positioning.news_sentiment`), zero triggered concerns, `agreement_count: 0`, action `HOLD`.
There is no stop-loss, trailing stop, ATR rule, time stop, or re-entry rule anywhere in this
live function — `suggested_trim_pct` is a constant per branch (0/33/50/100), not computed from
position size or price.

`stance_for` (`advisor_engine.py:815-824`): gated first on `data_coverage < 0.45 →
"INSUFFICIENT DATA"`; else `score >= 75 → ATTRACTIVE`, `>= 60 → PROMISING`, `>= 45 → MIXED`,
else `CAUTION`. THG: `data_coverage 0.87`, `score 81.3` → `"ATTRACTIVE"`, confirmed matching the
published `stance` field exactly.

### 8.2 Shadow — `recommendation_policy_v2.py`, `shadow_mode: true` (confirmed in
`pipeline/config/recommendation_policy_v2.json`, and echoed in every published row's
`recommendation_v2.policy_mode: "shadow"` / `legacy_recommendation_unchanged: true`)

**Two-axis classification** (`two_axis_classification`, lines 65-97, verified in full):
compares `structural_score` and `timeliness_score` against `cfg["score_matrix"]` thresholds
(`recommendation_policy_v2.json`: `structural_strong: 75, structural_acceptable: 55,
timeliness_buy: 70, timeliness_tactical: 75, timeliness_acceptable: 55, timeliness_weak: 50`).
Critically, **`timeliness_score is None` is its own branch**, not a numeric comparison against
a substituted value: `structural >= 75 → "quality_watch_timeliness_unavailable"`;
`structural >= 55 → "hold_or_watch_timeliness_unavailable"`; else
`"avoid_or_sell_thesis"`. Verified exactly against THG (`structural effective_score` 74.7 or
74.5 [see the unresolved discrepancy noted in `TRACE_THG.md` §4] — either value is `>= 55` and
`< 75` — `timeliness_score: null` → `"hold_or_watch_timeliness_unavailable"`, matching the
published `matrix_classification` exactly).

**Stop-loss / floor logic** (`_stop_state`, lines 323-376, verified in full): reads a named
`stop_profile` from `config["stop_profiles"]` (default profile confirmed to exist; other named
profiles not enumerated this session). Two independent stop rules can fire:
- `hard_cost_basis_stop`: `threshold = cost_basis * (1 + hard_cost_basis_pct/100)`; triggers if
  `current_price <= threshold`.
- `trailing_high_water_stop`: threshold computed one of three ways depending on
  `profile["mode"]` — `atr_based` (`high_water_mark − atr_multiple × ATR`),
  `volatility_adjusted` (a realized-volatility-scaled decline, clamped between configured
  min/max trailing percentages), or a flat `trailing_high_water_pct` off the high-water mark.

Both rules require a configured number of "confirming closes" (`persistence_closes`) before
being treated as confirmed, not triggered on a single-day breach — the `first_breached_at` /
`confirmed_at` fields in the payload are for tracking this persistence requirement over time.
**This machinery exists, is fully implemented, and is not reachable by any live position in the
current artifact** because `position_action.classification: "no_position"` for every row with
no portfolio context (confirmed for THG: `position_rule_state.classification: "no_position"`,
`rules: {}`) — `_stop_state` returns the `no_position` short-circuit (line 324-325) before any
of the above logic runs when `position` is falsy. **The brief's requested NEM floor/recovery
example ($85.18 / $107.13) is NOT produced by this stop-loss machinery** — it is produced by an
entirely separate, frontend-only mechanism (`src/lib/dipWatch.js`), detailed next.

**Trim sizing** (`_trim_percent`, lines 388-416, verified in full): `computed = base_by_flag_
count[n] × severity_multiplier × confidence_multiplier × concentration_multiplier ×
liquidity_multiplier × (1.0 if urgent else tax_cost_multiplier)`, clamped to
`[minimum(0.10), maximum(0.75)]` once positive. Five independent multiplier tables, each
sourced from `recommendation_policy_v2.json`'s `trim` block (confirmed present with the exact
band values quoted in §0's config excerpt earlier this session:
`base_by_flag_count: {"2": 0.20, "3": 0.50}`, `severity_multipliers: {mild: 0.75, moderate: 1.0,
severe: 1.5}`, `confidence_multipliers: {limited: 0.50, normal: 0.85, high: 1.0}`,
`concentration_multipliers: {below_target: 0.75, near_target: 1.0, overweight: 1.25,
severely_overweight: 1.5}`, `liquidity_multipliers: {high: 0.85, normal: 1.0, low: 1.10}`,
`tax_cost_multipliers: {high: 0.60, normal: 0.85, low: 1.0}`).

**Entry/re-entry rules** (`evaluate_entry_rules`, lines 450-508, verified in full): four
mutually exclusive states — `reentry_after_stop` (requires cooldown days elapsed, a recorded
"recovery condition met" flag, and score requalification), `initial_buy` (requires
`company_label` in `buy/accumulate/tactical_candidate` and no portfolio/thesis block or
earnings blackout), `average_down` (only when currently losing on the position; requires
`structural_score >= structural_strong` AND a *resolved and non-weak* timeliness score — an
unresolved timeliness layer explicitly blocks averaging down, per the function's own comment,
"Unknown timing is not positive timing" — plus a `valuation_meaningfully_improved` flag, a
minimum interval since the last add, and a cap on total additions), and `add_to_winner`
(when not losing, requires `buy`/`accumulate` label).

**Portfolio fit** (`classify_portfolio_fit`, lines 286-320, verified in full): `below_target`
whenever `current_weight < target_weight × 0.75`. With no portfolio supplied, `current → 0.0`,
`target → default_target_weight (0.03)` — `0 < 0.0225` is always true, so **`below_target` is
guaranteed for every unpositioned name**, confirmed still true and confirmed still the published
value for THG. This one item from the internal audit's findings is **not fixed** — it is a
structural property of evaluating portfolio fit with no portfolio, not a bug that was patched
alongside the others in §0.

### 8.3 Floor and recovery levels — the actual mechanism (frontend, not the shadow policy)

`src/lib/dipWatch.js`, read in full this session. This is a **client-side, JavaScript**
computation over the already-published row — not part of the Python pipeline or the shadow
policy's stop-loss machinery in §8.2.

```
weekHigh = price / (1 + pct_from_52w_high/100)     // back-calculated from published fields
weekLow  = price / (1 + pct_above_52w_low/100)
drawdownFloor = weekHigh × (1 + max_drawdown_252d/100)      // if max_drawdown_252d available
longTermFloor = (weekLow + drawdownFloor) / 2                // else weekLow alone
longTermMax   = longTermFloor × 1.20                          // RECOVERY_GAIN_OFF_FLOOR = 0.20
recent        = {high, low} over the trailing 60 close prices (RECENT_WINDOW_DAYS)
floor = recent.low × 0.6 + longTermFloor × 0.4        // RECENT_WEIGHT = 0.6
max   = recent.high × 1.02 × 0.6 + longTermMax × 0.4   // BREAKOUT_BUFFER = 0.02
status = "recovering" if price >= max
         "near_floor"  if price <= floor × 1.05         // NEAR_FLOOR_BAND = 0.05
         "in_range"     otherwise
```

Gated to fire only when `stock.stance` is `ATTRACTIVE`/`PROMISING` (`ELIGIBLE_STANCES`) **and**
the stock is not already flagged `TRIM`/`SELL` by the live `action_for` recommendation **and**
is currently down ≥8% from its 52-week high with a non-positive 60-day return
(`DOWN_FROM_HIGH_THRESHOLD = -8`). All six constants (`-8, 0.20, 0.05, 60, 0.6, 0.02`) are
literals in this one file, not sourced from `settings.json` or any Python config — **this is a
fully independent, undocumented-outside-this-file threshold set from every other bounded
parameter in the system**, and I did not find any cross-reference or shared config linking it to
the modifier caps or band cutoffs described elsewhere in this document. This directly answers
the brief's NEM floor/recovery example request: reproducing NEM's specific published $85.18/
$107.13 figures would require NEM's actual `price`, `pct_from_52w_high`, `pct_above_52w_low`,
`max_drawdown_252d`, and 60-day close history as of the run that produced those numbers, none of
which were pulled this session — the **formula** above is fully verified; the **specific NEM
numbers** are UNDETERMINED without re-running this calculation against NEM's actual data.

---

## 9. Publication contract

*(Section written from a dedicated research pass over `SAMPLE_OUTPUT.json`, the code paths that
produce each field, and every `src/` consumer. All citations verified directly against code read
this session.)*

### 9.1 Field-by-key annotation of `SAMPLE_OUTPUT.json` (THG)

Organized by substructure. One row per distinct field *shape* — repeated per-metric objects
(e.g. `fundamental_detail.<metric>`, `metric_status.<metric>`, `normalization.<metric>`) are
shown once with the metric name as an example, since the shape is identical across the ~29
metrics.

#### 9.1.1 Row identity / raw snapshot (top level)

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `ticker`, `name`, `sector`, `industry` | string | no | Identity/classification strings, straight from provider snapshot | `pipeline/canonical_metrics.py` snapshot construction (merged into the row via `**snapshot` at `advisor_engine.py:1124`) |
| `price`, `market_cap`, `dividend_yield`, `beta`, … (raw fundamentals: `price_to_book`, `forward_pe`, `debt_to_equity`, etc.) | number | yes | Raw provider values, pre-scoring | Same snapshot merge, `advisor_engine.py:1124` |
| `is_etf` | bool | no | ETF flag used for `StockDetailModal.jsx`'s `isEtf` branch and pipeline peer-group routing | Snapshot field, read at `pipeline/peer_groups.py:64` and `src/components/StockDetailModal.jsx:126` |
| `observations` | object of `{metric: [Observation, …]}` | metric-keyed, each list can be empty | Full per-metric provenance: `value`, `unit`, `source`, `source_field`, `observed_at`, `fetched_at`, `is_ttm`, `is_forward`, `quality_flags`, `transform_version` | `Observation` dataclass, `canonical_metrics.py:43-58` |
| `piotroski_tests` | object of 7 named booleans | no | The 7 individual Piotroski F-score component tests | `pipeline/fundamentals_extended.py:derive_piotroski` |
| `statement_periods` | array of ISO date strings | no | Fiscal period-end dates the statement-derived metrics are computed from | `fundamentals_extended.py`, attached during `enrich()` (`fetch_advisor.py:1465`) |
| `extended_coverage` | number [0,1] | no | Fraction of the ~13 statement-derived (extended) metrics that resolved | `fundamentals_extended.py` — exact producer line UNDETERMINED |

#### 9.1.2 Champion score block (top level)

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `score` | number | no | Final published champion score, post-modifiers | `advisor_engine.py:1109` (`apply_modifiers`), formula §4.2 |
| `base_score` | number | no | Score after the second coverage shrink, pre-modifiers | `advisor_engine.py:861` (`blend_research_components`) |
| `raw_score` | number | no | Weighted blend of the three components, pre-shrink | `advisor_engine.py:1108` |
| `stance` | enum string | no | `ATTRACTIVE`/`PROMISING`/`MIXED`/`CAUTION`/`INSUFFICIENT DATA` | `advisor_engine.py:815-824` (`stance_for`) |
| `data_coverage` | number [0,1] | no | Legacy/champion blended coverage scalar (§7 item 1) | `advisor_engine.py:827-843` |
| `components` | object `{fundamentals, market_behavior, news_sentiment}` | sub-fields nullable | Per-pillar scores feeding the blend | `advisor_engine.py:1101` |
| `fundamental_categories` | object, 6 named category scores | nullable (withheld categories) | Category-level scores post required-metric gate | `scorer.py:_categories_with_required_gate` |
| `sector_valuation_percentile` | number (16.7/50.0/83.3) or `null` | yes | Tier-ordinal (**not a raw percentile despite the name**) fed into `sector_percentile_modifier`, echoed onto the row | `advisor_engine.py:1130`; kept in sync with `valuation_percentile.ordinal` by an invariant check at `pipeline/validate_data.py:179` |
| `modifiers` | object `{applied, total, uncapped_total, notes}` | `applied` keys vary per row | The bounded modifier stack, §6.5 | `advisor_engine.py:apply_modifiers` (515-557) |
| `strengths`, `risks` | array of pre-formatted strings | no | Fully server-baked sentences (e.g. `"Strong valuation score (90/100)"`) — **not templates the frontend fills in; the exact string ships from Python** | `advisor_engine.py:build_evidence` (1034-1090) |
| `recommendation` | object | no | Legacy `action_for` output: `action`, `suggested_trim_pct`, `agreement_strength`, `agreement_count`, `reasons`, `summary`, `unmeasured_inputs`, `factors` | `advisor_engine.py:action_for` (715-799), §8.1 |
| `news_available` | bool | no | Whether any sentiment-eligible articles resolved this window | `advisor_engine.py:1129` |

#### 9.1.3 `fundamental_detail` (champion bands-mode detail)

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `<metric>` (e.g. `forward_pe: 100.0`) | number 0-100 or `null` | yes — `null` for suppressed/unavailable | Discrete band score for one metric | `scorer.py:_band_valuation_score` step 3, §4.1 |
| `categories` | object | mirrors `fundamental_categories` | Duplicate of the row-level category scores | `scorer.py:_categories_with_required_gate` |
| `coverage` | number [0,1] | no | Fraction of metric *weight* resolved, exempting suppressed metrics | `scorer.py:weighted_coverage` (496-512) |
| `raw_score` | number | no | Pre-shrink fundamentals score | `scorer.py:609` |
| `applicability_profile` | string | no | The resolved business profile | `canonical_metrics.py:classify_profile` (95-130) |
| `suppressed_metrics` | array of metric-id strings | no (can be empty) | Metrics zeroed out for this profile — **disagrees in membership with `analysis_v2.applicability.suppressed_metrics` for THG; root-caused in §10.2 item 9** | `scorer.py:548` |
| `categories_withheld` | object, keyed by category | can be `{}` | Categories zeroed by the required-metric gate | `scorer.py:_categories_with_required_gate` (515-535) |
| `sales_multiple_basis` | string or `null` | yes | Which raw metric (`ev_to_sales`) backs the derived `sales_multiple` score | `scorer.py:284, 622` |
| `normalization_mode` | const string `"bands"` | no | Declares which of the two live normalization modes produced this block | `scorer.py`, reads `SETTINGS.get("normalization_mode")` |

#### 9.1.4 `technical_detail`

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `return_5d`/`20d`/`60d`/`252d`, `max_drawdown_252d`, `sharpe_ratio`, `sortino_ratio`, etc. | number | yes (price-history depth) | Raw and derived price-series statistics | `advisor_engine.py:technical_factors` (line 95) |
| `technical_extended_detail.raw` / `.scored` | object of 4 named indicators | yes per-indicator | Raw and 0-100 scored indicator values | `pipeline/technical_indicators.py` |
| `momentum_12_1`, `risk_adjusted`, `relative_strength`, `drawdown_resilience`, `volume_confirmation`, `low_beta`, `technical_extended` | number 0-100 | yes | The 7 named sub-scores feeding `market_behavior`, weights per §6.4 | `advisor_engine.py:technical_factors` |
| `coverage` | number [0,1] | no | Technical-pillar coverage | Same function |
| `short_horizon_treatment` | enum string | no | Which short-horizon regime (`neutral`/`reversal`) was applied | Same function |

#### 9.1.5 `sentiment_detail`, `insider_activity`, `concentration_risk`, `geographic_exposure`

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `sentiment_detail.{article_count, average, weighted_average, coverage, news_available, weighting_method}` | mixed | several nullable when no news | Sentiment-pillar detail | `advisor_engine.py:sentiment_score` (line 237) |
| `insider_activity.{source, score_points, transactions_reviewed, buy_cluster, sell_cluster, method, notes}` | object | mostly null when `available: false` | Cohen/Malloy/Pomorski routine-vs-opportunistic Form 4 classification | `pipeline/insider_signal.py:score_insider_activity` (179), attached `fetch_advisor.py:1584` |
| `concentration_risk.{score_points, measured, available, reason, percentages}` | object | `available: false` for THG | ASC 280 customer-concentration signal | `pipeline/concentration_risk.py:score_concentration_risk` (54), attached `fetch_advisor.py:1590` |
| `geographic_exposure.{score_points, available, reason, shares}` | object | `available: false` for THG | ASC 280 geographic-revenue-split signal, challenger-only per §6.5 | `pipeline/geographic_exposure.py:score_geographic_concentration` (61), attached `fetch_advisor.py:1591` |
| `congressional_activity` | object or `null` | yes — `null` for THG | STOCK Act buying signal | attached `fetch_advisor.py:1586` — **confirmed never read anywhere in `src/`, §9.4** |

#### 9.1.6 `analysis_v2` (shadow structural/timeliness layer)

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `structural`/`timeliness` (identical shape: `raw_score`, `effective_score`, `evidence_weight_resolved`, `coverage`, `weight_renormalization{…}`, `missing_metrics`, `suppressed_metrics`, `classification`, `categories`/`forward`) | object | most numeric sub-fields nullable when unresolved | The two-layer structural/timeliness decomposition, §7 items 2-4 | `pipeline/scoring_v2.py:build_v2_analysis` (79) |
| `metric_status.<metric>.{status, value, score_contribution, replaced_by, reason, quality_flags}` | object per metric | `value`/`score_contribution`/`replaced_by`/`reason` independently nullable | Per-metric applicability/status detail, §5 | `scoring_v2.py`, via `applicability_for` (`canonical_metrics.py:141-150`) |
| `applicability.{profile_id, profile_confidence, applied_metrics, suppressed_metrics, replacement_metrics, unavailable_replacement_metrics, critical_data_gaps}` | object | arrays can be empty; `profile_confidence` is `0.0` for THG | Registry-level applicability summary, distinct from `business_profiles.json`'s registry per §5 | `scoring_v2.py:241-247` |
| `canonical_metrics` (e.g. `{"peg": null}`) | object | value nullable | A canonical-PEG side-computation | `scoring_v2.py:268` — **confirmed never read in `src/`, §9.4** |
| `screen_memberships` | array | can be `[]` | Which research screens this ticker currently qualifies for | `scoring_v2.py:256` — **confirmed never read in `src/`, §9.4** |
| `position_action` | `null` at this path for THG | yes | Structurally-identical sibling of `recommendation_v2.position_action`, at this path — **confirmed never read in `src/`, §9.4; only `recommendation_v2.position_action` is consumed** | `scoring_v2.py` |

#### 9.1.7 `recommendation_v2` (shadow policy)

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `company_structural_state`/`company_timeliness_state` | object | mirrors `analysis_v2.structural`/`.timeliness` (near-duplicate) | Same shape, second copy at this path — **root of the 74.7 vs. 74.5 `effective_score` discrepancy, root-caused in §10.2 item 8** | `pipeline/recommendation_policy_v2.py:build_recommendation_v2` (511) |
| `portfolio_fit_state` / `portfolio_fit` | object `{current_weight, target_weight, maximum_weight, classification, …}` | `classification` never null | `below_target` structural constant for unpositioned names, §8.2/§10.2 item 7 | `recommendation_policy_v2.py:classify_portfolio_fit` (286-320) |
| `position_rule_state` / `position_rules` | object | `rules: {}` when `no_position` | Stop-loss/floor machinery output, §8.2 | `recommendation_policy_v2.py:_stop_state` (323-376) |
| `company.structural`/`company.timeliness`, `company_action`, `matrix_classification`, `deterioration_groups`, `action` | object/array | `action` fields non-null; layer scores nullable | Two-axis classification + deterioration flags | `recommendation_policy_v2.py:two_axis_classification` (65-97) |
| `entry_action.{type, strategy, allowed, reason_codes}` | object | `allowed` always bool | Entry/re-entry gating | `recommendation_policy_v2.py:evaluate_entry_rules` (450-508) |
| `data_quality.{unassessed_layers, evidence_weight_resolved, data_coverage, missing_critical_metrics, severe_unresolved, …}` | object | several array/bool fields | Shadow-path evidence-quality summary — `unassessed_layers` consumed in `src/`; `missing_critical_metrics`/`severe_unresolved` **confirmed never read in `src/`, §9.4** | `recommendation_policy_v2.py:build_recommendation_v2` |
| `thesis_break_event` | `null` for THG | yes | Structural-break detector output | `recommendation_policy_v2.py:604` — **confirmed never read in `src/`, §9.4** |
| `critical_field_requirements` | array | can be `[]` | Duplicate, at this top-level path, of `analysis_v2.applicability.critical_data_gaps` | `recommendation_policy_v2.py:605` — **confirmed never read in `src/`, §9.4** (only `applicability.critical_data_gaps` is rendered, `LiveValidation.jsx:41`) |
| `legacy_recommendation_unchanged` | const `true` | no | Self-declares the shadow policy is non-authoritative | `recommendation_policy_v2.py:606` — **confirmed never read in `src/`, §9.4** |

#### 9.1.8 `valuation_percentile` (peer tier — full trace in §9.3)

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `peer_context` | object or `null` | `null` below 30 valid peers | Contains `tier`, `tier_phrase`, `tier_count`, `peer_count_with_valid_data`, `ranked_quantity_note` |
| `tier` | enum string or `null` | yes | `cheapest_third`/`middle_third`/`most_expensive_third` |
| `ordinal` | number (16.7/50.0/83.3) or `null` | yes | Tier midpoint — never a fine-grained percentile |
| `peer_group_id`, `peer_group_label` | string | no | Which profile/sector group this ticker was ranked in |
| `peer_count_total`, `peer_count_with_valid_data`, `minimum_peer_count` | integer | no | Sample-size transparency fields |
| `invalid_reason` | string or `null` | yes | `"insufficient_valid_peers"` when below minimum |
| `bottom_peers`, `top_peers` | array of `{ticker, value}` ×3 | no | Context peers regardless of whether a tier was assigned |

Producer for the whole block: `pipeline/peer_groups.py:canonical_percentiles`/`_metadata` (lines
99-170), attached at `pipeline/fetch_advisor.py:1613`.

#### 9.1.9 `score_variants`, `data_coverage_detail`, `evidence`, `estimate_detail`, `theme_exposure`, `history`

| Field | Type | Nullable | Meaning | Producer |
|---|---|---|---|---|
| `score_variants.{champion, normalization, short_horizon, confidence_shrinkage, modifier_recalibration, challenger}` | object per variant | variant-dependent | Full alternate scorings of the same evidence (§4.4, §6.5) — `normalization.fundamental_detail.normalization.<metric>` is the per-metric cross-sectional block (`raw_percentile`, `desirability_percentile`, `peer_count`, `normalization_scope`) consumed by `ScoreExplainability.jsx` (§9.3) | `pipeline/scorer.py:CrossSectionalNormalizer` (307) + `advisor_engine.py` variant builders (846-1032) |
| `data_coverage_detail.{data_coverage, components{completeness, freshness, source_reliability, peer_sample, model_agreement, historical_calibration}, limitations, interpretation}` | object | several component sub-fields nullable | Decomposed coverage explanation, §7 item 5 | `pipeline/data_coverage.py:data_coverage_components` (151) |
| `evidence.{news_events[], news_score, news_detail, insider_events[], insider_score, insider_score_long_term, insider_detail, expectation_score, expectation_detail}` | object | array fields can be empty | Dated, decayed evidence-event model backing the sentiment/insider/expectation scores | `pipeline/evidence_events.py:build_evidence` (395) |
| `estimate_detail.{revision_breadth_30d, eps_revision_30d_pct, net_upgrades_90d, consensus_target, target_change_30d_pct, inputs_resolved}` | object | numeric fields nullable | Consensus-estimate revision snapshot; also duplicated as bare top-level fields (only the nested `estimate_detail.*` copies are confirmed read client-side, via `src/lib/rankingModels.js:113`) | `pipeline/yahoo_estimates.py:collect_estimate_detail` |
| `theme_exposure` | array (`[]` for THG) | no | Theme-exposure matches | `pipeline/themes.py:score_theme_exposure` |
| `history.points[]` | array of `{recorded_at, refresh_id, champion_score, challenger_score, champion_stance, challenger_stance, category_scores}` | no | Stored score-history snapshots for the trend chart | `explainability.py`, attached via `attach_explainability` (248) |

### 9.2 Frontend consumption: where `advisor.json` is loaded

- **Single loader, no service worker.** `src/lib/useData.js:67-129` (`useData(file)`) is the one
  hook that fetches `public/data/*.json` files. `src/workers/` contains only
  `projectionWorker.js` (a Monte-Carlo compute worker), unrelated to data loading.
- The fetch itself: `useData.js:95` —
  `fetch(\`${import.meta.env.BASE_URL}data/${file}?v=${Date.now()}\`, { cache: 'no-store' })` — a
  plain client-side runtime fetch of the statically-committed JSON, cache-busted per call, not a
  build-time import. This matches §1's description of the render-time path exactly.
- **Caching**: successful payloads are written to `localStorage` under
  `dash:last-refresh:<file>` (`useData.js:9,30-38`) so a reload shows the last-seen snapshot
  immediately while a background revalidation runs (`useData.js:85-89`).
- **Schema migration on the way in**: `useData.js:98-99` calls `migrate(datasetFor(file), raw)`
  from `src/lib/schemaMigrations.js` before the data reaches a component. For `advisor.json` rows
  this performs additive-only fixups, including the `valuation_percentile` migration at
  `schemaMigrations.js:153-161` (drops legacy `value`/`display_value` keys, backfills
  `peer_context`/`tier`/`ordinal` to `null` if absent, nulls the legacy
  `sector_valuation_percentile` if the row predates the ordinal system).
- **Call sites**: 14 pages/components call `useData('advisor.json')` directly
  (`src/pages/{Watchlist,Methodology,Search,Dashboard,Picks,Insights,PolicyRadar,Glossary,
  Diversification,ThemeExposureScreen,Finances,StrategyScreen,OptionsScreen}.jsx`,
  `src/components/ModelVersionFooter.jsx`), each independently calling the hook — `useData`'s
  module-level `inFlightRequests`/`memoryPayloads` maps deduplicate concurrent fetches across
  these call sites (`useData.js:10-11`).

**Baked-in-Python vs. assembled-in-React, concretely:**
- Fully server-baked text strings, shipped verbatim: `strengths`/`risks`
  (`advisor_engine.py:1034-1090`), `modifiers.notes` (per-modifier explanation sentences, e.g.
  `"FRED macro regime is supportive for Financial Services (68/100)"`),
  `recommendation.summary`, `valuation_percentile.peer_context.tier_phrase`/
  `ranked_quantity_note`, `data_coverage_detail.interpretation`/`limitations`,
  `analysis_v2.timeliness.unavailable_reason`. None of these are template-filled client-side;
  React renders them as-is.
- Computed/formatted in React: currency/percent formatting (`src/lib/formatters.js`), the peer-
  context *sentence structure* wrapping the server-baked `tier_phrase` (`StockDetailModal.jsx:255`,
  §9.3), score-band groupings (`src/lib/scoreBands.js`), price-target suggestions
  (`watchlistPriceTargets.js`, entirely client-side math over published fields), stop-loss levels
  for *live positions* (`src/lib/positionRisk.js`, since the shadow policy's own stop machinery is
  unreachable per §8.2), dip/recovery floor levels (`src/lib/dipWatch.js`, §8.3), and all nine
  `rankingModels.js` composite scores (client-side re-blends of published numeric fields for the
  site's various screen pages, distinct from the pipeline's own scoring).

### 9.3 The peer-percentile sentence — full trace, including two live discrepancies

**The fixed, primary mechanism** — confirmed correctly wired end-to-end:

1. `pipeline/peer_groups.py:99-170` (`canonical_percentiles`/`_metadata`) enforces
   `MINIMUM_VALID_PEERS = 30` (line 36) and publishes `tier_phrase` pre-written per
   `TIER_LABELS` (lines 38-42), never a raw percentage.
2. Attached to the row at `pipeline/fetch_advisor.py:1613`.
3. Rendered at **`src/components/StockDetailModal.jsx:253-259`**, inside the "Explore the
   evidence" panel (`StockDetailModal.jsx:199-260`): the JSX reads `percentile.peer_context.
   tier_phrase` directly and only assembles the surrounding sentence scaffold — it does not
   recompute a percentage. A code comment immediately above (`StockDetailModal.jsx:248-252`)
   explicitly documents the old broken percentage sentence as the thing being replaced. THG
   (7 valid peers < 30) renders the "No peer comparison published" branch, matching
   `SAMPLE_OUTPUT.json`'s `valuation_percentile.peer_context: null` exactly.

**Two further mechanisms found this pass, not part of the original fix's scope:**

1. **`ScoreExplainability.jsx` renders a genuine "Nth percentile" sentence, gated by a different
   and much lower sample-size floor.** `MetricExplanation`
   (`src/components/ScoreExplainability.jsx:56-72`, rendered inside
   `StockDetailModal.jsx:279`) renders, per metric: `` `${ordinal(metric.sector_percentile)}
   percentile in ${scope}` `` (e.g. "51st percentile in Financial Services"). This is sourced
   from `metric.sector_percentile`, populated at `pipeline/explainability.py:145` from the
   **cross-sectional challenger's** per-metric block
   (`score_variants.normalization.fundamental_detail.normalization.<metric>`), produced by
   `pipeline/scorer.py:CrossSectionalNormalizer` with `self.sector_minimum = int(config.get(
   "sector_minimum_count", 8))` (`scorer.py:320`) — **a minimum of 8 sector peers (falling back
   to the full universe below that, `scorer.py:426`), not 30**. `attach_explainability`
   (`pipeline/explainability.py:248-268`) wires this same cross-sectional variant into the
   metric explanations for **both** the `champion` and `challenger` tabs, and `active_variant`
   defaults to `"champion"` (`explainability.py:258`) — so this per-metric percentile sentence is
   the **default-visible** explanation attached to a champion score that was itself computed with
   zero percentiles (bands mode, §4.4). This is a different field (per-metric multiple, not the
   composite valuation category) and a different, much weaker sample-size floor than the one the
   MINIMUM_VALID_PEERS=30 fix established as the system's standard — a live percentile sentence
   the fix did not reach. **Flagged as a new finding, §10.2 item 10.**
2. **`src/lib/watchlistPriceTargets.js` maintains its own copy of the tier-phrase wording,
   independent of the published string.** `TIER_PHRASES` (`watchlistPriceTargets.js:47-51`) is a
   hand-written map (`cheapest_third: 'the cheapest third of its peer group'`, etc.) used at line
   75 to build the "good buy price" suggestion sentence. It reads only the raw `tier` key and
   `ordinal` number off `stock.valuation_percentile` — it never reads the server-baked
   `peer_context.tier_phrase` string `StockDetailModal.jsx` uses. The wording is currently
   consistent with Python's `TIER_LABELS`, but is a second, independently-maintained copy of the
   same three phrases that would silently drift if `TIER_LABELS` wording ever changed. This is a
   live client-side reconstruction of tier text — smaller in scope than the retired percentage
   sentence (it stays in tier-language, bounded by the same `ordinal` gate), but it is exactly
   the "does any component still construct sentence text itself" case worth flagging.

No component was found constructing a **percentage**-style peer sentence (e.g. `"${pct}% of
peers"`) from `sector_valuation_percentile` or any other field — that field is confirmed used
only as a numeric input to internal client-side ranking-model math (`rankingModels.js`,
`modeConfidence.js`, `valueGrowthScore.js`, `researchScreens.js`), never formatted into peer-
comparison prose.

### 9.4 Fields confirmed never rendered anywhere in `src/`

Grep-verified (zero matches for the field name anywhere under `src/`, including tests) — the
pipeline computes and publishes these, but no page/component currently displays or reads them:
`congressional_activity` (`fetch_advisor.py:1586`), `data_quality_violations`
(`fetch_advisor.py:1612`), `alpha_enriched` (`fetch_advisor.py:1610`), `altman_z_variant`
(`scorer.py:623,663`), `fundamental_detail.sales_multiple_basis` (`scorer.py:622,662`),
`analysis_v2.canonical_metrics` (`scoring_v2.py:268`), `analysis_v2.screen_memberships`
(`scoring_v2.py:256`), `analysis_v2.position_action` (distinct from the consumed
`recommendation_v2.position_action`), `recommendation_v2.thesis_break_event`
(`recommendation_policy_v2.py:604`), `recommendation_v2.critical_field_requirements` (distinct
from the consumed `analysis_v2.applicability.critical_data_gaps`,
`recommendation_policy_v2.py:605`), `recommendation_v2.legacy_recommendation_unchanged`
(`recommendation_policy_v2.py:606`), `recommendation_v2.data_quality.missing_critical_metrics`/
`.severe_unresolved`.

By contrast, sibling-looking fields at nearby paths **are** consumed and should not be assumed
dead by association: `recommendation_v2.position_action`
(`RecommendationShadowPanel.jsx:63`, `LiveValidation.jsx:30`), `analysis_v2.applicability.
profile_confidence`/`unavailable_replacement_metrics`/`critical_data_gaps`
(`LiveValidation.jsx:35,40-41`), `recommendation_v2.data_quality.unassessed_layers`
(`RecommendationShadowPanel.jsx:119-120`).

This list is grep-verified but **not exhaustive** — a full field-by-field sweep of every path in
`SAMPLE_OUTPUT.json` against `src/` was not performed (see §11).

---

## 10. Known defects and contradictions

### 10.1 The brief's four "already-confirmed" defects — current status (see §0 for commit mapping)

1. **Peer percentile on a 14-name set** — **fixed** (`cb3cc53`). Verified: ≥30-peer minimum now
   enforced, THG correctly publishes no peer claim.
2. **`EARNINGS_TIMELINESS` at 0% coverage defaulting to 50/100** — **fixed** (`ac24342`).
   Verified: `null`/`null` published for THG, guarded by `layer_health.assert_layers_vary`
   against recurrence (guard's actual mechanics not independently read this session —
   UNDETERMINED whether it runs in CI or only at publish time; flagged for follow-up).
3. **Confidence figures disagreeing between paths** — **open, reshaped** (`cd581b5` renamed but
   did not consolidate). Verified: 4-5 distinctly-named, distinctly-computed scalars persist on
   one row, detailed fully in §7. I judge this a transparency improvement, not a resolution.
4. **Insurer DSO scored while P/B and D/E unavailable** — **fixed, and inverted** (`0e0a9ad`).
   Verified: DSO now suppressed, P/B and D/E now applied, for THG specifically and structurally
   for the whole insurer profile via the shared applicability registry.

### 10.2 Defects found independently this session, not in the brief or the internal audit

5. **A "replacement metric" does not inherit the suppressed metric's weight.** Detailed in full
   in §5. The applicability rule's `replaced_by` field is descriptive metadata; the actual
   weight redistribution is a blind renormalization across whatever remains applicable, so a
   metric named as the intended substitute for a heavily-weighted suppressed metric (e.g.
   `price_to_book` "replacing" `ev_to_ebitda`'s 0.27 weight) receives only its own small
   configured weight (0.05), while the freed weight is spread across every surviving metric in
   the category, not concentrated on the named replacement. **Severity: moderate** — this means
   the applicability system's documentation-in-data (`replaced_by`) overstates how much the
   named replacement actually matters to the resulting score, which could mislead a reader of
   the payload (or of `docs/spec/METRIC_REGISTRY.md`, if that document reports `replaced_by`
   without this caveat) into thinking the replacement metric carries more weight than it does.
6. **Two profiles absent from `business_profiles.json`'s `profiles` object.**
   `classify_profile` can return `"semiconductor"` or `"other_pre_profit"`, both of which have
   real suppression rules in `applicability_matrix.json` (confirmed working, e.g. CRUS), but
   neither appears in `business_profiles.json`'s `profiles` dict, which `scoring_v2.py` reads
   for `replacement_metrics`/`critical_metrics`. **Severity: not yet established** — I confirmed
   the gap exists in the config files but did not trace whether `scoring_v2.py`'s fallback for a
   missing profile entry (`(BUSINESS_PROFILES.get("profiles") or {}).get(profile, {})`, which
   defaults to an empty dict) causes any visible degradation for a real semiconductor name in
   the current artifact, or is a harmless dead branch because nothing downstream requires those
   two profiles to have replacement/critical metrics declared. Flagged for follow-up, not
   asserted as a confirmed live defect.
7. **`portfolio_fit: below_target` is a structural constant for every unpositioned name** — this
   item from the internal audit is confirmed **not fixed** (§8.2), unlike its three siblings.
   Severity: low for the *score* (portfolio fit is not an input to the composite score) but
   directly affects position-sizing guidance display for any user without a matching portfolio
   entry, which given `portfolio_coverage` limitations (not yet quantified this session — see
   §11) may be most published names.
8. **THG's `effective_score` appears as two slightly different values in one payload**: `74.7`
   (`recommendation_v2.company.structural.effective_score`) vs. `74.5`
   (`analysis_v2.structural.effective_score`) — same conceptual computation, same input `raw_
   score: 90.5`, not yet root-caused. Both round from a computation of the form `50 + confidence
   × (raw − 50)`; a 0.2-point gap implies the two call sites use slightly different `confidence`
   inputs (0.61 vs. a marginally different value) despite both being fed from what appears to be
   the same `structural` block. **Not root-caused this session — flagged, not resolved.**
9. **Two different `suppressed_metrics` lists for the same THG row** (noted in
   `TRACE_THG.md` §5, not yet resolved): `fundamental_detail.suppressed_metrics` includes
   `sales_multiple` and excludes `trailing_revenue_growth`; `analysis_v2.applicability.
   suppressed_metrics` does the reverse. Likely explained by the `ALIASES` mapping in
   `scoring_v2.py:72-76` (`revenue_growth → trailing_revenue_growth`) operating on a different
   metric-ID namespace than the legacy path uses, but not confirmed by reading the producing
   code for `fundamental_detail.suppressed_metrics` this session.

### 10.3 Not yet investigated this session (candidates flagged by the internal audit, unverified either way)

The internal audit raised several further items — the enrichment feedback loop (statement-level
metrics only ever fetched for names a prior run already ranked highly), the 17%-of-universe
coverage cliff on `capital_allocation`/`accounting_quality`, cross-metric redundancy within the
market-behavior blend (`relative_strength_20d` vs. `return_20d`), and duplicated/dead guidance
implementations across `advisor_engine.action_for`, `recommendation_policy_v2`, and several
`src/lib/*.js` files. None of these were re-verified against current code this session. Given
how many of the audit's *other* claims turned out to be already fixed, **none of these should be
repeated as current fact without independent re-verification** — they are listed here only as a
follow-up checklist, explicitly not as confirmed findings.

---

## 11. Undetermined

Consolidated from every UNDETERMINED marker above, plus items not yet touched at all:

- Exact current per-modifier point caps for 8 of 9 champion-path modifiers (only the ±15
  combined cap is directly confirmed; §6.5).
- Whether `ranking_weights` (fundamentals 0.78/market_behavior 0.18/news_sentiment 0.04) is
  actually present in `settings.json` or is running on the hardcoded `DEFAULT_RANKING_WEIGHTS`
  fallback (§6.1) — the two are numerically identical in what was observed, so this doesn't
  change any number in this document, but it changes *how* a reader would edit the weight.
- Full TTM/annual/quarterly period-convention audit across all ~29 fundamental metrics (§4.3).
- `CrossSectionalNormalizer`'s internal winsorization/tie-handling logic, beyond what's visible
  in one published example row (§4.4).
- Whether `"replaced"` is ever assigned as an actual metric status anywhere in current code, or
  is dead code alongside `"suppressed"` (§5).
- Whether `business_profiles.json`'s missing `semiconductor`/`other_pre_profit` entries cause
  any visible degradation (§10.2 item 6).
- Root cause of the 74.7 vs. 74.5 `effective_score` discrepancy (§10.2 item 8).
- Root cause of the two different `suppressed_metrics` lists on one row (§10.2 item 9).
- Split/dividend adjustment handling in price history (`fetch_prices.py`, not opened this
  session).
- Everything in §10.3 (audit items not re-verified).
- All of §§1-3, 9, 12 pending the parallel research pass's completion and integration.

---

## 12. Test and validation inventory

### 12.1 Test file inventory

**`pipeline/tests/*.py`** — 108 files, ~1,627 `def test_` functions, unittest/pytest style, run
via `pytest pipeline/tests` in `.github/workflows/ci.yml:30`. Selected files relevant to the
scoring core:

| File | Cases (approx.) | Covers | Kind |
|---|---|---|---|
| `test_scorer.py` | ~38 | Band/range/lower-is-better scoring primitives, category weight sums, sector-relative PE, coverage weighting | Unit (synthetic fixtures) |
| `test_canonical_v2.py` | ~29 | `calculate_peg`, `Observation`, `applicability_for`, `classify_profile`, `reconcile`, `build_v2_analysis`, `peer_groups.py` | Unit |
| `test_advisor_engine.py` | ~55 | Technical factors, sentiment blend, every bounded modifier, deterioration engine | Unit |
| `test_recommendation_policy_v2.py` | ~24 | `effective_score`, `build_recommendation_v2` action-label matrix, confidence gating | Unit, table-driven |
| `test_optimize_weights.py` | ~13 | Dirichlet weight sampling, holdout evaluation plumbing — tests the *search machinery*, not the resulting weights | Unit |
| `test_score_calibration.py` | ~20 | Gate logic, bucket math, `confidence_detail` wiring | Unit |
| `test_ic_harness.py` | ~17 | Append-only snapshot idempotency, ICIR unlock at 24 periods, sector-residual fallback, deflated-Sharpe trial count | Unit |
| `test_baseline_snapshot.py` | 4 | Anchors 5 real rows from a specific `advisor.json` as a regression fixture | Regression/snapshot — **not** outcome validation |
| `test_backtest_monthly.py`, `test_backtest_common.py`, `test_policy_backtest.py` | ~15 | Backtest-*engine* mechanics on synthetic series — not that any live weight beats a benchmark | Unit |
| `test_sec_edgar_contract.py` | ~6 | AST-walks every pipeline module to fail the build on duplicate method definitions | Static/meta-test |
| Remaining ~95 files | — | Screen builders (14 files), provider clients, PIT store, options-strategy backtests, plausibility/enrichment/coverage audits | mostly unit, some contract/integration |

**`tests/functions/*.test.js`** — 3 files, 18 cases, Vitest, covering `netlify/functions/*.mjs`
serverless handlers (mocked Firestore/GitHub API, request/response shape) — not financial-
calculation tests.

**`src/**/*.test.{js,jsx}`** (colocated per-file, not under a single `src/test/` dir) — 59 files,
~478 cases, run by `npm test` → `vitest run`. Covers frontend logic (`recommendation.test.js`,
`rankingModels.test.js`, `factorAnalytics.test.js`, `portfolioAnalytics.test.js`, etc.) — UI-facing
behavior, not independent verification of the Python scoring pipeline's math.

`research/STATE.md:409` records a full-suite checkpoint from an earlier commit than current HEAD:
`pytest pipeline/tests -q # 1595 passed`, `npm test # 508 passed` — close to but not identical to
the counts above; current suite has since grown.

### 12.2 Hand-computed financial-value assertions — hunted specifically

**None of the tests in `test_scorer.py`, `test_canonical_v2.py`, `test_advisor_engine.py`,
`test_recommendation_policy_v2.py` assert a scored value against an independently-sourced,
real-world "known-correct" outcome** (e.g. nothing of the shape "AAPL's ROIC on date X should
equal Y because that is AAPL's real ROIC"). What exists is **arithmetic-correctness testing of
the scoring formulas against hand-picked synthetic inputs** — verifying the code computes what
the formula says, not that the formula predicts anything real. Examples:
- `test_canonical_v2.py:23-24`: `calculate_peg(10, 10, "percentage_points", periods_match=True,
  definition_known=True) == 1.0` — hand-computed, but validates `calculate_peg`'s arithmetic, not
  that PEG=1.0 means anything for future returns.
- `test_scorer.py:56-57`: confirms `lower_is_better_score` returns the configured floor/ceiling
  for out-of-band inputs — a code-behavior check, not an outcome check.
- `test_recommendation_policy_v2.py:52`: `effective_score(90, 0.5) == 70.0` — confirms the
  confidence-shrinkage formula's arithmetic.
- Multiple `assertAlmostEqual(sum(weights.values()), 1.0)` checks confirm weight *configuration*
  sums correctly, not that the weights are empirically justified.

The closest thing to an outcome-linked assertion is `test_baseline_snapshot.py`, which anchors 5
rows of a specific `advisor.json` and asserts confidence stayed ≤0.5 for all of them — a
**regression/drift detector against the pipeline's own prior output** ("diffable against real
published behavior instead of only synthetic fixtures," per its own docstring), not a comparison
to any real subsequent stock-price outcome.

**Conclusion**: no test in the repository asserts a scored/derived financial value against a
known-correct outcome grounded in real market or fundamental data. All value-level assertions
found are formula-arithmetic checks against synthetic or fixture inputs.

### 12.3 `score_calibration.py` and `ic_harness.py` — what they compute, and whether either has ever produced a real result

**`ic_harness.py`** (`pipeline/validation/ic_harness.py`, 627 lines): a prospective full-universe
IC validation harness. `append_refresh` writes one immutable JSONL snapshot per scored ticker per
refresh into `pipeline/pit_store/<date>.jsonl`, idempotent per `refresh_id`. Snapshots group into
monthly observation periods; per period it computes forward return over a real trading-session
horizon and a **sector-residual label** (stock return minus equal-weight sector-peer mean) as the
primary target (a secondary calendar-day/raw-return diagnostic path also exists), Spearman rank
IC, ICIR (mean IC / IC stdev), a 95% CI, decile bucket returns/monotonicity, top-minus-bottom
long/short spread net of modeled trading costs, and a deflated-Sharpe probability using the
`experiment_registry.py`-tracked trial count as a floor. ICIR eligibility gates on
`CONFIG["minimum_icir_periods"] = 24` (`settings.json:77`).

**Has it ever produced a real result? No.** `main()` (`ic_harness.py:599-622`), what
`ci.yml:29` runs on every push/PR, by default only calls `write_report()`/`build_report()` over
whatever is already in `pipeline/pit_store/` — it does **not** pass `--append-current` in CI, so
CI grades the store, it does not grow it. The live `pipeline/pit_store/` directory holds exactly
**6 daily files, dated 2026-08-05 through 2026-08-10** — under one calendar week, nowhere near
the 24 *monthly* periods the ICIR gate requires. `test_ic_harness.py:66` and
`test_score_calibration.py`'s `LiveHarnessTests.test_the_current_harness_supplies_no_closed_
observations` (`:124`) both encode this as expected/tested behavior, not a bug — the test suite
itself asserts the gate is currently and correctly closed.

**`score_calibration.py`** (227 lines): consumes closed `(score, sector_residual_return)`
observations from the IC harness's primary path and buckets them two ways — 5 adaptive
equal-count quantiles and 6 fixed score bands (`FIXED_BANDS = ((80,101),(75,80),(70,75),(65,70),
(60,65),(0,60))`) — reporting per-bucket mean/median residual return, a 95% CI, "beat sector" rate
with a Wald CI, volatility, and a drawdown-of-sorted-outcomes stat, gated on
`MINIMUM_BUCKET_OBSERVATIONS = 30` observations per bucket. Running `main()` today:
`observations_from_harness()` returns an empty list (0 closed periods), so `build_report(rows=[])`
produces `status: "insufficient_data"` for every bucket and `publishable_to_confidence_detail:
False` — matching the live artifact's `historical_calibration: null` (§6.6). **This module has
never produced a populated report against real data**, by construction of what data currently
exists in the repo.

**Direct conclusion**: no IC study, backtest, or calibration check running through the live
pipeline's own harness has ever produced a real, populated result. The gate is real, working
code, correctly reporting its own emptiness — not a fabricated "everything is fine" stub.

### 12.4 `research/` — the actual predictive-validation study, characterized precisely

This is a **separate, offline research program**, not the live `ic_harness`/`score_calibration`
path, built on its own point-in-time fundamentals store reconstructed from raw SEC EDGAR XBRL
filings, independent of the live 6-day `pipeline/pit_store/`. All committed to `main` (27 commits
touch `research/`). It is the closest thing to a real predictive-validation study anywhere in
this repo.

- **Phase 4** (`research/results/PHASE4-BASELINES.md`, `research/baselines.py`): 820 US companies
  (median per rebalance), **2017-01-01 to 2026-06-01**, 164 rebalances (21-session hold),
  point-in-time fundamentals, top-20 and full decile ladders, 10bps/side costs. Equal-weight
  universe: 18.0% CAGR / Sharpe 0.99 (benchmark). `momentum_12_1` and `quality_and_momentum` sort
  cleanly (monotonicity +0.61/+0.81, +0.41/+0.40 Sharpe over universe). `value_earnings_yield`
  **sorts backwards** (monotonicity −0.62, Sharpe 0.79 vs. universe's 0.99, "actively harmful" per
  the doc's own verdict). `profitability` (gross-profits-to-assets) does not sort at all.
- **Phase 5** (`PHASE5-FEATURES.md`, `research/features.py`): all 32 of the live model's
  fundamental inputs, measured **as the model's own band-scored value**, same window. **"None of
  the thirty-two metrics passes a significance bar that accounts for testing thirty-two metrics.
  The largest t-statistic on the table is +2.4 against a Bonferroni threshold of 3.163"** — the
  exact "none of the thirty-two inputs survives multiple-testing correction" finding this task's
  brief references. 43.2% of score weight sits on positive-IC metrics, **44.2% on negative-IC
  metrics**. Four independent valuation multiples (`price_to_book`, `ev_to_ebitda`, `ev_to_ebit`,
  `ev_to_fcf`) all show negative IC and Sharpe-ladder monotonicity between −0.72 and −0.93 — the
  valuation block carries 28% of score weight.
- **Phase 5b** (`PHASE5B-BANDS.md`, `research/bands.py`): tested whether the model's band cutoffs
  destroy signal versus the underlying metrics. 26 of 27 comparable metrics score faithfully;
  band recalibration is explicitly closed off as a remedy.
- **Phase 6** (`PHASE6-COMPOSITE.md`, `research/composite.py`): the **live scorer itself**
  (`scorer._band_valuation_score`, real config), point-in-time, same window, 819 companies/
  rebalance. **"Ranking by the live composite and holding the best-scored decile earned a Sharpe
  of 0.86 against 0.99 for equal-weighting the whole universe. The ladder is inverted... Return
  monotonicity −0.87; Sharpe monotonicity −0.88"** — the exact "the composite ranks backwards"
  finding the brief references. The model's largest-weighted block (valuation, 28%) has the worst
  top-decile Sharpe (0.74); its smallest-weighted block (growth, 11%) has the best (1.13).
  Conclusion, quoted: "the complicated model did not beat holding everything, let alone the
  simple factor combinations in Phase 4, three of which did."
- **Phase 6b** (`PHASE6B-CANDIDATE.md`, `research/candidate.py`): a **pre-registered, split-sample**
  test — 6 candidate rankings selected by design-half (2017-01→2021-07) Sharpe-decile-
  monotonicity, winner chosen before the test half was read, scored on 2021-07→2026-06 out of
  sample. Selected candidate `momentum_only`: 43.5% CAGR / Sharpe 1.38 vs. live composite's
  15.1%/0.79 and universe's 9.8%/0.64 — but the doc itself flags momentum as "the factor most
  inflated by the one bias this pipeline has not fixed" (survivorship) and states explicitly
  "43.5% is not a forward expectation." It also **retracts** an interim recommendation to remove
  the valuation category — better in-sample (design-half Sharpe 1.17 vs. live 1.06) but **worse
  than the model it was fixing on every measure out-of-sample** (test-half Sharpe 0.54 vs. live
  0.79). The full-window "ranks backwards" finding is **not stable when split**: composite Sharpe
  monotonicity was −0.85 in the design half but **+0.04** (flat, not inverted) in the test half.
- **`LIVE-LEADERBOARD-AUDIT.md`** (`research/audit_leaderboard.py`, reads `advisor.json` directly,
  no backtest): the published leaderboard is sorted by **data-enrichment depth, not scoring
  merit** — 100 of the top 100 published rows come from the 16.8% of the universe with full
  statement enrichment; best rank achieved by any non-enriched company is #127; the
  enrichment-priority mechanism (`enrichment_selection.previous_top`) is self-reinforcing (16 of
  the current top 20 were in the prior run's top 20).

Every result file explicitly and repeatedly states the binding limitation is **survivorship
bias** (the candidate universe = companies with a price feed *today*; delisted/acquired/zeroed
names are absent, biasing every return upward by an unquantified amount) and that the window is a
single regime (2017-2026, one of the strongest growth-over-value stretches in decades) —
unresolved as of the last commit touching `research/`.

### 12.5 One unambiguous sentence

**No validation of the live ValueSignal model's predictive performance against real forward
outcomes exists anywhere in the pipeline's own production path** (`ic_harness.py`/
`score_calibration.py` have never accumulated enough point-in-time history to clear their own
gates) **— but a real, methodologically serious offline study does exist in `research/`** (Phases
4-6b, on 2017-2026 point-in-time SEC EDGAR data), **and its central finding is that the live
scoring composite, run on the actual production code and configuration, ranked its own top decile
*worse* than the equal-weighted universe on a risk-adjusted basis** (Sharpe 0.86 vs. 0.99,
Sharpe-monotonicity −0.88) **over the full window studied, with the model's largest-weighted
category (valuation, 28% of score) also its worst-performing one — though a pre-registered
out-of-sample split (Phase 6b) found this specific "ranks backwards" characterization was
concentrated in 2017-2021 and the model's ranking was closer to flat/random (not inverted) in
2021-2026, and every number in the study is qualified by an acknowledged, unquantified
survivorship bias** that its own authors say caps what can be claimed about absolute (not just
relative) performance.

### 12.6 Supplement to §6.6 — weight/threshold provenance, four more constants

| Constant | Location | `git log -S` result | Interpretation |
|---|---|---|---|
| `minimum_icir_periods: 24` | `settings.json:77` | Real origin found: `79ed21b`, "feat: add prospective IC validation harness" — the line was newly added there | No reference to fitting/backtesting in the commit; the number matches "2 years of monthly refreshes," a stated *a priori* design target (`score_calibration.py:9`, `research/STATE.md`), not a fitted one |
| `0.65 + 0.35*coverage` confidence multiplier | `scorer.py:615,652` | Predates the fetch boundary — true origin UNDETERMINED (see shallow-clone note below) | Cannot be traced further |
| `±15` combined-modifier cap | `advisor_engine.py:552` | Same shallow-clone boundary artifact | UNDETERMINED |
| `MINIMUM_BUCKET_OBSERVATIONS = 30` | `score_calibration.py:50` | Same shallow-clone boundary artifact | The file's own docstring gives a stated, non-empirical rationale: "Chosen before looking at any result: roughly the point at which a proportion's 95% interval is narrower than ±15 points" — an a priori statistical-power heuristic |

**Methodological finding, important on its own**: this checkout is a **shallow git clone with
four graft/boundary commits** (`.git/shallow` lists exactly `0e173cf`, `768fa11`, `993f354`,
`cbc38ff`; `git rev-list --max-parents=0 --all` confirms these are the only visible "roots").
Diffing against any of these four shows the entire file freshly added, because their real parents
were never fetched — meaning `git log -S <pattern>` in this checkout can spuriously report one of
these four as the origin of *any* string present in the files they touch, regardless of true
history (confirmed: unrelated feature-commit messages surfaced as apparent hits for scoring
constants during this check). **Any git-archaeology conclusion in this document that terminates
at one of these four hashes should be read as "predates the available history," not as a genuine
finding about that commit's intent** — this includes §6.6's own `ev_to_ebitda: 0.27` search.

No commit message reachable in this shallow history, for any constant investigated across this
document, references fitting, calibration, or backtesting as the basis for a specific numeric
value — consistent with, and extending, §6.6's original conclusion: **no weight in this system
has been fitted to or validated against outcome data.**

### 12.7 Open items / UNDETERMINED for this section

- True git origin of the `0.65 + 0.35×coverage` confidence multiplier, the ±15 combined-modifier
  cap, and `MINIMUM_BUCKET_OBSERVATIONS = 30` — blocked by the shallow clone's graft boundaries;
  would need a full/unshallow fetch of the actual remote history.
- Whether `pipeline/tests`/`npm test` currently pass in full — not re-run this session.
- Whether `ci.yml`'s `ic_harness.py --snapshot` invocation without `--append-current` is
  deliberate (grade-only) or an oversight — accumulation instead appears to depend on
  `refresh-advisor.yml`'s production runs writing to `pipeline/pit_store/` directly, not
  independently re-verified this session.
- Whether `research/`'s Phase 7 (multiple-testing correction) through Phase 11 (deliverables) were
  ever executed — `research/STATE.md:39` states "5-10 not started" as of that checkpoint, no
  `PHASE7`-or-later file exists in `research/results/`.
- Exact current row/refresh count inside `pipeline/pit_store/`'s 6 daily files, beyond the file
  count itself.

---

Independently confirmed and worth repeating here (also stated in §6.6): the live artifact's own
published `data_coverage_detail.limitations` states, for every row, "insufficient prospective
calibration history (requires 24 eligible IC periods)" — the system is, as of this run,
self-reporting that it has not been calibrated. This is not a test-suite finding; it's the
running system's own output, which is stronger evidence than a test result would be, since it
reflects the actual production state rather than a controlled test scenario.
