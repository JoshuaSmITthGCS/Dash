# Model Card — ValueSignal Research Score

## What it predicts

The champion score is a cross-sectional rank of companies by evidence quality — fundamentals
(78%), market behavior (18%, includes the new technical_extended factor at ~6% of that
share), and news sentiment (4%, dropped from the denominator when a company has no qualifying
coverage). It is designed as a research-evidence summary, not a validated forecast of forward
returns.

**It is not a probability.** A score of 84 is a rank position, not an 84% chance of anything.
No score bucket has enough closed forward windows to carry an empirical meaning — see
"Validation state".

## What it does not predict

- A specific price target, timing, or magnitude of a future move.
- Short-term (intraday, next-session) price direction.
- Outcomes for a specific holding period — no target horizon is bound to the champion score
  itself (individual sleeves in `pipeline/sleeves/` do declare a `target_horizon_days`, but
  the production composite does not).
- Anything for ETFs — ETFs are scored by a completely separate model
  (`pipeline/fetch_etfs.py`) and are ineligible for every stock sleeve.

## Universe

910 configured symbols (`pipeline/config/advisor_universe.json`), 40 published per refresh.
Eligibility thresholds: $5 minimum price, $300M minimum market cap, $2M minimum 60-day median
dollar volume, 253 minimum trading sessions (`docs/RESEARCH-CONTRACT.md`). No IPO-seasoning
window, no delisted-security replay in scoring.

## Rebalance / refresh assumptions

No fixed rebalance cadence. `refresh-advisor.yml` runs a full sweep once and two fast
refreshes on trading days (07:00, 12:00, 15:00 ET). Signal timestamp is the refresh's own
`generated_at`; there is no same-close-execution guard.

## Data sources and availability lags

Yahoo Finance (price/quote/statements — restated only, no as-reported history), Alpha
Vantage (max 5 symbols/refresh, overview/earnings/macro), Marketaux (news sentiment,
opt-in), FRED (macro regime, opt-in), SEC EDGAR (Form 4 insider, theme signals — needs
`SEC_USER_AGENT`), Financial Modeling Prep and the keyless public House/Senate disclosure
datasets (congressional disclosures, weekly). Statement
data typically lags 1-3 months after fiscal period end. See `docs/DATA-LINEAGE.md`.

## Data coverage

