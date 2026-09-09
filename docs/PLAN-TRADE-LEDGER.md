# Plan: Firebase is the portfolio record — trades, sales, and performance

**Status:** implementation plan, written 2026-09-09 on branch `claude/stock-selling-ux-bugs-svfmlr`.
**Audience:** the agent executing it. Every work package below is self-contained: files,
exact changes, tests, and an acceptance check. Read §1–§3 first; they say what is already
shipped on this branch so nothing gets rebuilt.

---

## 0. The one-paragraph version

The app's Firestore collections (`portfolios/{uid}/…`) are the record of what is held and
what has happened to it. The Fidelity export checked into `src/lib/referencePortfolio.js` is a
photograph of one morning, useful for seeding an *empty* account and as a dated price
observation, and for nothing else. A recorded sale must never be undone by anything, every
buy and sale must be visible to every performance measure, and the account must be brought
up to date with the real Fidelity activity through Sep 4, 2026. This plan makes those four
things true and adds guards so they stay true.

---

## 1. Root cause: why the LULU sale "didn't take"

Joshua sold 1 LULU on **Sep 3, 2026 for $102.40** (Fidelity activity). He recorded the sale in
Dash. It came back.

**Mechanism.** `REFERENCE_PORTFOLIO` in `src/lib/referencePortfolio.js` still lists
`['LULU', 1, 117.94, …]`. Before this branch, `planReferencePortfolioSync()` was
*authoritative*: any export ticker not currently held was added, every held ticker's shares and
cost were restated to the export, and any holding absent from the export was deleted. A
completed sale leaves exactly the "export ticker not held" state, so any sync re-created the
position from the export — and silently reset every trimmed share count at the same time.

**Two triggers, both live at the time:**

1. *Load-order race.* `usePortfolioForms.js` gated the one-shot auto-sync on
   `tracking.trackingState?.referencePortfolioVersion`, which is `null` both when nothing was
   ever synced **and** while the tracking document is still loading. The positions listener and
   the tracking listener resolve independently; on any page load where positions answered
   first, the gate read "never synced" and re-applied the whole 46-position export.
2. *The manual button* ("Reapply Aug 25 Fidelity snapshot") and the CLI
   (`npm run portfolio:sync -- --commit`) did the same thing on demand.

**Forensic check the executor can run** (WP4 automates it): a position document for a ticker
whose `closedPositions/{ticker}` document exists, or whose `importedAt`/`syncedAt` postdates a
`realized_gain` activity row naming that ticker, was resurrected by a sync.

---

## 2. Already shipped on this branch (do not redo)

| Commit | What it did |
|---|---|
| `0c63a64` | `closedPositions` collection; sync skips closed tickers; auto-sync waits for `trackingLoaded`; `useDialog` focus fix (typing in any sheet kicked focus out); sticky `TradeBar` in `StockDetailModal`; FIFO `submitTrade()`; "Sold" list under holdings. |
| `1cbd103` | A sale no longer flips `ledgerComplete` (only a bare Remove does); `realizedResultSummary()` + Realized KPI on Summary. |
| `84491ac` | `planReferencePortfolioSync(..., { mode: 'seed' \| 'reconcile' })`. App runs **seed only**: adds never-delivered tickers, backfills blank purchase dates, never restates, never deletes. `referencePortfolioSeeded` ledger on `tracking/state`. CLI writes seed-only unless `--authoritative`. `portfolioImport.js` explicitly reconciles. |
| `8eae175` | **Trades are ledger events.** `addPosition` writes `stock_purchase`; every sell path writes `sale_proceeds` beside `realized_gain`. `BASKET_FLOW_TYPES` in `portfolioAnalytics.js` is the shared vocabulary; Modified Dietz, TWR, XIRR, trader-insight units, and the reconciliation bridge all remove these flows. `netInvestedCapital()` deliberately ignores them. `recordSnapshot` stores per-ticker `prices`; `buildPriceModel` prefers the account's recorded prices over the export seed. |
| (this session) | `seededTickersFromTrackingState()` — an account seeded before the ledger existed is treated as having received the whole export. |

Tests: 1574+ passing. The `src/mediums/core/screens/HomeScreen.test.jsx` "as-of eyebrow" test
is a pre-existing `React.lazy` timing flake under full-suite load; it passes in isolation and on
a clean tree. Not this work's.

