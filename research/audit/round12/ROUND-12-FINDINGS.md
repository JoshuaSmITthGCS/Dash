# Round 12 — Valuation, currency, ADR, and scoring data-integrity audit

Full-pipeline audit requested against a specific complaint pattern: quality metrics (ROE, net
margin, current ratio, debt/equity, price) look reasonable for a company while its valuation
metrics (market cap, EV, P/E, EV/EBITDA, EV/FCF, dividend yield) are implausible. Three parallel
code-tracing passes covered (1) the valuation/EV/multiple calculation path end to end, (2)
ADR/currency/share-count handling, and (3) the scoring model's treatment of valuation factors,
followed by direct verification, fixes, and regression tests for every confirmed bug scoped
small enough to fix safely in this pass. Findings below are grounded in `pipeline/*.py` file:line
citations and, where noted, the actual committed `public/data/advisor.json` and
`pipeline/data/pit/fundamentals/*.jsonl`, not hypothetical scenarios.

**A constraint stated up front, not buried:** this sandbox's outbound proxy blocks Yahoo Finance
and SEC EDGAR outright (confirmed pre-existing in `docs/LIMITATIONS.md`, "Verification"
section). Every finding below is a static-code and committed-data finding; none of it required a
live fetch, but requirement #5 of the audit brief (compare 20+ companies against two live
external references each) could not be executed from here. Section 8 states exactly what a
follow-up pass with real network access needs to run to close that gap.

## Executive summary

**Root causes, ranked by demonstrated blast radius:**

