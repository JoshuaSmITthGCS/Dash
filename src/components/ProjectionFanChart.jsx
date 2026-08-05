const WIDTH = 720
const HEIGHT = 300
const PAD = { top: 18, right: 18, bottom: 42, left: 62 }

function pathBetween(points, upperKey, lowerKey, x, y) {
  const upper = points.map((point) => `${x(point).toFixed(1)},${y(point[upperKey]).toFixed(1)}`)
  const lower = [...points].reverse().map((point) => `${x(point).toFixed(1)},${y(point[lowerKey]).toFixed(1)}`)
  return `M${upper.join(' L')} L${lower.join(' L')} Z`
}

function linePath(points, key, x, y) {
  return `M${points.map((point) => `${x(point).toFixed(1)},${y(point[key]).toFixed(1)}`).join(' L')}`
}

export default function ProjectionFanChart({ fan = [], startAge = null, retirementAge = null, money }) {
  const [selectedIndex, setSelectedIndex] = useState(null)
  if (fan.length < 2) return null
  const plotWidth = WIDTH - PAD.left - PAD.right
  const plotHeight = HEIGHT - PAD.top - PAD.bottom
  const lastMonth = fan.at(-1).month || 1
  const maximum = Math.max(1, ...fan.map((point) => point.p90 || 0))
  const x = (point) => PAD.left + point.month / lastMonth * plotWidth
  const y = (value) => PAD.top + plotHeight - Math.max(0, value || 0) / maximum * plotHeight
  const retirementMonth = retirementAge != null && startAge != null ? Math.max(0, (retirementAge - startAge) * 12) : null
  const retirementX = retirementMonth != null && retirementMonth < lastMonth ? PAD.left + retirementMonth / lastMonth * plotWidth : null
  const tickEvery = Math.max(1, Math.ceil((fan.length - 1) / 5))
  const ticks = fan.filter((_, index) => index === 0 || index === fan.length - 1 || index % tickEvery === 0)
  const selected = selectedIndex == null ? null : fan[selectedIndex]
  const scrub = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    const fraction = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width))
    setSelectedIndex(Math.round(fraction * (fan.length - 1)))
  }
  const moveSelection = (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
    event.preventDefault()
    setSelectedIndex((current) => Math.max(0, Math.min(fan.length - 1, (current ?? 0) + (event.key === 'ArrowRight' ? 1 : -1))))
  }

  return <figure className="projection-fan-chart" tabIndex="0" onKeyDown={moveSelection}>
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby="projection-fan-title projection-fan-description" onPointerDown={(event) => { event.currentTarget.setPointerCapture?.(event.pointerId); scrub(event) }} onPointerMove={(event) => { if (event.buttons || event.pointerType === 'touch') scrub(event) }}>
      <title id="projection-fan-title">Projected balance percentile fan</title>
      <desc id="projection-fan-description">The wide band spans the 10th to 90th percentile, the inner band spans the 25th to 75th percentile, and the line is the median.</desc>
      {[0, 0.5, 1].map((fraction) => {
        const value = maximum * fraction
        return <g key={fraction}>
          <line className="projection-grid-line" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(value)} y2={y(value)} />
          <text className="projection-axis-label projection-y-label" x={PAD.left - 9} y={y(value) + 4} textAnchor="end">{money(value)}</text>
        </g>
      })}
      <path className="projection-band outer" d={pathBetween(fan, 'p90', 'p10', x, y)} />
      <path className="projection-band inner" d={pathBetween(fan, 'p75', 'p25', x, y)} />
      <path className="projection-median-line" d={linePath(fan, 'p50', x, y)} />
      {selected && <g className="projection-scrub-marker">
        <line x1={x(selected)} x2={x(selected)} y1={PAD.top} y2={PAD.top + plotHeight} />
        <circle cx={x(selected)} cy={y(selected.p50)} r="4" />
      </g>}
      {retirementX != null && <g className="projection-retirement-marker">
        <line x1={retirementX} x2={retirementX} y1={PAD.top} y2={PAD.top + plotHeight} />
        <text x={retirementX + 6} y={PAD.top + 13}>Retire</text>
      </g>}
      {ticks.map((point) => <text key={point.month} className="projection-axis-label" x={x(point)} y={HEIGHT - 14} textAnchor={point.month === 0 ? 'start' : point.month === lastMonth ? 'end' : 'middle'}>
        {startAge == null ? `Year ${Math.round(point.year)}` : `Age ${Math.round(startAge + point.year)}`}
      </text>)}
    </svg>
    {selected && <div className="projection-scrub-readout" role="status"><strong>{startAge == null ? `Year ${Math.round(selected.year)}` : `Age ${Math.round(startAge + selected.year)}`}</strong><span>10th {money(selected.p10)}</span><span>Median {money(selected.p50)}</span><span>90th {money(selected.p90)}</span></div>}
    <figcaption><span><i className="fan-swatch outer" />10th to 90th</span><span><i className="fan-swatch inner" />25th to 75th</span><span><i className="fan-swatch median" />Median</span></figcaption>
  </figure>
}
import { useState } from 'react'
