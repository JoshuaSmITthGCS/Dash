export const PORTFOLIO_SORT_OPTIONS = [
  { key: 'ticker', label: 'Ticker' },
  { key: 'company', label: 'Company' },
  { key: 'signal', label: 'Signal' },
  { key: 'value', label: 'Position value' },
  { key: 'gain', label: 'Gain/loss ($)' },
  { key: 'return', label: 'Total return (%)' },
  { key: 'score', label: 'Research score' },
  { key: 'trend', label: '1-month trend' },
  { key: 'shares', label: 'Share count' },
  { key: 'cost', label: 'Average cost' },
  { key: 'price', label: 'Current price' },
  { key: 'purchaseDate', label: 'Purchase date' },
  { key: 'invested', label: 'Amount invested' },
  { key: 'spValue', label: 'S&P instead ($)' },
  { key: 'spReturn', label: 'S&P return (%)' },
  { key: 'dollarsAhead', label: 'Dollars ahead of S&P' },
  { key: 'hypNow', label: '$ calculator: value now' },
  { key: 'hypReturn', label: '$ calculator: return (%)' },
  { key: 'hypSpValue', label: '$ calculator: S&P instead' },
  { key: 'hypSpReturn', label: '$ calculator: S&P return (%)' },
  { key: 'hypDollarsAhead', label: '$ calculator: dollars ahead' },
]

const VALUE_FOR = {
  ticker: (position) => position.ticker,
  company: (position) => position.priceInfo?.name,
  signal: (position) => ({
    HOLD: 0,
    WATCH: 1,
    TRIM: 2,
    SELL: 3,
  })[position.recommendation?.action],
  value: (position) => position.currentValue,
  gain: (position) => position.gain,
  return: (position) => position.gainPct,
  score: (position) => position.priceInfo?.score,
  trend: (position) => position.trendPct,
  shares: (position) => position.shares,
  cost: (position) => position.costBasis,
  price: (position) => position.currentPrice,
  purchaseDate: (position) => position.purchaseDate,
  invested: (position) => position.totalCost,
  spValue: (position) => position.versusBenchmark?.value,
  spReturn: (position) => position.versusBenchmark?.gainPct,
  dollarsAhead: (position) => (
    position.versusBenchmark ? position.currentValue - position.versusBenchmark.value : null
  ),
  hypNow: (position) => position.hypothetical?.stockValue,
  hypReturn: (position) => position.hypothetical?.stockReturnPct,
  hypSpValue: (position) => position.hypothetical?.benchmarkValue,
  hypSpReturn: (position) => position.hypothetical?.benchmarkReturnPct,
  hypDollarsAhead: (position) => position.hypothetical?.dollarsAhead,
}

export function sortPortfolioPositions(positions, key, direction = 'asc') {
  const valueFor = VALUE_FOR[key] || VALUE_FOR.ticker
  const multiplier = direction === 'desc' ? -1 : 1

  return positions
    .map((position, index) => ({ position, index }))
    .sort((left, right) => {
      const a = valueFor(left.position)
      const b = valueFor(right.position)
      const aMissing = a == null || a === '' || (typeof a === 'number' && !Number.isFinite(a))
      const bMissing = b == null || b === '' || (typeof b === 'number' && !Number.isFinite(b))
      if (aMissing !== bMissing) return aMissing ? 1 : -1
      if (aMissing) return left.index - right.index

      const comparison = typeof a === 'string' || typeof b === 'string'
        ? String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' })
        : Number(a) - Number(b)
      return comparison === 0 ? left.index - right.index : comparison * multiplier
    })
    .map(({ position }) => position)
}

export function nextPortfolioSort(current, key) {
  if (current.key === key) {
    return { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
  }
  const descendingByDefault = !['ticker', 'company', 'purchaseDate'].includes(key)
  return { key, direction: descendingByDefault ? 'desc' : 'asc' }
}
