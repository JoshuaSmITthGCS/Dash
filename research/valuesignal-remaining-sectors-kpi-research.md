# Sector-Specific Operating KPI Layers for ValueSignal: Research for the Remaining GICS Sectors

Research brief accepted into this repository as a source document. Not itself validated code
or a specification — see `docs/MODEL-CARD.md`'s "Operating-KPI text extraction" section for
what actually shipped from it (a narrow, off-by-default slice: same-store sales, net interest
margin, efficiency ratio, ARPU, postpaid churn) and what remains open (everything else below).
A companion, earlier worked-example brief ("Building Sector-Specific KPI Layers for
ValueSignal... Semiconductors, SaaS, and Hardware," covering Micron, Datadog, and Dell as
worked cycle-stage examples) made the same argument for those three sub-industries and is
summarized here rather than filed separately, since its recommendations are a subset of this
document's Technology section.

## TL;DR

- Across all nine remaining sectors, the operating KPIs analysts actually anchor on are almost
  never available in standardized SEC XBRL — the GAAP financials are tagged, but same-store
  sales, ARPU/churn, NIM, FFO/AFFO, same-store NOI, book-to-bill, capacity factor, rate base,
  and MW leasing all live in 10-K/10-Q MD&A prose and 8-K earnings-release supplementals, so
  ValueSignal needs a text/table-extraction pipeline (or a normalized vendor feed such as S&P
  Global Visible Alpha) as the backbone of these layers.
- Each sub-industry has 3–6 canonical metrics: telecom (ARPU, churn, net adds), media/internet
  (MAU/DAU, engagement, subscriber ARPU), retail (comps, inventory turns, sales/sq ft),
  restaurants (SSS, AUV, restaurant-level margin), banks (NIM, efficiency ratio, ROTCE, CET1,
  NPLs/PCL), capital markets (AUM, net flows, fee rate/revenue yield), REITs (FFO/AFFO,
  same-store NOI plus subtype-specific spreads/coverage/MW), SaaS (ARR, NRR, Rule of 40), semis
  (utilization, book-to-bill, design wins), utilities (rate base growth, allowed vs. earned
  ROE), IPPs (capacity factor, spark spread, PPA mix), and chemicals (capacity utilization,
  spreads, volume).
- Suppression matters as much as inclusion: EV/EBITDA and Altman Z-Score are meaningless for
  banks/broker-dealers; P/E and EV/EBITDA are inapplicable for REITs (use P/FFO, P/AFFO; EV/rate
  base is the utility analog); DSO/inventory-days are inapplicable to banks, utilities, and
  asset managers; generic FCF-yield and margin ratios are distorted for capital-intensive
  cyclicals (semis, chemicals, homebuilders) at cycle peaks/troughs.

## Key findings

1. **The XBRL gap is the central engineering constraint.** The SEC's own guidance confirms that
   operating metrics such as "same-store sales" calculated from GAAP revenues are not even
   classified as non-GAAP measures and are disclosed in MD&A, not the tagged financial
   statements. Custom XBRL tags exist "if and only if an appropriate tag does not exist in the
   standard list." Nearly every high-value operating KPI in this report requires parsing
   HTML/PDF supplementals, press releases (8-K Exhibit 99.x), and earnings-call transcripts —
   not a standard XBRL financial-statement pull.
2. **Financials (banks, capital markets) are the most standardized "operating" data** because
   regulators force disclosure — NIM, efficiency ratio, CET1, ROTCE, NPLs, and PCL appear in
   earnings releases and bank regulatory filings (Call Reports / FR Y-9C) in reasonably
   structured form, though not in the standard US-GAAP XBRL taxonomy.
3. **REITs need a subtype layer, not one REIT layer.** FFO/AFFO/same-store NOI/occupancy are
   universal, but office (leasing spreads, WALT, TI/LC), retail (tenant sales/sf, occupancy cost
   ratio), industrial (mark-to-market rent, retention), residential (blended lease-rate growth,
   turnover), healthcare (EBITDARM coverage, REVPOR, payor mix), and data center (MW bookings,
   backlog, interconnection, churn) each have distinct value drivers.

## Details by sector (condensed — canonical KPIs, source feasibility, suppression notes)

**1. Communication Services.** *Telecom carriers:* ARPU, postpaid churn (<~1%/month strong),
net subscriber additions, capex intensity/maintenance capex, EV/subscriber & EV/home-passed —
all MD&A/earnings-supplemental text extraction except capex (partially XBRL). Suppress:
lease-unadjusted EV/EBITDA, FCF yield distorted by lumpy spectrum auctions. *Media/internet:*
MAU/DAU and stickiness, paid subscribers & ARPU/ARPPU, churn/reactivation, engagement, content
spend/amortization — text extraction (amortization partially XBRL). Suppress: raw ARPU when free
users dominate (use ARPPU); GAAP P/E for high-content-amortization or pre-profit platforms.

