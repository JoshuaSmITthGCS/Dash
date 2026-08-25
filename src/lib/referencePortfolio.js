// Authoritative invested-positions snapshot exported from Fidelity (account Z32641125) on
// Aug 25, 2026 at 7:55 a.m. ET, with acquisition dates taken from the account's transaction
// history. FZFXX (held in money market) and Pending activity are deliberately absent: Dash
// tracks only invested holdings and their price movement.
//
// Two different documents, two different facts, and they must not be confused:
//
//   - The POSITIONS EXPORT gives quantity, total cost and current value. Its date (below,
//     in REFERENCE_PORTFOLIO_RECORDED_AT) is when those prices were observed. It says
//     nothing about when anything was bought and must never be written to a purchaseDate.
//   - The TRANSACTION HISTORY gives the acquisition date, which is the only source for
//     purchaseDate here. Where a holding was accumulated over several same-day buys, that
//     shared trade date is the date recorded.
//
// The two reconcile exactly: summing each ticker's buys in the history reproduces the
// export's total cost basis to the cent for 44 of the 46 holdings. The exceptions are BSX
// and VOO, both bought before the supplied history window begins -- they stay undated rather
// than guessed at, which costs since-purchase coverage on those two and nothing else.
//
// This replaces the Aug 14 baseline, which held 39 positions. The seven it did not have --
// AMP, AMZN, DELL, ETN, MPC, THC and TWLO -- were not lost from it: the history shows all
// seven bought on Aug 21, a week after that snapshot was taken, for exactly the $999.26 by
// which the two exports' cost bases differ. The 39 common tickers carry identical share
// counts and cost bases across both.
//
// Totals reconcile against the export: 46 invested positions, $5,549.26 total cost,
// $5,668.16 market value, which with the $2.68 FZFXX money-market line is the $5,670.84
// account total Fidelity displays.
export const REFERENCE_PORTFOLIO_VERSION = 'fidelity-positions-2026-08-25-0755-et-dated'

// Figures read straight off the Fidelity account summary, kept separate from the rows below
// on purpose: verifyReferencePortfolio() checks the rows against these, so editing a holding
// without updating the brokerage totals it came from fails loudly instead of silently
// producing a portfolio that no longer matches the statement it claims to reproduce.
export const REFERENCE_PORTFOLIO_EXPECTED = {
  positionCount: 46,
  costBasisTotal: 5549.26,
  marketValue: 5668.16,
  moneyMarketValue: 2.68, // FZFXX -- held, but never a tracked holding
  accountTotal: 5670.84,
  undatedTickers: ['BSX', 'VOO'], // bought before the supplied transaction history begins
}
export const REFERENCE_PORTFOLIO_RECORDED_AT = '2026-08-25T11:55:00.000Z'

