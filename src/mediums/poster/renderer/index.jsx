/**
 * Poster's chart renderer — halftone dot density instead of fills, exactly two spot inks plus
 * black. Implemented as SVG dot grids (not a literal <canvas>): same halftone visual outcome,
 * deterministic and directly testable. Registration offset (confidence) lives in LabelFrame,
 * not here — this file only draws the marks themselves, never on text.
 */
import { STATES } from '../../core/states.js'
import { seedFor } from '../../core/seed.js'

const INK1 = 'var(--ink-spot-1)'
const INK2 = 'var(--ink-spot-2)'
const BLACK = 'var(--ink-black)'
const FAINT = 'var(--ink-faint)'
const HAIRLINE = 'var(--rule-hairline)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return INK1
  if (state?.state === STATES.UNAVAILABLE) return FAINT
  return BLACK
}

function scaleLinear(domain, range) {
  const [d0, d1] = domain; const [r0, r1] = range
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

function Svg({ width = 240, height = 80, ariaLabel, children }) {
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>{children}</svg>
}

/** A halftone-density rectangle: dot radius grows with `density` (0..1), grid seeded from id. */
function Halftone({ x, y, width, height, density, color, id }) {
  const rng = seedFor(id || 'halftone')
  const cell = 6
  const cols = Math.max(1, Math.floor(width / cell))
  const rows = Math.max(1, Math.floor(height / cell))
  const dots = []
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const jitter = (rng() - 0.5) * 1.2
      const radius = Math.max(0.4, (cell / 2 - 0.5) * density)
      dots.push(<circle key={`${r}-${c}`} cx={x + c * cell + cell / 2 + jitter} cy={y + r * cell + cell / 2} r={radius} fill={color} />)
    }
  }
  return <>{dots}</>
}

function line({ series, values, width = 240, height = 80, thresholds = [], state, ariaLabel, metricId }) {
  const data = series?.length ? series.map((p) => p.y ?? p.value) : (values || [])
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [4, width - 4])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 4, 4])
  const path = data.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ')
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {thresholds.map((t, i) => <line key={i} x1={0} x2={width} y1={y(t.value)} y2={y(t.value)} stroke={HAIRLINE} strokeDasharray="2,2" />)}
      <path d={path} fill="none" stroke={toneFor(state)} strokeWidth="2" />
      <Halftone x={0} y={height - 10} width={width} height={10} density={0.3} color={INK2} id={metricId} />
    </Svg>
  )
}

function sparkline({ series, values, width = 60, height = 20, state, ariaLabel }) {
  const data = series?.length ? series.map((p) => p.y ?? p.value) : (values || [])
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [2, width - 2])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 2, 2])
  const path = data.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ')
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><path d={path} fill="none" stroke={toneFor(state)} strokeWidth="1.5" /></Svg>
}

function bar({ values = [], width = 240, height = 80, state, ariaLabel, metricId }) {
  const max = Math.max(...values.map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const bw = width / (values.length || 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((v, i) => {
        const h = y(Math.abs(v))
        const density = Math.abs(v) / max
        return <g key={i}><Halftone x={i * bw + 1} y={height - h} width={bw - 2} height={h} density={density} color={toneFor(state)} id={`${metricId}-${i}`} /></g>
      })}
    </Svg>
  )
}

function pairedBar({ values = [], width = 240, height = 80, ariaLabel }) {
  const max = Math.max(...values.flat().map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const gw = width / (values.length || 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map(([a, b], i) => {
        const ha = y(Math.abs(a || 0)); const hb = y(Math.abs(b || 0)); const gx = i * gw
        return <g key={i}>
          <rect x={gx + 2} y={height - ha} width={gw / 2 - 3} height={ha} fill={INK1} />
          <rect x={gx + gw / 2 + 1} y={height - hb} width={gw / 2 - 3} height={hb} fill={INK2} />
        </g>
      })}
    </Svg>
  )
}

function barTimeline(props) { return bar(props) }

function scatter({ series = [], width = 200, height = 200, state, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x); const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [8, width - 8])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 8, 8])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
      <line x1={width / 2} x2={width / 2} y1={8} y2={height - 8} stroke={HAIRLINE} />
      {series.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r="3" fill={toneFor(state)} />)}
    </Svg>
  )
}

