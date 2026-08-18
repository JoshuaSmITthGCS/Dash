/**
 * Score Bands (Tier System)
 *
 * Replaces exact 1-20 rankings with score band tiers.
 * More honest: stocks within same tier are roughly equivalent,
 * exact rank order implies false precision.
 *
 * Tier A: Top 4 stocks (80-100th percentile)
 * Tier B: Next 4 stocks (60-80th percentile)
 * Tier C: Next 4 stocks (40-60th percentile)
 * Tier D: Next 4 stocks (20-40th percentile)
 * Tier E: Bottom 4 stocks (0-20th percentile)
 */

export const SCORE_BANDS = {
  A: {
    label: 'Tier A',
    shortLabel: 'A',
    description: 'Top tier - strongest fundamentals',
    color: '#0a6f53',
    bgColor: '#e2f5ec',
    minPercentile: 80,
    maxPercentile: 100,
    icon: '🟢'
  },
  B: {
    label: 'Tier B',
    shortLabel: 'B',
    description: 'Strong - above average quality',
    color: '#2b6cc4',
    bgColor: '#e3edf7',
    minPercentile: 60,
    maxPercentile: 80,
    icon: '🔵'
  },
  C: {
    label: 'Tier C',
    shortLabel: 'C',
    description: 'Average - mixed signals',
    color: '#8a5f0e',
    bgColor: '#fdf2d8',
    minPercentile: 40,
    maxPercentile: 60,
    icon: '🟡'
  },
  D: {
    label: 'Tier D',
    shortLabel: 'D',
    description: 'Below average - caution warranted',
    color: '#c25a12',
    bgColor: '#fef0e6',
    minPercentile: 20,
    maxPercentile: 40,
    icon: '🟠'
  },
  E: {
    label: 'Tier E',
    shortLabel: 'E',
    description: 'Weakest - significant concerns',
    color: '#b83c37',
    bgColor: '#fbeae9',
    minPercentile: 0,
    maxPercentile: 20,
    icon: '🔴'
  }
}

/**
 * Calculate score band from percentile
 */
export function getScoreBand(percentile) {
  if (percentile >= 80) return SCORE_BANDS.A
  if (percentile >= 60) return SCORE_BANDS.B
  if (percentile >= 40) return SCORE_BANDS.C
  if (percentile >= 20) return SCORE_BANDS.D
  return SCORE_BANDS.E
}

/**
 * Calculate score band from rank (1-20)
 * Assumes 20 stocks total in ranked list
 */
export function getScoreBandFromRank(rank, totalStocks = 20) {
  if (rank < 1 || rank > totalStocks) return SCORE_BANDS.E

  // Convert rank to percentile (rank 1 = 100th percentile)
  const percentile = ((totalStocks - rank + 1) / totalStocks) * 100

  return getScoreBand(percentile)
}

/**
 * Group stocks by score band
 * Returns { A: [...], B: [...], C: [...], D: [...], E: [...] }
 */
export function groupByScoreBand(stocks, totalStocks = 20) {
  const groups = {
    A: [],
    B: [],
    C: [],
    D: [],
    E: []
  }

  stocks.forEach((stock, index) => {
    const rank = index + 1
    const band = getScoreBandFromRank(rank, totalStocks)
    groups[band.shortLabel].push({ ...stock, rank, band })
  })

  return groups
}

/**
 * Get band statistics
 */
export function getBandStats(stocks) {
  const groups = groupByScoreBand(stocks, stocks.length)

  return Object.entries(groups).map(([tier, stocksInTier]) => ({
    tier,
    band: SCORE_BANDS[tier],
    count: stocksInTier.length,
    avgScore: stocksInTier.length > 0
      ? stocksInTier.reduce((sum, s) => sum + (s.score || 0), 0) / stocksInTier.length
      : 0,
    stocks: stocksInTier
  }))
}

/**
 * Format band label with rank range
 * Example: "Tier A (Ranks 1-4)"
 */
export function formatBandLabel(band, totalStocks = 20) {
  const stocksPerTier = Math.floor(totalStocks / 5)
  const tierIndex = ['A', 'B', 'C', 'D', 'E'].indexOf(band.shortLabel)
  const startRank = tierIndex * stocksPerTier + 1
  const endRank = startRank + stocksPerTier - 1

  return `${band.label} (Ranks ${startRank}-${endRank})`
}

/**
 * Get disclaimer text for score bands
 */
export function getScoreBandDisclaimer() {
  return {
    title: 'About Score Bands',
    points: [
      'Stocks are grouped into tiers (A-E) instead of exact rankings',
      'Stocks within the same tier are roughly equivalent in quality',
      'Exact rank order implies false precision - small score differences are not meaningful',
      'Tier A does not mean "guaranteed winner" - all stocks carry risk',
      'Use tiers as a starting point for research, not as buy/sell signals'
    ]
  }
}