**Correction: this section previously called the published quantity "confidence" and cited a
`pipeline/confidence.py` that does not exist — see `docs/AUDIT-VERIFICATION-RESULTS.md` §6.**
The real file is `pipeline/data_coverage.py`; the scalar and the UI both call it **data
coverage**, not confidence — `advisor_engine.py::data_coverage_scalar()`'s own docstring states
it "was previously published as `confidence`, which invited every consumer to read it as
reliability," and was renamed for that reason. The dial component that renders it
(`src/components/StockDetailModal.jsx`'s `CoverageScoreDial`) likewise states in its own code
comment "the quantity is completeness, not reliability" and its visible label reads
"`{X}%` data coverage" — never "Evidence confidence."

Not a single number: `data_coverage.py::data_coverage_components()` publishes completeness,
freshness, source_reliability, peer_sample, and model_agreement components alongside the scalar.
`historical_calibration` is always `null` — the IC harness has not accumulated enough
prospective periods to report one (see "Validation state"). `score_calibration.py` will
populate it once at least one score band clears 30 closed observations, and refuses to before
then.

Data coverage measures **how much of the intended evidence actually resolved**, never how
reliable the resulting rank is, and never the probability of a price move. A real,
validated-against-realized-error confidence metric does not exist yet in this codebase — its
absence is the correct state until one is built and validated, not an oversight.

## Sector-specific replacement metrics: real vs. declared

`pipeline/config/business_profiles.json` has long named the multiples a bank, REIT, or insurer
should be judged on instead of the suppressed generic set — but for most of those names (e.g.
`combined_ratio`, `net_interest_margin`, `rate_base_growth`), nothing in the pipeline ever
computed a value: they existed only as strings in config and test fixtures, and
`applicability_matrix.json`'s bank/REIT/insurer rows fell back to substituting one already-
computed generic metric for another (`ev_to_ebitda` → `price_to_book`), not to the named
specialist multiple.

Two of those names are now real. `pipeline/fundamentals_extended.py::derive_tangible_returns`
computes **return on tangible common equity** (net income over average tangible book value,
reusing the same goodwill/intangible strip `price_to_tangible_book` already applies) for every
company with the inputs, not just banks. `derive_reit_ffo` computes **FFO and price/FFO**
(Nareit definition: net income plus real-estate D&A, less a disclosed property-sale gain when
the filer breaks that line out — most do not, so the gain add-back is often unavailable rather
than zero). Both are PIT-logged (`pipeline/pit_store.py`) starting from this change.

Both are deliberately **not yet wired into `SCORED_METRICS` or `settings.json`'s weights**.
Round 11's negative result (above) is about per-sector *weight* tuning of the existing metric
set, not about this — but adding a metric with zero prospective history to the live weighted
composite is still an unvalidated scoring change, and "Validation, not backtesting" is a hard
gate in this repository. Promoting either metric into the scored composite needs its own
`ic_harness.py` read once enough PIT history accumulates, exactly like any other scoring change.

The remaining sub-industry *replacement multiples* from the KPI-registry research — MLR for
managed care, distribution coverage for midstream, EV/EBITDAR for airlines, EV/rate-base and
allowed-vs-earned ROE for regulated utilities, EV/AUM for asset managers — are still not
computed as real values. Several (AUM, rate base, RevPAR, dayrates) are disclosed in 8-K
supplementals and MD&A prose rather than tagged in XBRL, so computing them is a
supplemental-parsing project (see "Operating-KPI text extraction" below), not a config change;
see `research/valuesignal-kpi-thematic-methodology.md` for the full registry.

## Sub-industry profiles: the suppression side, fully implemented

Suppression is a separate question from replacement-metric computation, and it is now complete
for the sub-industries the KPI-registry research calls out. `canonical_metrics.py::classify_profile`
gained eight new business profiles this pass — `insurance_broker`, `managed_care_insurer`,
`midstream_mlp`, `airline`, `aerospace_defense`, `capital_markets`, `asset_manager`,
`homebuilder` — plus `independent_power_producer` split out from `utility` (a merchant/IPP
earns nothing like a rate base and was previously indistinguishable from a regulated utility).
Each has real `applicability_matrix.json` suppression rules — `capital_markets` and
`managed_care_insurer` inherit `bank`'s and `property_casualty_insurer`'s rule sets respectively
via the existing `$inherits` mechanism, since both are the same underlying valuation problem
(leveraged-financial and insurer accounting, respectively) with a different label.

One real bug this closed: `"Insurance Brokers"` contains the substring `"insurance"` and was
landing on `diversified_insurer` — a profile that assumes underwriting risk and investment
float a broker never carries. It is now its own profile, checked ahead of the generic insurance
branch (`test_scorer.py::NewSubIndustryProfileTests::test_insurance_broker_no_longer_misrouted_into_diversified_insurer`
is the regression test). A second bug surfaced and was fixed while wiring these in:
`metric_registry.json`'s per-metric `applicability_profiles` declarations are a second,
independent suppression authority (`canonical_metrics.applicability_for` checks both the
`applicability_matrix.json` rule *and* this registry-declared list, and treats a profile
*absent* from either as suppressed) — the eight new profiles were absent from every such list,
which meant nearly the entire generic metric set was silently suppressed for them regardless of
what `applicability_matrix.json` said. All nine lists in `metric_registry.json` now include the
nine new profiles.

The specialized *replacement* multiples for these profiles (EV/AUM, MLR, EV/EBITDAR, distribution
coverage, book-to-bill as a scored input) remain unimplemented for the same data-availability
reason as the paragraph above — `business_profiles.json`'s `replacement_metrics` for these
profiles name the target multiple, same as the pre-existing bank/REIT entries did before this
session, as a documented intent rather than a computed value.

## Every remaining GICS sub-industry gets its own profile

The eight profiles above were the first pass. `classify_profile` now also distinguishes, by
sector:

- **Energy/Materials:** `specialty_chemicals` (formulation/IP-driven chemistry — including
  industrial gases, which have no separate industry code — trades at a stable premium multiple
  `commodity_producer`'s cyclical suppression would misprice), checked ahead of an extended
  `commodity_producer` match that now also catches mining, steel, coal, uranium, aluminum,
  paper, packaging, and agricultural inputs/fertilizer.
- **Industrials:** `machinery`, `electrical_equipment`, `building_products`,
  `engineering_construction`, `railroad`, `trucking`, `air_freight_logistics`,
  `marine_shipping`, `waste_management`, `staffing`, `consulting_services`,
  `industrial_distribution`.
- **Healthcare:** `large_cap_pharma`, `medical_devices`, `life_science_tools_diagnostics`,
  `pharmacy_healthcare_distribution`, `healthcare_it` — each checked ahead of the
  biotech/pre-profit fallback, which previously swallowed any of these that happened to be
  unprofitable into `other_pre_profit`.
- **Utilities:** `renewable_yieldco_developer` (CAFD/tax-equity economics — accelerated
  depreciation, non-cash HLBV allocations — a different problem from `independent_power_producer`'s
  merchant commodity exposure, not a generalization of it) and `water_utility`.
- **Financials:** `reinsurer` (large, lumpy per-event catastrophe losses, no direct
  policyholder relationship — inherits `property_casualty_insurer`), `financial_exchange`
  (fee/data revenue, no balance-sheet risk — inherits `capital_markets`), `consumer_finance`
  (revolving-receivable/charge-off economics, `"Credit Services"` in Yahoo's taxonomy — inherits
  `bank`), and `payment_processor` — ticker-override only (V, MA, PYPL, FI, GPN, FIS, WEX, EEFT),
  since Yahoo files card networks under the same `"Credit Services"` string as `consumer_finance`
  despite them carrying no consumer credit risk. AXP is deliberately left classified as
  `consumer_finance`: unlike the payment networks, it does carry cardmember-loan credit risk.
- **Technology:** `semiconductor_capital_equipment` (bookings/litho-cycle timing, not wafer
  volume — checked ahead of the generic `semiconductor` match, inherits its rules),
  `ems_electronic_components`, `networking_equipment`, `it_services_consulting`, and — the
  single largest gap this closed — **`saas`**, which previously had *no* profile treatment at
  all and, when unprofitable, was falling into `other_pre_profit` (built around biotech/early-
  stage burn economics, not deferred-revenue subscription economics). Both `saas` and
  `it_services_consulting` are checked ahead of that fallback.
- **Communication Services / Consumer Discretionary / Consumer Staples:** `telecom_carrier`,
  `media_entertainment`, `interactive_media_platform`, `video_games`, `publishing_advertising`,
  `retail_apparel`, `restaurants`, `ecommerce_retail`, `automaker`, `auto_dealership`,
  `auto_parts_supplier`, `leisure_products`, `education_services`, `agricultural_processor`,
  `packaged_food_processor`, `beverage_manufacturer`, `tobacco`, `food_distributor`,
  `grocery_staples_retail`.
- **Real estate:** the flat `reit` match is now a sub-dispatch — `office_reit`, `retail_reit`,
  `industrial_reit`, `residential_reit`, `healthcare_reit`, `hotel_reit`, and `mortgage_reit`
  resolve from the industry-text property type; `self_storage_reit`, `data_center_reit`,
  `net_lease_reit`, and `timber_reit` have no distinguishing industry string in Yahoo's taxonomy
  (all share `"REIT - Industrial"`/`"REIT - Specialty"`/`"REIT - Diversified"` with other
  subtypes) and are resolved exclusively via `ticker_overrides` — PSA/CUBE/EXR, DLR/EQIX,
  O/NNN/WPC, and RYN/WY/PCH respectively. Anything left unmatched (`"REIT - Diversified"`,
  `"REIT - Specialty"`) still falls back to the generic `reit` profile it always has. All ten
  subtypes currently `$inherits: reit` — no subtype-specific replacement metric exists yet, so
  this is the identification/routing groundwork the profile split enables, not new formulas.

None of these 58 profiles compute a new sector-specific metric of their own (with the narrow
exception of `capex_intensity`/`operating_ratio_proxy`/`gross_margin_trend`/
`inventory_correction_flag` above, which several list as `replacement_metrics` because they are
genuinely diagnostic for that profile's economics, not because a new formula was written for
it). What changes is suppression precision and identification: each is wired through all three
applicability authorities exactly like the original eight (`business_profiles.json`,
`applicability_matrix.json` — `$inherits` where the economics genuinely match an existing
profile, an explicit empty rule set where none of the generic suppressions apply, e.g.
`specialty_chemicals` — and every one of `metric_registry.json`'s nine `applicability_profiles`
allow-lists, to avoid recreating the omission bug from the previous section).
`RemainingSubIndustryProfileRoutingTests` in `pipeline/tests/test_scorer.py` is the regression
coverage: a routing table for all 58, the REIT/payment-processor ticker-override resolutions,
and a `return_on_equity` applicability probe across the whole set guarding against the
registry-omission bug class recurring.

**A real second-order effect this surfaced:** splitting a ~910-name universe across roughly 68
total profiles pushes most profile-specific peer groups below the n≥30 sample `peer_groups.py`
requires before publishing a valuation-tier claim (see "Validation, not backtesting" — the same
"a degraded estimate is worse than an absent one" reasoning that governs the THG false-precision
regression this module was built to prevent). Left unaddressed, that would have silenced peer
comparison for the majority of the universe. `peer_group()` now rolls a too-thin
profile-specific group up to its broader GICS-sector bucket for peer-*comparison* purposes only
— `classify_profile()` still governs which *metrics* apply to a name exactly as described above
— except for the seven profiles the THG audit was originally built around (`bank`,
`property_casualty_insurer`, `life_insurer`, `diversified_insurer`, `reit`, `utility`,
`commodity_producer`), which still go silent below the minimum rather than roll up into a
broader "Financial Services" or "Real Estate" bucket that would reintroduce exactly the
category error that audit exists to prevent.

## Thematic exposure: disclosure over narrative

Every `pipeline/themes/*.yaml` signal block previously weighted `filing_keyword_density_trend`
(10-K language, an NLP signal) at 0.35–0.40 — usually the single largest signal — against
`segment_revenue_share` (ASC 280 disclosed segment revenue) at 0.15–0.25. That is the inverse of
how index providers resolve thematic exposure: MSCI, FactSet RBICS and S&P Kensho all resolve to
a disclosed revenue-share number first and treat text as a corroborating, discretionary layer.

All 11 theme files now weight `segment_revenue_share` (and, where declared,
`customer_concentration_to_spenders`, the ≥10%-customer disclosure rule) as the dominant
signal, with `filing_keyword_density_trend`/`transcript_theme_salience` cut to 0.05–0.10 —
a tie-breaker, not the deciding vote. `pipeline/themes.py::score_theme_exposure` also now
applies `UNDISCLOSED_EXPOSURE_DISCOUNT` (0.85×) to the exposure score itself — not just to the
already-existing `confidence` figure — whenever no `DISCLOSURE_SIGNALS` member resolved for a
company, so a name that clears `min_signals_required` on filing/transcript language and a
theme-wide capex reading alone scores lower than an otherwise-identical name with real segment
revenue or customer-concentration evidence behind it. The row's `disclosure_backed` field and
`explain_exposure()` clause make this visible per company.

## Momentum-free "priced in" read: market-implied growth

`pipeline/reverse_dcf.py` adds a first, deliberately simplified version of the Mauboussin &
Rappaport reverse-DCF: instead of forecasting a fair value and comparing it to price, it solves
the single-stage perpetuity `EV = FCF*(1+g)/(WACC-g)` for the growth rate `g` the current
enterprise value already assumes, using a CAPM cost of equity (beta already computed by
`fundamentals_extended.py`) blended with an after-tax cost of debt into WACC. Every rate that
isn't computed per company — risk-free rate, equity risk premium, cost of debt — is a declared
assumption in `settings.json`'s `reverse_dcf` block, the same "labeled, not measured" honesty
`pipeline/costs.py` applies to its spread proxy: get the assumption wrong and every company's
implied growth shifts by roughly the same amount, so this is a comparable cross-sectional read,
not a precise per-company forecast. It is a single-stage approximation, not the full multi-stage
model with an explicit forecast horizon and competitive-advantage-period estimate the source
research describes — a real fidelity gap, not a rounding detail, and it uses zero momentum or
price-history input either way.

`market_implied_growth`, `market_implied_growth_wacc`, and `market_implied_growth_exceeds_ceiling`
are informational fields (PIT-logged from this change), not part of the scored composite, for
the same reason ROTCE and FFO are not yet: a brand-new signal has no prospective IC history to
validate against.

## Momentum-free "priced in" read: multiple-expansion decomposition

`pipeline/return_attribution.py` adds the other half of the source research's "priced in"
toolkit: splitting a company's realized return over a trailing window into re-rating (multiple
change) and delivery (implied fundamental growth). It uses the identity
`Price = Multiple x Fundamental`, so `price_now/price_then = (multiple_now/multiple_then) x
(fundamental_now/fundamental_then)` — solving that for the second factor gives the fundamental
growth implied by the re-rating the market actually applied, without ever needing the
fundamental (EPS, FFO, ARR) itself. Only two archived point-in-time series per ticker are
needed — price and one valuation multiple (`forward_pe` generally, `price_to_ffo` for REITs) —
both of which `pipeline/pit_store.py` already logs every run.

This is a return-*attribution* read, explaining a realized move after the fact, not a forward
momentum signal: it is never wired into `pipeline/themes.py`'s per-company exposure scoring,
where a price-derived signal is rejected outright by `validate_theme()`. `row.return_attribution`
(`total_return`, `multiple_change`, `delivery_growth`, `mostly_re_rating`) is informational only,
reading `None` until `pit_store` has accumulated at least `settings.json`'s
`return_attribution.months_back` (12) of history for a given ticker — like every other
new field here, it has no prospective IC history yet, so it is not a score input.

## Theme maturity and crowding: return dispersion and pairwise correlation

`pipeline/theme_trend.py` already computed a theme-level "is this actually moving, and is it
already priced" read (direction, breadth, leadership concentration, and a valuation-percentile
`crowding` reading) — architecture this session did not build, kept rigidly separate from
`themes.py`'s per-company exposure scoring so a price-derived group statistic can never leak
into an individual company's score. What that module did not yet compute was the two signals
the source research's maturity section specifically calls for: **return dispersion** (do
members' returns still differ, or is everything moving together) and **pairwise correlation**
(the more direct co-movement read). Both are now in `theme_trend.py::maturity_reading`, called
from `evaluate_theme()` and published as the trend block's new `maturity` key:

