# Build Plan

Master Remediation Prompt v3, Output section. Covers Parts B–E with real effort estimates,
produced after B1–B7's schemas were reviewed against actual code (not before, per the prompt's
own instruction). Items 1–7 below are DONE this session — implemented, tested, wired, and
user-visible, verified by `npm run lint && npm test && npm run build` (932 JS tests) and
`PYTHONPATH=pipeline python -m pytest pipeline/tests` (2212 tests), plus
`check_ui_weights.py`/`validate_documentation_claims.py`. Items 8–12 are proposals only, per the
Execution Contract's tier rules — none were implemented, and B3/B4 explicitly stop before any code.

---

## Done this session

| # | Item | What shipped | Files |
|---|---|---|---|
| 1 | Stale-doc correction | `docs/MASTER-METHODOLOGY.md` §3/§7, `docs/MODEL-CARD.md`'s confidence section, and the breakdown generator corrected to describe current code, not a formula retired 2026-08-12 or a UI label ("Evidence confidence") that was never shipped. | `docs/MASTER-METHODOLOGY.md`, `docs/MODEL-CARD.md`, `scripts/generate-app-breakdown.mjs` |
| 2 | MWR/XIRR wired to Performance | `portfolioReturnSummary` (already tested, never imported) is now rendered. Since real MWR needs recorded account-value snapshots and settled cash flows — neither of which any UI could write before this session — also built: an auto-recording snapshot effect, a cash-flow entry form (deposit/withdrawal/dividend/fee), and a ledger-complete toggle. | `src/pages/portfolio/Performance.jsx`, `src/lib/usePortfolioTracking.js`, `src/lib/portfolioAnalytics.js`, `src/styles/modules/portfolio.css` |
| 3 | Turnover wiring bug fixed | `executionStatistics()` was called with no arguments, always evaluating an empty rebalance list. A real rebalance ledger now captures the portfolio's cost-basis weight vector before/after every add, edit, remove, and sell, persisted to a new `rebalances` Firestore collection and wired into the Data overview's execution statistics. | `src/pages/portfolio/usePortfolioForms.js`, `src/lib/usePortfolioTracking.js`, `src/lib/portfolioAnalytics.js` (`costWeights`), `src/pages/portfolio/portfolioAnalyticsModel.js` |
| 4 | Portfolio reconciliation bridge (B2) | Full NAV bridge (beginning NAV + deposits − withdrawals + dividends − fees + realized gains + unrealized-gain change ± untracked-but-disclosed FX/taxes/trading-costs = ending NAV), scoped to the most recent two recorded snapshots (the only window where every line is independently sourced, not a residual plug), with a cent-tolerance reconciliation check and an explicit `RECONCILED`/`RECONCILIATION_FAILED` status. `recordSnapshot` now also captures `unrealizedGain` alongside `value`. | `src/lib/portfolioAnalytics.js` (`portfolioReconciliationBridge`), `src/lib/usePortfolioTracking.js`, `src/pages/portfolio/Performance.jsx` |
| 5 | Holdings-level data-quality display | `DataStatus.jsx` was pipeline-wide only. New `HoldingsDataQuality` panel reads the per-ticker `data_coverage`/`data_coverage_detail`/`data_quality_violations`/`last_polled_at` fields the pipeline already publishes (`portfolio_coverage`/`research`/`screen_universe`) but no page ever surfaced, scoped to the user's actual holdings. | `src/pages/portfolio/HoldingsDataQuality.jsx`, wired into `src/pages/portfolio/DataOverview.jsx` |
| 6 | Canonical transaction event schema | JSON Schema (draft 2020-12) covering every B1 timestamp field plus B3's lot/tax fields, with a companion doc mapping it against today's three narrower Firestore collections and what a B3 migration would need. Schema only — nothing reads or writes this shape yet. | `docs/schemas/transaction-event.schema.json`, `docs/TRANSACTION-EVENT-SCHEMA.md` |
| 7 | Fundamentals confidence-multiplier follow-up | Investigated registering an isolated challenger for `scorer.py`'s `0.65+0.35×coverage` multiplier. Discovered mid-implementation that the champion's published score already bypasses this multiplier entirely (`build_research()` reads `raw_score`, never the multiplied value) — the originally-planned challenger would have always equaled the champion exactly, testing nothing. Reverted that addition; corrected the prior session's overstated finding across four docs; added an additive `apply_confidence_multiplier` parameter (default preserves all behavior) and two tests proving (a) the champion bypasses the multiplier and (b) its one real remaining live consumer is `fetch_advisor.py::enrich()`'s enrichment-priority sort key. | `pipeline/scorer.py`, `pipeline/tests/test_round4_remediation.py`, `docs/AUDIT-VERIFICATION-RESULTS.md` §6, `docs/MODEL-RISK-REGISTER.md` §1, `docs/AUDIT-ROADMAP.md` item 8, `docs/METRIC-GAP-MATRIX.md` |

