# TODO

_Last updated: 2026-08-02 (revised after the first production run and the universe expansion)_

What is still needed to make the rebuilt scoring platform fully functional. The model,
schemas, tests, and infrastructure are in place and green; the items below are the gaps
between "the code runs" and "every declared capability actually produces data".

Grouped by what they block. Within each group, roughly in the order worth doing.

**Confirmed by the 2026-08-02 production run** (338 companies, 40 published): schema v2,
the 78/18/4 blend, the rebuilt technicals, `gross_profits_to_assets` (32/40), `ev_to_ebit`
(32/40), `asset_growth` (40/40), and sector-correct Altman variants (8 manufacturing,
24 non-manufacturing, 8 financials suppressed) all landed. The point-in-time store wrote
its first 338 observations and committed them. Cache hit rate was 47.5% on a cold start.
Form 4 and the theme screen both reported `unavailable` for the reason in §1.

**Universe expanded after that run**: stocks 343 -> 910, ETFs 40 -> 126. This was not
cosmetic. Every ETF peer group is now above the ranking threshold, so **zero funds fall back
to cross-asset-class pooling** (nine did before), and stock deciles hold ~91 names instead of
~34, which is what makes the rank-IC estimates in §3 worth reading. Alpha Vantage enrichment
is capped at five symbols regardless of universe size, so the growth costs only free Yahoo
requests. Price history is batched for both universes, quotes are prefetched in parallel, and
the screen payload was slimmed to the nine fields the screens actually read - without that
last change the browser would download roughly twice the JSON for no benefit.

---

## 1. Blocked on configuration — nothing works until these exist

These are credentials and endpoints, not code. Each one silently disables a feature that
is otherwise finished, and each reports itself unavailable rather than failing loudly.

- [ ] **`SEC_USER_AGENT` GitHub secret.** No registration or application is required — the
      SEC just wants a real identifier and a working email so they can make contact if a
      script misbehaves. Format is a plain string: `Joshua Smith jbmsmusic05@gmail.com`.
      Add it under **Settings → Secrets and variables → Actions**; the workflow already
      reads it, and `.env.local` covers local runs.

      Confirmed unset by the 2026-08-02 run: `source_status.sec_form4` reported
      `"unavailable"` and `theme_screen` reported
      `"SEC_USER_AGENT is required by SEC fair-access policy"`. **Two finished features
      produce nothing until this exists**: the Form 4 insider modifier and the entire
      theme-exposure screen. *Highest-value item on this list — free, and unblocks the most.*

- [ ] **Rule 6c-11 disclosure endpoints in `pipeline/config/universe.json`.** Currently
      **0 of 126 funds** have one, so every fund falls back to a quote-derived
      premium/discount and a single-moment bid-ask spread instead of the legally mandated
      30-day median. The adapter and field-mapping parser are done; each fund needs a
      `disclosure: {url, format, fields}` block. A worked example sits in
      `etf_scoring.disclosure.example`. Start with the largest issuers — iShares, Vanguard,
      and State Street cover most of the watchlist.

- [x] ~~Index proxies for the 18 funds that lack one.~~ **Largely resolved by the universe
      expansion**: adding the Vanguard sector funds gave every SPDR sector fund a
      like-for-like twin, and coverage went from 22/40 (55%) to 98/126 (78%). The 28 still
      without one are genuine singletons in this watchlist (DIA, ARKK, JETS, INDA, thematic
      one-offs). Either accept that tracking difference is unavailable for them - the UI
      already renders it as absent rather than zero - or add a twin for the handful worth it.

- [ ] **Verify the hardcoded expense ratios.** 126 funds now carry an `expense_ratio` in
      config, and they drift. A stale one directly biases the cost bucket, which is 17% of
      an ETF's score. Once §1's 6c-11 endpoints exist, source these from the disclosure feed
      rather than the config file. A unit-sanity guard (`< 3.0`) is in the test suite, but
      that only catches a decimal/percent mix-up, not a rate that moved 3bp.

---

## 2. Theme layer — declared signals that never answer

The screen technically runs, but only **2 of its 5 declared signals actually compute**
(`filing_keyword_density_trend` and `hyperscaler_capex_growth`). Since
`min_signals_required` is 2, every theme score currently rests on the bare minimum. That
is a thin basis for a screen whose whole purpose is corroboration.

