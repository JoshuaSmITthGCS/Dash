# Recommendation and position-management audit — shadow policy `decision-v2.0.0`

Date: 2026-08-02  
Status: implemented in shadow mode; legacy `recommendation` remains active

## Executive result

The active policy has four material correctness conflicts:

1. `advisor_engine.action_for()` turns two flags into the same 33% trim and can emit an un-namespaced 100% `SELL`.
2. `positionRisk.withStopLoss()` still upgrades the headline company action with a browser-side stop decision. It retains the original object, but the first label the user sees is still the position rule.
3. Backend and browser fallback deterioration rules use different thresholds and severity mappings.
4. Watchlist entry logic creates `BUY SETUP` from a third, client-side rule set with a 0.50 confidence threshold. It is not the same decision as backend company guidance.

The new output is additive at `recommendation_v2`, declares schema `5.0.0`, and exposes structural, timeliness, portfolio-fit, and position-rule states separately. No legacy recommendation was overwritten.

## Current decision lineage

| Rule ID | Source | Inputs | Threshold / lookback | Output | Priority / override | Confidence gate | Scope | Counts price? | Full exit? |
|---|---|---|---|---|---|---|---|---|---|
| LEG-SCORE-01 | `pipeline/scorer.py::valuation_score` | 28 accounting/valuation metrics | Bands and weights in `settings.json`; mixed current/TTM/forward periods | fundamental score and categories | Feeds composite | Coverage multiplier `0.65 + 0.35×coverage` | Company | No | No |
| LEG-SCORE-02 | `pipeline/advisor_engine.py::technical_factors` | closes, SPY closes, volume | 5/20/60/252 sessions; 60-session vol/high | technical score/detail | 15% composite input | Coverage 0.70–1.00 | Company | Yes | No |
| LEG-SCORE-03 | `advisor_engine.py::sentiment_score` | ticker-tagged articles | Current fetched news; five articles gives full coverage | sentiment score | 10% composite input | Article-count coverage | Company | Indirect reaction risk | No |
| LEG-SCORE-04 | `advisor_engine.py::build_research` | fundamental/technical/news scores | Fixed 75/15/10 blend | raw/base/final score | Modifiers add up to ±15 | Composite confidence 65/25/10 | Company | Yes | No |
| LEG-LABEL-01 | `advisor_engine.py::stance_for` | score, confidence | confidence <.45; score 75/60/45 | Attractive/Promising/Mixed/Caution | Display classification | .45 | Company | Indirectly | No |
| LEG-ACT-01 | `advisor_engine.py::action_for` | category scores, technical detail, news, shorts | category <45; coverage/interest/accrual thresholds; drawdown <-30; relative <-10; 20/60 decline; news <-.15 with 3 articles; short float ≥15% | HOLD/WATCH/TRIM/SELL | Published backend action wins | None tied to action confidence | Company presented as position guidance | Yes | Yes |
| LEG-ACT-02 | `advisor_engine.py::action_for` | factor count + score | 2 flags and score <45 → SELL 100%; 2 → TRIM 33%; 3 → TRIM 50% | fixed trim/full sell | Same priority for all severities | Text confidence only | Mixed | Yes | Yes |
| FALLBACK-01 | `src/lib/sellWatchLogic.js` | browser stock fields | fundamentals <50; 20d <-15; 5/20/60 decline; RS <-20; ≥3 negative articles | HOLD/WATCH/TRIM/SELL | Used only if backend action absent | No numerical gate | Mixed | Yes | Yes |
| CONF-UI-01 | `src/lib/recommendation.js::getRecommendation` | `analysis_v2.structural` and legacy action | <.40 → WATCH; <.60 suppress TRIM/SELL | UI action | Alters backend company action | Structural only; ignores timeliness confidence | Company | No | Suppresses it |
| ENTRY-01 | `src/lib/watchlistGuidance.js` | bull/bear score, score, confidence, 20d return, legacy action | thesis ≥5.5; score ≥65; confidence ≥.50; 20d >0 | BUY SETUP / DON'T BUY YET | Separate client verdict | .50 | Company + proposed position | Yes | No |
| STOP-01 | `src/lib/positionRisk.js::assessPositionStopLoss` | average cost, current price | cost loss ≤-20% | SELL | Upgrades headline through `withStopLoss` | None; user rule | Position | Yes | Yes |
| STOP-02 | `src/lib/positionRisk.js::assessPositionStopLoss` | average cost | cost loss ≤-12% | TRIM 33% | Upgrades headline | None | Position | Yes | No |
| STOP-03 | `src/lib/positionRisk.js::peakSincePurchase` | weekly closes after purchase | peak-to-current ≤-15% | TRIM 33% | Combines with cost stop | None | Position | Yes | No |
| STOP-04 | `src/lib/positionRisk.js::stopLossLevels` | average cost, high-water close | highest cost/trailing floor binds | displayed stop price | Informational | None | Position | Yes | No |
| PORT-01 | `src/lib/portfolioExposure.js` | browser holdings/value/sector | position >25%; sector >35% | warning text only | Does not affect action | None | Portfolio | No | No |
| UI-01 | `src/components/ActionGuidance.jsx` | merged recommendation | inherited | headline, badge, reasons, impact | Displays merged action first | inherited | Mixed | No recompute except shares/value | Displays full exit |
| UI-02 | `src/components/StockCard.jsx` | legacy backend action | non-HOLD only | colored badge and generic reason | Direct backend rendering | None | Mixed | No | Yes |
| UI-03 | `src/lib/portfolioSort.js` | action | HOLD 0, WATCH 1, TRIM 2, SELL 3 | sort priority | Frontend ordering | None | Position view | No | No |
| V2-SCORE-01 | `pipeline/scoring_v2.py::build_v2_analysis` | canonical metrics and applicability profile | confidence shrinkage to 50; <.40 insufficient; <.60 watch/review | structural/timeliness states | Additive shadow input | Explicit | Company | Timeliness may include price confirmation later | No |
| V2-POLICY-01 | `pipeline/recommendation_policy_v2.py` | V2 layers, deterioration groups, portfolio, position, events | all thresholds in `recommendation_policy_v2.json` | independent company and position actions | Shadow only | Explicit .40/.60/.80 | All four layers | Exactly one thesis group | Namespaced only |

