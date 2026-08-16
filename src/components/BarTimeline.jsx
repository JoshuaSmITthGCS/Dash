import { useId, useRef, useState } from 'react'
import { useElementWidth } from '../lib/useElementWidth.js'

/**
 * One value per period, single series, bars anchored to zero. For a volume-style
 * timeline (congress trade dollars by month, say) rather than a continuous trend —
 * GrowthChart already covers the line-chart case. Table view one click away, same
 * pattern as CorrelationHeatmap/ScatterChart/PairedBarChart.
 */

const HEIGHT = 240
const PAD = { top: 16, right: 16, bottom: 30, left: 56 }
// Same reasoning as ScatterChart: past this many bars, individual tab stops turn
// "reach the rest of the page" into too many key presses. Table view covers keyboard
// access past this size; the chart stays mouse-hoverable at any size.
const KEYBOARD_FOCUS_LIMIT = 40

export default function BarTimeline({ points = [], yLabel, yFormatter = String, caption, className = '' }) {
  const [view, setView] = useState('chart')
  const [hover, setHover] = useState(null)
  const plotRef = useRef(null)
  const titleId = useId()
  const measuredWidth = useElementWidth(plotRef, null)
  const width = Math.max(320, measuredWidth ?? 640)

  const usable = points.filter((point) => Number.isFinite(point.value))
  if (!usable.length) return null

  const max = Math.max(0, ...usable.map((point) => point.value))
  const innerHeight = HEIGHT - PAD.top - PAD.bottom
  const innerWidth = width - PAD.left - PAD.right
  const barSlot = innerWidth / usable.length
  const barWidth = Math.max(4, barSlot * 0.6)
  const yTicks = [max, max / 2, 0]

  const keyboardFocusable = usable.length <= KEYBOARD_FOCUS_LIMIT
  const readout = hover
    ? `${hover.label}: ${yLabel} ${yFormatter(hover.value)}`
    : `${usable.length} period${usable.length === 1 ? '' : 's'}. ${keyboardFocusable
      ? 'Hover or tab to a bar for its value.'
      : 'Hover a bar for its value, or use the Table view to reach every period by keyboard.'}`

  return (
    <figure className={`correlation-figure ${className}`.trim()} aria-labelledby={titleId}>
      <figcaption className="correlation-head">
        <span id={titleId} className="sr-only">{yLabel} by period</span>
        <p className="correlation-readout" aria-live="polite">{readout}</p>
        <div className="correlation-toggle" role="group" aria-label="Chart view">
          <button type="button" aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Chart</button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</button>
        </div>
      </figcaption>

      {view === 'table' ? (
        <div className="correlation-table-wrap">
          <table className="correlation-table">
            <caption className="sr-only">{caption || yLabel}</caption>
            <thead><tr><th scope="col">Period</th><th scope="col">{yLabel}</th></tr></thead>
            <tbody>
              {usable.map((point) => (
                <tr key={point.id ?? point.label}><th scope="row">{point.label}</th><td className="num">{yFormatter(point.value)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-scroll-region" ref={plotRef}>
          <svg viewBox={`0 0 ${width} ${HEIGHT}`} width="100%" height={HEIGHT} className="chart-plot-svg"
            role="img" aria-label={`${yLabel} by period, ${usable.length} periods`}>
            {yTicks.map((tick, index) => {
              const y = PAD.top + innerHeight - (tick / (max || 1)) * innerHeight
              return (
                <g key={index}>
                  <line x1={PAD.left} x2={width - PAD.right} y1={y} y2={y} stroke="var(--border)" strokeWidth="1" />
                  <text x={PAD.left - 8} y={y + 4} textAnchor="end" fill="var(--text-faint)"
                    fontSize="11" fontFamily="var(--font-mono)">{yFormatter(tick)}</text>
                </g>
              )
            })}
            {usable.map((point, index) => {
              const barHeight = Math.max(1, (point.value / (max || 1)) * innerHeight)
              const x = PAD.left + index * barSlot + (barSlot - barWidth) / 2
              const y = PAD.top + innerHeight - barHeight
              const active = hover?.id === (point.id ?? point.label)
              return (
                <g key={point.id ?? point.label}
                  onMouseEnter={() => setHover({ ...point, id: point.id ?? point.label })}
                  onFocus={keyboardFocusable ? () => setHover({ ...point, id: point.id ?? point.label }) : undefined}
                  onMouseLeave={() => setHover(null)}
                  onBlur={keyboardFocusable ? () => setHover(null) : undefined}>
                  <rect x={x} y={y} width={barWidth} height={barHeight} rx="2"
                    fill="var(--series-stock)" opacity={active ? 1 : 0.9} tabIndex={keyboardFocusable ? '0' : undefined}>
                    <title>{point.label}: {yFormatter(point.value)}</title>
                  </rect>
                  {(usable.length <= 12 || index % Math.ceil(usable.length / 12) === 0) && (
                    <text x={x + barWidth / 2} y={HEIGHT - 12} textAnchor="middle" fill="var(--text-dim)"
                      fontSize="11" fontFamily="var(--font-mono)">{point.label}</text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>
      )}
    </figure>
  )
}