- [ ] **`segment_revenue_share`** — `EdgarThemeSignals` accepts a `segment_map` but
      `fetch_advisor.build_theme_layer` constructs it with none, so this signal never
      fires. Either populate a curated map in config, or write an ASC 280 segment extractor
      against the XBRL segment axes. Note the standing caveat: segment granularity is
      management-determined and genuinely inconsistent between filers, so a curated map may
      be the more honest option.

- [ ] **`customer_concentration_to_spenders`** — same problem, `customer_map` is never
      populated. Needs a 10-K Item 1 major-customer extractor (ASC 280 requires naming
      customers above 10% of revenue) or a curated map.

- [ ] **`transcript_theme_salience`** — normalized in `themes.py` but no provider computes
      it. Needs an earnings-call transcript source. Many filers attach transcripts as 8-K
      exhibits, which is free on EDGAR; the paid APIs (API Ninjas, FMP) are the alternative.

- [ ] **`backlog_growth`** — listed in `LEADING_SIGNALS` and normalized, but nothing
      computes it and no shipped theme declares it. Either build the MD&A extractor or drop
      it from the constant so the list stops implying a capability that does not exist.

- [ ] **`expand_via_tnic: true`** is declared in `ai_infrastructure.yaml` and read by
      nothing. Either wire up the Hoberg-Phillips TNIC peer data (free download) to expand a
      theme from its seed tickers to product-space neighbours, or remove the flag.

- [ ] **Add a second theme.** One theme does not exercise the "drop in a YAML file, no code
      change" claim. A second, structurally different one would prove it.

---

## 2b. Earnings surprise — shipped, measured at zero, now opt-in

The fundamental-momentum input resolved for **0 of 40** published companies on the first
production run. yfinance serves `earnings_dates` by scraping a separate page, one request
per symbol, and the original code swallowed every failure silently — so it spent roughly
110 requests per run to populate a metric that never appeared, with no diagnostic.

It is now cached, logs its failures, reports `requested`/`resolved`/`failed` in
`capability_status`, and is **off by default** behind `ENABLE_EARNINGS_SURPRISE=1` — the
same treatment option-chain volatility already gets, for the same reason. Its growth-bucket
weight stays in config and reweights away while unavailable, so re-enabling needs no other
change.

- [ ] **Diagnose why it returns nothing.** Run once with `ENABLE_EARNINGS_SURPRISE=1` and
      read the new warnings: they will distinguish a blocked scrape from a genuinely absent
      calendar. If the endpoint is simply gone, source surprises elsewhere (Alpha Vantage
      `EARNINGS` returns `surprisePercentage` and would cost quota, not scrapes) or drop the
      metric and redistribute its 0.16 growth weight.

---

## 3. Validation — the harness has nothing to validate yet

- [ ] **Accumulate point-in-time history.** `evaluate_signal.py` currently exits with "the
      point-in-time store is empty". It needs roughly **8+ weekly observations** before an
      IC estimate means anything, so this resolves with calendar time, not with work. The
      store starts appending on the next pipeline run.

- [ ] **Validate the rebalanced weights against real data.** Every weight change in this
      rebuild is argued from published evidence, **not** verified on this universe. Once the
      store has depth, run `evaluate_signal.py --trials <honest count>` and check whether
      each bucket earns its weight. Per the stated benchmark: if a bucket's mean monthly
      rank IC is below ~0.02, cut its weight materially.

- [ ] **Migrate `optimize_weights.py` to the new harness.** It still sweeps weights against
      a single equity-curve objective with no deflation and no point-in-time inputs — which
      is precisely the overfitting pattern `evaluation.py` exists to catch. It should call
      `evaluate_candidate` and honour the deflated-Sharpe gate.

- [ ] **Migrate `backtest_historical.py` to the point-in-time store.** It reconstructs
      history from yfinance's restated statements, which it documents as an approximation.
      Once the store has depth, it should read from there instead.

- [ ] **Automate paper-trading promotion.** `log_paper_period` and `score_paper_log` exist
      and are tested, but nothing calls them on a schedule. A weekly job should freeze the
      live config, log the quantile portfolios, and compare realized forward IC against the
      backtest before any config change is promoted.

---

## 4. Adoption — built but not yet wired through

- [ ] **`providers.py` is only half adopted.** `fetch_advisor` imports `YahooAdapter` for
      one static helper; the rest of the fetch path still calls yfinance and the Alpha
      Vantage client directly. The ports-and-adapters layer only pays off once scoring
      depends on `AbstractDataProvider` alone. Migrating `collect()` is the main piece.

- [ ] **Per-stock theme exposure in the detail modal.** `theme_screen.by_ticker` is emitted
      for exactly this purpose and the frontend never reads it. A holding's theme exposure
      should appear alongside its fundamentals so exposure and quality are visible together.

