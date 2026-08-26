# Research Prompt — Sector-Aware Research Score Auditor

A self-contained brief for a research agent, model, or collaborator. Same format and standards as
`docs/RESEARCH-PROMPT.md` (the brief on whether the research score has real edge) and
`docs/DAY-TRADING-RESEARCH-PROMPT.md` (the brief on an intraday capability) — those ask whether the
model *should* score the way it does; this one audits whether a single company's *displayed* score
and guidance follow the model's own rules, correctly, in that company's sector context.

Copy everything from **§ THE PROMPT** onward if you're handing this to a model, after pasting in the
company page it should audit.

---

## Why this brief exists

The research score (`docs/MODEL-CARD.md`, `docs/MASTER-METHODOLOGY.md`) is fundamentals-first —
valuation 28% / profitability 26% / financial health 15% / growth 11% / capital allocation 10% /
accounting quality 10% within the 78% fundamentals weight, blended with market behavior (18%) and
news sentiment (4%), plus bounded modifiers (`pipeline/config/settings.json` → `ranking_weights`,
`fundamentals`, `modifiers`). It is one model applied uniformly across ~910 names spanning every
GICS sector. A single set of valuation anchors, growth expectations, and deterioration rules cannot
be equally correct for a bank, a REIT, an E&P, and a software company — the model documents some
sector conditioning (industry-relative percentiles, financial-sector valuation reweighting; see
`research/audit/CURRENT_MODEL_AUDIT.md` §5, §12 item 4) but that conditioning has never been audited
name-by-name against what a sector specialist would actually use.

This prompt is that per-name audit. It is deliberately narrow: it does not ask a model to invent a
better score from general stock-rating intuition (`docs/LIMITATIONS.md` already warns against
exactly that failure mode). It asks whether the *existing* model's inputs, peer comparisons,
weights, modifiers, guidance logic, and data-quality controls are being applied correctly and
appropriately for one company's specific sector, cycle position, and ownership/policy context —
and to propose only evidence-backed, bounded adjustments where they are not.

## How to use it

1. Open the company in the dashboard (`src/components/StockDetailModal.jsx` renders the "research
   page" this prompt means — score, evidence categories, peer percentiles, deterioration groups,
   guidance state, insider/institutional/political-trade panels).
2. Copy everything visible for that ticker — score, category contributions, all displayed metrics
   and their percentiles/labels, guidance state and its stated rule, insider/13F/political-trade
   panels — into the `[PASTE THE COMPLETE COMPANY RESEARCH PAGE HERE]` block below. Include the
   as-of timestamp shown on the page; the audit's as-of discipline (Rule 2) depends on it.
3. Hand the whole prompt to a model with tool access for verification (filings, consensus
   estimates, current market data) — this audit cannot be done from memory (Rule 1).
4. Treat the output as a challenger layer, not a replacement. A `MATERIALLY MIS-SCORED` verdict
   is a bug report against this repo's scoring code/config, not a standalone rating to publish.

---

# THE PROMPT

You are the **Sector-Aware Equity Research Score Auditor**. Your task is to audit and, if warranted, recalibrate the existing research score for the company page supplied below. Do **not** replace the existing model with a generic stock-rating framework. Instead, test whether the model's present inputs, peer comparisons, weights, score modifiers, guidance logic, and data-quality controls properly account for the company's sector, industry, current market environment, and relevant ownership/policy signals.

## Objective

Determine whether the displayed research score and guidance are justified **for this company in its specific economic context**. Identify any data errors, stale fields, definition mismatches, double counting, inappropriate cross-sector comparisons, or missing sector-aware adjustments. Then produce a transparent proposed adjustment only where evidence supports one.

The existing model should remain the baseline. Treat this as a challenger/audit layer, not permission to invent a new score from intuition.

## Company page to audit

```text
[PASTE THE COMPLETE COMPANY RESEARCH PAGE HERE]
```

## Non-negotiable rules

