import { useId, useRef, useState } from 'react'
import { useElementWidth } from '../lib/useElementWidth.js'

/**
 * Two measures plotted against each other, one point per entity.
 *
 * Same SVG/token/useElementWidth conventions as GrowthChart. Points carry an
 * optional `tone` (one of TONE_VAR's keys) for categorical color — omit it for
 * a single-series plot, which needs no legend (the title names the one series).
 * A quadrant reference cross (median or a fixed threshold on each axis) is
 * optional and purely descriptive; it never gates which points are eligible.
 *
 * Table view is one click away, same pattern as CorrelationHeatmap.
 */

const HEIGHT = 320
const PAD = { top: 16, right: 20, bottom: 34, left: 52 }
// Beyond this many points, making every circle its own tab stop turns "reach the rest
// of the page" into dozens or hundreds of key presses. The Table view — always one
// click away — is the keyboard-accessible enumeration past this size; the chart stays
// mouse-hoverable at any size.
const KEYBOARD_FOCUS_LIMIT = 40
const TONE_VAR = {
  high: '--tier-high', watch: '--tier-watch', neutral: '--tier-neutral', cool: '--tier-cool',
}

const identity = (value) => String(value)

export default function ScatterChart({
  points = [],
  xLabel,
  yLabel,
  xFormatter = identity,
  yFormatter = identity,
  quadrant = null,
  legend = null,
  caption,
  className = '',
}) {
  const [view, setView] = useState('chart')
  const [hover, setHover] = useState(null)
  const plotRef = useRef(null)
  const titleId = useId()
  const measuredWidth = useElementWidth(plotRef, null)
  const width = Math.max(280, measuredWidth ?? 640)

  const usable = points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
  if (!usable.length) return null

  const xs = usable.map((point) => point.x)
  const ys = usable.map((point) => point.y)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)
  const xSpan = xMax - xMin || 1
  const ySpan = yMax - yMin || 1
  const xPad = xSpan * 0.1
  const yPad = ySpan * 0.1
  const bounds = { xMin: xMin - xPad, xMax: xMax + xPad, yMin: yMin - yPad, yMax: yMax + yPad }

  const plotX = (value) => PAD.left + ((value - bounds.xMin) / (bounds.xMax - bounds.xMin || 1)) * (width - PAD.left - PAD.right)
  const plotY = (value) => HEIGHT - PAD.bottom - ((value - bounds.yMin) / (bounds.yMax - bounds.yMin || 1)) * (HEIGHT - PAD.top - PAD.bottom)

  const xTicks = [bounds.xMin, (bounds.xMin + bounds.xMax) / 2, bounds.xMax]
  const yTicks = [bounds.yMax, (bounds.yMax + bounds.yMin) / 2, bounds.yMin]

  const keyboardFocusable = usable.length <= KEYBOARD_FOCUS_LIMIT
  const readout = hover
    ? `${hover.label}: ${xLabel} ${xFormatter(hover.x)}, ${yLabel} ${yFormatter(hover.y)}`
    : `${usable.length} point${usable.length === 1 ? '' : 's'}. ${keyboardFocusable
      ? 'Hover or tab to a point for its values.'
      : 'Hover a point for its values, or use the Table view to reach every point by keyboard.'}`

  return (
    <figure className={`correlation-figure ${className}`.trim()} aria-labelledby={titleId}>
      <figcaption className="correlation-head">
        <span id={titleId} className="sr-only">{xLabel} versus {yLabel}, {usable.length} points</span>
        <p className="correlation-readout" aria-live="polite">{readout}</p>
        <div className="correlation-toggle" role="group" aria-label="Chart view">
          <button type="button" aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Chart</button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</button>
        </div>
      </figcaption>

      {view === 'table' ? (
        <div className="correlation-table-wrap">
          <table className="correlation-table">
            <caption className="sr-only">{caption || `${xLabel} versus ${yLabel}`}</caption>
            <thead><tr><th scope="col">Name</th><th scope="col" className="num">{xLabel}</th><th scope="col" className="num">{yLabel}</th></tr></thead>
            <tbody>
              {usable.map((point) => (
                <tr key={point.id ?? point.label}>
                  <th scope="row">{point.label}</th>
                  <td className="mono num">{xFormatter(point.x)}</td>
                  <td className="mono num">{yFormatter(point.y)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-scroll-region" ref={plotRef}>
          <svg viewBox={`0 0 ${width} ${HEIGHT}`} width="100%" height={HEIGHT} className="chart-plot-svg"
            role="img" aria-label={`${xLabel} versus ${yLabel} scatter, ${usable.length} points`}>
            {xTicks.map((tick, index) => (
              <text key={`x-${index}`} x={plotX(tick)} y={HEIGHT - PAD.bottom + 18} textAnchor="middle"
                fill="var(--text-faint)" fontSize="11" fontFamily="var(--font-mono)">{xFormatter(tick)}</text>
            ))}
            {yTicks.map((tick, index) => (
              <g key={`y-${index}`}>
                <line x1={PAD.left} x2={width - PAD.right} y1={plotY(tick)} y2={plotY(tick)} stroke="var(--border)" strokeWidth="1" />
                <text x={PAD.left - 8} y={plotY(tick) + 4} textAnchor="end" fill="var(--text-faint)"
                  fontSize="11" fontFamily="var(--font-mono)">{yFormatter(tick)}</text>
              </g>
            ))}
            <text x={(PAD.left + width - PAD.right) / 2} y={HEIGHT - 4} textAnchor="middle"
              fill="var(--text-dim)" fontSize="11" fontFamily="var(--font-mono)">{xLabel}</text>

            {quadrant && Number.isFinite(quadrant.x) && (
              <line x1={plotX(quadrant.x)} x2={plotX(quadrant.x)} y1={PAD.top} y2={HEIGHT - PAD.bottom}
                stroke="var(--border-strong)" strokeDasharray="3 3" />
            )}
            {quadrant && Number.isFinite(quadrant.y) && (
              <line x1={PAD.left} x2={width - PAD.right} y1={plotY(quadrant.y)} y2={plotY(quadrant.y)}
                stroke="var(--border-strong)" strokeDasharray="3 3" />
            )}

            {usable.map((point) => {
              const color = point.tone ? `var(${TONE_VAR[point.tone] || '--text-dim'})` : 'var(--series-stock)'
              const active = hover?.id === (point.id ?? point.label)
              return (
                <circle
                  key={point.id ?? point.label}
                  cx={plotX(point.x)} cy={plotY(point.y)} r={active ? 6 : 4.5}
                  fill={color} stroke="var(--surface-primary)" strokeWidth="1.5"
                  tabIndex={keyboardFocusable ? '0' : undefined}
                  onMouseEnter={() => setHover({ ...point, id: point.id ?? point.label })}
                  onFocus={keyboardFocusable ? () => setHover({ ...point, id: point.id ?? point.label }) : undefined}
                  onMouseLeave={() => setHover(null)}
                  onBlur={keyboardFocusable ? () => setHover(null) : undefined}
                >
                  <title>{point.label}: {xLabel} {xFormatter(point.x)}, {yLabel} {yFormatter(point.y)}</title>
                </circle>
              )
            })}
          </svg>
        </div>
      )}

      {legend && (
        <div className="chart-legend">
          {legend.map((item) => (
            <div key={item.tone} className="chart-legend-item">
              <span className="chart-legend-swatch" style={{ borderTop: `3px solid var(${TONE_VAR[item.tone] || '--text-dim'})` }} />
              <span className="chart-legend-label">{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </figure>
  )
}
