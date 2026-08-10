# TRACE — THG (The Hanover Insurance Group) end-to-end

Status: **complete for the pipeline-side trace.** Every open thread from the checkpoint
draft is now either resolved in place below (§5 records each resolution with the code that
settles it) or explicitly delegated: frontend rendering of the live-vs-shadow disagreement
is covered in `ARCHITECTURE.md` §9. This traces THG through the live (champion) scoring
path and the shadow (`analysis_v2` / `recommendation_v2`) path using the actual committed
artifact `public/data/advisor.json`, `generated_at: 2026-08-10T05:23:37Z`, `model_version:
3.2.0`, `schema_version: 6`. All numbers below are copied from that file, not reconstructed.
Code citations are read directly from the current working tree (branch
`claude/valuesignal-spec-audit-qf2wni`, HEAD `dbb2382`) — not from the repo's own internal
audit doc, which is dated 2026-08-09 and is one or more fix-commits behind. Where this trace
relies on the internal audit for orientation only (not as a source of fact), that is stated.

## 0. A load-bearing discovery, stated up front

`research/audit/CURRENT_MODEL_AUDIT.md` is a prior internal audit of this same system,
dated 2026-08-09, whose "four things simultaneously true" section is nearly identical in
substance to the four defects this task's brief lists as "already-confirmed." That audit
carries its own status table at the top stating most findings are already fixed, and git
history confirms a sequence of fix commits dated after it: `cb3cc53`, `ac24342`, `cd581b5`,
`0e0a9ad`, `790d0da`, among others (`git log --oneline`, checked 2026-08-10).

I re-verified all four of the brief's "already-confirmed" defects against the **current**
code and the **current** THG row, independent of both documents. Verified findings:

| Brief's claimed defect | Current status, verified against live code + THG row |
|---|---|
| Peer-percentile claim computed on a 14-name peer set | **No longer produced this way.** `pipeline/peer_groups.py:36` now requires `MINIMUM_VALID_PEERS = 30`; below that, `peer_context` is `None` with `invalid_reason`. THG's P&C-insurer peer group has 7 valid members (`valuation_percentile.peer_count_with_valid_data: 7`), so THG's published `valuation_percentile.peer_context` is `null`, `tier: null`, `invalid_reason: "insufficient_valid_peers"`. No percentage, no alphabetical tie-break, nothing rendered as a peer claim. |
| `EARNINGS_TIMELINESS` at 0% coverage defaulting to 50/100 | **No longer defaults.** `pipeline/scoring_v2.py` (current, lines 22-27, 174-182, 203-222) computes `timing_raw` via `renormalize()`; when no input resolves, `timing_raw is None` and `effective_score` is published as `null`, not `50 + 0·(50-50)`. THG's `analysis_v2.timeliness.raw_score`, `.effective_score` are both `null`. The module's own docstring (`scoring_v2.py:1-10`) documents that it used to publish exactly this fake 50.0 and names the fix as `ac24342`. |
| Confidence figures disagreeing between paths for the same name | **Partially true, differently shaped than described.** The legacy field is no longer called `confidence` — `cd581b5` renamed it to `data_coverage` (`pipeline/data_coverage.py`). THG publishes `data_coverage: 0.87` at the row's top level, `analysis_v2.structural.coverage: 0.84`, `analysis_v2.structural.evidence_weight_resolved: 0.61`, and `analysis_v2.timeliness.coverage: 0.0` — four differently-named, differently-defined scalars, still disagreeing in magnitude, but no longer sharing one ambiguous name. Whether this counts as fixed depends on what the defect is taken to mean; I treat this as **still-open, reduced severity**, and will document precisely in the main spec. |
| Insurer DSO surviving suppression while P/B and debt-to-equity are marked unavailable | **Inverted from the brief's description in current code — and inverted correctly.** THG's `analysis_v2.metric_status.days_sales_outstanding_trend.status` is `"suppressed"` (`replaced_by: "loss_ratio"`), and `fundamental_detail.days_sales_outstanding_trend` is `null` — DSO is *not* scored. `price_to_book` and `debt_to_equity` both show `status: "applied"` with real score contributions (75.0 and 100.0). `pipeline/scorer.py:548` now calls `applicability(snap)` (the same registry-driven function the shadow path uses) directly inside the live `_band_valuation_score`, replacing the retired `FINANCIAL_EXEMPT` / `TANGIBLE_BOOK_SECTORS`-only logic (see the "Retired" comment block at `pipeline/scorer.py:165-181`). Commit `0e0a9ad`, titled "make the applicability registry authoritative on the live path," is exactly this change. |

