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

function pathFor(points, stepped = false) {
  let path = ''
  let open = false
  for (const point of points) {
    if (!point) { open = false; continue }
    if (!open) path += `M${point.x.toFixed(1)} ${point.y.toFixed(1)} `
    else if (stepped) path += `H${point.x.toFixed(1)} V${point.y.toFixed(1)} `
    else path += `L${point.x.toFixed(1)} ${point.y.toFixed(1)} `
    open = true
  }
  return path.trim()
}

const money = (value) => `$${Math.round(value).toLocaleString('en-US')}`
const DAY_MS = 24 * 60 * 60 * 1000

// Calendar-day lookback windows rather than fixed point counts: the underlying grid mixes
// dense recent daily closes with sparser older weekly ones, so a point count can't mean the
// same span of time at both ends of the series.
const ZOOM_RANGES = [
  { key: 'all', label: 'All', days: null },
  { key: '1y', label: '1Y', days: 365 },
  { key: '6m', label: '6M', days: 182 },
  { key: '3m', label: '3M', days: 91 },
  { key: '1m', label: '1M', days: 30 },
  { key: '1w', label: '1W', days: 7 },
  { key: '5d', label: '5D', days: 5 },
  { key: '1d', label: '1D', days: 1 },
]

/** First index whose date falls within `days` of the series' last date. */
function cutoffIndex(dates, days) {
  if (days == null || !dates.length) return 0
  const last = new Date(`${dates[dates.length - 1]}T00:00:00Z`).getTime()
  const cutoff = last - days * DAY_MS
  const index = dates.findIndex((date) => new Date(`${date}T00:00:00Z`).getTime() >= cutoff)
  // Keep at least two points so a short range still draws a line rather than a single dot.
  return index < 0 ? dates.length - 1 : Math.min(index, dates.length - 2)
}