- `return_dispersion` — population stdev of members' `relative_strength` (already computed per
  member for the existing `direction`/`breadth` readings; no new data).
- `average_pairwise_correlation` — mean pairwise Pearson correlation of members' trailing
  60-trading-day daily returns, computed from the same `history.closes` series `theme_trend.py`
  already reads for its moving-average checks. Degrades to `None` below `MINIMUM_MATURITY_MEMBERS`
  (5) or when a member's price history is too short (30 of the requested 60 days minimum).
- `label` — `"crowded"` (correlation ≥ 0.60), `"differentiated"` (≤ 0.25), or `"broadening"`
  in between; stated bands, not fitted parameters, on the same principle as this module's
  existing `CROWDED_EXPENSIVENESS` convention.

Not implemented from the same maturity section: supplier/theme-wide book-to-bill as an explicit
crowding signal (the `backlog_growth` theme-exposure signal already exists per company but isn't
aggregated as a maturity read) and a thematic-ETF-launch counter-signal (no launch-date dataset
exists in this pipeline).

## Validating new metrics: a candidate-metric IC harness

`pipeline/validation/ic_harness.py` only grades the live composite score's forward-return IC —
`_metric_scores()` reads its candidate list from `settings.json`'s `fundamentals.metric_weights`,
so a metric that isn't scored (every new field this pass added) was simply invisible to it. That
was a real gap: this repository's own rule is that a scoring change ships only if it improves
out-of-sample IC after deflation, but there was no way to *measure* that IC for something not
already in the score — a chicken-and-egg the "informational field, promoted only after
validation" pattern above depends on actually being resolvable someday.