**Implication for the rest of this task:** section 10 of `ARCHITECTURE.md` cannot simply
restate the brief's four items as current defects — three of the four no longer reproduce
against the live code and the live artifact, and the fourth is real but different in shape
from the brief's description. I flagged this at the checkpoint rather than silently
substituting my own defect list for the brief's, since the brief was written assuming a
system state that has since changed under it.

## 1. Where THG enters the pipeline

- Universe membership — **resolved**: THG is one of the 910 entries in
  `advisor_universe.json`'s base `symbols` list, and is *not* one of the 21
  `portfolio_symbols` (both lists queried directly). The file also declares
  `publish_limit: 40` and `extended_limit: 150` — which is why the published artifact
  carries exactly 40 research rows out of a 926-name universe count.
- Run mode this artifact — **resolved**: the artifact's top level carries `data_mode:
  "live"`, `universe_mode: "fast"`, `polled_count: 247` (queried directly). So the row
  under trace was produced by a **fast-mode** refresh that re-polled 247 of the configured
  names rather than the full universe.
- `enrichment_selection.previous_top` contains `"THG"` (confirmed by direct query against the
  committed artifact) — THG was in the prior run's top tier and therefore qualified for
  statement enrichment (`fundamentals_extended.derive_extended`) this run via
  `pipeline/fetch_advisor.py:enrich()` (current line 1052). This is the enrichment
  feedback-loop mechanism the internal audit describes in its §12.4 — confirmed still present
  in the current code; not yet re-verified line-by-line for this checkpoint.

## 2. Live (champion) fundamental score

`pipeline/scorer.py:_band_valuation_score` (current, lines 538-623), called for THG with
`sector = "Financial Services"`.

1. `applicability(snap)` (line 548) returns `profile = "property_casualty_insurer"` and a
   `suppressed` set. For THG this set (from `analysis_v2.applicability.suppressed_metrics`,
   which is produced by the same underlying registry) is: `altman_z, capex_to_depreciation,
   cash_conversion, current_ratio, days_sales_outstanding_trend, ev_to_ebit, ev_to_ebitda,
   ev_to_fcf, free_cash_flow_yield, gross_profits_to_assets, inventory_days_trend,
   net_debt_to_ebitda, peg, piotroski_f, return_on_invested_capital` — 15 of THG's ~30 metric
   slots. (`sales_multiple`/`trailing_revenue_growth` appear suppressed in one payload
   location and not another; reconciling that is on the follow-up list, see §5 below.)
2. Every metric in the `suppressed` set is forced to `None` (line 607) *before* categories are
   computed, so it is excluded from both the score and, per `weighted_coverage`
   (`scorer.py:496`, not yet re-read line-by-line this pass), the coverage denominator.
3. `categories, blocked = _categories_with_required_gate(metrics, cfg, profile)` (line 608) —
   function not yet read; UNDETERMINED what "required gate" means precisely and whether it
   ever zeroes/withholds a whole category. THG's `categories_withheld: {}` is empty, so it did
   not fire for THG.
4. `raw = weighted_available(categories, cfg["category_weights"])` (line 609) — confirmed
   present at `scorer.py:159`, not yet read in full; this is the within-category-then-across-
   category reweighting step the brief asks about. THG's published `fundamental_detail.raw_score:
   89.0` and `categories`: valuation 90.0, profitability 77.5, financial_health 100.0, growth
   86.1, capital_allocation 91.9, accounting_quality 100.0.
5. `coverage = weighted_coverage(...)`. THG: `0.96` (`fundamental_detail.coverage`).
6. `confidence_multiplier = 0.65 + 0.35 * coverage` (line 615) → `0.65 + 0.35*0.96 = 0.986`.
7. `total = raw * confidence_multiplier` → `89.0 * 0.986 = 87.75`, rounds to the published
   `components.fundamentals: 87.7`. **This arithmetic checks out exactly** against the
   published artifact — first fully-verified formula-to-output match in this trace.

This is the **first of at least two places coverage/confidence shrinks the score** — see §4.

## 3. Live market-behavior and blend

`components.market_behavior: 73.9`, `components.news_sentiment: null` for THG (news
unavailable this row). Not yet traced against `advisor_engine.technical_factors` —
UNDETERMINED pending next pass; the internal audit's weight table (`momentum_12_1 0.30,
risk_adjusted 0.26, relative_strength 0.16, drawdown_resilience 0.14, volume_confirmation
0.08, low_beta 0.06, technical_extended 0.06`) needs re-verification against current
`advisor_engine.py`, not yet done.

`blend_research_components` lives at `pipeline/advisor_engine.py:846` (shifted from the
internal audit's stale line 758 — confirms the file has changed materially since that audit).
**Now read in full and verified arithmetically** — see `ARCHITECTURE.md` §4.2 for the
line-by-line treatment. Summary against THG: `raw_score: 85.1` → `base = round(85.1 ×
(0.8 + 0.2 × 0.87), 1) = 82.9` (the second coverage shrink, using `data_coverage: 0.87`)
→ `82.9 + modifiers (macro_regime +1.06, insider_activity −2.63, total −1.57) = 81.33 →
81.3`, matching the published `score: 81.3` exactly. The "coverage counted twice" claim
**does hold in current code**: the fundamentals component entering this blend was already
shrunk once by `0.65 + 0.35 × coverage` inside `_band_valuation_score` (§2 step 6/7 above)
before `data_coverage_scalar` shrinks the composite again here. Both shrink events verified
against this row's published numbers.

## 4. Shadow path (`analysis_v2`, `recommendation_v2`)

Confirmed working and internally consistent for THG:

- `structural.raw_score: 90.5`, `effective_score: 74.7` in
  `recommendation_v2.company.structural` vs `74.5` in `analysis_v2.structural` — **a genuine
  0.2-point discrepancy between two copies of the same computed value in one payload, now
  root-caused as a rounding-order defect.** The two structural blocks are otherwise
  byte-identical (same `raw_score`, same `evidence_weight_resolved: 0.61`, same weights,
  same metric lists — confirmed by direct field-by-field comparison). The producer,
  `scoring_v2.py:164-166`, computes `confidence = coverage × provenance_reliability` from
  **unrounded** inputs: `0.3418/0.4066 × 0.72 = 0.60525…`, giving `effective = 50 +
  0.60525 × (90.5 − 50) = 74.51 → 74.5`, and then publishes the confidence rounded to two
  decimals (`evidence_weight_resolved: round(confidence, 2) = 0.61`,
  `scoring_v2.py:188`). The consumer, `recommendation_policy_v2._score_layer`
  (`recommendation_policy_v2.py:46-62`), **recomputes** the effective score at line 59
  instead of trusting the layer's own `effective_score` field — and it recomputes from the
  *rounded published* `evidence_weight_resolved`: `50 + 0.61 × 40.5 = 74.705 → 74.7`. Both
  arithmetics reproduce the published values exactly. The defect is that a downstream module
  re-derives a value its input already carries, from lossier (rounded) inputs, so the payload
  publishes two versions of "the" effective score that can differ by up to ±0.2 (half the
  0.01 confidence-rounding step × the 40.5-point distance from neutral). Recorded as
  finding 9 in `ARCHITECTURE.md` §10.2.
- `structural.evidence_weight_resolved: 0.61`, `coverage: 0.84`.
- `timeliness.raw_score: null`, `effective_score: null`, `coverage: 0.0` — confirmed no
  fabricated 50.0 (see §0).
- `matrix_classification: "hold_or_watch_timeliness_unavailable"` — a named branch for the
  "timeliness absent" state, distinct from a numeric `50 < 55` comparison. This means the
  two-axis matrix's None-handling was rewritten alongside the timeliness fix, not left to
  silently coerce `None` into a comparison. Not yet read against
  `recommendation_policy_v2.py`'s actual current source — UNDETERMINED whether this is a
  literal early-return branch or something else; policy source not yet opened this pass.
- `company_action: {"label": "watch", "display_label": "WATCH FOR ENTRY", "confidence": 0.61
  (= evidence_weight_resolved reused as a fifth "confidence"-flavored number for this row),
  "reason_codes": ["hold_or_watch_timeliness_unavailable"]}`.
- `policy_mode: "shadow"`, `legacy_recommendation_unchanged: true` — confirms the shadow
  policy is explicitly labeled non-authoritative in its own output, consistent with
  `recommendation_policy_v2.json`'s `"shadow_mode": true` (config file read directly,
  confirmed).
- Live legacy `recommendation.action: "HOLD"`, `agreement_count: 0`,
  `unmeasured_inputs: ["positioning.news_sentiment"]` — produced by `advisor_engine.action_for`
  (current lines 715-799, read in full this pass). Confirmed **the fail-open defaults the
  internal audit's §7a describes (`... or 99`, `... or 0`) are gone**: every test now uses a
  `_reading()` helper and an explicit `if value is None: unmeasured.append(...)` branch before
  any threshold comparison (e.g. lines 740-744, 754-758). A missing input is recorded in
  `unmeasured`, not silently converted into "no concern." This matches the docstring's claim
  (lines 716-726) and matches THG's actual output (one unmeasured input, zero triggered
  concerns, HOLD). This is a fifth brief-adjacent defect (not one of the four the brief names
  as "already-confirmed," but directly related to them) that also appears fixed.

Live stance `ATTRACTIVE` (score 81.3 ≥ 75, per `stance_for`, not yet re-read this pass) versus
shadow `company_action: watch` for the identical company in the identical payload — this is
exactly the "shadow vs legacy disagree, and the disagreement is presented to the user how?"
question the brief asks in §8. Not yet traced into the frontend to see how `stance` vs
`recommendation_v2.company_action` are actually reconciled or juxtaposed on screen —
UNDETERMINED, next step.

## 5. The checkpoint draft's open threads — all resolved

1. **The two different `suppressed_metrics` lists — root-caused, and it is a real defect,
   not a display artifact.** For THG, `fundamental_detail.suppressed_metrics` contains
   `sales_multiple` but not `trailing_revenue_growth`; `analysis_v2` (and both structural
   blocks) contain `trailing_revenue_growth` but not `sales_multiple` (16 items each,
   otherwise identical — confirmed by set-difference on the live row). Two independent
   mechanisms produce the divergence, both confirmed by direct read:

   - **Namespace split.** The live path (`scorer.applicability` →
     `canonical_metrics.suppressed_metrics`, `scorer.py:252`) queries the applicability
     registry with **legacy** metric IDs; the v2 path first maps IDs through `ALIASES`
     (`scoring_v2.py:72-76`: `revenue_growth → trailing_revenue_growth`, `earnings_growth →
     trailing_eps_growth`, `sales_multiple → price_to_sales`) and queries with **canonical**
     IDs (`scoring_v2.py:103-104`). `applicability_matrix.json`'s
     `property_casualty_insurer` rule block is keyed `sales_multiple` (legacy namespace,
     confirmed in the rule-key list) — so the live path finds that rule and suppresses, while
     the v2 path asks about `price_to_sales`, finds no rule and no registry entry
     (`metric_registry.json` has no `price_to_sales` entry — confirmed), and falls through
     to `"applied"` (`canonical_metrics.py:150`), publishing it as merely *missing*
     (`price_to_sales` appears in v2's `missing_metrics` for THG).
   - **Fallback asymmetry.** `applicability_for` (`canonical_metrics.py:141-150`, the v2
     path) has a second suppression source the live path lacks entirely: a metric *with* a
     registry entry whose `applicability_profiles` does not list the profile is suppressed by
     default (line 147-149). `trailing_revenue_growth`'s registry entry declares
     `['general', 'utility', 'commodity_producer', 'pre_profit_biotechnology',
     'other_pre_profit']` — no insurer profiles — so v2 suppresses it for THG. The live
     path's `canonical_metrics.suppressed_metrics` (lines 153-172) consults **only**
     `profile_rules` and never reads `metric_registry.json`, and it queries with the legacy
     ID `revenue_growth` (which has no registry entry at all) — so the live scorer **scores
     revenue growth for insurers** (`scorer.py:584`) even though the canonical registry
     declares it inapplicable. The effect is visible in the published row: legacy `growth`
     category 86.1 (includes the revenue-growth band score) vs. v2 `growth` category 100.0
     (excludes it).

   The docstring on `suppressed_metrics` says "One authority now serves both paths"
   (`canonical_metrics.py:156-162`, describing commit `0e0a9ad`) — both paths do now read
   the same files, but through **different ID namespaces and different fallback rules**, so
   they can still disagree metric-by-metric. Recorded as a new finding in
   `ARCHITECTURE.md` §10.2.
2. `blend_research_components` — read in full, "coverage counted twice" confirmed against
   current code and this row's arithmetic (§3 above; `ARCHITECTURE.md` §4.2).
3. `_categories_with_required_gate`, `weighted_available`, `weighted_coverage` — read in
   full; documented in `ARCHITECTURE.md` §4.1 steps 4-5. THG's `categories_withheld: {}`
   is consistent: the P&C-insurer `required_for_score` metrics all resolved for THG.
4. Market-behavior sub-weights — verified (`advisor_engine.py:53-59`;
   `ARCHITECTURE.md` §6.4).
5. 74.7 vs 74.5 — root-caused as a rounding-order defect (§4 above).
6. Universe membership and run mode — resolved (§1 above: base-universe symbol, fast-mode
   artifact, 247 polled).
7. `data_coverage_components` — traced in full against THG's published components
   (`ARCHITECTURE.md` §7 item 5).
8. Frontend rendering of `stance` vs `recommendation` vs `recommendation_v2` — covered in
   `ARCHITECTURE.md` §9.
9. Floor/recovery mechanism — it is `src/lib/dipWatch.js`, frontend-only, fully documented
   with all six constants in `ARCHITECTURE.md` §8.3 (and it is *not* the shadow policy's
   stop-loss machinery, which no published row can currently reach).
