# ValueSignal: Sub-Industry KPI Registry & Thematic Exposure Methodology

Research brief accepted into this repository as a source document for a phased implementation.
It is not itself validated code or a specification — see `docs/MODEL-CARD.md`'s "Sector-specific
replacement metrics" and "Thematic exposure" sections for what has actually shipped from it and
what remains open. Benchmarks and figures below are quoted from external sources as of the
document's own August 2026 cutoff and are practitioner rules of thumb unless cited otherwise —
see this file's own "CAVEATS" section.

## TL;DR

- **The generic ratio set breaks hardest in five places, and each needs a dedicated valuation multiple, not a suppression patch:** financials (use P/TBV↔ROTCE for banks, EV/AUM + organic growth for asset managers, MLR + P/E for managed care), real estate (P/FFO, P/AFFO and NAV-to-cap-rate — never P/E, EV/EBITDA or P/B), midstream/MLPs (EV/EBITDA and P/DCF with distribution coverage), regulated utilities (P/E on regulated EPS + rate-base growth + EV/rate-base), and capital-intensive cyclicals/transports (EV/EBITDAR for airlines; book-to-bill/backlog/FCF conversion for A&D; adjusted P/B for homebuilders). For these, forward P/E, EV/EBITDA, ROIC, current ratio and FCF-based screens are actively misleading and should be suppressed or replaced.
- **For thematic exposure, measure from filings, not narrative:** ASC 280 segment revenue, ASC 606 disaggregation, customer-concentration (the "10% customer" rule), and backlog/RPO are the auditable anchors; the peer-reviewed NLP methods to formalize your text layer are Sautner–van Lent–Vilkov–Zhang (Journal of Finance 2023, >10,000 firms, 34 countries, 2002–2020) and Hassan–Hollander–van Lent–Tahoun (QJE 2019). Index-provider practice (MSCI Relevance Score, FactSet RBICS, STOXX, S&P Kensho) resolves exposure to a revenue-share number — copy that discipline.
- **"Already priced in" is best judged with reverse DCF (Mauboussin/Rappaport market-implied growth), multiple-expansion decomposition, and valuation-percentile-vs-own-history — all momentum-free.** The strongest empirical warning is Ben-David, Franzoni, Kim & Moussawi (RFS 2023, NBER 28369): specialized/thematic ETFs "lose about 30% (risk-adjusted)" over their first five years, ~-3.1%/yr alpha, "driven by the overvaluation of the underlying stocks at the time of the launch." As of 2026, Reshoring looks late/past-peak, AI Infrastructure and GLP-1 mid-cycle with pushback emerging, and Rearmament/Grid/Water earlier but with the liquid large-caps already re-rated.

## KEY FINDINGS

**Part 1 organizing principle.** Your suppression layer is correct in spirit but incomplete: for whole sectors the problem is not that a few metrics are noisy, it is that the *entire equity-multiple frame* is wrong. Where earnings are an accounting artifact (REITs, banks, MLPs, insurers) or where the balance sheet *is* the business (banks, homebuilders, asset managers), swap the multiple rather than percentile-ranking a broken one. Prioritized below are the sub-industries where the generic set is most misleading.

**Part 2 organizing principle.** Exposure, linkage, and pricing are three separate questions and your platform is right to keep momentum out of all three. Exposure and linkage are *measurable from disclosure*; "priced-in" is *estimable from valuation math without price trend*. The academic record is unambiguous that thematic baskets are systematically overpriced at the moment they become investable products — so your "connected, not yet re-rated" category is the single most defensible output you produce, provided it is gated on filing evidence.

## DETAILS — PART 1: SUB-INDUSTRY KPI REGISTRY

Format per entry: **KPIs** (name · calc · why · benchmark) → **Multiple** → **Suppress** → **Data feasibility** → **Value-trap**. Benchmarks marked "rule of thumb" are practitioner conventions, not established facts.

### COMMUNICATION SERVICES

**Integrated / wireless carriers.** KPIs: *Postpaid phone net adds* (subs added ex-churn; the demand signal analysts lead on); *postpaid churn* (monthly deactivations/base; <1.0% good, >1.3% weak — rule of thumb); *ARPU / ARPA* (service revenue per unit/account); *service-revenue EBITDA margin*; *capex intensity* (capex/revenue; 15–18% ex-spectrum). Multiple: **EV/EBITDA** and **EV/(EBITDA–capex)**; equity FCF/dividend coverage for the high-payout names. Suppress: **P/E** (heavy D&A and spectrum amortization distort it), **P/B** (spectrum/goodwill), **current ratio** (structurally <1 by design), **asset growth** (spectrum purchases swamp it), **gross margin** (not how telcos are run). Feasibility: net adds/churn/ARPU are 8-K Exhibit 99 supplementals and earnings calls, not XBRL; capex and EBITDA derivable from XBRL. Value-trap: high dividend yield + "cheap" EV/EBITDA masks spectrum/network capex that must be refunded perpetually; leverage (net debt/EBITDA 3–4x) makes equity optically cheap.

**Cable & satellite.** KPIs: *broadband net adds* (now the entire equity story — video is a melting ice cube); *ARPU*; *homes passed / penetration*; *broadband EBITDA margin*. Multiple: **EV/EBITDA**, **EV/(EBITDA–capex)**. Suppress same as telecom plus **revenue growth** read naively (video losses mask broadband economics). Feasibility: net adds in supplementals/calls. Value-trap: fixed-wireless and fiber overbuilders are structurally compressing terminal broadband ARPU — a low multiple can be a correct discount, not a bargain.

**Towers & fiber infrastructure (many are REITs).** KPIs: *AFFO/share growth*; *organic tenant billings growth* (same-tower revenue; 5%+ good); *churn*; *tenants per tower / colocation*. Multiple: **P/AFFO** and **NAV** (see REIT section). Suppress: **P/E, EV/EBITDA on GAAP, P/B, current ratio, ROIC** — real-estate depreciation and long-lived assets make them meaningless. Feasibility: AFFO and tenant billings in supplementals. Value-trap: carrier consolidation (e.g., Sprint/T-Mobile) drives multi-year churn that a trailing yield hides.

