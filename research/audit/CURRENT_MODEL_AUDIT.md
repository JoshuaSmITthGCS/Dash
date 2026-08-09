# ValueSignal — Current Model Audit (Phase 0)

**No edits were made to produce this document.** Every numeric claim is computed from
`public/data/advisor.json` as committed (generated `2026-08-09T09:09:35Z`, model `3.2.0`,
universe 926, scored rows 877, published rows 40). Code reading establishes mechanism; the
artifact establishes fact.

Companion: `research/audit/PIPELINE-MAP.md`.

---

## 0. Headline

The system is a carefully engineered, well-documented, thoroughly tested implementation of a
methodology that does not survive contact with its own output. The engineering is genuinely
good — per-provider token buckets, an append-only point-in-time store, reconciliation
policies, an explainability reconciler that *raises* if attribution fails to add up. The
methodology underneath it is not.

Four things are true simultaneously and are the substance of this audit:

1. **A published peer-relative claim is decided by the alphabet.** THG and SIGI have the
   *identical* valuation score of 95.7. The 7.7-percentile gap between them — published as
   "cheaper than approximately 85%" vs 77% — comes entirely from `sorted(key=(value, ticker))`
   breaking the tie alphabetically.
2. **A layer with zero cross-sectional variance controls a branch of the shadow policy.**
   `timeliness.effective_score` is exactly 50.0 for **40 of 40** published names, with
   confidence 0.0 and coverage 0. Because 50 < the configured `timeliness_acceptable` of 55,
   no name can ever reach `buy_candidate`. All 40 resolve to `insufficient_evidence`.
3. **Coverage is called confidence, and it is applied to the score three times.** Once inside
   the fundamentals score, once in the composite blend, and once again in the frontend's Setup
   Quality geometric mean. The same quantity is also the hard gate on whether a user may size
   a position.
4. **For every one of 125 financial-sector rows, 71% of the valuation weight is deleted and
   the remainder renormalized to 100%, then published as a Value score with no marker.** The
   surviving 29% is 52% forward P/E, 31% PEG — a metric the project's own applicability matrix
   declares invalid for insurers — and 17% price-to-tangible-book.

**Harsh rating of the current methodology: 3/10.** The infrastructure is 7/10. The
methodology is 2/10. It has never been validated out-of-sample because no out-of-sample data
exists, and several of its published claims are demonstrably false about the world rather than
merely imprecise.

---

## 1. Corrections to the brief's premises

The brief asked to be told where its reconnaissance was wrong. Five corrections. Three make
the situation worse.

**C-1. The universe is 910 configured / 926 seen / 877 scored, not ~120.**
`pipeline/config/advisor_universe.json` holds 910 unique symbols. This changes the degrees-of-
freedom argument in the brief's favour on breadth but not on depth: 877 names × 33 metrics is
enough cross-section, and **8 days** of time series is not (see C-3). The constraint is time,
not width.

**C-2. There is no layer named `EARNINGS_TIMELINESS`.** The defect is real and is exactly as
described, but it lives in `pipeline/scoring_v2.py :: build_v2_analysis` as the `timeliness`
block, surfaced by `src/components/AnalysisLayers.jsx:42` under the title "Earnings
timeliness". Anyone grepping the literal string finds nothing and concludes the defect was
fixed. It was not.

**C-3. The point-in-time problem is far worse than "restated, not point-in-time".**
`pipeline/data/pit/observations.jsonl` contains **8,305 rows across 8 calendar days**
(2026-08-02 → 2026-08-09), 877 tickers. Not 8 months. Eight days.

```
2026-08-02  1152      2026-08-06  1138
2026-08-03   573      2026-08-07  2408
2026-08-04   320      2026-08-08  1181
2026-08-05   214      2026-08-09  1319
```

`pipeline/data/backtest_cache/` holds 860 tickers × ~10 years, but it is Yahoo restated
statements plus today's survivor universe — the contaminated source, not a substitute.
`pipeline/backtest_historical.py` applies a *fixed* `report_lag_days` to period-end dates
(`quarter_known_dates`, line 134) rather than actual filing dates, and has an
`allow_current_shares` path that injects present-day shares outstanding into historical
snapshots. That is direct look-ahead on top of restatement contamination.

**Consequence:** Phases 4–10 are not merely at risk of overstating performance. They cannot
run at all. This should be stated plainly to the user before any work is planned around them.

