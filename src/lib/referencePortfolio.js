// Authoritative invested-positions snapshot exported from Fidelity (account Z32641125) on
// Aug 25, 2026 at 7:55 a.m. ET. FZFXX (held in money market) and Pending activity are
// deliberately absent: Dash tracks only invested holdings and their price movement.
//
// The export date is when these prices were observed. It is NOT when anything was bought,
// and must never be written to a position's purchaseDate: Fidelity's positions view reports
// what is held now, not when it was acquired. planReferencePortfolioSync below therefore
// adds holdings with an empty purchaseDate and preserves any date already on an existing
// holding, and the date this file carries lives only in snapshotRecordedAt (a price
// timestamp). Every since-purchase measure -- money-weighted return, versus-benchmark since
// purchase, holding-period risk, trader insights -- excludes an undated holding rather than
// substituting this date, so an undated lot costs coverage but never reports a wrong number.
// Real buy dates are entered per holding from the Purchased column or the Edit sheet.
//
// This export replaces the Aug 14 baseline, which had lost seven holdings -- AMP, AMZN,
// DELL, ETN, MPC, THC and TWLO, together exactly $999.26 of cost basis. The 39 tickers
// carried over from Aug 14 have identical share counts and cost bases here, so the only
// difference between the two exports is those seven positions plus repriced values.
//
// Totals reconcile against the export: 46 invested positions, $5,549.26 total cost,
// $5,668.16 market value, which with the $2.68 FZFXX money-market line is the $5,670.84
// account total Fidelity displays.
export const REFERENCE_PORTFOLIO_VERSION = 'fidelity-positions-2026-08-25-0755-et'
export const REFERENCE_PORTFOLIO_RECORDED_AT = '2026-08-25T11:55:00.000Z'

// [ticker, shares, total cost basis, last price, market value]. The export's positions view
// carries no previous close, so snapshotPreviousClose is null here rather than guessed at --
// every consumer treats it as an optional fallback behind the live quote feed. Prices are
// the exported value divided by the exported quantity, which reproduces both the displayed
// "Last" column and the displayed value to the cent.
export const REFERENCE_PORTFOLIO = [
  ['ACGL', 1.009, 99.96, 101.1397, 102.05],
  ['ACN', 0.36, 50.00, 186.5278, 67.15],
  ['ADBE', 0.23, 49.93, 276.2609, 63.54],
  ['AGO', 0.595, 49.96, 74.1849, 44.14],
  ['AMAT', 0.087, 49.57, 484.1379, 42.12],
  ['AMP', 0.179, 99.74, 561.1173, 100.44],
  ['AMZN', 0.386, 99.79, 262.0725, 101.16],
  ['BAC', 0.82, 49.95, 62.3293, 51.11],
  ['BSX', 1.466, 99.97, 49.0041, 71.84],
  ['CCK', 0.834, 99.96, 119.7482, 99.87],
  ['CI', 0.351, 99.86, 280.4274, 98.43],
  ['COP', 0.411, 49.95, 133.3333, 54.80],
  ['CRUS', 1.344, 174.97, 111.6369, 150.04],
  ['DECK', 0.995, 99.92, 92.0704, 91.61],
  ['DELL', 0.228, 100.00, 433.2018, 98.77],
  ['DINO', 1.165, 99.99, 95.176, 110.88],
  ['DXCM', 0.965, 79.93, 91.057, 87.87],
  ['EOG', 1.368, 199.95, 150.2047, 205.48],
  ['ETN', 0.475, 199.98, 408.6526, 194.11],
  ['EXPE', 0.164, 49.95, 339.0854, 55.61],
  ['FTDR', 0.539, 49.95, 82.7458, 44.60],
  ['GMED', 1.239, 99.96, 84.0759, 104.17],
  ['HIG', 1.394, 199.97, 138.9742, 193.73],
  ['INTU', 1.055, 299.99, 369.9147, 390.26],
  ['LULU', 1, 117.94, 122.78, 122.78],
  ['MCY', 1.842, 199.93, 106.2758, 195.76],
  ['META', 0.327, 199.81, 558.9908, 182.79],
  ['MGY', 3.818, 99.98, 27.2184, 103.92],
  ['MPC', 0.276, 99.90, 362.5, 100.05],
  ['MSFT', 0.098, 37.97, 487.2449, 47.75],
  ['MU', 0.101, 99.30, 910.396, 91.95],
  ['NEM', 0.891, 99.99, 131.8294, 117.46],
  ['NTNX', 1.284, 49.99, 66.6745, 85.61],
  ['NUE', 0.183, 49.83, 244.5902, 44.76],
  ['OXY', 0.854, 49.95, 60.1054, 51.33],
  ['QCOM', 1.164, 199.99, 158.5223, 184.52],
  ['RNR', 0.31, 99.80, 329.4194, 102.12],
  ['SCHW', 1.961, 199.98, 113.6461, 222.86],
  ['SIGI', 2.075, 199.92, 92.6458, 192.24],
  ['SYF', 1.243, 99.95, 80.0161, 99.46],
  ['THC', 0.719, 199.96, 278.5814, 200.30],
  ['THG', 0.87, 199.88, 227.4598, 197.89],
  ['TRV', 0.539, 199.66, 370.538, 199.72],
  ['TWLO', 0.906, 199.89, 222.5828, 201.66],
  ['VGT', 1.692, 199.97, 116.4184, 196.98],
  ['VOO', 0.146, 92.47, 701.8493, 102.47],
].map(([ticker, shares, costBasisTotal, snapshotPrice, snapshotValue]) => ({
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
}))

/**
 * Reconciles the cloud holdings to the brokerage export. This import is intentionally
 * authoritative: quantities and exact total cost bases are refreshed, missing positions are
 * added, and holdings absent from the export are removed.
 *
 * purchaseDate is the one field the export cannot speak to and so is never taken from it --
 * an added holding starts undated and an existing holding keeps whatever date it already
 * had, even though every other field is overwritten.
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
        record: { ...snapshot, ticker },
      }
    }

    return {
      kind: 'update',
      id: existing.id,
      record: {
        ...existing,
        ...snapshot,
        ticker,
        purchaseDate: existing.purchaseDate || '',
      },
    }
  })
  const removals = positions
    .filter((position) => !referenceTickers.has(normalizeTicker(position.ticker)))
    .map((position) => ({ kind: 'remove', id: position.id, record: position }))

  return [...upserts, ...removals]
}