**Media & entertainment (studios/streaming).** KPIs: *streaming subscriber net adds*; *streaming ARPU*; *DTC segment operating income/margin* (the pivot to profitability is the whole debate); *content spend / amortization*; *studio backlog*. Multiple: **EV/EBITDA** and increasingly **DTC-profitability-adjusted SOTP**. Suppress: **P/E** (content amortization and impairments), **FCF yield** read in isolation (content cash spend is lumpy), **gross buybacks**. Feasibility: subs/ARPU in supplementals; content amortization derivable from XBRL/10-K. Value-trap: subscriber growth bought with content spend that never earns its cost of capital.

**Interactive media & advertising platforms.** KPIs: *DAU/MAU and engagement*; *ad revenue growth*; *ARPU by geography*; *operating margin*. Multiple: **EV/EBITDA**, **P/E** (these are genuinely profitable), **EV/Sales** for the faster growers. Suppress: **P/B, P/TBV** (intangible-driven), **dividend yield**, **net debt/EBITDA** (net cash). Feasibility: DAU/ARPU on calls/supplementals; financials in XBRL. Value-trap: regulatory (privacy/antitrust) and AI-disruption risk not in trailing multiples.

**Video games & interactive entertainment.** KPIs: *bookings / net bookings* (sales adjusted for deferral — the real demand metric, not GAAP revenue); *live-services / recurrent spending %*; *MAU*; *pipeline/release slate*. Multiple: **EV/EBITDA**, **P/E on bookings-based EPS**. Suppress: raw **revenue growth** and **P/E on GAAP** (deferred revenue accounting makes both jump around release cycles), **inventory days**. Feasibility: bookings are non-GAAP, in press releases/calls. Value-trap: a hit title inflates trailing earnings right before a content drought — the classic "lowest P/E at peak."

**Publishing / advertising agencies.** KPIs: *organic revenue growth* (ex-FX, ex-M&A — the core agency metric); *net new business*; *EBITA margin*; *staff cost ratio*. Multiple: **EV/EBITA**, **P/E**. Suppress: **P/B** (goodwill-heavy from roll-ups), **capex/depreciation** (asset-light). Feasibility: organic growth in MD&A/calls. Value-trap: structural loss of ad budgets to platforms/in-housing; cheap multiple is often terminal decline.

### CONSUMER DISCRETIONARY

**Broadline & specialty retail.** KPIs: *same-store / comparable sales* (ex-new-stores; the anchor); *gross margin & inventory-to-sales*; *sales per square foot*; *e-commerce penetration*. Multiple: **EV/EBITDA**, **P/E**. Suppress: nothing wholesale, but read **inventory days trend** as a *leading* signal (rising inventory pre-warns margin markdowns) rather than a valuation input; **asset growth** distorted by leases (ASC 842). Feasibility: comps in press releases; inventory in XBRL. Value-trap: comp "beats" driven by inflation/AUR not traffic; peak-margin trough-multiple in expansions.

**Apparel & footwear brands.** KPIs: *DTC vs wholesale mix*; *gross margin*; *inventory freshness/days*; *brand-heat proxies (full-price sell-through)*. Multiple: **EV/EBITDA**, **P/E**. Suppress: **P/TBV** (brand value is off-balance-sheet). Feasibility: mix in segments (ASC 280); sell-through only on calls. Value-trap: fashion cyclicality — one bad season resets the multiple; wholesale channel stuffing inflates near-term revenue.

**E-commerce / internet retail.** KPIs: *GMV*; *gross profit growth* (better than revenue given 1P/3P mix); *fulfillment cost/order*; *take rate* (marketplace). Multiple: **EV/Gross profit**, **EV/EBITDA**, **EV/Sales** for growth names. Suppress: **P/E** (deliberate margin suppression), **P/B**. Feasibility: GMV/take-rate on calls/supplementals. Value-trap: GMV growth without contribution-margin path.

**Restaurants (QSR vs casual).** KPIs: *same-store sales* (traffic vs check split); *unit growth / net new units*; *restaurant-level margin (four-wall)*; *franchise mix* (highly franchised = higher multiple). Multiple: **EV/EBITDA**; franchised models command materially higher multiples — heavily-franchised chains trade at more than double the EV/EBITDA of lightly-franchised chains, and premier QSR franchisors reach ~20x+ while a franchisee like Carrols sat near 5.8x. Suppress: **P/B** (asset-light franchisors carry little tangible equity; franchisees carry leased assets), **current ratio**. Feasibility: SSS/unit growth in press releases. Value-trap: QSR check-driven comps in inflation mask traffic declines; casual dining is structurally challenged.

**Hotels, resorts & cruise lines.** KPIs: *RevPAR* (revenue per available room = occupancy × ADR) and *net cruise yields*; *ADR/occupancy*; *net-unit/berth growth*; *management/franchise fee mix* (asset-light hotel brands). Multiple: **EV/EBITDA** (and EV/EBITDAR where leases matter); asset-light brands on **P/E/FCF**. Suppress: **P/E** for cruise lines (post-COVID leverage/D&A), **net debt/EBITDA** read statically (cruise balance sheets recovering). Feasibility: RevPAR/yields in supplementals. Value-trap: cruise lines' recovery earnings + high leverage = optical cheapness with equity subordinated to debt.

**Gaming & casinos.** KPIs: *GGR (gross gaming revenue)*; *property EBITDAR*; *hold %*; *regional vs Macau/Vegas mix*; *digital/iGaming growth*. Multiple: **EV/EBITDAR** (leases/master-lease REIT separations). Suppress: **P/B, current ratio, P/E** (D&A-heavy). Feasibility: GGR from regulators (third-party) + segment EBITDAR. Value-trap: Macau concession/regulatory risk; regional saturation.