**C-4. DSO *trend* is suppressed for insurers in the v2 applicability matrix — and the v2
matrix does not govern the published score.** `applicability_matrix.json:27` correctly
suppresses `days_sales_outstanding_trend` for `property_casualty_insurer`. That rule is read
only by `scoring_v2.build_v2_analysis`, which is shadow. The live path
(`scorer._band_valuation_score:568`) scores it for every sector unconditionally. THG's
published row carries `days_sales_outstanding: 215.2` and a scored
`days_sales_outstanding_trend: 80.0`. So the registry is right, and it is wired to nothing that
users see. This is worse than the registry being wrong: the correct rule exists and is inert.

**C-5. The "conflated confidence" defect is not confined to the score.** The same
completeness-derived scalar is the *hard gate* on position sizing:
`src/lib/watchlistGuidance.js:85` blocks all sizing when `confidence < hard_confidence_floor`
(0.45), and `src/lib/confidenceGate.js` bands it into "High confidence" at ≥ 0.75. A user is
being told data completeness is a reason to trust a recommendation, and is being blocked from
acting when a data feed is merely incomplete.

Everything else in the brief's reconnaissance is confirmed.

---

## 2. Defect 1 — the false peer-relative claim

### What is published

```json
"valuation_percentile": {
  "value": 84.6, "display_value": 84.6,
  "peer_group_id": "property_casualty_insurer",
  "peer_group_label": "Property & casualty insurers",
  "peer_count_total": 14, "peer_count_with_valid_data": 14,
  "metric_id": "structural_valuation_score",
  "underlying_value": 95.7,
  "direction": "higher_is_cheaper",
  "winsorization_method": "none",
  "percentile_method": "inclusive_rank",
  "minimum_peer_count": 4,
  "confidence": 0.7
}
```

Rendered by `src/components/StockDetailModal.jsx:243` as
*"Cheaper than approximately 85% of Property & casualty insurers, based on 14 valid peers."*

### Origin

- `pipeline/peer_groups.py :: canonical_percentiles` (line 30) — computes the percentile.
- `pipeline/peer_groups.py :: peer_group` (line 10) — assigns the group.
- `pipeline/peer_groups.py :: MIN_VALID_PEERS = 4` (line 7) — the entire gate.
- `pipeline/fetch_advisor.py:1397` — call site.
- `src/components/StockDetailModal.jsx:243` — the sentence.

### Why it is backwards — proven from the artifact

The percentile is not a percentile of any valuation multiple. It is a percentile of
`fundamental_categories.valuation`, the model's own 0–100 composite band score, relabelled
`higher_is_cheaper`.

Published P&C insurers, sorted by that composite:

| Ticker | Valuation score | Published percentile | P/B | P/TBV | Fwd P/E | PEG |
|---|---|---|---|---|---|---|
| CNA | 100.0 | 92.3 | 1.26 | 1.23 | 10.84 | 0.92 |
| **THG** | **95.7** | **84.6** | **2.18** | **2.48** | 11.76 | 0.34 |
| SIGI | 95.7 | 76.9 | 1.66 | 1.60 | 10.97 | 0.28 |
| MCY | 90.6 | 69.2 | 2.34 | — | 9.12 | 1.11 |
| ORI | 77.6 | 61.5 | 1.70 | 1.76 | 13.04 | 1.39 |
| ALL | 67.8 | 46.2 | 2.14 | 2.51 | 9.86 | 3.20 |

Three independent failures visible in six rows:

1. **THG and SIGI have the identical score of 95.7.** The 7.7-point percentile gap between
   them is produced by `sorted(group["valid"], key=lambda item: (item[1], item[0]))`
   (`peer_groups.py:41`) — a tie broken **alphabetically**, then published to three
   significant figures. SIGI trades at 1.60× tangible book; THG at 2.48×. THG is 55% more
   expensive and is ranked as cheaper, for no reason other than that T follows S.
2. **P/TBV cannot separate them.** `settings.fundamentals.price_to_tangible_book` has
   `good_max: 3.0`, so `band_score` returns 75 for everything between 1.5 and 3.0. 1.60 and
   2.48 are the same number to this model.
3. **With n = 14 the percentile is quantized to multiples of 100/13 = 7.69.** "84.6%" is one
   of only 14 attainable values. `display_value` is additionally capped at 99.0
   (`peer_groups.py:55`) — an undocumented ceiling that silently rewrites the cheapest name in
   every group.