- [ ] **Surface the data-freshness panel.** `pit_store.freshness_report` is computed and
      published to `advisor.json` on every run; no component displays it.

- [ ] **Surface point-in-time depth in the UI.** `point_in_time_store` is published so the
      site can say when backtests become trustworthy. Nothing shows it yet.

---

## 5. Smaller cleanups

- [ ] Remove the four pre-existing unused imports flagged by pyflakes in
      `alpha_vantage.py`, `fetch_news.py`, and `fetch_prices.py`.
- [ ] `fetch_prices.py` and `seed_mock_data.py` still bypass the cache layer entirely.
- [ ] The built JS bundle is ~898 kB (267 kB gzipped) and Vite warns about it; the
      dashboard would benefit from route-level code splitting.
- [ ] `capability_status.form4_insider_transactions` and the older capability notes in
      `fetch_advisor.py` should be re-checked once §1 and §2 land — several will have moved
      from "required" to "available".

---

## 6. Strategy-lens input coverage — the screens work, the inputs are thin

The research page's strategy lenses are now genuine screens over the whole scored universe
(they publish their own top 20 rather than re-sorting the leaderboard), and each one reports
its own input coverage on screen. Measured against the 2026-08-08 payload, 875 stocks:

| Lens | Qualifying | Evaluable | Binding input |
|---|---|---|---|
| Momentum | 460 | 875 | – |
| Value turnaround | 29 | 874 | – |
| Analyst conviction | 114 | 114 | analyst coverage, 114/875 |
| Tailwind | 45 | 45 | scored theme exposure, 45/875 |
| Reversal | 19 | 119 | 60-day drawdown, 119/875 |
| Catalyst | 0 | 2 | Form 4 insider activity, 0/875 |

- [x] ~~Form 4 filings downloaded but never parsed.~~ `primaryDocument` in EDGAR's
      submissions feed is the XSL-rendered HTML of an ownership form, not its XML. Fetching
      it verbatim raised in `parse_form4`, the exception was swallowed per filing, and the
      layer reported itself healthy while scoring 0 open-market transactions for all 82
      symbols it reviewed. `sec_edgar.form4_document_urls` now strips the rendering
      directory and falls back, a rendered page is rejected rather than read as an empty
      filing, and `source_status.sec_form4` publishes `filings_reviewed` /
      `filings_unreadable` so this cannot go quiet again.
- [ ] **Per-ticker news reaches almost nothing.** Entity-level sentiment is fetched only for
      the Alpha-enriched shortlist (five symbols per refresh) plus one discovery batch, so
      `components.news_sentiment` resolved for 3 of 877 rows and the catalyst screen has
      essentially no news leg to stand on. Either widen the Marketaux symbol coverage per
      run or accept that Catalyst is a shortlist-only lens and say so in its description.
- [ ] **Reversal sees 119 of 875 names** because `drawdown_60d` only ships on freshly polled
      rows. The fast-refresh rotation added in `rotation_slice` re-polls the stalest tail
      every run, which should close this within a handful of refreshes — re-measure after
      about a week of scheduled runs and drop this item if the table above has moved.
- [ ] Analyst coverage resolves for 114 of 875 rows. Worth checking whether that is a Yahoo
      coverage limit or an enrichment-budget artifact before treating the lens as narrow by
      nature.

---

## Standing caveats — not tasks, but do not let them drift

These are properties of the domain, not bugs to be fixed. They are listed so nobody later
mistakes them for oversights.

- **Published factor premia are historical, in-sample estimates.** The 5.28%/yr
  enterprise-multiple premium, the 82 bps/month opportunistic-insider return, the
  ~0.66%/month QMJ figure — all are evidence about which signals have mattered, not
  forecasts of what they will return.
- **Anomaly decay is real and ongoing.** Accruals largely stopped working after 2002;
  price-to-book has been weak for decades on intangibles. Whatever is reweighted today will
  need rechecking.
- **Free-tier limits move constantly.** Alpha Vantage's daily cap has gone 500 → 100 → 25;
  Polygon rebranded; FMP moved segments and transcripts behind paid tiers. Re-verify before
  relying on any of them.
- **yfinance is unofficial** and breaks without notice. Never a production-critical path
  without cache and fallback.
- **Price momentum must never contribute to theme exposure.** Enforced in three places
  (config validation, scoring, and `validate_data.py`). If a future change needs one of
  those relaxed, that is the signal to stop, not to relax it.