**Homebuilders & building products.** KPIs: *net orders* (leading demand signal); *backlog units/value*; *gross margin* (20–25% healthy — rule of thumb); *cancellation rate*; *community count*; *land/lots controlled (owned vs optioned)*; *ROE/ROIC*. Multiple: **P/adjusted book value** (assets marked toward fair value) plus **P/E** and **EV/EBITDA** capturing backlog. Suppress: **EV/FCF and FCF yield** (cash flow swings inversely to growth as land spend consumes cash in upturns), **DSO**, **accruals**. Feasibility: orders/backlog/margin in press releases; land in MD&A. Value-trap: classic peak-cycle — lowest P/E and best margins occur at the cycle top just before orders roll; cash generation looks best when the business is shrinking.

**Automakers.** KPIs: *unit deliveries/mix*; *ASP*; *auto gross margin ex-credits*; *EV mix/margin*; *incentives per unit*. Multiple: **EV/EBITDA**, **P/E on mid-cycle** (deeply cyclical). Suppress: **trailing P/E at peak**, **P/B** less useful, treat **captive-finance arm** separately (it distorts consolidated ratios — ROIC, debt/equity, interest coverage). Feasibility: units/mix in supplementals; finco in segments. Value-trap: peak-earnings/trough-P/E; EV transition capex.

**Auto parts & dealers.** KPIs (dealers): *same-store sales, F&I gross per unit, parts-and-service (fixed ops) absorption*; (parts): *content per vehicle, book-to-bill, aftermarket vs OEM mix*. Multiple: **EV/EBITDA**, **P/E**. Suppress: **P/B** for asset-light distributors. Value-trap: parts suppliers tied to OEM production cycles; dealer F&I margins normalize from post-COVID peaks.

**Leisure products & education services.** Leisure (boats/RVs/equipment): *retail registrations, dealer inventory/channel weeks, unit shipments* — highly cyclical, use **EV/EBITDA on mid-cycle**, suppress trailing P/E at peak. Education: *enrollment/starts, revenue per student, regulatory (Title IV / cohort default)* — **P/E/EV-EBITDA**; regulatory risk dominates. Feasibility: registrations third-party; enrollment on calls.

### CONSUMER STAPLES

**Packaged food & meats.** KPIs: *organic sales growth (volume vs price/mix)*; *gross margin*; *protein spread* (meatpackers — livestock cost vs meat price, third-party data). Multiple: **EV/EBITDA**, **P/E**. Suppress: for commodity meat processors, **operating-margin trend and P/E** are swamped by the spread cycle (treat like a cyclical, echoing your gold-miner logic). Feasibility: organic growth on calls; spreads from USDA (third-party). Value-trap: private-label share loss; protein-spread peak earnings.

**Beverages (soft drinks vs alcoholic).** KPIs: *organic revenue (volume vs price/mix)*; *unit-case/depletion volume*; *shipment-vs-depletion gap* (spirits — channel inventory signal); *premiumization mix*. Multiple: **EV/EBITDA**, **P/E** (staples command premium multiples for defensiveness). Suppress: **P/B**. Feasibility: depletions on calls/third-party (Nielsen/IRI). Value-trap: GLP-1 volume-demand overhang on alcohol/sugary drinks; shipments outrunning depletions.

**Household & personal products.** KPIs: *organic sales (price/mix vs volume)*; *gross margin*; *market share by category*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: price-led growth masking volume declines to private label.

**Tobacco.** KPIs: *cigarette volume decline rate*; *net pricing*; *reduced-risk-product (RRP) revenue mix and growth*. Multiple: **P/E** and **dividend/FCF yield** (income vehicle). Suppress: **revenue growth** naively (structural volume decline is normal), **asset growth**. Feasibility: volumes/RRP on calls. Value-trap: high yield + low P/E is the definition — the question is whether RRP replaces combustible cash flows before terminal decline; a "value trap by design."

**Food distributors.** KPIs: *case volume growth*; *gross-profit-per-case*; *independent-restaurant mix* (higher margin); *operating leverage*. Multiple: **EV/EBITDA**. Suppress: **gross margin %** in isolation (low by nature; GP/case matters), **P/B**. Value-trap: thin margins mean small volume misses swing earnings hard.

**Grocery & staples retail.** KPIs: *identical/comp sales*; *gross margin & shrink*; *fuel contribution* (where applicable). Multiple: **EV/EBITDA, P/E**. Suppress: **P/B** partly. Value-trap: comps inflated by food inflation; margin pressure from hard discounters.

**Agricultural products.** KPIs: *crush/processing margins, volume, price realizations* — commodity-cycle driven. Multiple: **EV/EBITDA on mid-cycle**. Suppress: **P/E at peak, operating-margin trend, 3y FCF growth** (commodity price swamps them — your gold-miner suppression logic applies directly). Feasibility: margins from crop/oilseed markets (third-party). Value-trap: peak-crush-margin trough-multiple.

### FINANCIALS

**Regional and money-center/universal banks.** KPIs: *ROTCE* (net income/avg tangible common equity — the single best value-creation metric; strong franchises sustain high-teens to 20%+); *NIM*; *efficiency ratio* (noninterest expense/revenue; ~50–55% strong, JPMorgan-class ~52%); *CET1 ratio* (well-capitalized >10%; regulatory min 4.5%); *net charge-offs / provisions and NPL coverage*; *deposit cost/mix (cost of funds)*; *TBV/share growth*. Multiple: **P/TBV paired with ROTCE** via the justified P/TBV = (ROTCE − g)/(r − g) framework — the ROTCE↔P/TBV regression is the core FIG tool (e.g., 15% ROTCE, 3% g, 10% r ⇒ ~1.7x justified P/TBV; 18% ROTCE ⇒ ~2.1x). Secondary **P/E**. Suppress: **EV/EBITDA and EV/anything** (EV meaningless for banks — deposits/debt are raw material, not financing), **current ratio, interest coverage, net debt/EBITDA, gross margin, FCF yield, cash conversion, capex/depreciation, Altman Z, Piotroski F** (all designed for non-financials). Feasibility: NIM/efficiency/CET1/NCOs in XBRL and call reports (highly standardized). Value-trap: cheap P/TBV on a low-ROTCE bank is *correct* pricing, not a bargain; unrealized AOCI securities losses (rate risk) can hollow out tangible book; credit costs lag — cheapest just before the credit cycle turns.

