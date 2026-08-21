// Authoritative invested-positions snapshot exported from Fidelity on Aug 21, 2026 at
// 2:50 p.m. ET. FZFXX (held in money market) and Pending activity are deliberately absent:
// Dash tracks only invested holdings and their price movement.
export const REFERENCE_PORTFOLIO_VERSION = 'fidelity-positions-2026-08-21-1450-et'
export const REFERENCE_PORTFOLIO_RECORDED_AT = '2026-08-21T18:50:00.000Z'

export const REFERENCE_PORTFOLIO = [
  ['ACGL', 1.009, 99.96, 99.7919, 100.69, 99.3062],
  ['ACN', 0.36, 50.0, 183.75, 66.15, 181.3611],
  ['ADBE', 0.23, 49.93, 273.6522, 62.94, 272.2174],
  ['AGO', 0.595, 49.96, 74.3529, 44.24, 74.2689],
  ['AMAT', 0.087, 49.57, 491.0345, 42.72, 496.2069],
  ['AMP', 0.179, 99.74, 556.8156, 99.67, 557.2067],
  ['AMZN', 0.386, 99.79, 258.9119, 99.94, 258.5233],
  ['BAC', 0.82, 49.95, 61.8171, 50.69, 61.8659],
  ['BSX', 1.466, 99.97, 50.4161, 73.91, 49.3724],
  ['CCK', 0.834, 99.96, 119.5444, 99.7, 117.1463],
  ['CI', 0.351, 99.86, 277.5783, 97.43, 274.3875],
  ['COP', 0.411, 49.95, 135.1338, 55.54, 134.8905],
  ['CRUS', 1.344, 174.97, 114.747, 154.22, 116.8973],
  ['DECK', 0.995, 99.92, 91.4573, 91.0, 88.8543],
  ['DELL', 0.228, 100.0, 439.2105, 100.14, 438.5965],
  ['DINO', 1.165, 99.99, 96.9785, 112.98, 92.721],
  ['DXCM', 0.965, 79.93, 91.6891, 88.48, 90.2176],
  ['EOG', 1.368, 199.95, 152.7193, 208.92, 152.1857],
  ['ETN', 0.475, 199.98, 421.6211, 200.27, 421.0105],
  ['EXPE', 0.164, 49.95, 322.6829, 52.92, 324.1463],
  ['FTDR', 0.539, 49.95, 82.2078, 44.31, 81.9295],
  ['GMED', 1.239, 99.96, 86.5133, 107.19, 85.6659],
  ['HIG', 1.394, 199.97, 136.5925, 190.41, 137.1234],
  ['INTU', 1.055, 299.99, 365.763, 385.88, 361.8768],
  ['LULU', 1.0, 117.94, 120.54, 120.54, 115.69],
  ['MCY', 1.842, 199.93, 105.798, 194.88, 103.8708],
  ['META', 0.327, 199.81, 550.0306, 179.86, 545.841],
  ['MGY', 3.818, 99.98, 28.1037, 107.3, 28.219],
  ['MPC', 0.276, 99.9, 362.8623, 100.15, 361.9565],
  ['MSFT', 0.098, 37.97, 482.449, 47.28, 481.1224],
  ['MU', 0.101, 99.3, 969.2079, 97.89, 974.3564],
  ['NEM', 0.891, 99.99, 131.5937, 117.25, 127.6431],
  ['NTNX', 1.284, 49.99, 67.243, 86.34, 66.3318],
  ['NUE', 0.183, 49.83, 242.2404, 44.33, 240.4372],
  ['OXY', 0.854, 49.95, 61.4871, 52.51, 61.5222],
  ['QCOM', 1.164, 199.99, 160.6701, 187.02, 160.7388],
  ['RNR', 0.31, 99.8, 323.4516, 100.27, 322.129],
  ['SCHW', 1.961, 199.98, 111.7389, 219.12, 109.7909],
  ['SIGI', 2.075, 199.92, 91.8795, 190.65, 90.8096],
  ['SYF', 1.243, 99.95, 79.2679, 98.53, 76.7096],
  ['THC', 0.719, 199.96, 278.6509, 200.35, 278.1085],
  ['THG', 0.87, 199.88, 223.7011, 194.62, 223.1034],
  ['TRV', 0.539, 199.66, 364.397, 196.41, 364.4898],
  ['TWLO', 0.906, 199.89, 222.1744, 201.29, 220.6291],
  ['VGT', 1.692, 199.97, 118.3333, 200.22, 118.357],
  ['VOO', 0.146, 92.47, 703.9726, 102.78, 701.0274],
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
  snapshotSource: 'Fidelity positions export · Aug 21, 2026',
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