### Contributing cause — the metric mix for an insurer

`scorer.raw_fundamental_metrics` / `_band_valuation_score` null five of eight valuation
metrics when `sector in ("Financial Services", "Financials")`. Configured valuation weights:

| Metric | Weight | Insurer |
|---|---|---|
| ev_to_ebitda | 0.27 | **nulled** |
| ev_to_fcf | 0.18 | **nulled** |
| forward_pe | 0.15 | kept |
| ev_to_ebit | 0.12 | **nulled** |
| peg | 0.09 | kept |
| sales_multiple | 0.09 | **nulled** |
| price_to_book | 0.05 | **nulled** |
| price_to_tangible_book | 0.05 | kept |

**71% of the valuation weight is deleted.** `weighted_available` renormalizes the surviving
0.29 to 1.00, so an insurer's Value score is:

- **52% forward P/E**
- **31% PEG** — which `applicability_matrix.json:17` itself declares
  `["suppressed", "forward_pe", "Universal PEG does not normalize underwriting cycles or
  reserve development."]`
- **17% price-to-tangible-book** — the one canonical insurer valuation input

THG's PEG of 0.34 is Yahoo's `trailingPegRatio`, carrying the quality flag
`unknown_growth_definition_and_horizon` (`canonical_metrics.yahoo_observations:199`) and
explicitly rejected as non-canonical by `calculate_peg`. The live scorer uses it anyway, and
it is nearly twice the weight of tangible book.

The published Value score of 95.7 and the composite 86.2 both rest on this.

---

## 3. Defect 2 — the fictional scoring layer

### Origin

`pipeline/scoring_v2.py:153-162`:

```python
revision       = snapshot.get("forward_eps_revision_30d")     # never populated
revision_score = None if revision is None else ...
surprise       = snapshot.get("earnings_surprise")            # opt-in, default OFF
surprise_score = None if surprise is None else ...
timing_raw              = _weighted([(revision_score, 0.7), (surprise_score, 0.3)])   # → None
timing_coverage         = 0.0
timing_confidence       = 0.0
timing_raw_for_effective = 50 if timing_raw is None else timing_raw     # ← the fiction
timing_effective        = 50 + 0.0 * (50 - 50)                          # ← exactly 50.0
```

### Measured

Across all 40 published rows, `(effective_score, confidence, coverage)` = **(50.0, 0.0, 0)**
for 40/40. Zero cross-sectional variance. `earnings_surprise` is `None` for THG, CRUS and NEM
alike — `ENABLE_EARNINGS_SURPRISE` is off by default (`fetch_advisor.py:433`), documented as
having resolved 0 of 40 companies on its first run. `forward_eps_revision_30d` is never
written by any module.

### It is not inert — it is load-bearing

`recommendation_policy_v2.two_axis_classification` (line 60) against
`recommendation_policy_v2.json`:

```
structural_strong 75 | timeliness_buy 70 | timeliness_acceptable 55 | timeliness_weak 50
```

With `timeliness_score` permanently 50.0:

- structural ≥ 75 → `50 < 55` → **`quality_watch`**. `buy_candidate` is unreachable.
- structural ≥ 55 → `50 < 50` is false → `hold_or_watch` at the boundary.

Measured outcome: `company_action` is `insufficient_evidence` for **40 of 40**, and
`portfolio_fit` is `below_target` for **40 of 40**. The entire shadow policy — every stop
profile, the severity × confidence × concentration × liquidity trim ladder, the entry and
re-entry rules — produces one constant for every company in the universe.

The UI displays it as evidence: `AnalysisLayers.jsx:42` renders "Earnings timeliness" with
"Evidence confidence 0%" beside an effective score of 50.

`PORTFOLIO FIT: below_target` has the identical pathology, from
`recommendation_policy_v2.classify_portfolio_fit:244`: with no portfolio supplied,
`current_weight` defaults to 0.0 and `target_weight` to 0.03, so `0 < 0.03 * 0.75` is always
true. A constant dressed as an assessment.

---

## 4. Defect 3 — coverage is called confidence, and counted three times

### The quantity

`advisor_engine.blend_research_components:771`:

```python
confidence = 0.65 * coverage["fundamentals"] + 0.25 * coverage["market_behavior"] + 0.10 * coverage["news_sentiment"]
```

