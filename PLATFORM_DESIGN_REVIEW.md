> **Historical snapshot, not current status.** Written mid-project; specific counts (test totals, universe size) and some completeness claims are now stale. For the authoritative account of this upgrade see `docs/CHANGELOG-QUANT-UPGRADE.md`; for current repo state see `README.md` and `APP-COMPLETE-BREAKDOWN.md`.

---

# Investment Platform Design Review

**Review standard:** pre-launch institutional quantitative, portfolio-management, market-data, risk, and software architecture audit  
**Repository state reviewed:** working tree as observed 3 August 2026; this matters because the tree contains uncommitted production-hardening work and a malformed published dataset  
**Capital standard:** a system that may influence hundreds of millions of dollars, not a consumer watchlist application  

This review evaluates implemented behavior, published behavior, and aspirational configuration separately. A metric named in a registry is not a live factor. A test of a pure function is not a validated strategy. A shadow recommendation is not the production decision engine. A JSON schema is not a data-governance program. Those distinctions drive the scores below.

## Audit basis and current release condition

The architecture was traced through the Python pipeline, canonical metric registry, applicability rules, scoring engines, research screens, recommendation policies, point-in-time store, validation code, React data loader, schema migrations, portfolio utilities, public datasets, tests, and build output. The current repository cannot pass a launch gate:

| Check | Observed result | Institutional interpretation |
|---|---:|---|
| Python test suite | 392 passed; one LibreSSL/urllib3 warning | Useful unit coverage. It proves deterministic code paths, not economic validity or production operability. |
| React test suite | 107 passed, 3 timed out | Failed gate. Timeouts affected charts and the finances page; chart rendering also emitted duplicate-key warnings. |
| ESLint | Passed | Necessary hygiene, low evidentiary value for investment correctness. |
| Production build | Passed | Bundle is 928.85 kB minified / 276.00 kB gzip and triggers the >500 kB warning. There is no route splitting. |
| Public-data validation | Aborted before schema checks | `public/data/advisor.json` contains unresolved `<<<<<<<`, `=======`, and `>>>>>>>` merge markers and is not valid JSON. |
| Point-in-time depth | 1,152 observations, 81 revisions, 3 universe snapshots | A collection seed, not a research history. Three universe records cannot establish survivorship-free multi-regime results. |
| Live v2 invariants | 10/10 synthetic/live probes passed | Good contract probes; not predictive validation. |
| Live ETF invariants | 8/8 passed | Good plumbing probes; not evidence that ETF ranks forecast utility or flows. |
| Historical backtest artifact | 52 weeks, 120 usable names, top 20, weekly re-ranking | Far too short and narrow; reports 13.89% versus SPY 8.42%, but omits credible costs, capacity, delistings, and multi-cycle evidence. |
| Weight sweep | 200 trials, 156 weeks, three 60-week holdout folds | Better than naive in-sample tuning, but the objective is a bespoke 0–10 score, the sample is short, and no deflated/OOS rank-IC promotion artifact is published. |

**Immediate launch verdict:** blocked. A malformed research payload alone is sufficient. More importantly, the system is a promising research prototype with institutional vocabulary and several correct design instincts; it is not an institutional investment platform.

---

# 1. Overall Architecture

## 1.1 System map

```text
Yahoo / Alpha Vantage / SEC / FRED / Marketaux / issuer disclosures
                              |
                    adapters, retries, cache
                              |
          normalized snapshots + partial observation lineage
                              |
        +---------------------+----------------------+
        |                                            |
  legacy scoring                              canonical v2 shadow
  78/18/4 blend                         applicability + reconciliation
        |                                            |
  production recommendation                 v2 decision matrix
        |                                      (shadow only)
        +---------------------+----------------------+
                              |
                    committed public JSON
                              |
               static React application + Firebase
                              |
              user portfolio utilities in browser
```

The diagram exposes the architectural problem: the safer canonical path does not yet own the production decision. The frontend reads committed JSON directly, while portfolio actions, stop logic, and fallbacks also exist in JavaScript. The platform therefore has multiple decision authorities.

## 1.2 Category scores

| Category | Score /10 | Judgment |
|---|---:|---|
| Overall philosophy | 7.0 | Fundamentals-first, explicit uncertainty, and separation of research horizons are defensible. The philosophy becomes inconsistent when fixed stop-losses and browser-side fallback recommendations override thesis logic. |
| Structural versus tactical separation | 8.0 | The cleanest design choice in the repository. Durable business evidence is not allowed to masquerade as entry timing. The separation is not complete because the legacy 78/18/4 production blend recombines horizons. |
| Decision engine | 5.5 | The v2 two-axis matrix, confidence gates, thesis-break namespace, and company/position separation are strong. It is shadow-only, has arbitrary thresholds, no transition ledger, and no approved production owner. |
| Confidence model | 5.0 | Shrinking scores toward 50 and separating coverage from reliability are correct. Reliability constants of 0.72/0.55 and linear penalties are hand-set, not calibrated probabilities. Timeliness confidence can be dominated by field presence rather than estimate quality. |
| Coverage model | 6.0 | Weight-aware applicable coverage and suppression are materially better than imputing neutral values. Replacement metrics are mostly declared but absent, so profile confidence correctly collapses while legacy scoring may still publish. |
| Scoring pipeline | 5.0 | Explainable and version-labelled, but step-function bands discard cross-sectional information; two scoring generations coexist; score semantics differ among stocks, ETFs, themes, and screens. |
| Provider abstraction | 6.5 | Ports/adapters, capability routing, fake providers, bounded retries, and non-averaging reconciliation are good engineering. Production remains dependent on unofficial Yahoo data and reconciliation is incomplete at the period/accounting-basis level. |
| Configuration architecture | 6.5 | Weights and thresholds are externalized and comments preserve intent. Config is fragmented, duplicated in Python constants, and lacks signed promotion manifests or immutable model packages. |
| JSON schema | 4.5 | Draft 2020-12 validation and read-time migrations are useful. Schemas do not prevent an invalid committed payload from reaching the tree, compatibility is only partially managed, and additive-only evolution is an aspiration rather than enforced producer/consumer contracts. |
| Frontend/backend separation | 4.5 | Static JSON makes deployment simple and limits secret exposure. There is no query API, entitlement layer, calculation service, job status contract, or atomic dataset release; client code contains material investment logic. |
| Caching | 6.0 | Atomic writes, TTLs, stale-on-error behavior, provenance envelopes, and rate limiting are sensible. Cache validity is based mainly on fetch age, not source effective date, filing revision, corporate action, or model version. |
| Versioning | 5.5 | Model/config/schema labels exist. The current file conflict demonstrates that version labels do not amount to release integrity. There is no dataset manifest tying every output to code SHA, config SHA, provider snapshot, and validation report. |
| Extensibility | 6.5 | Theme YAML, adapters, registries, profile rules, and screen configs reduce code changes. Adding a genuinely new industry model still requires data acquisition, canonical definitions, scoring, tests, UI, and history; the config makes extension look easier than it is. |
| Observability and operations | 4.0 | Status and diagnostics exist, but no institutional SLOs, lineage graph, incident workflow, immutable releases, dual controls, or reconciliation dashboard exists. |
| Security and governance | 3.5 | Secrets are kept server-side and Firebase gates personal pages. There is no RBAC model for research approval, maker-checker controls, audit retention policy, model inventory, or evidence of penetration/security testing. |

## 1.3 What is structurally good, and why

1. **Structural and tactical evidence are named separately.** A business can be excellent and badly timed; a weak business can rally. Most retail ranking products compress those states into a single adjective. The matrix preserves the distinction and makes later portfolio policy possible.
2. **Unavailable and inapplicable are different states.** Suppressing bank EV/EBITDA or REIT P/E is industry practice. Treating an inapplicable metric as 50 would quietly penalize specialists and distort coverage.
3. **Uncertain scores shrink toward neutral.** `50 + confidence × (raw − 50)` is transparent Bayesian-style regularization. It prevents a sparse 90 from looking like a fully evidenced 90.
4. **Provider disagreement is preserved rather than averaged.** Averaging two differently defined values creates a number no source reported. Preference plus conflict flags is the correct default.
5. **ETF ranking is peer-relative.** A Treasury ETF and a technology ETF cannot be ranked in one volatility/return batch without converting asset-class exposure into apparent fund quality.
6. **Theme exposure is separate from the core score and explicitly excludes momentum.** This prevents a fashionable price move from becoming evidence of revenue exposure.
7. **Point-in-time collection records revisions separately.** That is the right data model. Its weakness is history depth, not conceptual direction.

## 1.4 Principal architectural defects

### Multiple sources of decision truth

There are at least four relevant policies: legacy pipeline `action_for`, v2 shadow recommendation, browser `sellWatchLogic`, and position stop-loss utilities. Thresholds differ. Portfolio exposure defaults in the browser are 25% per name and 35% per sector, while v2 policy uses 5% default max position and 25% sector. A user can receive a company HOLD, a browser stop SELL, and a v2 shadow no-action simultaneously. Institutional systems may have multiple views, but they must have one authoritative policy engine, explicit precedence, and an audit record.

**Required change:** create a server-side/versioned `DecisionPackage` with input snapshot ID, model ID, policy ID, company state, portfolio state, proposed order, constraint results, tax/cost result, approver status, and reason codes. The UI renders it; it does not recompute it. Effort: 4–8 weeks. Expected improvement: very high. Research impact: neutral; governance and operational risk improve substantially.

### Static files are being used as a database and release bus

Committed JSON is attractive for a small transparent site, but it cannot provide atomic multi-file publication, row-level entitlements, historical queries, corrections, replay, or a durable audit trail. The merge markers in `advisor.json` demonstrate the failure mode: source control accepted an invalid production artifact that the app will fetch at runtime.

