/**
 * Treemap-style sector performance heatmap.
 * Rectangles sized by sector weight, colored by average daily change.
 */

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
      const worst = testRow.reduce((max, r) => {
        const size = (r.weight / testTotal) * side
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

function changeTone(change) {
  if (change == null) return 'var(--surface-tertiary)'
  const abs = Math.min(Math.abs(change), 3)
  const intensity = 0.2 + (abs / 3) * 0.6
  const base = change >= 0 ? 'var(--positive)' : 'var(--negative)'
  return `color-mix(in srgb, ${base} ${Math.round(intensity * 100)}%, var(--surface-tertiary))`
}

export default function MarketHeatmap({ rows = [] }) {
  const sectorMap = {}
  for (const row of rows) {
    const sector = row.sector || 'Unclassified'
    if (!sectorMap[sector]) sectorMap[sector] = { sector, totalChange: 0, count: 0, tickers: [] }
    sectorMap[sector].count += 1
    if (row.dayChange != null) sectorMap[sector].totalChange += row.dayChange
    if (sectorMap[sector].tickers.length < 3) sectorMap[sector].tickers.push(row.ticker)
  }

  const sectors = Object.values(sectorMap)
    .map((s) => ({ ...s, avgChange: s.count ? s.totalChange / s.count : 0, weight: s.count }))
    .sort((a, b) => b.weight - a.weight)

  if (!sectors.length) return null

  const W = 720
  const H = 340
  const rects = squarify(sectors, 0, 0, W, H)

  return (
    <section className="market-heatmap" aria-labelledby="heatmap-title">
      <header className="section-heading">
        <div><span className="eyebrow">Market view</span><h2 id="heatmap-title">Sector heatmap</h2></div>
      </header>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Sector performance heatmap" className="heatmap-svg">
        {rects.map((rect) => {
          const change = rect.avgChange
          const label = `${rect.sector}: ${change >= 0 ? '+' : ''}${change.toFixed(2)}%`
          const showLabel = rect.w > 50 && rect.h > 35
          return (
            <g key={rect.sector}>
              <rect x={rect.x + 1} y={rect.y + 1} width={Math.max(0, rect.w - 2)} height={Math.max(0, rect.h - 2)}
                rx="6" fill={changeTone(change)} />
              {showLabel && <>
                <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 - 6}
                  textAnchor="middle" fill="var(--text-primary)" fontSize="10" fontWeight="700" fontFamily="var(--font-display)">
                  {rect.sector.length > rect.w / 7 ? rect.sector.slice(0, Math.floor(rect.w / 7)) + '…' : rect.sector}
                </text>
                <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 + 8}
                  textAnchor="middle" fill="var(--text-secondary)" fontSize="9" fontFamily="var(--font-mono)">
                  {change >= 0 ? '+' : ''}{change.toFixed(2)}%
                </text>
                {rect.h > 55 && (
                  <text x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 + 22}
                    textAnchor="middle" fill="var(--text-tertiary)" fontSize="8" fontFamily="var(--font-mono)">
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