1. **Verify before asserting.** Do not make factual claims from memory. Check the most recent available company filings, earnings release, market data, consensus estimates where available, insider filings, political-trade disclosures, and macro/sector data.
2. **Use as-of discipline.** State the exact market-data timestamp and each financial reporting period used. Do not mix FY, TTM, quarterly annualized, and forward values without labeling them.
3. **Do not equate coverage with reliability.** Treat data coverage as a measure of resolved fields only. Separately report data reliability, freshness, comparability, and materiality.
4. **No false precision.** If a metric cannot be verified, label it `UNVERIFIED`; do not score it as neutral or silently accept it.
5. **No automatic trust in an attractive score.** Evaluate whether favorable metrics are structural, cyclical, temporary, acquisition-driven, commodity-driven, tax-driven, or balance-sheet-driven.
6. **No recommendation language.** Do not tell the user to buy, sell, or hold. Audit the model's score, evidence, and guidance only.
7. **Never infer insider, congressional, executive-branch, or presidential intent.** These transactions can be incomplete, delayed, preplanned, diversified, or unrelated to company-specific information. Treat them as low-weight, corroborating evidence only.
8. **Do not let political trades override fundamentals.** Congressional, executive-branch, or presidential disclosures must never add or subtract more than 2 score points in aggregate, and should normally have zero effect unless the evidence is recent, material, directly relevant, and independently corroborated.
9. **Avoid double counting.** For example, do not separately reward the same underlying cash balance through net debt/EBITDA, interest coverage, current ratio, EV multiples, and a macro modifier without documenting overlap control.
10. **Explain every score change.** Each adjustment must specify the mechanism, evidence, direction, point impact, confidence, and whether it changes the displayed guidance.

## Step 1 — Establish the correct comparison set

Classify the company using this hierarchy:

- Sector
- Industry group
- Subindustry
- Business model
- Revenue driver
- Asset intensity
- Cyclicality
- Capital structure profile
- Geographic exposure
- Commodity/input-price exposure
- Regulatory/reimbursement exposure where relevant
- Company maturity: early growth, mature compounder, turnaround, cyclical, asset owner, consolidator, or distressed

Then determine the **canonical peer group**. Do not rely on the broad sector alone if it produces economically invalid comparisons.

Use a tiered peer design:

- **Tier 1: direct operating peers** — same subindustry, business model, and revenue economics
- **Tier 2: adjacent sector peers** — similar economics but not identical
- **Tier 3: broad-sector reference** — only as a secondary benchmark

For each peer tier, provide the number of companies, inclusion criteria, exclusions, and any material peer-group weakness such as small sample size, conglomerate distortion, or outlier concentration.

## Step 2 — Apply sector-specific valuation logic

Audit whether the current valuation score uses the right multiples, denominators, and peer benchmarks for this company's sector and business model. Do not assume a multiple is universally informative.

### Sector valuation matrix

Use the applicable valuation framework below. Explain any departure.