`coverage` is `scorer.weighted_coverage` — answered metric weight ÷ total metric weight. It
contains no statistical property of the signal: no dispersion, no historical error, no
out-of-sample hit rate. `confidence.py` is explicit and honest about this in its docstrings,
and then publishes the number under the name anyway.

### Triple counting

| # | Where | Formula |
|---|---|---|
| 1 | `scorer._band_valuation_score:583` | `total = raw × (0.65 + 0.35 × coverage)` |
| 2 | `advisor_engine.blend_research_components:778` | `base = raw × (0.8 + 0.2 × confidence)` |
| 3 | `src/lib/watchlistGuidance.js:80` | `confidence` is 20% of the Setup Quality geometric mean |

Plus `src/lib/researchRating.js:48` (`rating *= confidence`) and
`src/lib/confidenceGate.js` (bands it as "High confidence" ≥ 0.75). A single completeness
statistic shrinks the score, shrinks the composite, shrinks the setup score, shrinks the
rating, and gates whether the user may size a position at all.

### Measured contradictions

| Row | legacy `confidence` | v2 `structural.confidence` | v2 `timeliness.confidence` |
|---|---|---|---|
| THG | **0.88** | 0.42 | 0.00 |
| CRUS | **0.89** | 0.66 | 0.00 |
| NEM | **0.89** | 0.69 | 0.00 |

THG publishes 88% confidence and 42% confidence for the same company in the same payload, and
0% on a third layer. `confidence.model_agreement_component` exists to detect exactly this and
measures agreement between *score variants*, not between confidence definitions, so it never
fires.

### Coverage is a fiction for financials specifically

THG's published `fundamental_detail.coverage` is **0.97**. Thirteen of its 33 metrics are
`None`. Coverage reads 97% because `FINANCIAL_EXEMPT` (`scorer.py:167`) removes ten of them
from the *denominator*. The model does not know it is missing P/B and debt-to-equity; it has
been told those metrics do not exist for this company. It then publishes a Value score of 95.7
and a confidence of 0.88.

**Every one of 125 financial-sector rows publishes a Value score with P/B suppressed. 125 of
125.** This is structural, not an edge case.

### 837 of 877 rows have no confidence at all

`_screen_row` (`fetch_advisor.py:203`) does not project `confidence`, `fundamental_detail` or
`valuation_percentile`. Only the published top 40 carry them. The other 837 rows are ranked,
screened and surfaced by every client-side strategy lens with the confidence field absent —
and `src/lib/researchRating.js` handles that by applying a `LIGHT_DATA_SHRINK` constant.
Another neutral default.

---

## 5. Defect 4 — inconsistent industry conditioning

Three separate, mutually inconsistent conditioning systems:

| System | Location | Governs | Reaches the user? |
|---|---|---|---|
| `is_financial` / `TANGIBLE_BOOK_SECTORS` hard-nulling | `scorer.py:167-176`, `230-273`, `504-588` | the published score | **yes** |
| `applicability_matrix.json` + `METRIC_REGISTRY.applicability_profiles` | `canonical_metrics.applicability_for` | `analysis_v2` only | **no** |
| `business_profiles.json` replacement/critical metrics | `scoring_v2` applicability block | display only | no |

### 5a. Insurers — DSO scored, P/B and D/E deleted

THG published row: `days_sales_outstanding: 215.2`, `days_sales_outstanding_trend: -0.0341`
scored **80.0**. `applicability_matrix.json:27` suppresses this metric for P&C insurers. The
suppression never runs on the live path. `advisor_engine.build_evidence:990` will print
"Receivable days up X%" as a risk for an insurer whenever the trend is positive.

Simultaneously `price_to_book` (2.18 in the row) and `debt_to_equity` (0.23 in the row) are
present in the data and forced to `None` by `raw_fundamental_metrics`. The two canonical
insurer inputs are discarded while a meaningless one is scored.

### 5b. Fabless semiconductors — capex starvation

CRUS: `capex_to_depreciation: 0.28` → `range_score` → **25.0** (the floor tier).
`settings.fundamentals.capex_to_depreciation` has a single universal ideal band. Cirrus Logic
outsources fabrication to TSMC; a low capex/depreciation ratio is the *definition* of the
business model, not underinvestment. There is no `fabless` profile in
`classify_profile` — CRUS resolves to `"general"`. The penalty is applied to every fabless
designer in the universe.