**Consumer finance & credit cards.** KPIs: *net charge-off rate and delinquency (30+/90+)*; *loan/receivables growth*; *net interest margin/yield*; *reserve/allowance ratio (CECL)*; *purchase volume*. Multiple: **P/E** and **P/TBV↔ROTCE**. Suppress: same bank suppressions (EV/EBITDA, coverage, Altman Z, current ratio). Feasibility: NCOs/delinquencies in supplementals + XBRL. Value-trap: low P/E at peak credit quality just before losses normalize up; reserve releases flatter EPS unsustainably.

**Mortgage finance / mortgage REITs.** KPIs: *book value/share* (the whole game for mREITs), *net interest spread, prepayment (CPR), leverage, hedge position*; (originators) *gain-on-sale margin, lock volume*. Multiple: **P/book (tangible)** for mREITs; **P/E** for originators. Suppress: **EV/EBITDA, dividend yield read naively** (mREIT yields are often unsustainable and return-of-capital), **P/E** for mREITs. Value-trap: double-digit mREIT yields precede book-value erosion and dividend cuts in rate/spread shocks.

**Capital markets / investment banks.** KPIs: *ROTCE*; *comp/revenue ratio*; *trading VaR and revenue mix*; *investment-banking backlog/pipeline*; *book value growth*. Multiple: **P/TBV↔ROTCE**, **P/E on normalized** (earnings are volatile). Suppress: EV/EBITDA, coverage, current ratio, Altman Z. Value-trap: peak-cycle trading/IB revenue → trough multiple.

**Asset managers.** KPIs: *AUM and net flows (organic growth = net flows/beginning AUM — the key differentiator)*; *fee rate/revenue yield* (15–70 bps by asset class; passives far lower); *operating margin* (30–45% traditional, 50–60%+ alternatives); *base vs performance fee mix*. Multiple: **P/E** (purest), **EV/EBITDA**, **EV/AUM** (only vs close peers; rule-of-thumb ~1–3% of AUM, alternatives richer). Suppress: **P/B, P/TBV** (asset-light), **net debt/EBITDA** less relevant, **current ratio**. Feasibility: AUM/flows/fee rate in supplementals. Value-trap: market-beta inflates AUM/earnings at cycle tops; structural fee compression and passive share loss make trailing multiples optimistic — outflows compound.

**Exchanges & financial-data providers.** KPIs: *recurring/subscription revenue mix*, *organic revenue growth*, *ASV (annual subscription value)*, *volumes* (for transaction-based). Multiple: **EV/EBITDA, P/E** (premium multiples for recurring-revenue moats). Suppress: **P/B**. Value-trap: transaction-volume peaks (volatility spikes) inflate trailing earnings.

**Insurance brokers.** KPIs: *organic revenue growth* (the anchor; mid-single-digit+ good), *EBITDA margin* (high-20s to 30s%), *retention*. Multiple: **EV/EBITDA** and **P/E** (asset-light, capital-light — NOT valued like underwriters). Suppress: **P/B/P/TBV** (goodwill-heavy roll-ups), insurance-specific reserve/float metrics (brokers take no underwriting risk). Feasibility: organic growth on calls. Value-trap: roll-up multiples depend on cheap M&A funding; organic slowdown de-rates fast.

**Life insurance.** KPIs: *ROE and operating ROE*, *book value/share ex-AOCI*, *statutory capital/RBC ratio*, *spread income, VNB (value of new business)*, *sensitivity to rates/equities*. Multiple: **P/book (ex-AOCI)** and **P/E on operating EPS**; embedded-value where disclosed. Suppress: **EV/EBITDA, FCF yield, current ratio, Altman Z, Piotroski, cash conversion, gross/operating margin, capex/depreciation** — all non-financial constructs; combined ratio (that is P&C). Feasibility: RBC/statutory in regulatory filings; operating EPS non-GAAP on calls. Value-trap: rate-sensitive spread compression; AOCI swings distort GAAP book.

**Reinsurance.** KPIs: *combined ratio* (but with far more cat volatility than primary P&C), *ROE, tangible book value/share growth* (the true scorecard across cycles), *reserve development, rate-on-line / pricing cycle*. Multiple: **P/tangible book** (the discipline metric) and **P/E on normalized**. Suppress: same insurer suppressions as the P&C list, but note reinsurance TBV/share is far lumpier — normalize across cat years. Value-trap: soft-market pricing + benign cat years produce peak earnings and a trough multiple right before the cycle turns.

### HEALTHCARE (ex-hospitals)

**Large-cap pharma.** KPIs: *patent-cliff/LOE exposure* (share of revenue losing exclusivity through 2030), *pipeline rNPV and Phase III catalysts*, *R&D productivity*, *peak-sales estimates per asset*. Multiple: **sum-of-the-parts / rNPV**. Secondary **P/E, EV/EBITDA**. Suppress: **terminal P/E, PEG**, **asset growth**. Feasibility: LOE dates public; peak-sales are analyst estimates. Value-trap: optically low P/E approaching a major LOE is a melting asset, not value.

**Biotech (commercial vs clinical-stage).** Commercial-stage: *launch trajectory, net revenue, gross-to-net, script trends* → **P/E / EV/revenue**. Clinical-stage: *cash runway, Phase catalysts, probability of success, cash/share* → **rNPV / cash-adjusted**. Suppress for clinical-stage: essentially all generic profitability/valuation ratios. Value-trap: binary trial risk; "cheap" on cash is illusory if a readout can zero the equity.

**Medical devices & equipment.** KPIs: *organic revenue growth, procedure volumes, R&D/sales, gross margin*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: reimbursement cuts; procedure-volume normalization post-COVID.

**Life-science tools & diagnostics.** KPIs: *organic growth, consumables/instrument mix, book-to-bill, recurring %*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: post-pandemic biopharma-funding and COVID-testing air pockets create tough comps.

**Managed care / health insurers.** KPIs: *Medical Loss Ratio (MLR)* (medical costs/premiums; ACA floors 80–85%), *medical-cost trend, membership growth by segment, premium yield, admin/SG&A ratio, adjusted EPS*. Multiple: **P/E** on adjusted EPS. Suppress: **EV/EBITDA, gross margin, current ratio, FCF yield read naively, Altman Z, Piotroski, inventory/DSO**. Feasibility: MLR/membership in supplementals + CMS/state filings. Value-trap: MLR spikes hit earnings suddenly; regulatory risk.

