# TODO

_Last updated: 2026-08-09, revised three times same day (backlog_growth wired via
dimensional XBRL, §2; customer-concentration and geographic-concentration modifiers moved
to shadow mode pending coverage measurement, §2a; institutional 13F pulled out of the
score into a congress-style screen with active/passive manager classification, then put
back into the champion score with filing-lag decay and amendment/revision handling per
explicit instruction, §2a; a political-protection framing for Congressional trades
declined, a narrower reward-only congressional-buying modifier built instead per
follow-up instruction, §2a; point-in-time capture for all of the above confirmed, §2c)_

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

The screen technically runs, and now **3 of its 6 declared signals actually compute**
(`filing_keyword_density_trend`, `hyperscaler_capex_growth`, and — as of this update —
`backlog_growth`, once it has actually run in production; see below). Since
`min_signals_required` is 2, every theme score still rests close to the bare minimum. That
is a thin basis for a screen whose whole purpose is corroboration.

- [ ] **`segment_revenue_share`** — `EdgarThemeSignals` accepts a `segment_map` but
      `fetch_advisor.build_theme_layer` constructs it with none, so this signal never
      fires. Either populate a curated map in config, or write an ASC 280 segment extractor
      against the XBRL segment axes. Note the standing caveat: segment granularity is
      management-determined and genuinely inconsistent between filers, so a curated map may
      be the more honest option.

- [ ] **`customer_concentration_to_spenders`** — same problem, `customer_map` is never
      populated. Needs a 10-K Item 1 major-customer extractor (ASC 280 requires naming
      customers above 10% of revenue) or a curated map. Note this stays a name-matching
      problem even after `xbrl_dimensions.dimensional_facts` — `us-gaap:
      ConcentrationRiskPercentage1` dimensioned by `ConcentrationRiskByTypeAxis =
      CustomerConcentrationRiskMember` gives the *magnitude* of concentration, not the
      customer's identity, so it can sharpen a curated match's confidence but cannot
      replace the name lookup. **Before wiring the percentage in as anything more than a
      confidence input**, measure tagging coverage across the scored universe — plenty of
      filers disclose the customer in Item 1 prose and never tag the percentage at all. If
      coverage comes in under roughly 60%, treat it as a confidence input, not a gate, and
      lean on full-text search over the risk-factor language as the fallback.

- [ ] **`transcript_theme_salience`** — normalized in `themes.py` but no provider computes
      it. Needs an earnings-call transcript source. Many filers attach transcripts as 8-K
      exhibits, which is free on EDGAR; the paid APIs (API Ninjas, FMP) are the alternative.