### 5c. Commodity producers — cycle read as quality

NEM: `operating_margin_trend: 0.1699` → **100.0**; `incremental_margin: 1.2824` (128.2%);
`fcf_growth_3y` → 100.0; `capital_allocation` category → 100.0. Newmont's margin expansion is
the gold price. `classify_profile` *does* assign `commodity_producer`, and
`applicability_matrix.json:40` contains exactly one rule for it (`peg → midcycle_ev_ebitda`)
which, again, only the shadow path reads. Nothing marks trailing margin trend, incremental
margin or FCF growth as cycle-contaminated on the live path.

An incremental margin of 128.2% is arithmetically impossible as a steady state and is not
flagged anywhere. THG's 89.9% likewise.

---

## 6. Duplicated information — measured, not asserted

Spearman rank correlation across the published universe. This measures redundancy among
*inputs*; it makes no claim about returns and needs no point-in-time data.

### Market behaviour is one signal wearing seven hats

| Pair | ρ | n |
|---|---|---|
| `momentum_12_1` × `risk_adjusted` | **+0.93** | 876 |
| `return_20d` × `relative_strength_20d` | **+1.00** | 877 |
| `drawdown_60d` × `relative_strength_20d` | +0.71 | 877 |
| `return_20d` × `drawdown_60d` | +0.71 | 877 |
| `return_60d` × `volume_ratio_60d` | +0.69 | 876 |
| `pct_above_52w_low` × `risk_adjusted` | +0.66 | 876 |
| `return_60d` × `drawdown_60d` | +0.66 | 876 |
| `momentum_12_1` × `pct_above_52w_low` | +0.56 | 876 |

Two findings are structural rather than empirical:

- **ρ = 1.00 for `return_20d` × `relative_strength_20d` is a tautology.**
  `technical_factors:139` computes `relative = ret_20 - bench_ret`, where `bench_ret` is the
  *same scalar for every row*. Subtracting a constant cannot change a cross-sectional ranking.
  "Relative strength" carries 0.16 of the market-behaviour weight and is rank-identical to a
  metric already in the blend.
- **ρ = 0.93 for `momentum_12_1` × `risk_adjusted`** — together 0.56 of market-behaviour
  weight. `risk_adjusted` is a Sortino/Sharpe blend over the trailing 252 days; over a single
  year, cross-sectional Sharpe is dominated by the return numerator.

Net: of market behaviour's 1.00 weight, ~0.72 (momentum 0.30 + risk_adjusted 0.26 +
relative_strength 0.16) is one underlying factor. Momentum is materially overweighted relative
to its nominal 30%. **The brief's hypothesis of hidden momentum overweighting is confirmed.**

### Quality is redundant but cannot be measured at universe scale

| Pair | ρ | n |
|---|---|---|
| `return_on_invested_capital` × `return_on_equity` | +0.75 | **39** |
| `return_on_invested_capital` × `profit_margin` | +0.46 | 40 |
| `return_on_equity` × `profit_margin` | +0.43 | 39 |

n = 39–40 because these fields exist only for statement-enriched names. `gross_profits_to_assets`
and `piotroski_f` did not clear n ≥ 30 against the others at all. **The brief's hypothesis of
hidden quality overweighting is directionally confirmed on ROIC/ROE/margin (ρ up to 0.75) but
cannot be settled for the F-score and gross-profits-to-assets without a full-universe
enrichment run.** That run exists as `FULL_UNIVERSE_RESEARCH=1` and should be the first thing
executed in Phase 5.

### The categories are not the problem

| Pair | ρ | n |
|---|---|---|
| valuation × profitability | −0.01 | 874 |
| valuation × financial_health | −0.01 | 773 |
| profitability × growth | +0.01 | 872 |
| profitability × accounting_quality | +0.39 | 147 |
| valuation × capital_allocation | +0.36 | 148 |

At category level the six buckets are close to orthogonal. **The redundancy is inside
buckets, not between them.** Any fix should collapse metrics within families rather than
reweight the families.

### The categories are also not the same categories row-to-row

| Category | Rows with a value | Share |
|---|---|---|
| valuation | 874 / 877 | 100% |
| profitability | 874 / 877 | 100% |
| growth | 872 / 877 | 99% |
| financial_health | 773 / 877 | 88% |
| **capital_allocation** | **148 / 877** | **17%** |
| **accounting_quality** | **147 / 877** | **17%** |