// [ticker, shares, total cost basis, last price, market value, acquisition date]. The
// export's positions view carries no previous close, so snapshotPreviousClose is null here
// rather than guessed at -- every consumer treats it as an optional fallback behind the live
// quote feed. Prices are the exported value divided by the exported quantity, which
// reproduces both the displayed "Last" column and the displayed value to the cent. The
// trailing date comes from the transaction history, never from the export; null means the
// buy predates the supplied history.
export const REFERENCE_PORTFOLIO = [
  ['ACGL', 1.009, 99.96, 101.1397, 102.05, '2026-08-05'],
  ['ACN', 0.36, 50.00, 186.5278, 67.15, '2026-07-23'],
  ['ADBE', 0.23, 49.93, 276.2609, 63.54, '2026-07-23'],
  ['AGO', 0.595, 49.96, 74.1849, 44.14, '2026-07-23'],
  ['AMAT', 0.087, 49.57, 484.1379, 42.12, '2026-07-23'],
  ['AMP', 0.179, 99.74, 561.1173, 100.44, '2026-08-21'],
  ['AMZN', 0.386, 99.79, 262.0725, 101.16, '2026-08-21'],
  ['BAC', 0.82, 49.95, 62.3293, 51.11, '2026-07-23'],
  ['BSX', 1.466, 99.97, 49.0041, 71.84, null],
  ['CCK', 0.834, 99.96, 119.7482, 99.87, '2026-08-04'],
  ['CI', 0.351, 99.86, 280.4274, 98.43, '2026-07-23'],
  ['COP', 0.411, 49.95, 133.3333, 54.80, '2026-07-23'],
  ['CRUS', 1.344, 174.97, 111.6369, 150.04, '2026-08-04'],
  ['DECK', 0.995, 99.92, 92.0704, 91.61, '2026-07-23'],
  ['DELL', 0.228, 100.00, 433.2018, 98.77, '2026-08-21'],
  ['DINO', 1.165, 99.99, 95.176, 110.88, '2026-08-05'],
  ['DXCM', 0.965, 79.93, 91.057, 87.87, '2026-07-31'],
  ['EOG', 1.368, 199.95, 150.2047, 205.48, '2026-07-23'],
  ['ETN', 0.475, 199.98, 408.6526, 194.11, '2026-08-21'],
  ['EXPE', 0.164, 49.95, 339.0854, 55.61, '2026-08-04'],
  ['FTDR', 0.539, 49.95, 82.7458, 44.60, '2026-08-07'],
  ['GMED', 1.239, 99.96, 84.0759, 104.17, '2026-08-05'],
  ['HIG', 1.394, 199.97, 138.9742, 193.73, '2026-08-07'],
  ['INTU', 1.055, 299.99, 369.9147, 390.26, '2026-07-23'],
  ['LULU', 1, 117.94, 122.78, 122.78, '2026-07-30'],
  ['MCY', 1.842, 199.93, 106.2758, 195.76, '2026-08-07'],
  ['META', 0.327, 199.81, 558.9908, 182.79, '2026-07-23'],
  ['MGY', 3.818, 99.98, 27.2184, 103.92, '2026-08-14'],
  ['MPC', 0.276, 99.90, 362.5, 100.05, '2026-08-21'],
  ['MSFT', 0.098, 37.97, 487.2449, 47.75, '2026-07-23'],
  ['MU', 0.101, 99.30, 910.396, 91.95, '2026-07-23'],
  ['NEM', 0.891, 99.99, 131.8294, 117.46, '2026-08-07'],
  ['NTNX', 1.284, 49.99, 66.6745, 85.61, '2026-03-12'],
  ['NUE', 0.183, 49.83, 244.5902, 44.76, '2026-08-07'],
  ['OXY', 0.854, 49.95, 60.1054, 51.33, '2026-07-23'],
  ['QCOM', 1.164, 199.99, 158.5223, 184.52, '2026-07-23'],
  ['RNR', 0.31, 99.80, 329.4194, 102.12, '2026-08-14'],
  ['SCHW', 1.961, 199.98, 113.6461, 222.86, '2026-07-23'],
  ['SIGI', 2.075, 199.92, 92.6458, 192.24, '2026-08-07'],
  ['SYF', 1.243, 99.95, 80.0161, 99.46, '2026-08-14'],
  ['THC', 0.719, 199.96, 278.5814, 200.30, '2026-08-21'],
  ['THG', 0.87, 199.88, 227.4598, 197.89, '2026-08-07'],
  ['TRV', 0.539, 199.66, 370.538, 199.72, '2026-08-14'],
  ['TWLO', 0.906, 199.89, 222.5828, 201.66, '2026-08-21'],
  ['VGT', 1.692, 199.97, 116.4184, 196.98, '2026-08-04'],
  ['VOO', 0.146, 92.47, 701.8493, 102.47, null],
].map(([ticker, shares, costBasisTotal, snapshotPrice, snapshotValue, purchaseDate]) => ({
  ticker,
  shares,
  costBasis: costBasisTotal / shares,
  costBasisTotal,
  costBasisUnit: 'per_share',
  costBasisInputMode: 'total',
  snapshotPrice,
  snapshotValue,
  snapshotPreviousClose: null,
  snapshotRecordedAt: REFERENCE_PORTFOLIO_RECORDED_AT,
  snapshotSource: 'Fidelity export price · Aug 25, 2026',
  purchaseDate,
}))

/**
 * Reconciles the cloud holdings to the brokerage export. This import is intentionally
 * authoritative: quantities and exact total cost bases are refreshed, missing positions are
 * added, and holdings absent from the export are removed.
 *
 * purchaseDate is the exception to that, in both directions. It is never taken from the
 * export date, only from the transaction history carried on each reference row; and a date
 * already stored on a holding always wins, so a correction made in the Edit sheet or the
 * Purchased column survives every later sync. An empty stored date is backfilled from the
 * history, which is what puts real acquisition dates on holdings imported before those dates
 * were known. A holding the history does not reach stays undated rather than dated wrongly.
 */
