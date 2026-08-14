// Authoritative invested-positions snapshot exported from Fidelity on Aug 14, 2026 at
// 2:29 p.m. ET. FZFXX (held in money market) and Pending activity are deliberately absent:
// Dash tracks only invested holdings and their price movement.
export const REFERENCE_PORTFOLIO_VERSION = 'fidelity-positions-2026-08-14-1429-et'
export const REFERENCE_PORTFOLIO_RECORDED_AT = '2026-08-14T18:29:00.000Z'

export const REFERENCE_PORTFOLIO = [
  ['ACGL', 1.009, 99.96, 98.8, 99.68, 98.03],
  ['ACN', 0.36, 50.0, 176.63, 63.58, 178.49],
  ['ADBE', 0.23, 49.93, 265.19, 60.99, 270.49],
  ['AGO', 0.595, 49.96, 76.38, 45.44, 76.17],
  ['AMAT', 0.087, 49.57, 504.45, 43.88, 534.54],
  ['BAC', 0.82, 49.95, 64.495, 52.88, 64.09],
  ['BSX', 1.466, 99.97, 52.155, 76.45, 51.69],
  ['CCK', 0.834, 99.96, 119.58, 99.72, 118.37],
  ['CI', 0.351, 99.86, 281.65, 98.85, 277.99],
  ['COP', 0.411, 49.95, 127.08, 52.22, 124.52],
  ['CRUS', 1.344, 174.97, 120.77, 162.31, 121.22],
  ['DECK', 0.995, 99.92, 93.64, 93.17, 93.3],
  ['DINO', 1.165, 99.99, 93.04, 108.39, 91.87],
  ['DXCM', 0.965, 79.93, 89.72, 86.57, 91.48],
  ['EOG', 1.368, 199.95, 143.5245, 196.34, 141.41],
  ['EXPE', 0.164, 49.95, 331.74, 54.4, 328.31],
  ['FTDR', 0.539, 49.95, 86.79, 46.77, 84.66],
  ['GMED', 1.239, 99.96, 85.78, 106.28, 85.94],
  ['HIG', 1.394, 199.97, 138.37, 192.88, 137.81],
  ['INTU', 1.055, 299.99, 346.54, 365.59, 358.29],
  ['LULU', 1.0, 117.94, 119.7841, 119.78, 119.56],
  ['MCY', 1.842, 199.93, 105.105, 193.6, 104.92],
  ['META', 0.327, 199.81, 591.24, 193.33, 594.97],
  ['MGY', 3.818, 99.98, 26.315, 100.47, 25.86],
  ['MSFT', 0.098, 37.97, 495.51, 48.55, 496.88],
  ['MU', 0.101, 99.3, 961.325, 97.09, 949.83],
  ['NEM', 0.891, 99.99, 118.06, 105.19, 114.19],
  ['NTNX', 1.284, 49.99, 66.62, 85.54, 67.95],
  ['NUE', 0.183, 49.83, 270.345, 49.47, 272.29],
  ['OXY', 0.854, 49.95, 58.625, 50.06, 57.7],
  ['QCOM', 1.164, 199.99, 164.445, 191.41, 164.79],
  ['RNR', 0.31, 99.8, 323.525, 100.29, 319.86],
  ['SCHW', 1.961, 199.98, 110.91, 217.49, 109.74],
  ['SIGI', 2.075, 199.92, 94.375, 195.82, 93.89],
  ['SYF', 1.243, 99.95, 80.735, 100.35, 80.08],
  ['THG', 0.87, 199.88, 223.91, 194.8, 223.19],
  ['TRV', 0.539, 199.66, 370.84, 199.88, 370.0],
  ['VGT', 1.692, 199.97, 122.265, 206.87, 122.99],
  ['VOO', 0.146, 92.47, 713.225, 104.13, 714.95],
].map(([ticker, shares, costBasisTotal, snapshotPrice, snapshotValue, snapshotPreviousClose]) => ({
  ticker,
  shares,
  costBasis: costBasisTotal / shares,
  costBasisTotal,
  costBasisUnit: 'per_share',
  costBasisInputMode: 'total',
  snapshotPrice,
  snapshotValue,
  snapshotPreviousClose,
  snapshotRecordedAt: REFERENCE_PORTFOLIO_RECORDED_AT,
  snapshotSource: 'Fidelity positions export · Aug 14, 2026',
}))

/**
 * Reconciles the cloud holdings to the brokerage export. This import is intentionally
 * authoritative: quantities and exact total cost bases are refreshed, missing positions are
 * added, and holdings absent from the export are removed.
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
