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