## Conflicts, duplicates, and unreachable or implicit behavior

| Finding | Evidence | Consequence | Shadow-policy treatment |
|---|---|---|---|
| Stop action replaces the headline | `withStopLoss()` mutates `action` and `suggestedTrimPct` | Strong company thesis can appear as SELL | Independent `company.action` and `position_action`; stop reasons start `sell_position_` |
| Fixed factor-count sizing | backend 2→33%, 3→50% | Mild and severe evidence are sized alike | Base × severity × confidence × concentration × liquidity × tax/cost |
| Backend/browser disagreement | backend RS threshold -10; browser -20; browser severe factor can sell | Same data can render differently when published field is absent | Backend is authoritative; shadow UI never derives missing reasons or percentages |
| Price family repeats | composite technical score includes trend, risk, RS, drawdown; action logic again inspects drawdown, RS and momentum; stops inspect cost/high-water loss | Price can influence rank, group flag, and position action | Thesis grouping uses only sustained trend, RS, and volume as one `market_behavior` group; stops never vote in thesis |
| Confidence is not action confidence | active action emits `high`/`moderate` from branch labels, unrelated to numeric score confidence | Sparse data may read high confidence | Company action confidence is capped by the weaker structural/timeliness confidence |
| Timeliness confidence omitted in UI gate | `getRecommendation()` gates only structural confidence | Missing forward revisions can be ignored | Uses minimum structural/timeliness confidence |
| HOLD has two meanings | watchlists and no-position research can show HOLD | Users may read HOLD as a buy endorsement | `hold_existing_position` only when held; otherwise `watch`, `quality_watch`, or `avoid` |
| BUY is a separate client verdict | `watchlistGuidance` creates BUY SETUP | Entry label bypasses canonical matrix/critical fields | New company action owns entry classification; portfolio can still block adding |
| Concentration is disconnected | exposure engine only warns at 25%/35% | Thesis action and portfolio risk conflict silently | Portfolio fit can independently return concentration trim |
| Small trims are not checked | position impact simply multiplies shares | $10–$20 recommendations can appear | Minimum $50, portfolio fraction, and cost multiple; otherwise `review` |
| Sector magic/defaults | active fallback uses ROE/current ratio/D/E universally | Insurer/bank false positives | Applicability profile and critical-field declaration; HIG uses insurer profile |
| Stale/default behavior | missing sentiment becomes neutral 50; historical backtest does the same | Absence can look like evidence | Missing/stale/conflict arrays remain explicit and confidence is reduced |
| Unreachable legacy WATCH branch | browser `getSellWatchRecommendation` requires ≥2 factors before proceeding, then initializes WATCH, but two moderate flags become TRIM and any severe becomes SELL | WATCH after the factor-count gate is effectively limited to unusual severity values | Explicit matrix WATCH is evidence/entry state, not deterioration vote count |
| Action copy overstates evidence | “Multiple factors disagree with the thesis” for fixed trim | Moderate tactical weakness sounds like thesis failure | Namespaced, reason-specific copy |

