/**
 * "Most undervalued" column sort: cheap relative to peers AND growing, blended into one
 * number so the whole list can be re-ordered by it directly - a plain column sort (see
 * COLUMN_SORTS in Picks.jsx), not a gated ranking model.
 *
 * Valuation reads the pipeline's own sector-relative percentile for stocks, or the fund's own
 * cost score for ETFs (a fund's closest analog to "cheap" - paying less expense ratio for the
 * same exposure) - both already 0-100 and peer-relative, higher meaning cheaper. Growth reads
 * published revenue growth when available (most rows don't have it -
 * only the fully published leaderboard does), and otherwise falls back to a peer-percentile
 * read of 12-1 price momentum for stocks or trailing 1-year return for ETFs - proxies for
 * "the market is pricing in growth here", ranked against the row's own pool since a raw
 * growth rate and a raw return aren't comparable to each other without ranking first.
 *
 * Stocks and ETFs are never pooled against each other for this, the same separation every
 * other score in this codebase keeps - see fundsAllocation.js and researchRating.js.
 */

const finite = (value) => typeof value === 'number' && Number.isFinite(value)
const MIN_POOL = 5

function valuationOf(row) {
  // A fund doesn't have a "cheap vs. peers" price the way a stock does; its cost score
  // (already 0-100, higher meaning a lower expense ratio) is the closest real analog - paying
  // less for the same exposure is its own kind of undervalued.
  if (row.is_etf) return finite(row.scores?.cost) ? row.scores.cost : null
  return finite(row.sector_valuation_percentile) ? row.sector_valuation_percentile : null
}

function rawGrowthOf(row) {
  if (row.is_etf) {
    return finite(row.technical_detail?.return_252d) ? row.technical_detail.return_252d : null
  }
  if (finite(row.revenue_growth)) return row.revenue_growth
  const momentum = row.technical_detail?.momentum_12_1_pct ?? row.technical_detail?.momentum_12_1
  return finite(momentum) ? momentum : null
}

function percentileRank(sortedAscending, value) {
  const below = sortedAscending.filter((entry) => entry < value).length
  const equal = sortedAscending.filter((entry) => entry === value).length
  return ((below + equal / 2) / sortedAscending.length) * 100
}

export function buildValueGrowthContext(rows) {
  const stockGrowth = []
  const etfGrowth = []
  for (const row of rows || []) {
    const growth = rawGrowthOf(row)
    if (finite(growth)) (row.is_etf ? etfGrowth : stockGrowth).push(growth)
  }
  return { stockGrowth: stockGrowth.sort((a, b) => a - b), etfGrowth: etfGrowth.sort((a, b) => a - b) }
}

/** 0-100, higher means more undervalued and more growth; null when neither leg resolves. */
export function valueGrowthScore(row, context) {
  if (!row || !context) return null
  const valuation = valuationOf(row)
  const rawGrowth = rawGrowthOf(row)
  const pool = row.is_etf ? context.etfGrowth : context.stockGrowth
  const growth = finite(rawGrowth) && pool.length >= MIN_POOL ? percentileRank(pool, rawGrowth) : null
  const parts = [valuation, growth].filter(finite)
  if (!parts.length) return null
  return parts.reduce((sum, value) => sum + value, 0) / parts.length
}