**Pharmacy & healthcare distributors.** KPIs: *revenue growth (low-margin passthrough), gross-profit-per-script/unit, generic deflation/inflation, operating margin*. Multiple: **P/E, EV/EBITDA**. Suppress: **gross margin %** in isolation, **P/B**, **revenue growth** naively. Value-trap: opioid/legal liabilities; thin margins amplify disruptions.

**Healthcare IT.** KPIs: *bookings, recurring/SaaS mix, net revenue retention, backlog/RPO*. Multiple: **EV/Sales, EV/EBITDA, Rule-of-40**. Suppress: **P/E** for the not-yet-profitable, **P/B**. Value-trap: long hospital sales cycles; implementation risk.

### INDUSTRIALS

**Aerospace & defense (primes vs suppliers).** KPIs: *book-to-bill*, *backlog and total estimated contract value*, *free-cash-flow conversion*, *program margins/EACs*. Multiple: **EV/EBITDA** (~20x for primes) and **P/E** and **FCF yield**; suppliers ~7–12x EBITDA / 1.2–2x revenue. Suppress: **revenue growth read short-term**, **current ratio**, **PEG**. Feasibility: book-to-bill/backlog well disclosed in 8-K/10-Q. Value-trap: EAC writedowns on fixed-price programs; backlog quality (funded vs unfunded IDIQ) varies.

**Machinery & capital equipment.** KPIs: *orders/book-to-bill, backlog, dealer inventory, aftermarket/parts mix, incremental margins*. Multiple: **EV/EBITDA on mid-cycle**, **P/E on normalized**. Suppress: **trailing P/E at peak**, **FCF yield at peak**. Value-trap: peak-earnings/trough-multiple; channel-inventory destocking.

**Electrical equipment.** KPIs: *organic growth, orders/backlog, book-to-bill, data-center/electrification exposure, backlog coverage*. Multiple: **EV/EBITDA, P/E**. Suppress: static **P/B**. Value-trap: much of the electrification order book converts to revenue in 2027–2028 — a duration trade already priced.

**Building products & construction materials (cement/aggregates).** KPIs: *volume/pricing, EBITDA/ton, capacity utilization, backlog*. Multiple: **EV/EBITDA**. Suppress: **P/E at peak**, **P/B** partly. Value-trap: housing/nonres-cycle peak earnings.

**Engineering & construction.** KPIs: *backlog and book-to-bill, project margins, contract mix*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**, **current ratio**. Value-trap: fixed-price project writedowns; low-quality backlog.

**Railroads.** KPIs: *operating ratio*, *volumes/carloads, core pricing, fuel surcharge*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B** partly, **asset growth**. Value-trap: OR improvement from cost cuts can mask volume/service deterioration.

**Truckload & LTL trucking.** KPIs: *operating ratio, tonnage/shipments, revenue per hundredweight, load counts*. Multiple: **EV/EBITDA, P/E on mid-cycle**. Suppress: **trailing P/E at freight-cycle peak**. Value-trap: peak earnings/trough multiple; LTL structurally better than TL.

**Air freight & logistics.** KPIs: *volumes, yield/revenue-per-piece, network density, ground vs express mix*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: e-commerce-driven peak volumes normalize.

**Airlines.** KPIs: *RASM/PRASM, CASM and CASM-ex-fuel, load factor, yield, break-even load factor*. Multiple: **EV/EBITDAR** and **P/E on mid-cycle**; **P/TBV** as distress floor. Suppress: **P/E at peak, P/B/P/TBV read naively, net debt/EBITDA static, current ratio**. Value-trap: cyclical + operationally leveraged + fuel-exposed — the textbook peak-earnings/trough-multiple cyclical.

**Marine shipping.** KPIs: *spot/time-charter rates, fleet utilization, days, NAV of vessels*. Multiple: **EV/EBITDA and P/NAV**. Suppress: **P/E at peak, operating-margin trend, FCF growth**. Value-trap: peak charter rates → trough multiple; newbuild oversupply.

**Waste management.** KPIs: *volume/price (core price), landfill capacity/airspace, recycling commodity exposure, EBITDA margin*. Multiple: **EV/EBITDA**. Suppress: **P/B**. Value-trap: rare — the trap is overpaying for a quality compounder.

**Staffing & HR services.** KPIs: *organic revenue/billings growth, gross margin (perm vs temp mix), SG&A leverage*. Multiple: **EV/EBITDA, P/E on mid-cycle**. Suppress: **trailing P/E at peak**. Value-trap: peak-employment earnings; cyclical.

**Professional/consulting services.** KPIs: *organic growth, utilization, bill rates, headcount, book-to-bill/backlog*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: discretionary-spend cyclicality.

**Industrial distribution.** KPIs: *daily sales/organic growth, gross margin, working-capital turns, e-commerce mix*. Multiple: **EV/EBITDA, P/E**. Suppress: **gross margin %** naively. Value-trap: industrial-cycle peak; destocking.

### ENERGY (ex-E&P)

**Refining & marketing.** KPIs: *crack spreads / refining margin per barrel, throughput/utilization, complexity, capture rate*. Multiple: **EV/EBITDA on mid-cycle**. Suppress: **trailing P/E at peak**, **operating-margin trend, FCF growth, PEG**. Value-trap: refiners look cheapest exactly when cracks are unsustainably high.

**Midstream / pipelines & MLPs.** KPIs: *distributable cash flow (DCF) and distribution coverage ratio, fee-based revenue %, net debt/EBITDA, volumes/contract profile (MVCs)*. Multiple: **EV/EBITDA** and **P/DCF**. Suppress: **P/E**, **dividend/distribution yield used as the valuation metric**, **current ratio, gross margin, FCF yield read naively**. Value-trap: a very high distribution yield often signals an impending cut.

**Oilfield services & drilling.** KPIs: *rig count/utilization and dayrates, pricing, backlog (offshore), incremental margins*. Multiple: **EV/EBITDA on mid-cycle**. Suppress: **trailing P/E at peak, FCF growth, margin trend**. Value-trap: peak-activity/trough-multiple.