export function planReferencePortfolioSync(positions, reference = REFERENCE_PORTFOLIO) {
  const normalizeTicker = (ticker = '') => String(ticker).trim().toUpperCase()
  const existingByTicker = new Map(
    positions.map((position) => [normalizeTicker(position.ticker), position])
  )
  const referenceTickers = new Set(reference.map((position) => normalizeTicker(position.ticker)))

  const upserts = reference.map((snapshot) => {
    const ticker = normalizeTicker(snapshot.ticker)
    const existing = existingByTicker.get(ticker)
    if (!existing) {
      return {
        kind: 'add',
        id: `${ticker}-reference`,
        record: { ...snapshot, ticker, purchaseDate: snapshot.purchaseDate || '' },
      }
    }

    return {
      kind: 'update',
      id: existing.id,
      previous: existing,
      record: {
        ...existing,
        ...snapshot,
        ticker,
        purchaseDate: existing.purchaseDate || snapshot.purchaseDate || '',
      },
    }
  })
  const removals = positions
    .filter((position) => !referenceTickers.has(normalizeTicker(position.ticker)))
    .map((position) => ({ kind: 'remove', id: position.id, record: position }))

  return [...upserts, ...removals]
}

/**
 * The exact document body to write for one planned operation. Shared so the in-app sync and
 * the `sync-portfolio-firebase` CLI shape identical records -- the two run against the same
 * collection, and a field only one of them sets is a divergence that surfaces as a portfolio
 * that looks different depending on which path last touched it.
 *
 * purchaseDate arrives already resolved by planReferencePortfolioSync and is passed through
 * untouched: blanking it here would discard every acquisition date the history knows.
 */
export function referenceSyncRecord(operation, importedAt) {
  return operation.kind === 'add'
    ? { ...operation.record, id: operation.id, importedAt }
    : { ...operation.record, syncedAt: importedAt }
}

/**
 * The invested-only intraday observation this export represents, as a document id and body.
 * Money-market cash and pending activity are already absent from REFERENCE_PORTFOLIO, so the
 * value here is invested holdings alone.
 */
export function referenceIntradaySnapshot(reference = REFERENCE_PORTFOLIO) {
  const investedValue = reference.reduce((sum, position) => sum + position.snapshotValue, 0)
  return {
    id: REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 16).replace(/[:.]/g, '-'),
    document: {
      value: investedValue,
      investedValue,
      coveragePct: 100,
      source: 'fidelity_positions_export',
      recordedAt: REFERENCE_PORTFOLIO_RECORDED_AT,
      marketDate: REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 10),
      positionCount: reference.length,
      prices: reference.map((position) => ({
        ticker: position.ticker,
        shares: position.shares,
        price: position.snapshotPrice,
        value: position.snapshotValue,
        previousClose: position.snapshotPreviousClose,
        marketTime: REFERENCE_PORTFOLIO_RECORDED_AT,
      })),
    },
  }
}

/** Marks which export an account has been reconciled to, so the sync runs once per version. */
export function referenceTrackingState(importedAt) {
  return {
    referencePortfolioVersion: REFERENCE_PORTFOLIO_VERSION,
    referencePortfolioImportedAt: importedAt,
  }
}

/** added/updated/removed counts for a plan, as both callers report them. */
export function summarizeReferenceSync(operations) {
  return {
    added: operations.filter((operation) => operation.kind === 'add').length,
    updated: operations.filter((operation) => operation.kind === 'update').length,
    removed: operations.filter((operation) => operation.kind === 'remove').length,
  }
}

// The stored fields that carry meaning for a holding. A sync that changes none of them is a
// no-op on that row, which is what lets a report say whether an account is already in sync
// rather than just how many documents the write would touch.
const TRACKED_FIELDS = [
  'shares', 'costBasis', 'costBasisTotal', 'purchaseDate', 'snapshotPrice', 'snapshotValue',
]

const sameValue = (left, right) => {
  if (typeof left === 'number' && typeof right === 'number') return Math.abs(left - right) < 1e-9
  return (left ?? '') === (right ?? '')
}