New `pipeline/validation/candidate_metric_ic.py` closes that gap: the same rank-IC/ICIR
statistics as `ic_harness.py` (it reuses that module's `_ic_summary` directly), computed instead
from raw `pit_store` observation history for any two fields — a candidate metric and price — so
it needs no live score at all. A period is scored only from tickers actually observed at that
exact date, so a stale reading is never silently reused across periods a name wasn't refreshed
in. Run it directly: `python pipeline/validation/candidate_metric_ic.py --metric
return_on_tangible_common_equity`.

Run against this repository's real committed `pit_store` data, every candidate (`return_on_
tangible_common_equity`, `price_to_ffo`, `gross_margin_trend`, `market_implied_growth`) reports
**0 periods, accumulating** — expected and correct, since these fields were only added this
pass and have no history yet. This is the harness that will answer the promotion question once
enough pipeline runs have accumulated PIT history for them; it does not answer it today, and
this pass makes no promotion claim for any of them.

## Gross margin trend and the inventory correction flag

Two smaller additions from the companion semis/SaaS/hardware worked-examples research (Micron,
Datadog, Dell): `fundamentals_extended.py::derive_margins` now computes `gross_margin_trend`
(this year's gross margin less last year's, the same construction as the existing
`operating_margin_trend`) — the semiconductor gross-margin bridge that research calls the single
most decision-relevant semis read is, at minimum, now a real level-and-direction number rather
than absent. `derive_working_capital_trends` now also emits `inventory_correction_flag`
(`"lean"` / `"normal"` / `"elevated"`), a heuristic on the year-over-year drift in
`inventory_days_trend` (≤ -10% lean, ≥ +15% elevated) rather than the absolute day count, since
what counts as lean inventory is sector-relative (120 days is lean for a memory chipmaker
mid-shortage, elevated for a grocer) and this pipeline has no sector-relative inventory-days
percentile built. Both are PIT-logged; both are informational, same reasoning as everything
above. `derive_capital_allocation` now also computes `capex_intensity` (capex/revenue), and
`derive_margins` computes `operating_ratio_proxy` (1 − operating margin) — both zero-new-data
reads used as the generic `replacement_metrics` entry for several of the newer sub-industry
profiles below where no sector-specific KPI exists yet (see next section). A semiconductor
cycle-stage tag (trough/peak-margin/correction) from the same research is not implemented.

## Operating-KPI text extraction (off by default)

A follow-on research pass (`research/valuesignal-remaining-sectors-kpi-research.md`) made the
same data-gap finding as above its own headline conclusion: same-store sales, net
interest margin, ARPU, FFO/AFFO, rate base, and nearly every other sub-industry operating KPI
across all nine remaining GICS sectors live in 8-K Exhibit 99.x earnings-release tables and
10-Q/10-K MD&A prose, not standardized XBRL — the SEC's own guidance treats "same-store sales
calculated from GAAP revenues" as an MD&A disclosure, not a tagged financial-statement fact.

`pipeline/filing_extraction.py` locates a company's Exhibit 99.x documents (reusing
`SecEdgarClient.filing_index`/`filing_document`, already built for Form 4 and XBRL work),
flattens the HTML into lines (one per table row or paragraph, so a label and its value stay on
the same line), and regex-matches a metric registry now covering every sub-industry the source
research names: same-store/comparable sales (retail, restaurants), net interest margin and
efficiency ratio (banks), ARPU and postpaid churn (telecom), AUM/net-flows/fee-rate (capital
markets and asset managers), same-store NOI/occupancy/leasing spread (REITs), book-to-bill and
backlog (aerospace & defense, semiconductors), net revenue retention (SaaS), capacity
utilization (semiconductors, chemicals/metals/paper, independent power producers), rate-base
growth and allowed ROE (regulated utilities), and capacity factor (independent power
producers). A company is routed to its subset by `filing_extraction_group()` — sector/industry
text matching kept deliberately independent of `canonical_metrics.classify_profile`, so this
routing can't perturb the live scored composite. Every reading carries `"unaudited": True` and
surfaces only as a display field (`row.filing_extracted_metrics`) — never a score input,
matching how reverse_dcf and the new sector metrics above are handled.

**This has not been validated against a single live SEC EDGAR fetch.** It was written in a
sandboxed session whose outbound network policy blocked `sec.gov` outright (a proxy-level 403,
not a timeout), so every extraction pattern was checked only against synthetic HTML fixtures
built from the known structure of real earnings releases — see
`pipeline/tests/test_filing_extraction.py` and the module's own docstring. (One real bug this
already caught: two label patterns used a bare `a|b` alternation instead of `(?:a|b)`, so the
label alone silently satisfied the whole compiled pattern with the value groups all `None` —
fixed, and now covered by a regression test, but it's a concrete example of the class of
mistake that only surfaces against a real filing's actual phrasing, not a hand-written
fixture.) `settings.json`'s `filing_extraction.enabled` defaults to `false` for exactly this
reason; flipping it on should wait until a session with real SEC EDGAR access confirms
extraction accuracy against actual filings and checks the configured `minimum_coverage` (0.8)
is actually cleared per metric.

## Validation state

**No signal has been promoted.** The IC harness has observed 0 of the 24 eligible periods
`minimum_icir_periods` requires. No IC, Sharpe, drawdown, or hit-rate statistic reported
anywhere in this repository should be read as a validated result.

**What has been measured**, from a survivorship-biased five-year backtest that uses
approximated filing timestamps and raw rather than sector-residual returns. The current
numbers come from `pipeline/reports/{factor_regression_p0,benchmark_alpha_regressions,strategy_diagnostics}.json`:

- Six-factor regression (Newey-West, 57 months): annualized alpha **+3.06%, |t| = 0.680**,
  still statistically indistinguishable from zero. Significant loadings are market (8.32),
  size (3.85) and momentum (2.92) — not the value and
  profitability the score is mostly built from.
- Against 14 tradeable style/size ETF legs: all are beaten on CAGR and six smaller-cap or
  breadth benchmarks are beaten with significant positive alpha. Alpha remains insignificant
  against SPY, VTV, and the fixed IJH/IWD blend, while the six-factor residual above remains
  insignificant.
- Regime-dependent: **+11.1pp** annualized against SPY in bear markets, **+9.6pp** in falling
  rates, and **−6.7pp** in rising rates.

**The score's predictive sign is itself regime-dependent** (Round 11 regime diagnosis,
`pipeline/regime_diagnosis.py`, results in `research/audit/round11/regime_diagnosis.json`):
on the 10-year monthly backtest panel (2016–2026, 119 resolved periods), the champion
composite's mean monthly rank IC breaks at **2021-03** — **−0.023 before, +0.038 after**
(Welch t = 3.221; permutation p = 0.019, computed against the maximum statistic over every
candidate breakpoint, so scanning for the break is priced into the p-value). The break sits
47 months from the computed Yahoo-native/EDGAR statement-source boundary, so it is market
history, not a data-construction artifact. Concretely: the score **anti-predicted through
2018–2020** (yearly hit rates 25–42%) and has been positive every year since 2021. Any
forward-looking read of the score's usefulness is therefore conditional on the post-2021
regime persisting; nothing in this repository demonstrates the score works across regimes.
A rolling 12-period IC monitor (`rolling_ic_regime` in
`public/data/validation/signal_metrics.json`) exists so a future sign flip surfaces in the
published artifacts within months rather than in a later backtest.

Round 11 also settled the per-sector weighting question negatively: two 500-candidate-per-
sector searches (full universe and a growth/quality-filtered universe), graded out-of-sample
under pre-registered gates, found **0 of 11 sectors** where any sector-specific weighting
beat the uniform champion weights (`research/audit/round11/harness_run_results.json`,
`sector_search_growth_quality.json`).

**Current classification: B — a transparent factor tilt with no demonstrated residual alpha**,
carrying a real Verdict D caveat because the contract's own target has never been measured.
Do not present SPY outperformance as this model's objective.

The forecast target is now implemented as specified: 63 **trading sessions**, sector-residual,
preregistered as primary. Deflation uses the honest trial count (51 variants across 14
experiments, `pipeline/reports/experiment_registry.json`), not the 5 configured shadow
strategies.

## Transaction costs

`pipeline/costs.py` models `half_spread + fees + volatility_scaled_impact` across three
scenarios, with a labeled (not measured) spread proxy — see `docs/TRANSACTION-COSTS.md`. Wired
into both `backtest_monthly.py` and `ic_harness.py` behind `validation.cost_model`, defaulting
to the original flat 10bps so prior results reproduce exactly.

At the realized 50.8% mean monthly turnover, the published flat 10bps path costs an estimated
**61bps a year**, or 3.5% of implied gross annualized return. The flat-rate stress scenario is
25bps; full per-name tiered reruns are reproducible from the committed cache but remain separate
experiments (`pipeline/reports/cost_sensitivity.json`).

## Known limitations

See `docs/LIMITATIONS.md` for the full list. Headline items: no empirical score calibration,
no residual alpha demonstrated after factor controls, statement-derived metrics computed only
for a shortlist (no unenriched name reaches the top 100 —
`docs/ENRICHMENT-BIAS-ANALYSIS.md`), only 1 of 6 portfolio-construction methods built, 9 of 16
screen presets are specification-only.

## Promotion status

**Champion:** `bands_champion` (sector/industry-band fundamental scoring,
`advisor_engine.py`), in production.

**Challengers**, all shadow-only, published in `score_variants` alongside the champion but
never selected: `cross_sectional_normalization`, and the `signal_corrections` family
(`normalization`, `short_horizon`, `confidence_shrinkage`, `modifier_recalibration`,
cumulative). None have passed the promotion gates in `docs/RESEARCH-CONTRACT.md` — none have
been evaluated against them, because the IC harness has not reached minimum history.