---

## 3. Audit: what is wired correctly, and what is still wrong

### 3.1 Correct now (verified by tests on this branch)

- **Holdings, allocation, sector mix, day move, concentration** — all derive from `positions`;
  a sold ticker leaves them the moment its document is gone.
- **Value charts** — `currentHoldingsSeries` / `currentHoldingsPerformanceSeriesForPeriod`
  re-price *current* shares against historical prices, so a sold name leaves the whole line
  rather than cutting a cliff. `currentBasketValue()` returns `null` when any held ticker is
  missing from a snapshot's prices — a snapshot predating a buy is discarded, never undercounted.
- **Reconciliation bridge, TWR, Modified Dietz, XIRR, trader-insight units** — remove
  `stock_purchase` / `sale_proceeds` flows. A sale reconciles to the cent; a sale reinvested
  same-day nets to zero NAV step; a real loss still charts as a loss.
- **Sync** — seed mode cannot restate or delete. Closed and already-seeded tickers are skipped.

### 3.2 Still wrong or unguarded (this plan's work)

| # | Finding | Where | Consequence | WP |
|---|---|---|---|---|
| A | **History predates the flow rows.** Every buy and sale made before `8eae175` has no `stock_purchase` / `sale_proceeds` row. | `activity` collection | Any performance window spanning an old trade is still wrong: the NAV step reads as gain or loss. | WP3 |
| B | **Joshua's account is not current.** LULU position doc still exists (resurrected). NTNX sale (Sep 4), TSM buy (Sep 2), $400 deposit (Sep 1), dividends — none recorded. | Firestore | Every figure on screen is off by these. | WP2 |
| C | **Seeding can still run on a non-empty account.** Gate is `referencePortfolioVersion` mismatch. When the export is next refreshed (new `REFERENCE_PORTFOLIO_VERSION`), the auto-run fires on every existing account. Seed mode makes it safe, but "safe because the planner is careful" is a weaker guarantee than "does not run". | `usePortfolioForms.js` effect | A future planner bug re-creates the LULU class of failure. | WP1 |
| D | **File import ignores closed tickers and writes no flow rows.** `applyPortfolioImport` → `planPortfolioImport` (reconcile) does not pass `closedTickers`; positions appear/disappear with no ledger event. | `src/lib/portfolioImport.js:160`, `useFirebasePortfolio.js applyPortfolioImport` | Importing a stale export re-adds sold names and breaks every return measure across the import date. | WP5 |
| E | **Bare Remove and share Edit are silent NAV steps.** `handleRemove` writes `position_removed` (no flow, flips `ledgerComplete`); `saveEdit` changing `shares` writes only `position_updated`. | `usePortfolioForms.js` | Bridge fails, TWR charts it. Remove is *documented* as "not a sale" — but the UI never asks whether it was one. | WP5 |
| F | **Snapshots are only recorded from the Performance page.** `recordSnapshot` fires once per market day *if the user opens Performance*. No visit → no observation → bridge windows span many days, MWR/TWR starve. | `Performance.jsx:163` | Sparse, user-behaviour-dependent history. | WP6 |
| G | **Money-market lines.** Fidelity shows FZFXX dividends/reinvestments. Tracked NAV excludes money market by design; these must be *excluded*, and the reconciliation script must not import them. | — | If imported as dividends they inflate the bridge. | WP2 |
| H | **`external_contribution` has no writer.** Reserved for "purchase declared as outside money"; the Add Position form has no such flag. Harmless (nothing writes it) but the comment at `portfolioAnalytics.js:346` describes a form control that does not exist. | `Holdings.jsx AddPositionForm` | Documentation/behaviour drift. | WP5 (optional) |
| I | **No audit tool.** Nothing checks the ledger identities across the whole history or detects a resurrected position. | — | The LULU failure was found by the user, not the system. | WP4 |

---

## 4. Design rules (apply to every WP)

1. **Firestore is the record.** No runtime read path may prefer in-code data over a stored
   position, activity row, or recorded snapshot. The export is (a) a seed for an *empty*
   account and (b) one dated observation in `intradaySnapshots`. Nothing else.