**Integrated oil majors.** KPIs: *upstream production/reserves, downstream+chemicals mix, cash flow from operations, reinvestment rate, breakeven oil price, distribution coverage*. Multiple: **EV/EBITDA, P/CF, FCF/distribution yield at mid-cycle oil**. Suppress: **P/E at peak oil, P/B** partly. Value-trap: commodity-price peak earnings; energy-transition terminal-value debate.

**Coal.** KPIs: *realized price/ton, cost/ton, met vs thermal mix, contracted volumes, reserves*. Multiple: **EV/EBITDA (low, terminal-decline discount), FCF yield**. Suppress: **P/E at peak, growth metrics, terminal multiples**. Value-trap: high FCF yield + low multiple is often correct pricing for a declining asset.

**Uranium.** KPIs: *contracted vs spot price exposure, production cost, pounds under long-term contract, reserve grade/life*. Multiple: **EV/EBITDA, P/NAV**. Suppress: **P/E, margin trend, FCF growth**. Value-trap: spot-price momentum masks contract-book realities.

### MATERIALS (ex-precious-metals mining)

**Commodity chemicals.** KPIs: *spread (product price − feedstock), operating rates/utilization, volume*. Multiple: **EV/EBITDA on mid-cycle**. Suppress: **trailing P/E at peak, operating-margin trend, 3y FCF growth, PEG**. Value-trap: peak-spread trough-multiple.

**Specialty chemicals.** KPIs: *organic growth, volume/price, R&D/sales, EBITDA margin, formulation/innovation mix*. Multiple: **EV/EBITDA**. Suppress: **P/B** partly. Value-trap: "specialty" names that are really commoditizing.

**Agricultural chemicals / fertilizers.** KPIs: *realized nutrient prices, cash cost/ton, operating rate, gas-cost position*. Multiple: **EV/EBITDA on mid-cycle, FCF yield**. Suppress: **trailing P/E at peak, margin trend**. Value-trap: peak-fertilizer-price trough-multiple.

**Industrial gases.** KPIs: *pricing, volumes, backlog/on-site project pipeline, EBITDA margin, ROC*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: quality compounders rarely screen cheap.

**Steel.** KPIs: *steel spread / metal margin, capacity utilization, shipments, mini-mill vs integrated cost position*. Multiple: **EV/EBITDA on mid-cycle**. Suppress: **trailing P/E at peak, margin trend, FCF growth**. Value-trap: the definitive peak-earnings/trough-P/E cyclical.

**Aluminum & copper/base metals.** KPIs: *realized LME price, C1 cash cost, volumes, grade, reserve life*. Multiple: **EV/EBITDA, P/NAV**. Suppress: **P/E at peak, margin trend, 3y FCF growth, PEG**. Value-trap: peak-metal-price trough-multiple.

**Paper, packaging & containers.** KPIs: *containerboard/pulp prices, volumes, integration, operating rates*. Multiple: **EV/EBITDA**. Suppress: **P/E at peak**. Value-trap: box-demand and price cycle.

**Lithium & battery materials.** KPIs: *realized lithium price, cash cost, volume/expansion, resource grade/life, offtake contracts*. Multiple: **EV/EBITDA, P/NAV**. Suppress: **P/E, margin trend, FCF growth**. Value-trap: extreme price cyclicality — a "cheap" multiple on peak lithium prices is a trap.

### REAL ESTATE (all REITs: the multiple is P/FFO, P/AFFO, and NAV vs cap rate)

Shared suppression list for every REIT sub-type: **P/E, EV/EBITDA on GAAP, P/B/P/TBV, ROIC/ROE on GAAP earnings, current ratio, FCF yield, cash conversion, gross margin**. Shared metrics: **FFO** (Nareit: net income + real-estate D&A − property-sale gains), **AFFO/FAD/CAD**, **AFFO payout ratio** (<80% sustainable), **NAV = property NOI/cap rate − net debt**, **net debt/EBITDA**. Universal value-trap: a high dividend yield / low P/FFO usually reflects a correct discount for structural demand risk or rising cap rates — cross-check NAV discount and AFFO payout coverage.

Sub-type-specific KPIs: **Office** — leasing spreads, occupancy, WALT, TI/leasing capex, sublease overhang. **Retail/mall** — occupancy, releasing spreads, sales/sq ft, occupancy cost ratio. **Industrial/logistics** — same-store NOI, releasing spreads, occupancy (premium P/FFO). **Residential/apartment** — same-store NOI, occupancy, blended lease-rate growth. **Healthcare** — payer/operator mix, coverage ratios, senior-housing occupancy. **Data center** — leasing/bookings, power capacity, churn (premium multiple). **Net lease** — WALT, occupancy, cap-rate spread, rent escalators, tenant credit; AFFO≈FFO. **Self-storage** — same-store revenue/NOI, occupancy, ECRI. **Hotel** — RevPAR, ADR, occupancy, brand/management mix (AFFO 70–85% of FFO). **Timber** — harvest volumes, log/lumber prices, timberland acreage/HBU value. **Specialty (towers/gaming/billboards)** — see towers under Comm Services; gaming REITs: master-lease coverage. **Real estate services/brokerage** — not a REIT: transaction volumes, commission mix → **P/E, EV/EBITDA**.

### TECHNOLOGY (beyond semis/SaaS/hardware)

**IT services & consulting.** KPIs: *organic constant-currency revenue growth, bookings/book-to-bill, backlog, utilization, attrition, deal TCV*. Multiple: **P/E, EV/EBITDA**. Suppress: **P/B**. Value-trap: GenAI disruption to labor-arbitrage model.

**Payment processors & merchant acquirers.** KPIs: *total payment volume (TPV) and growth, net revenue, net take rate, volume retention, embedded/software mix*. Multiple: **EV/net revenue** and **EV/EBITDA / P/E** for mature acquirers. Suppress: **gross revenue / P/S on gross**, **P/B**, **gross margin** naively. Value-trap: headline gross-revenue "growth" that is passthrough.

