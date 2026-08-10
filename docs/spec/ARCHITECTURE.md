# ValueSignal — Architecture Specification

**Status: complete draft, all twelve required sections written.** All sections are
independently verified against current code (branch `claude/valuesignal-spec-audit-qf2wni`,
HEAD as of 2026-08-10). `docs/spec/METRIC_REGISTRY.md` (one row per metric, 51 metrics
documented, 43 fully determined) and `docs/spec/registry.json` (machine-readable equivalent,
plus a top-level `weights` object and a `defaults` array of 23 silent-default sites) are
complete companion documents — §6's tables here give the full weight hierarchy narratively;
the registry files give the exhaustive per-metric detail (formula, source, fallback chain,
suppression profile, display label/tooltip) this document does not repeat in full to avoid the
two documents drifting apart. Section 11 (undetermined) remains a living list of what this pass
could not establish — it is deliberately not empty, per the task brief's own instruction that a
thorough undetermined list is a better outcome than false completeness.

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

ValueSignal is a static React single-page application (built by Vite, deployed to Netlify) that
displays a pre-computed research payload. All scoring happens offline, in a Python pipeline run
by scheduled GitHub Actions — the deployed frontend never computes a score; it renders JSON
committed to the repository. This split (compute offline, serve static JSON) means "the system"
is really two independent programs that only communicate through committed files:
`pipeline/*.py` (producer) and `src/**/*.{jsx,js}` (consumer), plus three small Netlify
serverless functions that bridge live, low-latency needs the static JSON can't serve.

**Path from a scheduled run to a rendered number:**

1. GitHub Actions fires `refresh-advisor.yml` on a cron schedule (confirmed in
   `docs/spec/FILE_INVENTORY.md`: `cron: '7 11,12,16,17,19,20 * * 1-5'`, weekdays,
   ET-market-hours-aligned, ~6 runs/day, gated against `America/New_York` so DST doesn't shift
   the effective local time) or on manual `workflow_dispatch`.
2. The workflow runs `pipeline/fetch_advisor.py`'s `run()` function (entry point confirmed at
   line 1313 as of this session — this number has already shifted once during this
   investigation, confirming the file is under active edit; do not trust line numbers from any
   document older than this session). This is the one function that produces
   `public/data/advisor.json` and is described in full in §§2-8 of this document.