**2. Consumer Discretionary.** *Retail/apparel:* comps, inventory turnover (derivable from
XBRL COGS/inventory), sales/sq ft, gross margin & GMROI, e-commerce penetration — mostly text
extraction; inventory turns and DSO are meaningful here (unlike financials) but must be
sub-industry-benchmarked. *Restaurants:* SSS split traffic vs. ticket, AUV, restaurant-level
margin, unit growth/franchise mix, prime cost (target <~60% of revenue) — all text extraction.
*Autos:* unit volume/ASP, incentives per unit, gross profit per unit, warranty cost rate, EV mix
and utilization — mostly text extraction. *Homebuilders:* net new orders, cancellation rate,
backlog (units/value) & conversion, community count/absorption, adjusted gross margin, land
position — text extraction; suppress Altman Z (heavy inventory/land, high structural leverage)
and P/E at cycle extremes in favor of price-to-book/price-to-tangible-book.

**3. Consumer Staples.** Organic sales growth split volume vs. price/mix, gross margin/pricing
power, category share, volume elasticity, A&P spend ratio — mostly text extraction (share from
Nielsen/IRI). Same-store sales applies to grocery specifically, not branded manufacturers.

**4. Financials (banks, capital markets — not insurance).** *Banks:* NIM (~2.5–3.0% healthy),
efficiency ratio (JPMorgan's FY2024 adjusted overhead ratio 52%, per its 4Q24 supplement), ROTCE,
CET1 ratio, NPL ratio/PCL & coverage, loan/deposit growth & cost of funds — earnings
release/regulatory, semi-structured. Suppress: EV/EBITDA, EBITDA margins, DSO, inventory days,
Altman Z, FCF yield are all inapplicable — valuation uses P/TBV vs. ROTCE and P/E. *Capital
markets/asset managers:* AUM, net flows/organic growth, fee rate (bps; passive ~15bps),
operating margin (30–45% traditional, 50–60%+ alternatives), fee-related earnings/performance-fee
mix, trading VaR/net trading revenue — text extraction. Suppress: EV/EBITDA and inventory/DSO
inapplicable; valued on P/FRE, %-of-AUM, and EV/EBITDA only among peers (7–10x traditional,
15–25x alternatives).

**5. Industrials.** *Aerospace & defense:* book-to-bill (>1.0 = growing backlog), funded/unfunded
backlog, program/segment margins, FCF conversion — text extraction. *Machinery/diversified:*
organic growth, book-to-bill/orders/backlog, incremental/decremental margins, aftermarket mix —
text extraction. *Transportation/logistics:* operating ratio (Class I railroads ~60–65% per
Oliver Wyman; several ≤60% in Q4 2025), revenue per ton-mile/carload, volume, load
factor/RASM/CASM for airlines — text extraction. *Business services:* organic growth,
retention/renewal, revenue per employee/utilization, book-to-bill for project firms.

**6. Real Estate/REITs.** Universal layer: FFO/AFFO per share (Nareit-defined; AFFO not
standardized), same-store NOI growth, occupancy, P/FFO & P/AFFO, NAV premium/discount, AFFO
payout ratio, net debt/EBITDA — supplemental/MD&A text extraction (FFO/AFFO occasionally
carry custom XBRL tags but remain non-GAAP). Subtype layer (all text extraction, none
standardized): office (leasing spreads, WALT, TI+LC/sf, SNO pipeline, % investment-grade
tenants); retail/mall (tenant sales/sf, occupancy cost ratio, re-leasing spread, foot traffic
third-party); industrial/logistics (rent change on rollover, mark-to-market/loss-to-lease,
retention, development pipeline yield); residential (blended lease-rate growth new vs. renewal,
turnover, loss/gain-to-lease, occupancy ~95–96%); healthcare (EBITDARM/EBITDAR coverage,
self-reported/unaudited; SHOP occupancy; REVPOR/ExpPOR; payor mix); data center (MW
bookings/backlog, interconnection revenue, cash/GAAP renewal spreads and churn, pipeline MW
%-pre-leased). Suppress: P/E and EPS inapplicable to REITs; cap rate and NAV are the
property-level anchors.

**7. Technology.** *SaaS:* ARR/MRR growth (top-quartile ~45% per McKinsey), NRR (>120% premium,
top quartile ~130%), Rule of 40 (derivable from already-computed growth + margin), gross/net
dollar churn, CAC payback/LTV:CAC (rarely disclosed), gross margin (75%+ signals true software) —
text extraction; Rule of 40 is the one metric in this whole document computable with zero new
data, since it is just a composite of two metrics ValueSignal already derives. Suppress: GAAP
P/E near-useless for growth-stage SaaS; use EV/revenue, EV/ARR. *Semiconductors* (see also the
companion Micron worked example): fab/capacity utilization (optimal >85%), book-to-bill, design
wins, gross margin (fab-depreciation- and ASP/yield-driven), ASP & yield per wafer, inventory
days (derivable from XBRL) — mostly text extraction/earnings-call. Suppress: EV/EBITDA and P/E
distorted across the cycle (peak margin → low multiple, trough → high/negative); normalize to
mid-cycle. *Hardware:* unit shipments & ASP, gross margin & mix, backlog/book-to-bill, attach
rate/recurring mix — text extraction (see also the companion Dell worked example: AI-server
mix dilutes blended gross margin even as backlog and revenue hit records).

**8. Utilities.** *Regulated electric/gas:* rate base growth (~6–9% CAGR targets; sector capex
projected $1.4T 2025–2030 per Morningstar DBRS), allowed vs. earned ROE (e.g. FPL's 10.95%
authorized ROE, Florida PSC settlement approved Nov 2025), regulatory-jurisdiction quality
(qualitative/third-party), capex plan, customer/load growth (now boosted by data-center load) —
rate-case/MD&A text extraction. Suppress: not EV/EBITDA in isolation; FCF structurally negative
during capex super-cycles, so FCF yield is misleading — dividend coverage and rate-base growth
matter more. *IPPs/merchant generation:* capacity factor (EIA 2024: nuclear 92%, gas 59.9%, coal
42.4%, wind 34.3%, solar 23.4%), spark/dark spread, PPA vs. merchant mix, capacity-market
revenue, heat rate — text extraction. Suppress: rate-base metrics inapplicable to merchant IPPs;
use EV/EBITDA on mid-cycle spreads and contracted-cash-flow DCF instead.

**9. Basic Materials (ex-precious-metals mining).** *Chemicals:* capacity utilization/operating
rate, product spread over feedstock, volume growth, EBITDA margin & ROCE (specialty 18–28%
EBITDA/12–18x vs. commodity 5–8x), specialty-vs-commodity mix — text extraction. Suppress:
normalize P/E and EV/EBITDA to mid-cycle for commodity chemicals (S&P: revenue can fall ~7%
average/23% peak-to-trough, EBITDA margin ~15%/28% swing in downturns). *Metals
(steel/aluminum/copper):* capacity utilization, realized price/premium, cash cost per ton,
shipments — text extraction. *Paper/packaging:* operating rate, price realization by grade,
volume/box shipments, integration/cost per ton — text extraction. All three: cyclical: normalize
P/E and EV/EBITDA to mid-cycle; price-to-book and cost-curve position are better cycle anchors.

## Recommendations (as staged in the original brief)

1. Build the extraction pipeline first; treat XBRL as secondary for operating KPIs. Only
   leverage/valuation ratios and a few derivable metrics (inventory turns, DSO where
   applicable, capex) come cleanly from XBRL. Set a "populated" threshold at >80% coverage of a
   sub-industry's universe over trailing four quarters before activating a KPI in production
   ranking.
2. Stage the rollout by data tractability: Phase 1 (banks, capital markets, REITs, SaaS —
   regulator-forced or widely-templated disclosure); Phase 2 (retail/restaurants/homebuilders/
   telecom — well-templated supplementals); Phase 3 (chemicals/metals spreads, IPP spark
   spreads, utility rate base, semi utilization — hardest, most prose-bound, several need
   third-party commodity/price data).
3. Encode subtype routing — REITs, chemicals, utilities, and communication services must
   branch on sub-industry before selecting the KPI set and suppression list.
4. Implement the suppression matrix explicitly (see per-sector notes above).
5. Flag non-standardized and self-reported metrics (AFFO, lease mark-to-market, EBITDARM
   coverage) as "requires normalization; not cross-comparable without adjustment" so percentile
   ranks carry a confidence flag.
6. Consider a normalized vendor feed (e.g. S&P Global Visible Alpha) for consensus
   operating-KPI comp tables where building extraction is uneconomic, especially Phase 3.

## Caveats

- Bank/broker profitability thresholds and several benchmark values (postpaid churn <~1%, SaaS
  top-quartile NRR ~130%, chemical downturn declines) come from methodology guides,
  McKinsey/BCG, and rating-agency notes — indicative benchmarks, not hard rules; re-verify
  against primary company disclosures before production use.
- Recency/quarter-specific figures cited from earnings transcripts and aggregators are
  illustrative of disclosure format, not audited data points, except where traced to a named
  primary source (JPMorgan's 4Q24 supplement, the Florida PSC settlement, Morningstar DBRS,
  DOE/EIA, Oliver Wyman).
- XBRL continues to evolve; some operating metrics may become tag-eligible over time, so the
  "text-extraction-required" classification should be revisited periodically.
- Self-reported operator data (healthcare-REIT EBITDARM coverage, industrial mark-to-market) is
  explicitly disclaimed as unaudited by issuers and is not comparable across companies without
  normalization.
- Tech hardware and a few industrial sub-verticals (business services) were synthesized from
  adjacent sources rather than dedicated searches; validate those KPI sets against primary
  sell-side methodology before production deployment.