Item 7's self-correction is itself worth flagging as a process point: a production-code change
was drafted on the strength of an unverified-in-full claim, and the check that would have caught
it (does the champion actually consume this value?) was run before the change was committed, not
after. That is the discipline the Execution Contract's tiers are for.

---

## Proposals only — not implemented, per the Execution Contract's T4 tier

### B3 — Transaction / tax-lot ledger

**Status: first real slice built in a follow-up session, with explicit user sign-off** (this
document's own T4 tier requires it; the user said "proceed" after being asked which of B3/B4 to
prioritize). What follows records both what was proposed and what was actually implemented.

**Current architecture (superseded by the discovery below)**: three narrow Firestore collections
built this session (`intradaySnapshots`, `activity`, `rebalances`) plus the pre-existing position
store (`portfolios/{uid}/positions`, one row per held ticker with `shares`/`costBasis`/
`purchaseDate`, average-cost only). None of these have lot identity — a sell computes
`realizedGain` once, as `proceeds − sharesSold × averageCostBasis`, and the position's share count
is simply reduced.

**What the follow-up session found before writing any code**: `addPosition()`
(`useFirebasePortfolio.js`) creates a fresh Firestore document with its own id on every buy
(`${ticker}-${Date.now()}`), never merging into one running-average position per ticker. That
means every stored position document already IS a lot — one purchase date, one cost basis, one
share count — contrary to this proposal's original "average-cost only" framing above. The actual
gap was narrower than originally scoped: not "lots don't exist," but "there is no engine that can
sell a quantity of a ticker spanning more than one of its existing lots." Clicking the existing
per-row Sell button already constitutes specific identification of that one lot (IRS Publication
550's alternative to FIFO) and needed no change.

**What was built**: `src/lib/taxLots.js` — `lotsForTicker` (a ticker's open lots, oldest
acquisition date first), `planFifoSale` (depletes across as many lots as a sale needs, oldest
first, unavailable with a clear reason if the requested quantity exceeds total holdings),
`realizedGainForPlan` (proceeds/cost basis/realized gain, total and per lot), `lotCountsByTicker`.
Wired into `usePortfolioForms.js` as a new, additive `saveLotSell` flow (`startLotSell`/
`cancelLotSell`/`lotSellPlan` live preview) that depletes the affected position documents via the
same `updatePosition`/`removePosition` calls the existing single-lot sell already uses, records one
`realized_gain` activity entry with a per-lot breakdown in its note, and captures one rebalance
event spanning every depleted lot. UI: `Holdings.jsx`/`HoldingCard.jsx` show a "Sell across N lots"
action next to the existing per-row Sell, only for tickers actually held across more than one lot
(`lotCountsByTicker`), with a `LotSellSheet` that previews exactly which lots a quantity would draw
from before the user confirms. 12 tests in `taxLots.test.js`, 8 in `usePortfolioForms.test.js`, 2 in
`HoldingCard.test.jsx`. Full JS suite, lint, and build all pass. Not manually verified in a running
browser — the dev-mode preview portfolio (`mobile_preview_positions` in `settings.json`) holds no
ticker across multiple lots, so the new button never renders against it; verification rests on the
automated test coverage above, not a live click-through.

**Explicitly not built this slice, per the original estimate's own sequencing** (unchanged from the
original proposal below): specific-identification lot-picker UI (FIFO already covers the IRS
default case; picking a specific lot manually is additional UI, not additional engine), the
wash-sale detector (the original estimate is explicit that this "depends on lot data, can't be
built first" — lots need to exist and be exercised before that detector has anything to reason
about), LIFO or other non-default depletion methods, and any retroactive backfill of lots for sales
already recorded before this session (impossible to reconstruct the original per-purchase history
for a sale that already collapsed it into one `realizedGain` figure).