No circular function calls were found. There is semantic circularity: price helps the composite score/stance, is tested again for deterioration, and is tested a third time against user stops.

## Canonical action definitions

- `buy`: no-position entry candidate; structural/timeliness/confidence/data quality and portfolio capacity pass.
- `accumulate`: gradual addition; strong structure and improving but not top-tier timing, within concentration limits.
- `hold_existing_position`: held security remains supported. It is never an entry instruction.
- `watch` / `quality_watch`: no position change; evidence is incomplete/mixed or timing is weak despite quality.
- `trim`: held position reduction sized by cause and context.
- `exit`: close a held position under a namespaced user, thesis, or portfolio rule.
- `avoid`: do not initiate; not an instruction to sell an existing holding.
- `sell_thesis`: verified company evidence failed, independent of cost basis.
- `insufficient_evidence`: company confidence below 0.40; prescriptive company actions suppressed.

## Shadow state machine

1. Canonicalize/apply sector profile and compute structural and timeliness raw scores.
2. Apply `effective = 50 + confidence × (raw − 50)` independently to each axis.
3. Declare data coverage, freshness, provider conflicts, stale fields, and missing fields.
4. Apply the configurable two-axis matrix.
5. Apply the company confidence gate; a verified thesis-break event is the only company bypass.
6. Evaluate three deterioration groups. Each group normally needs two distinct, persistent subfactors. Stops never enter a group.
7. Evaluate portfolio fit independently.
8. Evaluate the selected asset/strategy stop profile from adjusted cost/high-water data.
9. Resolve position action priority: verified thesis failure → hard/trailing user rule → portfolio constraint → severity trim → hold.
10. Check share precision and economic materiality. Emit `review` instead of a meaningless trim.
11. Serialize both company and position decisions with reason namespaces. Keep legacy output beside it.

## Configuration and contract

- Policy config: `pipeline/config/recommendation_policy_v2.json`
- Backend policy: `pipeline/recommendation_policy_v2.py`
- JSON Schema: `pipeline/schemas/recommendation-v5.schema.json`
- Additive advisor field: `research[].recommendation_v2`
- Shadow model: `decision-v2.0.0`
- Output schema: `5.0.0`

All matrix thresholds, confidence gates, group evidence requirements, trim multipliers, economic minimums, portfolio limits, stop profiles, thesis-break codes, and entry/cooldown defaults live in configuration.

## UI behavior

`RecommendationShadowPanel.jsx` shows:

- active legacy action;
- shadow company action and its reason;
- shadow position action and its namespaced reason;
- the four state layers;
- confidence/coverage and independent deterioration-group count.

The comparison is labelled **Shadow**. It does not recompute a missing backend reason or trim. When server-side user holdings are unavailable, position state says it was not assessed instead of inferring a result in React.

## Deterministic regression fixtures

`pipeline/tests/test_recommendation_policy_v2.py` covers all 15 requested cases plus confidence shrinkage and rejection of an unverified thesis-break headline. The hard-stop case asserts company action is not `sell_thesis` while position action is `exit`. The price/stop case asserts only `market_behavior` is a company factor.