For 83% of the universe, `capital_allocation` (0.10) and `accounting_quality` (0.10) are
absent and their combined 20% of category weight is silently renormalized into the other four.
**A screen row's composite score and a published row's composite score are not the same
statistic, and they are sorted into one leaderboard.**

---

## 7. Silent defaults — exhaustive

The most important section. Every place a missing value becomes a number.

### 7a. Class 1 — missing data reads as "no concern" (guidance)

`advisor_engine.action_for`, the entire live deterioration rule:

| Line | Code | Effect when the field is missing |
|---|---|---|
| 696 | `(extended.get("interest_coverage") or 99) < 2` | absent coverage → **99×** → never flags |
| 698 | `(extended.get("accruals_ratio") or 0) > 0.10` | absent → 0 → never flags |
| 704 | `(technical_parts.get("max_drawdown_252d") or 0) < -30` | absent → 0 → never flags |
| 706 | `(technical_parts.get("relative_strength_20d") or 0) < -10` | absent → 0 → never flags |
| 708 | `(technical_parts.get("return_60d") or 0) < -15` | absent → 0 → never flags |
| 717 | `(extended.get("short_percent_of_float") or 0) >= 0.15` | absent → 0 → never flags |

Also `or 0` is falsy-triggered, not None-triggered: a genuine `0.0` reading is treated
identically to a missing one. Every deterioration test in the production guidance engine fails
*open*. A company with no data cannot be told to TRIM or SELL. **This is the single most
dangerous default in the codebase**, because it governs sell discipline rather than ranking.

Same pattern in `build_evidence:994-1001`, so a data-starved company also cannot display a
risk.

### 7b. Class 2 — neutral imputation into a score

| Location | Default | Consequence |
|---|---|---|
| `scoring_v2.py:150` | `raw = 50.0 if raw is None else raw` | structural falls back to neutral |
| `scoring_v2.py:161` | `timing_raw_for_effective = 50 if timing_raw is None` | **Defect 2** |
| `recommendation_policy_v2.py:42` | `raw = _number(raw_score, 50.0)` | shadow effective score |
| `recommendation_policy_v2.py:48` | `confidence = _clamp(_number(..., 0.0))` | missing confidence → 0 → shrink to exactly 50 |
| `advisor_engine.py:800` | `raw = ... if available else config["shrinkage_target"]` | no components → configured neutral |
| `src/lib/watchlistGuidance.js:20` | `return config.neutral_subscore` (0.5) | missing thesis/research/confidence → 0.5 |
| `src/lib/watchlistGuidance.js:81` | `config.guidance_scores[action] ?? neutral_subscore` | unknown action → 0.5 |
| `src/lib/researchRating.js:48` | `LIGHT_DATA_SHRINK` | screen rows with no confidence field |
| `scoring_v2.py:146` | `provenance_reliability = 0.72 if observations else 0.55` | two magic constants, no derivation |

### 7c. Class 3 — silent weight renormalization

`scorer.weighted_available:158` and `advisor_engine.blend_research_components:767` drop
missing inputs and rescale. This is the *correct* behaviour in principle and the brief asks for
it to be generalized in Phase 1.2 — but today it is **unrecorded**. Nothing in the payload says
"this valuation score was computed from 29% of its intended weight". The consumer cannot tell a
fully-evidenced 95.7 from a 3-metric 95.7.

### 7d. Class 4 — coverage-denominator manipulation

`FINANCIAL_EXEMPT` and the `TANGIBLE_BOOK_SECTORS` exemption remove metrics from
`weighted_coverage`'s denominator, so deleting evidence *raises* measured coverage. THG: 13
missing metrics, 0.97 coverage.

### 7e. Class 5 — dataclass and config defaults

`canonical_metrics.Observation` defaults `period_start`, `period_end`, `available_at`,
`observed_at`, `fiscal_period` to `None` and `is_ttm`/`is_forward` to `False`. An observation
constructed without a period is *silently* a non-TTM, non-forward, undated observation. Both
call sites (`overview_snapshot`, `yahoo_observations`) construct exactly that and compensate
with a `provider_period_not_supplied` quality flag — which nothing in the scoring path reads.

`recommendation_policy_v2.classify_portfolio_fit:246-248`: `current_weight → 0.0`,
`target_weight → 0.03`, `maximum_weight → 0.05` — the source of the constant `below_target`.