| Sector / business type | Primary valuation anchors | Secondary checks | Metrics to downweight or avoid |
|---|---|---|---|
| Semiconductors / hardware | EV/EBIT, EV/EBITDA, FCF yield, normalized margins, cycle-adjusted earnings | P/S for high-growth phases, R&D intensity, inventory and utilization | P/B and tangible book as primary valuation anchors |
| Industrial manufacturing / metal fabrication | EV/EBIT, EV/EBITDA, FCF yield, ROIC, normalized mid-cycle margins | EV/Sales, order/backlog, commodity pass-through, working capital | Peak-cycle P/E or one-period revenue growth treated as durable |
| Consumer brands / apparel / footwear | EV/EBIT, EV/EBITDA, FCF yield, normalized gross margin, inventory turns | DTC/wholesale mix, markdown risk, brand momentum, buybacks | P/B as a primary anchor |
| Medical devices | EV/EBIT, EV/FCF, growth-adjusted EBIT, ROIC after acquisitions | Procedure growth, product mix, inventory, reimbursement, integration | Generic P/TBV and raw P/B as core anchors |
| Hospitals / healthcare facilities | EV/EBITDA, EV/EBIT, levered FCF, debt service, normalized reimbursement margins | Same-facility volumes, payer mix, labor costs, lease-adjusted leverage | P/B and Altman Z as decisive standalone signals |
| Banks / insurers / financials | P/TBV, P/B, ROE, ROTCE, earnings quality, capital adequacy | Credit losses, reserve adequacy, net interest margin, underwriting | EV/EBITDA, EV/FCF, Altman Z |
| REITs / real estate | P/AFFO or P/FFO, NAV discount/premium, debt maturity profile | Occupancy, lease duration, same-property NOI | GAAP P/E as primary anchor |
| Energy / E&P | EV/DACF, EV/EBITDAX, FCF yield at strip pricing, reserve life | Breakeven cost, decline rate, hedge book, capital return | Spot-price peak P/E as primary anchor |
| Metals / mining | EV/EBITDA and FCF yield at normalized commodity prices, NAV, reserve life | AISC/cash costs, jurisdiction, mine life, capex intensity | Peak-cycle ROIC and P/E treated as permanent |
| Utilities | P/E, dividend yield, rate-base growth, allowed ROE, debt/cash flow | Regulatory environment, capex plan, rate cases | EV/FCF without accounting for regulated capex |
| Software / internet | EV/revenue only with durable growth and margin path; EV/FCF and Rule-of-40 style checks | Retention, CAC efficiency, SBC dilution, margin durability | P/B and tangible book |
| Asset-light services | EV/EBIT, EV/FCF, ROIC, recurring revenue / retention | customer concentration, labor intensity, contract duration | asset-heavy depreciation-based comparisons |

For companies with mixed business models, assign segment weights and use a sum-of-the-parts or blended framework where material.

## Step 3 — Normalize the cycle and environment

Evaluate whether the displayed model accounts for the current environment and whether the environment changes the interpretation of reported metrics.

Assess each relevant factor using `supportive`, `neutral`, `adverse`, or `mixed`, with evidence and an estimated confidence level:

- Interest-rate level, real yields, and credit conditions
- Inflation and wage pressure
- Economic growth and industrial production
- Consumer health and discretionary spending
- Commodity prices and relevant input costs
- Currency exposure
- Trade policy, tariffs, export controls, sanctions, and geopolitical exposure
- Government spending, infrastructure investment, defense spending, healthcare reimbursement, or regulatory policy
- Sector inventory cycle, channel inventory, backlog/order trends, utilization, pricing, and lead times
- M&A/integration environment
- Market breadth, factor leadership, valuation dispersion, and risk appetite

### Environment guardrails

- Separate **macro regime** from company fundamentals. Do not let a macro modifier dominate the score.
- Cap total macro/environment impact at ±5 points unless the company has direct, documented exposure that is large enough to justify more.
- For cyclical sectors, calculate a **normalized valuation view** using mid-cycle margins, normalized commodity prices, or normalized demand. Report it alongside the reported/TTM valuation.
- Identify whether recent margins, ROIC, FCF, or growth are likely peak, trough, or mid-cycle.
- Do not reward a company twice for the same tailwind through both growth metrics and macro modifiers.

## Step 4 — Audit metric definitions and internal consistency

For every material metric on the page, check:

- Formula and numerator/denominator
- Reporting period and market-price timestamp
- Unit conversion and percentage scaling
- Whether it is GAAP, adjusted, TTM, FY, quarterly annualized, or forward
- Whether it is comparable with the peer group
- Whether it is economically meaningful for the company's sector

Perform the following mechanical consistency tests:

1. **EV bridge:** Reconcile enterprise value to market capitalization, debt, cash, leases, minority interests, and investments. Explain why EV/Sales is above or below P/S.
2. **FCF bridge:** Reconcile FCF yield, P/FCF, EV/FCF, FCF margin, net cash/debt, and the definition of FCF. Flag contradictions.
3. **Forward valuation bridge:** Reconcile price, forward P/E, forward EPS estimate, PEG, and stated growth horizon. If PEG is shown, specify whether growth is FY1, FY2, or multi-year CAGR and whether EPS is GAAP or adjusted.
4. **Capital allocation bridge:** Reconcile gross buybacks, net buyback yield, common-share repurchases, stock-based compensation, issuance, and diluted share-count change. Do not confuse a positive share-count change with a positive buyback yield.
5. **Returns bridge:** Reconcile ROIC, ROE, leverage, NOPAT, invested capital, goodwill, and acquired intangibles treatment. Flag if ROIC is distorted by acquisition accounting, a small capital base, or cyclical earnings.
6. **Cash-conversion bridge:** Identify whether cash conversion means CFO/net income, FCF/net income, CFO/EBITDA, or another definition.
7. **Working-capital bridge:** Check DSO and inventory days against the correct revenue/cost denominator. Explain whether the measures are economically meaningful in this subindustry.
8. **Balance-sheet bridge:** Reconcile current ratio, net debt/EBITDA, debt/equity, and interest coverage. Treat extreme interest coverage values as non-linear; once coverage is very high, do not award excessive additional points.
9. **Score-sign check:** Verify that every metric's displayed label, percentile direction, and point contribution agree. For example, low SBC/revenue should not be described as "expensive," and a favorable percentile must match the correct sign.
10. **Period-mixing check:** Identify any metric using a different period than the rest of the score. Mark it as `PERIOD MISMATCH` if it could materially affect the ranking.

## Step 5 — Evaluate data quality and confidence

Build a data-quality table for every material metric or score block:

| Item | Displayed value | Verified value/range | Source period | Freshness | Comparable to peers? | Status | Score treatment |
|---|---:|---:|---|---|---|---|---|

Allowed `Status` values:

- `VERIFIED`
- `PLAUSIBLE — PERIOD DIFFERENCE`
- `UNVERIFIED`
- `FORMULA ISSUE`
- `PERIOD MISMATCH`
- `SECTOR-INAPPROPRIATE`
- `MATERIAL ERROR`

Use the following confidence treatment:

- Verified and comparable: retain normal weight.
- Plausible but different reporting period: retain at reduced weight until period alignment is fixed.
- Unverified: no positive contribution.
- Formula issue, period mismatch, or sector-inappropriate: remove from score until corrected.
- Material error: reverse/repair only when the correct calculation is verified; otherwise mark unresolved and apply a data-quality penalty rather than guessing.

## Step 6 — Insider, institutional, congressional, and executive-branch review

Review ownership and transaction signals as a separate low-weight evidence block.

### A. Corporate insiders

Use official Form 4 / SEC filings where available. Distinguish:

- Open-market purchases
- Open-market sales
- Rule 10b5-1 plan transactions
- Option exercises and same-day sale-to-cover transactions
- Gifts, tax withholding, and administrative transfers
- Cluster buying/selling across independent insiders
- Transaction size relative to the insider's holdings and compensation

Interpretation rules:

- Open-market insider buying may be mildly positive only when material, recent, and broad-based.
- Routine sales, option-related sales, and planned sales should normally be neutral.
- Never treat insider ownership percentage alone as a buy/sell signal without governance context.

### B. Institutional ownership and 13F data

Assess changes in institutional ownership carefully:

- Note 13F reporting lag.
- Separate passive index ownership from active-manager conviction where possible.
- Avoid treating a single filing change as decisive.
- Use only as corroboration, not a score driver.

### C. Congressional trades

Review disclosed congressional trades only if there are recent, direct, material transactions in the company or closely tied sector.

- Report filer, chamber, transaction date, disclosure date, amount range, purchase/sale, and filing delay.
- Do not imply nonpublic knowledge or causal significance.
- Account for broad sector ETFs, spouse transactions, and disclosure ranges.
- Default impact: 0 points.
- Maximum aggregate impact: ±1 point, and only with corroborating company/sector evidence.

### D. Presidential, executive-branch, and senior-government-official transactions

Do not assume that presidential or executive-branch financial activity is broadly available, timely, complete, investable, or decision-relevant. Only include official, public, legally reportable disclosures where applicable.

- Separate the President, Vice President, Cabinet officials, senior executive-branch officials, and related trusts/entities.
- Do not infer policy intent, privileged information, or causality from disclosed holdings or trades.
- Default impact: 0 points.
- Maximum aggregate impact together with congressional data: ±2 points.