/**
 * What an update would actually change, field by field. Returns [] for a row the sync would
 * rewrite identically -- an operation list alone cannot distinguish that from a real edit,
 * because the planner emits an update for every held ticker.
 */
export function referenceSyncDrift(operation) {
  if (operation.kind !== 'update' || !operation.previous) return []
  // An empty string and a missing field both mean "no value stored" -- an undated holding is
  // written as '' but read back as undefined on a document that predates the field. Reporting
  // them as one null keeps a report from showing a change where nothing actually differs.
  const reported = (value) => (value === undefined || value === '' ? null : value)
  return TRACKED_FIELDS
    .filter((field) => !sameValue(operation.previous[field], operation.record[field]))
    .map((field) => ({ field, from: reported(operation.previous[field]), to: reported(operation.record[field]) }))
}

const round = (value) => Math.round(value * 100) / 100

/**
 * Checks the shipped rows against the brokerage figures they were transcribed from, and
 * against the internal invariants the rest of the app relies on. Every check states what it
 * compared, so a failing report says which number disagreed with which source rather than
 * only that something is wrong.
 */
export function verifyReferencePortfolio(
  reference = REFERENCE_PORTFOLIO,
  expected = REFERENCE_PORTFOLIO_EXPECTED,
) {
  const cost = round(reference.reduce((sum, position) => sum + position.costBasisTotal, 0))
  const value = round(reference.reduce((sum, position) => sum + position.snapshotValue, 0))
  const exportDay = REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 10)
  const tickers = reference.map((position) => position.ticker)
  const undated = reference.filter((position) => !position.purchaseDate).map((position) => position.ticker)

  const mispriced = reference.filter((position) =>
    Math.abs(position.snapshotPrice * position.shares - position.snapshotValue) >= 0.005)
  const misCosted = reference.filter((position) =>
    Math.abs(position.costBasis * position.shares - position.costBasisTotal) >= 1e-6)
  const badDates = reference.filter((position) => position.purchaseDate
    && !(/^\d{4}-\d{2}-\d{2}$/.test(position.purchaseDate) && position.purchaseDate < exportDay))

  const check = (name, ok, detail) => ({ name, ok, detail })
  return [
    check('Holdings match the brokerage position count', reference.length === expected.positionCount,
      `${reference.length} rows vs ${expected.positionCount} reported`),
    check('Total cost basis matches the account summary', cost === expected.costBasisTotal,
      `$${cost.toFixed(2)} vs $${expected.costBasisTotal.toFixed(2)} reported`),
    check('Market value matches the account summary', value === expected.marketValue,
      `$${value.toFixed(2)} vs $${expected.marketValue.toFixed(2)} reported`),
    check('Value plus money market reconciles to the account total',
      round(expected.marketValue + expected.moneyMarketValue) === expected.accountTotal,
      `$${expected.marketValue.toFixed(2)} + $${expected.moneyMarketValue.toFixed(2)} = $${expected.accountTotal.toFixed(2)}`),
    check('Every price reproduces its exported value', mispriced.length === 0,
      mispriced.length ? `off by a cent or more: ${mispriced.map((row) => row.ticker).join(', ')}` : 'shares x price = value on all rows'),
    check('Every cost basis reproduces its exported total', misCosted.length === 0,
      misCosted.length ? `inconsistent: ${misCosted.map((row) => row.ticker).join(', ')}` : 'shares x cost/share = total cost on all rows'),
    check('No money-market or pending line is tracked as a holding',
      !tickers.some((ticker) => ['FZFXX', 'SPAXX', 'Pending activity'].includes(ticker)),
      'invested holdings only'),
    check('No ticker appears twice', new Set(tickers).size === tickers.length,
      `${new Set(tickers).size} distinct of ${tickers.length}`),
    check('No purchase date is taken from the export date', badDates.length === 0,
      badDates.length ? `suspect: ${badDates.map((row) => row.ticker).join(', ')}` : `all buys precede ${exportDay}`),
    check('Only the expected holdings are undated',
      undated.join(',') === expected.undatedTickers.join(','),
      undated.length ? `${undated.join(', ')} (no buy in the supplied history)` : 'every holding dated'),
  ]
}
