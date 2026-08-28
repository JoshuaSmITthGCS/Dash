# Data Sources, Sub-Industry Taxonomy, Screens & Ranking Methods

A consolidated reference for three questions `docs/MASTER-METHODOLOGY.md` answers but does not
gather in one place: **every data source** this app draws on (including the sub-industry
taxonomy that decides which metrics apply to which company), **how every screen is built and
organized** (with the data shape/type backing each one), and **every ranking or sorting method**
that orders a list anywhere in the app — the research score's own weight tree plus the ten
client-side ranking lenses and every screen-specific composite score, none of which live in one
document today.

This file does not supersede `docs/MASTER-METHODOLOGY.md` (the deeper, line-cited reference for
every formula) or `docs/MODEL-CARD.md` (the changelog of what was added, why, and what remains
unvalidated) — it reorganizes and completes the material from both around the three questions
above, with file:line citations so every claim can be re-verified against the code that produces
it. Where a fact is already fully derived in one of those documents, this file cites the section
rather than re-deriving it.

No score described here is a probability, a price target, or investment advice — see
`docs/LIMITATIONS.md` and `docs/VALIDATION-METHODOLOGY.md` before treating any number as
predictive.

---

## Table of contents

1. [Every data source](#1-every-data-source)
2. [Point-in-time stores](#2-point-in-time-stores)
3. [The sub-industry taxonomy](#3-the-sub-industry-taxonomy)
4. [Screens — how they're built and organized, and their data types](#4-screens--how-theyre-built-and-organized-and-their-data-types)
5. [The research score — every sorting method, and how each is made](#5-the-research-score--every-sorting-method-and-how-each-is-made)
6. [Every other ranking/sorting method in the app](#6-every-other-rankingsorting-method-in-the-app)
7. [Where this is published in the app](#7-where-this-is-published-in-the-app)

---

## 1. Every data source

| Provider | What it supplies | Key required | Status / cadence |
|---|---|---|---|
| **Yahoo Finance** (`yfinance`) | Price/quote history, financial statements, analyst estimate revisions (EPS revision counts, EPS trend, upgrade/downgrade history, price targets — `pipeline/yahoo_estimates.py`), per-symbol company news (`pipeline/yahoo_news.py`) | none | Primary provider for price and statements; restated only — no as-reported (as-originally-filed) history |
| **SEC EDGAR** | Form 4 insider transactions (feeds the insider-activity modifier, §5), XBRL theme signals, canonical fundamentals fallback, and — via the filings tracker — DEF 14A/DEFC14A/DEFA14A proxy tracking, 8-K item-code materiality, and 10-K/10-Q/NT 10-K/NT 10-Q late-filing tracking (`pipeline/build_filings_screen.py`, `pipeline/edgar_filing_signals.py`), all read from the submissions API (`data.sec.gov/submissions/CIK{cik}.json`) already used for Form 4 | `SEC_USER_AGENT` header (SEC fair-access policy) | Free; a `preferred_providers` source for statement metrics (`sec_xbrl`), the insider-trading feed, and (every 3 days) the filings tracker |
| **Alpha Vantage** | Company overview, earnings, forward estimates, macro | `ALPHA_VANTAGE_API_KEY` | Max 5 symbols per refresh (quota-limited) |
| **Marketaux** | Entity-level news sentiment | `MARKETAUX_API_TOKEN` | Optional — feeds the 4%-weight news sentiment component (§5.3) |
| **FRED** (Federal Reserve Economic Data) | Macro regime: rates, inflation, labor, yield curve (6 series feed the macro-regime modifier), plus VIX-derived volatility (published informationally, not yet in the modifier) | `FRED_API_KEY` | Optional — feeds the MarketPulse backdrop and the macro-regime modifier (§5.4) |
| **Marketstack** (apilayer) | Premarket/intraday and end-of-day price bars for the top-100 published tickers; re-sorts the Stocks (movers) and Reversal screens from accumulated closes (`pipeline/marketstack.py`, `pipeline/collect_marketstack.py`, `pipeline/resort_marketstack_screens.py`) | `MARKETSTACK_API_KEY` | Optional — two batched runs/day; falls back from intraday to `eod_latest` on plan restriction; the Reversal screen reports "accumulating" until 60 sessions are collected |
| **Financial Modeling Prep** | Congressional STOCK Act disclosures (Senate/House "latest" endpoints), "since purchase" price history on the Congress trades screen | Plan covering Congressional endpoints (HTTP 402 without it) | Weekly; the screen still builds without this key via the keyless fallbacks below |
| **Senate eFD** | Senate STOCK Act disclosures, direct from the Senate's own system | none (keyless) | Weekly |
| **House/Senate stock-watcher datasets** | Third-party mirrors of Congressional disclosures. House defaults to a live mirror (`kadoa-org/congress-trading-monitor`); the Senate mirror is withdrawn (HTTP 403) but immaterial since Senate eFD covers that side directly. Overridable via `CONGRESS_HOUSE_DATASET_URL` / `CONGRESS_SENATE_DATASET_URL` | none | Weekly |
| **OpenFIGI** | CUSIP → ticker mapping for 13F institutional holdings | `OPENFIGI_API_KEY` (optional; without it, 10 CUSIPs per request instead of 100) | Monthly |

**Provider preference order for canonical statement metrics**
(`pipeline/config/metric_registry.json`'s `declaration_defaults.preferred_providers`):
`sec_xbrl` → `alpha_vantage` → `yahoo`. Individual metrics can override this — forward-looking
metrics (`forward_pe`, PEG) prefer `alpha_vantage`/`yahoo` directly, since SEC filings carry no
consensus estimates.

**Availability lag:** statement-derived metrics typically resolve 1–3 months after fiscal
period end (provider-restated, not as-filed); price/quote data resolves same-session;
Congressional disclosures can lag up to 45 days (screens rank on *disclosure* date, never
transaction date, for this reason); 13F institutional filings disclose up to 45 days after
quarter-end, and the `institutional_13f` modifier treats a filing older than 135 days as fully
stale.

**Corporate actions:** handled entirely at the provider layer via Yahoo-adjusted price series —
no independent corporate-action event log exists in this pipeline.

See `docs/MASTER-METHODOLOGY.md` §1 for the fully line-cited version of this table, including the
note that `pipeline/providers.py`'s `REGISTRY` is a narrower ports/adapters abstraction (only
`yahoo`, `alpha_vantage`, `sec_edgar`, `fake`) and is not itself the authoritative provider list —
this table is.

---

## 2. Point-in-time stores

Three separate append-only stores, all committed to the repository rather than gitignored — the
scheduled runner is ephemeral and providers only ever serve today's restated numbers, so history
only exists if every run appends to it:

1. **Raw fundamentals PIT** — `pipeline/data/pit/observations.jsonl`, `revisions.jsonl`,
   `universe.jsonl`. Every observed value, its source, and observation timestamp; a restatement
   log; a universe-membership log (survivorship defense). `as_of()` never returns a value
   observed after a given cutoff.
2. **Scored validation PIT** — `pipeline/pit_store/YYYY-MM-DD.jsonl`. One immutable row per
   (refresh, ticker): champion + challenger scores, `config_hash`, realized forward returns once
   the horizon elapses. This is what feeds §5's validation harness.
3. **Shadow portfolios** — `pipeline/shadow_store/{strategy}/YYYY-MM-DD-<sha12>.json`.
   Content-addressed; refuses a duplicate snapshot for the same strategy/date.

Every observation carries `observed_at`, `observation_date`, `source`; scored rows additionally
carry `recorded_at`, `data_as_of`, `model_version`, `config_hash`, `universe_membership`,
`published_research` (bool), `quality_flags`.

---

## 3. The sub-industry taxonomy

Two different questions get one answer each from this taxonomy: **which metrics apply to a
company at all** (a bank has no EV/EBITDA; a REIT's P/E is close to meaningless), and **which
peer group a company's valuation is ranked against**. Both are resolved from the same starting
classification but diverge downstream — see "Peer grouping" below.

### 3.1 How a company is classified — `classify_profile()`

`pipeline/canonical_metrics.py:95-322`, called on every scored snapshot. It is an ordered,
first-match text classifier over `sector`/`industry` strings (mostly sourced from Yahoo's
taxonomy), checked in a specific sequence because several sub-industry strings are substrings of
a broader, wrongly-generic match (`"Insurance Brokers"` contains `"insurance"`; `"Oil & Gas
Midstream"` contains `"gas"`) — every such case is commented in the source with the specific
misroute it exists to prevent, and each is checked *ahead of* the generic branch it would
otherwise fall into.

1. **Ticker override first.** `pipeline/config/business_profiles.json`'s `ticker_overrides` map
   (checked before any text match) resolves names Yahoo's taxonomy cannot distinguish by industry
   string alone — most REIT subtypes (self-storage, data-center, net-lease, timber all share
   `"REIT - Industrial"`/`"REIT - Specialty"`/`"REIT - Diversified"` with other property types)
   and payment networks (Visa, Mastercard, PayPal, Fiserv, Global Payments, Fidelity National
   Information Services, WEX, EEFT are all filed under the same `"Credit Services"` string as
   ordinary consumer lenders, despite carrying no consumer credit risk — American Express is
   deliberately left classified as `consumer_finance`, since unlike the networks it *does* carry
   cardmember-loan credit risk).
2. **ETF check.** `is_etf` routes to the `etf` profile, which is scored by an entirely separate
   model (§6).
3. **Ordered text matches**, each a flat substring/keyword test against `f"{sector} {industry}"`
   or `industry` alone, falling through to the next branch on no match. The final fallback is
   `pre_profit_biotechnology` / `profitable_biotechnology` / `other_pre_profit` (unprofitable,
   non-biotech names with no more specific match) or, last, `general`.

### 3.2 The full profile list — 79 sub-industry profiles, plus `general` and `etf`

`pipeline/config/business_profiles.json`'s `profiles` map declares 81 entries; each carries a
`replacement_metrics` list (the specialized multiples that sub-industry's research calls for —
several are declared intent rather than a computed value today, see §3.3) and, where its
economics genuinely match an existing profile, an `$inherits` reference into
`pipeline/config/applicability_matrix.json` rather than a duplicated rule set.

| Sector (GICS-style) | Profiles | Routing notes |
|---|---|---|
| **Real estate** | `reit` (generic fallback), `residential_reit`, `office_reit`, `retail_reit`, `healthcare_reit`, `hotel_reit`, `mortgage_reit`, `industrial_reit`, `self_storage_reit`, `data_center_reit`, `net_lease_reit`, `timber_reit` | The first seven resolve from industry-text property type (`"residential"`, `"office"`, `"hotel"`/`"motel"`/`"lodging"`, etc.); the last four have no distinguishing industry string and resolve exclusively via `ticker_overrides` (PSA/CUBE/EXR, DLR/EQIX, O/NNN/WPC, RYN/WY/PCH respectively). All twelve currently `$inherits: reit` — the split is identification/routing groundwork, not yet a new formula per subtype. |
| **Banks & diversified financials** | `bank`, `capital_markets`, `asset_manager`, `financial_exchange`, `consumer_finance`, `payment_processor` | `capital_markets` (`"Capital Markets"`/`"Investment Banking"`) and `financial_exchange` (`"Financial Data & Stock Exchanges"`, fee/data revenue with no balance-sheet risk) both `$inherits: bank`-style rules. `consumer_finance` (`"Credit Services"`, revolving-receivable/charge-off economics) also inherits `bank`. `payment_processor` is ticker-override only (see 3.1). |
| **Insurance** | `property_casualty_insurer`, `life_insurer`, `diversified_insurer` (generic fallback), `insurance_broker`, `managed_care_insurer`, `reinsurer` | `insurance_broker` (`"broker"` + `"insurance"`) is checked ahead of the generic insurance branch — it earns commission/fee income and carries no underwriting risk or investment float, unlike a diversified insurer. `managed_care_insurer` (`"healthcare plan"` / `"managed care"` / `"health insurance"`) is also checked first. `reinsurer` (`"reinsurance"` in industry) inherits `property_casualty_insurer`'s catastrophe-exposure rules — large, lumpy per-event losses, no direct policyholder relationship. |
| **Utilities** | `utility` (generic fallback), `independent_power_producer`, `renewable_yieldco_developer`, `water_utility` | `independent_power_producer` (`"independent power"`/`"power producer"`) is checked first — a merchant/IPP earns nothing like a rate base. `renewable_yieldco_developer` (CAFD/tax-equity economics: accelerated depreciation, non-cash HLBV allocations) is a different problem, not a generalization of IPP. `water_utility` trades at a persistent scarcity/ESG premium the regulated-electric bands weren't calibrated for. |
| **Energy / Materials** | `commodity_producer` (generic fallback — oil, gas, mining, gold, copper, steel, coal, uranium, chemical, aluminum, paper, packaging, agricultural inputs, fertilizer), `midstream_mlp`, `specialty_chemicals` | `midstream_mlp` (`"midstream"`/`"pipeline"`) is checked ahead of the commodity match — a tolling business, not upstream production economics. `specialty_chemicals` (`"specialty chemical"`, plus industrial gases with no separate industry code) is checked ahead too — formulation/IP-driven chemistry trades at a stable premium multiple that `commodity_producer`'s cyclical suppression would misprice. A handful of names that classify as `specialty_chemicals` by industry string but trade like true commodity producers (e.g. lithium converters) are corrected via `ticker_overrides` rather than a fabricated distinguishing substring. |
| **Industrials** | `airline`, `aerospace_defense`, `machinery`, `electrical_equipment`, `building_products`, `engineering_construction`, `railroad`, `trucking`, `air_freight_logistics`, `marine_shipping`, `waste_management`, `staffing`, `consulting_services`, `industrial_distribution` | Each a flat, mutually-exclusive compound industry-string match, checked ahead of any commodity/airline/aerospace term already resolved above. |
| **Technology** | `semiconductor_capital_equipment`, `semiconductor` (generic fallback for the sector), `ems_electronic_components`, `networking_equipment`, `saas`, `it_services_consulting` | `semiconductor_capital_equipment` (`"semiconductor equipment"`/`"semiconductor materials"`, bookings/litho-cycle timing rather than wafer volume) is checked ahead of the generic `semiconductor` match and inherits its cyclical capex/inventory suppression rules. `saas` (`"software - application"`/`"software - infrastructure"`) was, before this profile existed, falling into `other_pre_profit` (built around biotech burn economics) when unprofitable — now checked ahead of that fallback. A proposed `cloud_infrastructure_provider` ticker-override profile was deliberately **not** added without a confirmed covered-ticker list; those names still classify as `saas` or `general`. |
| **Healthcare** | `large_cap_pharma`, `medical_devices`, `life_science_tools_diagnostics`, `pharmacy_healthcare_distribution`, `healthcare_it` | Each checked ahead of the biotech/pre-profit fallback, which previously swallowed any of these into `other_pre_profit` when unprofitable. |
| **Communication Services / Consumer Discretionary / Consumer Staples** | `telecom_carrier`, `media_entertainment`, `interactive_media_platform`, `video_games`, `publishing_advertising`, `retail_apparel`, `restaurants`, `ecommerce_retail`, `automaker`, `auto_dealership`, `auto_parts_supplier`, `leisure_products`, `education_services`, `homebuilder`, `agricultural_processor`, `packaged_food_processor`, `beverage_manufacturer`, `tobacco`, `food_distributor`, `grocery_staples_retail` | Each a flat industry-string match, checked ahead of the biotech/pre-profit fallback and `general` so none silently default into either. |
| **Pre-profit / unclassified fallback** | `pre_profit_biotechnology`, `profitable_biotechnology`, `other_pre_profit`, `general` | `pre_profit_biotechnology` requires both a negative profit margin *and* `"biotech"` in the sector/industry text; `other_pre_profit` catches any other unprofitable name that matched nothing more specific above; `general` is the terminal fallback (roughly a third of the ~910-name universe). |

This is the full 79-profile list (81 minus `general` and `etf`); the eight-profile first pass
(`insurance_broker`, `managed_care_insurer`, `midstream_mlp`, `airline`, `aerospace_defense`,
`capital_markets`, `asset_manager`, `homebuilder`, plus `independent_power_producer` split out of
`utility`) and the ~58 that followed to cover every remaining GICS sub-industry are both
documented, with the specific misclassification bug each one fixed, in `docs/MODEL-CARD.md`
("Sub-industry profiles: the suppression side, fully implemented" and "Every remaining GICS
sub-industry gets its own profile"). `pipeline/tests/test_scorer.py`'s
`NewSubIndustryProfileTests` and `RemainingSubIndustryProfileRoutingTests` are the regression
coverage — a routing table asserting every one of the 79 profiles resolves the ticker/industry
combination it's meant to, plus a cross-profile `return_on_equity` applicability probe.

### 3.3 What a profile actually changes

Three independent authorities apply a profile's rules, and a profile is wired through all three
or the omission silently suppresses most of the generic metric set for it (a real bug this
taxonomy closed once — see `docs/MODEL-CARD.md`):

1. **`pipeline/config/business_profiles.json`** — declares the profile's `replacement_metrics`:
   the specialized multiples that sub-industry's own research calls for (e.g. `combined_ratio`
   for P&C insurers, `funds_from_operations`/`price_to_ffo` for REITs, `net_interest_margin` for
   banks, `distribution_coverage_ratio` for midstream MLPs). Most of these are still **declared
   intent, not a computed value** — several (AUM, rate base, RevPAR, dayrates) are disclosed in
   8-K supplementals and MD&A prose rather than tagged XBRL, so computing them is a
   supplemental-parsing project (`pipeline/filing_extraction.py`, off by default — see
   `docs/MODEL-CARD.md`'s "Operating-KPI text extraction" section), not a config change. The
   generic zero-new-data reads `capex_intensity`, `operating_ratio_proxy`, `gross_margin_trend`,
   and `inventory_correction_flag` (`pipeline/fundamentals_extended.py`) stand in as
   `replacement_metrics` for several newer profiles where no sector-specific KPI is computed yet.
2. **`pipeline/config/applicability_matrix.json`** — the suppression side: which of the *generic*
   metrics (§5.4's fundamentals set) do not apply to this profile at all (a bank's EV/EBITDA, an
   insurer's Altman Z), each with a stated reason, or an `$inherits` pointer to another profile's
   rule set where the economics genuinely match.
3. **`pipeline/config/metric_registry.json`**'s per-metric `applicability_profiles` allow-lists —
   a second, independent suppression authority (`canonical_metrics.applicability_for` checks
   both this and the matrix above, and treats a profile *absent* from either list as suppressed).

### 3.4 Peer grouping — a related but separate question

`pipeline/peer_groups.py` decides which population a company's *valuation score* is ranked
against for the percentile-tier claim shown on the stock detail sheet ("Valuation score in the
cheapest third of Commodity producers"). `classify_profile()` still governs which *metrics*
apply to a name exactly as above; `peer_group()` only changes the *population* a valuation
percentile is measured against, and diverges from the metric-applicability profile in one way:

- Splitting a ~910-name universe across ~79 profiles pushes most profile-specific peer groups
  below the **n ≥ 30** sample this module requires before publishing a tier claim at all
  (`MINIMUM_VALID_PEERS`). A too-thin profile-specific group rolls up to its broader GICS-sector
  bucket for peer-*comparison* purposes only — except for the seven profiles the original THG
  false-precision audit was built around (`bank`, `property_casualty_insurer`, `life_insurer`,
  `diversified_insurer`, `reit`, `utility`, `commodity_producer`), which stay silent below the
  minimum instead of rolling up into a broader "Financial Services" or "Real Estate" bucket that
  would reintroduce the category error the audit exists to prevent
  (`LEGACY_PEER_COMPARISON_PROFILES`).
- Ranking method: **tiers, never a two-significant-figure percentage.** Cheapest third / middle
  third / most expensive third, with `n` always published alongside. Ties share an averaged rank
  (and therefore a tier) rather than an arbitrary alphabetical break — see §6.2 for the exact
  mechanics, since this is itself one of the app's ranking methods.

---

## 4. Screens — how they're built and organized, and their data types

### 4.1 Two kinds of screen

- **The research score itself** (§5) is a per-stock number computed for the whole scored
  universe and published inside `advisor.json`'s `research` array — not a "screen" in this
  section's sense, since it isn't a separate ranked list over a separate question.
- **`/screens/*`** are cross-sectional lists over that same universe (typically ~910 stocks + 126
  ETFs from static config, plus any held portfolio symbols merged in and deduped), each ranking a
  *different* question than "is this a good business at this price" — momentum continuation,
  earnings timeliness, a 2-day-to-8-week swing setup, congressional trading activity, and so on.
  Every screen is built by its own `pipeline/build_*.py` or `pipeline/*_screens*.py` module and
  published as its own `public/data/screens/*.json` file (or, for a handful, computed client-side
  from `report.json`/`advisor.json` — noted per row below).

Top-level navigation order (`SCREEN_NAV`, `src/pages/ResearchScreen.jsx`): Swing signals, Fast
growth, Options, Momentum, Quality at valuation lows, Earnings timeliness, Structural vs
tactical, Early session, Shadow portfolios, Live validation, Politics trade alert, Institutional
accumulation, Inside information, Theme exposure, Backtest comparison. `Screens` in the primary
nav lands on `/screens/swing`.

### 4.2 Screens catalog — route, data file, builder, what it ranks

| Route | Data file | Built by | What it ranks |
|---|---|---|---|
| `/screens/swing` | `screens/swing.json` | `pipeline/swing_signals.py` + `pipeline/build_swing_screen.py` | §5's swing-horizon composite (2 trading days to 8 weeks) — see §6.2's `swing` ranking model for the identical formula read off the advisor row |
| `/screens/fast-growth` | none — client-computed from `report.json` | `src/lib/researchScreens.js` | Two sub-screens: Breakouts and Emerging growth (§6.3) |
| `/screens/options` + 7 sub-strategies | `screens/options.json` + 6 more (short-term-trades, covered-call, cash-secured-put, protective-put, collar, vertical-spread, advanced-strategies) | `pipeline/build_options_screen.py`, `pipeline/build_options_strategies.py`, `pipeline/build_covered_call_screen.py`, `pipeline/build_cash_secured_put_screen.py`, `pipeline/build_protective_put_screen.py`, `pipeline/build_collar_screen.py`, `pipeline/build_vertical_spread_screen.py`, `pipeline/build_advanced_options_screen.py` | Multi-day options ideas per mechanism (§6.4) |
| `/screens/momentum` | `screens/momentum.json` | `pipeline/build_momentum_screen.py` (scoring in `pipeline/research_screens_v2.py::momentum_scores`) | §6.5.1 — 12-1/12-7/6-1 momentum, 52w proximity, industry-relative momentum |
| `/screens/quality-value` | `screens/quality-value.json` | `pipeline/build_quality_value_screen.py` (scoring in `pipeline/research_screens_v2.py::robust_value_score`) | §6.5.3 — own-history valuation percentile + quality + distress/revision gates |
| `/screens/earnings` | `screens/earnings-timeliness.json` | `pipeline/build_tactical_screens.py` (scoring in `pipeline/research_screens_v2.py::tactical_score`) | §6.5.2 — revision/surprise tactical score |
| `/screens/matrix` | `screens/structural-tactical.json` | `pipeline/build_tactical_screens.py` | 2×2 structural (§5) × tactical (§6.5.2) classification |
| `/screens/early-session` | `screens/early-session.json` | early-session reversal research pipeline (Marketstack-fed) | Shadow-mode/capability-gated |
| `/screens/shadow` | `screens/shadow-portfolios.json` | shadow-portfolio tracker reading `pipeline/shadow_store/` | Immutable, net-of-cost prospective strategy performance |
| `/screens/validation` | `validation/live_v2_validation.json`, `validation/ic_validation.json`, `validation/research_evidence.json`, `validation/monte_carlo_projection.json` | `pipeline/validation/ic_harness.py`, `pipeline/build_research_evidence.py`, `pipeline/monte_carlo_projection.py` | Champion-vs-challenger prospective evidence and a 10,000-path Monte Carlo projection of the strategy itself |
| `/screens/politics` | `screens/congress-trades.json` | `pipeline/build_congress_screen.py` | §6.6 — STOCK Act disclosures, filterable by chamber/committee/trade size |
| `/screens/institutional` | `screens/institutional-13f.json` | `pipeline/build_institutional_screen.py` | SEC Form 13F-HR accumulation/distribution — same source as the `institutional_13f` modifier (§5.4), shown here as a descriptive, disclaimed screen rather than folded into any score |
| `/screens/inside-information` | `screens/inside-information.json` | `pipeline/build_inside_information_screen.py` | §4.3 — institutional 13F + Congressional trading, merged and filtered to only the notable subset of each |
| `/screens/themes` | `advisor.json` (`theme_exposure_score` per name, embedded, not a separate file) | `pipeline/themes.py` + `pipeline/theme_signals.py` | §4.4 — structural-trend exposure |
| `/screens/backtests` | `screens/backtest-comparison.json` | `pipeline/build_backtest_comparison.py` | A meta-comparison of every backtest result file in the repo, not a scored screen of its own |

### 4.3 Data types — what's schema-enforced, and what isn't

`pipeline/validate_data.py` is the single source of truth for what's actually typed and checked
on every run. Two different enforcement mechanisms cover different files:

**JSON-Schema-validated** (`pipeline/schemas/*.schema.json`, Draft 2020-12, checked against every
committed file by `Draft202012Validator`) — nine top-level files:

| File | Top-level required fields | Shape |
|---|---|---|
| `advisor.json` | `schema_version:int`, `model_version:str`, `model_metadata:obj`, `generated_at:str`, `data_mode`, `count:int`, `universe_count:int`, `methodology:obj`, `research:array`, `benchmark_history:obj`, `hypothetical_basis:num`, `portfolio_coverage`, `market:obj`, `source_status`, `run_manifest`, `disclaimer:str` | One row per scored company/ETF in `research`; each row is the shape described throughout §5 (score, components, fundamental_categories, technical_detail, theme_exposure, modifiers, etc.) |
| `etfs.json` | `schema_version:int`, `generated_at:str`, `data_mode`, `benchmarks:obj`, `count:int`, `etfs:array` | One row per ETF, scored by the fully separate model in §6.5.4 |
| `picks.json` | `generated_at:str`, `data_mode`, `disclaimer:str`, `buckets:obj` | Curated pick buckets, grouped |
| `status.json` | `generated_at:str`, `status`, `stages:obj` | Pipeline-run health/progress, one entry per stage |
| `signals.json` | `generated_at:str`, `data_mode`, `count:int`, `hot_sectors:obj`, `signals:array`, `cooling:array` | Sector-level heat/cooling read |
| `trades.json` | `generated_at:str`, `data_mode`, `count:int`, `lookback_days:int`, `trades:array` | Individual trade-level records |
| `prices.json` | `generated_at:str`, `data_mode`, `count:int`, `prices:obj` | Keyed by ticker, not an array |
| `news.json` | `generated_at:str`, `data_mode`, `count:int`, `feed_health:array`, `flagged_sectors:obj`, `flagged_tickers:obj`, `items:array` | One row per article |
| `politicians.json` | `generated_at:str`, `data_mode`, `count:int`, `leaderboard:array` | One row per member of Congress |

`congress-trades.json` has its own dedicated schema (`congress_trades_schema_errors()`,
`pipeline/validate_data.py`) checked outside the `FILES` loop above, since `screens/*.json` files
sit outside that loop. `recommendation-v5.schema.json` describes the `recommendation`/
`recommendation_v2` sub-shape embedded in an `advisor.json` row rather than a standalone
top-level file.

**Cross-file invariant checks, not JSON Schema** (still in `pipeline/validate_data.py`, but
asserted in code rather than declared in a schema) — the theme-screen anti-hype guardrails
embedded in `advisor.json` (`theme_screen_errors()`: price momentum must contribute exactly zero
to theme exposure; every row must declare `eligible`), enrichment-coverage checks, ETF
peer-group consistency, the `advisor.json` blend-weight contract (fundamentals ≥ 60% of the
blend and must outweigh price + news combined; news capped at 15%), the peer-tier schema
contract (§3.4 — a `sector_valuation_percentile` must agree with the canonical `ordinal`, and no
row below the minimum sample may publish a continuous percentile), and — directly relevant to
"how a screen is organized" — an explicit **sort-order invariant**: `advisor.json`'s `research`
rows must be strictly ordered by descending `score`, checked by comparing the published array
against its own sorted copy (`scores != sorted(scores, reverse=True)` is a hard validation
failure). This is the mechanism, not a convention, that guarantees the research leaderboard is
actually sorted the way it claims to be.

**Every other `screens/*.json` file** (swing, momentum, quality-value, earnings-timeliness,
structural-tactical, early-session, shadow-portfolios, institutional-13f, inside-information,
backtest-comparison, and the options family) has no dedicated JSON Schema — its shape is enforced
by its own builder script (each constructs a fixed dict with `generated_at`, a `count`, and one
named array of ranked rows, the same convention the schema-validated files use) plus whatever
cross-file checks `validate_data.py` happens to assert for it (several, like the theme guardrails
above, live inside the `advisor.json` check because the theme screen is embedded there rather
than published standalone). A screen without a formal schema is not untyped in practice — every
builder module declares its row shape in code and is covered by `pipeline/tests/` — it simply
isn't checked against a machine-readable contract the way the nine `FILES` are.

### 4.4 Theme exposure — a screen built from disclosure, not price

`pipeline/themes.py` + `pipeline/theme_signals.py`, published inside `advisor.json` rather than
its own file. Answers "how exposed is this company to a multi-year structural demand driver,
independent of whether its price has already moved?" — price momentum contributes **exactly
zero** weight to theme exposure, a hardcoded rule (not configurable), because thematic ETFs have
a documented history of losing ~30% risk-adjusted over their first five years by launching near
valuation peaks in already-hyped names (Ben-David, Franzoni, Kim & Moussawi, *Review of Financial
Studies* 2023).

Up to six signal families per theme (each theme declares its own subset and weights, normalized
to sum to 1): `segment_revenue_share` (ASC 280 XBRL segment reporting — the dominant signal in
all 11 theme files), `filing_keyword_density_trend` (10-K language change, a tie-breaker at
0.05–0.10), `transcript_theme_salience` (same measurement on earnings-call transcripts),
`customer_concentration_to_spenders` (ASC 280 named customers matched against confirmed theme
spenders), `spender_capex_growth`, `backlog_growth`. A theme requires **at least 2 resolved
signals** before it publishes any score. Eleven themes ship (`ai_infrastructure`,
`automation_and_robotics`, `grid_electrification`, `reshoring_industrial_capacity`,
`defense_rearmament`, `energy_security`, `cybersecurity`, `digital_payments`,
`obesity_care_supply_chain`, `aging_demographics`, `water_infrastructure`).

**Ranking within a theme group** — the `opportunity_score`:
`exposure_score·0.45 + fundamental_score·0.35 + cheapness·0.20`, where `cheapness` is the same
peer-group valuation tier midpoint from §3.4 (16.7 / 50 / 83.3), not a true percentile. This is
one of the ranking methods catalogued in §6.7.

A related, separately-computed block, `pipeline/theme_trend.py`, evaluates whether a theme is
*actually moving* (direction, breadth, leadership, crowding) — the one place in the theme layer
that reads price on purpose, kept structurally separate so a price-derived group statistic can
never leak into an individual company's exposure score; `validate_data.py` enforces the
separation by requiring the trend block to publish `contributes_to_exposure: false` and treating
any price field on an exposure row as a hard error. See `docs/MASTER-METHODOLOGY.md` §14 for
`theme_trend.py`'s six-reading maturity model and six-verdict classification in full.

### 4.5 Portfolio, planning, and finances screens — organization

These require sign-in (Firebase Auth); Firestore holds portfolio, transaction, snapshot, pool,
goal, preference, and alert-rule data, distinct from every static `public/data/*.json` file
above.

- **`/portfolio`** (`src/pages/Portfolio.jsx`, `view` prop) — three views on one page: Summary
  (holdings table, performance vs. benchmark, uninvested cash), Performance (a single
  benchmark-comparison chart plus an "opportunity cost" comparison against the same cost basis
  held in the S&P 500 or flat cash), and Data overview (move-attribution, scenario sensitivity,
  the full performance-metrics suite — computed only when this view is active).
- **`/portfolio/diversification`** (`src/pages/Diversification.jsx`) — concentration (HHI,
  effective holdings), pairwise return correlation, covariance-based risk decomposition
  (effective bets, diversification ratio), ETF look-through, a five-factor-plus-momentum OLS
  regression against the French Data Library factors, historical expected shortfall, tracking
  error, and active share.
- **`/portfolio/insights`** (`src/pages/Insights.jsx`) — tracked activity and behavioral
  insights: "you vs. benchmark," holdings-vs-benchmark since purchase date, trading-behavior
  stats, purchase-timing analysis, milestones.
- **`/finances`** — income, spending, savings "pools," linked accounts, contribution-room
  tracking; goals reuse the same pool structure and feed the Planning simulator.
- **`/planning`** — a 5,000-path block-bootstrap retirement/goal-probability simulator
  (`src/lib/projectionEngine.js`), publishing the 10th/25th/50th/75th/90th percentile paths.

See `docs/MASTER-METHODOLOGY.md` §16 for the full formula set behind each panel (HHI, factor
regression, the return-source selection order the bootstrap uses, etc.).

---

## 5. The research score — every sorting method, and how each is made

This section documents *how the research score itself is built* — the number every stock
detail sheet, the Dashboard, and `/research` sort by. §6 catalogs every *other* ranking method
in the app, several of which re-sort the same underlying rows by a different question entirely.

### 5.1 The published score, top to bottom

Entry point: `build_research()`, `pipeline/advisor_engine.py:1241-`.

```
raw   = Σ(component_i · weight_i) / Σ(weight_i)      — only over components that resolved
base  = raw                                           — no coverage multiplier applied at this level
score = clamp(base + modifier_points, 0, 100)         — modifier_points capped to ±15 total
```

Three top-level components (`ranking_weights`, `pipeline/config/settings.json`):

| Component | Weight |
|---|---:|
| **Fundamentals** | **78%** |
| **Market behavior** (technical) | **18%** |
| **News sentiment** | **4%** |

### 5.2 Fundamentals (78% of the score) — six categories, each a weighted sub-tree

| Category | Weight of fundamentals | Leading metric |
|---|---:|---|
| Valuation | 28% | EV/EBITDA (27% of category) — capital-structure-neutral, the best-validated single value multiple in the published research |
| Profitability + cash | 26% | ROIC (26%) — leverage cannot inflate invested capital the way it inflates ROE |
| Financial health | 15% | Interest coverage (30%) — answers "can this business service its debt at current rates," which debt/equity alone cannot |
| Growth | 11% | Revenue growth (26%) |
| Capital allocation | 10% | Net buyback yield (34%) |
| Accounting quality | 10% | Piotroski F-score (45%) — the one earnings-quality signal that still validates well; the accruals-ratio anomaly has decayed in US data since 2002, so it's weighted lightly |

Every metric's exact formula, weight, and direction (higher/lower/ideal-range/range-score) is
tabulated in `docs/MASTER-METHODOLOGY.md` §4 — 26 metrics across the six categories.

**Coverage weighting and confidence penalty**: `weighted_coverage()` computes the fraction of
total metric *weight* actually resolved for a company (a missing headline metric like ROIC costs
far more confidence than a missing minor one like DSO trend), and the fundamentals score itself
is shrunk by its own coverage: `raw · (0.65 + 0.35 · coverage)`. Bank/insurer snapshots skip 12
metrics that don't apply to their balance sheets (`FINANCIAL_EXEMPT`) — those leave the coverage
denominator entirely rather than counting as missing evidence, which is the general applicability
mechanism §3.3 describes for the full sub-industry taxonomy.

**Two interchangeable scoring engines** produce the six category scores from different
normalization strategies (`normalization_mode` in `settings.json`):

- **Band mode** (champion, in production) — every raw metric mapped to 0–100 through fixed,
  hand-set bands, configured per-sector.
- **Cross-sectional mode** (challenger, shadow-only) — every metric scored as a winsorized
  percentile against the current refresh's own universe (sector distribution if ≥8 peers, else
  the full universe). Published beside the champion for comparison, never swapped in silently.

### 5.3 Market behavior and news sentiment (18% + 4%)

Market behavior (`technical_factors()`) blends seven weighted sub-signals — 12-1 momentum (30%
raw weight, skip-month construction to avoid short-term reversal), risk-adjusted return (26%,
`0.65·Sortino + 0.35·Sharpe`), relative strength vs. SPY (16%, currently dropped and
renormalized away in production per `short_horizon_treatment: "neutral"`), drawdown resilience
(14%), volume confirmation (8%), low-beta reward (6%), and a four-indicator `technical_extended`
blend (6%) — combined as `Σ(value·weight) / Σ(weight of resolved signals)`.

News sentiment (`sentiment_score()` → `pipeline/news_intelligence.py::weighted_sentiment`) is a
rolling 7-day window with exponential recency decay (3-day half-life), source-quality weighting,
title-similarity deduplication, and a minimum entity-confidence floor — deliberately capped at 4%
of the total score (cut from an original 10%; Tetlock 2007 finds media pessimism's price effect
reverts to fundamentals within days, so it's a tilt, not a tenth of the thesis).

Full formulas: `docs/MASTER-METHODOLOGY.md` §5–§6.

### 5.4 Modifiers — the bounded post-blend adjustment layer

`apply_modifiers()`, `pipeline/advisor_engine.py:373-396`. Each modifier is independently capped;
the combined total is clamped to **±15 points** before being added to the blended base score. All
caps are read live from `settings.json::modifiers`:

| Modifier | Mechanics |
|---|---|
| Sector-relative valuation | Cheap/rich vs. sector peers, not absolute multiples |
| Short interest | Cross-sectional information from unusually high or low short interest, not automatically bearish |
| Insider activity | SEC Form 4 open-market trades split routine (score zero) vs. opportunistic (positive, decaying over time) |
| Liquidity | A name that can't be exited without moving the price carries a real cost fundamentals never show |
| Analyst expectations | Used only when the published minimum analyst coverage is present |
| Macro regime | FRED rates/inflation/labor/yield-curve, weighted by sector sensitivity, never replacing company evidence |
| Institutional 13F | Curated, publicly traded, actively managed filers only (index funds and private-equity managers excluded); decayed by filing lag |
| Congressional buying | Reward-only — disclosed purchases score a mild positive, with a bonus for a member's first-ever trade in a sub-$2B company; sales never penalize |
| Customer concentration (shadow only) | ASC 280 disclosures, penalty-only; not yet in the published score |
| Geographic concentration (shadow only) | Single-country revenue concentration, penalty-only; not yet in the published score |

Full per-modifier caps and trigger mechanics: `docs/MASTER-METHODOLOGY.md` §8.

### 5.5 The leaderboard sort itself, and the peer-tier ranking inside it

Two distinct "sorting methods" sit downstream of the score above:

- **The published leaderboard.** `advisor.json`'s `research` array is required, by a hard
  validation check (§4.3), to be strictly ordered by descending `score` — the simplest sort in
  this document, and the one every other ranking method in §6 exists precisely because it isn't
  enough for every question a reader might ask.
- **The peer-relative valuation tier**, shown per company on the stock detail sheet. This is
  *not* a re-sort of the leaderboard — it's a separate ranking of one company's valuation
  composite against its peer group (§3.4), computed by `pipeline/peer_groups.py`:
  1. Group companies by `peer_group()` (their sub-industry profile, or sector fallback).
  2. Require **n ≥ 30** valid peers or publish nothing (`insufficient_valid_peers`).
  3. Sort the group by valuation composite, **tied values sharing one averaged rank** —
     `_averaged_rank_fractions()` — so two companies with the same composite land in the same
     tier rather than being split apart by an arbitrary secondary sort key (an alphabetical tie
     break is exactly the bug this module replaced: it once put two insurers 7.7 percentile
     points apart for scoring identically).
  4. Map the resulting rank fraction to one of three tiers — cheapest third (`≥ 2/3`), middle
     third, most expensive third (`≤ 1/3`) — never a two-significant-figure percentage, since a
     percentile over a composite of discrete band scores can't support that resolution.

### 5.6 What has and hasn't been validated

A scoring change ships only if it improves **out-of-sample rank information coefficient (IC)**
after deflation for the number of configurations tried — not because a single backtest's equity
curve looks good. `pipeline/validation/ic_harness.py` is the harness; `docs/MASTER-METHODOLOGY.md`
§9 and `docs/VALIDATION-METHODOLOGY.md` are the full state of what has and hasn't cleared that
bar. This document, like the Methodology page it's bundled from, is a description of the current
model's mechanics, not a claim that the mechanics predict returns.

---

## 6. Every other ranking/sorting method in the app

The research score (§5) answers one question — "is this a good business, at this price, to own
for years." Everything below re-ranks the same or an overlapping universe by a *different*
question, each with its own declared weights, gates, and formula. None of these feed back into
the published research score.

### 6.1 The ten client-side ranking lenses (`src/lib/rankingModels.js`)

Ten independent models, each declaring its own components/weights in one object so the "why"
panel and the score can never drift apart. Four rules govern all ten:

1. **Composition is declared, not implied** — weights are frozen starting priors, not claims of
   measured optimality.
2. **Inapplicable components are dropped, never zeroed**, and the remaining weights renormalize —
   a metric a company legitimately cannot report costs confidence, not a fabricated zero.
3. **Percentiles against peers, not raw thresholds** — `peerPercentile()` ranks within industry
   when the sample supports it (≥3 peers, `MIN_PEER_SAMPLE = 8` for a full industry/sector tier),
   falling back to sector, then the whole universe.
4. **Confidence shrinks the result** — each model's raw score is pulled toward 50 by
   `src/lib/modeConfidence.js`'s confidence reading before ranking (`shrinkToConfidence`), the
   same shrinkage formula the confidence-gate module uses elsewhere in the app.

| Model | Question | Heaviest components | Gate |
|---|---|---|---|
| `research` | Is this a good business, at this price, to own for years? | Business quality 35%, sector valuation 20%, growth 15% | none |
| `valuation` | Is it cheap against the peers it should be compared with? | Sector valuation percentile 70%, valuation category score 30% | none |
| `fundamentals` | How strong is the business itself, price aside? | Profitability 30%, cash quality 20%, financial health 20% | none |
| `catalyst` | Has new information arrived the market may still be digesting? | Material recent news 55%, insider conviction 25%, expectation change 20% | at least one leg present and directionally non-neutral |
| `momentum` | Is an established trend continuing, with confirmation? | 12-1 momentum 35%, 3-month relative momentum 20%, 52w-high proximity 15% | positive 20-day *and* 5-day return |
| `reversal` | Has the price fallen further than the information justifies? | Volatility-scaled price shock 30%, statistical overextension 20%, fundamental shield 20% | pulled back over the medium term, turned up over the last week, fundamentals not below floor; capped at 45 if a thesis-break event (restatement, auditor, guidance, financing, regulatory, litigation) is present |
| `valueTurnaround` | Is it cheap AND is something measurably getting better? | Valuation discount 35%, operating improvement 25%, expectation change 15% | cheap (valuation ≥60) and business quality not below floor (≥55) |
| `analystConviction` | Are professional expectations being revised upward, and how fast? | EPS revision strength 40% (the *change*, not the level), upgrades vs. downgrades 25% | ≥3 covering analysts and at least one of a rating/target/revision reading |
| `swing` | Is there evidence at the 2-day–8-week swing horizon, from signals that survive costs? | Post-earnings drift (SUE) 30%, analyst revision change 25%, high-volume premium 20% | ≥2 of five swing-horizon signals resolved; above the liquidity floor ($2M avg. dollar volume); capped at 45 if heavily shorted |
| `tailwind` | Is the evidence improving faster than the price has re-rated? | Peer theme read-through 25%, own expectation revisions 25%, valuation discount 20% | scored structural-trend exposure exists; not blocked by negative own expectations/news |

Scoring mechanics (`scoreRow()`): a row failing its model's `gate` is excluded entirely rather
than padded into a low-ranked position — "a screen lists names that clear its bar." Components
are summed weighted, then renormalized over whichever components actually resolved (unless the
model is flagged `neutralCoverage`, which — used only by `swing`, whose heaviest leg resolves for
a fraction of the universe by construction — imputes a neutral 50 for a missing component
instead of renormalizing, keeping the scale comparable across rows with different evidence
counts). The `swing` model's five legs and weights are the identical formula the published
`/screens/swing` composite uses (§6.2) — not a second opinion, the same model read directly off
the advisor row.

### 6.2 The swing-horizon composite — one formula, two call sites

`pipeline/swing_signals.py::swing_scores` (→ `/screens/swing`) and the `swing` ranking model
above are the same five-leg formula, evidence-ordered by the horizon each leg's academic source
actually supports: post-earnings drift (Bernard & Thomas 1989/1990), analyst revision *change*
(Jegadeesh-Kim-Krische-Lee 2004 — the change predicts, the level mostly doesn't), high-volume
premium (Gervais-Kaniel-Mingelgrin 2001), 52-week-high proximity scaled by the stock's own
volatility (George-Hwang 2004), and prior-week reversal (Jegadeesh 1990, reversed — deliberately
the smallest weight, since Da-Liu-Schaumburg 2014 found its risk-adjusted alpha shrinks to
0.33%/month and it's the most cost-constrained of the five). Heavy short interest is a negative
screen, not a scored leg (Boehmer-Jones-Zhang 2008 is a short-side result a long-only book can't
harvest) — it caps the score at 45 rather than contributing a component.

### 6.3 Fast growth — the two client-computed sub-screens

`src/lib/researchScreens.js`, computed from `report.json` rather than a published pipeline
artifact.

- **Breakouts** (`rankBreakoutInProgress`) — sharp recent acceleration already validated by price
  action. Requires 5-day return > 2% and 20-day return > 0%, and that momentum is *accelerating*.
  Rank score: `burst·0.4 + acceleration·0.3 + trend·0.2 + volume·0.1`.
- **Emerging growth** (`rankEmergingGrowth`) — explicitly labeled
  `research_status: "prospective_unvalidated"`. Requires revenue growth > 5% and positive 20-day
  relative strength, and deliberately excludes anything Breakouts already caught. Rank score,
  weights renormalized over whichever terms resolve: growth 35%, margin 20%, relative strength
  20%, volatility contraction 15%, estimate-revision breadth 10% (only when present).

### 6.4 Options screens — ranking weights per strategy

All opt-in (`ENABLE_MULTIDAY_OPTIONS_SCREEN` / `ENABLE_ADVANCED_OPTIONS_SCREEN`), and every one
is explicitly a research screen, not a trade instruction.

| Route | Mechanism | Ranking weights |
|---|---|---|
| `/screens/options` (Multi-day) | Buy call/put, near-the-money, trend-directional | `iv_value` 25%, `liquidity` 35%, `trend_strength` 25%, `news_sentiment` 8%, `research_confidence` 7% |
| `/screens/options/covered-call` | Sell a covered call | `expected_value_pct` 38%, `liquidity` 25%, `cushion` 21%, `research_confidence` 10%, `news_sentiment` 6% |
| `/screens/options/cash-secured-put` | Sell a cash-secured put | `expected_value_pct` 33%, `probability_otm` 25%, `liquidity` 25%, `research_confidence` 10%, `news_sentiment` 7% |
| `/screens/options/protective-put` | Buy a protective put | `liquidity` 33%, `iv_value` 28%, `cost_efficiency` 26%, `research_confidence` 8%, `news_sentiment` 5% |
| `/screens/options/collar` | Long stock + protective put + covered call | `cost_efficiency` 35%, `range_width` 26%, `liquidity` 26%, `research_confidence` 8%, `news_sentiment` 5% |
| `/screens/options/vertical-spread` | Directional call or put spread | `risk_reward` 34%, `liquidity` 26%, `trend_strength` 25%, `news_sentiment` 8%, `research_confidence` 7% |
| `/screens/options/advanced-strategies` (iron condor) | Sell call spread + sell put spread | `credit_efficiency` 34%, `probability_in_range` 30%, `liquidity` 21%, remainder split across sentiment/confidence |
| `/screens/options/advanced-strategies` (straddle) | Buy call + buy put, same strike | `probability_of_profit` 31%, `liquidity` 31%, `iv_value` 25%, `news_sentiment` 8%, `research_confidence` 5% |

`news_sentiment`/`research_confidence` are sign-aligned with the chosen side in every directional
screen (call=+1, put=−1) — a conviction-confirmation role, not an independent signal.

### 6.5 The pipeline-side screen scores not already covered

- **6.5.1 Momentum screen** (`pipeline/research_screens_v2.py::momentum_scores`) — `momentum_12_1`
  40%, `momentum_12_7` 20%, `momentum_6_1` 15%, `high_52w_proximity` 15%,
  `industry_relative_momentum` 10%, every factor winsorized then z-scored against the *current*
  universe (cross-sectional, unlike the research score's absolute mapping). Eligibility gates:
  $5 min price, $300M min market cap, $2M min 60-day dollar volume, 253 min history sessions.
  Entry/exit hysteresis (enter ≥90th percentile, exit only below 75th) prevents flicker.
- **6.5.2 Tactical / earnings-timeliness score** (`pipeline/research_screens_v2.py::tactical_score`)
  — 15 weighted factors led by revision magnitude (15%), revision agreement (12%), and industry
  revision breadth (10%); cross-tabulated against the structural score (§10.1 of
  `docs/MASTER-METHODOLOGY.md`) at `/screens/matrix`, requiring both structural ≥65 and tactical
  ≥60 for the top classification.
- **6.5.3 Quality-value screen** (`pipeline/research_screens_v2.py::robust_value_score` +
  `classify_quality_value`) — cheapness is the weighted median of each metric's own-*history*
  percentile (distinct from sector-relative or universe-relative cheapness elsewhere in this
  document); final classification requires cheapness ≥70th own-history percentile *and* quality
  ≥65, screening out severe forward-estimate deterioration.
- **6.5.4 ETF composite score** (`pipeline/fetch_etfs.py::score_etf_universe`) — a fully separate
  model from the stock score: Performance 28%, Risk 27% (Sortino/Sharpe/max drawdown/beta),
  Cost 17% (expense ratio, tracking difference, NAV premium/discount), Liquidity 16%,
  Quality 12% (`structural_quality()` — issuer reputation adjusted for leverage/inverse structure,
  synthetic replication, aggressive securities lending). Percentiles computed within each fund's
  own peer group (`pipeline/config/universe.json`).

### 6.6 Political / Congressional trade score

Two distinct scores, never combined:

- `pipeline/scorer.py::run()` — a six-factor weighted score (track record 25, committee relevance
  20, cluster detection 20, trade size 15, direction/recency 10, policy catalyst 10) that writes
  `signals.json`. Nothing in the production CI pipeline currently calls this outside seeded demo
  data — it describes the model this score *would* compute in production, not what's presently
  published alongside real Congressional data.
- `pipeline/congress_signal.py::score_congressional_buying` — the score that actually reaches
  production, folded into the research score as the capped "Congressional buying" modifier
  (§5.4), reading the live `screens/congress-trades.json`.

`/screens/inside-information` reuses neither directly — it reuses
`political_institutional.rank_disclosed_trades`, whose combined score is
`political_points + institutional_points` at native scale (political points capped at 4.0,
institutional points clamped to [-2.0, +3.0] after lag decay). Point-in-time visibility gating
applies: only rows visible as of their disclosure/filing date are used, never transaction date.

### 6.7 Theme opportunity score and watchlist setup score

- **Theme opportunity score** (§4.4): `exposure_score·0.45 + fundamental_score·0.35 +
  cheapness·0.20`, ordering rows within a theme's leaders/sector-connected groups.
- **Watchlist setup score** (`src/lib/watchlistGuidance.js`) — combines four subscores (thesis,
  research score, data coverage, guidance) with a **weighted geometric mean**,
  `G = exp(Σ w_i·ln(s_i) / Σ w_i)`, rather than an arithmetic blend, specifically so a single
  zero subscore forces the geometric mean to zero — a published Sell guidance can't be diluted
  into a middling setup score by averaging it against three healthy subscores. Each raw signal
  maps to its subscore through a logistic centering function,
  `s(x) = 1 / (1 + exp(-k·(x - center)/width))`, so the configured center always reads 0.5.
  Hard-blocked (setup forced to "Avoid", allocation to zero) when data coverage is below the
  published evidence floor or guidance is Sell.

### 6.8 Backtest comparison — sorting within, never across, method families

`pipeline/build_backtest_comparison.py` normalizes 13 backtest methods across three families and
explicitly sorts only within like-for-like groups, since "success rate" means three different
things depending on the method: `rebalance_periods_positive` (held-portfolio methods, including
the research score itself rebalanced monthly), `trades_profitable` (the 9 options-strategy
backtests), and `periods_with_positive_ic` (the swing composite's own rank-IC diagnostic, kept
separate from its portfolio-return backtest). A "feature rollup" averaging success rates across
methods sharing a declared input is explicitly labeled co-occurrence, not causal attribution.

---

## 7. Where this is published in the app

The Methodology page (`/methodology`, `src/pages/Methodology.jsx`) is the in-app summary of the
research score's weights and guardrails, and its "Download full docs (.md)" button bundles the
unedited source documents this file draws from — `APP-COMPLETE-BREAKDOWN.md`,
`docs/MASTER-METHODOLOGY.md`, and this file — so a reader gets the same file:line-cited material
the page itself is generated from, not a paraphrase of it.