**EMS & components.** KPIs: *book-to-bill, capacity utilization, inventory turns, customer concentration, margin*. Multiple: **EV/EBITDA, P/E on mid-cycle**. Suppress: **gross margin** naively, **trailing P/E at peak**. Value-trap: customer-concentration and cyclical inventory corrections.

**Networking equipment.** KPIs: *product orders/book-to-bill, backlog, software/recurring mix, gross margin, hyperscaler exposure*. Multiple: **EV/EBITDA, P/E**. Suppress: **P/B**. Value-trap: lumpy hyperscaler order cycles.

**Cybersecurity software.** KPIs: *ARR and ARR growth, net revenue retention, net new ARR, gross margin, Rule of 40, RPO/backlog*. Multiple: **EV/ARR** and **EV/Sales**, **EV/FCF** for the mature. Suppress: **P/E**, **P/B, P/TBV**. Value-trap: decelerating NRR with a still-premium EV/ARR.

**Data center/colocation & cloud infrastructure.** Multiple: **EV/EBITDA, P/FFO** (REITs), **EV/Sales** (cloud). Suppress: **P/E**, REIT-inappropriate ratios. Value-trap: capex intensity + AI-demand assumptions priced as certainty.

**Semiconductor capital equipment.** KPIs: *book-to-bill, WFE spend outlook, backlog/deferred revenue, service/installed-base revenue mix, China exposure/export-control risk*. Multiple: **EV/EBITDA, P/E on mid-cycle**. Suppress: **trailing P/E at peak**, **P/B**. Value-trap: WFE-cycle peak earnings.

### UTILITIES

**Regulated electric & gas utilities.** KPIs: *rate-base growth, allowed ROE vs earned ROE, regulatory-jurisdiction constructiveness, FFO/debt, equity ratio, CWIP treatment/regulatory lag*. Multiple: **P/E on regulated EPS**, **EV/rate base** (1.2–1.8x), **dividend yield vs Treasury spread**. Suppress: **EV/EBITDA less useful, P/B naively, ROIC/ROE generic, FCF yield, current ratio**. Value-trap: over-earning allowed ROE invites regulatory rollback at the next rate case.

**Water utilities.** As regulated utilities — *rate base, allowed ROE, infrastructure-replacement runway, acquisition pipeline*. Multiple: **P/E** (premium) and **EV/rate base**. Value-trap: premium P/E leaves little margin for regulatory disappointment.

**Independent power producers / merchant generation.** KPIs: *spark spreads/power prices, capacity factors, hedged vs merchant %, capacity-market revenue, PPA coverage*. Multiple: **EV/EBITDA** (lower/more volatile than regulated). Suppress: **P/E at peak power prices**, regulated-utility framing. Value-trap: merchant power-price peaks are unsustainable, though 2026 data-center demand is re-rating gas/firm-power IPPs.

**Renewable / yieldco developers.** KPIs: *contracted CAFD, PPA backlog/WALT, development pipeline, cost of capital vs project returns, tax-equity structures*. Multiple: **P/CAFD, EV/EBITDA**, dividend coverage. Suppress: **P/E, P/B**. Value-trap: yieldco dividend growth depends on cheap capital and drop-downs.

**Multi-utilities.** Blend of electric/gas regulated frameworks — same as regulated utilities.

## DETAILS — PART 2: THEMATIC EXPOSURE METHODOLOGY

### (a) Measuring exposure from filings, not narrative

The auditable hierarchy, strongest to weakest: (1) **ASC 280 segment reporting** (the "management approach") — segment revenue, significant segment expenses (ASU 2023-07), profit, reflecting internal resource allocation; discretionary, so a themed business can be buried in a broad segment. (2) **ASC 606 revenue disaggregation (606-10-50-5)** — by product/service, geography, contract type, channel; SEC staff pushes alignment between segment external revenue and ASC 606 revenue. (3) **Geographic and customer-concentration disclosures** — ASC 280 requires major-customer disclosure at ≥10% of revenue, plus geographic revenue; the single most direct linkage evidence. (4) **Backlog and RPO (ASC 606-10-50-13)** — forward-looking committed revenue. (5) **Risk-factor and MD&A text** — weakest as a quantitative input, useful as corroboration and NLP input. (6) **Capex/R&D directional disclosure** — a leading indicator of capital commitment ahead of revenue.

Peer-reviewed NLP methods to formalize a text layer: **Sautner, van Lent, Vilkov & Zhang, "Firm-Level Climate Change Exposure," Journal of Finance 78(3), June 2023** (machine-learning keyword discovery on earnings-call transcripts, >10,000 firms/34 countries/2002–2020); **Hassan, Hollander, van Lent & Tahoun, "Firm-Level Political Risk," QJE 134(4), Nov 2019** (same pattern-based approach, finds most variation is firm-level not sector-level, data at firmlevelrisk.com). Recommendation: implement the text layer as a bigram-share measure trained on theme-specific vocabularies, treated strictly as a corroborating signal subordinate to ASC 280/606 revenue evidence — never as the primary exposure number.

### (b) Supply-chain linkage evidence

Professional standard: resolve exposure to a revenue-share number, then verify the counterparty relationship. **Customer-concentration disclosure** (≥10% rule) is the strongest primary-source linkage. **Supply-chain relationship datasets** (FactSet Revere/supply-chain, Bloomberg SPLC) map customer-supplier edges. **Revenue-share estimation** by index providers: **MSCI Thematic Relevance Score** maps segments to SIC codes, computes a 0–1 Relevance Score, applies a discount factor to revenue attributed via SIC-mapping versus directly reported segment revenue. **FactSet RBICS** classifies into ~1,500 sub-industries with "pure-play" commonly ≥75% revenue from one RBICS L4 industry. **S&P Kensho** uses RBICS Focus data plus NLP, weights by float-market-cap × exposure score. **ARK-style** is discretionary/analyst-driven, the least rules-based. Documented criticisms: classification lag, revenue attribution often estimated rather than disclosed, backfilled/overfit custom indices, survivorship bias, unauditable discretionary scoring. Defensible design: primary exposure = ASC 280/606 disclosed themed revenue %, linkage confirmed by ≥10% customer disclosure or a supply-chain dataset edge, text-share only as tie-breaker.