2. **Every NAV step has a ledger row.** Buy → `stock_purchase`. Sell → `sale_proceeds` +
   `realized_gain`. Cash in/out of the account → `deposit` / `withdrawal`. Dividend → `dividend`.
   A position change with no row is a bug.
3. **Writes are idempotent and attributable.** Derived or imported rows get deterministic ids
   (`<kind>-<sourceId>` or `<kind>-<ticker>-<date>-<cents>`), carry `source`, and where
   derived carry `derived: true, derivedFrom: <activityId>`. Reruns never duplicate.
4. **Dry run by default** for any script that writes Firestore. `--commit` writes.
5. **Performance is derived, not stored.** Metrics are computed at render from the raw
   collections. "Recalculate" therefore means: make the raw ledger complete (WP2, WP3), then
   invalidate any client cache (WP6). Do not introduce a stored-metrics table.
6. **Tests first for the identities.** Each WP lists the assertion that proves it.

---

## 5. Work packages

### WP1 — Seeding only ever runs on an empty account

**Files:** `src/pages/portfolio/usePortfolioForms.js` (the `useEffect` at ~L79),
`src/lib/useFirebasePortfolio.js` (`syncReferencePortfolio`), `src/pages/Portfolio.jsx`
(the data-actions button), `scripts/sync-portfolio-firebase.mjs`.

**Change:**
1. Add `isEmptyAccount(positions, tracking)` in `usePortfolioForms.js`:
   `positions.length === 0 && (tracking.activities || []).length === 0 && !tracking.trackingState?.trackingStartedAt`.
   The auto-sync effect fires **only** when `tracking.trackingLoaded && isEmptyAccount(...)`,
   in addition to the existing gates. Remove the `referenceReady` condition from the gate —
   version mismatch is no longer a reason to run. Keep `referencePortfolioSyncStarted` ref.