**Required change:** publish immutable, content-addressed dataset versions to object storage; write a small manifest only after all schemas, invariants, freshness, and cross-file checks pass. The manifest should include code SHA, config SHA, source watermarks, row counts, hashes, model versions, validation artifact IDs, and rollback pointer. Serve through an API/CDN that switches the active manifest atomically. Effort: 2–4 weeks. Expected improvement: critical. Engineering implication: introduces a backend and deployment pipeline, but eliminates partial releases.

### Canonical v2 is a safety overlay, not the live scoring foundation

`build_v2_analysis` consumes legacy component scores, then disallows contributions without observation rows. That is transitional plumbing, not a canonical calculation engine. Many profile-specific replacement metrics exist only as names. The live probes correctly label those gaps, but the production leaderboard still originates from the legacy engine.

**Required change:** calculate every canonical metric from typed observations, attach period and availability timestamps, transform cross-sectionally, and produce structural/tactical scores directly. Retire legacy score computation after a parallel-run acceptance period. Effort: 1–3 months, dominated by data contracts and history. Expected improvement: highest single architectural gain.

## 1.5 Competitive architecture comparison

The comparisons are against publicly documented product capabilities, not private implementation details. Bloomberg describes unified positions, risk, performance, validation, multi-asset models, stress testing, attribution, optimization, orchestration, and reporting in PORT. FactSet documents multi-asset exposure, risk, more than ten attribution models, workflow checks, scenario analysis, APIs, and optimization. Morningstar Direct documents holdings analysis, custom peers, blended benchmarks, optimization, scenario analysis, and attribution. Those are different product classes from this repository ([Bloomberg PORT](https://professional.bloomberg.com/products/bloomberg-terminal/portfolio-analytics/), [FactSet Portfolio Analytics](https://www.factset.com/solutions/portfolio-analytics), [Morningstar Direct](https://www.morningstar.com/business/products/direct/portfolio-management-tool)).

| Platform | ValueSignal exceeds | Roughly equal | ValueSignal trails |
|---|---|---|---|
| Bloomberg | Transparent small-model formulas; source-readable rules; explicit theme anti-hype guardrail | Nothing material at institutional workflow level | Real-time/global data, identifiers, messaging, research, execution, multi-asset risk, scenarios, attribution, optimization, validation, uptime, support, entitlements |
| FactSet | Easier inspection of every hand-set threshold | Separation of modular analytics is philosophically similar | Data depth, point-in-time estimates, risk models, portfolio accounting, attribution, APIs, workflow checks, governance, integrations |
| Morningstar | More explicit structural/tactical stock distinction | Consumer-facing explainability | Fund/manager data, holdings look-through, custom peers, blended benchmarks, optimizer, scenario analysis, licensed research, reporting |
| YCharts | More academically explicit momentum and applicability logic | Lightweight research/dashboard positioning | Historical data breadth, custom calculations, presentation/reporting, screening flexibility, support |
| Seeking Alpha | More transparent raw formulas and explicit coverage confidence | Similar factor-family presentation | Daily coverage, estimates/revisions depth, articles/transcripts/community, alerts, sector-relative database scale; Seeking Alpha publicly describes 100+ metrics and five peer-relative factors ([methodology](https://help.seekingalpha.com/premium/quant-ratings-and-factor-grades-faq)) |
| Simply Wall St | Better auditability and less decorative scoring | Visual consumer explanation intent | Global coverage, polished company reports, consistency, onboarding; neither is institutional portfolio infrastructure |
| Zacks | More diversified structural quality model; less dependence on one revisions rank | Both separate style factors from a top-level signal | Estimate history, long-running production process, coverage and distribution. Zacks explicitly centers short-horizon estimate revisions and Value/Growth/Momentum style scores ([Zacks Style Scores](https://www.zacks.com/style-scores-education/)) |
| Koyfin | More explicit model confidence and PIT intent | Modern web-dashboard ambition | Custom charting, 5,900 advertised filters, global market coverage, reusable views, alerts, portfolio/reporting workflow ([Koyfin features](https://www.koyfin.com/features/)) |
| Portfolio Visualizer | Stock-specific fundamental research and decision explanations | Some benchmark-comparison intent | Asset allocation, factor regression, optimization, Monte Carlo, robust portfolio backtesting |

---

# 2. Scoring System

## 2.1 Score inventory and disposition

| Score | Why it exists | Should it exist? | Current weakness | Institutional replacement or improvement |
|---|---|---|---|---|
| Structural | Estimate durable business quality and valuation independent of timing | Yes; make it the primary research state | Built from step-band legacy scores; replacement metrics largely absent | Cross-sectional sector/industry residual scores, own-history valuation, robust z-scores, explicit forecast horizon, calibrated confidence |
| Valuation | Expected returns vary with price paid relative to fundamentals | Yes | Mixes forward and trailing denominators; fixed sector bands; correlated multiples; no duration/WACC framework | Composite of EBIT/TEV, FCF/EV, earnings yield, asset-specific metrics, own-history and peer residuals, with sector-neutral winsorization |
| Profitability | Profitable firms tend to be higher quality and, controlling for price, have stronger expected returns | Yes; one of the strongest families | ROE, ROIC, margins, FCF yield, and cash conversion overlap; FCF yield is also valuation | Separate operating profitability from valuation; use gross profitability, operating profitability, ROIC spread over WACC, stability, and cash conversion |
| Financial health | Avoid permanent impairment and model leverage/safety | Yes | Industrial ratios are coarse; interest coverage and leverage are backward-looking; sector handling incomplete | Default probability, distance-to-default, debt maturity ladder, fixed-charge coverage, liquidity runway, covenant/headroom; sector-specific solvency |
| Growth | Capture fundamental momentum and future economics | Yes, but never as raw growth alone | Revenue/EPS/FCF growth and margin trend can reward expensive, low-quality expansion; earnings surprise duplicates timeliness | Growth persistence, per-share growth, incremental margins, reinvestment efficiency, analyst revisions; residualize against valuation and industry |
| Capital allocation | Distinguish compounding from dilution/empire building | Yes | Buyback yield can reward debt-funded repurchases; capex/depreciation range is crude | Net payout yield, issuance, M&A discipline, reinvestment rate × incremental ROIC, leverage change, acquisition goodwill impairments |
| Accounting quality | Detect earnings manipulation and weak conversion | Yes | Piotroski dominates but is coarse; DSO/inventory trends are industry-dependent; accruals overlap cash conversion | Accrual variants, cash-flow consistency, Beneish components, auditor/restatement flags, working-capital residuals, revenue-recognition risk |
| Momentum | Capture persistent cross-sectional price trends | Yes as a separate sleeve or tactical confirmation | Five price-derived features create false diversification; no residual momentum or crash control in ranking | 12–1 primary, residual/industry-neutral momentum, breadth, volatility scaling, turnover buffer, beta/sector constraints, crash regime overlay |
| Technical / market behavior | Describe tradability and price confirmation | Yes, but label it market behavior rather than technical truth | Sharpe/Sortino/drawdown/volume/low beta blend returns with risk and duplicates momentum | Separate expected-return signal, risk forecast, and execution/liquidity signals; never put Sharpe into alpha without proving incremental IC |
| Risk | Penalize exposure likely to produce unacceptable loss | Yes, outside alpha score | Current risk score rewards low beta and shallow drawdown but does not model covariance, tail risk, liquidity, or factor exposure | Ex-ante covariance model, factor risk, specific risk, stress loss, liquidity horizon, expected shortfall, marginal contribution to risk |
| ETF | Compare implementation vehicles | Yes, separate from stock scores | Average returns across windows; issuer reputation prior; pooled small peer groups; tracking proxy imperfections | Mandate-specific utility: expected tracking drag, liquidity/market impact, tax, securities lending, structure, counterparty risk, holdings quality |
| Theme | Measure economically evidenced exposure to a structural trend | Yes, as descriptive exposure | Segment/filing/customer/capex inputs are hard to source consistently; no causal revenue mapping or exposure uncertainty | Revenue/profit exposure with provenance, taxonomy confidence, double-counting control, supplier/customer graph, scenario sensitivity; no recommendation blend |
| Portfolio | Determine whether a position improves the whole portfolio | Essential, but currently not a score | Current implementation is concentration warnings and same-day SPY comparisons | Constrained optimization and what-if engine with expected returns, covariance, costs, taxes, factor/sector/country constraints and risk attribution |

## 2.2 Weight audit

### Top-level legacy blend: 78% fundamentals, 18% market behavior, 4% news

The philosophy is defensible but the numbers are not empirically justified for this universe and horizon. “Evidence strength” cannot by itself determine a blend because factors differ in scale, correlation, turnover, and forecast horizon. A 78% correlated cluster of value/quality metrics may represent fewer independent bets than an 18% market-behavior block. The blend should be selected from out-of-sample incremental rank IC and covariance of factor forecasts, then constrained by turnover and interpretability.

News at 4% is appropriately small. The correct next step is not tuning it to 3% or 5%; it is testing whether entity-resolved, novelty-weighted, event-classified news has incremental IC after revisions and momentum. If not, remove it from ranking and retain it as an alert/risk channel.

### Structural category weights

| Category | Current | Judgment |
|---|---:|---|
| Valuation | 28% | Plausible but too dominant if FCF yield remains in profitability and value is measured by correlated multiples. |
| Profitability | 26% | Strong research basis, but the bucket includes FCF yield, creating category leakage. |
| Financial health | 15% | Reasonable for general equities; should vary by leverage regime and business model. |
| Growth | 11% | Reasonable as a quality complement, but surprise belongs in timeliness. |
| Capital allocation | 10% | Deserves 10–15% if measured correctly; current inputs are too crude to support more. |
| Accounting quality | 10% | Sensible; should act partly as a veto/penalty because manipulation risk is asymmetric. |

### Metric duplication

* EV/EBITDA, EV/EBIT, EV/FCF, and EV/Sales share enterprise value and business-cycle exposure.
* ROIC, gross profits/assets, ROE, margin, and cash conversion are correlated quality manifestations.
* FCF yield is a valuation measure placed in profitability.
* Earnings growth, FCF growth, margin trend, and earnings surprise partly encode the same operating improvement.
* Net buyback yield and stock compensation are two sides of net share issuance.
* Accruals and cash conversion overlap.
* 12–1, 12–7, 6–1, high proximity, industry-relative momentum, relative strength, Sharpe, Sortino, drawdown, and low beta reuse the same price path.

The code’s correlation diagnostic is a good admission of this problem, but capping the total score after correlation exceeds 0.8 is not orthogonalization. Use a factor covariance matrix, cluster correlated signals, or choose one representative per cluster based on incremental OOS IC.

## 2.3 Transformation defects

Step bands assign the same score to economically different observations and create threshold cliffs. A forward P/E of 25.01 can drop sharply relative to 25.00 even though the measurement error is larger than the difference. Fixed “excellent/good/fair” bands also drift as rates, inflation, industry mix, and accounting standards change.

Institutional implementation should:

1. validate units and point-in-time availability;
2. winsorize within industry/date using robust percentiles;
3. transform directionally, preferably by rank-normal or robust z-score;
4. residualize against sector, size, country, and other intended neutral exposures;
5. combine using OOS IC-weighted or constrained equal-risk contributions;
6. decay stale observations;
7. attach standard error and coverage;
8. publish raw, normalized, residual, and contribution values.

This preserves information and makes a score comparable through time. Effort: 3–6 weeks after data history exists. Expected improvement: high. Implementation risk: medium because it changes rank stability and requires frozen benchmark comparisons.

---

# 3. Factor Research

## 3.1 Evidence standard

Academic publication is prior evidence, not validation of this implementation. The Kenneth French library shows momentum portfolios based on prior 2–12 month returns and monthly reconstruction; it also documents profitability and investment portfolios and notes that database revisions can alter historical returns ([French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library.html), [momentum construction](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor_daily.html)). Quality-minus-junk research defines quality broadly through profitability, growth, and safety and finds broad historical risk-adjusted performance, not that any hand-built 0–100 quality score will work ([Quality Minus Junk](https://research.cbs.dk/da/publications/quality-minus-junk-2/)). Momentum has severe conditional crash risk, particularly after market declines and during rebounds ([Daniel and Moskowitz](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2371227)).

## 3.2 Ranked expected long-term usefulness

Ranking assumes liquid developed-market equities, realistic costs, monthly/quarterly turnover, and disciplined neutralization.

| Rank | Factor family | Usefulness | Persistence / decay | Crowding and implementation risk | Required platform action |
|---:|---|---|---|---|---|
| 1 | Profitability / quality | Very high | Slow, annual/quarterly | Crowded but capacity is high; definition risk | Keep, simplify, emphasize stability and incremental ROIC |
| 2 | Value using enterprise and cash-flow measures | High | Slow; can endure long drawdowns | Value traps, intangible economy, sector bets | Keep; industry residualize and combine with quality |
| 3 | Cross-sectional 12–1 momentum | High | Medium; decays over months | High turnover, crash risk, crowding | Keep as separate sleeve with crash/volatility controls |
| 4 | Conservative investment / asset growth | High | Slow | Sector and lifecycle dependence | Keep, improve industry normalization |
| 5 | Earnings-estimate revisions | High when PIT data is genuine | Fast, weeks to months | Expensive data, analyst herding, timestamp risk | Increase tactical weight only after licensed PIT history |
| 6 | Net issuance / shareholder yield | Medium-high | Slow | Debt-funded buybacks and M&A confounds | Keep after balance-sheet and valuation conditioning |
| 7 | Accounting quality / accruals composite | Medium-high | Slow to medium | Known anomaly decay; data revisions | Keep as risk gate/composite, reduce standalone accrual weight |
| 8 | Low beta / defensive | Medium-high risk-adjusted | Slow | Rate sensitivity, leverage constraints, crash in risk-on rebounds | Treat as risk/style exposure, not “quality” alpha |
| 9 | Gross profitability | Medium-high | Slow | Strong overlap with quality | Keep within profitability, not as an independent bet |
| 10 | Post-earnings announcement drift | Medium | Fast | Execution around events, timestamp precision | Add only with PIT earnings calendar and costs |
| 11 | Industry-relative momentum | Medium | Medium | Peer taxonomy and small-sample error | Keep with leave-one-out peers and minimum breadth |
| 12 | Residual momentum | Medium | Medium | Model dependency | Add; it removes market/sector/style contamination |
| 13 | Price proximity to 52-week high | Medium | Medium | Duplicates momentum | Use as a small behavioral feature or remove |
| 14 | Cash conversion | Medium | Slow | Industry/accounting sensitivity | Keep within accounting quality, avoid double-counting accruals |
| 15 | Short interest | Medium / asymmetric | Weeks to months | Recall, squeeze risk, reporting lag | Use as risk/positioning context, not linear penalty |
| 16 | Insider opportunistic purchases | Medium | One to three months | Sparse, classification error, legal filing lag | Keep bounded; require transaction coding and cluster independence |
| 17 | Volume confirmation | Low-medium | Short | Noisy, venue fragmentation, overlaps trend | Reduce or use solely for execution/tradability |
| 18 | Headline sentiment | Low standalone | Days | Vendor/model drift, duplicate articles | Remove from structural score; retain event alerts |
| 19 | PEG | Low | Unstable | Denominator sensitivity and horizon ambiguity | Remove from scoring; show diagnostically |
| 20 | Raw Sharpe/Sortino of a stock | Low as alpha | Window-dependent | Strong momentum/volatility overlap | Remove from alpha score; retain risk reporting |

## 3.3 Implemented metric-level research disposition

This table covers the actual structural and market-behavior inputs. “Evidence” describes the broad empirical prior; it does not validate the platform’s threshold function.

| Metric | Evidence and economic rationale | Persistence / decay | Main correlation and implementation risk | Disposition |
|---|---|---|---|---|
| Forward P/E | Conventional value proxy; forward denominator can improve timeliness | Slow multiple, fast estimate changes | Negative/near-zero EPS, optimistic consensus, sector duration | Keep at low-medium weight with estimate quality and own-history/peer residuals |
| PEG | Heuristic, weak asset-pricing foundation | Unstable | Divides two noisy forecasts; horizon/unit mismatch; ignores risk and reinvestment | Remove from score; diagnostic only |
| P/S or EV/Sales | Useful for negative-earnings firms when margins are comparable | Slow | Margin/business-model dependence; P/S ignores leverage | Prefer EV/Sales; low weight and industry-margin conditioning |
| P/B | Classic value proxy, still relevant for financial/asset-heavy firms | Slow | Intangibles, buybacks, accounting marks | Suppress for asset-light firms; retain for appropriate profiles |
| P/tangible book | Important for banks/insurers in context | Slow | Reserve/asset marks and franchise value | Keep only for financial/selected asset-heavy profiles |
| EV/EBITDA | Enterprise value proxy with broad practitioner use | Slow | Ignores capex, working capital, lease/accounting differences | Keep, but below EBIT/TEV and FCF/EV where data quality permits |
| EV/EBIT | Stronger than EBITDA for capital-intensive comparability | Slow | Depreciation/accounting and cyclical earnings | Keep as a primary general-company value metric |
| EV/FCF | Direct owner-cash valuation when FCF is normalized | Slow but denominator volatile | Working capital, growth capex, one-offs; negative denominator | Keep with multi-year normalization; classify as valuation, not profitability |
| ROIC | Strong quality/economic-profit rationale | Slow | Invested-capital definition, goodwill, leases, cyclicality | Keep high weight; score ROIC spread and stability |
| Gross profits/assets | Strong documented profitability signal | Slow | Asset-light bias and industry accounting | Keep; industry-neutralize and avoid duplicating margin/ROIC |
| ROE | Useful for financials and broad quality | Slow | Leverage and negative/small equity distort | Reduce for general firms; emphasize normalized ROTCE for banks/insurers |
| FCF yield | Value/cash-generation hybrid | Slow | Same issues as EV/FCF; market-cap denominator ignores leverage | Move to valuation; prefer enterprise yield |
| Profit margin | Descriptive quality and business-model economics | Slow | Cross-industry incomparability, cyclicality, tax/one-offs | Retain as industry residual and stability measure, not raw universal band |
| Cash conversion | Detects weak earnings realization | Quarterly/annual | Overlaps accruals; growth working capital and capex distort | Keep modestly in accounting quality with multi-year measure |
| Interest coverage | Basic solvency indicator | Medium | Backward-looking EBIT, floating rates, maturity wall ignored | Keep; add fixed-charge coverage and forward interest burden |
| Net debt/EBITDA | Standard leverage measure | Medium | EBITDA/cycle/profile flaws; net cash location/restrictions | Keep for industrial profiles with cycle normalization |
| Debt/equity | Coarse leverage measure | Medium | Book-equity denominator makes it unstable | Reduce/remove when better leverage metrics exist |
| Current ratio | Basic short-term liquidity | Medium | Industry working-capital models differ; inventory quality ignored | Low weight or diagnostic; use cash runway/liquidity facilities instead |
| Altman Z / Z'' | Established distress screen in calibrated populations | Medium | Model/version and industry domain errors | Keep only as named variant and risk flag, not broad alpha factor |
| Revenue growth | Fundamental growth input | Medium | Acquisition, FX, inflation, unprofitable growth | Keep after organic/per-share/industry adjustment |
| EPS growth | Growth plus operating/financial leverage | Medium | Buybacks, tax, one-offs, negative base | Reduce raw weight; use normalized per-share and consensus revisions |
| Three-year FCF growth | Longer cash-growth evidence | Medium-slow | Endpoint sensitivity and negative base | Keep only with robust slope/CAGR rules and coverage |
| Operating-margin trend | Captures improving economics/incremental margin | Medium | Cycle, mix, restructuring, accounting | Keep; industry residualize and require persistence |
| Earnings surprise | Revisions/PEAD prior, tactical horizon | Fast | Estimate quality and exact announcement timing | Move entirely to timeliness; combine with revision breadth/history |
| Net buyback yield | Net issuance anomaly/shareholder yield | Slow | Debt-funded or overvalued repurchases | Keep with leverage and valuation interaction |
| SBC/revenue | Captures dilution/economic labor cost | Slow | Industry/lifecycle and grant accounting | Keep, but net against share-count dilution and cash compensation economics |
| Capex/depreciation | Rough reinvestment/lifecycle signal | Slow | Inflation, maintenance/growth split, intangible investment | Replace with reinvestment and incremental ROIC where possible |
| Asset growth | Well-established investment factor prior | Slow | M&A, financial firms, intangibles, lifecycle | Keep with profile/industry normalization; do not reward indiscriminate shrinkage |
| Accruals ratio | Historical earnings-quality anomaly | Medium | Documented decay, definition variants, overlap with conversion | Retain small weight or as veto; validate variant-specific OOS IC |
| Piotroski F-score | Useful composite historically, especially among value firms | Annual | Binary information loss and domain dependence | Keep as diagnostic/composite; avoid 45% bucket dominance without validation |
| DSO trend | Potential revenue-quality warning | Quarterly | Seasonality, mix, acquisitions, growth correlation | Use industry/growth residual and persistence; never universal raw band |
| Inventory-days trend | Potential demand/obsolescence warning | Quarterly | Supply-chain strategy, commodities, seasonality | Profile-specific only; distinguish raw materials/WIP/finished goods |
| 12–1 return | Robust cross-sectional momentum prior | Months | Crash risk, turnover, factor crowding | Keep as primary momentum signal |
| Relative strength vs SPY | Short-horizon market-relative trend | Weeks | Market beta and sector contamination | Replace with market/sector residual momentum for ranking |
| Sharpe | Risk-adjusted historical return statistic | Window-dependent | Estimation error; mixes alpha and risk | Report as risk/performance, not alpha input |
| Sortino | Downside-risk-adjusted historical return | Window-dependent | Very noisy downside sample; overlaps Sharpe | Report as risk/performance, not alpha input |
| Maximum drawdown | Intuitive path-risk statistic | Regime/path dependent | Backward-looking, sample-start sensitivity | Report and stress; do not treat as independent alpha evidence |
| Volume confirmation | Behavioral/liquidity confirmation | Days/weeks | Fragmented volume, event dependence, weak persistence | Remove or reduce in alpha; use for execution/liquidity diagnostics |
| Low beta | Defensive/BAB prior in risk-adjusted returns | Slow | Sector/rate exposures and leverage constraint mechanism | Treat as explicit style/risk exposure; allocate intentionally |
| News sentiment | Event information and attention | Days | Duplicates, entity errors, novelty decay, model drift | Keep as alert/event classifier; rank only if incremental PIT IC survives |
| Short interest | Informed positioning versus squeeze/crowding | Weeks/months | Reporting lag, borrow supply, nonlinear effects | Use nonlinear context/risk; avoid simple universal penalty |
| Opportunistic insider activity | Evidence is strongest for non-routine purchases/clusters | One to three months | Sparse trades, coding/classification, executive motives | Keep bounded, event-timestamped, and independent of routine sales |
| Macro regime | Conditional risk/discount-rate context | Months | Timing instability, vintage revisions, sector exposure masquerading as alpha | Use scenario/risk conditioning with ALFRED vintages; do not tune a ±3 overlay casually |

## 3.4 Factor-by-factor interaction analysis

* **Value × quality:** the highest-priority interaction. Cheap weak firms and expensive quality firms have different expected returns. The platform’s quality-value screen is directionally right, but own-history requires far more than 12 observations and peer value deserves more than 15% when history is shallow.
* **Momentum × value:** negatively correlated in many regimes and useful for diversification, but naive blending can cancel signals. Portfolio sleeves with explicit risk budgets are more interpretable than one composite.
* **Momentum × volatility:** raw momentum tends to load into high-volatility losers before rebounds. Volatility scaling and dynamic beta control reduce crash severity but do not eliminate it.
* **Growth × profitability:** growth creates value only when incremental returns exceed cost of capital. Raw revenue growth should not score highly without gross margin, unit economics, reinvestment needs, and dilution.
* **Buybacks × valuation × leverage:** repurchases are beneficial when shares are undervalued and funded sustainably. A high buyback yield at extreme valuation or rising net debt can destroy value.
* **Accruals × growth:** working-capital investment naturally rises during growth. DSO/inventory signals must be residualized against sales growth and industry seasonality.
* **Low beta × sector:** utilities, staples, and REITs can dominate. Neutralize sector or explicitly accept a defensive sector bet.

## 3.5 Correlation and orthogonality requirements

The existing equicorrelation approximation and family cap are diagnostics, not an institutional solution. Produce monthly factor correlation, partial correlation, incremental IC, turnover correlation, and marginal contribution to portfolio risk. A factor remains only if it contributes one of: independent OOS IC, tail-risk reduction, turnover reduction, or a necessary economic constraint. “Different name” is not a reason.

---

# 4. Business Model Profiles

The existing profiles cover insurers, banks, REITs, utilities, commodity producers, and biotech, but they are contracts rather than complete live models. Industrials, software, semiconductors, healthcare services/devices, consumer, telecom, materials, and transportation still fall largely into `general`. That is not industry-aware scoring.

| Industry | Metrics never used without qualification | Metrics that should always be present | Missing/high-value additions | Quality and forward adjustments |
|---|---|---|---|---|
| Industrials | P/S across dissimilar margins; current ratio as sole liquidity test; raw capex/depreciation | Organic revenue growth, backlog, book-to-bill, segment margin, ROIC, FCF conversion, leverage | Aftermarket/service mix, price-cost, working-capital cycle, order cancellation, pension deficit | Normalize cycle and acquisitions; separate volume, price, FX, M&A; measure incremental margins |
| Software | P/B, tangible book, generic capex/depreciation; EBITDA that adds back recurring SBC | ARR/revenue growth, gross margin, FCF margin, net retention, SBC, dilution, CAC/payback where available | Rule-of-40 decomposition, remaining performance obligations, churn, customer concentration, capitalized commissions, revenue recognition | Treat SBC as economic cost; distinguish usage-based from seat-based revenue; normalize cloud transition |
| Semiconductors | Single-period P/E/PEG; raw inventory days across foundry/fabless models | Cycle-normalized gross margin, inventory/channel days, capex intensity, FCF, market share, customer concentration | Utilization, wafer starts, node mix, book-to-bill, lead times, foundry commitments, geopolitical fabrication exposure | Mid-cycle earnings and replacement capex; separate secular content growth from inventory cycle |
| Insurance | Industrial FCF, current ratio, net debt/EBITDA, EV/EBITDA, Piotroski without modification | Combined ratio for P&C, reserve development, normalized ROE, RBC/statutory capital, book-value growth, investment yield | Duration mismatch, reinsurance recoverables, social inflation, catastrophe PML, surrender risk, product spread guarantees | Normalize catastrophe losses and reserve releases; stress rates, credit, mortality, lapse, and inflation |
| Banks | EV/EBITDA, FCF yield, current ratio, industrial debt metrics, Altman Z | CET1, tangible common equity, ROTCE, NIM, efficiency, NPAs, net charge-offs, reserve coverage, deposits | Uninsured deposits, securities marks, CRE concentration, liquidity coverage, wholesale funding, duration gap | Through-cycle credit costs and normalized NIM; stress deposit beta, unemployment, property prices, curve |
| Utilities | Unqualified FCF yield and generic asset growth | Regulated mix, rate-base growth, allowed/earned ROE, FFO/debt, interest coverage, funding need, jurisdiction quality | Regulatory lag, customer affordability, wildfire/nuclear liability, equity issuance need, load growth | Model rate-case calendar, financing plan, allowed return vs cost of capital, weather normalization |
| Energy | Spot P/E/PEG, current-cycle EBITDA without normalization | Realized price, production, lifting cost, reserve life/replacement, FCF breakeven, leverage, capital return | Hedge book, decline rates, finding/development costs, methane/carbon liability, acreage quality, decommissioning | Scenario NAV across commodity decks; normalize mid-cycle margins; distinguish integrated/refining/E&P |
| REITs | EPS P/E, generic FCF, current ratio, book value without property marks | FFO/AFFO, P/FFO, NAV discount, same-store NOI, occupancy, debt/EBITDAre, fixed-charge coverage, payout | Lease expiry, rent spreads, tenant concentration, debt maturity, secured debt, development yield, cap rates | Property-type and geography-specific cap rates; mark debt and assets; model refinancing and supply |
| Healthcare | One generic sector band; growth without payer/regulatory context | Organic growth, margin, ROIC, FCF, pipeline/product mix, reimbursement exposure | Procedure volume, payer mix, patent/exclusivity, recalls, trial/regulatory calendar, customer concentration | Probability-adjust launches/pipeline; separate devices, services, managed care, pharma, diagnostics |
| Biotech | P/E/PEG/PB for pre-profit firms; Altman Z; pipeline “count” | Cash runway, burn, dilution, stage, indication, trial design, binary-event risk | Probability of technical/regulatory success, addressable treated population, competitive standard of care, royalty economics | rNPV by asset and indication; scenario dilution; correlated trial risks; post-approval commercialization |
| Consumer | P/S without gross-margin context; raw growth that includes store openings/acquisitions | Same-store sales, units/traffic/ticket, gross margin, inventory, ROIC, FCF, leverage | Cohort/store economics, markdowns, loyalty, private label, channel mix, promotional intensity | Separate price, mix, traffic, units; normalize commodities/FX; test consumer-income sensitivity |
| Telecom | EBITDA without spectrum/lease debt; dividend yield alone | ARPU, churn, subscribers, capex, spectrum liabilities, FCF after leases, leverage | Network quality, fixed wireless/fiber economics, handset financing, regulatory obligations | Adjust debt for leases/spectrum; model capex cycle and price competition; distinguish subscriber quality |
| Materials | Spot multiples at commodity peak; raw margin | Mid-cycle margin, cost-curve position, capacity, utilization, FCF breakeven, leverage | Feedstock/energy exposure, contracts, environmental liabilities, reserve grade, project execution | Commodity/scenario normalization, cost inflation, currency, maintenance versus growth capex |
| Transportation | P/S; unadjusted P/E at cycle extremes; generic inventory metrics | Yield/rate, volume/load factor, unit cost, utilization, fleet age, capex, leverage, FCF | Contract exposure, fuel hedges, labor, network density, maintenance, orderbook, regulatory/safety | Normalize fuel and cycle; use lease-adjusted leverage; segment airlines, rails, trucking, logistics |

**Profile-engine correction:** classification based on sector/industry strings plus a few ticker overrides is too fragile. Use an effective-dated security master with GICS/NAICS, issuer/entity hierarchy, business-model tags, and analyst override history. Conglomerates require segment-level mixed profiles. Effort: 4–8 weeks plus data licensing. Expected improvement: very high for false-comparability reduction.

---

# 5. Momentum System

## 5.1 Current model audit

| Element | Current treatment | Judgment |
|---|---|---|
| 12–1 | 40%; exact month-end, skips recent month | Correct primary signal; use adjusted total returns and verify delisting/corporate actions |
| 12–7 | 20% | This is an older five-month formation slice, heavily overlapping 12–1; lower to 0–10% unless incremental IC is proven |
| 6–1 | 15% | Reasonable faster complement; overlaps 12–1 |
| 52-week-high proximity | 15% | Supported behavioral proxy but mostly redundant; 5–10% maximum |
| Industry-relative momentum | 10% | Good idea; leave-one-out median and minimum peers are correct; needs effective-dated peer groups |
| Sharpe / Sortino | Used in legacy market behavior and ETF risk | Do not call these momentum factors. Window-sensitive and redundant with return/volatility |
| Volatility | Used for sizing/sleeve scaling | Correct location; needs ex-ante forecast, not only trailing realized volatility |
| Relative strength | Legacy 20-day versus SPY | Too short and benchmark-specific; tactical only |
| Volume confirmation | Legacy 8% market behavior | Weak/noisy; reduce or use for liquidity/execution |
| Distance from highs | In momentum | Acceptable small feature; do not count as independent evidence |
| Trend persistence | Implicit through overlapping horizons | Add explicit sign/breadth/persistence if it earns incremental IC |
| Momentum crashes | Regime variant list only | Not implemented as a validated dynamic control |
| Volatility scaling | Sleeve helper exists | Correct, but disconnected from actual portfolio construction |
| Hysteresis | Enter 90th / exit 75th percentile | Strong turnover-control design; validate buffer width net of cost |
| Monthly rebalance | Intended | Appropriate baseline; current historical backtest re-ranks weekly, creating methodology inconsistency |
| Turnover | 30% monthly maximum config | No demonstrated enforcement/order optimizer or realized turnover report |
| Sector neutrality | 25% sector ceiling | Ceiling is not neutrality; residualize or constrain active sector exposure |
| Residual momentum | Missing | Add residual returns after market/sector/style factor regression |
| Time-series momentum | Missing | Useful for sleeve risk/regime, not a substitute for cross-sectional selection |
| Cross-sectional momentum | Present | Correct core framing |
| Breadth | Missing | Add fraction of industry/market above trend and dispersion; useful for crash/regime context |
| Ranking | Winsorized z-scores and percentiles | Sound baseline; missing-value contribution is currently zero, which equals cross-sectional mean without confidence penalty |
| Visualization | Ranked screen with contributions/eligibility fields | Needs factor waterfall, percentile history, turnover state, regime, confidence, and accessible data table |

## 5.2 Critical formula issue

`momentum_factors` requires 13 month ends and calculates start/end offsets correctly for its documented windows. However, the diagnostic describes 12–1 as 11 included return months, 12–7 as five, and 6–1 as five. Naming must make that convention explicit because practitioners use “12–1” inconsistently. The platform should publish formation start, formation end, skip window, return type, corporate-action basis, and annualization status for every observation. The boundary diagnostic is excellent and should become part of the public factor lineage.

## 5.3 Institutional-grade target

```text
eligible universe
  -> PIT security master + liquidity/price/corporate-action gates
  -> adjusted total returns
  -> raw 12-1, 6-1, residual 12-1, industry relative
  -> robust cross-sectional normalization
  -> combine only incremental signals
  -> beta/sector/country/style neutralization
  -> crash regime + breadth overlay
  -> ex-ante volatility scaling
  -> buffer/hold constraints
  -> cost-aware optimizer and participation limits
  -> orders, fills, realized cost and attribution
```

Recommended initial weights before validation: 50% 12–1, 20% 6–1, 20% residual 12–1, 10% industry relative; high-proximity becomes a tie-breaker, and 12–7 is removed. This is a research hypothesis, not a production answer. Select the final blend using purged walk-forward incremental IC and net returns.

**Crash management:** estimate market drawdown state, recent market return, momentum long/short beta, cross-sectional dispersion, and realized correlation. Scale rather than turn the signal off. Sudden rebounds after severe declines are the known danger. Dynamic hedging must be evaluated net of whipsaw and cannot be justified by a handful of recent regimes.

**Turnover:** report one-way turnover, two-way turnover, names entered/exited, buffer saves, estimated spread, market impact, borrow where relevant, and capacity. A 30% cap without an optimization algorithm is a configuration wish.

---

# 6. Recommendation Engine

## 6.1 Label taxonomy

| Requested label | Proper meaning | Current support | Decision |
|---|---|---|---|
| BUY | Initiate at target weight after portfolio/cost constraints | v2 “buy candidate,” not a final order | Keep only as **BUY CANDIDATE** until portfolio approval |
| ACCUMULATE | Add toward target, thesis and valuation intact | Supported for existing positions | Keep; require marginal portfolio benefit and add cadence |
| WATCH | Evidence merits monitoring, no trade | Supported | Keep |
| TACTICAL | Short-horizon opportunity with explicit exit horizon | Supported as candidate | Keep separate sleeve, risk budget, and benchmark |
| HOLD | No company action for an existing position | Supported | Keep; do not imply endorsement for a new investor |
| TRIM | Reduce a specified amount for risk/thesis/valuation | Supported with percentage calculation | Keep; split reason into thesis, risk, tax, and rebalance |
| EXIT | Liquidate a position because mandate/risk/stop requires it | Supported as position action | Keep distinct from SELL thesis |
| SELL | Fundamental thesis invalidated / negative expected value | Legacy and v2 thesis-break | Keep as company view; never derive from cost basis alone |
| INSUFFICIENT DATA | No reliable view | Supported | Keep and make it dominant over all positive labels |

The taxonomy is stronger than a single Strong Buy–Strong Sell scale because it separates company research from position management. But the UI should always show two fields: `Research view` and `Position action`. “BUY” without a portfolio, price, tax lot, and execution context is not a professional decision.

## 6.2 Logic audit

* **Decision matrix:** transparent, but 75/55/70 thresholds are arbitrary. Calibrate each transition on prospective outcome distributions and decision costs.
* **State transitions:** hysteresis exists for momentum, but recommendation states have no explicit transition graph, minimum dwell time, previous-state input, or transition audit. A score oscillating around 75 can flip daily.
* **Confidence gates:** 0.40/0.60/0.80 are sensible labels but uncalibrated. Confidence should mean a measured probability or reliability class, not a linear blend of availability and constants.
* **Coverage gates:** critical-field checks are good. General profile requires forward estimates, making most free-data v2 recommendations insufficient; that is honest, but it means the live product cannot claim v2 breadth.
* **Severity:** deterioration requires two distinct subfactors within a group and two periods. This is better than two arbitrary raw metrics, but shared economic drivers can still be counted as independent.
* **Position sizing:** an ATR helper and 5% cap exist. There is no portfolio covariance, forecast alpha, optimization, lot/tax/execution integration, or approved order workflow.
* **Portfolio fit:** current/target/max, sector/theme, look-through, factor, and marginal-risk flags are modeled. Most inputs are supplied booleans rather than calculated risk analytics.
* **Stops:** multiple profiles are configurable. The legacy browser fixed stops can override the company view, creating a second authority.
* **Tax:** a categorical multiplier reduces trims. It does not inspect tax lots, holding periods, wash sales, loss harvesting, account type, or client constraints.
* **Economic threshold:** $50, 5 bps of portfolio, and 5× transaction cost are useful guards. Transaction cost estimation itself is not institutional.

## 6.3 How professional PM decisions are made

Professional decisions are portfolio-relative and opportunity-cost based:

1. update expected return and its uncertainty from new information;
2. identify whether information changes the thesis, horizon, or risk rather than merely price;
3. compare the holding with the best replacement and cash;
4. measure marginal factor, sector, country, liquidity, and tail risk;
5. optimize after spreads, impact, taxes, borrow, and turnover budget;
6. check mandate/compliance limits;
7. route for approval/execution;
8. record ex-ante rationale and expected contribution;
9. attribute realized outcome to thesis, sizing, timing, and cost.

A stop is not automatically professional risk management. Fixed percentage stops often realize volatility and can conflict with long-horizon value strategies. Stops are appropriate when tied to strategy design, liquidity, gap risk, or a validated loss-control overlay. Thesis breaks, mandate breaches, and risk-limit breaches are more defensible universal exits than “down 20% from cost.”

**Required state machine:** `insufficient -> watch -> candidate -> approved -> building -> target -> trim/review -> exit`, with allowed transitions, dwell/buffer rules, event overrides, human approval, and immutable reason codes. Effort: 3–5 weeks. Expected improvement: high operational consistency.

---

# 7. Portfolio Construction

## 7.1 Current capability

The portfolio page tracks positions, cost basis, purchase date, current value, simple concentration, stop levels, and same-cash-flow comparisons with SPY. The same-day benchmark comparison is a good consumer calculation because it avoids comparing against the wrong entry date. It is not performance attribution: there are no dividends, fees, cash flows beyond recorded buys, corporate actions, tax lots, time-weighted return, money-weighted return, or reconciliation to a custodian book of record.

| Requirement | Current status | Required institutional design |
|---|---|---|
| Position sizing | ATR helper; default caps | Forecast-alpha/uncertainty and marginal-risk sizing with liquidity/cost constraints |
| Factor diversification | Boolean breach input in v2 | Holdings-level factor exposures, covariance, active risk contributions |
| Sector/industry | Simple sector percentages | Effective-dated classifications, benchmark-relative active weights, nested industry constraints |
| Country/currency | Missing | Domicile, revenue geography, listing/currency, FX hedge exposure |
| Beta | Security metric, not portfolio aggregation | Portfolio beta and nonlinear exposure by regime |
| Volatility | Sleeve scalar helper | Ex-ante covariance model with specific/factor risk |
| Tracking error | ETF metric only | Portfolio active risk against chosen benchmark |
| Maximum drawdown | Historical stock/ETF metric | Portfolio scenario and path analysis; drawdown budget is not optimizable directly without approximation |
| Concentration | 25%/35% browser warnings; 5%/25% v2 defaults | One authoritative limits service; issuer, sector, theme, factor, liquidity, and look-through |
| Cash | Display/comparison only | Cash target, liquidity buffer, collateral, subscriptions/redemptions, opportunity cost |
| Expected return | Score used as proxy | Calibrated horizon-specific alpha forecast in return units with error bands |
| Expected volatility | Missing at portfolio level | Factor/statistical covariance forecast and model comparison |
| Expected alpha | Missing | Score-to-forward-return calibration net of decay and costs |

## 7.2 Target optimizer

Start with a constrained mean-variance/risk-budget formulation, not a black-box optimizer:

```text
maximize: expected alpha - lambda * active variance - costs - taxes - turnover penalty

subject to:
  sum(weights) + cash = 1
  per-name, issuer, sector, industry, country, theme limits
  beta and tracking-error bands
  factor exposure bands
  liquidity / days-to-liquidate / ADV participation limits
  minimum and maximum holdings
  turnover budget and lot-size rules
  restricted list and mandate rules
```

Expected returns are the least reliable input. Use shrinkage, robust optimization, and scenario ranges; never let small forecast differences produce extreme weights. Covariance should combine fundamental factor and statistical/specific risk, with shrinkage and stress overrides. Provide equal-weight, risk-parity, minimum-variance, benchmark, and current portfolio as comparison portfolios.

**Phased evolution:**

1. portfolio accounting and reconciled returns;
2. exposure and covariance service;
3. what-if marginal risk/cost engine;
4. constrained optimizer in shadow;
5. pre-trade compliance and tax lots;
6. order/fill feedback and attribution.

Effort: 2–6 months for a credible equity-only engine; longer for multi-asset. Expected improvement: critical. Research support: strong for diversification and cost-aware construction, weak for any one optimizer’s estimated alpha.

---

# 8. Backtesting and Validation

## 8.1 What is good

Rank IC, quantile spreads, monotonicity, ICIR, a t-stat hurdle, deflated Sharpe, probability of backtest overfitting, bootstrap utilities, immutable shadow snapshots, and paper logs are the right vocabulary and mostly the right functions. The deflated Sharpe method exists because selection and non-normal returns inflate conventional Sharpe ([Bailey and López de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)). The repository explicitly warns that the honest trial count must be supplied. That is excellent model-risk thinking.

## 8.2 Why current evidence is inadequate

| Risk | Status | Consequence |
|---|---|---|
| Point-in-time fundamentals | Approximate 45-day report lag in old backtest; canonical store only recently started | Restatement and availability bias remain |
| Point-in-time estimates | Snapshot collector exists; little/no historical depth | Tactical revision model cannot be backtested honestly |
| Survivorship | Current universe plus three PIT universe snapshots | Departed, bankrupt, acquired, and delisted names are not credibly represented |
| Look-ahead | Some explicit `as_of` and filing-date logic | Provider histories and classification changes may still leak current knowledge |
| Corporate actions/delistings | Not demonstrated | Return and universe bias |
| Costs | No credible spread/impact/tax model in historical result | Weekly top-20 strategy likely overstated |
| Rebalance consistency | Historical artifact re-ranks weekly; momentum design says monthly | Validation does not match intended production policy |
| Sample length | 52-week headline; optimizer 156 weeks | No full rate, inflation, recession, crash, and recovery cycles |
| Breadth | 120 names in headline backtest | Weak cross-sectional power and capacity inference |
| Multiple testing | Functions exist; no published candidate report tying 200 trials to promotion | Controls are not part of the release gate |
| Holdout | Three overlapping/short folds reported | Too few independent regimes; bespoke score objective |
| Shadow portfolio | Config and pages exist | No long prospective return record |

The 13.89% versus 8.42% one-year result is not evidence of repeatable alpha. It is one path, a short bull-market sample, with weekly turnover and no credible costs. The result should not appear in marketing or influence weight selection.

## 8.3 Required research protocol

1. **Freeze the question.** Define universe, horizon, signal availability, rebalance, benchmark, neutralization, costs, and promotion criterion before testing.
2. **Use a licensed PIT research database.** Include delisted securities, effective-dated identifiers/classifications, filing availability, original estimates, revisions, corporate actions, and total returns.
3. **Create a development/train period, validation period, and untouched final holdout.** The final holdout is accessed once by an independent reviewer.
4. **Purged/embargoed walk-forward splits.** Prevent overlapping forward-return labels from leaking.
5. **Measure monthly rank IC and Newey-West confidence, quantile monotonicity, top-minus-bottom and top-minus-universe returns, turnover, capacity, exposure, and decay curves.**
6. **Evaluate gross and net.** Spreads, impact, delay, borrow, fees, taxes where relevant, and missed fills.
7. **Track every trial.** Config hash, researcher, hypothesis, dataset version, code SHA, results. Deflate using the family’s effective number of trials, not the winning script’s counter.
8. **Bootstrap in blocks and by regime.** Preserve autocorrelation; report probability of positive net alpha and worst-decile outcome.
9. **Benchmark alternatives.** Equal weight, sector-neutral, value, quality, momentum, and simple published factors. Complexity must beat a simple baseline.
10. **Prospective shadow for 12–24 months.** Freeze production candidates and timestamp orders before returns.
11. **Independent replication.** A second implementation must reproduce factor values and portfolio returns.
12. **Promotion gate.** Economic significance, statistical significance, stable regimes, acceptable turnover/capacity, no unexplained exposures, and documented failure conditions.

Minimum useful history is 15–20 years for slow structural factors and as much high-quality PIT estimate history as licensing permits. A shorter post-2009 period may be a supplemental regime test, never the only test.

---

# 9. Frontend UX

The UI/UX review applies a professional data-dense dashboard standard: keyboard access, semantic structure, visible provenance, non-color encoding, responsive tables/charts, exact-value access, stable navigation, and decision hierarchy. The application has a skip link, labelled icon buttons, desktop/mobile navigation, semantic tables in several places, loading/empty states, and accessible chart labels in parts of the code. Those are good foundations.

## 9.1 Cross-product problems

1. **The information architecture does not match the product model.** “Research” routes to Picks, “Screens” routes only to Momentum, and other screens are discoverable from internal links rather than first-class navigation. Stock and ETF detail are modals, preventing durable URLs, sharing, browser history, and research-note linking.
2. **Recommendation authority is obscured.** The UI can render legacy recommendation, client fallback, v2 confidence overrides, and position stops. Users need the model/policy version and whether a label is production, shadow, or portfolio-specific beside the label.
3. **Dense content is card-heavy.** Professional users need customizable tables, saved views, column selection, keyboard navigation, exports, cross-sectional distributions, and multi-select comparison.
4. **Charts are not yet professional analytical instruments.** The bundle has homegrown SVG charts, duplicate keys, timed-out tests, and limited accessible table alternatives. There is no consistent zoom/crosshair/tooltip/export/benchmark/event overlay framework.
5. **Responsive design hides rather than reformats some density.** A professional mobile view should prioritize action, risk, and freshness while preserving drill-down. Wide portfolio forms/tables and inline styles are brittle.
6. **No route-level splitting.** A 929 kB bundle increases initial latency and couples unrelated authenticated finance tools to research pages.
7. **Status is global but decision provenance is local.** Users need freshness per metric, source, period, availability date, conflict, and confidence at the point of use.

## 9.2 Page-by-page review

| Page | Effective elements | Defects | Exact redesign |
|---|---|---|---|
| Dashboard | Freshness, top candidates, trend and theme panels give breadth | Too many heterogeneous cards; “Good morning” consumes prime space; leader score is shown before data quality and portfolio relevance | Top strip: data health, portfolio risk, actionable changes. Then decision queue. Move discovery/theme panels below. Add “changed since last run” and exception list. |
| Research / Picks | Candidate grid and detail access | Cards impede cross-sectional comparison; no saved screen/query; no stable detail URL | Default to sortable virtualized table with score, structural, tactical, confidence, coverage, change, sector, valuation, risk. Cards optional. |
| Stock detail | Layered metrics, strengths/risks, recommendation explanation | Modal breaks deep linking and comparison; raw score may dominate uncertainty; limited historical factor context | Route `/security/:id`; sticky header with research view, position action, confidence, freshness. Tabs: thesis, factors, estimates, valuation history, risk, filings/news, lineage. |
| ETF detail | Dedicated ETF comparison components and peer labels | Still embedded/modal-oriented; proxy benchmark caveats are easy to miss; holdings/look-through limited | Route with mandate, index, tracking drag, spread/AUM, structure, holdings, overlap, tax, scenario, and comparison. Put benchmark confidence next to every relative metric. |
| Momentum | Eligibility reasons, factor contributions, hysteresis state exist in data | Screen UI does not surface enough methodology state; no breadth/regime/turnover panel | Table plus factor waterfall, percentile history, entry/exit buffer, sector exposure, breadth, regime scale, turnover, and “why changed.” |
| Theme | Eligibility and stretched-valuation flag are visible | Exposure quality can appear like a recommendation; provenance of exposure is not primary | Label “exposure, not expected return.” Show revenue/profit exposure evidence, source, confidence, time horizon, and valuation guardrail separately. |
| Portfolio | Same-day SPY comparison, purchase dates, concentration warnings, mobile cards | Not a book of record; 25% position guideline conflicts with v2 5%; no dividends/tax lots/cash/covariance; destructive Remove has no confirmation/undo | Reconciled account view; TWR/MWR; allocation and active risk; lots/tax; decision queue; what-if; authoritative limits; confirm/undo deletion. |
| Compare | ETF comparison exists; fixed-basis comparisons exist | No general multi-security comparison page | Add URL-addressable comparison with normalized metrics, history, factor radar only as secondary, valuation distribution, estimates, risk, and export. Use grouped bars/tables for precision. |
| Live validation | Valuable transparency into invariants | Passing probes may be mistaken for strategy validation | Separate “data contract checks” from “economic validation”; show observation counts, dates, failures, and promotion gate. |
| Methodology | Explanatory content supports trust | Risk of documenting intended rather than live behavior | Generate tables from active model manifest; clearly mark legacy, shadow, and promoted versions. |
| Finances | Useful personal-planning adjunct | Dilutes institutional research product; its tests time out and it loads in main bundle | Separate product/module and lazy-load; do not place personal budget data in institutional research navigation. |

## 9.3 Visual and accessibility priorities

* Use tabular numerals for all financial columns.
* Never encode gain/loss, confidence, or eligibility by red/green alone; add signs, icons, labels, and patterns.
* Every chart needs axes/units, keyboard-reachable exact values, a text insight, a tabular alternative, loading/error/empty states, and export.
* Maintain 4.5:1 text contrast, visible focus, 44×44 touch targets, reduced-motion handling, and no hover-only information.
* Add route-change focus management and preserve filter/scroll state on back navigation.
* Replace scattered inline styles with semantic tokens/components and establish one table, badge, alert, chart, and data-quality grammar.

Effort: 4–8 weeks for the information architecture and core analytical components. Expected improvement: high professional usefulness, not alpha.

---

# 10. Data Quality

## 10.1 Provider assessment

| Source | Appropriate use | Unacceptable reliance |
|---|---|---|
| SEC EDGAR/XBRL | Source filings, filing availability, statements, Form 4 | Automated metrics without taxonomy reconciliation and filing amendment handling |
| Yahoo/yfinance | Prototype prices/quotes and broad enrichment | Institutional production book of record; terms, stability, adjustment, identifiers, and support are inadequate |
| Alpha Vantage free tier | Small enrichment/backup | 900-name timely institutional universe; quota makes coverage structurally unequal |
| FRED | Macro context | Company-level alpha without release-vintage data (ALFRED) and explicit lag handling |
| Marketaux/news | Alerts and descriptive context | Material rank weight without deduplication, entity resolution, novelty, and vendor validation |
| Issuer ETF disclosures | NAV/spread/premium-discount | Assuming uniform endpoint semantics or availability |

## 10.2 Contract strengths and gaps

* **Abstraction:** good class boundary, but not all production fetch paths appear to use it consistently. Enforce adapters as the only vendor-key boundary with static checks.
* **Normalization:** observation objects include units, source field, periods, timestamps, flags, and transform version. This should be the universal representation. Many live observations still say `provider_period_not_supplied`.
* **Fallback:** stale-on-error is reasonable for display, dangerous for scoring unless the decision package explicitly degrades and decay is applied. A stale successful response is not current evidence.
* **Confidence:** currently heuristic. Calibrate provider reliability by field using historical reconciliation and correction rates.
* **Coverage:** weight-aware coverage is good. Also report cross-sectional coverage, sector bias, missingness mechanism, and change over time.
* **Staleness:** TTL by metric is better than one global timestamp. Use source effective/release/available dates; fetch time is not economic freshness.
* **Schema evolution:** read migrations handle old reader/new snapshot. Unknown newer schemas are passed through on an “additive-only” assumption; this is unsafe without `additionalProperties` policy and compatibility tests.
* **Validation:** JSON Schema and invariants are necessary. Current malformed JSON proves validation is not a required pre-commit/pre-publish gate.
* **Errors:** degraded modes exist, but broad exception swallowing can convert systemic failure into sparse “success.” Establish error budgets and fail closed for ranking-critical fields.
* **Diagnostics:** public debug views are useful. Separate operator diagnostics from user-facing provenance and avoid exposing sensitive raw paths.
* **Lineage:** partial. There is no graph from displayed score contribution to canonical observation to raw provider payload/hash to transform code/config.

## 10.3 Institutional data architecture

```text
raw immutable zone
  provider payload + legal entitlement + fetch metadata + checksum
        |
normalized observations
  security ID, metric ID, value, unit, period, effective/available/fetched time
        |
reconciliation and quality
  precedence, conflicts, validation, corrections, confidence
        |
PIT feature store
  as-of joins, universe membership, corporate actions, classifications
        |
model feature set
  immutable dataset ID + code/config hashes
        |
scores / portfolios / orders
  complete lineage and approval
```

Use permanent security and issuer identifiers rather than ticker as the primary key. Tickers change and are reused. Maintain entity/share-class relationships, exchange, currency, listing status, corporate actions, delisting return, classifications, and provider symbol mappings with effective dates.

**Data quality controls:** completeness, uniqueness, validity, timeliness, consistency, reconciliation, distribution drift, stale repeats, impossible jumps, unit flips, sign flips, split detection, period overlap, amendment handling, and cross-provider discrepancy. Each should have owner, severity, threshold, SLA, exception state, and resolution history.

Effort: 2–6 months for a credible equity research data foundation; ongoing data operations thereafter. Expected improvement: critical. Without it, further factor tuning has negative expected ROI.

---

# 11. Competitive Feature Analysis

Legend: **Better** means this platform has a substantively superior implementation for the stated use; **Equal** means comparable for the narrow feature; **Worse** means present but inferior; **Missing** means no credible implementation.

| Feature | Bloomberg | FactSet | Morningstar | Zacks | Seeking Alpha | Simply Wall St | Koyfin | Portfolio Visualizer | Finviz | Yahoo Finance |
|---|---|---|---|---|---|---|---|---|---|---|
| Transparent score formulas | Better | Better | Better | Better | Better | Better | Better | Equal | Better | Better |
| Structural/tactical separation | Better | Equal | Better | Better | Better | Better | Better | Better | Better | Better |
| Real-time/global data | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Missing | Worse | Worse |
| Point-in-time fundamentals/estimates | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Equal-to-worse |
| Industry-specific models | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Missing | Worse | Missing |
| Factor explainability | Equal for formulas, worse for depth | Worse | Equal | Equal | Equal | Equal | Equal | Better for custom analysis | Equal | Better |
| Screening customization | Worse | Worse | Worse | Worse | Worse | Equal | Worse | Worse | Worse | Equal |
| Portfolio accounting | Missing | Missing | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Worse |
| Portfolio risk model | Missing | Missing | Missing | Missing | Missing | Missing | Worse | Worse | Missing | Missing |
| Optimization | Missing | Missing | Missing | Missing | Missing | Missing | Missing | Missing | Missing | Missing |
| Attribution | Missing | Missing | Missing | Missing | Missing | Missing | Worse | Worse | Missing | Missing |
| Scenario/stress testing | Missing | Missing | Missing | Missing | Missing | Missing | Missing | Worse | Missing | Missing |
| Backtest governance | Worse | Worse | Worse/private | Equal-to-better in conceptual transparency | Unknown/private | Missing | Missing | Worse for portfolio tooling | Worse | Missing |
| News/research/transcripts | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Missing | Worse | Worse |
| Charts and custom workspaces | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Worse | Worse |
| Data lineage visible to user | Potentially Better in intent | Equal | Better | Better | Better | Better | Equal | Equal | Equal | Equal |
| API/integration | Worse | Worse | Worse | Worse | Worse | Missing | Worse | Missing | Worse | Worse |
| Alerts/collaboration/reporting | Missing | Missing | Missing | Worse | Worse | Worse | Worse | Missing | Worse | Worse |
| Low-cost deployability | Better | Better | Better | Better | Better | Equal | Better | Equal | Equal | Equal |

Explanations by competitor:

* **Bloomberg:** the gap is not prettier screens; it is the integrated data, identifier, news, communication, pricing, risk, scenario, order, and support network. This platform can remain more transparent but cannot approximate Bloomberg through additional free APIs.
* **FactSet:** FactSet’s documented pre/post calculation checks, reconciliation, standardization, multi-asset risk, attribution, scenario analysis, and APIs define the missing enterprise layer. Its public product claims over ten attribution models and workflow monitoring ([FactSet](https://www.factset.com/solutions/portfolio-analytics)).
* **Morningstar:** this platform’s stock factor logic is more inspectable, but Morningstar’s managed-investment coverage, holdings look-through, peer groups, blended benchmarks, optimizer, and reports are far ahead.
* **Zacks:** ValueSignal has broader structural reasoning, while Zacks has a mature revision-centered production dataset and clear short-horizon product. Zacks’ public performance disclosures distinguish backtests and delivered trades, though any vendor claim still requires independent diligence ([disclosure](https://www.zacks.com/performance_disclosure/)).
* **Seeking Alpha:** ValueSignal is more transparent; Seeking Alpha has much stronger content, estimates, daily refresh, coverage, alerts, and user workflow. Its factor set is simpler but production-tested at scale.
* **Simply Wall St:** ValueSignal can exceed its methodological transparency; Simply Wall St exceeds visual consistency, international breadth, onboarding, and report polish. Neither should be treated as an institutional risk system.
* **Koyfin:** Koyfin’s charting, saved views, filters, global coverage, alerts, and portfolio/reporting workflow make it much more useful for daily discretionary research. ValueSignal’s PIT and confidence aspirations are more explicit.
* **Portfolio Visualizer:** superior for allocation, factor analysis, Monte Carlo, and portfolio backtests; inferior for single-company fundamental analysis.
* **Finviz:** Finviz has faster discovery, maps, real-time Elite data, alerts, exports/APIs, correlations, holdings, and mature screening. ValueSignal provides deeper factor rationale and confidence concepts. Finviz documents real-time screens, exports/APIs, 8-year statements, ETF holdings, alerts, and backtests ([Finviz Elite](https://elite.finviz.com/help/elite.ashx)).
* **Yahoo Finance:** Yahoo is broader and more reliable as a consumer information destination; ValueSignal has deeper decision logic. Using Yahoo as a core upstream provider prevents a defensible claim of higher data quality.

---

# 12. Three-Horizon Roadmap

Scales: improvement 1–5 (5 highest); difficulty 1–5; research support 1–5; implementation risk 1–5.

## 12.1 Quick wins: 1–2 days each

| Rank | Work | Improvement | Difficulty | Research support | Risk | Exact completion criterion |
|---:|---|---:|---:|---:|---:|---|
| 1 | Repair and gate public JSON | 5 | 1 | 5 | 1 | Remove conflict markers; validate every public file; CI blocks merge/deploy; atomic manifest generated |
| 2 | Make test suite a hard release gate | 5 | 1 | 5 | 1 | No timeouts/warnings; deterministic chart tests; validation runs in the project venv |
| 3 | Display “legacy / shadow / promoted” everywhere | 4 | 1 | 5 | 1 | Every score/action shows model and policy status/version |
| 4 | Remove browser recommendation fallback in production | 4 | 1 | 5 | 2 | Missing server decision becomes unavailable, never recomputed with a different policy |
| 5 | Reconcile limit constants | 4 | 1 | 5 | 1 | One limits config; UI 25%/35% contradiction removed |
| 6 | Publish current validation limitations | 4 | 1 | 5 | 1 | Live invariant page says “contract validation, not return validation”; displays PIT depth |
| 7 | Add merge-marker and JSON parse pre-commit check | 4 | 1 | 5 | 1 | `rg '^(<<<<<<<|=======|>>>>>>>)' public pipeline/config` and parser gate |
| 8 | Add bundle route splitting | 3 | 2 | 4 | 2 | Lazy-load routes; initial chunk below defined budget |
| 9 | Correct destructive Remove UX | 2 | 1 | 5 | 1 | Confirm or undo; accessible announcement |
| 10 | Export methodology from active config | 3 | 2 | 5 | 2 | Documentation tables are generated from the active model manifest |

## 12.2 Medium projects: 1–2 weeks each

| Rank | Work | Improvement | Difficulty | Research support | Risk | Engineering/research detail |
|---:|---|---:|---:|---:|---:|---|
| 1 | Immutable dataset manifest and atomic publish | 5 | 3 | 5 | 2 | Content hashes, code/config SHA, watermarks, validation ID, rollback; UI reads one active manifest |
| 2 | One authoritative decision package | 5 | 3 | 5 | 3 | Server-generated company and position states; explicit precedence and reason namespace |
| 3 | Score contribution lineage view | 5 | 3 | 5 | 2 | From displayed contribution to observation/period/source/conflict/transform |
| 4 | Recommendation transition ledger | 4 | 3 | 4 | 2 | Previous state, event, buffer/dwell, approver, timestamp, state diagram |
| 5 | Data-quality control plane | 5 | 4 | 5 | 3 | Completeness, stale, outlier, discrepancy, coverage bias, owners, severity and SLA |
| 6 | Momentum model simplification experiment | 4 | 3 | 5 | 3 | Compare 12–1 baseline with residual/industry variants; net IC, turnover, crash regimes |
| 7 | Professional security route and comparison page | 4 | 4 | 4 | 3 | Deep links, saved state, table-first view, provenance, accessible charts/export |
| 8 | Portfolio accounting baseline | 5 | 4 | 5 | 3 | Cash flows, dividends, splits, fees, TWR/MWR, benchmark, custodian reconciliation |
| 9 | Effective-dated security master | 5 | 4 | 5 | 3 | Permanent IDs, ticker history, issuer/share class, status, classification, provider mappings |
| 10 | Trial registry and promotion report | 5 | 3 | 5 | 2 | Every experiment hashed; honest trial family; DSR/PBO/OOS result required to promote |

## 12.3 Major architecture: 1–3 months each

| Rank | Work | Improvement | Difficulty | Research support | Risk | Deliverable |
|---:|---|---:|---:|---:|---:|---|
| 1 | Licensed PIT data foundation | 5 | 5 | 5 | 4 | Survivorship-free fundamentals, estimates, classifications, actions, delistings, total returns |
| 2 | Canonical scoring replacement | 5 | 5 | 5 | 4 | All scores from canonical observations; legacy retired after parallel validation |
| 3 | Institutional validation program | 5 | 5 | 5 | 3 | 15–20 years, purged walk-forward, untouched holdout, costs, capacity, independent replication |
| 4 | Portfolio risk and optimization service | 5 | 5 | 5 | 5 | Covariance/factor model, marginal risk, scenarios, cost/tax-aware constrained optimizer |
| 5 | Industry model data products | 5 | 5 | 5 | 4 | Live bank/insurance/REIT/utility/energy/biotech plus software/semis/consumer/etc. with history |
| 6 | Model-risk governance | 5 | 4 | 5 | 3 | Inventory, owner, validation, limitations, approvals, monitoring, change control, retirement |
| 7 | API/event platform | 4 | 5 | 5 | 4 | Queryable history, entitlements, jobs/events, atomic releases, audit, SLOs |
| 8 | Execution and post-trade feedback | 4 | 5 | 5 | 5 | Pre-trade compliance, order proposals, fills, cost attribution, drift/rebalance workflow |
| 9 | Multi-tenant institutional security | 4 | 5 | 5 | 4 | RBAC/ABAC, SSO, secrets/KMS, audit retention, environment separation, incident controls |
| 10 | Professional analytical UI system | 4 | 4 | 4 | 3 | Tables, workspaces, charts, exports, notes, alerts, collaboration, accessibility and performance budgets |

The ordering is deliberate. Buying data and establishing an immutable PIT research foundation precede optimizing weights. Tuning on free, current-restated data makes the model more precisely wrong.

---

# 13. Overall Evaluation

## 13.1 Scores

| Dimension | Score /10 | Basis |
|---|---:|---|
| Architecture | 5.5 | Strong modular intent, undermined by dual generations, static-file release bus, and multiple policy authorities |
| Research quality | 5.0 | Correct factor instincts and caution, but little credible PIT/OOS evidence |
| Academic rigor | 5.5 | Papers and appropriate statistics inform design; citations sometimes justify exact weights they do not establish |
| Professional usefulness | 4.5 | Useful idea-generation prototype; weak as a daily PM/risk/data workflow |
| Extensibility | 6.5 | Configs/adapters/registries are extensible; required data and validation are not plug-and-play |
| Transparency | 7.5 | Formulas, comments, confidence, applicability, and shadow status are unusually visible |
| Reliability | 3.0 | Invalid published JSON, failed frontend tests, unofficial core data, no atomic release |
| Engineering | 5.5 | Good unit testing and thoughtful modules; release integrity, duplication, bundle design, and backend boundaries lag |
| User experience | 5.5 | Polished consumer dashboard foundation; not yet a professional analytical workstation |
| Institutional readiness | 2.0 | Missing book of record, licensed PIT data, validated alpha, risk model, optimizer, governance, controls, SLOs, and audit workflow |
| **Overall** | **4.9** | **Promising research prototype; unsuitable for delegated investment authority** |

## 13.2 Trust decisions

### Would I trust it to manage my own money?

No—not to manage money or generate autonomous trades. I would use it as a secondary research checklist after repairing release integrity, while independently verifying every source and making portfolio decisions elsewhere. Its output can help ask better questions; it has not demonstrated that its ranks produce net alpha or that its risk actions improve outcomes.

### Would I trust it to manage institutional money?

No. Not even a small institutional sleeve in the current state. The blockers are objective: malformed live data, shadow-only safer policy, unofficial data dependency, negligible PIT history, no reconciled accounting, no ex-ante portfolio risk, no cost-aware optimizer, no order/compliance process, no model validation record, and no operational governance.

### What prevents Bloomberg/FactSet quality?

The missing asset is not a feature list. It is an industrial data-and-workflow organization: licensed global datasets, identifiers, corporate actions, PIT estimates, reconciliation teams, field-level lineage, multi-asset analytics, risk models, entitlements, APIs, execution connectivity, reporting, support, uptime, security, and decades of operational exception handling. A small transparent model can be better at explaining itself; it cannot substitute for that infrastructure with more YAML.

### What prevents consistent outperformance of passive investing?

There is no demonstrated, statistically and economically significant net alpha. Published factor evidence is not proof that this construction beats an investable benchmark after crowding, turnover, impact, taxes, model decay, and selection bias. Scores are not calibrated to expected returns, portfolio construction is rudimentary, and the backtest sample is far too short. Even a correctly engineered platform cannot promise consistent outperformance; active returns are noisy, capacity-constrained, regime-dependent, and competitive.

### Single highest-ROI improvement

**Build the immutable point-in-time data and validation spine, then make it the mandatory input and release gate for the canonical model.**

This means licensed survivorship-free data, effective-dated security/universe history, original estimates and revisions, corporate actions/delistings, canonical typed observations, content-addressed dataset versions, honest trial registry, purged walk-forward evaluation, costs/capacity, prospective shadow portfolios, and an atomic validated manifest. Effort: 2–6 months for a credible first version. Expected improvement: transformative. Academic basis: every claimed factor and every validation statistic depends on correct as-of information. Engineering implication: it replaces committed mutable JSON and legacy scalar fields as the foundation. Implementation risk: high, but lower than continuing to tune a model on data that cannot answer what was known at the decision time.

Until that spine exists, new factors, finer weights, extra recommendation labels, and prettier charts mostly increase confidence faster than correctness.
