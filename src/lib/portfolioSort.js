export const PORTFOLIO_SORT_OPTIONS = [
  { key: 'ticker', label: 'Ticker' },
  { key: 'company', label: 'Company' },
  { key: 'value', label: 'Position value' },
  { key: 'gain', label: 'Gain/loss ($)' },
  { key: 'return', label: 'Total return (%)' },
  { key: 'score', label: 'Research score' },
  { key: 'trend', label: '1-month trend' },
  { key: 'shares', label: 'Share count' },
  { key: 'cost', label: 'Average cost' },
  { key: 'price', label: 'Current price' },
  { key: 'purchaseDate', label: 'Purchase date' },
]

const VALUE_FOR = {
  ticker: (position) => position.ticker,
  company: (position) => position.priceInfo?.name,
  value: (position) => position.currentValue,
  gain: (position) => position.gain,
  return: (position) => position.gainPct,
  score: (position) => position.priceInfo?.score,
  trend: (position) => position.trendPct,
  shares: (position) => position.shares,
  cost: (position) => position.costBasis,
  price: (position) => position.currentPrice,
  purchaseDate: (position) => position.purchaseDate,
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