2. The manual button becomes two-step: a `window.confirm` naming exactly what it will do
   ("Adds N holdings from the {label} snapshot that this account has never held. It cannot
   change or remove anything."), where N comes from a **dry-run** plan computed client-side
   with `planReferencePortfolioSync(positions, undefined, { closedTickers, seededTickers, mode: 'seed' })`.
   If N === 0, no confirm — just the "nothing to add" status line. Export
   `planReferenceSeed({ positions, closedTickers, seededTickers })` from
   `useFirebasePortfolio` for this.
3. `syncReferencePortfolio` refuses `mode !== 'seed'` (it never accepted one; assert it).
4. CLI: `--authoritative` additionally requires `--i-understand-this-overwrites` (or
   equivalent explicit acknowledgement flag); print the removals list before the prompt.
5. Refreshing the export should still record its dated observation for existing accounts
   **without seeding**. Split `syncReferencePortfolio` into `recordReferenceObservation()`
   (writes the `intradaySnapshots` doc + `referencePortfolioVersion`/`ImportedAt` on
   tracking/state) and `seedReferenceHoldings()` (positions). The version-mismatch effect
   calls only the former on a non-empty account.

**Tests:** `usePortfolioForms.test.js` — (a) connected + loaded + positions present +
version mismatch → `syncReferencePortfolio` **not** called, `recordReferenceObservation`
called once; (b) empty account → seed called once; (c) button with N=0 → no confirm, message
contains "Nothing to add". `referencePortfolio.test.js` unchanged.

**Acceptance:** with a non-empty account and `REFERENCE_PORTFOLIO_VERSION` bumped, no
position document is written; one new `intradaySnapshots` doc appears.

---

### WP2 — Bring Joshua's account up to date with Fidelity activity

Source of truth: the Fidelity Activity → History screenshots (Aug 31 – Sep 4, 2026). Numbers
below are transcribed from them; reconfirm against the app before committing.

**Build:** `scripts/reconcile-portfolio-activity.mjs` (+ `.test.mjs`), reusing the credential
and backend plumbing from `scripts/sync-portfolio-firebase.mjs` (extract `connect()` and the
two backends into `scripts/lib/portfolio-firestore-backend.mjs` so both scripts share it).
Input: a JSON file of events. Dry run default; `--commit` writes; `--report <path>`.

Event schema (one array):
```json
[
  { "kind": "deposit",  "date": "2026-09-01", "amount": 400.00, "note": "Electronic Funds Transfer Received" },
  { "kind": "dividend", "date": "2026-09-01", "ticker": "SIGI", "amount": 0.89 },
  { "kind": "dividend", "date": "2026-09-01", "ticker": "COP",  "amount": 0.35 },
  { "kind": "buy",      "date": "2026-09-02", "ticker": "TSM",  "shares": null, "cost": 199.67, "note": "share count from Fidelity Positions tab — REQUIRED" },
  { "kind": "dividend", "date": "2026-09-02", "ticker": "DINO", "amount": 0.61 },
  { "kind": "sell",     "date": "2026-09-03", "ticker": "LULU", "shares": 1,     "proceeds": 102.40 },
  { "kind": "dividend", "date": "2026-09-03", "ticker": "AGO",  "amount": 0.23 },
  { "kind": "sell",     "date": "2026-09-04", "ticker": "NTNX", "shares": 1,     "proceeds": 67.86 },
  { "kind": "sell",     "date": "2026-09-04", "ticker": "NTNX", "shares": 0.284, "proceeds": 19.26 }
]
```
Excluded on purpose (rule G): FZFXX dividend/reinvestment, Fidelity Government MM dividend.

**What each kind writes** (all via the same functions the app uses — import
`planFifoSale`/`realizedGainForPlan` from `src/lib/taxLots.js` and the record shapes from
`useFirebasePortfolio.js`; do not hand-roll documents):

- `sell` → FIFO plan against current positions; per-lot `positions` update/delete;
  `activity/realized_gain-<id>` (amount = proceeds − cost sold);
  `activity/sale_proceeds-<id>` (amount = proceeds); `closedPositions/<TICKER>` when the
  ticker is fully exited. `id = ${ticker}-${date}-${Math.round(proceeds*100)}`.
  Expected results: LULU realized **−15.54** (102.40 − 117.94), closed. NTNX two rows,
  realized **+37.13** total (87.12 − 49.99), closed after the second.
- `buy` → `positions/<TICKER>-<date>` document with `costBasisUnit: 'per_share'`,
  `costBasis = cost / shares`, `costBasisInputMode: 'total'`, `purchaseDate`; plus
  `activity/position-added-<id>` and `activity/stock_purchase-<id>` (amount = cost).
  Refuse to run if `shares` is null: the script prints "TSM share count required".
- `deposit` → `activity/deposit-<id>`.
- `dividend` → `activity/dividend-<id>` with `ticker`.
- All rows: `effectiveDate`, `recordedAt: now`, `source: 'fidelity_activity_import'`,
  `importId: <id>`.

**Idempotency:** before writing, read existing `activity` docs; skip any whose id already
exists; print "already recorded" per event. A sell whose ticker has no open lots prints
"nothing to sell — already recorded?" and skips.

**Also in this WP:** set `tracking/state.ledgerComplete = true` **only if** the user confirms
the $400 EFT is the only external flow since `trackingStartedAt` (ask; do not assume).

**Tests (`scripts/reconcile-portfolio-activity.test.mjs`):** plan for the JSON above against
a stored portfolio matching `REFERENCE_PORTFOLIO` yields: LULU delete + realized −15.54;
NTNX two updates ending in delete + realized 37.13; TSM add; dividend/deposit rows; FZFXX
lines absent; running the plan twice yields zero writes the second time.

**Acceptance:** after `--commit`, the Summary shows no LULU/NTNX tile, TSM present,
Realized tile reads **+$21.59** (37.13 − 15.54), "Sold" list shows LULU (Sep 3) and NTNX
(Sep 4), Performance's cash-flow list shows the deposit and four dividends.

---

### WP3 — Derive the missing flow rows for historical trades

**Build:** `scripts/rebuild-trade-ledger.mjs` (+ test). Dry run default.

For every account, read `activity` sorted by `recordedAt`, and emit missing rows:

| Existing row | Derived row | Amount | Derivable? |
|---|---|---|---|
| `position_added` (has `amount`) with no `stock_purchase-*` sharing its `recordedAt` ±2s or `derivedFrom` | `stock_purchase` | `amount` | yes |
| `realized_gain` with `note` naming a ticker and no matching `sale_proceeds` | `sale_proceeds` | proceeds = gain + (shares sold × cost basis) | **only if** shares sold and cost basis are recoverable: from a `position_removed` row (full exit: `shares` field) or a `position_updated` row (`updates.shares` vs the prior share count) with the same ticker within ±60s. Else emit a `needs_review` line and **do not guess**. |
| `position_removed` with `source: 'manual_holding_removal'` and no `realized_gain` within ±60s | none | — | Bare removal. List under `needs_review`: "shares left with no sale recorded". |

Derived rows: id `derived-<kind>-<sourceActivityId>`, `derived: true`, `derivedFrom`,
`source: 'ledger_rebuild'`, `effectiveDate` copied from the source row. Bump
`tracking/state.ledgerRevision` (integer, default 0) on commit.

**Tests:** fixtures for each row of the table, including the "not derivable → needs_review"
case, and idempotency (second run = zero writes).

**Acceptance:** `npm run portfolio:audit` (WP4) reports zero bridge failures across the
account's recorded history except windows flagged `needs_review`.

---

### WP4 — Ledger audit tool (the thing that would have caught LULU)

**Build:** `scripts/audit-portfolio-ledger.mjs`, wired as `npm run portfolio:audit`. Read-only.
Exit code 1 on any finding. Reuse the shared backend from WP2.

Checks:
1. **Resurrected positions:** any `positions` doc whose ticker has a `closedPositions` doc, or
   whose `importedAt`/`syncedAt` > the latest `realized_gain`/`sale_proceeds` for that ticker.
2. **Closed tickers still held:** `closedPositions` ∩ held tickers (should be ∅ unless a
   later `stock_purchase` exists — a re-buy — in which case the closed doc should be gone).
3. **Bridge identity across history:** for every consecutive pair of daily snapshots carrying
   `unrealizedGain`, run `portfolioReconciliationBridge()`; report each `RECONCILIATION_FAILED`
   window with its residual and the activity rows inside it.
4. **Orphan NAV steps:** `position_added` without `stock_purchase`; `realized_gain` without
   `sale_proceeds`; `position_removed` with `manual_holding_removal` — same rules as WP3, reported
   not fixed.
5. **Snapshot price coverage:** snapshots with no `prices` (pre-`8eae175`) — informational.
6. **Reference drift (informational):** `planReferencePortfolioSync(..., { mode: 'reconcile' })`
   differences, clearly labelled "the statement differs from your record; this is expected after
   trading and is **not** applied".

Output: markdown table per check, plus `--json`.

**Tests:** run each check against in-memory fixtures (no Firestore): a resurrected LULU is
flagged; a clean account passes; a failed bridge window lists the rows inside it.

**Acceptance:** `npm run portfolio:audit -- --email <you>` on Joshua's account after WP2+WP3
prints only informational sections.

---

### WP5 — Close the remaining silent NAV steps

1. **File import** (`src/lib/portfolioImport.js`, `useFirebasePortfolio.js applyPortfolioImport`):
   pass `{ closedTickers }` through `planPortfolioImport`; for each `add` write a
   `stock_purchase` row (amount = shares × costBasis, `source: 'portfolio_import'`); for each
   `remove` in replace mode, refuse unless `--mode replace` was explicitly chosen in the UI *and*
   write a `position_removed` row with `source: 'portfolio_import'` (still not a sale — the
   audit will flag it). Update `ImportHoldings.jsx` copy to say imports never record sales.
2. **Bare Remove** (`HoldingCard.jsx`, `usePortfolioForms.handleRemove`): replace the direct
   remove with a small sheet: "Did you sell this? [Record the sale] [Remove without a sale]".
   "Record the sale" opens the existing `SellSheet` pre-filled with all shares. "Remove without a
   sale" proceeds as today and shows the existing warning that returns will not reconcile.
3. **Share edits** (`saveEdit`): when `shares` changes, write
   `activity/position_corrected-<id>` with `{ from, to, ticker }`, `source: 'manual_correction'`.
   Not a flow — but the audit (WP4 check 4) lists corrections so a reconciliation failure has a
   named cause.
4. *(optional)* Add an "Funded with new money" checkbox to `AddPositionForm` and the TradeBar's
   buy side; when checked write `external_contribution` **instead of** `stock_purchase`. This
   is the control `portfolioAnalytics.js:346` already describes. If not built, fix that comment.

**Tests:** import with a closed ticker in the file → no add for it; import add → one
`stock_purchase`; remove flow → sale path writes `sale_proceeds`; edit → correction row.

---

### WP6 — Recalculating performance from Firebase

Metrics are computed at render (`Performance.jsx`, `Summary.jsx`, `DataOverview.jsx`) from
`tracking.snapshots`, `tracking.activities`, `positions`. There is nothing stored to recompute;
the raw ledger *is* the input. So:

1. **`ledgerRevision`** on `tracking/state`: bumped (`increment(1)`) by every trade write
   (`addPosition`, sells, WP2/WP3 scripts). Expose from `usePortfolioTracking`. Include it in
   the `useMemo` dependency lists in the three views and in `buildPriceModel`'s inputs, so a
   rebuild is reflected without a reload.
2. **Record a daily observation from Summary as well as Performance** — move the once-per-
   market-day `recordSnapshot` effect out of `Performance.jsx` into `Portfolio.jsx` (it already
   has `holdings` and `tracking`). Same guard (`alreadyRecorded`), same `prices` via
   `snapshotPriceRows`. This is what makes bridge windows daily instead of visit-shaped.
3. **Backdated trades and the recorded history.** A sale entered today but dated Sep 3 books its
   flows on Sep 3; snapshots recorded Sep 3–8 still carry the *pre-sale* NAV. That is correct
   for the bridge (the flow lands in the Sep 3 window) and correct for the value chart (it
   re-prices current shares). Document this in `docs/SYSTEM-SETUP.md`; do **not** rewrite past
   snapshots.
4. **Performance page copy:** the "Reconciliation bridge" card gets a one-line source note:
   "Every line comes from your Firestore ledger; nothing here reads the Fidelity export."

**Tests:** `Portfolio` records one snapshot per market day with `prices` (jsdom test with
fake timers); revision bump triggers re-derivation (render test asserting the Realized KPI
updates when `activities` prop changes — already true, just add the assertion).

---

### WP7 — Guards so it cannot regress

1. **Invariant test (`src/lib/referencePortfolio.invariants.test.js`):** for every `mode`,
   `planReferencePortfolioSync()` never emits an `add` for a ticker in `closedTickers`; seed
   mode never emits `update`/`remove`; seed mode never emits `add` for a ticker in
   `seededTickers`. Property-style over generated tickers.
2. **Write-path test (`useFirebasePortfolio.test.js`, mock `firebase/firestore`):** the only
   functions that call `batch.set` on `positions/*` are `addPosition`, `updatePosition`,
   `syncReferencePortfolio` (seed), `applyPortfolioImport`. Assert by wrapping `writeBatch`.
3. **Ledger contract test:** every function in `usePortfolioForms` that changes `shares` also
   calls `recordActivity` with a `BASKET_FLOW_TYPES` member, except `saveEdit` (which writes
   `position_corrected`). Enumerate them; the test fails if a new one appears without a row.
4. **CI:** add `npm run portfolio:audit -- --fixtures` (WP4 in fixture mode, no network) to the
   `site` job in `.github/workflows/ci.yml`.
5. **Firestore rules (optional, evaluate first):** a `create` on `positions/{id}` could be
   denied when `exists(/databases/$(database)/documents/portfolios/$(uid)/closedPositions/$(request.resource.data.ticker))`.
   Caveat: `addPosition` deletes the closed marker in the *same batch*; rules see pre-batch
   state, so a legitimate re-buy would be denied. Only adopt if `addPosition` is changed to
   clear the marker in a separate write first. Otherwise skip and rely on 1–3.

---

### WP8 — The Data Overview evidence page: say what it measures, and add a Firebase scope

**Finding J (found after §3 was written).** Every scope on the Data Overview — "All portfolio
history", "Since algorithm activation", **and "Live algorithm only"** — computes its statistics
from `holdingsSeriesFull` (`src/pages/portfolio/portfolioAnalyticsModel.js:59-66`), which is
`currentHoldingsSeries(positions, priceData, dates)`: *today's* share counts applied to the
published price history in `report.json`. None of it reads `tracking.snapshots`. Consequences:

- After WP2 the page re-derives itself with no rebuild (every number there is computed at
  render from current positions — the "46 priced holdings", the detractors list, Sharpe, IR,
  capture, the 36-observation series). **Nothing to recompute; just reload.**
- But the series then describes a basket that never held LULU or NTNX — it cannot know they
  were held until Sep 3/4. The observation count does not reset because the series is synthetic.
- "Live algorithm only" is the same synthetic basket sliced from `LIVE_TRACKING_START`
  (2026-07-20). The label reads as "the real account" and is not.

**Change:**
1. **Honest labels.** In `src/pages/portfolio/format.js` `ANALYTICS_SCOPES`, rename
   `live_algorithm` → label "Today's basket, since algorithm start" and `all_history` →
   "Today's basket, full price history"; keep ids. Add a one-line note under the scope selector
   in `DataOverview.jsx`: "These scopes re-price the shares you hold *now* across history. They
   do not include holdings you have since sold. For your recorded account path see the
   Recorded scope / Performance page."
2. **New `recorded` scope (Firebase).** Series = `recordedAccountSeries(tracking.snapshots,
   tracking.activities, true)` from `portfolioAnalytics.js` (flow-adjusted, index-based daily
   NAV; already removes `BASKET_FLOW_TYPES` after `8eae175`). Convert to the shape
   `performanceMetrics`/`performanceStatistics` expect (dates + values) — `recordedAccountSeries`
   already returns `{ dates, values }`. Wire it in `buildAnalyticsModel` as
   `analyticsScope === 'recorded' ? recordedSeries : …`. `Portfolio.jsx` must pass
   `tracking.snapshots`/`tracking.activities` into `buildAnalyticsModel` (it already passes
   `rebalances`). Gate on `ledgerComplete` exactly as `portfolioReturnSummary` does; when not
   confirmed, show the same "Confirm the complete deposit and withdrawal history first" reason
   rather than a silently unadjusted series.
3. **Time-to-valid for the recorded scope** counts recorded market days, not published closes.
   `timeToValidMetric(observations, lastDate)` already takes a count — pass the recorded one.
4. **Sold holdings in "Why your portfolio moved today".** `PortfolioMoveExplanation` reads
   current positions and today's prices; nothing to change. Assert in its test that a closed
   ticker is absent.

**Tests:** `portfolioAnalyticsModel.test.js` — recorded scope uses snapshot values (fixture with
three daily snapshots and one `sale_proceeds` row: the sale day shows ~0% return, not the NAV
drop); `live_algorithm` scope unchanged; labels updated in `format.test.js` if one exists.

**Acceptance:** with the Recorded scope selected on Joshua's account after WP2/WP3/WP6, the
series' start date is the first recorded snapshot, Sep 3 does not register as a −N% day, and
the copy under the selector names which scope is synthetic.

---

## 6. Execution order and verification

```
WP1  → npm test -- src/pages/portfolio src/lib/referencePortfolio.test.js
WP4  → npm test -- scripts/ ; npm run portfolio:audit -- --email <you>      # expect findings A/B
WP3  → npm run portfolio:rebuild-ledger -- --email <you>  (dry run) → --commit
WP2  → confirm TSM share count → npm run portfolio:reconcile -- --email <you> --input fidelity-2026-09-04.json → --commit
WP4  → npm run portfolio:audit -- --email <you>                             # expect clean
WP5, WP6, WP7, WP8 → npm run lint && npm test && npm run build
```

Definition of done: audit clean on the live account; Summary Realized tile = **+$21.59**;
LULU and NTNX absent from holdings and present under "Sold"; TSM held; a bumped
`REFERENCE_PORTFOLIO_VERSION` on a non-empty account writes one snapshot doc and zero position
docs; all suites green.

---

## 7. Decisions already made by Joshua (2026-09-09)

1. **TSM share count** on the Sep 2 buy (cost $199.67, marked Margin) — **still needed**; read
   it from Fidelity → Positions before WP2 `--commit`. The script refuses to run without it.
2. **$400 EFT on Sep 1** — treat as a deposit. Whether it is the *only* external flow since
   tracking started is not yet confirmed; leave `ledgerComplete` untouched unless Joshua says so.
3. **Dividends: record them. Money-market lines (FZFXX, Fidelity Government MM): excluded.**
4. **NTNX: record both fills** (1 sh @ $67.86, 0.284 sh @ $19.26).
5. **Money-market cash stays out of tracked NAV** — unchanged rule.