**Proposed schema**: `docs/schemas/transaction-event.schema.json` (item 6) already specifies the
event shape. B3 additionally needs a `Lot` entity, not yet schematized:

```json
{
  "lot_id": "string, stable, unique",
  "security_id": "string, matches transaction-event's security_id",
  "account_id": "string",
  "acquisition_event_id": "string, the buy/transfer_in event_id that created this lot",
  "acquisition_date": "date",
  "original_quantity": "number",
  "remaining_quantity": "number",
  "original_basis_per_unit": "number",
  "adjusted_basis_per_unit": "number, after wash-sale/return-of-capital adjustments",
  "basis_adjustments": [{ "event_id": "string", "amount": "number", "reason": "enum: wash_sale | return_of_capital | corporate_action" }],
  "tax_treatment": "enum, matches the owning account",
  "status": "enum: open | fully_depleted",
  "closed_at": "date, null while open"
}
```

**Migration**: not a breaking change to what exists. Today's average-cost position becomes,
under this schema, a single lot per historical purchase (or one lot per position if purchase
history isn't granular enough to split) — existing `shares`/`costBasis` data maps onto
`original_quantity`/`original_basis_per_unit` directly. The harder part is the *engine*, not the
schema: FIFO/LIFO/specific-identification depletion logic (IRS Pub 550's default is FIFO absent
specific identification at the time of sale), a real wash-sale detector (loss disposals within
the 61-day window around a replacement purchase, with basis carried forward — not a tax
determination, a warning), and rewiring `saveSell` (`usePortfolioForms.js`) to deplete specific
lots instead of adjusting one aggregate `shares` field.

**Affected code**: `usePortfolioForms.js` (sell flow rewritten around lot selection),
`usePortfolioTracking.js` (new `lots` collection + read/write), `portfolioAnalytics.js`
(realized/unrealized gain currently computed from aggregate cost basis, would need to sum across
lots), a new `taxLots.js` module for depletion/wash-sale logic, plus UI for lot selection at sale
time (specific-identification requires the user to pick which lot(s) to sell, not just enter a
share count).

**Effort estimate**: 2–3 weeks for a solo engineer to build the lot engine, migration, and
specific-identification UI correctly and test it against IRS Pub 550's rules; another 1 week for
the wash-sale detector once lots exist (it depends on lot data, can't be built first). Multi-week,
correctness-critical, touches money math a user could act on incorrectly if wrong — squarely T4.

### B4 — Independent corporate-action ledger

**Current architecture**: none. `pipeline/config/research_contract.json` states outright: "no
independent corporate-action event log exists yet." All price/split/dividend adjustment happens
inside Yahoo's adjusted-close series, with no separate reconciliation (confirmed,
`docs/AUDIT-VERIFICATION-RESULTS.md` §7.2).

**Proposed schema** (from the master prompt's B4, unchanged — it was not contradicted by
anything found this session):

```text
security_id, action_id, action_type, declaration_date, record_date, ex_date, payment_date,
effective_date, cash_amount, ratio, currency, source, source_event_id, observed_at, revised_at,
status
```

**Migration**: this is net-new ingestion, not a migration of existing data — there is nothing to
migrate from. The corporate-action ledger would sit upstream of both the pipeline's price series
and the frontend's `transaction-event.schema.json`'s `corporate_action_id` cross-reference (item
6), which already anticipates this.

**Affected code**: a new `pipeline/corporate_actions.py` provider module (source TBD — Massive/
Tiingo event feeds were the master prompt's suggestion, cross-checked against SEC filings), a new
`pipeline/schemas/corporate_actions.schema.json`, a new committed artifact under
`public/data/corporate_actions/` or similar, and a reconciliation check comparing each
security's adjusted-close series against this ledger's implied adjustments — exactly the kind of
check `docs/BUILD-PLAN.md`'s reconciliation bridge (item 4) already models for cash-flow
reconciliation, extended to price-series reconciliation.

**Effort estimate**: 1–2 weeks for ingestion + schema + the committed artifact, assuming a
provider is chosen and its free-tier terms are re-checked first (per `docs/API-DATA-SOURCE-PLAN.md`
— Tiingo's free tier is internal-use-only, Massive's free tier is individual-use); another few
days for the price-series reconciliation check. Lower urgency than B3 for a personal-use
deployment (Yahoo's adjustments are usually correct), but a release blocker per the master
prompt's own release-gate table before any multi-user exposure ("corporate actions can silently
corrupt returns → not investment-grade, full stop").

---

## B5 — Metric registry

**Status**: not built. The specific divergent case the master prompt flagged (`momentum_12_1`
computed twice, differently) is confirmed and documented (`docs/METRIC-GAP-MATRIX.md`), but no
general registry exists mapping every derived metric to its definition/source/timestamp
model/validation tests.

**Effort estimate**: a registry *schema* (metric_id, definition_version, economic_definition,
source_fields, provider_priority, timestamps, transformation, missing_data_policy, UI_units,
validation_tests, owner) is a 1-day design task, similar in scope to item 6's transaction-event
schema. Backfilling it for even the ~30 metrics already flagged as needing disambiguation
(the momentum pair, the two Monte Carlo systems, the confidence/coverage rename) is another
2–3 days of careful documentation work, not code. Populating it for the full metric surface
(hundreds of fields across `pipeline/config/settings.json`) would be multi-week and is not
recommended as a single project — better done incrementally, one registry entry per metric
touched by future work, per `docs/AUDIT-ROADMAP.md` item 28's ablation registration.

## B6 — Health artifact extension

**Status**: partially exists. `pipeline/reports/normalization_audit.json`, `bias_check.json`, and
similar artifacts already publish data-quality diagnostics. The specific new fields the master
prompt asks for — `rank_spearman_same_config` (isolating data-driven rank drift from
methodology-driven drift), `enrichment_job_status`/`enrichment_job_estimated_completion_at`, and
a machine-readable `reason_codes` array on the publish gate — do not exist yet.

**Effort estimate**: `rank_spearman_same_config` needs two consecutive runs with an unchanged
`config_hash` to compare — the comparison logic itself is a half-day of work
(`scipy.stats.spearmanr` over two rank vectors, already a pattern used elsewhere in this
pipeline), but it depends on `config_hash` actually being published per-run and compared, which
per this session's B9 investigation (below) is not currently true for the published `research`
rows. `enrichment_job_status` doesn't apply as originally scoped — this session's Step 0
investigation found no long-running background enrichment job exists (each scheduled refresh
completes in under 30 minutes; enrichment coverage is steady-state, not climbing — see this
session's git/GitHub Actions history). That specific field can be dropped from the design rather
than built. Total: 2–3 days once `config_hash` publishing exists, per the note below.

## B7 — Backfill policy

**Status**: effectively already followed. The PIT store's append-only, never-backfilled
discipline (`pipeline/pit_store.py`) already enforces exactly this distinction for fundamentals
inputs, and this session's own additions (the reconciliation bridge, MWR, turnover) all follow the
same rule explicitly — every new Firestore field (`unrealizedGain` on snapshots, the `rebalances`
collection) starts accumulating from the moment it was added, nothing was backfilled. No new work
needed; this is a discipline to maintain, not a gap to close.

## B8 — Signal dimensionality / never-run ablations

**Status**: not run. `docs/AUDIT-ROADMAP.md` item 28 and `docs/AUDIT-VERIFICATION-RESULTS.md` §5.3
already list exactly which ablations (market-behavior-only, no-news, no-valuation,
no-profitability standalone, no-analyst-modifier, equal-weight-*categories*, reduced-redundant-
metric, sector-neutralized) have never been run as named champion comparisons, distinct from ones
already run in `research/audit/round3-6/`.

**Effort estimate**: registering each as an `experiment_registry.py` entry once actually run is
trivial (the schema already exists and is exercised by 14 entries). Running them requires a live
pipeline environment with real market data — not available in this session (no network access to
a live refresh) — so this remains correctly deferred, not skipped. Estimate once network access
exists: a few hours per ablation to run and record, half a day to compute the eigenvalue-based
`N_eff` signal-dimensionality measure (B8's formula) across the results.

## B9 — Score explainability, backward trace

Per the master prompt's explicit instruction to verify before building anything new:

**What already works**: `pipeline/explainability.py::score_attribution` and
`metric_explanations` decompose a *current* published score forward — from neutral evidence
through category weights through the final score — for any row, already wired into
`StockDetailModal.jsx`'s waterfall/evidence display. This is real, tested, and live.

**Where the chain actually breaks, confirmed this session**:
1. `docs/MASTER-METHODOLOGY.md` states scored rows carry `model_version`/`config_hash`. Checked
   directly against a live published row (`public/data/advisor.json`'s `research[0]`): neither
   field is present. `data_fetched_at` is present; `model_version`/`config_hash`/`recorded_at`/
   `data_as_of` are not. This means a past score cannot currently be tied to the exact formula
   version that produced it — exactly the ambiguity that made this session's own confidence-
   multiplier investigation (item 7) require reading source code and git history rather than
   reading a stored field, and precisely the gap the master prompt's B9 section predicted.
2. `pipeline/pit_store.py::TRACKED_FIELDS` (the fundamentals-input log) does not track
   `config_hash` either — so even the append-only PIT history can't answer "what formula version
   scored this row" without cross-referencing git history by timestamp.
3. Whether `raw observation → provider/source document` is retained (the second gap the master
   prompt predicted) was not fully verified this session — `pipeline/data/pit/fundamentals`'s
   XBRL facts (per `docs/AUDIT-VERIFICATION-RESULTS.md` §7.5) do retain accession-level source
   references for EDGAR-sourced facts, but Yahoo-sourced facts' raw provider responses are not
   independently confirmed retained.

**Effort estimate, and status update**: publishing `config_hash` was a half-day change with a
clear, low-risk diff (additive field, no scoring change) — done in a follow-up session.
`fetch_advisor.py` now computes a SHA-256 of `settings.json` (reusing
`validation/experiment_manifest.py::sha256_of_file`, the same hashing this file's Part B/C
proposals already treat as prior art) once per run and publishes it as a top-level `config_hash`
field on `advisor.json`, alongside the existing `model_version`. It is also passed into
`pit_store.py::append_snapshot()` as a new `config_hash` key on each observation row (deliberately
*not* folded into `TRACKED_FIELDS`, which is per-ticker fundamentals metrics, not run-level
metadata) — this is the part that actually answers "what formula version produced this PIT
observation taken months ago" without cross-referencing git history by timestamp. Verifying and,
if needed, extending raw-provider-response retention for Yahoo-sourced facts remains a separate,
larger investigation (1–2 days) not completed. Still a P1, not P0: a reproducibility/audit-trail
gap, not a correctness bug in any currently-published score.

---

## Part D — Rubric application

Not run this session. Applying the master prompt's weighted rubric (research methodology 15,
PIT/data integrity 15, statistical validation 15, portfolio performance accounting 10, risk
analytics 10, execution/liquidity/cost 8, data coverage/source quality 8, planning/model risk 6,
options 5, UX 5, engineering 3) properly — line-by-line against code, not from documentation —
is a substantial, standalone audit task in its own right, and several of this session's own
corrections (item 7's self-correction chief among them) argue for caution about doing this
quickly. Recommend a dedicated pass once B3/B4 sign-off decisions are made, since those decisions
materially affect the "portfolio performance accounting" and "PIT/data integrity" category scores.

## Sequencing recommendation

Unchanged from `docs/AUDIT-ROADMAP.md`'s existing order, updated for what's now done: items 1–7
above are complete. Next in priority, per that roadmap: item 9 (options r=0 disclosure, T1-adjacent,
small), then the remaining T3 portfolio-analytics wiring items (weighted ETF expense ratio,
benchmark policy, rolling metric stability beyond Sharpe), then B9's `config_hash` publishing
(cheap, unblocks real audit-trail value), then B3/B4 once sign-off is given.