### 7f. Class 6 — 175 non-trivial `.get(key, default)` sites

Full mechanical scan of `pipeline/**.py` excluding tests, excluding trivial
`None/{}/[]/0/False` defaults:

| Module | Count |
|---|---|
| `advisor_engine.py` | 23 |
| `recommendation_policy_v2.py` | 18 |
| `scorer.py` | 13 |
| `validate_data.py` | 12 |
| `fetch_advisor.py` | 10 |
| `research_screens_v2.py` | 10 |
| `themes.py`, `shadow_portfolios.py`, `fetch_etfs.py` | 7 each |
| remainder (17 modules) | 68 |

Most are config-shape defaults (`cfg.get("max_penalty", 6.0)`) and are benign in kind but
harmful in effect: **the operative numeric constants of the model exist in two places at
once** — `settings.json` and the code's fallback — so a config key typo silently reverts a
weight to a hardcoded value with no error. Phase 1 should make config access fail-loud.

---

## 8. Displayed precision versus demonstrated calibration

`pipeline/score_calibration.py` exists and `confidence.historical_calibration_component`
gates on it. Measured: `historical_calibration` is `None` for every row, and the published
`limitations` array says so —
*"insufficient prospective calibration history (requires 24 eligible IC periods)"*.

**The model itself reports that it has never been calibrated.** With 8 days of point-in-time
history it cannot have been. Against that, here is what is displayed:

| Displayed | Precision | Justified? |
|---|---|---|
| Research Score `86.2` | 0.1 on 0–100 | **No.** Published top-10 span 86.2 → 81.0. The top three are 86.2 / 85.5 / 85.3 — a 0.9-point spread. Nothing demonstrates the model can order them. |
| Setup Quality `99.3` | 0.1, geometric mean of four logistics | **No.** Three of four inputs are themselves uncalibrated; one is data coverage. |
| Evidence confidence `89%` | 1% | **No.** It is a weight ratio, and it disagrees with the same payload's other two confidence numbers by up to 46 points. |
| Peer percentile `84.6%` | 0.1% | **No.** n = 14 quantizes to 7.69; ties break alphabetically; `display_value` capped at 99.0. |
| Valuation category `95.7` | 0.1 | **No.** Built from 3 metrics scoring on 4-tier discrete bands (100/75/50/25). The *input* resolution is one tier; the output claims 1000 levels. |
| `thesis = 100` | integer max | **No.** |
| Modifier points `+2.08` | 0.01 | **No.** Derived from the peer percentile above. |

The band scorers emit values from a set of about twelve discrete levels. A weighted average of
twelve-level inputs cannot support one-decimal output on a 0–100 scale. **The displayed
precision exceeds the input resolution before any question of predictive calibration arises.**

`stance_for` cliffs at 75 / 60 / 45 and `label_for` at configured cutoffs turn a 0.1-point
difference into a categorical change with no hysteresis.

---

## 9. Duplicated and dead machinery

Worth naming because it inflates apparent sophistication:

- **Four independent guidance implementations**: `advisor_engine.action_for` (live),
  `recommendation_policy_v2` (shadow, inert), `src/lib/sellWatchLogic.js` +
  `src/lib/positionRisk.js` (client-side), `src/lib/dipWatch.js`. They do not agree and
  nothing reconciles them.
- **Three peer definitions**: sector nulling, `CrossSectionalNormalizer` sector-vs-universe,
  `peer_groups` business profiles.
- **Three confidence definitions**: legacy scalar, `structural.confidence`,
  `timeliness.confidence` — all three published on the same row.
- **A full provenance system (`Observation`, `reconcile`, `provider_reconciliation.json`) that
  the production score does not consult.**
- **A correct applicability matrix wired only to a shadow path.**
- `own_history_percentile` reports `status: "accumulating"` universe-wide — 8 days of history
  against a `own_history_minimum_observations` gate.

The pattern is consistent: the *right* mechanism was built, then attached to the shadow model
and never promoted, while the legacy path kept publishing. Phase 1–3 should be understood
mostly as **promotion and deletion**, not new invention.

---

## 10. Entity keying — Phase 2.1 confirmed and scoped