- [x] ~~**`backlog_growth`**~~ Root cause wasn't a missing MD&A extractor: 
      `RevenueRemainingPerformanceObligation` is XBRL-tagged, but `company_concept` and
      `companyfacts` return default (non-dimensional) facts only, and filers routinely tag
      this concept solely in `SatisfactionPeriodAxis` bands ("within 12 months" / "beyond
      12 months") with no undimensioned total for those APIs to return — so the concept
      looked untagged when it was really just dimensioned. `pipeline/xbrl_dimensions.py`
      reads `<context>` segments straight out of the filing document (the same raw text
      `filing_keyword_signals` already fetches), and
      `EdgarThemeSignals.backlog_values`/`backlog_total` sum the bands when no total
      exists. `ai_infrastructure.yaml` now declares it at weight 0.10. **Not yet done:**
      run it in production and check resolution rate across the scored universe — nothing
      here has executed against a live filing.

- [ ] **`expand_via_tnic: true`** is declared in `ai_infrastructure.yaml` and read by
      nothing. Either wire up the Hoberg-Phillips TNIC peer data (free download) to expand a
      theme from its seed tickers to product-space neighbours, or remove the flag.

- [ ] **Add a second theme.** One theme does not exercise the "drop in a YAML file, no code
      change" claim. A second, structurally different one would prove it.

---

## 2a. `capability_status.fx_exposure`, `.institutional_13f_changes`, and
     `.customer_concentration_risk` — corrected diagnosis, revised architecture

First pass (2026-08-09, early) wired all three straight into the champion score. Review
caught two separate mistakes in that: shipping unmeasured coverage as if it were verified,
and treating curated-manager 13F flow as a clean proxy for conviction when it is dominated
by mechanical index rebalancing. Both are fixed below, not patched over.

- [x] ~~**`fx_exposure`**~~ Scored as single-country revenue concentration
      (`pipeline/geographic_exposure.py`) from `us-gaap:Revenues` dimensioned on
      `StatementGeographicalAxis`, read via `pipeline/xbrl_dimensions.dimensional_facts`
      the same way `backlog_growth` is — deliberately narrower than "FX exposure" as a
      general idea, penalizing concentration in one non-domestic geography, not
      international revenue in general. **Shadow mode only**: wired into
      `apply_challenger_modifiers`, deliberately absent from the champion
      `apply_modifiers` (see that function's docstring). Two reasons, not one: coverage
      is unmeasured (below), and geography tags routinely reflect shipping destination or
      contracting entity rather than end demand — a contract manufacturer can book
      enormous "China" revenue that is really an assembly step. Both need checking against
      real filings before this penalizes a live score.

- [x] ~~**`customer_concentration_risk`**~~ Not the same capability as the theme layer's
      `customer_concentration_to_spenders` above (§2) — kept separate deliberately.
      `us-gaap:ConcentrationRiskPercentage1` dimensioned by `ConcentrationRiskByTypeAxis =
      CustomerConcentrationRiskMember` gives concentration *magnitude*, scored as a
      penalty-only modifier (`pipeline/concentration_risk.py`); it still cannot name the
      customer, so it cannot answer the theme layer's supply-chain question. **Shadow mode
      only**, same as `geographic_concentration` and for the sharper version of the same
      reason: a penalty-only modifier that only fires on filers who happened to tag the
      concept systematically favors whichever companies didn't tag it — worse than not
      scoring it at all. `capability_status.customer_concentration_risk` now publishes
      `concentration_tag_coverage` (tagged filings ÷ filings reviewed) every run
      specifically so this has a number attached before anyone promotes it to champion.
      **The gate**: promote to `apply_modifiers` only once coverage across the scored
      universe is measured on a live run and clears roughly the same ~60% bar the theme
      layer's own concentration signal is held to (§2 above) — below that, it stays a
      confidence input at most, never a hard modifier.

- [x] ~~**`institutional_13f_changes`**~~ **Back in the champion score, third revision of
      this capability in one day.** First pass: bounded modifier, straight into
      `apply_modifiers`, no lag treatment. Second pass: pulled out of scoring entirely
      into `pipeline/build_institutional_screen.py`, a standalone factual screen (same
      architecture as `pipeline/build_congress_screen.py`), on the reasoning that
      restricting 13F reads to *publicly traded* managers (there is still no per-company
      "who holds this ticker" EDGAR endpoint, so full-universe coverage still needs SEC's
      bulk quarterly data sets) oversamples the largest passive indexers — BlackRock,
      State Street, Invesco — whose position changes are close to mechanically determined
      by index membership, not conviction. Third pass, per an explicit instruction to put
      it back with staleness priced in: restored to `apply_modifiers`, keeping everything
      the second pass built rather than discarding it.

      **What "priced in" means concretely**: the screen (still monthly, still the source
      of record — nothing in the hourly/daily advisor refresh re-fetches SEC or OpenFIGI
      for this) now publishes `undecayed_magnitude` and `as_of` per ticker.
      `fetch_advisor.collect_institutional_signals` reads that publish, computes
      `days_since_filed` against *today* (the day the score is actually being computed,
      not the screen's own generation time), and applies
      `institutional_ownership.decay` — a 45-day half-life, zero past 135 days — before
      it ever reaches `advisor_engine.institutional_ownership_modifier`. A filing sitting
      near the next quarter's deadline contributes close to nothing; a fresh one scores
      near full weight. Config in `settings.json`'s `modifiers.institutional_13f`
      (`half_life_days`/`max_age_days`).

      **What "retroactive" amendments needed, concretely**: a 13F-HR/A revises a quarter
      already filed, and grouping by filing order alone would mistake the amendment for a
      new quarter or silently prefer whichever filing happened to be fetched last.
      `build_institutional_screen.manager_quarters` now groups by the *period* a filing
      covers (`sec_edgar.SecEdgarClient.filings_for_cik`/`recent_forms` carry EDGAR's
      `reportDate` and `form` fields for exactly this) and keeps the most recently *filed*
      record per period, so an amendment supersedes the original it revises. A value
      change between the two is logged to
      `pipeline/data/institutional_13f/revisions.jsonl` (mirroring
      `pit_store.diff_revisions`) rather than silently overwritten — the original
      observation stays in history either way.

      **Kept from the second pass, unchanged**: coverage still defaults to `style: active`
      managers only (`pipeline/config/institutional_managers.json`) — passive and
      private-equity/`alternative` managers are still excluded, since decay addresses
      staleness, not the sampling-bias problem the second pass identified. That bias is
      *mitigated*, not eliminated, and is documented on the modifier itself
      (`advisor_engine.institutional_ownership_modifier`'s docstring), not silently
      assumed fixed by being back in the score. CIK resolution is still always through the
      live `ticker_map()`, never a hand-typed CIK; CUSIP→ticker still goes through
      OpenFIGI (`pipeline/openfigi_client.py`).

      **Not yet done, because there was no network access while any of this was
      written**: none of it has executed against the live OpenFIGI endpoint or a live 13F
      filing. Verify the CUSIP resolution rate and manager coverage on the first real
      run — the logic is tested end-to-end against synthetic fixtures
      (`tests/test_institutional_ownership.py`, `tests/test_openfigi_client.py`,
      `tests/test_build_institutional_screen.py`, `tests/test_collect_institutional_
      signals.py`, `tests/test_sec_edgar.py`), but a fixture cannot tell you OpenFIGI's
      real resolution rate, whether the curated managers' tickers still route to the CIKs
      this list assumes, or how often a real amendment actually revises a real filing.

- [x] ~~**`congressional_buying` — declined once, then built in a narrower, confirmed
      form.**~~ First ask: weight the institutional 13F modifier by whether Congressional
      trade disclosures show the same stock or sector as one politicians "wouldn't let
      fail." Declined — `advisor_engine.py`'s own governing line was an unqualified "No
      political inputs," and `build_congress_screen.py`'s docstring is explicit that it
      publishes facts with no conflict-of-interest interpretation layered on. Treating
      congressional holdings as evidence of political protection and scoring that would
      have reversed both decisions rather than extended them.

      Follow-up ask, confirmed after the tradeoff was raised: score disclosed
      Congressional *purchases* on their own terms — not a political-protection claim,
      a reward-only signal on the same evidentiary footing insider buying already gets.
      Refined twice more in conversation: not just large dollar amounts, but *unique*
      picks (a member's first-ever trade in a company, and specifically a small one —
      the obvious blue-chip everyone already holds isn't unusual), and "any positive
      sign" should count too, not only the unusual ones.

      **What shipped**: `pipeline/congress_signal.py`, a bounded, reward-only modifier
      (`congressional_buying`) with two tiers, mirroring `insider_signal.py`'s own
      breadth/freshness/cluster-bonus shape rather than inventing a new one — any
      disclosed purchase is a mild positive (breadth of distinct members × freshness,
      reusing `insider_signal.decay`), and purchases flagged `EXTRAORDINARY_BUY` by a new
      `build_congress_screen.classify` rule (a member's first-ever trade in a company
      under a $2B market-cap ceiling — `market_cap_by_ticker()`, reused from the same
      main-pipeline classification `sector_by_ticker()` already draws on) earn an
      additional breadth-scaled bonus. Sells and non-buying never penalize; this is the
      one modifier in the file that is asymmetric that way, deliberately — a member not
      buying a stock carries none of the "how would they know about this" information
      content a purchase might. Reads the weekly-published congress screen
      (`collect_congressional_signals` in `fetch_advisor.py`), no live FMP calls in the
      per-refresh path, same non-live-fetch pattern the 13F modifier uses.

      `advisor_engine.py`'s module docstring was rewritten to state this exception
      explicitly rather than leave an inaccurate blanket claim in the code — every other
      modifier in the file remains free of political inputs; this is one scoped
      exception, not a reversal of the principle.

      **Evidentiary basis, stated with its limit**: Ziobrowski et al. ("Abnormal Returns
      from the Common Stock Investments of the U.S. Senate", *JFQA* 2004, and the 2011
      House companion study) find significant abnormal returns to disclosed Congressional
      purchases — but in samples predating the STOCK Act's 2012 mandatory-disclosure and
      trading-restriction regime. Whether the edge survives in the post-STOCK-Act world
      this module actually reads (45-day disclosure deadline, the same regime this
      codebase's own point-in-time handling already accounts for) is untested here and
      should be treated skeptically rather than assumed. Has never run against live FMP
      data or a real congress screen publish; verify the `EXTRAORDINARY_BUY` hit rate
      on the first real run, the same way every other never-network-tested capability in
      this file needs verifying.

---

## 2c. The point-in-time record for these signals — confirmed, not assumed

Every one of `backlog_growth`, `customer_concentration_risk`, `geographic_concentration`,
`insider_activity`, `institutional_13f`, and `congressional_buying` has a specific,
checkable answer for "does today's run get recorded before it's gone forever" —
`pit_store.py`'s own governing claim is that a day not captured **cannot be
reconstructed retroactively**.

- **The five score modifiers** (`insider_activity`, `customer_concentration_risk`,
  `geographic_concentration`, `institutional_13f`, `congressional_buying`) are captured
  through `validation/ic_harness.py`, not `pit_store.TRACKED_FIELDS` — that list is
  fundamentals inputs (P/E, ROE, ...), and no modifier has ever lived there, insider
  activity included. `ic_harness.append_refresh` runs on every `fetch_advisor.run()`
  (`fetch_advisor.py`'s `append_ic_refresh` call) and snapshots `row["modifiers"]` through
  `_modifier_contract`, keyed off `settings.json`'s `validation.modifier_fields` — which
  now lists every new modifier name alongside `insider_activity`. Confirmed by
  `tests/test_ic_harness.py::test_snapshot_jsonl_contains_required_reproducibility_fields`
  and `tests/test_explainability.py`, both asserting the full modifier key set. Champion
  `all_points` shows `0.0` for `customer_concentration_risk`/`geographic_concentration`
  (shadow mode) and the real, lag-decayed value for `institutional_13f`; challenger
  `all_points` carries the undecayed-cap comparison for all three.
- **`backlog_growth`** is a theme-layer signal, evaluated through the theme screen's own
  scoring history, not `pit_store`/`ic_harness` at all — same treatment every other theme
  signal (`segment_revenue_share`, `hyperscaler_capex_growth`, ...) already gets.
- **Institutional 13F has two separate point-in-time records now, not one.**
  `pipeline/data/institutional_13f/positions.jsonl` (append-only, keyed by manager/CUSIP/
  **period**, timestamped by **filing** date, with amendments logged to
  `revisions.jsonl` rather than silently overwriting) is the record of what the screen
  itself observed, independent of scoring. `ic_harness`'s own snapshot separately records
  what the *score* used that day, including the decayed `score_points` the modifier
  actually applied — two different questions ("what did the screen see" vs. "what did the
  score do with it"), both answered, neither conflated with the other.
- **Known real gap, pre-existing and not introduced here**: `payload["research"]` (what
  `ic_harness` snapshots with full modifier detail) is only the published top-`N` rows;
  the rest of the scored universe is slimmed via `_screen_row` before reaching
  `screen_universe`, which does not carry `row["modifiers"]`. Every modifier — insider
  activity included — has only ever had point-in-time modifier detail for published rows.
  Not a new limitation, but worth having written down once instead of rediscovering it
  during the first backtest that asks why an unpublished row's modifier history is empty.

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
- [x] ~~**Per-ticker news reaches almost nothing.**~~ Entity sentiment covered 3 of 877 rows
      because it was fetched only for the five Alpha-enriched symbols per refresh.
      `pipeline/yahoo_news.py` now pulls Yahoo's own per-symbol feed for every polled company,
      cached under the existing 30-minute `news` namespace and paced by the shared Yahoo
      limiter. Marketaux/Alpha articles are merged ahead of it rather than replaced: where the
      same story appears in both, clustering folds them into one event and the provider's
      entity sentiment wins it outright.
- [ ] **Validate the headline direction lexicon.** Yahoo publishes no sentiment score, so
      direction comes from `evidence_events.headline_direction_markers` — 65 signed phrases
      matched over the headline and summary. It is a keyword match, not a sentiment model, and
      every event records `direction_source` so the two never get confused; a headline matching
      no phrase is recorded as coverage and scores nothing. Two things worth measuring once
      there is history: what share of real headlines match anything at all (if it is low, the
      catalyst model is running on a thin slice of its own coverage), and whether the matched
      ones are directionally right often enough to be worth the weight.
- [ ] **Watch `source_status.yahoo_news.status` for `unreadable`.** yfinance passes Yahoo's
      stream items through untouched, so this parses an undocumented shape that can change
      without notice. Received-versus-readable counts are published specifically so a shape
      change surfaces as "2,400 items received, none readable" instead of silently looking
      like a quiet news week — the same failure the Form 4 layer had.
- [ ] **Reversal sees 119 of 875 names** because `drawdown_60d` only ships on freshly polled
      rows. The fast-refresh rotation added in `rotation_slice` re-polls the stalest tail
      every run, which should close this within a handful of refreshes — re-measure after
      about a week of scheduled runs and drop this item if the table above has moved.
- [ ] Analyst coverage resolves for 114 of 875 rows. Worth checking whether that is a Yahoo
      coverage limit or an enrichment-budget artifact before treating the lens as narrow by
      nature.
- [ ] **Re-measure the table above after one full refresh on the new collection path.**
      `pipeline/yahoo_estimates.py` now collects EPS revision counts, the EPS trend, rating
      changes and consensus targets, so analyst conviction should stop publishing raw 98s at
      30% confidence (which is what "ranked on level, with no evidence of change" correctly
      looks like today). `target_change_30d_pct` stays null until a second run exists to
      compare against — Yahoo has no as-of-a-past-date endpoint, which is exactly why the
      revision fields are now in `pit_store.TRACKED_FIELDS`.

---

## 7. Ranking-model priors awaiting validation

The nine models in `src/lib/rankingModels.js` carry declared, frozen weights. They are
starting priors drawn from the literature and ordinary market experience — **not** measured
optima, and nothing in this repository has yet tested whether any of them predicts anything.
They are frozen deliberately so the point-in-time store accumulates observations under one
fixed policy; changing them before there is walk-forward evidence would reset that clock.

- [ ] Run the IC harness against each model separately once §3 has eligible periods. A model
      that answers a different question needs its own evaluation, not the champion's.
- [ ] The published research score (`advisor_engine.blend_research_components`) is deliberately
      **unchanged** and still drives `row["score"]`, the calibration bands, the shadow
      portfolios and the PIT observations. The `research` ranking model is a differently
      composed view sitting alongside it. If the evidence eventually favours the new
      composition, promote it through the existing challenger/champion machinery
      (`score_variants`, `experiment_registry`) rather than by editing the champion in place.
- [ ] Event materiality and half-lives (`settings.evidence_events`) are the least evidenced
      numbers in the system. The honest test is whether the decayed event score at time t
      predicts return over t+1..t+k better than article count does.

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

## Redesign follow-ups (from the `docs/REDESIGN-PLAN.md` execution, 2026-08-15)

> Full handoff — what is done, what is left, and four corrections to the plan
> itself — is in `docs/REDESIGN-STATUS.md`. Read that before continuing the work.

Phases 0, 1, 3 and the metadata pass are complete. Phases 2 and 4 are partly
done and 5 is not started. What is left, and why:

### Phase 2 — component consolidation
- **Decompose the giants.** ~~`Portfolio.jsx` (1,286 lines, three views)~~ **done**
  — split into a 233-line shell plus `src/pages/portfolio/` (Summary, Performance,
  DataOverview, Holdings, HoldingCard, ComparisonTables, two pure model modules, a
  forms hook). Rendered DOM verified byte-identical across all three views.
  `SwingScreen.jsx` (839) and `Picks.jsx` (816) still hold view + data + sort logic
  in one file.
- **Four tables not yet on `DataTable`:** Picks, SwingScreen, Portfolio, and the
  three evidence tables in `ResearchEvidence.jsx`. The system and nine
  migrations are in; these four are mechanical but large.
- **Inline-style diet.** 167 `style={{}}` sites remain (down from ~340). The
  static ones should become classes; the computed ones (bar widths, chart
  geometry, `--widget-order`) stay.

### SVG type floor — fixed
`DESIGN.md` forbids text below 11px "including SVG labels". Charts set `fontSize="11"`
as an attribute, but a fixed `viewBox` with `width="100%"` scaled it: `GrowthChart`
painted at 8.9px/7.6px, `ProjectionFanChart` at 8.1px/4.2px, `MarketHeatmap` at 6.8px
below 1100px. Fixed by making the viewBox track the measured container width
(`src/lib/useElementWidth.js`), so the scale is 1 and px means px. Also recovered 69px
of letterboxed chart height and un-clipped the y-axis labels. `node design/typefloor.mjs`
now reports 0 across 10 routes × 3 widths and exits non-zero on regression — worth
wiring into the `site` CI job.

### Phase 4 — data visualization
Shipped: palette validation for all four palettes, and the correlation heatmap.
Not shipped, with reasons:
- **Bullet charts for `validation/signal_metrics.json`** — the plan assumed
  `value` + numeric `kill_threshold` on a shared scale. In the published data
  `kill_threshold` is prose for 17 of the 23 metrics that have one (e.g.
  "Non-monotonic quantiles are fragile"), only 6 parse numerically, 14 values
  are null, and the 40 metrics span incomparable scales. Drawing it needs a
  pipeline change that publishes a numeric threshold and a comparison basis, or
  a different form. Do not fake the numbers.
- Risk/return scatter (ShadowPortfolios), dot-plot small multiples
  (BacktestComparison), paired bars (LiveValidation), quadrant scatter
  (ResearchScreen), congress volume timeline, macro bullet trio, factor-exposure
  bars, projection fan revival, score-history line in the modal. All have the
  data; none are built.

### Phase 5 — page-by-page pass
Not started. Every page now inherits the new tokens and card system, but the
per-page composition work (hierarchy, one headline number per widget, the shared
screen-page skeleton, real empty states for `InstitutionalActivity`'s permanent
`results: []`) has not been done.

### Smaller items
- **`og:image` and `og:url` are root-relative** in `index.html` because the
  deploy domain is not committed to this repo. Facebook and Twitter want
  absolute URLs — set them once the domain is known.
- **Nine unreachable source files remain** (~2,020 lines): `evidenceStrength`,
  `labelDistribution`, `nightlyRefresh`, `pipelineGuardrails`, `sentimentEngine`,
  `usePortfolio`, `scoreBands` (kept: CLAUDE.md cites its test as the example
  command), plus the two deliberate stubs `fidelityConnectorStub` and
  `securityStub`. Decide keep-or-delete per file.
- **`advisor.json` is 37 MB** and is fetched by Search, Watchlist and Finances.
  Phase 6 item 1 — check whether `report.json` (6.5 MB) covers their fields.
- **`score-history.json` (31 MB) and `diagnostics.json` (4.9 MB)** are committed
  and read by nothing.