1. **`dividend_yield` is stored with an inconsistent, unverified unit convention, and two
   different parts of this codebase already disagree about which convention it is.** Checked
   directly against the committed `public/data/advisor.json`: **25 of 40 published rows**
   (62.5%) carry a `dividend_yield` value that is unambiguously percentage-shaped (EOG=2.85,
   THG=1.67, SYF=1.76 — i.e. 285%, 167%, 176% yields if read as decimals, versus plausible
   2.85%/1.67%/1.76% if read as already-percentage numbers). `pipeline/rank_picks.py` scores and
   formats the field as a decimal fraction (`dy > 0.03`, `dy*100:.1f%`); `src/lib/
   resolvedMetricSections.js:36` formats it as an already-percentage number
   (`value.toFixed(2)+'%'`, the only field in that entire table that doesn't multiply by 100).
   **Both cannot be right about the same stored value, and the live data proves neither
   assumption holds universe-wide.** This is the single most severe, most widely-manifesting
   defect found — not hypothetical, present today in the published artifact. Partially
   mitigated in this pass (Section 3); not fully fixable without live provider verification
   (Section 8).
2. **A negative EV-based multiple or negative P/B was scored as the single worst possible value
   in the champion model**, when it is very often the opposite: net cash exceeding market cap
   (deep value) or buyback-driven negative book equity (a clean balance sheet), not distress.
   Confirmed live in `pipeline/scorer.py`'s `multiple_score`/`band_score`, confirmed as an
   already-recognized-and-half-fixed bug class (the identical fix exists for
   `net_debt_to_ebitda` and in the shadow `CrossSectionalNormalizer`, but not in the champion
   `bands` path). Fixed in this pass (Section 3).
3. **No currency-normalization layer exists anywhere in this pipeline**, and the EDGAR
   statement-enrichment fallback merged whatever unit an XBRL fact happened to be tagged in —
   confirmed on disk: Birkenstock Holding plc (BIRK, a live universe member) has its *entire*
   EDGAR fact history tagged EUR, and 256 other CIKs carry at least one non-USD-tagged fact
   (CNY, CAD, EUR, GBP, JPY, and 35+ more unit strings observed). A EUR revenue/debt/cash figure
   merged next to a USD market cap would silently misprice every EV-based multiple by roughly
   the FX rate. Fixed for the EDGAR fallback path in this pass (Section 3); no general
   cross-provider currency layer exists or was built (Section 6 specifies one).
4. **No ADR/ADS-to-ordinary-share ratio handling exists anywhere in this pipeline.** Two call
   sites (`pipeline/valuation_history.py`, `pipeline/backtest_historical.py`) reconstruct
   `market_cap = price × shares` from a statement-derived share count that, for a foreign-listed
   ADR (TSM, ASML, NVO, ABB are confirmed live in the 932-symbol universe), is the issuer's
   *ordinary*-share count, not the ADS-equivalent count the ADR's USD price implies — a
   structural, permanent mismatch (TSM: 1 ADS = 5 ordinary shares), not a one-time event, so
   nothing in the existing split-detection machinery would ever catch it. Fixed for both call
   sites in this pass via a new, deliberately unpopulated verification registry (Section 3, 7).
5. **A dead plausibility guard**: `plausibility.implied_share_count_violations` — built
   specifically to catch "a split-adjusted price paired with an unadjusted share count, and the
   reverse" — could never fire in production because no live code path ever set
   `shares_outstanding` on the snapshot it screens. Fixed in this pass (Section 3).
6. **The `signals.json`/Congressional-trades scoring path (`fetch_prices.py` +
   `scorer.run()`) had zero plausibility screening of any kind**, unlike the `advisor.json`
   path. Every implausible-field defect above reached that score unguarded. Fixed in this pass
   (Section 3).
7. Two labeling/naming defects that don't change a published number but corrupt any consumer
   that trusts the label: Yahoo's `revenueGrowth`/`earningsGrowth` were marked `is_ttm=True`
   when they are quarter-over-quarter YoY figures (fixed in this pass), and `ev_to_sales`
   (annual-basis, from statements) sits beside `price_to_sales` (genuinely TTM, from the quote)
   in the same row with no field distinguishing the basis (not fixed — see Section 2.D).

**Should today's published data be trusted?** Quality metrics (ROE, margins, current ratio,
debt/equity) that come straight from a single-currency, same-listing quote payload are
generally sound for ordinary US-domiciled names — the complaint pattern's premise is confirmed
correct: the asymmetry between "quality looks fine, valuation looks broken" traces to exactly
the multi-source, multi-currency, multi-listing joins valuation multiples require and quality
ratios mostly don't. **Do not trust `dividend_yield` on any row today** (Section 3's partial
fix only removes the unambiguous half of the defect). **Do not trust any EV-based multiple,
`total_debt`, `free_cash_flow`, or `revenue` for BIRK** or any other name whose EDGAR-fallback
statement history is non-USD (now blocked rather than silently wrong, as of this pass, but was
wrong before it). **Do not trust `market_cap`, or anything computed from it, from
`valuation_history.py`'s "quality at valuation lows" screen or from `backtest_historical.py`'s
backtest engine for TSM, ASML, NVO, or ABB** before this pass (fixed to fail closed rather than
silently wrong, as of this pass — see Section 7 for why the ratio itself still isn't populated).
Everything else audited — capex sign convention, FCF construction, EV additive-components logic
(cash/debt netting), non-scoring plausibility rules already in place — was checked and found
sound; those are documented as confirmed-correct, not merely unexamined, in Section 2.

## Method

Three parallel research passes traced (a) every valuation/EV/multiple calculation from raw
provider field to displayed value, (b) ADR/currency/share-count handling specifically, and (c)
how the scoring model consumes valuation factors — each independently grepping and reading the
actual `pipeline/*.py` source, not summarizing prior documentation. Every claim below cites the
file:line it came from; the few claims that could not be verified against live data because of
the sandbox's network restriction are labeled as such rather than asserted.

## Section 1 — Metric lineage (representative fields)

| Metric | Raw source field(s) | Source date/period | Currency | Units | Share/listing basis | Formula | Validation status | Issue found |
|---|---|---|---|---|---|---|---|---|
| `price` | Yahoo `info.currentPrice`/`regularMarketPrice` (`fetch_prices.py:66`); AV close fallback (`fetch_advisor.py:868`, actually reuses whichever price history is longer, almost always Yahoo) | live quote | Whatever Yahoo trades the symbol in (`info.currency`, captured but never checked) | raw | listing the ticker resolves to (ADR for TSM/ASML/NVO/ABB) | pass-through | Cross-checked vs. AV within 5% (`plausibility.py` `PRICE_TOLERANCE`) only when AV covers the symbol | Currency of the quote is never verified to be USD |
| `market_cap` | Yahoo `info.marketCap` (`fetch_prices.py:82`); AV `MarketCapitalization` (`fetch_advisor.py:835`) | live quote | unverified (`"usd"` unit tag in `canonical_metrics.py:444` is an unchecked label) | raw | vendor-computed, generally ADR-consistent for Yahoo's own field | pass-through | Cross-checked vs. AV within 20% (`MARKET_CAP_TOLERANCE`); **now** also cross-checked against `price × shares_outstanding` (this pass, Section 3) | None found in the vendor field itself; the *reconstruction* of market cap elsewhere from statement share counts was the bug (Section 2.A) |
| `shares_outstanding` | **Was never published on the live snapshot at all** before this pass. Now: Yahoo `info.sharesOutstanding` (`fetch_prices.py`, this pass) | live quote | shares | raw | same listing as `price`/`market_cap` (i.e., ADR share count for an ADR — internally consistent with `market_cap`, not the ordinary-share count) | pass-through | `implied_share_count_violations` now live (was dead code) | Deliberately *not* sourced from the balance-sheet "Ordinary Shares Number" row, which is a different, ADR-inconsistent concept (Section 2.A) |
| `enterprise_value` | `enterpriseValue` if Yahoo supplies it, else `market_cap + total_debt − cash` (`fundamentals_extended.py:551-555`) | live market_cap + latest annual balance sheet (or EDGAR PIT fallback) | **Not verified same-currency** across the three components before this pass for the EDGAR-fallback path | raw dollars | market_cap's listing basis; debt/cash from whatever statement source resolved | additive | `multiple() ` caps result at 500x and drops outliers to `None` (`fundamentals_extended.py:566-569`) | Confirmed: EDGAR fallback could merge non-USD debt/cash into a USD market_cap (fixed this pass, Section 3) |
| `ev_to_ebitda` | `EV / EBITDA`, `EBITDA = operating_income + |D&A|` when not directly reported (`fundamentals_extended.py:556,577`; EDGAR-fallback synthesis at `edgar_enrichment.py:149-151`) | annual statements (see `ev_to_sales` note on TTM/annual mismatch, Section 2.D) | see `enterprise_value` | multiple | n/a | `multiple(ebitda)` | Sector-agnostic band (`settings.json fundamentals.ev_to_ebitda`, one universal band for every sector) | Sign-inversion bug (Section 2.E) fixed this pass; sector-conditioning gap (Section 4, Finding 2) not fixed |
| `ev_to_sales` | `EV / revenue` (`fundamentals_extended.py:558,584`) | **annual** statement revenue | see `enterprise_value` | multiple | n/a | `multiple(revenue)` | none dedicated | Sits beside `price_to_sales` (genuinely TTM, `priceToSalesTrailing12Months`) in the same row with no field saying which basis backs which multiple (Section 2.D, not fixed) |
| `dividend_yield` | Yahoo `info.dividendYield` (`fetch_prices.py:95`); AV `DividendYield` (`fetch_advisor.py:870`) | live quote | **unverified — the entire defect** | ambiguous: decimal fraction in some rows, percentage number in others, confirmed by inspecting live data | n/a | pass-through, no formula | **New this pass**: `dividend_yield_likely_percentage_not_decimal`/`negative_dividend_yield` rules in `plausibility.py` | Root cause #1 above; only the unambiguous >50% tail is caught (Section 3, Section 8) |
| `free_cash_flow` | `operating_cash_flow − |capex|` (`fundamentals_extended.py:193-198`, `edgar_enrichment.py:158-160`) or Yahoo's own `freeCashflow` pass-through (`fetch_prices.py:83`) | TTM/annual depending on path (two independent computations exist) | see `enterprise_value` | raw dollars | n/a | capex sign handled correctly (`abs()`) everywhere checked | none dedicated | Confirmed **correct** sign handling throughout — checked specifically per the audit brief's Section E and found sound |
| `net_debt` | Never published as its own field; only appears inline inside `enterprise_value` and inside `net_debt_to_ebitda` (`fundamentals_extended.py:290-298`) | see `enterprise_value` | see `enterprise_value` | raw dollars | n/a | `debt − cash`, missing components treated as 0 | `lower_is_better_score` correctly reads negative (net cash) as a strength | Missing cash silently treated as `$0` cash rather than flagged "unknown" (Section 2.C, not fixed — see remediation plan) |
| `trailing_revenue_growth` | Yahoo `revenueGrowth` (`canonical_metrics.py`) or AV `QuarterlyRevenueGrowthYOY` (`fetch_advisor.py:842`) | **quarter-over-quarter YoY, not TTM, from either provider** | n/a | decimal | n/a | pass-through | **Fixed this pass**: was `is_ttm=True` for the Yahoo mapping only, now `is_ttm=False` + `quarterly_not_ttm` flag on both mappings | Confirmed live: field name itself (`trailing_revenue_growth`) is still misleading — a naming debt beyond this pass's scope (Section 2.D) |

## Section 2 — System-wide error report, by category

### A. ADR / share-class issues

- **Confirmed, fixed this pass.** `pipeline/valuation_history.py::_multiples()` and
  `pipeline/backtest_historical.py::build_snapshot()` both computed
  `market_cap = close_or_price × shares`, where `shares` came from the balance sheet's
  "Ordinary Shares Number"/"Share Issued" row (`fundamentals_extended.py:47`,
  `edgar_enrichment.py` `BALANCE_ROWS`) — the issuer's *ordinary*-share count. For TSM (1 ADS =
  5 ordinary shares, publicly and stably documented by the depositary), multiplying an ADR's USD
  price by the full ordinary-share count overstates market cap, and every ratio built on it, by
  roughly 5x. This is a *structural*, permanent mismatch, not a point-in-time event like a
  split, so `pit_shares.py`'s existing (and otherwise careful) split-detection machinery would
  never flag it — it only looks for step changes. ASML, NVO, and ABB are also confirmed present
  in the 932-symbol universe as ADRs/foreign-domiciled names.