### (c) Detecting whether a theme is already priced in (momentum-free)

1. **Reverse DCF / market-implied expectations** (Mauboussin & Rappaport, *Expectations Investing*) — solve for the growth the market requires from the current price, decomposed into sales growth, operating margin, incremental investment, cost of capital, and implied competitive-advantage period. 2. **Implied-duration-of-excess-returns** analysis. 3. **Multiple-expansion decomposition** — split return into earnings/FFO/ARR growth (delivery) vs multiple change (re-rating) vs dividends; a name whose return is mostly re-rating has pulled forward future returns. 4. **Valuation percentile vs the company's own history** — a level, not a trend, so momentum-free. 5. **Consensus-estimate embedding** — compare consensus long-term growth already priced against realistic TAM-implied growth.

Academic backing: **Ben-David, Franzoni, Kim & Moussawi, "Competition for Attention in the ETF Space," NBER WP 28369 (2021), published RFS 36(3), March 2023** — specialized ETFs "lose about 30% (risk-adjusted)" over their first five years, ~-3.1%/yr alpha, driven by overvaluation of underlying stocks at launch. Morningstar corroborates: thematic funds returned ~+7.3% annualized over five years to June 2023 while investors captured only ~+2.4% due to poor entry/exit timing.

### (d) Theme breadth and maturity signals

**Return dispersion within the theme** — early themes show high dispersion; maturing themes narrow as fundamentals sort winners from losers; late-stage crowding compresses dispersion further. **Correlation/co-movement of constituents** — rising pairwise correlation is a classic crowding signal. **Capex cycle position of the theme's suppliers** — simultaneous capacity additions across equipment/materials suppliers historically mark tops. **Thematic ETF launches as a contrarian/late-cycle indicator** — products launched after a run-up, at peak attention, then underperform (Ben-David et al.). Lifecycle: root driver → early pure-plays re-rate → media/consensus → product proliferation → over-pricing → dispersion collapse → disappointment.

### (e) The eleven themes — 2026 state (see original brief for full detail and citations)

Cybersecurity (mid, durable spending, premium EV/ARR already prices demand); Digital Payments & Financial Infrastructure (mid/maturing developed markets); Aging Demographics & Care Capacity (secular/steady); Automation & Robotics (mid); Metabolic Care/GLP-1 (mid, injectable capacity cresting, device/fill-finish second-order thesis structurally at risk from oral GLP-1s and the Novo/Catalent consolidation); Reshoring & Industrial Capacity (late/past-peak — US manufacturing construction spend down ~21–30% from its Aug-2024 peak, ~$47B in IRA-linked projects paused/cancelled by May 2026); Water Infrastructure (early-to-mid, thinnest fresh sourcing); Grid & Electrification Buildout (early-to-mid, demand inflection, but "none of these stocks is cheap" and much backlog revenue lands 2028+); Allied Rearmament & Munitions (early-to-mid demand runway, but liquid large-caps — e.g. Rheinmetall — already re-rated and flagged "priced for perfection"); Energy Security & Firm Power (early-to-mid, converges with Grid); AI Infrastructure Buildout (mid — 2026 combined hyperscaler capex guided to ~$725–760B, +~77% YoY, but the first real investor-pushback year, with named bubble warnings from Goldman's Covello, JPMorgan's Hunter, Morgan Stanley, and the MIT NANDA "95% zero ROI" study).

## RECOMMENDATIONS (as staged in the original brief)

**Stage 1** — Fix the multiple, not just the metric, for REITs/banks/insurers/asset managers/managed care/midstream/utilities/airlines/homebuilders/A&D/pharma; hard rule: suppress EV/EBITDA, P/E, P/B, current ratio, interest coverage, FCF yield, Altman Z and Piotroski by default for REITs and depository/insurer financials. **Stage 2** — Encode a cyclical value-trap flag (peak margins/spreads + low trailing P/E ⇒ flag as cycle peak, not value) for refining, chemicals, steel, base metals, lithium, fertilizers, autos, machinery, trucking, semi-cap-equipment, marine shipping, OFS, IPPs, staffing. **Stage 3** — Rebuild thematic exposure on disclosure: primary = disclosed themed-revenue % (ASC 280/606), linkage confirmed by ≥10%-customer disclosure or supply-chain dataset edge, text-share as tie-breaker only; apply an MSCI-style discount factor to SIC-inferred exposure. **Stage 4** — Operationalize "priced-in" without momentum: reverse DCF, return-attribution (delivery vs re-rating), valuation percentile vs own history, for every top-scoring themed name. **Stage 5** — Maturity labeling: intra-theme return dispersion, pairwise correlation, supplier book-to-bill, with a new-thematic-ETF-launch counter-signal that downgrades freshness.

## CAVEATS

- **Benchmarks vs facts.** Nearly all "good/bad" thresholds (churn <1%, homebuilder GM 20–25%, AFFO payout <80%, NRR >110–120%, efficiency ratio ~50%, MLR sweet spot low-80s, midstream coverage >1.2x, book-to-bill >1.0) are practitioner rules of thumb, not established constants, and drift with the cycle.
- **Data-feasibility reality.** The highest-value operating KPIs (net adds, RASM/CASM, same-store sales, bookings, DCF/coverage, take rate, RevPAR, MLR, book-to-bill, ARR/NRR, rate base) are overwhelmingly in 8-K Exhibit 99 supplementals, MD&A prose, or earnings calls — not standardized XBRL. Building this registry in full requires a supplemental-parsing/NLP layer and, for commodity/traffic KPIs, third-party data (USDA, SEMI, CBRE/JLL, DOT Form 41, LME, Nielsen/IRI).
- **Part 2(e) source quality.** Several 2026 capex and market-size figures come from secondary aggregators and are explicit projections; named-analyst quotes were relayed via CNBC/TheStreet/Fortune rather than original notes. GLP-1 2026 market-size estimates diverge materially by source.
- **Not investment advice.** Theme cycle-stage and priced-in labels are analytical judgments as of August 2026 and will move with capex guidance, policy, and rate cases.
