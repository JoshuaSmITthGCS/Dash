/**
 * Star Chart's chart renderer — custom SVG on a faint graticule. Point marks (scatter, dotPlot,
 * bullet) scale by AREA, never radius (`r = k * sqrt(value)`), the correct astronomical
 * convention — radius-scaling exaggerates large values (DESIGN.md §7).
 */
import { STATES } from '../../core/states.js'

const INK = 'var(--ink-primary)'
const FAINT = 'var(--ink-faint)'
const BREACH = 'var(--state-breach)'
const GRATICULE = 'var(--graticule)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return BREACH
  if (state?.state === STATES.UNAVAILABLE) return FAINT
  return INK
}

function areaRadius(value, base = 2.5, k = 2.2) {
  return base + Math.sqrt(Math.abs(value ?? 1)) * k
}

function scaleLinear(domain, range) {
  const [d0, d1] = domain; const [r0, r1] = range
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

function seriesData(series = [], values = []) { return series.length ? series.map((p) => p.y ?? p.value) : values }

function Graticule({ width, height }) {
  return (
    <>
      <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={GRATICULE} strokeWidth="0.5" />
      <line x1={0} x2={width} y1={height / 2} y2={height / 2} stroke={GRATICULE} strokeWidth="0.5" />
    </>
  )
}

function Svg({ width = 240, height = 100, ariaLabel, children }) {
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>{children}</svg>
}

function line({ series, values, width = 240, height = 100, thresholds = [], state, ariaLabel }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [8, width - 8])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 8, 8])
  const points = data.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <Graticule width={width} height={height} />
    {thresholds.map((t, i) => <line key={i} x1={0} x2={width} y1={y(t.value)} y2={y(t.value)} stroke={GRATICULE} strokeDasharray="2,2" />)}
    <polyline points={points} fill="none" stroke={toneFor(state)} strokeWidth="1" />
  </Svg>
}

function sparkline({ series, values, width = 60, height = 20, state, ariaLabel }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [2, width - 2])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 2, 2])
  const points = data.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><polyline points={points} fill="none" stroke={toneFor(state)} strokeWidth="1" /></Svg>
}

function bar({ values = [], width = 240, height = 100, state, ariaLabel }) {
  const max = Math.max(...values.map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height - 10])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <Graticule width={width} height={height} />
    {values.map((v, i) => {
      const h = y(Math.abs(v))
      return <rect key={i} x={i * bw + 2} y={height - 2 - h} width={bw - 4} height={h} fill="none" stroke={toneFor(state)} strokeWidth="1" />
    })}
  </Svg>
}

function pairedBar({ values = [], width = 240, height = 100, ariaLabel }) {
  const max = Math.max(...values.flat().map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height - 10])
  const gw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map(([a, b], i) => {
      const ha = y(Math.abs(a || 0)); const hb = y(Math.abs(b || 0)); const gx = i * gw
      return <g key={i}>
        <rect x={gx + 2} y={height - 2 - ha} width={gw / 2 - 4} height={ha} fill="none" stroke={INK} strokeWidth="1" />
        <rect x={gx + gw / 2 + 1} y={height - 2 - hb} width={gw / 2 - 4} height={hb} fill="none" stroke={FAINT} strokeWidth="1" />
      </g>
    })}
  </Svg>
}

function barTimeline(props) { return bar(props) }

/** Marks scale by area, never radius — the astronomical convention this medium is named for. */
function scatter({ series = [], width = 200, height = 200, state, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x); const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [8, width - 8])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 8, 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <Graticule width={width} height={height} />
    {series.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r={areaRadius(p.magnitude ?? 1)} fill={toneFor(state)} />)}
  </Svg>
}

function composition({ values = [], width = 200, height = 24, ariaLabel }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => { const value = Math.max(0, v.value ?? v); const w = (value / total) * width; const r = <rect key={i} x={cursor} width={w} height={height} fill="none" stroke={INK} strokeWidth="1" />; cursor += w; return r })}
  </Svg>
}

function heatmap({ values = [], width = 160, height = 160, ariaLabel }) {
  const rows = values.length || 1; const cols = values[0]?.length || 1
  const cw = width / cols; const ch = height / rows
  const flat = values.flat(); const max = Math.max(...flat.map(Math.abs), 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((row, r) => row.map((v, c) => <circle key={`${r}-${c}`} cx={c * cw + cw / 2} cy={r * ch + ch / 2} r={areaRadius(Math.abs(v) / max, 1, 4)} fill={INK} opacity="0.7" />))}
  </Svg>
}

function fan({ series = [], width = 240, height = 100, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, series.length - 1], [4, width - 4])
  const points = series.map((p, i) => `${x(i)},${height - (p.median ?? 0.5) * height}`).join(' ')
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><polyline points={points} fill="none" stroke={INK} strokeWidth="1" /></Svg>
}

function bullet({ values = [], thresholds = [], width = 200, height = 28, state, ariaLabel }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const x = scaleLinear(domain, [4, width - 4])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={GRATICULE} strokeWidth="1" />
    <line x1={x(threshold.value)} x2={x(threshold.value)} y1={4} y2={height - 4} stroke={FAINT} strokeWidth="1" />
    <circle cx={x(value)} cy={height / 2} r={areaRadius(Math.abs(value), 2, 1.5)} fill={toneFor(state)} />
  </Svg>
}

function dotPlot({ values = [], width = 200, height = 60, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [8, width - 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={GRATICULE} />
    {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r={areaRadius(Math.abs(v), 2, 1)} fill={INK} />)}
  </Svg>
}

function waterfall({ values = [], width = 240, height = 100, ariaLabel }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height - 10])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => {
      const start = cumulative; cumulative += v
      const top = height - 2 - y(Math.max(start, cumulative)); const h = Math.max(1, y(Math.abs(v)))
      return <rect key={i} x={i * bw + 2} y={top} width={bw - 4} height={h} fill="none" stroke={v >= 0 ? INK : BREACH} strokeWidth="1" />
    })}
  </Svg>
}

function dial({ values = [], domain = [0, 1], width = 120, height = 120, state, ariaLabel }) {
  const value = values[0] ?? 0
  const fraction = Math.max(0, Math.min(1, (value - domain[0]) / ((domain[1] - domain[0]) || 1)))
  const r = width / 2 - 10
  const cx = width / 2; const cy = height / 2
  const circumference = 2 * Math.PI * r
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={GRATICULE} strokeWidth="1" />
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={toneFor(state)} strokeWidth="2" strokeDasharray={`${circumference * fraction} ${circumference}`} transform={`rotate(-90 ${cx} ${cy})`} />
    <text x={cx} y={cy + 4} fontSize="10" textAnchor="middle" fill={INK} fontFamily="var(--font-mono)">{domain[0]}–{domain[1]}</text>
  </Svg>
}

function profile({ values = [], width = 200, height = 120, ariaLabel }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const rowHeight = height / (sorted.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={GRATICULE} />
    {sorted.map((row, i) => {
      const value = row.value ?? row
      return <circle key={i} cx={width / 2 + (value >= 0 ? 1 : -1) * areaRadius(Math.abs(value), 2, 6)} cy={i * rowHeight + rowHeight / 2} r={areaRadius(Math.abs(value), 2, 4)} fill={value >= 0 ? INK : BREACH} />
    })}
  </Svg>
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