- **The only other ADR-specific code anywhere in this repository** is a single retirement note
  in `fetch_advisor.py:219` for a delisted ticker ("Tata Motors NYSE ADR delisted January
  2025") — not ratio handling of any kind.
- **Fix implemented (this pass):** `pipeline/adr_registry.py` + `pipeline/config/
  adr_listings.json` (Section 7) gate both call sites. A ticker flagged as a known,
  unreconciled ADR now returns "unavailable" for the price×shares reconstruction rather than a
  silently wrong number. **The ratio itself is deliberately left unpopulated** — see Section 7
  for why fabricating one from training-data recollection inside an audit whose premise is
  distrust of exactly this kind of unverified-but-precise number would be the wrong call.
- **Not investigated / not fixed:** whether `Quote.currency` (captured, e.g.
  `providers.py:289`, but never read downstream anywhere in the codebase — confirmed by
  exhaustive grep) ever actually disagrees with USD for these tickers live; this sandbox cannot
  reach Yahoo to check. `derive_extended`'s primary EV/multiple path (fed by `market_cap` passed
  in directly from the quote snapshot, not reconstructed from `price × shares`) is *not* exposed
  to this specific bug, because it never reconstructs market cap itself — it is currency-mixing
  contamination (Category B) that threatens that path instead.

### B. Currency issues

- **Confirmed and fixed this pass**, for the EDGAR-fallback enrichment path specifically.
  `pipeline/edgar_facts.py:96-98` already records a `unit`/`unit_recognized` field per XBRL
  observation with a comment stating "anything else is recorded with its unit so a consumer can
  reject it rather than silently mixing scales" — but no consumer ever did.
  `pipeline/edgar_enrichment.py::_shard_rows()` silently dropped the `unit` field when building
  its per-CIK fact index, so `_annual_facts_as_of`/`_all_facts_as_of`/`merge_edgar_fallback`
  merged a fact's raw numeric value regardless of what currency it was tagged in. Verified on
  disk: `pipeline/data/pit/fundamentals/*.jsonl` contains 40+ distinct non-USD unit strings
  (CNY, CAD, EUR, AUD, GBP, BRL, JPY, CHF, HKD, INR, and more) across 257 CIKs, and **Birkenstock
  Holding plc (BIRK, confirmed in `pipeline/config/advisor_universe.json`'s live 932-symbol
  list) has its entire EDGAR fact history tagged EUR** — there is no USD-tagged fact for that CIK
  at all. Any BIRK metric Yahoo left `None` would have been silently backfilled with a raw EUR
  figure sitting next to a USD `market_cap` inside `enterprise_value = market_cap + debt − cash`
  and every multiple derived from it.
- **Fix implemented:** `edgar_enrichment.py`'s `_shard_rows`/`_annual_facts_as_of`/
  `_all_facts_as_of` now carry the `unit` field through and reject (treat as unavailable, not
  as USD) any monetary fact not tagged `"USD"` and any share-count fact not tagged `"shares"`,
  including a missing/unrecognized unit — fail-closed, per the audit's own required behavior
  ("mark it unknown and fail validation"). Regression tests in `test_edgar_enrichment.py`
  reproduce the BIRK case directly.
- **Not fixed — no general currency-normalization layer exists anywhere in this codebase.**
  Exhaustive grep for `fx`, `exchange_rate`, `financialCurrency`, `non_usd`,
  `reporting_currency` across `pipeline/` returns nothing. `Quote.currency`
  (`providers.py:79,289,364`) and the Alpha Vantage snapshot's `"currency"` field
  (`fetch_advisor.py:865`) are captured and then never read by any other code — dead metadata,
  confirmed by grep. This means: (1) `derive_enterprise_multiples`'s primary path (market_cap
  from the quote, debt/cash from Yahoo's own statement frames, not EDGAR) has never been
  independently confirmed currency-consistent for TSM/ASML/NVO/ABB-style names, because this
  sandbox cannot reach Yahoo to check whether `info["currency"]` and `info["financialCurrency"]`
  ever disagree for these tickers; (2) no ratio anywhere in this pipeline is ever computed with
  an explicit currency check before dividing. Section 6 specifies the layer this needs.

### C. Units and magnitude issues

- **Confirmed live, partially fixed.** `dividend_yield` — see the executive summary's root
  cause #1. `plausibility.py`'s own `DECIMAL_RATIO_FIELDS` mechanism already exists for exactly
  this failure mode (`profit_margin`, `gross_margin`, `operating_margin`) but never covered
  `dividend_yield`. New rules added this pass (`dividend_yield_likely_percentage_not_decimal` at
  >50%, `negative_dividend_yield`) catch the unambiguous tail — 25 of 40 rows in the committed
  `advisor.json` — but **cannot** resolve the ambiguous remainder (a value of, say, `0.03` is
  genuinely indistinguishable between "3% as a decimal" and "0.03% as an already-multiplied
  percentage" from magnitude alone). See Section 8 for what a live-network pass needs to do to
  close this properly (inspect actual `yfinance`/Alpha Vantage responses per ticker and
  normalize at ingestion).
- **Confirmed, not fixed.** `net_debt`'s missing-cash handling (`fundamentals_extended.py:555`:
  `market_cap + (debt or 0) - (cash or 0)`) treats an unresolved `cash` identically to a
  genuine `$0` cash balance — defensible for keeping the additive formula from aborting
  entirely, but it means a company with truly unknown cash silently gets the same enterprise
  value as one with confirmed zero cash, with no flag distinguishing the two cases. Left as a
  remediation item (Section 10) rather than fixed in this pass, because a general fix (adding a
  `cash_unresolved`/`debt_unresolved` flag threaded through every consumer of `enterprise_value`)
  touches more call sites than this pass's fix budget covers safely.
