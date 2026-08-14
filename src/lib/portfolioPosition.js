export const PER_SHARE_COST = 'per_share'

export function buildPortfolioPriceData(screenUniverse = [], portfolioCoverage = [], research = []) {
  return Object.fromEntries([...screenUniverse, ...portfolioCoverage, ...research]
    .filter((row) => row?.ticker && row.price != null)
    .map((row) => [String(row.ticker).trim().toUpperCase(), row]))
}

export function mergePortfolioQuotes(priceData, quotes = {}) {
  const merged = { ...priceData }
  for (const [ticker, quote] of Object.entries(quotes)) {
    if (!Number.isFinite(quote?.price)) continue
    merged[ticker] = {
      ...(merged[ticker] || { ticker }),
      name: merged[ticker]?.name || quote.name || ticker,
      price: quote.price,
      portfolioQuote: true,
      quoteMarketTime: quote.marketTime || null,
      previousClose: quote.previousClose ?? merged[ticker]?.previousClose ?? null,
    }
  }
  return merged
}

/** Prefer a newer brokerage-export price while retaining the published history/metadata. */
export function mergePositionSnapshots(priceData, positions = [], publishedAt = null) {
  const merged = { ...priceData }
  const publishedTime = Date.parse(publishedAt || '')
  positions.forEach((position) => {
    const ticker = String(position?.ticker || '').trim().toUpperCase()
    const snapshotTime = Date.parse(position?.snapshotRecordedAt || '')
    if (!ticker || !Number.isFinite(Number(position?.snapshotPrice))) return
    const current = merged[ticker]
    const snapshotIsNewer = !Number.isFinite(publishedTime)
      || (Number.isFinite(snapshotTime) && snapshotTime >= publishedTime)
    if (current?.portfolioQuote || (Number.isFinite(Number(current?.price)) && !snapshotIsNewer)) return
    merged[ticker] = {
      ...(current || { ticker }),
      price: Number(position.snapshotPrice),
      previousClose: Number.isFinite(Number(position.snapshotPreviousClose))
        ? Number(position.snapshotPreviousClose)
        : current?.previousClose ?? null,
      positionSnapshot: true,
      quoteMarketTime: position.snapshotRecordedAt || null,
    }
  })
  return merged
}

// These records were entered before the portfolio form distinguished total dollars from
// dollars per share. Their exact values make the intended total unambiguous: treating the
// entered amount as a per-share price produces the broken returns reported in the UI.
// Keep the match exact and narrow so unrelated legacy positions are never guessed at.
const LEGACY_TOTAL_COST_FIXES = [
  { ticker: 'EXPE', shares: 0.164, totalCost: 50 },
  { ticker: 'CRUS', shares: 1.344, totalCost: 175.67 },
  { ticker: 'VGT', shares: 1.692, totalCost: 200 },
]

const closeTo = (left, right) =>
  Number.isFinite(Number(left)) && Math.abs(Number(left) - right) < 0.00001

export function normalizePortfolioPosition(documentId, stored = {}) {
  const position = { ...stored, id: documentId }
  if (stored.costBasisUnit === PER_SHARE_COST) {
    return { position, firestoreUpdates: null }
  }

  const ticker = String(stored.ticker || '').trim().toUpperCase()
  const legacyFix = LEGACY_TOTAL_COST_FIXES.find((candidate) =>
    candidate.ticker === ticker
      && closeTo(stored.shares, candidate.shares)
      && closeTo(stored.costBasis, candidate.totalCost)
  )
  if (!legacyFix || Number(stored.shares) <= 0) {
    return { position, firestoreUpdates: null }
  }

  const firestoreUpdates = {
    costBasis: legacyFix.totalCost / Number(stored.shares),
    costBasisUnit: PER_SHARE_COST,
    costBasisInputMode: 'total',
  }
  return {
    position: { ...position, ...firestoreUpdates },
    firestoreUpdates,
  }
}