3. Downstream builders run in the same job (per `FILE_INVENTORY.md`'s workflow trace): the
   options-strategy screen builders, `run_strategy_backtests.py`, `fetch_etfs.py` /
   `build_etf_comparisons.py` / `fetch_factors.py`, `rescore.py`,
   `build_quality_value_screen.py`, `build_tactical_screens.py`, `shadow_portfolios.py`,
   `validate_data.py`, `stability_report.py`, `evaluate_alerts.py` — then the workflow commits
   the updated `public/data/*.json` files directly to the repository (`contents: write`
   permission, push retries, per `FILE_INVENTORY.md`).
4. Netlify rebuilds and redeploys the static site on every push to the default branch
   (`npm run build` → `vite build`, publishing `dist/`), or serves the previously-built site
   unchanged if only data files (not app code) changed — the published JSON under `public/data/`
   is fetched by the already-deployed frontend at runtime, so a data-only refresh does not
   necessarily require a full site rebuild (exact caching/versioning behavior of this handoff is
   UNDETERMINED — not traced this session).
5. The browser loads the SPA, fetches `public/data/advisor.json` (and siblings) directly, and
   `src/lib/useData.js` / `src/lib/schemaMigrations.js` parse and (if needed) upgrade the row
   shape before any component renders a number.

**Three run parameters that shape every published payload**, confirmed by direct code read:
- `ADVISOR_UNIVERSE_MODE` (`fetch_advisor.py:1337`, default `"full"`): `full` polls all 910
  configured symbols and refits cross-sectional normalization distributions from scratch; `fast`
  polls only the prior run's top 100 + portfolio + a rotating 120-name slice of the stalest
  tail, reusing the prior fit (§3 has the full mechanics).
- `ALPHA_ENRICH_LIMIT` (`fetch_advisor.py:1343`, clamped `max(0, min(5, ...))`, default 5):
  regardless of universe size, only 5 symbols per refresh receive Alpha Vantage enrichment.
- `publish_limit` (40) and `extended_limit` (150), both from `advisor_universe.json`: of the
  ~910-symbol universe, at most 150 receive statement-derived (ROIC, Altman Z, Piotroski, etc.)
  enrichment, and only the top 40 are published to the `research` array the frontend's main
  leaderboard reads from — everything else lands in the lighter `screen_universe` array (§4.1
  and §6 already establish that a `screen_universe` row and a `research` row are not the same
  statistic; this is why).

**The published artifact examined throughout this document**, `public/data/advisor.json`,
carries `generated_at: 2026-08-10T05:23:37Z`, `model_version: 3.2.0`, `schema_version: 6`,
`universe_count: 926` (confirmed by direct query against the committed file — 926 vs. the
universe file's 910 configured symbols reflects portfolio/watchlist additions layered on top of
the base list at run time, consistent with `advisor_universe.json`'s separate
`portfolio_symbols` block). Its provenance fields identify it as a **fast-mode** product:
`data_mode: "live"`, `universe_mode: "fast"`, `polled_count: 247` — so the committed rows were
produced by a refresh that re-polled 247 names, not the full universe — and its `research`
array holds exactly 40 rows, matching `publish_limit`.

**Netlify serverless functions** (`netlify/functions/*.mjs`, confirmed in `FILE_INVENTORY.md`):
`refresh-data.mjs` (admin-authenticated manual refresh trigger, dispatches and polls GitHub
Actions runs), `portfolio-prices.mjs` (Firebase-ID-token-authenticated live/post-market quote
fetch for a user's held symbols), `alert-push.mjs` (Web Push notification delivery for
Firestore-recorded alert events, quiet-hours aware). These are the only three points where the
deployed system does anything beyond serving static JSON.

**Repo layout, by module purpose** (full detail in `docs/spec/FILE_INVENTORY.md`, which covers
every significant file individually — not reproduced here): `pipeline/` (the Python scoring
pipeline and ~20 screen builders), `research/` (backtesting/candidate-signal research code, plus
the prior internal audit discussed in §0), `src/` (the React frontend — `pages`, `components`,
`lib`, `workers`), `netlify/functions/` (the three serverless bridges above), `scripts/`
(evidence/report generation, screenshots, hygiene checks), `.github/workflows/` (the refresh,
backfill, and CI schedules).


---

## 2. Data sources

### 2.1 Provider-by-provider

**Yahoo Finance (yfinance)** — `pipeline/providers.py` (`YahooAdapter`) and `pipeline/fetch_advisor.py`.
- Calls: `yf.Ticker(symbol).info`, `.history()`, statement frames (`extended_inputs`), option
  chains — `fetch_advisor.py:417-431` (quote snapshot), `:501-543` (`yahoo_extended`,
  statement-derived metrics), `:546-576` (options IV, opt-in via `ENABLE_OPTIONS_VOLATILITY`).
- Auth: none (no key required).
- Rate limit as implemented: `DEFAULT_RATE_LIMITS["yahoo"] = 240`/min — a **self-declared
  guess**, not a documented Yahoo limit; `cache.py:39-43`'s comment states this explicitly
  ("Yahoo publishes no rate limit ... this is our own conservative guess"). Enforced via
  `limiter_for("yahoo")` at `fetch_advisor.py:452`, `providers.py:175/208/253`,
  `yahoo_news.py:185`.
- Cache: namespaces `price_history` (TTL 6h), `quote` (TTL 900s), `statements` (TTL 7 days) —
  `cache.py:53-55`.
- Retry: `retry_with_backoff` (`cache.py:347-362`) — 4 attempts, delay `2**attempt` seconds
  (2/4/8/16s). Used for batch `yf.download` (`fetch_advisor.py:400-403`) and elsewhere.
- On failure: per-symbol try/except swallows the error, logs a warning, serves a stale cache
  entry if one exists (`DiskCache.fetch`, `allow_stale_on_error=True` by default,
  `cache.py:225-245`), or leaves that field unenriched. `.info` failure and statement-frame
  failure are caught **separately** (`fetch_advisor.py:501-528`) so one broken call doesn't
  blank the other. A symbol is dropped from the run only if it has fewer than 21 price sessions
  or no name (`fetch_advisor.py:1036-1037`, caught per-symbol at `:1399-1401`).
- Point-in-time: **no** — Yahoo/yfinance serves only as-of-today restated data, which is exactly
  why the separate PIT store layer exists (below).

**Alpha Vantage** — `pipeline/alpha_vantage.py` (`AlphaVantageClient`).
- Functions called from `fetch_advisor.py`: `OVERVIEW` (`:990`), `TIME_SERIES_DAILY` (`:992`,
  plus SPY benchmark at `:1372-1375`), `NEWS_SENTIMENT` (`:1010`, only when Marketaux is
  unavailable/failed), `INSIDER_TRANSACTIONS` (`:1014`).
- Auth: `ALPHA_VANTAGE_API_KEY` from `.env.local` (`alpha_vantage.py:21-38`).
- Coverage capped at `min(5, ALPHA_ENRICH_LIMIT)` symbols per run (`fetch_advisor.py:1343,
  1348`) — 905 of 910 universe symbols never touch Alpha Vantage at all.
- Rate limit: does **not** use `cache.py`'s token-bucket machinery. Paces itself with a
  hardcoded `min_interval=1.1`s between requests (`alpha_vantage.py:36,42,60-62`).
  `DEFAULT_RATE_LIMITS["alpha_vantage"] = 5`/min (`cache.py:34`) is **dead configuration for
  this call path** — a separate, unused `AlphaVantageAdapter` class in `providers.py:291-323`
  does call `limiter_for`, but nothing imports it; `fetch_advisor.py` imports
  `AlphaVantageClient` from `alpha_vantage.py` instead. Flagged as a new finding in §10.
- Cache: own file cache under `pipeline/cache/alpha_vantage/`, default `cache_hours=20`.
- Retry: **none** — a single `requests.get`; any error status or an `Error Message`/`Note`/
  `Information` field in the payload raises immediately (`alpha_vantage.py:63-76`).
- On failure: caught in `fetch_optional()` (`fetch_advisor.py:945-950`), logged, returns `{}` —
  silent, not loud. `merge_snapshots()` falls through to Yahoo for every field.
- Point-in-time: no.

**Marketaux** — `pipeline/marketaux.py`.
- Endpoint `https://api.marketaux.com/v1/news/all` (`marketaux.py:19`), called per-symbol
  (`fetch_advisor.py:1001-1004`) and for broader discovery news (`:695-699`).
- Auth: `MARKETAUX_API_TOKEN`.
- Rate limit: `DEFAULT_RATE_LIMITS["marketaux"] = 60`/min exists (`cache.py:46`) but, like Alpha
  Vantage, is **never invoked** — no `limiter_for` call anywhere in `marketaux.py`.
- Cache: own file cache, `cache_hours=4` default.
- Retry: none — a non-200 or malformed payload raises immediately.
- On failure: caught at `fetch_advisor.py:1006-1008`, symbol falls back to Alpha Vantage news
  (if alpha-enriched) or runs on Yahoo's own per-symbol news, which is fetched unconditionally
  regardless of Marketaux state (`:985-986`). If `MARKETAUX_API_TOKEN` is unset, the client is
  `None` for the whole run.
- Point-in-time: no.

**FRED** — `pipeline/fred.py`.
- Endpoint `https://api.stlouisfed.org/fred/series/observations`, six series (`treasury_10y,
  fed_funds, cpi, unemployment, yield_curve, sahm`) — `fred.py:14,18-25`.
- Auth: `FRED_API_KEY`.
- Rate limit: `DEFAULT_RATE_LIMITS["fred"] = 120`/min defined (`cache.py:45`) but **never
  enforced** — `fred.py` never calls `limiter_for`.
- Cache: **none at all**. The module docstring states explicitly "raw observations are held in
  memory only" (`fred.py:3`) — every refresh re-fetches all 6 series live.
- Retry: none.
- On failure: `fetch_regime()` tolerates up to 4 of 6 series failing (`fred.py:167-178`); a
  total failure sets the whole macro-regime block to `None` rather than fabricating a value —
  confirmed the run continues either way.
- Point-in-time: no — current-value-only, and explicitly not persisted.

**SEC EDGAR** — `pipeline/sec_edgar.py`.
- Endpoints: Form 4 ownership XML (`recent_form4_filings`/`form4_transactions`, called at
  `fetch_advisor.py:754`); `ticker_map()` from SEC's `company_tickers.json`
  (`sec_edgar.py:222-239`); submissions JSON; XBRL `company_facts`/`company_concept`/`frames`
  (used by `theme_signals.py`); full-text search. 13F-HR retrieval happens in a **separate
  monthly job** (`build_institutional_screen.py`), not live inside the advisor refresh.
- Auth: no API key, but requires `SEC_USER_AGENT` (a real contact string) per SEC fair-access
  policy — without it, the insider and theme layers report themselves unavailable rather than
  spoof a client (`sec_edgar.py:1-6,154-155,169-171,186-187`).
- Rate limit: `540`/min (9/s, deliberately under SEC's published 10/s) — `cache.py:35-38`,
  **actually enforced** via a real shared token bucket (`sec_edgar.py:173-177,191`) — the one
  provider besides Yahoo where the configured limit is genuinely wired in.
- Cache: `sec_submissions` TTL 24h, `sec_document` TTL 30 days ("a filed document never
  changes"), `sec_xbrl` TTL 24h.
- Retry: a dedicated 5-attempt exponential backoff specifically on `403/429/500/502/503/504`
  (`sec_edgar.py:182-215`), separate from `cache.py`'s generic retry helper.
- On failure: per-symbol exceptions caught, added to a `failures` list; diagnostics distinguish
  "no filings" from "unreadable filings."
- Point-in-time: **the one genuinely point-in-time source in this pipeline.** EDGAR facts are
  as-filed and immutable once filed. `pipeline/pit_fundamentals_store.py`,
  `pipeline/pit_shares.py`, `pipeline/pit_market.py`, `pipeline/pit_store.py` build a
  deduplicated point-in-time capture layer on top of it. Every other provider (Yahoo, Alpha
  Vantage, Marketaux, FRED) is as-of-today-only.

**Congress / FMP / Senate eFD** — `pipeline/congress_trades.py`, run by a **separate weekly
job** (`build_congress_screen.py`), not called live from `fetch_advisor.py`, which only reads
the already-published `public/data/screens/congress-trades.json` at read time
(`fetch_advisor.py:902-925`, docstring: "No live FMP calls here"). Three source clients, per the
module's own docstring none alone dependable: `CongressTradesClient` (FMP, key `FMP_API_KEY`,
**not present in `.env.example`**), `SenateEfdClient` (keyless), `StockWatcherClient` (its own
docstring states this mirror **currently returns HTTP 403 on every request** — confirmed dead).
Live artifact check: `congress-trades.json` currently shows `status: "partial"`, 1,162 rows —
the job runs but incompletely, consistent with one of its three sources being dead.

**Institutional ownership (13F) + OpenFIGI** — `pipeline/institutional_ownership.py` +
`pipeline/openfigi_client.py`, run by a separate monthly job. `fetch_advisor.py:852-899` reads
the published `institutional-13f.json` at read time and applies filing-lag decay — no live
SEC/OpenFIGI calls inside the advisor refresh itself. OpenFIGI auth (`OPENFIGI_API_KEY`) is
optional; unset falls to an anonymous tier capped at 10 jobs/request vs. 100 keyed (**not in
`.env.example`**). Live artifact check (`institutional-13f.json`): `status: "success"`,
`openfigi_tier: "anonymous"`, `cusips_seen: 3489`, `cusips_mapped: 278`, but **`results: []` —
zero published rows**, because only 4 of 9 configured 13F managers resolved a filer CIK at all,
and the corroboration gate (`min_managers: 2`, `institutional_ownership.py:49`) is never
cleared. Confirmed: `institutional_ownership` is `None` for all 40 published rows in the current
artifact. A stale in-code comment (`fetch_advisor.py:1901-1904`, "has never run against the live
OpenFIGI endpoint or live 13F filings") is itself now inaccurate — the pipeline does run against
both live endpoints, it just produces zero usable corroborated output. **Flagged as a defect in
its own right in §10: a diagnostic comment that no longer describes the code's actual behavior.**

**Marketstack** — separate scheduled job (`.github/workflows/marketstack-premarket.yml`), not
called from `fetch_advisor.py`. Auth `MARKETSTACK_API_KEY` (**not in `.env.example`**). Batches
up to 100 symbols/request, twice daily, to stay under a 100-calls/month plan. Data appended
point-in-time under `pipeline/data/marketstack/`, never overwritten.

**RSS feeds** — `pipeline/fetch_news.py`, a keyless fallback using `feedparser` against named
feeds, used when Marketaux is unavailable.

### 2.2 Field-level provenance table

| Field | Primary source | Fallback chain | On total failure |
|---|---|---|---|
| `price` | Alpha Vantage OVERVIEW-derived close (5 enriched symbols only), `fetch_advisor.py:613,619` | Yahoo `fetch_snapshot` via `merge_snapshots` (`:633-646,1022`) for all symbols | `None` — no numeric default substituted anywhere in this path |
| `forward_pe` | Alpha Vantage `ForwardPE` (5 symbols) | Yahoo `.info`-derived fallback via `merge_snapshots` | `None` |
| `return_on_equity` | Alpha Vantage `ReturnOnEquityTTM` | Yahoo fallback; statement-derived ROIC (distinct metric) computed separately for the top-150 enriched subset | `None` |
| `days_sales_outstanding` | `fundamentals_extended.derive_extended`, statement-derived, top-150 (`EXTENDED_LIMIT`) subset only | none — statement-only | `None` (absent entirely outside the shortlist) |
| `short_percent_of_float` | Yahoo `.info.shortPercentOfFloat` via `derive_extended`, top-150 subset only | none | `None` |
| `analyst_rating` | Yahoo `.info.recommendationMean` via `derive_extended`, top-150 subset only | none | `None` |
| `institutional_ownership` | `public/data/screens/institutional-13f.json` (monthly job) | none | `None` — verified 0 of 40 published rows non-null currently |
| `congressional_activity` | `public/data/screens/congress-trades.json` (weekly job) | none | `None` — verified 1 of 40 published rows non-null currently |
| `insider_activity` | Live SEC EDGAR Form 4, shortlist sized by `SEC_FORM4_LIMIT` | none | symbol absent from `signals`, added to a `failures` list |
| news sentiment | Marketaux, merged ahead of Yahoo's unconditional per-symbol news | Alpha Vantage `NEWS_SENTIMENT` if Marketaux absent/failed and alpha-enriched → Yahoo-only baseline otherwise | never fully `None` — Yahoo per-symbol news always runs |
| macro regime inputs | FRED, 6 series | none (an unused Alpha Vantage `macro_context()` helper exists but is not called from `main()`) | whole `fred_regime` block `None` if fewer than 2 of 6 series resolve |
| `valuation_percentile`/`peer_context` | `peer_groups.canonical_percentiles` | n/a | explicit `None` with `invalid_reason`, never a fabricated tier |
| `market_cap` | Alpha Vantage (5 symbols) | Yahoo fallback | `None`; also subject to a cross-source plausibility check (`fetch_advisor.py:1026-1035`) that can drop an implausible value entirely |

Cross-provider disagreement handling: `screen_plausibility()` (`fetch_advisor.py:1026-1035`)
explicitly compares Alpha Vantage vs. Yahoo readings for `market_cap`/`price` and can drop a
field as implausible rather than silently keeping whichever provider answered first.

**Summary of point-in-time status**: of every provider in this pipeline, only SEC EDGAR is
genuinely point-in-time (as-filed, immutable, captured into an append-only store). Yahoo, Alpha
Vantage, Marketaux, and FRED all serve current/restated-only data with no historical capture at
the provider layer — any point-in-time reconstruction for those sources depends entirely on
`pipeline/pit_store.py` and siblings having captured a prior run's observation, not on the
provider itself.

---

## 3. Universe construction

`pipeline/config/advisor_universe.json` — loaded directly and confirmed: top-level keys
`description`, `publish_limit` (**40**), `extended_limit` (**150**), `portfolio_symbols` (21
tickers), `symbols` (**910 tickers**, a flat array of ticker strings — no CIK or exchange
qualifier attached in this file).

**Static, not generated.** No code in `pipeline/*.py` builds this file programmatically at
runtime; `fetch_advisor.py:55-57` simply loads it via `load_json(...)`.

**Inclusion/exclusion criteria**: the file's own `description` field states a rationale in
prose — a "diversified liquid US large- and mid-cap candidate universe," with breadth justified
by the argument that a signal's information ratio scales with the square root of the number of
independent bets. This is a **documented design rationale, not an enforced code-level filter** —
no market-cap floor, liquidity screen, or sector cap was found applied against this list at
runtime. What does exist is regression/consistency testing on the curated list itself:
`pipeline/tests/test_universe_config.py` — `test_symbols_are_unique_and_well_formed`,
`test_breadth_is_wide_enough_for_cross_sectional_ranking`,
`test_the_statement_shortlist_stays_well_under_the_universe`,
`test_configured_holdings_are_inside_the_scored_universe`. These check shape and internal
consistency, not membership criteria.

**Ticker-to-entity resolution**: tickers map to CIKs only at lookup time, via
`SecEdgarClient.ticker_map()`, which builds `{ticker.upper(): cik.zfill(10)}` from SEC's own
`company_tickers.json` (`sec_edgar.py:232-239`). There is no exchange qualifier anywhere in the
configuration — a bare ticker string is the only identifier the universe file carries, and CIK
resolution is a live/cached lookup layered on top, never a stored mapping in
`advisor_universe.json` itself. This means cross-listing or ticker-reuse ambiguity is inherently
unresolvable from the universe file alone.

**Change history**: `git log --oneline -- pipeline/config/advisor_universe.json` returns exactly
one commit visible in this clone. **This repository is a shallow clone** (confirmed:
`git rev-parse --is-shallow-repository` → `true`, 136 total commits visible) — this does not
prove the universe has only changed once historically, only that a single change is visible in
the truncated history available to this session. Whether the universe has changed prior to this
clone's history horizon is **UNDETERMINED**, not "no."

**`ADVISOR_UNIVERSE_MODE`** (`fetch_advisor.py:1337-1370`, re-read fresh — line numbers have
shifted since earlier in this session, confirming the file is still under active edit):
- `os.getenv("ADVISOR_UNIVERSE_MODE", "full")` — default **`full`**.
- `full`: all 910 configured (or `ADVISOR_SYMBOLS`-overridden) symbols are polled.
- `fast`: restricted to the union of (a) the prior run's top `ADVISOR_FAST_UNIVERSE_SIZE`
  (default 100) ranked symbols, (b) current `portfolio_symbols`, and (c) an
  `ADVISOR_FAST_ROTATION_SIZE` (default 120) slice of the stalest tail names — sized, per an
  in-code comment, so the full ~900-name universe cycles through roughly every seven fast
  refreshes. Symbols left out of a fast refresh are **not dropped** — they carry forward their
  last full-refresh row.
- `publish_limit` (40) and `extended_limit` (150) are independent of universe mode — they gate
  how many symbols get statement enrichment or make the published leaderboard, not how many get
  quote-polled.

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
  `scorer.py:CrossSectionalNormalizer` (class at line 307, **now read in full**). Verified
  mechanics:
  - **Winsorization**: each metric's full-universe distribution is clipped at the 1st/99th
    percentiles (`winsor_lower_percentile: 0.01` / `winsor_upper_percentile: 0.99`,
    config-overridable via `settings.challengers.cross_sectional_normalization`); the
    universe-derived bounds are then applied to every *sector* sub-distribution too, so a
    sector's tails are clipped at universe levels, not sector levels (`_fit`, the shared
    `winsor()` closure over `lower_bound`/`upper_bound`).
  - **Sector-vs-universe selection**: per metric, per row — the sector distribution is used
    iff it holds ≥ `sector_minimum_count` (default 8) eligible observations, else the
    universe distribution (`score()`, the `len(sector_values) >= self.sector_minimum`
    branch). This is what THG's published block shows: `forward_pe` scored against 123
    sector peers, `price_to_book` against 693 universe values.
  - **Tie handling**: average-rank percentile via `bisect_left`/`bisect_right` —
    `percentile = 100 × (left + right − 1)/2 / (n − 1)`; a single-value distribution scores
    50.0.
  - **Direction**: `lower_is_better` metrics and range metrics flip (`100 − percentile`);
    range metrics are first transformed to distance-from-configured-ideal
    (`_range_distance`). Non-positive valuation multiples are excluded from the fit and
    scored `not_applicable_nonpositive` rather than ranked.
  - **Fast-mode reproducibility**: `from_published()` restores the exact prior full-refresh
    fit from the published `normalization_distributions` block, which is how a fast-mode
    refresh (like the committed artifact) reuses the prior fit rather than refitting on a
    partial poll.
  - **Own-history percentile**: valuation multiples only, requires ≥12 observations
    (`own_history_minimum_observations`) over a 5-year window before publishing a value;
    below that it publishes `own_history_status: "accumulating"` with the observation count
    — exactly THG's published state (3 observations, accumulating).
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
- `"replaced"`: **resolved this session — a real, assignable status that happens to be
  invisible in the current artifact.** The matrix declares it for exactly two rules
  (`utility.free_cash_flow_yield` and `commodity_producer.peg` — confirmed by enumerating
  every rule tuple's status in `applicability_matrix.json`), and `applicability_for` passes a
  rule's status through verbatim (`canonical_metrics.py:146`), so those two metric/profile
  pairs would publish `status: "replaced"`. It does not appear in the current artifact for two
  verified reasons: (a) all 10 published `commodity_producer` rows have their `peg` status
  **overwritten** to `"suppressed"` by the canonical-PEG special case
  (`scoring_v2.py:119-121`, which fires whenever `calculate_peg` rejects the provider PEG —
  true for every one of the 10, each carrying the `provider_peg_rejected` quality flag,
  confirmed by artifact query), and (b) no `utility`-profile row is in this run's published 40
  (profile census of the artifact: 15 general, 10 commodity_producer, 4 P&C, 3 diversified
  insurer, 3 bank, 2 life insurer, 2 profitable biotech, 1 semiconductor). Behaviorally,
  `"replaced"` and `"suppressed"` are identical everywhere they are consumed — both
  membership tests (`canonical_metrics.py:169`, `scoring_v2.py:127`) treat them as one set —
  so the distinction is purely descriptive, and finding 5 (§10.2) applies to it in full: the
  named replacement inherits no weight either way.
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
dropped back to the hardcoded default rather than raising. **Resolved this session:
`settings.json` does contain a top-level `ranking_weights` block** with `fundamentals: 0.78,
market_behavior: 0.18, news_sentiment: 0.04` (read directly), numerically identical to
`DEFAULT_RANKING_WEIGHTS` — so the config file is the operative source, the code default is a
live-but-redundant fallback, and an editor of these weights should edit `settings.json`. The
config block also carries a `_comment` giving the stated rationale for the 4% news weight
("headline alpha decays within days (Tetlock 2007)") — like §6.4's momentum comment, a design
rationale in prose, not a citation to a validation result on this system's own data.

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
metric's effective composite weight, source, fallback chain, and suppression profile is in
`docs/spec/METRIC_REGISTRY.md` (human-readable) and `docs/spec/registry.json`
(machine-readable) — not reproduced in full here to avoid duplication and drift between the
documents. Both confirm the true fundamentals metric count is **32**, not the "~33" this task's
brief approximated.

### 6.4 Market behavior: sub-weights — and a structural correction found late in this pass

`advisor_engine.py:53-59` (`DEFAULT_TECHNICAL_WEIGHTS`, overridden by
`settings.json.market_behavior.weights`, confirmed present and numerically identical to the
defaults):

| Sub-metric | Configured weight |
|---|---|
| momentum_12_1 | 0.30 |
| risk_adjusted | 0.26 |
| relative_strength | 0.16 |
| drawdown_resilience | 0.14 |
| volume_confirmation | 0.08 |
| low_beta | 0.06 |
| technical_extended | 0.06 |

These sum to **1.06**, not 1.0 — confirmed by direct computation against `settings.json`. This
is mathematically inert on its own: `technical_score_from_parts` (`advisor_engine.py:207-234`)
always divides by `sum(weight for _, weight in answered)` (line 232), not by a fixed constant,
so the *ratios* between sub-metrics are unaffected by the table not summing to 1. It is worth
recording precisely rather than silently correcting, since a reader computing "effective
composite weight" by hand from the raw table (as this document did in an earlier draft) would
get a number about 6% too high for every sub-metric unless they either renormalize by 1.06 or
account for the second effect below.

**The champion path currently runs with `relative_strength` structurally removed, not merely
occasionally missing.** `settings.json`'s top-level (not `market_behavior`-nested)
`short_horizon_treatment` key is set to `"neutral"` (confirmed by direct read). The champion's
one and only call to `technical_factors` (`advisor_engine.py:1099`, inside `build_research`)
passes no explicit `short_horizon_treatment`, so it resolves via `treatment =
short_horizon_treatment or SETTINGS.get("short_horizon_treatment", "legacy_momentum")`
(`advisor_engine.py:182-184`) to `"neutral"`. Inside `technical_score_from_parts`
(`advisor_engine.py:207-234`), the `"neutral"` branch does `weights.pop("relative_strength",
None)` (line 219) — **`relative_strength` is entirely removed from the weight table before the
weighted average is computed, for every row the champion scores**, not renormalized-away only
when its value happens to be missing. The other six sub-weights are renormalized over their own
sum (0.30+0.26+0.14+0.08+0.06+0.06 = 0.90):

| Sub-metric | Configured weight | **Actual effective weight within market_behavior (champion, current config)** |
|---|---|---|
| momentum_12_1 | 0.30 | 0.30/0.90 = **0.333** |
| risk_adjusted | 0.26 | 0.26/0.90 = **0.289** |
| relative_strength | 0.16 | **0 — structurally excluded, not merely reweighted on absence** |
| drawdown_resilience | 0.14 | 0.14/0.90 = **0.156** |
| volume_confirmation | 0.08 | 0.08/0.90 = **0.089** |
| low_beta | 0.06 | 0.06/0.90 = **0.067** |
| technical_extended | 0.06 | 0.06/0.90 = **0.067** |

Effective composite weight of `momentum_12_1` under current config is therefore `0.18 × 0.333 ≈
0.060`, not the `0.18 × 0.30 = 0.054` a reader would compute from the raw table alone.

**This appears to be a deliberate, already-shipped fix for exactly the redundancy the internal
(stale) audit's §6 flagged** — that `relative_strength_20d` is rank-identical to `return_20d`
by construction (`relative = ret_20 - bench_ret`, where `bench_ret` is the same scalar for every
row, so subtracting it cannot change a cross-sectional ranking) and was, in that audit's
snapshot, drawing 16% of the market-behavior weight for zero incremental ranking information.
`technical_score_from_parts`'s docstring (lines 208-213) documents all three treatments
(`legacy_momentum` keeps it, `neutral` removes it, `reversal` flips its sign to `100 -
legacy_score` under a separately configured weight) as a deliberate design surface, and the
`"neutral"` treatment is what current config actually runs. **I did not find this fix
called out anywhere else in this document's earlier drafts or in the internal audit's own status
table (§0)** — it is not one of the four/five commit-tagged fixes already discussed, but the
live config value achieves the same practical effect (zero weight on the redundant metric) via a
different mechanism (a global treatment switch rather than deleting the metric or its weight
entry). Confirmed present in the live artifact: THG's `score_variants.short_horizon` challenger
variant explicitly declares `"short_horizon_treatment": "reversal"` as a distinct alternative
being tested — meaning the champion score and this named challenger differ specifically on this
one axis, which is exactly what a champion/challenger comparison is for.

A module comment (`advisor_engine.py:45-52`) explicitly argues `technical_extended`'s small
weight is deliberate given "the literature behind adding many technical indicators mostly shows
data-snooping" — the closest thing to a stated methodological justification for a specific
weight value found anywhere in this codebase. It is a design-rationale comment, not a citation
to an external validation result.

A module comment (`advisor_engine.py:45-52`, attached directly to this weight table) explicitly
argues `technical_extended`'s small weight is deliberate given "the literature behind adding
many technical indicators mostly shows data-snooping" — this is the closest thing to a stated
methodological justification for a specific weight value found anywhere in this codebase this
session. It is a comment, not a citation to an external validation result; treated here as a
design rationale, not evidence of fitting.

### 6.5 Bounded post-blend modifiers

`pipeline/advisor_engine.py:apply_modifiers` (lines 515-557), champion path. **Every
per-modifier bound below is now verified by direct read of the modifier function's body**, and
every cap value was cross-checked against `settings.json`'s `modifiers` block (read directly),
which declares the identical numbers — so config and code defaults agree, and config
(`MODIFIERS = SETTINGS.get("modifiers", {})`, `advisor_engine.py:43`) is the operative source:

| Modifier | Range (points) | Shape | Source function (all in `advisor_engine.py`) |
|---|---|---|---|
| sector_valuation | −3 / 0 / +3 | discrete three-way: full cap for cheapest peer tier, full penalty for most expensive, nothing for middle or for `None` (no tier below 30 peers) | `sector_percentile_modifier` (465-486) |
| short_interest | [−6, 0] | penalty-only: −6 at ≥15% of float, −3 at ≥8%, +1.5 added (still clamped to −6) at ≥5 days-to-cover | `short_interest_modifier` (254-278) |
| liquidity | [−3, 0] | penalty-only: −3 below $5M average daily dollar volume, −1.5 below $25M | `liquidity_modifier` (428-438) |
| expectations | [−3, +3] | ±half-cap each from analyst target upside (≥+20% / ≤−5%) and consensus rating (≤2.0 / ≥3.5), requires ≥3 analysts | `expectations_modifier` (441-462) |
| macro_regime | [−3, +3] | continuous, sector-weighted FRED factor blend scaled to the cap, dead-zoned below 0.25 points, requires macro coverage ≥0.7 | `macro_regime_modifier` (489-512) |
| insider_activity | [−3, +5] | asymmetric two-sided clamp of `insider_signal`'s score | `insider_modifier` (281-305) |
| institutional_13f | [−2, +3] | asymmetric two-sided clamp of the decayed 13F breadth score (decay applied upstream; `max_age_days: 135` in config) | `institutional_ownership_modifier` (308-334) |
| congressional_buying | [0, +4] | reward-only clamp | `congressional_buying_modifier` (337-357) |
| customer_concentration_risk | [−3, 0] | penalty-only clamp; `measured: False` rows scored nothing rather than credited | `concentration_risk_modifier` (360-393) |

**Combined cap, confirmed by direct read**: `total = round(max(-15.0, min(15.0,
uncapped_total)), 2)` (`advisor_engine.py:552`) — a hard ±15-point cap on the summed modifiers,
confirmed as a literal in the function body, not a config value. (The theoretical pre-cap sum
of the individual bounds is [−23, +16], so the ±15 combined cap can actually bind on the
penalty side.) `geographic_concentration` remains challenger-only ([−2, 0],
`geographic_concentration_modifier`, lines 396-425; applied in `apply_challenger_modifiers`
starting at line 560), per that function's docstring, for a stated correctness reason
(geography-tagged revenue often reflects shipping/contracting entity rather than end demand)
rather than a coverage reason.

A separate challenger variant (`score_variants.modifier_recalibration`, confirmed present in
THG's live row) uses a **different combined cap of 20.0** and allocates each modifier a
*fraction* of that cap (`fractions` object in `SAMPLE_OUTPUT.json`, e.g. `short_interest_penalty:
0.3` of the 20-point cap = 6 points max) — this is a distinct, non-champion scoring path; do not
conflate its ±20 cap with the champion's ±15 cap.

### 6.5b A fourth, independent weighting scheme feeding the frontend "thesis" gauge

`src/lib/bullBearScore.js` (read in full): computes a "bull/bear thesis" score from its own
hardcoded weight table — `FACTORS = [['Fundamentals', 0.4, ...], ['Price behavior', 0.3, ...],
['News sentiment', 0.2, ...], ['Risk quality', 0.1, ...]]` (lines 1-17) — **40/30/20/10**,
reading `stock.components.fundamentals`, `.market_behavior`, `.news_sentiment`, and
`stock.technical_detail.risk_adjusted` respectively. This is a **fourth weighting scheme**
alongside the champion's `ranking_weights` (78/18/4), the shadow structural category weights
(§6.2), and the shadow timeliness weights (§4, `scoring_v2.py`) — all four operate on
overlapping or identical underlying inputs (`components.fundamentals`/`market_behavior`/
`news_sentiment` specifically) but assign them materially different relative importance. This
`thesis` score in turn feeds directly into `watchlistGuidance.js`'s Setup Quality geometric mean
(§9.2) at a further 0.30 weight. **A single published `components` object is reweighted at
least twice more downstream of the backend, by two different and undocumented-as-related
schemes, before a user sees a final "Setup Quality" number.** No cross-reference or shared
config was found linking `bullBearScore.js`'s 40/30/20/10 to any other weight table in this
system — it appears to be an independent design decision made directly in the frontend.

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

**Schemas present**: `pipeline/schemas/` contains `advisor.schema.json` (930 lines — top-level
`$schema`, `type`, `required`, `properties`, `additionalProperties`, `$defs`), plus
`etfs.schema.json`, `news.schema.json`, `picks.schema.json`, `politicians.schema.json`,
`prices.schema.json`, `recommendation-v5.schema.json`, `signals.schema.json`,
`status.schema.json`, `trades.schema.json`. Full field-by-field schema walkthrough not exhaustively
reproduced here — see `docs/spec/METRIC_REGISTRY.md` and `docs/spec/SAMPLE_OUTPUT.json`'s
key-by-key annotation (below) for the fields that matter for scoring; the schema file itself is
the authoritative full contract for anyone validating a payload mechanically.

`pipeline/config/research_contract.json`: top-level keys `_comment`, `contract_version
("1.0.0")`, `universe`, `forecast_targets`, `execution_assumptions`,
`champion_challenger_governance`. Notably, `forecast_targets.primary` **self-declares**
`implementation_status: "not_implemented"` for its 63-trading-day forward sector-residual return
target, and points to `pipeline/validation/ic_harness.py` as scoring a related-but-not-identical
raw-return diagnostic today. This is an honest, self-reported gap rather than a false claim of a
working target.

### 9.1 The peer-percentile sentence, traced end to end (current code)

1. `pipeline/peer_groups.py:99-126` (`canonical_percentiles`) — confirmed no continuous
   percentage is ever computed or exposed. `MINIMUM_VALID_PEERS = 30` (line 36); tiers only
   (`cheapest_third`/`middle_third`/`most_expensive_third`); tie-averaged rank fractions
   (lines 79-96) so tied names always land in the same tier; an explicit `None` with
   `invalid_reason: "insufficient_valid_peers"` when a group is too thin (lines 117-120). The
   `_metadata()` function has no `value`/`display_value` key by design (comment at lines
   137-139). THG's live row: `peer_context: null` (7 valid peers, below the 30 minimum).
2. **Frontend rendering** — `src/components/StockDetailModal.jsx:253-259`:
   ```jsx
   {percentile?.peer_context
     ? <p className="stock-peer-context" title={...}>
         Valuation score {percentile.peer_context.tier_phrase} {percentile.peer_group_label}
         ({percentile.peer_context.tier_count} of {percentile.peer_context.peer_count_with_valid_data} names).
         Ranks this model's valuation composite, not a price multiple.
       </p>
     : percentile && <p className="stock-peer-context">
         No peer comparison published: {percentile.peer_count_with_valid_data} valid
         {percentile.peer_group_label} peers, below the {percentile.minimum_peer_count} needed to rank against.
       </p>}
   ```
   A code comment directly above (lines 248-252) documents the old defect being replaced
   verbatim: *"The old sentence read 'Cheaper than approximately 85% of Property & casualty
   insurers, based on 14 valid peers'... Groups under the minimum publish nothing at all now."*
   **There is no remaining "cheaper than X%" sentence anywhere in `src/`** — confirmed by
   grepping `peer_context|tier_phrase|valuation_percentile|cheapest_third` across the whole
   `src/` tree; every hit is tier-phrase language or a plain `tier`/`ordinal` consumer
   (`src/lib/watchlistPriceTargets.js`, `src/lib/modeConfidence.js`,
   `src/lib/valueGrowthScore.js`, `src/lib/rankingModels.js`), none of which render a percentage
   to the user. Regression tests exist specifically to prevent recurrence:
   `pipeline/tests/test_peer_claims_regression.py::test_no_row_anywhere_publishes_a_continuous_percentile`,
   `::test_every_published_tier_is_backed_by_a_sufficient_sample`,
   `::test_tied_valuation_scores_never_land_in_different_tiers`.

### 9.2 Setup Quality — `src/lib/watchlistGuidance.js` (full file read)

A **weighted geometric mean**: `weightedGeometricMean` computes `G = exp(Σ wᵢ·ln(sᵢ) / Σ wᵢ)`
and returns `0` outright if any weighted subscore is `≤ 0` — the file's own comment states this
is deliberate, "a zero subscore makes the geometric mean zero, so published Sell stays
decisive." Four subscores feed it: `thesis` (from `bullBearScore`, sigmoid-transformed),
`research` (the raw model `score`, sigmoid-transformed), `coverage` (sigmoid-transformed
**`data_coverage`** — confirmed the current, renamed field: `const dataCoverage =
finite(stock.data_coverage) ? stock.data_coverage : null`, `watchlistGuidance.js:76` — no
reference to a stale `confidence` field anywhere in this file), and `guidance` (a lookup table
keyed on the recommendation action). A hard block independently forces `Avoid` and zero
allocation when `dataCoverage < config.hard_coverage_floor` or the action is `SELL`, regardless
of what the geometric mean computed.

### 9.3 `confidenceGate.js` and `researchRating.js` — confirmed migrated to `data_coverage`

`src/lib/confidenceGate.js`'s own docstring states directly: the quantity it gates on "is
`data_coverage` — the share of the evidence this model intended to use that actually resolved.
It is not a reliability score ... which is exactly why it was renamed out of 'confidence'."
Every exported function still takes an internally-named `confidence` parameter, but callers
(`src/lib/recommendation.js`, `src/lib/entryTiming.js`) feed it `stock.data_coverage` values —
confirmed by reading the call sites, not just the gate module. `src/lib/researchRating.js:48`:
`rating *= finite(row.data_coverage) ? Math.max(MIN_CONFIDENCE_SHRINK, row.data_coverage) :
LIGHT_DATA_SHRINK` — reads `data_coverage` directly, with a fixed shrink fallback for
`screen_universe` rows that never compute a coverage figure. A one-time migration shim remains
for legacy cached rows: `src/lib/schemaMigrations.js:131-153` — `if (migrated.data_coverage ==
null && row.confidence != null) migrated.data_coverage = row.confidence` — but every live
consumer reads `data_coverage` as primary, and this shim only exists to upgrade old data, not as
an ongoing dual-name dependency.

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
6. **Two distinct config files both omit `"semiconductor"`/`"other_pre_profit"` — one causes a
   real, severe score effect via `metric_registry.json`; the other causes an informational-only
   gap via `business_profiles.json`. Both confirmed independently this session, against
   different mechanisms.**

   **6a. `metric_registry.json`'s default profile list — confirmed high-severity score effect.**
   The live path's suppression function, `canonical_metrics.suppressed_metrics(profile,
   metric_ids)` (`canonical_metrics.py:153-171`, called from `scorer.applicability` at
   `scorer.py:243-260`), suppresses a metric **only** when an *explicit* per-profile rule exists
   in `applicability_matrix.json`'s `rules` object — for `"semiconductor"`, exactly two metrics
   (`capex_to_depreciation`, `inventory_days_trend`). The shadow path's suppression function,
   `canonical_metrics.applicability_for(metric_id, profile)` (lines 141-150, called once per
   metric from `scoring_v2.build_v2_analysis`), has a **second, broader suppression path**: when
   no explicit rule exists for a metric/profile pair, it checks whether the profile is listed in
   that metric's `applicability_profiles` declaration in `metric_registry.json`, and **suppresses
   by default if not listed**. `metric_registry.json`'s `declaration_defaults.
   applicability_profiles` (the fallback list used by any metric without its own explicit
   declaration) lists 11 profiles and does not include `"semiconductor"` or
   `"other_pre_profit"`. Net effect, verified against the live artifact for CRUS
   (`applicability_profile: "semiconductor"`): the **live** path suppresses 3 metrics; the
   **shadow** path's `analysis_v2.applicability.suppressed_metrics` suppresses **28 of CRUS's
   ~32 scoreable metrics**, including `forward_pe`, `price_to_book`, `return_on_equity`,
   `interest_coverage`, and `piotroski_f`. This is not informational-only: CRUS's shadow
   `structural.raw_score` (100.0) is computed from `applicable_weight: 0.1304` — only 13% of
   total category weight is even applicable — with three of six categories (`financial_health`,
   `growth`, `accounting_quality`) entirely `None` (verified by direct query against the live
   artifact). **Severity: high.** For a semiconductor name, the shadow structural score is not a
   differently-computed version of the same evaluation the champion performs — it is computed
   from almost no data, confidently, because a single missing entry in a config file's default
   profile list silently starves it. This has no live-path analogue (the live path's raw_score
   for CRUS uses the normal ~29-metric base) and is a materially more severe, and mechanically
   distinct, finding from the informational-only gap in 6b below.

   **6b. `business_profiles.json`'s `profiles` object — confirmed informational-only, no score
   effect.** The same two profiles are also absent from `business_profiles.json`'s `profiles`
   dict, which `scoring_v2.py:241-247` reads separately for `replacement_metrics`/
   `critical_metrics` — a different config file from 6a, consulted by different code.
   `required_for_score` reads `applicability_matrix.json`, and category weights read
   `settings.json`; neither consults `business_profiles.json`, so this specific gap has **no
   score effect**. Live consequences instead: the v2 applicability contract's
   `replacement_metrics`/`unavailable_replacement_metrics`/`critical_data_gaps` fields publish
   empty (`[]`/`[]`/`[]`) for CRUS, versus THG's 23 declared replacement metrics (21 unavailable)
   and 3 critical data gaps — the "what should we be measuring instead, and what's missing"
   machinery structurally cannot fire for a semiconductor or other-pre-profit name. Worse,
   `profile_confidence` (`scoring_v2.py:247`: `0.0 if not critical else (len(critical) −
   len(critical_gaps)) / len(critical)`) publishes `0.0` for THG because all three declared
   critical metrics are missing, and *also* `0.0` for CRUS because none were ever declared — a
   reader of the payload cannot distinguish "profile contract fully unmet" from "no profile
   contract exists" from this field alone. **Severity: low today** (informational fields only,
   confirmed no score impact), but see 6a for the same root config gap's much more severe sibling
   effect elsewhere in the same shadow layer.
7. **Seven metrics named as profile replacements in config have zero computation anywhere in
   the pipeline.** Confirmed by the parallel metric-registry compilation and independently
   grep-checked this session: `combined_ratio`, `risk_based_capital_ratio`, `normalized_roe`,
   `capital_ratio`, `price_to_ffo`, `affo_yield`, `cash_runway_months` are named as the intended
   substitute metrics for insurers, banks, and REITs in `applicability_matrix.json`'s
   `replaced_by` fields and/or `business_profiles.json`'s `replacement_metrics` lists, but no
   function in `pipeline/*.py` computes any of them — they are declared in
   `metric_registry.json` (so they have units, a direction, a definition) but never populated.
   Combined with finding §5's separate result (a *computed* replacement metric doesn't inherit
   the suppressed metric's weight), this means the applicability system's `replaced_by` metadata
   currently promises two things neither of which is delivered in full: the named replacement
   either (a) doesn't exist as a computed value at all (this finding), or (b) exists but carries
   only its own small configured weight rather than the suppressed metric's larger one (§5).
   **Severity: moderate** — this is arguably honest (an insurer's combined ratio genuinely isn't
   available from this pipeline's free data sources, matching the "unbuildable on free data"
   conclusion the internal audit reached about the timeliness layer), but the config's framing
   as a "replacement" rather than an acknowledged gap could mislead a reader of the applicability
   payload into thinking a substitute is actually in use.
8. **`portfolio_fit: below_target` is a structural constant for every unpositioned name** — this
   item from the internal audit is confirmed **not fixed** (§8.2), unlike its three siblings.
   Severity: low for the *score* (portfolio fit is not an input to the composite score) but
   directly affects position-sizing guidance display for any user without a matching portfolio
   entry, which given `portfolio_coverage` limitations (not yet quantified this session — see
   §11) may be most published names.
9. **THG's `effective_score` appears as two slightly different values in one payload —
   root-caused as a rounding-order defect.** `74.5` (`analysis_v2.structural`) is computed by
   the producer from **unrounded** confidence (`scoring_v2.py:164-166`: `0.3418/0.4066 × 0.72
   = 0.60525…` → `50 + 0.60525 × 40.5 = 74.51`), which is then published rounded to two
   decimals (`evidence_weight_resolved: 0.61`, `scoring_v2.py:188`). `74.7`
   (`recommendation_v2.company.structural`) comes from `recommendation_policy_v2._score_layer`
   (`recommendation_policy_v2.py:59`), which **recomputes** the effective score from the
   layer's *rounded* published confidence instead of trusting the `effective_score` field the
   layer already carries: `50 + 0.61 × 40.5 = 74.705 → 74.7`. Both arithmetics reproduce the
   published values exactly. **Severity: low numerically (bounded by ±0.005 × |raw − 50|, so
   ≤ ±0.25 points), but it is a genuine "same value, two answers" contract violation** — a
   downstream module re-derives from lossier inputs what its input already states, and both
   versions publish. Full derivation in `TRACE_THG.md` §4.
10. **The live path and the v2 path can suppress *different metrics for the same company* —
   root-caused as two distinct registry-consultation gaps, both confirmed by direct read.**
   For THG: `fundamental_detail.suppressed_metrics` includes `sales_multiple` but not
   `trailing_revenue_growth`; the v2 blocks do the reverse. Cause (full detail in
   `TRACE_THG.md` §5 item 1):
   - *Namespace split*: the live path queries the applicability registry with legacy IDs
     (`scorer.py:252`), the v2 path with canonical IDs after `ALIASES` mapping
     (`scoring_v2.py:103-104`). `applicability_matrix.json`'s insurer rule is keyed
     `sales_multiple` (legacy), so only the live path sees it; the v2 path asks about
     `price_to_sales`, which has no rule and no registry entry, and treats it as applied-but-
     missing.
   - *Fallback asymmetry*: `applicability_for` (v2, `canonical_metrics.py:147-149`)
     suppresses by default any metric whose `metric_registry.json` entry does not declare the
     profile applicable; the live path's `suppressed_metrics` (`canonical_metrics.py:153-172`)
     never consults `metric_registry.json` at all. `trailing_revenue_growth`'s registry entry
     declares no insurer profiles, so v2 suppresses it — while **the live scorer scores
     revenue growth for insurers** (`scorer.py:584`), against the registry's declared intent.
     The effect is score-relevant, not cosmetic: THG's legacy `growth` category is 86.1 (with
     revenue growth in) vs. v2's 100.0 (with it out).
   - The `suppressed_metrics` docstring's claim that "one authority now serves both paths"
     (`canonical_metrics.py:156-162`, describing `0e0a9ad`) is therefore only half-true: one
     *file set*, two inconsistent read paths. **Severity: moderate** — the live score includes
     (or excludes) metrics contrary to the canonical registry's declarations for any profile
     whose rules are keyed in only one namespace, or whose suppression relies on the
     registry-declaration default.

### 10.3 Further defects found this session, from the data-sources/publication research pass

11. **Configured rate limits for Alpha Vantage, Marketaux, and FRED are dead configuration.**
    `pipeline/cache.py`'s `DEFAULT_RATE_LIMITS` declares `alpha_vantage: 5`/min, `marketaux:
    60`/min, `fred: 120`/min, but none of the three provider modules ever calls
    `limiter_for()` — Alpha Vantage instead paces itself with an independent hardcoded
    `1.1`s-between-requests constant inside `alpha_vantage.py`; Marketaux and FRED have no
    pacing at all beyond whatever the synchronous per-symbol loop imposes naturally. Only Yahoo
    and SEC EDGAR actually route through the shared token-bucket limiter. **Severity: low
    operationally** (Alpha Vantage's own pacing is arguably more conservative than the
    configured limit, and the low per-run call volumes for Marketaux/FRED make a runaway
    unlikely), **but the config values are misleading** — a reader of `settings.json`/`cache.py`
    would reasonably conclude all five providers are rate-limited identically, and three of them
    are not limited by this mechanism at all.
12. **A whole unused adapter class.** `pipeline/providers.py:291-323` defines
    `AlphaVantageAdapter`, which *does* correctly call `limiter_for(self.name)` — but nothing in
    the codebase imports or instantiates it; `fetch_advisor.py` uses `AlphaVantageClient` from
    `alpha_vantage.py` instead, which is the version described in defect 10 above. This reads as
    an abandoned refactor: the rate-limit-respecting version of the Alpha Vantage client exists
    in the codebase and is not the one actually running.
13. **A stale diagnostic comment describing the opposite of current behavior.**
    `fetch_advisor.py:1901-1904` states institutional-ownership scoring "has never run against
    the live OpenFIGI endpoint or live 13F filings." The live artifact
    (`public/data/screens/institutional-13f.json`) shows it has run — `status: "success"`,
    3,489 CUSIPs seen, 278 mapped — and produces zero usable rows only because the
    corroboration gate (`min_managers: 2`) isn't cleared with just 3-4 resolved managers. A
    reader of this comment would conclude the feature is entirely unbuilt/untested rather than
    built, running, and currently under-corroborated. **Severity: low** (does not affect scoring
    — `institutional_ownership` is `None` for all 40 published rows either way, correctly), but
    it actively misleads anyone reading the code to understand system state, which is the exact
    failure mode this whole specification exercise is meant to guard against.
14. **`StockWatcherClient`'s endpoint is confirmed dead** (HTTP 403 on every request, per its
    own docstring in `congress_trades.py`), leaving the weekly Congressional-trades screen
    dependent on two of its three intended sources. The published screen self-reports
    `status: "partial"`. Not hidden — the status field is honest — but worth noting as a
    source that could simply be removed rather than left silently failing every run.
15. **Three provider API keys used in code are absent from `.env.example`**: `FMP_API_KEY`
    (`congress_trades.py`), `OPENFIGI_API_KEY` (`openfigi_client.py`), `MARKETSTACK_API_KEY`
    (`marketstack.py`). A new deployer following `.env.example` and the README's local-setup
    instructions would not know these three variables exist or matter, even though three
    published screens (Congressional trades, institutional 13F look-through, Marketstack
    pre/post-market prices) depend on them.

### 10.4 Not yet investigated this session (candidates flagged by the internal audit, unverified either way)

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

Consolidated from every UNDETERMINED marker above, plus items not yet touched at all.
Resolved since the checkpoint draft (and removed from this list): per-modifier caps (§6.5, now
all directly verified), `ranking_weights` config presence (§6.1, confirmed in `settings.json`),
the 74.7 vs. 74.5 discrepancy (§10.2 item 9, root-caused), the two `suppressed_metrics`
lists (§10.2 item 10, root-caused), the `"replaced"` status question (§5 — real but
currently invisible, behaviorally identical to `"suppressed"`), and the missing
`semiconductor`/`other_pre_profit` profile entries (§10.2 item 6 — split into a confirmed
high-severity score effect via `metric_registry.json` and a confirmed informational-only gap
via `business_profiles.json`; see item 6a/6b), and `CrossSectionalNormalizer`'s internals
(§4.4, now read in full). Still open:

- Full TTM/annual/quarterly period-convention audit across all ~29 fundamental metrics (§4.3).
- Split/dividend adjustment handling in price history (`fetch_prices.py`, not opened this
  session).
- Everything in §10.4 (audit items not re-verified).
- Whether the universe (`advisor_universe.json`) has ever changed prior to this repository
  clone's visible history — this session's clone is shallow (136 commits visible), so "1 commit
  touches this file" is not proof of a static history, only of what's visible (§3).
- Full field-by-field walkthrough of `pipeline/schemas/advisor.schema.json` (930 lines) — only
  spot-referenced this session, not exhaustively mapped field-by-field to producing code (§9).

---

## 12. Test and validation inventory

**Scale**: `pipeline/tests/` — **111** Python test files. `src/**/*.test.{js,jsx}` — **59**
files (14 components, 32 lib, 12 pages, 1 at `src` root).

Representative sample across modules: `test_fundamentals_extended.py`
(`test_altman_z_is_skipped_for_banks`, `test_altman_variant_follows_the_sector`,
`test_z_double_prime_drops_the_asset_turnover_term`,
`test_piotroski_rewards_improving_fundamentals`); `test_peer_claims_regression.py`
(`test_thg_publishes_no_percentile_claim`,
`test_no_row_anywhere_publishes_a_continuous_percentile`,
`test_tied_valuation_scores_never_land_in_different_tiers` — this file exists specifically to
prevent the §10.1 peer-percentile defect from recurring, with THG as a named regression case);
`test_universe_config.py`; `test_ic_harness.py` (18 tests); `test_score_calibration.py`;
`test_data_coverage.py` (19 tests); `test_pit_store.py` (18 tests); `test_scorer.py` (38 tests).
These span provider clients, scoring, PIT storage, and screen builders.

**Does any test assert a financial calculation against an independently-known-correct value?**
Yes, at the formula level, against hand-computed expected numbers on synthetic fixtures — e.g.
`test_fundamentals_extended.py`: `derive_roic(INCOME, BALANCE) ≈ 0.1572`;
`derive_interest_coverage(INCOME) == 12.5`; gross-profits-to-assets `== 0.3` (hand-derived from
`(1000-400)/2000`); `derive_asset_growth == 0.2` (`1200/1000-1`); `days_sales_outstanding ==
150/1000*365`. These are internal-consistency/regression checks against fixed synthetic inputs,
**not** validation against an independently-published real-world reference value for an actual
company (e.g. a hand-verified Altman Z for a real, named filer). No such external-ground-truth
test was found.

**Backtest / IC / calibration — verified against code and live artifacts together, not code
alone:**

- `pipeline/score_calibration.py` (227 lines): builds a score-vs-forward-return calibration
  table from the IC harness's closed observations. Its own docstring states plainly that "the IC
  harness has 0 of the 24 required periods and the PIT store is three days deep, so this
  publishes `insufficient_data` with real bucket definitions and zero counts."
- `pipeline/reports/score_calibration.json` (live artifact) confirms this at runtime: every
  fixed score band (`80+, 75-79, ... 0-59`) shows `"status": "insufficient_data",
  "observations": 0, "shortfall": 30`.
- `pipeline/evaluation.py` (442 lines) and `pipeline/validation/ic_harness.py` (626 lines)
  implement the actual methodology described in the README: rank IC (Spearman), ICIR, quantile
  spread/monotonicity, deflated Sharpe ratio (Bailey & López de Prado 2014), and
  probability-of-backtest-overfitting via combinatorially-symmetric cross-validation (Bailey et
  al. 2017). `ic_harness.py` states it "only grades scores that were recorded before their
  forward returns existed... until a later PIT snapshot supplies a complete forward horizon,
  every statistic remains in an accumulating state."
- Live artifact `public/data/validation/ic_validation.json` (`generated_at:
  2026-08-10T05:23:43Z`) confirms this is still true today: `snapshot_refreshes: 29`,
  `monthly_score_snapshots: 1`, and for every horizon under `primary_variants.champion`:
  `"periods_accumulated": 0, "minimum_periods": 24, "status": "accumulating", "mean_rank_ic":
  null, "icir": null`.
- Confirmed in `public/data/advisor.json`: every published row's
  `data_coverage_detail.components.historical_calibration` is `null` (spot-checked across the
  file). `pipeline/data_coverage.py:127,159-178` is the code that always resolves this to `None`
  while `CFG.get("historical_calibration_minimum_periods", 24)` is unmet.

**Plain statement, as the brief requires: no predictive-performance validation currently exists
with a non-null result anywhere in this repository.** The machinery — rank IC, ICIR, deflated
Sharpe, CSCV overfitting probability, score-bucket calibration — is fully implemented and wired
into a real IC harness that has accumulated 29 snapshot refreshes so far, but every gate
requires either 24 monthly IC periods or 30 closed forward-return observations per score bucket,
and both remain at 0/insufficient as of the latest run. This is visible both in the code's own
comments and in the live JSON artifacts the system currently publishes — it is a designed,
self-reported "not yet," not a silently missing or fabricated capability. This directly answers
§6.6's question from the other direction: it is not merely that no weight has been *fitted* to
data — no score, weight, or threshold in this system has been *validated* against forward
outcomes either, and the system says so about itself in its own published output.