CIK appears only inside `sec_edgar.py`, resolved from SEC's `company_tickers.json` via
`ticker_map()` (line 198) and used solely to fetch filings. Every other store — `pit_store`
(`ticker` key), `backtest_cache/*.json` (filename = ticker), `peer_groups`,
`business_profiles.ticker_overrides`, `advisor_universe.json`, every published row — is keyed
by ticker.

`sec_edgar.filings_for_ticker:263` returns `None` on an unmapped ticker rather than raising, so
an ambiguous or reassigned symbol degrades silently.

The universe file has no duplicate symbols (910 unique of 910). Cross-listing collisions of the
THG type cannot be detected without an exchange field, which the universe file does not carry —
that is itself a Phase 2.1 finding: **there is no exchange qualifier anywhere in the
configuration**, so `(ticker → CIK)` is the only mapping available and it is inherently
ambiguous.

---

## 11. What I recommend, and what I recommend against

### Recommend

1. **Reorder the engagement. Phase 2 first, Phase 1 second.** Phase 1's gate asks for score
   diffs on THG/CRUS/NEM, which needs no PIT data, so Phase 1 can proceed — but Phase 2 is on
   the critical path for everything else and takes calendar time to accumulate. Start the EDGAR
   XBRL backfill immediately and in parallel.
2. **Phase 1.2's "raise if a layer is constant across the universe" guard should be applied
   retroactively as a test right now**, before any fix. It would have caught `timeliness`
   (40/40 identical), `portfolio_fit` (40/40 identical) and `company_action` (40/40 identical)
   on the first production run.
3. **Add a second guard: raise if any published score's input resolution is coarser than its
   displayed precision.** This is mechanical and catches the whole of §8.
4. **Fix `action_for`'s fail-open defaults in Phase 1**, not Phase 9. It is a sell-discipline
   bug, it is a two-line-per-branch change, and it does not depend on any research result.
5. **Run `FULL_UNIVERSE_RESEARCH=1` once before Phase 5** so quality-metric redundancy can be
   measured on 877 rows instead of 40.
6. **Delete `relative_strength_20d` from the market-behaviour blend in Phase 1.** It is
   rank-identical to `return_20d` by construction. This is not a research finding requiring
   validation; it is arithmetic.

### Recommend against

1. **Do not build a replacement confidence metric in Phase 1.** The brief already says this;
   the audit reinforces it. With no calibration history, any new confidence number would be
   another `provenance_reliability = 0.72`.
2. **Do not run Phases 4–10 on `backtest_cache/`.** It is restated Yahoo statements over
   today's survivors with a fixed lag approximation and a current-shares-outstanding path. Any
   number it produces is inadmissible, and producing it would create pressure to use it.
3. **Do not attempt the estimate-revision layer on free data.** `capability_status` already
   records `analyst_revision_trends: provider_required` and
   `guidance_beat_miss_history: provider_required`. The honest Phase 10 answer is likely
   "unbuildable on free data; remove it or buy data" — the brief anticipated this and the
   evidence supports it.
4. **Do not reweight the six categories.** They are near-orthogonal (§6). The redundancy is
   within buckets. Reweighting would be motion without effect.
5. **Do not promote `recommendation_policy_v2` as-is.** It is more sophisticated than the live
   path and currently produces one constant for every company. Promoting it would replace a
   crude working rule with an elaborate broken one.

---

## 12. What this brief did not anticipate

1. **The alphabetical tie-break.** The single most embarrassing finding, and it is not in the
   brief's list. Peer percentiles are ordered by `(value, ticker)`.
2. **`relative_strength_20d` is rank-identical to `return_20d`.** ρ = 1.00 by construction, and
   it draws 16% of the market-behaviour weight.
3. **The 17% coverage cliff.** Two of six fundamental categories exist for only 17% of the
   universe, and rows with structurally different composites share one leaderboard.
4. **The enrichment feedback loop.** Statement-derived metrics are fetched only for the
   *previous* run's top 20 plus 5 challengers. The model can only ever discover names a weaker
   version of itself already liked. This is a self-reinforcing ranking bias that no amount of
   scoring-methodology work will fix, and it silently invalidates any claim that the leaderboard
   reflects the universe.
5. **The deterioration engine fails open on missing data** (§7a).
6. **Eight days of point-in-time history**, not months.
7. **The shadow model is 100% degenerate** — `insufficient_evidence` for 40/40 — so the
   "shadow vs legacy" comparison the platform advertises has never actually compared anything.