- **Confirmed correct, checked specifically per the audit brief.** Capex sign handling: every
  FCF/capex-ratio derivation found (`fundamentals_extended.py:196-198,534,542`,
  `edgar_enrichment.py:158-160`, `pit_derive.py:191-193`) applies `abs(capex)` before
  subtracting, so the result is `operating_cash_flow − |capex|` regardless of whether the
  underlying vendor stores capex as a signed outflow or a positive magnitude. No sign-convention
  bug found in this area.

### D. Period mismatch issues

- **Confirmed, fixed this pass.** Yahoo's `revenueGrowth`/`earningsGrowth` are
  quarter-over-quarter year-on-year figures, not TTM. `canonical_metrics.py::yahoo_observations`
  used to tag them `is_ttm=True` while the sibling Alpha Vantage mapping for the identical
  underlying concept (`QuarterlyRevenueGrowthYOY`/`QuarterlyEarningsGrowthYOY`,
  `fetch_advisor.py:842-843,853-854`) already correctly tagged `is_ttm=False` with a
  `quarterly_not_ttm` flag. Any consumer of the `Observation.is_ttm` field would have read the
  same underlying concept as TTM or not depending purely on which provider happened to serve it.
  Fixed to match the honest Alpha Vantage convention; regression test added.
- **Confirmed, not fixed (documentation/naming debt, flagged for follow-up).** The published
  field is still named `trailing_revenue_growth` despite carrying quarterly-YoY data, not a
  trailing-twelve-month figure — the `is_ttm` metadata is now honest, but the field's own name
  is not. Renaming it touches `settings.json`, `scorer.py`'s `SCORED_METRICS`, schemas, and the
  frontend glossary/labels, which is a larger, coordinated rename this pass did not attempt.
- **Confirmed, not fixed.** `ev_to_sales` (annual-basis statement revenue) and `price_to_sales`
  (genuinely TTM, `priceToSalesTrailing12Months`) are published on the same row as two readings
  of "the sales multiple" with no field distinguishing which basis backs which number — a reader
  (or a downstream consumer) comparing two companies' sales multiples has no way to know if one
  is TTM and the other annual without reading source.
- **Confirmed correct, checked specifically.** The unused-in-production `pit_derive.py`
  TTM-construction logic (four-quarter summation, ±45-day tolerance, missing-Q4 synthesis) is
  genuinely rigorous, but has no live caller — noted as a real, well-built capability that
  nothing in the production scoring path actually uses; the live path's revenue/EBITDA/margin
  figures are annual-statement-basis, not TTM, wherever they come from `fundamentals_extended.py`
  rather than a direct TTM-native vendor field.

### E. Sign-convention issues

- **Confirmed and fixed this pass** — the scoring-model sign-inversion bug. See Section 4,
  Finding 1, for the full detail; summarized here because it is, at its root, a sign-convention
  defect: `scorer.py`'s `multiple_score`/`band_score` treated any negative EV-based multiple or
  P/B as the single worst possible score (5.0/15.0), when a negative EV-based multiple almost
  always means net cash exceeds market cap while the earnings/cash denominator is still
  positive (deep value, not distress), and negative book equity is routinely buyback-driven
  (a clean, shareholder-friendly balance sheet), not distressed. The codebase had already fixed
  this exact bug class once, for `net_debt_to_ebitda` (`lower_is_better_score`,
  `scorer.py:116-121`) and inside the shadow `CrossSectionalNormalizer` — but not in the
  champion `bands` scoring path, where 76%+ of the audit's target metrics actually run.
- **Confirmed correct, checked specifically.** No other sign-convention defect found in capex,
  debt-reduction, dividend, or repurchase fields during this pass's tracing.

### F. Share-count issues

- **Confirmed and fixed this pass.** `plausibility.implied_share_count_violations`
  (`plausibility.py:154-174`) — purpose-built to catch "a split-adjusted price paired with an
  unadjusted share count, and the reverse" — could never fire in production. Its own unit test
  (`test_plausibility.py`) passed `shares_outstanding` in by hand, creating false confidence
  that the guard was live; in the actual `collect()`/`enrich()` pipeline, no code path ever set
  `snapshot["shares_outstanding"]`. Fixed by adding `"shares_outstanding": safe(info,
  "sharesOutstanding")` to `fetch_prices.py::fetch_snapshot()` — deliberately Yahoo's own
  vendor-reported share count from the *same quote payload* as `marketCap`/`currentPrice`, not
  the balance-sheet "Ordinary Shares Number" row, because the latter is a different, ADR-
  inconsistent concept (Category A) that would have made this check fire on every healthy ADR
  for the wrong reason.
- **Confirmed, not further generalized.** `fundamentals_extended.py:32`'s `diluted_shares` alias
  falls back silently to `"Basic Average Shares"` when a diluted figure isn't present, blending
  basic and diluted share counts under one name with no flag distinguishing which was actually
  used. Left as a remediation item (Section 10): the fix (an explicit
  `diluted_shares_basis: "diluted"|"basic"` companion field) is straightforward but touches
  every consumer of `diluted_shares` and was judged lower-severity than the four fixes made in
  this pass.

### G. Enterprise-value issues

- **Confirmed correct, checked specifically.** The additive EV formula
  (`enterprise_value = market_cap + total_debt − cash`, `fundamentals_extended.py:551-555`)
  correctly nets cash against debt and treats a missing component as `$0` (see Category C for
  why that specific choice, while defensible, still loses a "we don't actually know" signal).
  Negative EV (net cash exceeding market cap) is arithmetically supported end to end; the bug
  was entirely in how the *scorer* interpreted a negative EV-derived multiple (Category E/
  Section 4), not in the EV calculation itself.
