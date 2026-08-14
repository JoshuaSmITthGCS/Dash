import { useId } from 'react'
import { dailyMoveForPosition } from '../lib/marketPresentation.js'

/**
 * Portfolio sector treemap.
 * Tile area is proportional to the user's current allocation and tile color
 * reflects the allocation-weighted daily return of the holdings in that sector.
 */

const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))

function squarify(items, x, y, width, height) {
  const total = items.reduce((sum, item) => sum + item.weight, 0)
  if (!total || !items.length) return []
  const rects = []
  let remaining = [...items]
  let cx = x, cy = y, cw = width, ch = height

  while (remaining.length) {
    const isWide = cw >= ch
    const side = isWide ? ch : cw
    const remainingTotal = remaining.reduce((sum, item) => sum + item.weight, 0)
    let row = []
    let rowTotal = 0
    let bestRatio = Infinity

    for (const item of remaining) {
      const testRow = [...row, item]
      const testTotal = rowTotal + item.weight
      const rowFraction = testTotal / remainingTotal
      const rowSize = rowFraction * (isWide ? cw : ch)
      const worst = testRow.reduce((max, rowItem) => {
        const size = (rowItem.weight / testTotal) * side
        const ratio = Math.max(rowSize / size, size / rowSize)
        return Math.max(max, ratio)
      }, 0)
      if (worst > bestRatio && row.length) break
      bestRatio = worst
      row = testRow
      rowTotal = testTotal
    }

    const rowFraction = rowTotal / remainingTotal
    const rowSize = rowFraction * (isWide ? cw : ch)
    let offset = 0

    for (const item of row) {
      const itemFraction = item.weight / rowTotal
      const itemSize = itemFraction * side
      if (isWide) {
        rects.push({ ...item, x: cx, y: cy + offset, w: rowSize, h: itemSize })
      } else {
        rects.push({ ...item, x: cx + offset, y: cy, w: itemSize, h: rowSize })
      }
      offset += itemSize
    }

    if (isWide) { cx += rowSize; cw -= rowSize }
    else { cy += rowSize; ch -= rowSize }
    remaining = remaining.slice(row.length)
  }

  return rects
}

export function buildPortfolioSectorHeatmap(positions = []) {
  const useCurrentValue = positions.some((position) => finite(position.currentValue) && Number(position.currentValue) > 0)
  const sectors = new Map()

  positions.forEach((position) => {
    const weightValue = useCurrentValue ? position.currentValue : position.allocationPct
    const weight = finite(weightValue) ? Number(weightValue) : 0
    if (weight <= 0) return

    const sector = position.priceInfo?.sector || position.sector || 'Unclassified'
    const current = sectors.get(sector) || {
      sector,
      weight: 0,
      weightedChange: 0,
      changeWeight: 0,
      holdings: [],
    }
    const change = dailyMoveForPosition(position).pct

    current.weight += weight
    current.holdings.push({ ticker: position.ticker, weight })
    if (finite(change)) {
      current.weightedChange += Number(change) * weight
      current.changeWeight += weight
    }
    sectors.set(sector, current)
  })

  const totalWeight = [...sectors.values()].reduce((sum, sector) => sum + sector.weight, 0)
  return [...sectors.values()]
    .map((sector) => ({
      sector: sector.sector,
      weight: sector.weight,
      allocationPct: totalWeight ? sector.weight / totalWeight * 100 : 0,
      avgChange: sector.changeWeight ? sector.weightedChange / sector.changeWeight : null,
      tickers: sector.holdings
        .sort((left, right) => right.weight - left.weight)
        .slice(0, 3)
        .map((holding) => holding.ticker),
    }))
    .sort((left, right) => right.weight - left.weight)
}

function toneForChange(change) {
  if (!finite(change) || Number(change) === 0) return 'neutral'
  return Number(change) > 0 ? 'positive' : 'negative'
}

function textColorForTone(tone) {
  if (tone === 'positive') return 'var(--pill-positive-ink)'
  if (tone === 'negative') return 'var(--pill-negative-ink)'
  return 'var(--text-primary)'
}

function signedChange(change) {
  if (!finite(change)) return 'Move unavailable'
  return `${Number(change) > 0 ? '+' : ''}${Number(change).toFixed(2)}%`
}

export default function MarketHeatmap({ positions = [] }) {
  const titleId = useId()
  const sectors = buildPortfolioSectorHeatmap(positions)
  if (!sectors.length) return null

  const W = 720
  const H = 340
  const rects = squarify(sectors, 0, 0, W, H)
  const summary = sectors
    .map((sector) => `${sector.sector} ${sector.allocationPct.toFixed(1)}% allocation, ${signedChange(sector.avgChange)}`)
    .join('; ')

  return (
    <section className="market-heatmap" aria-labelledby={titleId}>
      <header className="section-heading heatmap-heading">
        <div><span className="eyebrow">Your portfolio · Today</span><h2 id={titleId}>Sector heatmap</h2></div>
        <div className="heatmap-legend" aria-label="Heatmap legend">
          <span><i className="positive" aria-hidden="true" />Gain</span>
          <span><i className="negative" aria-hidden="true" />Loss</span>
          <small>Tile size = allocation</small>
        </div>
      </header>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
        aria-label={`Portfolio sector performance heatmap. ${summary}`} className="heatmap-svg">
        {rects.map((rect) => {
          const tone = toneForChange(rect.avgChange)
          const textColor = textColorForTone(tone)
          const label = `${rect.sector}: ${rect.allocationPct.toFixed(1)}% allocation, ${signedChange(rect.avgChange)}`
          const showLabel = rect.w > 50 && rect.h > 35
          return (
            <g key={rect.sector} data-sector={rect.sector} data-tone={tone} data-allocation-pct={rect.allocationPct.toFixed(1)}>
              <rect className={`heatmap-tile ${tone}`} x={rect.x + 1} y={rect.y + 1}
                width={Math.max(0, rect.w - 2)} height={Math.max(0, rect.h - 2)} rx="6" />
              {showLabel && <>
                <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 - 10}
                  textAnchor="middle" fill={textColor} fontSize="10" fontWeight="700" fontFamily="var(--font-display)">
                  {rect.sector.length > rect.w / 7 ? `${rect.sector.slice(0, Math.max(2, Math.floor(rect.w / 7)))}…` : rect.sector}
                </text>
                <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 + 5}
                  textAnchor="middle" fill={textColor} fontSize="9" fontWeight="700" fontFamily="var(--font-mono)">
                  {signedChange(rect.avgChange)}
                </text>
                {rect.h > 54 && (
                  <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 + 20}
                    textAnchor="middle" fill={textColor} fillOpacity=".82" fontSize="8" fontFamily="var(--font-mono)">
                    {rect.allocationPct.toFixed(1)}% allocated
                  </text>
                )}
                {rect.h > 78 && rect.w > 90 && (
                  <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 + 34}
                    textAnchor="middle" fill={textColor} fillOpacity=".7" fontSize="8" fontFamily="var(--font-mono)">
                    {rect.tickers.join(' · ')}
                  </text>
                )}
              </>}
              <title>{label}</title>
            </g>
          )
        })}
      </svg>
    </section>
  )
}
