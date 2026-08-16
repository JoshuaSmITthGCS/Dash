import { useId, useRef, useState } from 'react'
import { useElementWidth } from '../lib/useElementWidth.js'

/**
 * Two named series compared side by side within each group — champion vs. challenger
 * per horizon, here. Values can be negative (a rank IC below zero is a real, meaningful
 * result), so bars grow from a shared zero baseline rather than the group's own floor.
 *
 * Fixed two-series color order (--series-stock, --series-benchmark), same convention
 * ScatterChart and GrowthChart already use — color follows the series identity, never
 * a per-group rank. Table view is one click away, same pattern as CorrelationHeatmap.
 */

const HEIGHT = 260
const PAD = { top: 24, right: 16, bottom: 34, left: 44 }
const SERIES_VAR = ['--series-stock', '--series-benchmark']

export default function PairedBarChart({
  groups = [],
  seriesLabels = ['Series A', 'Series B'],
  yFormatter = String,
  caption,
  className = '',
}) {
  const [view, setView] = useState('chart')
  const [hover, setHover] = useState(null)
  const plotRef = useRef(null)
  const titleId = useId()
  const measuredWidth = useElementWidth(plotRef, null)
  const width = Math.max(320, measuredWidth ?? 640)

  const usable = groups.filter((group) => group.values.some((value) => Number.isFinite(value)))
  if (!usable.length) return null

  const allValues = usable.flatMap((group) => group.values).filter(Number.isFinite)
  const min = Math.min(0, ...allValues)
  const max = Math.max(0, ...allValues)
  const span = max - min || 1
  const innerHeight = HEIGHT - PAD.top - PAD.bottom
  const innerWidth = width - PAD.left - PAD.right
  const zeroY = PAD.top + innerHeight - ((0 - min) / span) * innerHeight
  const valueY = (value) => PAD.top + innerHeight - ((value - min) / span) * innerHeight

  const groupWidth = innerWidth / usable.length
  const barGap = 4
  const barWidth = Math.max(6, (groupWidth - barGap * 3) / 2)

  const readout = hover
    ? `${hover.series}, ${hover.group}: ${yFormatter(hover.value)}`
    : `${usable.length} group${usable.length === 1 ? '' : 's'}. Hover or tab to a bar for its value.`

  return (
    <figure className={`correlation-figure ${className}`.trim()} aria-labelledby={titleId}>
      <figcaption className="correlation-head">
        <span id={titleId} className="sr-only">{seriesLabels.join(' versus ')} by group</span>
        <p className="correlation-readout" aria-live="polite">{readout}</p>
        <div className="correlation-toggle" role="group" aria-label="Chart view">
          <button type="button" aria-pressed={view === 'chart'} onClick={() => setView('chart')}>Chart</button>
          <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>Table</button>
        </div>
      </figcaption>

      {view === 'table' ? (
        <div className="correlation-table-wrap">
          <table className="correlation-table">
            <caption className="sr-only">{caption || seriesLabels.join(' versus ')}</caption>
            <thead><tr><th scope="col">Group</th>{seriesLabels.map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
            <tbody>
              {usable.map((group) => (
                <tr key={group.label}>
                  <th scope="row">{group.label}</th>
                  {group.values.map((value, index) => (
                    <td key={seriesLabels[index]} className="num">{value == null ? '–' : yFormatter(value)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-scroll-region" ref={plotRef}>
          <svg viewBox={`0 0 ${width} ${HEIGHT}`} width="100%" height={HEIGHT} className="chart-plot-svg"
            role="img" aria-label={`${seriesLabels.join(' versus ')}, ${usable.length} groups`}>
            <line x1={PAD.left} x2={width - PAD.right} y1={zeroY} y2={zeroY} stroke="var(--border-strong)" strokeWidth="1" />
            {usable.map((group, groupIndex) => {
              const groupX = PAD.left + groupIndex * groupWidth
              return (
                <g key={group.label}>
                  <text x={groupX + groupWidth / 2} y={HEIGHT - 12} textAnchor="middle"
                    fill="var(--text-dim)" fontSize="11" fontFamily="var(--font-mono)">{group.label}</text>
                  {group.values.map((value, seriesIndex) => {
                    if (!Number.isFinite(value)) return null
                    const barX = groupX + barGap + seriesIndex * (barWidth + barGap)
                    const top = Math.min(zeroY, valueY(value))
                    const barHeight = Math.max(1, Math.abs(valueY(value) - zeroY))
                    const active = hover?.group === group.label && hover?.series === seriesLabels[seriesIndex]
                    return (
                      <g key={seriesLabels[seriesIndex]}
                        onMouseEnter={() => setHover({ group: group.label, series: seriesLabels[seriesIndex], value })}
                        onFocus={() => setHover({ group: group.label, series: seriesLabels[seriesIndex], value })}
                        onMouseLeave={() => setHover(null)}
                        onBlur={() => setHover(null)}>
                        <rect x={barX} y={top} width={barWidth} height={barHeight} rx="2"
                          fill={`var(${SERIES_VAR[seriesIndex] || '--text-dim'})`}
                          opacity={active ? 1 : 0.9} tabIndex="0">
                          <title>{seriesLabels[seriesIndex]}, {group.label}: {yFormatter(value)}</title>
                        </rect>
                        <text x={barX + barWidth / 2} y={value >= 0 ? top - 4 : top + barHeight + 12}
                          textAnchor="middle" fill="var(--text-faint)" fontSize="11" fontFamily="var(--font-mono)">
                          {yFormatter(value)}
                        </text>
                      </g>
                    )
                  })}
                </g>
              )
            })}
          </svg>
        </div>
      )}

      <div className="chart-legend">
        {seriesLabels.map((label, index) => (
          <div key={label} className="chart-legend-item">
            <span className="chart-legend-swatch" style={{ borderTop: `3px solid var(${SERIES_VAR[index] || '--text-dim'})` }} />
            <span className="chart-legend-label">{label}</span>
          </div>
        ))}
      </div>
    </figure>
  )
}
