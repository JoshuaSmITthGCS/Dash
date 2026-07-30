// User-provided brokerage snapshot. Prices are intentionally tagged as snapshots, never live quotes.
export const REFERENCE_PORTFOLIO = [
  ['SCHW', 1.961, 101.98, 104.47], ['QCOM', 1.164, 171.81, 155.68],
  ['OXY', 0.854, 58.49, 56.03], ['MU', 0.101, 983.00, 983.00],
  ['MSFT', 0.098, 387.45, 390.54], ['META', 0.327, 611.04, 585.61],
  ['INTU', 1.055, 284.35, 333.13], ['EOG', 1.368, 146.16, 145.94],
  ['DECJ', 0.995, 100.42, 100.42], ['COP', 0.411, 121.53, 118.06],
  ['CI', 0.351, 284.50, 296.47], ['BAC', 0.82, 60.91, 61.07],
  ['AMAT', 0.087, 569.77, 569.77], ['AGO', 0.595, 83.97, 83.97],
  ['ADBE', 0.23, 217.09, 263.43], ['ACN', 0.36, 138.89, 173.17],
  ['NTNX', 1.284, 38.93, 38.93], ['BSX', 1.466, 68.19, 46.04],
  ['VOO', 0.146, 633.36, 633.36],
].map(([ticker, shares, costBasis, snapshotPrice]) => ({
  ticker, shares, costBasis, snapshotPrice, snapshotSource: 'User-provided brokerage snapshot',
}))

export function planReferencePortfolioSync(positions, reference = REFERENCE_PORTFOLIO) {
  const normalizeTicker = (ticker = '') => String(ticker).trim().toUpperCase()
  const existingByTicker = new Map(
    positions.map((position) => [normalizeTicker(position.ticker), position])
  )

  return reference.map((snapshot) => {
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
        ticker,
        snapshotPrice: snapshot.snapshotPrice,
        snapshotSource: snapshot.snapshotSource,
      },
    }
  })
}