function composition({ values = [], width = 200, height = 24, ariaLabel }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  const tones = [BLACK, INK1, INK2, FAINT]
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((v, i) => { const value = Math.max(0, v.value ?? v); const w = (value / total) * width; const r = <rect key={i} x={cursor} width={w} height={height} fill={tones[i % tones.length]} />; cursor += w; return r })}
    </Svg>
  )
}

function heatmap({ values = [], width = 160, height = 160, ariaLabel, metricId }) {
  const rows = values.length || 1; const cols = values[0]?.length || 1
  const cw = width / cols; const ch = height / rows
  const flat = values.flat(); const max = Math.max(...flat.map(Math.abs), 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((row, r) => row.map((v, c) => (
        <g key={`${r}-${c}`}><Halftone x={c * cw} y={r * ch} width={cw - 1} height={ch - 1} density={Math.abs(v) / max} color={BLACK} id={`${metricId}-${r}-${c}`} /></g>
      )))}
    </Svg>
  )
}

function fan({ series = [], width = 240, height = 100, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, series.length - 1], [4, width - 4])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <path d={series.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${height - (p.median ?? 0.5) * height}`).join(' ')} fill="none" stroke={BLACK} strokeWidth="1.5" />
  </Svg>
}

function bullet({ values = [], thresholds = [], width = 200, height = 28, state, ariaLabel }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const x = scaleLinear(domain, [4, width - 4])
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={HAIRLINE} strokeWidth="4" />
      <line x1={x(threshold.value)} x2={x(threshold.value)} y1={4} y2={height - 4} stroke={INK2} strokeWidth="2" />
      <circle cx={x(value)} cy={height / 2} r="5" fill={toneFor(state)} />
    </Svg>
  )
}

function dotPlot({ values = [], width = 200, height = 60, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [8, width - 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
    {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r="4" fill={BLACK} />)}
  </Svg>
}

function waterfall({ values = [], width = 240, height = 100, ariaLabel }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height])
  const bw = width / (values.length || 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      {values.map((v, i) => { const start = cumulative; cumulative += v; const top = height - y(Math.max(start, cumulative)); const h = Math.max(1, y(Math.abs(v))); return <rect key={i} x={i * bw + 1} y={top} width={bw - 2} height={h} fill={v >= 0 ? BLACK : INK1} /> })}
    </Svg>
  )
}

function dial({ values = [], domain = [0, 1], width = 120, height = 120, state, ariaLabel, metricId }) {
  const value = values[0] ?? 0
  const fraction = Math.max(0, Math.min(1, (value - domain[0]) / ((domain[1] - domain[0]) || 1)))
  const r = width / 2 - 10
  const cx = width / 2; const cy = height / 2
  const circumference = 2 * Math.PI * r
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={HAIRLINE} strokeWidth="8" />
      <circle
        cx={cx} cy={cy} r={r} fill="none" stroke={toneFor(state)} strokeWidth="8"
        strokeDasharray={`${circumference * fraction} ${circumference}`}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text x={cx} y={cy + 4} fontSize="10" textAnchor="middle" fill={BLACK}>{domain[0]}–{domain[1]}</text>
      <Halftone x={cx - r} y={cy - r} width={r * 2} height={4} density={fraction} color={INK1} id={metricId} />
    </Svg>
  )
}

function profile({ values = [], width = 200, height = 120, ariaLabel }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const max = Math.max(...sorted.map((v) => Math.abs(v.value ?? v)), 1)
  const x = scaleLinear([0, max], [0, width / 2 - 4])
  const rowHeight = height / (sorted.length || 1)
  return (
    <Svg width={width} height={height} ariaLabel={ariaLabel}>
      <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={HAIRLINE} />
      {sorted.map((row, i) => { const value = row.value ?? row; const w = x(Math.abs(value)); const cx = width / 2; return <rect key={i} x={value >= 0 ? cx : cx - w} y={i * rowHeight + 2} width={w} height={rowHeight - 4} fill={value >= 0 ? BLACK : INK1} /> })}
    </Svg>
  )
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