export default function GrowthChart({
  dates = [],
  series = [],
  height = 240,
  width = 720,
  title,
  caption,
  zoomable = false,
  valueFormatter = money,
  earningsMarker = null, // { value, label } – most recent earnings-surprise reading, if the pipeline has one
}) {
  const [zoom, setZoom] = useState('all')
  const [activeIndex, setActiveIndex] = useState(null)
  const availableLines = series.filter((line) =>
    Array.isArray(line.values) && line.values.some((value) => value != null))
  const fullDates = dates.length
    ? dates
    : availableLines[0]?.values.map((_, index) => String(index)) || []
  if (!availableLines.length || fullDates.length < 2) {
    return (
      <div className="card card-pad" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        No comparable price history yet – it appears after the next data refresh.
      </div>
    )
  }
  const selectedRange = ZOOM_RANGES.find((range) => range.key === zoom) || ZOOM_RANGES[0]
  const startIndex = cutoffIndex(fullDates, selectedRange.days)
  const usableDates = fullDates.slice(startIndex)
  const lines = availableLines.map((line) => ({
    ...line,
    values: line.values.slice(startIndex),
  }))
  const availableRanges = ZOOM_RANGES.filter((range) =>
    range.days == null || cutoffIndex(fullDates, range.days) > 0)

  const allValues = lines.flatMap((line) => line.values.filter((value) => value != null))
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const bounds = { min: min - (max - min) * 0.08 || 0, max: max + (max - min) * 0.08 }
  const ticks = [bounds.max, (bounds.max + bounds.min) / 2, bounds.min]
  const innerHeight = height - PAD.top - PAD.bottom
  const chartStyle = document.documentElement.dataset.chartStyle || 'line'

  const labelIndexes = [...new Set([0, Math.floor((usableDates.length - 1) / 2), usableDates.length - 1])]
  const chartSummary = `${title || 'Growth comparison chart'}. ${lines.map((line) => {
    const values = line.values.filter((value) => value != null)
    return `${line.label}: ${valueFormatter(values[values.length - 1])}`
  }).join('. ')} at the end of the period.`
  const selectPoint = (clientX, target) => {
    const bounds = target.getBoundingClientRect()
    const plotLeft = bounds.left + PAD.left / width * bounds.width
    const plotWidth = (width - PAD.left - PAD.right) / width * bounds.width
    const relative = Math.max(0, Math.min(1, (clientX - plotLeft) / plotWidth))
    setActiveIndex(Math.round(relative * (usableDates.length - 1)))
  }
  const activeX = activeIndex == null ? null : PAD.left + (activeIndex / (usableDates.length - 1)) * (width - PAD.left - PAD.right)
  const displayedIndex = activeIndex ?? usableDates.length - 1
  const changeZoom = (key) => {
    setZoom(key)
    setActiveIndex(null)
    if (navigator.vibrate && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) navigator.vibrate(8)
  }

  // The pipeline only has an aggregate "recent quarters, newest weighted heaviest" earnings-surprise
  // number, not a dated per-quarter actual-vs-estimate history – so this marks the latest point on
  // the primary line rather than pretending to know which past date the report landed on.
  const earningsPoint = earningsMarker?.value != null
    ? [...scalePoints(lines[0]?.values || [], usableDates, width, height, bounds)].reverse().find(Boolean)
    : null

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
                onClick={() => changeZoom(range.key)}
              >
                {range.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="chart-scrub-summary" role="status" aria-live="polite">
        <span>{String(usableDates[displayedIndex]).slice(0, 10)}</span>
        <div>{lines.map((line) => <strong key={line.label} style={{ color: line.color }}><small>Scrub: {line.label}</small>{line.values[displayedIndex] == null ? '–' : valueFormatter(line.values[displayedIndex])}</strong>)}</div>
      </div>
      <div className="chart-scroll-region" style={{ overflowX: 'auto' }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
          height={height}
          role="img"
          aria-label={chartSummary}
          tabIndex="0"
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture?.(event.pointerId)
            selectPoint(event.clientX, event.currentTarget)
          }}
          onPointerMove={(event) => selectPoint(event.clientX, event.currentTarget)}
          onPointerLeave={() => setActiveIndex(null)}
          onFocus={() => setActiveIndex((value) => value ?? usableDates.length - 1)}
          onBlur={() => setActiveIndex(null)}
          onKeyDown={(event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
            event.preventDefault()
            if (event.key === 'Home') setActiveIndex(0)
            else if (event.key === 'End') setActiveIndex(usableDates.length - 1)
            else setActiveIndex((value) => Math.max(0, Math.min(usableDates.length - 1, (value ?? usableDates.length - 1) + (event.key === 'ArrowRight' ? 1 : -1))))
          }}
          style={{ display: 'block', minWidth: 320, touchAction: 'pan-y' }}
        >
          {ticks.map((tick, index) => {
            const y = PAD.top + (index / (ticks.length - 1)) * innerHeight
            return (
              <g key={`${index}-${tick}`}>
                <line className="chart-grid-line" x1={PAD.left} x2={width - PAD.right} y1={y} y2={y}
                  stroke="var(--border)" strokeWidth="1" />
                <text x={PAD.left - 8} y={y + 4} textAnchor="end"
                  fill="var(--text-faint)" fontSize="10" fontFamily="var(--font-mono)">
                  {valueFormatter(tick)}
                </text>
              </g>
            )
          })}

          {lines.map((line) => {
            const points = scalePoints(line.values, usableDates, width, height, bounds)
            const last = [...points].reverse().find(Boolean)
            const connected = points.filter(Boolean)
            const areaPath = connected.length > 1 ? `${pathFor(points, chartStyle === 'step')} L${connected.at(-1).x.toFixed(1)} ${(height - PAD.bottom).toFixed(1)} L${connected[0].x.toFixed(1)} ${(height - PAD.bottom).toFixed(1)} Z` : ''
            return (
              <g key={line.label}>
                {chartStyle === 'area' && line.emphasis && <path className="chart-data-area" d={areaPath} fill={line.color} opacity=".1" />}
                <path className="chart-data-line" d={pathFor(points, chartStyle === 'step')} fill="none" stroke={line.color}
                  strokeWidth={line.emphasis ? 2.4 : 1.8}
                  strokeDasharray={line.dashPattern || (line.dashed ? '5 4' : undefined)}
                  strokeLinejoin="round" strokeLinecap="round" />
                {last && <circle cx={last.x} cy={last.y} r="3.5" fill={line.color} />}
              </g>
            )
          })}

          {earningsPoint && (
            <g>
              <circle cx={earningsPoint.x} cy={earningsPoint.y} r="7.5" fill="none"
                stroke={earningsMarker.value >= 0 ? 'var(--pos)' : 'var(--neg)'} strokeWidth="2" />
              <title>{earningsMarker.label}</title>
            </g>
          )}

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
          {activeIndex != null && <g className="chart-tooltip">
            <line x1={activeX} x2={activeX} y1={PAD.top} y2={height - PAD.bottom} stroke="var(--text-faint)" strokeDasharray="3 3" />
            <rect x={Math.max(PAD.left, Math.min(width - 174, activeX - 76))} y={8} width="160" height={22 + lines.length * 17} rx="8" fill="var(--surface-primary)" stroke="var(--border-strong)" />
            <text x={Math.max(PAD.left + 8, Math.min(width - 166, activeX - 68))} y="24" fill="var(--text-primary)" fontSize="10" fontFamily="var(--font-mono)">{String(usableDates[activeIndex]).slice(0, 10)}</text>
            {lines.map((line, index) => <text key={line.label} x={Math.max(PAD.left + 8, Math.min(width - 166, activeX - 68))} y={41 + index * 17} fill={line.color} fontSize="10" fontFamily="var(--font-mono)">{line.label}: {line.values[activeIndex] == null ? '–' : valueFormatter(line.values[activeIndex])}</text>)}
          </g>}
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
              <span className="mono" style={{ fontWeight: 600 }}>{valueFormatter(latest)}</span>
            </div>
          )
        })}
      </div>
      {earningsMarker?.value != null && (
        <p style={{ marginTop: 4, fontSize: 12, color: earningsMarker.value >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
          ○ {earningsMarker.label}
        </p>
      )}
      {caption && (
        <p style={{ marginTop: 8, fontSize: 12, color: 'var(--text-faint)' }}>{caption}</p>
      )}
    </figure>
  )
}
