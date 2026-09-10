export const PER_SHARE_COST = 'per_share'

// Number(null) is 0 and Number.isFinite(0) is true, so a bare Number.isFinite(Number(x)) reads
// an absent value as a real zero. That matters here: a brokerage export states quantity and
// cost but often no price and never a previous close, and those arrive as null. Treated as
// zero they became a $0.00 price and a zero previous close that silently disabled every day
// move -- the same guard the rest of the app uses (factorAnalytics, taxLots, portfolioAnalytics).
const finite = (value) =>
  value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))

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

/**
 * The most recent price this account has actually recorded for each ticker, from the
 * `intradaySnapshots` collection in Firestore.
 *
 * This is the account's own price record, and it is the reason a holding does not stay pinned
 * to whatever a brokerage export said on the morning it was seeded. Two writers fill that
 * collection and both store prices in the same shape: the app's own daily observation
 * (recordSnapshot in usePortfolioTracking.js) and a brokerage export applied as a dated
 * observation (referenceIntradaySnapshot in referencePortfolio.js). So updating the export
 * moves prices forward by adding an observation to this history, not by rewriting position
 * documents — which is what keeps the stored portfolio the record.
 *
 * Newest wins per ticker, judged by the observation's own timestamp rather than by document
 * order, since a later-applied export can carry an earlier date than a snapshot already taken.
 */
export function latestRecordedPrices(snapshots = []) {
  const latest = {}
  for (const snapshot of Array.isArray(snapshots) ? snapshots : []) {
    const recordedAt = snapshot?.recordedAt || null
    const time = Date.parse(recordedAt || '')
    if (!Array.isArray(snapshot?.prices) || !Number.isFinite(time)) continue
    for (const row of snapshot.prices) {
      const ticker = String(row?.ticker || '').trim().toUpperCase()
      if (!ticker || !finite(row?.price)) continue
      if (latest[ticker] && latest[ticker].time >= time) continue
      latest[ticker] = {
        ticker,
        time,
        recordedAt,
        price: Number(row.price),
        previousClose: finite(row.previousClose) ? Number(row.previousClose) : null,
        source: snapshot.source || null,
      }
    }
  }
  return latest
}

/**
 * Marks each holding at the account's own most recent recorded price, where that observation
 * is newer than the published research price it would otherwise use. A live quote refresh
 * still wins — it is newer than anything recorded — and so does a research price published
 * after the last observation.
 */
export function mergeRecordedPrices(priceData, recorded = {}, publishedAt = null) {
  const merged = { ...priceData }
  const publishedTime = Date.parse(publishedAt || '')
  for (const [ticker, observation] of Object.entries(recorded)) {
    const current = merged[ticker]
    if (current?.portfolioQuote) continue
    // A position-document snapshot is a seed value, so any recorded observation at least as
    // new as it replaces it. A published research price is only beaten by a newer observation.
    const incumbentTime = current?.positionSnapshot
      ? Date.parse(current.quoteMarketTime || '')
      : publishedTime
    if (finite(current?.price) && Number.isFinite(incumbentTime) && incumbentTime > observation.time) continue
    merged[ticker] = {
      ...(current || { ticker }),
      price: observation.price,
      previousClose: observation.previousClose
        ?? (finite(current?.previousClose) ? Number(current.previousClose) : null),
      positionSnapshot: false,
      recordedPrice: true,
      recordedAt: observation.recordedAt,
      quoteMarketTime: observation.recordedAt,
    }
  }
  return merged
}

/** The per-ticker price rows an account-value observation stores alongside its total. */
export function snapshotPriceRows(positions = [], recordedAt = new Date().toISOString()) {
  return positions
    .filter((row) => row?.ticker && finite(row?.currentPrice))
    .map((row) => ({
      ticker: String(row.ticker).trim().toUpperCase(),
      shares: finite(row.shares) ? Number(row.shares) : null,
      price: Number(row.currentPrice),
      value: finite(row.currentValue) ? Number(row.currentValue) : null,
      previousClose: finite(row.priceInfo?.previousClose) ? Number(row.priceInfo.previousClose) : null,
      marketTime: row.priceInfo?.quoteMarketTime || recordedAt,
    }))
}

/** Prefer a newer brokerage-export price while retaining the published history/metadata. */
export function mergePositionSnapshots(priceData, positions = [], publishedAt = null) {
  const merged = { ...priceData }
  const publishedTime = Date.parse(publishedAt || '')
  positions.forEach((position) => {
    const ticker = String(position?.ticker || '').trim().toUpperCase()
    const snapshotTime = Date.parse(position?.snapshotRecordedAt || '')
    if (!ticker || !finite(position?.snapshotPrice)) return
    const current = merged[ticker]
    const snapshotIsNewer = !Number.isFinite(publishedTime)
      || (Number.isFinite(snapshotTime) && snapshotTime >= publishedTime)
    if (current?.portfolioQuote || (finite(current?.price) && !snapshotIsNewer)) return
    merged[ticker] = {
      ...(current || { ticker }),
      price: Number(position.snapshotPrice),
      // Falls through to the row's own price history when the export carries no previous
      // close, which is the normal case: dailyMove derives one from published closes, but
      // only if this is genuinely absent rather than present-and-zero.
      previousClose: finite(position.snapshotPreviousClose)
        ? Number(position.snapshotPreviousClose)
        : finite(current?.previousClose) ? Number(current.previousClose) : null,
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
