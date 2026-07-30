import { useState } from 'react'

/**
 * Dollar-value comparison line chart, drawn as inline SVG.
 *
 * It supports both a fixed starting investment and dated contributions. No chart library,
 * so it inherits the page's theme tokens and works in both light and dark without a second
 * implementation.
 */

const PAD = { top: 16, right: 14, bottom: 26, left: 52 }

function scalePoints(series, dates, width, height, bounds) {
  const { min, max } = bounds
  const span = max - min || 1
  const innerWidth = width - PAD.left - PAD.right
  const innerHeight = height - PAD.top - PAD.bottom
  const step = dates.length > 1 ? innerWidth / (dates.length - 1) : 0
  return series.map((value, index) => (value == null ? null : {
    x: PAD.left + index * step,
    y: PAD.top + innerHeight - ((value - min) / span) * innerHeight,
    value,
    date: dates[index],
  }))
}

function pathFor(points) {
  let path = ''
  let open = false
  for (const point of points) {
    if (!point) { open = false; continue }
    path += `${open ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)} `
    open = true
  }
  return path.trim()
}

const money = (value) => `$${Math.round(value).toLocaleString('en-US')}`
const ZOOM_RANGES = [
  { key: 'all', label: 'All', points: null },
  { key: '1y', label: '1Y', points: 53 },
  { key: '6m', label: '6M', points: 27 },
  { key: '3m', label: '3M', points: 14 },
  { key: '1m', label: '1M', points: 6 },
]

export default function GrowthChart({
  dates = [],
  series = [],
  height = 240,
  width = 720,
  title,
  caption,
  zoomable = false,
}) {
  const [zoom, setZoom] = useState('all')
  const availableLines = series.filter((line) =>
    Array.isArray(line.values) && line.values.some((value) => value != null))
  const fullDates = dates.length
    ? dates
    : availableLines[0]?.values.map((_, index) => String(index)) || []
  if (!availableLines.length || fullDates.length < 2) {
    return (
      <div className="card card-pad" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        No comparable price history yet — it appears after the next data refresh.
      </div>
    )
  }
  const selectedRange = ZOOM_RANGES.find((range) => range.key === zoom) || ZOOM_RANGES[0]
  const startIndex = selectedRange.points
    ? Math.max(0, fullDates.length - selectedRange.points)
    : 0
  const usableDates = fullDates.slice(startIndex)
  const lines = availableLines.map((line) => ({
    ...line,
    values: line.values.slice(startIndex),
  }))
  const availableRanges = ZOOM_RANGES.filter((range) =>
    range.points == null || range.points < fullDates.length)

  const allValues = lines.flatMap((line) => line.values.filter((value) => value != null))
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const bounds = { min: min - (max - min) * 0.08 || 0, max: max + (max - min) * 0.08 }
  const ticks = [bounds.max, (bounds.max + bounds.min) / 2, bounds.min]
  const innerHeight = height - PAD.top - PAD.bottom

  const labelIndexes = [0, Math.floor((usableDates.length - 1) / 2), usableDates.length - 1]
  const chartSummary = `${title || 'Growth comparison chart'}. ${lines.map((line) => {
    const values = line.values.filter((value) => value != null)
    return `${line.label}: ${money(values[values.length - 1])}`
  }).join('; ')} at the end of the period.`

  return (
    <figure style={{ margin: 0 }}>
      <div className="chart-heading">
        {title && <figcaption>{title}</figcaption>}
        {zoomable && availableRanges.length > 1 && (
          <div className="chart-zoom" aria-label="Chart time range">
            {availableRanges.map((range) => (
              <button
                key={range.key}
                className={zoom === range.key ? 'active' : ''}
                aria-pressed={zoom === range.key}
                onClick={() => setZoom(range.key)}
              >
                {range.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div style={{ overflowX: 'auto' }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label={chartSummary}
          style={{ display: 'block', minWidth: 320 }}
        >
          {ticks.map((tick, index) => {
            const y = PAD.top + (index / (ticks.length - 1)) * innerHeight
            return (
              <g key={tick}>
                <line x1={PAD.left} x2={width - PAD.right} y1={y} y2={y}
                  stroke="var(--border)" strokeWidth="1" />
                <text x={PAD.left - 8} y={y + 4} textAnchor="end"
                  fill="var(--text-faint)" fontSize="10" fontFamily="var(--font-mono)">
                  {money(tick)}
                </text>
              </g>
            )
          })}

          {lines.map((line) => {
            const points = scalePoints(line.values, usableDates, width, height, bounds)
            const last = [...points].reverse().find(Boolean)
            return (
              <g key={line.label}>
                <path d={pathFor(points)} fill="none" stroke={line.color}
                  strokeWidth={line.emphasis ? 2.4 : 1.8}
                  strokeDasharray={line.dashPattern || (line.dashed ? '5 4' : undefined)}
                  strokeLinejoin="round" strokeLinecap="round" />
                {last && <circle cx={last.x} cy={last.y} r="3.5" fill={line.color} />}
              </g>
            )
          })}

          {labelIndexes.map((index) => {
            const step = (width - PAD.left - PAD.right) / (usableDates.length - 1)
            const x = PAD.left + index * step
            return (
              <text key={index} x={x} y={height - 8}
                textAnchor={index === 0 ? 'start' : index === usableDates.length - 1 ? 'end' : 'middle'}
                fill="var(--text-faint)" fontSize="10" fontFamily="var(--font-mono)">
                {String(usableDates[index]).slice(0, 10)}
              </text>
            )
          })}
        </svg>
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 10 }}>
        {lines.map((line) => {
          const values = line.values.filter((value) => value != null)
          const latest = values[values.length - 1]
          return (
            <div key={line.label} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12 }}>
              <span style={{
                width: 16, height: 0, borderTop: `3px ${line.dashPattern ? 'dashed' : 'solid'} ${line.color}`,
                opacity: line.dashPattern || line.dashed ? 0.85 : 1,
              }} />
              <span style={{ color: 'var(--text-dim)' }}>{line.label}</span>
              <span className="mono" style={{ fontWeight: 600 }}>{money(latest)}</span>
            </div>
          )
        })}
      </div>
      {caption && (
        <p style={{ marginTop: 8, fontSize: 12, color: 'var(--text-faint)' }}>{caption}</p>
      )}
    </figure>
  )
}