- **Not investigated.** Preferred equity, noncontrolling interests, pension liabilities, and
  finance leases — the audit brief's full EV checklist — are not present as separate line items
  anywhere in `derive_enterprise_multiples`, so this pipeline's EV is `market_cap + total_debt −
  cash` only, with no bank/financial-company-specific EV treatment (banks are suppressed from
  EV-based metrics entirely via `applicability_matrix.json`, which is the correct call for that
  category rather than a gap). Whether omitting preferred equity/NCI/pension liabilities
  materially affects specific names in the universe was not evaluated — flagged as a scope item
  for a follow-up pass, not asserted as either fine or broken.

### H. Corporate-action issues

- **Confirmed correct, checked specifically.** Prices are fetched with `auto_adjust=False`
  (`providers.py:177,222`) — split-adjusted, not dividend-adjusted, which is the right choice
  for a market-cap reconstruction (documented explicitly in `pit_shares.py:10-14`).
  `pit_shares.py` itself is a genuinely careful share-count/split reconciliation engine for the
  point-in-time backtest store, but (confirmed by grep) it is used only by `pit_market.py`, not
  by the live scoring path or by `valuation_history.py`/`backtest_historical.py` — the two sites
  with the actual ADR bug (Category A) never touch this reconciliation machinery, and it has no
  concept of a permanent ADR ratio distinct from a one-time split event regardless.
- **Not investigated** beyond the ADR case: reverse splits, mergers, and spin-offs were not
  specifically traced for a live failure case in this pass.

### I. Source/API mapping issues

- **Confirmed live, direct evidence of the same root cause as Category C.** Two different
  consumers of the identical `dividend_yield` field assume opposite unit conventions:
  `pipeline/rank_picks.py:64-66,161` treats it as a decimal fraction (`dy > 0.03`,
  `f"{dy*100:.1f}% yield"`); `src/lib/resolvedMetricSections.js:36` treats it as an
  already-percentage number (`` `${value.toFixed(2)}%` `` — the only metric in that file's
  entire formatting table that does not multiply by 100; every sibling yield/margin/return field
  in the same file uses the shared `pct = (value) => (value*100).toFixed(...)+'%'` helper). Given
  the live data confirms the stored value's convention is itself inconsistent row-to-row, *both*
  consumers are wrong for a meaningful share of the universe simultaneously, just for different
  rows.
- **Confirmed, fixed this pass.** `signals.json`/`scorer.run()` — the Congressional-trades
  scoring path — had no plausibility screening of any kind (`fetch_prices.py::build_prices()`
  never called `plausibility.screen`, unlike `fetch_advisor.py`'s `collect()`/`enrich()`), so
  every defect above reached `valuation_score` there completely unguarded. Fixed by wiring
  `screen_plausibility` into `build_prices()`'s per-ticker loop.

### J. Frontend formatting issues

- **Confirmed live** — see Category I above; the `dividend_yield` formatter in
  `src/lib/resolvedMetricSections.js:36` is the frontend half of that finding. Not changed in
  this pass: flipping it to multiply by 100 (matching every sibling field) would fix the rows
  where the stored value is a genuine decimal and *break* the rows where it's already a
  percentage number, since the underlying pipeline field's convention is not currently uniform.
  Fixing the display layer correctly requires fixing the source convention first (Section 8),
  not the other way around — displaying a wrong number more confidently is not a fix.
- Beyond this one field, frontend display/rounding logic for the other valuation metrics was
  not exhaustively audited in this pass (out of the time budget spent on the higher-severity
  backend findings above); flagged as a scope item, not asserted as clean.

## Section 3 — Fixes implemented in this pass

All of the following are committed with regression tests; none required new external
dependencies or config beyond one new registry file.

| # | File(s) | Fix | Test(s) |
|---|---|---|---|
| 1 | `pipeline/scorer.py` | `multiple_score`/`band_score` gained `exclude_nonpositive=True`, wired at every `VALUATION_MULTIPLES` call site in `_band_valuation_score`/`sales_multiple_score` (peg, forward_pe, sales_multiple, price_to_book, price_to_tangible_book, ev_to_ebitda, ev_to_ebit, ev_to_fcf). A negative value now excludes the metric (reweights its category) instead of scoring it as the worst tier. | `test_scorer.py`: `test_negative_ev_multiple_is_excluded_not_scored_worst`, `test_negative_price_to_book_is_excluded_not_scored_worst`, `test_champion_valuation_score_excludes_negative_ev_to_ebitda` |
| 2 | `pipeline/edgar_enrichment.py` | `_shard_rows`/`_annual_facts_as_of`/`_all_facts_as_of` now carry and enforce the XBRL `unit` field; a monetary concept must be tagged `USD` and a share-count concept `shares`, or it is treated as unavailable rather than merged. | `pipeline/tests/test_edgar_enrichment.py` (new), reproducing the real BIRK CIK and a mixed-currency-statement case; existing `test_asfiled_backtest.py` fixtures updated to carry the now-required unit field |
| 3 | `pipeline/fetch_prices.py` | Added `"shares_outstanding": safe(info, "sharesOutstanding")` to the live snapshot (Yahoo's own vendor figure, same quote payload as `marketCap`/`currentPrice`), making `plausibility.implied_share_count_violations` live for the first time. Also wired `plausibility.screen()` into `build_prices()`, closing the previously-unscreened `signals.json` path. | `pipeline/tests/test_fetch_prices.py` (new) |
| 4 | `pipeline/plausibility.py` | Added `dividend_yield_likely_percentage_not_decimal` (>0.5) and `negative_dividend_yield` (<0) rules. | Exercised directly against the committed `public/data/advisor.json` by the existing `test_plausibility.py::LivePayloadTests`, updated to document the 25/40-row finding explicitly rather than weakening the check to dodge it |
| 5 | `pipeline/canonical_metrics.py` | `yahoo_observations`: `trailing_revenue_growth`/`quarterly_eps_growth` now `is_ttm=False` with a `quarterly_not_ttm` flag, matching the Alpha Vantage mapping for the identical concept. | `test_canonical_v2.py::test_yahoo_revenue_and_eps_growth_are_labeled_quarterly_not_ttm` |
| 6 | `pipeline/adr_registry.py` (new), `pipeline/config/adr_listings.json` (new), `pipeline/valuation_history.py`, `pipeline/backtest_historical.py`, `pipeline/build_quality_value_screen.py` | A known, unreconciled ADR (TSM, ASML, NVO, ABB — registered but deliberately left `verified: false`, see Section 7) now blocks the `price × statement-derived-shares` reconstruction in both call sites rather than silently overstating market cap; a ticker not in the registry is unaffected; a future *verified* ratio would convert rather than block. | `test_adr_registry.py` (new), `test_valuation_history.py` (3 new cases), `test_backtest_historical.py::AdrShareCountGuardTests` (new) |

Full relevant test suite (`pipeline/tests/test_scorer.py`, `test_plausibility.py`,
`test_canonical_v2.py`, `test_edgar_enrichment.py`, `test_fetch_prices.py`,
`test_adr_registry.py`, `test_valuation_history.py`, `test_backtest_historical.py`,
`test_asfiled_backtest.py`, `test_dead_cohort_pit.py`) passes after these changes, plus the
full `pipeline/tests` suite for regressions elsewhere in the codebase.

## Section 4 — Scoring model audit

Champion path confirmed: `settings.json: "normalization_mode": "bands"` →
`scorer._band_valuation_score`. `cross_sectional`/`fixed_feature` exist only as shadow
challengers, never selected.

| Factor | Metric | Direction as coded | Sector-conditioned? | Missing-data handling | Data-quality risk this pass found |
|---|---|---:|---|---|---|
| Forward P/E | `forward_pe` | lower-better, `multiple_score` | **Yes** (`forward_pe_by_sector`) | excluded, category renormalized | Fixed: negative case now excluded (was already separately screened by `plausibility.py`'s `negative_forward_pe`, so this is defense-in-depth, and the only live effect is on the previously-unscreened `signals.json` path) |
| Sales multiple | `ev_to_sales`/`price_to_sales` | lower-better, `multiple_score` | **Yes** (`ev_to_sales_by_sector`/`price_to_sales_by_sector`) | excluded, reweighted | Fixed: negative case now excluded |
| EV/EBITDA | `ev_to_ebitda` | lower-better, `multiple_score` | **No** — one universal band for every sector | excluded, reweighted | Fixed: negative case now excluded (was the flagship sign-inversion bug) |
| EV/EBIT | `ev_to_ebit` | lower-better, `multiple_score` | **No** | excluded, reweighted | Fixed: negative case now excluded |
| EV/FCF | `ev_to_fcf` | lower-better, `multiple_score` | **No** | excluded, reweighted | Fixed: negative case now excluded |
| P/B | `price_to_book` | lower-better, `band_score` | **No** | excluded, reweighted | Fixed: negative case now excluded |
| P/Tangible-Book | `price_to_tangible_book` | lower-better, `band_score` | Sector *gate*, not a band | excluded, reweighted | Fixed: negative case now excluded |
| PEG | `peg` | lower-better, `band_score` | No | excluded, reweighted | Fixed: negative case now excluded |
| FCF yield | `free_cash_flow_yield` | **higher-better**, correctly under `profitability` not `valuation` | n/a | excluded, reweighted | None — direction confirmed correct |
| Dividend yield | `dividend_yield` | **not scored at all** | n/a | n/a — absent from `SCORED_METRICS` | Displayed in the Glossary's "Valuation" term group with no note that it's display-only, unlike ROTCE/FFO/reverse-DCF, which the Model Card explicitly flags as informational (not fixed this pass — documentation gap, not a scoring bug, since it carries zero weight either way) |

**Finding 1 (fixed this pass):** the sign-inversion bug detailed in Section 2.E/3. Concretely,
against the live `settings.json` bands, a −2.5x EV/EBITDA (net-cash, hyper-cheap) used to score
5.0 while a genuinely overpriced +30x scored 15.0 — the net-cash company read as *worse* than
the overpriced one. `ev_to_ebitda` alone carries 27% of the valuation category × 28% of the
composite × 78% fundamentals weight ≈ 5.9% of the total published score; a name hitting this
branch could swing roughly 90 points on that one input.

**Finding 2 (not fixed — sector-conditioning gap, documented not corrected):** 76% of valuation
category weight (`ev_to_ebitda` 27%, `ev_to_ebit` 12%, `ev_to_fcf` 18%, `peg` 9%,
`price_to_book` 5%, `price_to_tangible_book` 5%) uses one universal band for every sector,
despite `docs/MODEL-CARD.md` describing the champion as "sector/industry-band" scoring. Only
`forward_pe` (15%) and the sales multiple (9%) are actually sector-banded. The existing
`sector_percentile_modifier` (a capped ±3-point post-blend adjustment) ranks names within an
already sector-band-biased distribution; it cannot correct the underlying band mis-calibration.
Not fixed in this pass — recalibrating six sets of sector-specific bands is a scoring-weight
change subject to this repository's own IC-validation gate (`docs/VALIDATION-METHODOLOGY.md`),
not a same-pass code fix.

**Finding 3 (partially addressed):** `plausibility.py` had no dedicated check for
`price_to_book`, `price_to_tangible_book`, `peg`, or any EV-based multiple's sign/magnitude
before this pass, and the `signals.json` path had no plausibility screening of any kind. Both
gaps are closed as of Section 3's fixes 1 and 3 respectively (the sign gap via the scorer fix
rather than a new plausibility rule, since exclusion is the more precise fix for a
metric-definition question).

**Finding 4 (documented, not fixed):** `dividend_yield` is fetched and displayed but carries
zero scoring weight — confirmed absent from `SCORED_METRICS` and every `metric_weights`
category. Not a scoring-correctness bug (an unscored field can't corrupt the score), but the
Glossary listing it alongside scored valuation metrics with no "informational only" annotation
is a documentation-accuracy gap worth closing alongside the unit-convention fix in Section 8,
since fixing the display without fixing the "is this even used" confusion leaves half the
problem.

**Finding 5 (documented, not fixed):** the fundamentals-internal `0.65 + 0.35×coverage`
confidence multiplier inside `_band_valuation_score` is computed but never actually applied to
the published `advisor.json` composite (`advisor_engine.build_research` reads
`fundamental_parts["raw_score"]`, the pre-multiplier value) — its own docstring's "still live
here" is accurate for the function in isolation but could mislead a future reader into assuming
the champion score is coverage-shrunk twice at this layer. A documentation correction, not a
behavior change (changing the behavior now would be an unreviewed scoring change against this
repository's own validation gate).

No look-ahead bias was found in the live scoring path. The only look-ahead risk identified is
latent, not live: `backtest_historical.py::build_snapshot`'s `allow_current_shares` parameter
defaults to `True`, which is correct for none of the current callers (all three explicitly pass
`False`) but is a landmine for a future ad-hoc caller that omits the argument. Not changed in
this pass (changing a public default is a larger-blast-radius edit than the fixes made here);
flagged for the remediation plan.

## Section 5 — Canonical normalized financial-data schema (specification)

No existing schema in `pipeline/schemas/*.schema.json` declares `currency`, `units`, or
`share_basis` on any field (confirmed by exhaustive grep); every schema's `additionalProperties`
is `true`, so adding fields is non-breaking. The following is a specification for a future
migration, not implemented in this pass (implementing it fully means re-deriving every published
field with unit metadata attached, which is a substantially larger, independently-reviewable
change than the scoped bug fixes above):

```
{
  "ticker": "TSM",
  "issuer_identifier": {"cik": "0001046179", "lei": null},
  "listing_identifier": {"exchange": "NYSE", "security_type": "ADR", "adr_ratio": 5,
                          "adr_ratio_verified": true, "adr_ratio_source": "<citation>"},
  "quote_currency": "USD",
  "reporting_currency": "TWD",
  "unit_scale": "raw",
  "period": {"type": "annual", "start": "2024-01-01", "end": "2024-12-31"},
  "filing_date": "2025-03-14",
  "source_timestamp": "2026-08-30T12:00:00Z",
  "raw_source_field": "Total Revenue",
  "raw_value": 2894308000000,
  "raw_value_currency": "TWD",
  "normalized_usd_value": null,
  "fx_rate": null,
  "fx_source": null,
  "fx_timestamp": null,
  "formula_version": "enterprise_multiples_v3",
  "validation_status": "unavailable_currency_unverified",
  "confidence_level": "unknown"
}
```

`normalized_usd_value`/`fx_rate`/`fx_source`/`fx_timestamp` are `null` by design until Section 6's
layer exists — the schema's job is to make "this needs conversion and none has happened" a
visible, queryable state rather than an implicit one, per the audit's own required behavior:
"Do not infer missing unit, currency, share-basis, or period metadata. Mark it unknown and fail
validation."

## Section 6 — Currency-normalization layer (specification, not implemented)

Not built in this pass because: (1) this pipeline has no FX rate provider configured at all
today (FRED integration is macro-regime-only, confirmed by reading `pipeline/fred.py`), so
building the layer would mean also selecting and integrating a new external data source, which
is a materially larger and more consequential change than a bug fix; (2) the sandbox's network
restriction means any such integration could not be tested against a live rate in this session.
Specification for a follow-up pass:

- A `pipeline/fx.py` module fetching daily close FX rates for every reporting currency observed
  in `pipeline/data/pit/fundamentals/*.jsonl` (confirmed list: at minimum CNY, CAD, EUR, AUD,
  GBP, BRL, JPY, CHF, HKD, INR, plus TWD/DKK for TSM/NVO once their EDGAR facts are captured),
  cached and PIT-logged the same way `pit_store.py` already logs everything else.
  - **Documented policy for which FX date to use:** a statement-period value converts at the FX
    rate as of the statement's own period-end (or fiscal-year-end for an annual figure), *never*
    the stock-price date's FX rate — the audit's own required behavior ("Do not use a stock-price
    FX conversion rate for a financial-statement period without documenting that choice") is a
    single named policy here, so `normalize_to_usd(value, currency, as_of=period_end)` is the only
    signature callers get; there is no default that would let a caller quietly reach for the
    wrong date.
- Every ratio-computing function (`derive_enterprise_multiples`, `derive_net_debt_to_ebitda`,
  etc.) takes normalized-USD inputs only; a component whose currency cannot be resolved raises
  (or, matching this codebase's existing `plausibility.py` convention, is dropped with a
  recorded violation) rather than being silently combined.
- `Quote.currency`/the Alpha Vantage snapshot's `"currency"` field — captured today and never
  read — become the trigger: any ticker whose quote currency is not `"USD"`, or whose EDGAR/
  Yahoo statement `financialCurrency` disagrees with its quote currency, routes through this
  layer before any cross-field ratio is computed.

## Section 7 — ADR ratio registry: implemented infrastructure, deliberately unpopulated data

`pipeline/adr_registry.py` + `pipeline/config/adr_listings.json` are implemented and wired into
both confirmed bug sites (Section 3, fix 6). Every entry (TSM, ASML, NVO, ABB — the four
foreign-domiciled names confirmed present in the live 932-symbol universe) ships with
`"verified": false` and `"adr_ratio": null` **on purpose**. TSM's 1-ADS-to-5-ordinary-shares
ratio, for instance, is a widely and stably documented fact — but this session has no live
network access to re-verify it against a primary source (the depositary bank's own ratio
disclosure, or the issuer's 20-F "Description of American Depositary Shares" item) before
writing it into a file another engineer, or this pipeline itself, would trust unread. Shipping a
plausible-looking number without that verification would be committing exactly the failure mode
this entire audit exists to find, one level removed. `is_unreconciled_adr()` treats
`verified: false` as "ratio unknown" and blocks the reconstruction rather than guessing — a
strictly safer default than either the pre-existing silent 5x-style overstatement or a
fabricated ratio.

**Action required from an environment with real network access, before this can convert instead
of merely blocking:** for each of TSM, ASML, NVO, ABB (and any future addition), check the
issuer's current 20-F "Description of American Depositary Shares" item or the depositary bank's
ratio disclosure page, fill in `adr_ratio`/`ordinary_currency`/`source`, and flip
`verified: true`. `test_adr_registry.py::test_config_file_ships_with_every_entry_unverified`
enforces that a verified entry always carries a `source` citation, so this cannot regress
silently.

## Section 8 — External benchmark comparison

**Not executable from this environment.** The audit brief's Section 5 calls for comparing at
least 20 companies (spanning US/foreign/ADR/dual-listed/multi-currency/banks/REITs/
semiconductors/SaaS/capital-intensive/negative-earnings/negative-FCF/recently-split names)
against at least two independent external sources per company (SEC filings, exchange data,
established market-data providers). This sandbox's outbound proxy blocks both Yahoo Finance and
SEC EDGAR outright — the same restriction `docs/LIMITATIONS.md`'s "Verification" section
already documents for this codebase's own test suite ("this sandbox also cannot reach Yahoo
Finance"). No fabricated comparison is presented here; a fabricated one would be exactly the
kind of precise-looking, unverified number this audit's own required behavior forbids
("Prefer 'unavailable' over a misleading value").

**What a follow-up pass with real network access should run, concretely, using
infrastructure already built in this pass:**

1. For each of the four confirmed ADRs (TSM, ASML, NVO, ABB) plus a same-sized sample of the
   audit brief's other named categories (a bank, a REIT, a name with negative earnings, a name
   with negative FCF, a recently-split name — all of which exist somewhere in the 932-symbol
   `advisor_universe.json`), pull a live `yfinance.Ticker(...).info` payload and record
   `currentPrice`, `marketCap`, `sharesOutstanding`, `currency`, and `financialCurrency` side by
   side with the same company's SEC EDGAR `companyfacts` JSON.
2. Run `pipeline/adr_registry` verification: confirm each ADR's ratio against the issuer's 20-F
   and populate `adr_listings.json` per Section 7.
3. Run the new `_unit_acceptable` filter (Section 3, fix 2) against a fresh EDGAR pull for BIRK
   specifically and confirm it still reports zero enrichable USD facts — the expected, correct
   outcome given BIRK's entire history is EUR-tagged, not a bug to chase further.
4. Cross-check `market_cap`, `enterprise_value`, and every multiple in Section 1's lineage table
   against a second, independent source (e.g. the company's own investor-relations fact sheet or
   a stock-data terminal) for each sampled name, flagging any discrepancy over 2% per the audit
   brief's own tolerance.
5. For `dividend_yield` specifically: pull the *actual* live `yfinance` response shape for 10+
   dividend payers across different `yfinance`/data-source vintages to determine definitively
   whether the decimal/percentage split correlates with anything resolvable at ingestion (e.g. a
   specific field name change, a specific vendor version) rather than being genuinely
   per-request-inconsistent — this determines whether Section 8's fix is a parsing correction or
   requires per-row provenance tracking.

## Section 9 — Automated tests added this pass

- `pipeline/tests/test_scorer.py`: 3 new tests for the sign-inversion fix (Section 3, fix 1),
  including one full end-to-end `valuation_score()` case proving a negative EV/EBITDA now scores
  identically to a missing one.
- `pipeline/tests/test_edgar_enrichment.py` (new file): currency-unit filter unit tests,
  including the real BIRK CIK reproduced directly, and a mixed-currency-statement case.
- `pipeline/tests/test_asfiled_backtest.py`: existing fixtures updated to carry the now-required
  `unit` field (no behavior change to the tests themselves — point-in-time visibility logic is
  unaffected by the currency filter when every fact is USD, as these fixtures are).
- `pipeline/tests/test_fetch_prices.py` (new file): `shares_outstanding` lineage and the
  `implied_share_count_violations` check actually firing on a synthetic stale-share-count case.
- `pipeline/tests/test_plausibility.py`: `dividend_yield` rules exercised directly against the
  committed `public/data/advisor.json`; the existing "no mass rejection" regression test updated
  to document the 25/40-row finding explicitly (see the test's own comment) rather than weakened
  to pass silently.
- `pipeline/tests/test_canonical_v2.py`: 1 new test for the `is_ttm`/`quarterly_not_ttm` fix.
- `pipeline/tests/test_adr_registry.py` (new file): registry policy tests (unregistered ticker
  passes through unaffected, unverified ADR blocks, verified ratio converts, config-file
  integrity check that a verified entry always cites a source).
- `pipeline/tests/test_valuation_history.py`: 3 new tests (unreconciled ADR produces no
  multiples rather than a wrong market cap; an unregistered ticker is unaffected; a
  hypothetical verified ratio converts correctly, with the exact 5x arithmetic shown).
- `pipeline/tests/test_backtest_historical.py`: new `AdrShareCountGuardTests` class mirroring
  the above for the backtest engine's own `build_snapshot()`.

Every listed test file was run and passes; the full `pipeline/tests` suite was run for
regressions beyond the directly-touched files.

## Section 10 — Prioritized remediation plan

**Immediate (this pass, done):** the six fixes in Section 3 — sign-inversion, currency-unit
filtering for EDGAR fallback, dead share-count guard revival, dividend-yield unit-format tail
rejection, is_ttm mislabeling, and ADR reconstruction blocking.

**Short-term (data-model and validation, not yet done):**
- Resolve `dividend_yield`'s unit convention at the source (Section 8, item 5) — this is the
  single highest-value remaining fix, since it is confirmed live and universe-wide.
- Verify the four ADR ratios (Section 7) from an environment with real network access, so the
  registry can convert instead of merely blocking.
- Build the currency-normalization layer (Section 6) so `derive_enterprise_multiples`'s primary
  (non-EDGAR-fallback) path is provably currency-consistent for foreign issuers, not merely
  unexamined.
- Add a `cash_unresolved`/`debt_unresolved` flag to `enterprise_value`'s missing-component
  handling (Section 2.C) so "unknown" and "confirmed zero" stop being indistinguishable.
- Add an explicit `diluted_shares_basis` flag where `fundamentals_extended.py` silently falls
  back from diluted to basic shares (Section 2.F).
- Split `ev_to_sales` (annual) and `price_to_sales` (TTM) with an explicit basis field so a
  reader can't compare two companies' "sales multiples" across different periods unknowingly
  (Section 2.D).
- Rename or annotate `trailing_revenue_growth`/`quarterly_eps_growth` to stop claiming a TTM
  basis they don't have (Section 2.D) — a coordinated rename across `settings.json`, `scorer.py`,
  schemas, and the frontend glossary.
- Sector-condition the 76% of valuation weight that currently uses one universal band per metric
  (Section 4, Finding 2) — subject to this repository's own IC-validation gate before promotion,
  not a same-pass code change.
- Fix `backtest_historical.py::build_snapshot`'s `allow_current_shares` default (currently
  `True`, a look-ahead landmine for any future caller that omits the argument) to a safe default,
  or require it be passed explicitly.

**Long-term (monitoring, benchmark reconciliation, alerting):**
- Execute Section 8's benchmark-comparison plan from an environment with real network access,
  and wire its cross-checks into a recurring CI job (mirroring how `check_ui_weights.py`/
  `validate_documentation_claims.py` already gate on doc/code drift) rather than a one-time
  manual pass.
- Extend `plausibility.py`'s cross-source-agreement mechanism (currently `market_cap`/`price`
  only) to `enterprise_value` and every EV-based multiple once the currency layer exists, so a
  genuine cross-provider disagreement on those fields is caught the same way it already is for
  market cap.
- Add a periodic audit of `pipeline/data/pit/fundamentals/*.jsonl` for new non-USD-tagged CIKs
  as the universe changes, so a newly-added foreign issuer is flagged before its first
  publish, not discovered after.
