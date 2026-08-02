# TODO

_Last updated: 2026-08-02_

What is still needed to make the rebuilt scoring platform fully functional. The model,
schemas, tests, and infrastructure are in place and green; the items below are the gaps
between "the code runs" and "every declared capability actually produces data".

Grouped by what they block. Within each group, roughly in the order worth doing.

---

## 1. Blocked on configuration — nothing works until these exist

These are credentials and endpoints, not code. Each one silently disables a feature that
is otherwise finished, and each reports itself unavailable rather than failing loudly.

- [ ] **`SEC_USER_AGENT` GitHub secret.** SEC fair-access policy requires a real
      application and contact string (for example `ValueSignal research you@example.com`).
      Without it, `SecEdgarClient.available` is false and **two finished features produce
      nothing**: the Form 4 insider modifier and the entire theme-exposure screen. Add
      under **Settings → Secrets and variables → Actions**; the workflow already reads it.
      *Highest-value item on this list — it costs nothing and unblocks the most.*

- [ ] **Rule 6c-11 disclosure endpoints in `pipeline/config/universe.json`.** Currently
      **0 of 40 funds** have one, so every fund falls back to a quote-derived
      premium/discount and a single-moment bid-ask spread instead of the legally mandated
      30-day median. The adapter and field-mapping parser are done; each fund needs a
      `disclosure: {url, format, fields}` block. A worked example sits in
      `etf_scoring.disclosure.example`. Start with the largest issuers — iShares, Vanguard,
      and State Street cover most of the watchlist.

- [ ] **Index proxies for the 18 funds that lack one.** `DIA, JEPI, XLK, XLF, XLV, XLE,
      XLY, XLP, XLI, XLB, XLRE, XLU, XLC, ITA, ICLN, TAN, ARKK, IBIT` have no
      `index_proxy`, so they get no tracking difference and their cost bucket falls back to
      the expense ratio alone. The sector SPDRs have no free like-for-like twin in this
      watchlist; either add Vanguard sector funds to the universe as proxies, or accept
      that tracking difference is unavailable for them and say so in the UI.

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
