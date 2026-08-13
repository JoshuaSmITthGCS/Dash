# TRACE — THG (The Hanover Insurance Group) end-to-end, checkpoint draft

Status: **partial, checkpoint draft**. This traces THG through the live (champion) scoring
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

- Universe membership: `pipeline/config/advisor_universe.json` (not yet fully read this pass
  — UNDETERMINED whether THG is in the base list or a portfolio addition; to confirm before
  final doc).
- Run mode this artifact: `data_mode` / `universe_mode` fields exist in `advisor.json` top level
  (not yet extracted) — UNDETERMINED, will pull in the next pass.
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

`blend_research_components` now lives at `pipeline/advisor_engine.py:846` (shifted from the
internal audit's stale line 758 — confirms the file has changed materially since that audit).
Not yet read in full this pass. THG: `score: 81.3`, `base_score: 82.9`, `raw_score: 85.1`,
`data_coverage: 0.87`. The gap `85.1 → 82.9` and `82.9 → 81.3` (modifiers: `macro_regime
+1.06`, `insider_activity -2.63`, `total -1.57`) is arithmetically consistent
(`82.9 - 1.57 = 81.33 → 81.3`), but the `85.1 → 82.9` step (presumably the second coverage/
confidence shrink the internal audit's §4 describes as "counted twice") is **not yet verified
against the actual `blend_research_components` body** — I have not read that function's
current text yet. This is the single most important formula left to verify before the main
document is trustworthy on the "counted twice" claim, since the audit's version of this claim
is from before `cd581b5`/`ac24342` and may no longer hold in the same form.

## 4. Shadow path (`analysis_v2`, `recommendation_v2`)

Confirmed working and internally consistent for THG:

- `structural.raw_score: 90.5`, `effective_score: 74.7` (note: two slightly different
  effective_score values appear in the payload — `recommendation_v2.company.structural.
  effective_score: 74.7` vs `analysis_v2.structural.effective_score: 74.5` — **a genuine
  0.2-point discrepancy between two copies of what should be the same computed value in the
  same payload**, not yet explained; flagged as a finding to chase, not yet root-caused).
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

## 5. Open threads before this trace is complete

1. Reconcile the two slightly different sets of "suppressed metrics" for THG appearing at
   `fundamental_detail.suppressed_metrics` (16 items, includes `sales_multiple`, excludes
   `trailing_revenue_growth`) vs `analysis_v2.applicability.suppressed_metrics` (16 items,
   includes `trailing_revenue_growth`, excludes `sales_multiple`) — likely two different
   registries or two different metric-ID alias layers (`ALIASES` in `scoring_v2.py:72-76`
   maps `revenue_growth → trailing_revenue_growth`, `sales_multiple` has no such alias) but
   not yet confirmed by reading the code that produces `fundamental_detail.suppressed_metrics`.
2. Read `blend_research_components` in full to verify or refute the "coverage counted twice"
   claim against current code (§3 above).
3. Read `_categories_with_required_gate`, `weighted_available`, `weighted_coverage` in full
   (currently only located, not read).
4. Read `advisor_engine.technical_factors` for the market-behavior sub-weights and verify
   against current `settings.json`.
5. Root-cause the 74.7 vs 74.5 `effective_score` discrepancy in §4.
6. Confirm THG's universe/portfolio membership path and run mode (`full` vs `fast`) for this
   specific artifact.
7. Trace `data_coverage_components` (`pipeline/data_coverage.py`, confirmed to exist,
   functions listed but not read: `completeness_component`, `freshness_component`,
   `peer_sample_component`, `model_agreement_component`, `run_source_reliability`,
   `historical_calibration_component`, `data_coverage_components`) against THG's
   `data_coverage_detail.components` (`completeness: 0.87, freshness: null, source_reliability:
   0.92, peer_sample: 0.35, model_agreement: 0.25, historical_calibration: null`) to get the
   exact current formula, not the old `confidence.py` formula the internal audit describes
   (that module no longer exists under that name).
8. Frontend rendering: how `stance`, `recommendation`, and `recommendation_v2` are surfaced
   together (or not) on THG's detail page — not yet opened any `src/` component for this.
9. Floor/recovery-level logic exists in `src/lib/dipWatch.js` (confirmed present by grep, not
   yet read) — needed for brief §8's NEM floor/recovery example.