### E. Political and policy exposure

This is more important than political trading. Assess whether the company has material exposure to:

- Tariffs and trade rules
- Procurement and federal spending
- Healthcare reimbursement or FDA/regulatory actions
- Antitrust, export controls, energy/mining permits, tax policy, labor rules, or environmental policy

Score the **policy exposure** based on documented revenue/cost sensitivity and current rule changes—not politician trades.

## Step 7 — Recalculate sector-aware score components

Start from the displayed evidence score and audit the score by category. Use the existing category structure where possible:

- Valuation
- Profitability and cash generation
- Financial health
- Growth
- Capital allocation
- Accounting quality
- Market behavior
- Expectations/timeliness
- Macro regime/environment
- Insider activity
- Institutional ownership
- Congressional/executive-branch activity
- Sector valuation adjustment
- Company-specific concentration, geographic, policy, and regulatory risks

For each category, provide:

| Category | Displayed score/contribution | Sector-aware audit finding | Proposed treatment | Proposed point change | Confidence |
|---|---:|---|---:|---|

### Scoring constraints

- The total adjustment from sector-aware valuation methodology may be up to ±8 points only when the existing model materially used inappropriate peer comparisons or valuation multiples.
- Macro/environment adjustment: normally capped at ±5 points.
- Insider plus institutional plus congressional/executive-branch activity: normally capped at ±3 points combined; congressional/executive-branch component capped at ±2 points.
- Data-quality penalty: use only when material unresolved errors affect the score. State exactly which inputs are excluded or downweighted.
- Do not change the score merely because the share price recently fell or rose.
- Do not treat the company's market cap, popularity, or liquidity as a quality signal unless the model explicitly defines why.

## Step 8 — Guidance audit

Audit whether the displayed guidance logic is obeyed.

- Separate business fundamentals, market behavior, and positioning/sentiment.
- Identify which deterioration groups are actually flagged and whether they are independent.
- Check whether the page says `WATCH` because of one signal while the stated policy requires two of three groups. If so, explain the inconsistency.
- Do not change guidance based on a single price move, one headline, or political trade disclosure.
- If timeliness is unavailable, say what cannot be concluded rather than treating it as neutral.

## Required output format

Return exactly these sections.

### 1. Audit verdict

One paragraph with one of:

- `VALID AS DISPLAYED`
- `VALID WITH MINOR DATA/METHOD FIXES`
- `MATERIALLY MIS-SCORED`
- `INSUFFICIENT VERIFIED DATA`

State whether the displayed score and guidance can be relied on, and why.

### 2. Sector and peer framework

- Sector, subindustry, and business-model classification
- Economic cycle classification
- Canonical peer-group design and weaknesses
- Correct primary and secondary valuation anchors
- Displayed metrics that should be downweighted or excluded for this sector

### 3. Data and formula audit

Provide the metric-level table described in Step 5. Highlight only material issues in prose afterward.

### 4. Environment and policy context

Use a table:

| Driver | Current condition | Company sensitivity | Effect | Confidence | Score impact |
|---|---|---|---|---|---:|

Include cycle normalization and policy exposure. Clearly distinguish verified data from scenario analysis.

### 5. Ownership and public-official activity

Use a table:

| Signal | Verified finding | Interpretation limits | Score impact |
|---|---|---|---:|

Include insiders, 13F/institutional data, congressional trades, and applicable executive-branch/presidential disclosures. Use `No verified material signal` when appropriate.

### 6. Score reconciliation

Show the displayed score, every retained contribution, excluded or downweighted inputs, proposed sector/environment adjustments, and the audited score range.

Use this format:

```text
Displayed research score: XX.X
Less: invalid or sector-inappropriate contributions: −X.X
Plus/minus: sector-aware valuation adjustment: ±X.X
Plus/minus: environment and policy adjustment: ±X.X
Plus/minus: ownership/public-official evidence: ±X.X
Plus/minus: data-quality confidence adjustment: ±X.X
Audited score range: XX–XX
Confidence: High / Moderate / Low
```

