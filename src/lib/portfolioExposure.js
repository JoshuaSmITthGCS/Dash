/**
 * Concentration checks: how much of the portfolio rides on one position or one sector.
 * A stock's own thesis and your entry price can both be fine while the portfolio as a
 * whole is still one bad quarter away from a large, correlated loss.
 */

const DEFAULTS = {
  maxPositionPct: 25, // guideline ceiling for a single ticker's share of portfolio value
  maxSectorPct: 35, // guideline ceiling for a single sector's share of portfolio value
}

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

export function assessPortfolioExposure(positions, thresholds = {}) {
  const { maxPositionPct, maxSectorPct } = { ...DEFAULTS, ...thresholds }
  const priced = (positions || []).filter((pos) => finite(pos.currentValue) && pos.currentValue > 0)
  const totalValue = priced.reduce((sum, pos) => sum + pos.currentValue, 0)

  if (!totalValue) {
    return { totalValue: 0, positions: [], sectors: [], warnings: [], maxPositionPct, maxSectorPct }
  }

  const positionExposure = priced
    .map((pos) => ({ ticker: pos.ticker, value: pos.currentValue, pct: (pos.currentValue / totalValue) * 100 }))
    .sort((left, right) => right.pct - left.pct)

  const sectorTotals = new Map()
  for (const pos of priced) {
    const sector = pos.priceInfo?.sector || 'Unclassified'
    sectorTotals.set(sector, (sectorTotals.get(sector) || 0) + pos.currentValue)
  }
  const sectorExposure = [...sectorTotals.entries()]
    .map(([sector, value]) => ({ sector, value, pct: (value / totalValue) * 100 }))
    .sort((left, right) => right.pct - left.pct)

  const warnings = [
    ...positionExposure
      .filter((position) => position.pct > maxPositionPct)
      .map((position) => ({
        type: 'position',
        label: position.ticker,
        pct: position.pct,
        message: `${position.ticker} is ${position.pct.toFixed(1)}% of your portfolio, above the ${maxPositionPct}% single-position guideline`,
      })),
    ...sectorExposure
      .filter((sector) => sector.pct > maxSectorPct)
      .map((sector) => ({
        type: 'sector',
        label: sector.sector,
        pct: sector.pct,
        message: `${sector.sector} is ${sector.pct.toFixed(1)}% of your portfolio, above the ${maxSectorPct}% sector-concentration guideline`,
      })),
  ].sort((left, right) => right.pct - left.pct)

  return { totalValue, positions: positionExposure, sectors: sectorExposure, warnings, maxPositionPct, maxSectorPct }
}
