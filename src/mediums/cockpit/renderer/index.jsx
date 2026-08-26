/**
 * Cockpit's chart renderer — custom SVG only, no chart library, no CRT layer. Tick-scale
 * geometry is precomputed per mount (the same polar-math technique as the existing
 * `src/components/ScoreGauge.jsx`), never recalculated per frame. Glow is a static
 * `--glow-live`/`--glow-breach` box-shadow token applied by the caller's Container, never a
 * live filter — this file only draws geometry.
 */
import { STATES } from '../../core/states.js'

const FAINT = 'var(--ink-faint)'
const ESTABLISHED = 'var(--state-established)'
const BREACH = 'var(--state-breach)'
const HAIRLINE = 'var(--rule-hairline)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return BREACH
  if (state?.state === STATES.UNAVAILABLE) return FAINT
  return ESTABLISHED
}

function scaleLinear(domain, range) {
  const [d0, d1] = domain
  const [r0, r1] = range
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

function pointsFromSeries(series = [], values = [], width, height, padding = 4) {
  const data = series.length ? series.map((point) => point.y ?? point.value) : values
  if (!data.length) return { path: '', x: () => 0, y: () => 0 }
  const min = Math.min(...data)
  const max = Math.max(...data)
  const x = scaleLinear([0, data.length - 1], [padding, width - padding])
  const y = scaleLinear([min, max], [height - padding, padding])
  const path = data.map((value, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(value)}`).join(' ')
  return { path, x, y, data }
}

function Svg({ width = 240, height = 80, ariaLabel, children }) {
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>
      {children}
    </svg>
  )
}

function line({ series, values, width = 240, height = 80, thresholds = [], state, ariaLabel }) {
  const { path, y } = pointsFromSeries(series, values, width, height)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {thresholds.map((t, i) => (
        <line key={i} x1={0} x2={width} y1={y(t.value)} y2={y(t.value)} stroke={FAINT} strokeDasharray="2,2" />
      ))}
      <path d={path} fill="none" stroke={toneFor(state)} strokeWidth="1.5" />
    </Svg>
  )
}

function sparkline({ series, values, width = 60, height = 20, state, ariaLabel }) {
  const { path } = pointsFromSeries(series, values, width, height, 2)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <path d={path} fill="none" stroke={toneFor(state)} strokeWidth="1" />
    </Svg>
  )
}

function bar({ values = [], width = 240, height = 80, state, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const max = Math.max(...values.map(Math.abs), 1)
  const barWidth = width / values.length
  const y = scaleLinear([0, max], [0, height])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((value, index) => {
        const h = y(Math.abs(value))
        return <rect key={index} x={index * barWidth + 1} y={height - h} width={barWidth - 2} height={h} fill={toneFor(state)} />
      })}
    </Svg>
  )
}

function pairedBar({ values = [], width = 240, height = 80, ariaLabel }) {
  const max = Math.max(...values.flat().map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const groupWidth = width / values.length
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map(([a, b], index) => {
        const ha = y(Math.abs(a || 0))
        const hb = y(Math.abs(b || 0))
        const gx = index * groupWidth
        return (
          <g key={index}>
            <rect x={gx + 2} y={height - ha} width={groupWidth / 2 - 3} height={ha} fill={ESTABLISHED} />
            <rect x={gx + groupWidth / 2 + 1} y={height - hb} width={groupWidth / 2 - 3} height={hb} fill={FAINT} />
          </g>
        )
      })}
    </Svg>
  )
}

function barTimeline({ values = [], width = 320, height = 60, ariaLabel }) {
  return bar({ values, width, height, ariaLabel })
}

function scatter({ series = [], width = 200, height = 200, thresholds = [], state, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x)
  const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [8, width - 8])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 8, 8])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
      <line x1={width / 2} x2={width / 2} y1={8} y2={height - 8} stroke={HAIRLINE} />
      {series.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r="3" fill={toneFor(state)} />)}
      {thresholds.map((t, i) => <text key={i} x={4} y={12} fontSize="9" fill={FAINT}>{t.label}</text>)}
    </Svg>
  )
}

function composition({ values = [], width = 200, height = 24, ariaLabel }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  const tones = [ESTABLISHED, FAINT, HAIRLINE, BREACH]
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((v, index) => {
        const value = Math.max(0, v.value ?? v)
        const w = (value / total) * width
        const rect = <rect key={index} x={cursor} y={0} width={w} height={height} fill={tones[index % tones.length]} />
        cursor += w
        return rect
      })}
    </Svg>
  )
}

function heatmap({ values = [], width = 160, height = 160, ariaLabel }) {
  const rows = values.length || 1
  const cols = values[0]?.length || 1
  const cellW = width / cols
  const cellH = height / rows
  const flat = values.flat()
  const max = Math.max(...flat.map(Math.abs), 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((row, r) => row.map((value, c) => {
        const t = Math.min(1, Math.abs(value) / max)
        return <rect key={`${r}-${c}`} x={c * cellW} y={r * cellH} width={cellW - 1} height={cellH - 1} fill={ESTABLISHED} opacity={0.15 + t * 0.7} />
      }))}
    </Svg>
  )
}

function fan({ series = [], width = 240, height = 100, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const bands = series[0]?.bands || []
  const x = scaleLinear([0, series.length - 1], [4, width - 4])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {bands.map((_, bandIndex) => {
        const upper = series.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${height - (p.bands[bandIndex]?.[1] ?? 0) * height}`).join(' ')
        return <path key={bandIndex} d={upper} fill="none" stroke={FAINT} strokeWidth="1" opacity={0.5} />
      })}
      <path
        d={series.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${height - (p.median ?? 0.5) * height}`).join(' ')}
        fill="none" stroke={ESTABLISHED} strokeWidth="1.5"
      />
    </Svg>
  )
}

/** Value vs. kill_threshold on one scale — only rendered when both are real numbers. */
function bullet({ values = [], thresholds = [], width = 200, height = 28, state, ariaLabel }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const x = scaleLinear(domain, [4, width - 4])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={HAIRLINE} strokeWidth="4" />
      <line x1={x(threshold.value)} x2={x(threshold.value)} y1={4} y2={height - 4} stroke={FAINT} strokeWidth="2" />
      <circle cx={x(value)} cy={height / 2} r="5" fill={toneFor(state)} />
    </Svg>
  )
}

function dotPlot({ values = [], width = 200, height = 60, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [8, width - 8])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
      {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r="4" fill={ESTABLISHED} />)}
    </Svg>
  )
}

function waterfall({ values = [], width = 240, height = 100, ariaLabel }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height])
  const barWidth = width / (values.length || 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((v, index) => {
        const start = cumulative
        cumulative += v
        const top = height - y(Math.max(start, cumulative))
        const h = Math.max(1, y(Math.abs(v)))
        return <rect key={index} x={index * barWidth + 1} y={top} width={barWidth - 2} height={h} fill={v >= 0 ? ESTABLISHED : BREACH} />
      })}
    </Svg>
  )
}

/** The dial — MUST render a labeled scale, never a bare gauge. Cockpit's signature type. */
function dial({ values = [], domain = [0, 1], thresholds = [], width = 120, height = 120, state, ariaLabel }) {
  const value = values[0] ?? 0
  const [d0, d1] = domain
  const radius = width / 2 - 12
  const cx = width / 2
  const cy = height / 2
  const startAngle = -220
  const sweep = 260
  const angleFor = (v) => startAngle + ((v - d0) / (d1 - d0 || 1)) * sweep
  const toXY = (angleDeg, r) => {
    const rad = (angleDeg * Math.PI) / 180
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)]
  }
  const [needleX, needleY] = toXY(angleFor(value), radius - 8)
  const ticks = [d0, (d0 + d1) / 2, d1]
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <circle cx={cx} cy={cy} r={radius} fill="none" stroke={HAIRLINE} strokeWidth="2" />
      {ticks.map((t, i) => {
        const [tx, ty] = toXY(angleFor(t), radius + 10)
        return <text key={i} x={tx} y={ty} fontSize="8" fill={FAINT} textAnchor="middle">{t}</text>
      })}
      {thresholds.map((t, i) => {
        const [tx, ty] = toXY(angleFor(t.value), radius)
        return <circle key={i} cx={tx} cy={ty} r="2" fill={BREACH} />
      })}
      <line x1={cx} y1={cy} x2={needleX} y2={needleY} stroke={toneFor(state)} strokeWidth="2" />
      <circle cx={cx} cy={cy} r="3" fill={toneFor(state)} />
    </Svg>
  )
}

/** Factor-loading profile — sorted bar/dot profile, replaces the banned radar chart. */
function profile({ values = [], width = 200, height = 120, ariaLabel }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const max = Math.max(...sorted.map((v) => Math.abs(v.value ?? v)), 1)
  const x = scaleLinear([0, max], [0, width / 2 - 4])
  const rowHeight = height / (sorted.length || 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={HAIRLINE} />
      {sorted.map((row, index) => {
        const value = row.value ?? row
        const w = x(Math.abs(value))
        const cx = width / 2
        return (
          <rect
            key={index}
            x={value >= 0 ? cx : cx - w}
            y={index * rowHeight + 2}
            width={w}
            height={rowHeight - 4}
            fill={value >= 0 ? ESTABLISHED : BREACH}
          />
        )
      })}
    </Svg>
  )
}

export default {
  line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap,
  fan, bullet, dotPlot, waterfall, dial, profile,
}