## Backtest command and validation status

Run the same walk-forward entries through all eight policies:

```bash
PYTHONPATH=pipeline python3 pipeline/backtest_historical.py \
  --weeks 104 --top-n 20 --policy-suite \
  --spread-bps 5 --slippage-bps 5 --tax-bps 0 \
  --out pipeline/backtest_policy_results.json
```

`policy_backtest.py` reports CAGR, Sharpe, Sortino, maximum drawdown, turnover, and net return after configured spread/slippage/tax friction for A–H. Metrics requiring true tax lots or event-following counterfactual windows are present as `null`, not invented. The full sample must not be used for promotion: use a development window followed by an untouched period, or rolling walk-forward folds.

No claim of improvement is made. The current historical data lacks point-in-time estimate revisions/news and complete tax lots, so promotion remains blocked on prospective evidence.

## HIG before / shadow after

| Layer | Active / before | Shadow `decision-v2.0.0` |
|---|---|---|
| Composite | 82.0, `ATTRACTIVE`, confidence .85 | Not used as the company action |
| Active guidance | `HOLD`, high textual confidence | Preserved unchanged for comparison |
| Structural | Broad insurer-inappropriate inputs previously helped the score | Raw 93.9 → effective 69.0 at .43 confidence; insurer-inapplicable metrics suppressed |
| Timeliness | Trailing growth could influence the broad score | Effective 50.0, confidence 0.0; forward revisions/surprise absent |
| Company action | HOLD | `insufficient_evidence`; matrix is `hold_or_watch` but confidence gate wins |
| Position action | Could be overwritten in browser by a user stop | `no_action` in published shadow row because no server-side position was supplied |

## BSX before / shadow after

| Layer | Active / before | Shadow `decision-v2.0.0` |
|---|---|---|
| Composite | 69.8, `PROMISING`, confidence .83 | Not used as the company action |
| Active guidance | `WATCH`; one market-behavior flag from 61% max drawdown | Preserved unchanged for comparison |
| Structural | High available valuation/quality metrics | Raw 76.6 → effective 62.3 at .46 confidence |
| Timeliness | Trailing growth present; no point-in-time revision history | Effective 50.0, confidence 0.0 |
| Company action | WATCH | `insufficient_evidence`; missing forward revision/surprise data controls |
| Position action | Browser stop could still upgrade headline | `no_action` in published shadow row until holdings are supplied server-side |

## Rules still provisional

1. Structural/timeliness matrix cutoffs (75/55 and 70/55/50/75).
2. Confidence gates (.40/.60/.80) and the use of the weaker axis as action confidence.
3. Two-subfactor, two-period group confirmation and 0.45 severity threshold.
4. Every trim multiplier, min/max trim, $50 economic floor, and fractional-share precision.
5. Default and asset-profile stop distances, persistence, close-vs-intraday execution, and cooldowns.
6. ATR/volatility-adjusted stops until adjusted daily ATR is retained in the payload.
7. Split, dividend, lot, add-share reset, partial-fill, and gap-down execution behavior; input fields are defined but brokerage-grade state is not yet available.
8. Tax multiplier and transaction-cost estimates until account type and tax lots are server-side.
9. Sector/theme/ETF look-through/factor/beta/correlation/marginal-risk constraints; contract fields exist, current data coverage is incomplete.
10. Thesis-break event verification workflow and source allow-list.
11. Initial/add/average-down/re-entry classifications are implemented, but order routing and brokerage execution are not.
12. Insurer/bank/ETF critical metrics until providers deliver capital, underwriting, credit, holdings-liquidity, and tracking-quality fields.
13. Backtest recovery/whipsaw/trim-counterfactual metrics until event windows and tax lots are modeled.

## Promotion rule

Keep `shadow_mode: true` and retain old-versus-new presentation until an untouched or rolling walk-forward evaluation demonstrates acceptable net-of-cost results, data coverage is sufficient for the intended asset profiles, and a human policy review approves the provisional thresholds. Promotion must be an explicit version/config change; it must not happen as a frontend fallback.