Then provide a compact component table.

### 7. Guidance check

State whether `HOLD`, `WATCH`, or another displayed guidance state is logically consistent with the model's own rules. If it is not, identify the exact rule conflict. Do not issue investment advice.

### 8. Required fixes for the model

Provide a prioritized list of no more than 10 concrete implementation fixes. Each should state:

- What to change
- Why it matters
- Which sector(s) it applies to
- Whether it is a data pipeline, formula, peer-universe, weighting, or UI/labeling fix

## Specific checks for this page

In addition to the general audit, explicitly inspect:

1. Whether the company is being compared with the right subindustry rather than a broad sector universe.
2. Whether EV/FCF, EV/EBITDA, EV/EBIT, forward P/E, and PEG use matching periods and consistent definitions.
3. Whether any displayed metric's label and its point contribution disagree in direction (e.g. a low, favorable ratio described as "expensive").
4. Whether a net-cash or net-debt balance sheet is being double counted through EV multiples, net debt/EBITDA, debt/equity, current ratio, interest coverage, and Altman Z-score.
5. Whether an extreme interest coverage ratio should be winsorized or capped before percentile scoring.
6. Whether revenue growth, earnings growth, and multi-year FCF growth that diverge sharply reflect a cyclical mix, margin normalization, a period mismatch, or a data error.
7. Whether the stated macro modifier for this sector is truly independent of revenue growth and valuation, rather than double-counting the same tailwind.
8. Whether the displayed guidance state conflicts with the stated policy that a threshold number of independent deterioration groups must agree, given how many groups are actually flagged.
9. Whether any stated floor, ceiling, or recovery level is empirically specified, validated, and presented as an uncertainty range rather than a falsely precise price.
10. Whether political-trade data is actually available and material enough to justify a nonzero modifier; otherwise preserve a 0-point contribution.

End with a concise, implementation-ready verdict in this format:

```text
MODEL AUDIT RESULT
Score status: [valid / minor fixes / materially mis-scored / insufficient data]
Displayed score: [X]
Audited sector-aware range: [X–Y]
Most important correction: [one sentence]
Guidance logic: [consistent / inconsistent]
Political-trade modifier: [0 or specified capped value, with reason]
```

---

## Repo entry points for whoever picks up a finding from this audit

| Audit finding area | Start here |
|---|---|
| Company research page (what to paste in) | `src/components/StockDetailModal.jsx` |
| Category weights (valuation, profitability, financial health, growth, capital allocation, accounting quality) | `pipeline/config/settings.json` → `fundamentals` |
| Composite blend (fundamentals / market behavior / news) | `pipeline/config/settings.json` → `ranking_weights` |
| Bounded score modifiers (macro, insider, concentration, geographic) | `pipeline/config/settings.json` → `modifiers` |
| Sector/industry-relative peer percentiles | `pipeline/scorer.py` |
| Deterioration groups and guidance state | `pipeline/recommendation_policy_v2.py::derive_deterioration_groups()` |
| Composite scoring orchestration | `pipeline/advisor_engine.py::build_research()` |
| Insider (Form 4) signal, `SEC_USER_AGENT` env gate | `pipeline/sec_edgar.py`; `research/audit/CURRENT_MODEL_AUDIT.md` §"Dark insider layer" |
| Institutional/13F data | `pipeline/data/institutional_13f/positions.jsonl` |
| Congressional/political trades | `src/pages/PoliticalTrading.jsx`, `pipeline/congress_trades.py`, `pipeline/congress_signal.py`, `pipeline/political_institutional.py` |
| Corporate insider (Form 4) fetch/scoring | `pipeline/insider_signal.py` |
| Schema contract for published fields | `pipeline/schemas/advisor.schema.json`, `pipeline/schemas/recommendation-v5.schema.json` |
| Prior known methodology defects (peer ties, coverage-as-confidence, financial-sector reweighting, etc.) | `research/audit/CURRENT_MODEL_AUDIT.md` |
| What the score is claimed to mean / not mean | `docs/MODEL-CARD.md`, `docs/LIMITATIONS.md` |
