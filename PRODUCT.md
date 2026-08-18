# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Individual investor using ValueSignal as a personal research tool. Seeks clean, modern, high-tech, data-rich interface for equity research and portfolio decisions.

## Product Purpose

ValueSignal provides precomputed, fundamentals-first equity research: a 0–100 score per company, the component breakdown, and the evidence behind it. Every number on screen comes from a committed JSON snapshot, refreshed on schedule by a Python batch pipeline. The product makes it possible to evaluate ~900 US equities and ~125 ETFs without running the analysis yourself, with full visibility into what was measured and what gaps remain.

Success means the score prompts deeper research into the right names—not wrong ones that looked good on price alone.

## Positioning

**Fundamentals-first scoring.** 78% of the research score comes from company fundamentals (valuation, profitability, financial health, growth, capital allocation, accounting quality), with market behavior and news sentiment as tilts rather than drivers. Most equity screens lead with technicals or momentum; ValueSignal inverts that.

**Full transparency.** The evidence that produced a score sits beside it, not behind a click. Coverage gaps are drawn (dashed meter segments, unavailable metric labels) rather than hidden. When the model could not measure something, the interface says so.

## Operating Context

Research workflow: evaluating candidates, comparing fundamentals across stocks, monitoring portfolio positions, tracking thematic trends. Used on desktop and mobile, in market hours and outside them. The interface serves as a starting point for deeper research, not a real-time trading terminal.

## Capabilities and Constraints

**Static architecture.** There is no application server or database. `public/data/*.json` (committed to the repo) is the entire product surface. The Python pipeline scores the universe, validates the output against JSON schemas, and commits it back to `main`. The browser fetches these committed files as static assets.

**Precomputed, scheduled data.** GitHub Actions refreshes data at 07:00, 12:00, and 15:00 Eastern on weekdays. Authenticated users can trigger a fast manual refresh from the Overview page (Netlify Function + GitHub workflow dispatch). Live portfolio valuations update every five minutes during market hours via a separate scheduled Netlify Function.

**Firebase for user state.** Auth, portfolios, and watchlists live in Firestore; everything else on screen is precomputed by the pipeline.

**Free-tier API limits.** Alpha Vantage free allowance is 25 calls/day; enrichment is capped at five symbols. Yahoo Finance fills the rest. The pipeline caches provider responses locally and enforces rate limits.

**Coverage and confidence.** Not every metric is available for every company. The score reflects what was measured, and the coverage meter shows the share of applicable metrics actually obtained. A name that never makes the preliminary top-shortlist never gets its best fundamentals computed.

**Terminology.** Research score (0–100), coverage (share of applicable metrics measured), confidence (final weight adjustment for missing data), theme exposure (structural trend participation, walled off from the score), momentum guardrails (price momentum contributes zero to thematic exposure), evidence rail (the "why this score" breakdown for the selected row).

## Brand Commitments

**Name:** ValueSignal

**Voice:** Professional, evidence-based, serious research tool. Not a trading app, not gamified, not hype-driven. The interface states what it knows and admits what it does not.

## Evidence on Hand

Real data: ~900-stock equity universe (configurable in `pipeline/config/advisor_universe.json`), ~125-fund ETF watchlist, eleven thematic screens (AI infrastructure, automation & robotics, grid & electrification, reshoring, rearmament, energy security, cybersecurity, digital payments, metabolic care, aging demographics, water infrastructure), committed point-in-time metric store (`pipeline/pit_store/*.jsonl`), factor-loading evidence from the validation harness.

Absences: No testimonials, no customer logos, no benchmark promises, no forward return forecasts. The disclaimer ("general research only—not individualized financial advice") is product truth and must stay visible.

## Product Principles

1. **Evidence before claims.** Show the data that produced a score, not just the score. Draw unavailable metrics as gaps, never as zeros.

2. **Fundamentals outrank price action.** Valuation, profitability, and financial health carry 78% of the weight. Price behavior is a tilt, not a driver.

3. **Transparency over polish.** Admit coverage gaps, flag value traps, state when the model could not measure something. Honest incompleteness beats false precision.

4. **Density serves the task.** The user is doing research, not being persuaded. High information density, scannable structure, and direct access to evidence outrank spaciousness.

5. **Anti-hype by design.** Price momentum contributes zero to theme exposure. Names already in the top valuation decile of their sector are flagged, not promoted. The score is a research prompt, not a buy signal.

## Accessibility & Inclusion

No product-specific accessibility requirements beyond WCAG AA compliance. Interface must remain usable on mobile (research happens outside market hours and away from desks) and must not require color perception to distinguish states (coverage gaps, score bands, evidence categories).
