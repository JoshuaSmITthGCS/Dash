/**
 * Ticker's chart renderer — flat, hairline-only, monospace. `sparkline` is the one chart type
 * used inline in the wire-feed row grammar; the rest exist for the destinations that need a
 * larger chart (at most one per screen, per the master's density rule).
 */
import { STATES } from '../../core/states.js'

const INK = 'var(--ink-primary)'
const FAINT = 'var(--ink-faint)'
const BREACH = 'var(--state-breach)'
const HAIRLINE = 'var(--rule-hairline)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return BREACH
  if (state?.state === STATES.UNAVAILABLE) return FAINT
  return INK
}

function scaleLinear(domain, range) {
  const [d0, d1] = domain; const [r0, r1] = range
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

function seriesData(series = [], values = []) { return series.length ? series.map((p) => p.y ?? p.value) : values }

function Svg({ width = 240, height = 60, ariaLabel, children }) {
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>{children}</svg>
}

function line({ series, values, width = 240, height = 60, thresholds = [], state, ariaLabel }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [2, width - 2])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 2, 2])
  const path = data.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ')
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {thresholds.map((t, i) => <line key={i} x1={0} x2={width} y1={y(t.value)} y2={y(t.value)} stroke={HAIRLINE} strokeDasharray="2,2" />)}
    <path d={path} fill="none" stroke={toneFor(state)} strokeWidth="1" />
  </Svg>
}

function sparkline({ series, values, width = 56, height = 16, state, ariaLabel }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [1, width - 1])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 1, 1])
  const path = data.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(v)}`).join(' ')
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><path d={path} fill="none" stroke={toneFor(state)} strokeWidth="1" /></Svg>
}

function bar({ values = [], width = 240, height = 60, state, ariaLabel }) {
  const max = Math.max(...values.map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => { const h = y(Math.abs(v)); return <rect key={i} x={i * bw + 1} y={height - h} width={bw - 2} height={h} fill={toneFor(state)} /> })}
  </Svg>
}

function pairedBar({ values = [], width = 240, height = 60, ariaLabel }) {
  const max = Math.max(...values.flat().map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const gw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map(([a, b], i) => { const ha = y(Math.abs(a || 0)); const hb = y(Math.abs(b || 0)); const gx = i * gw; return <g key={i}>
      <rect x={gx + 1} y={height - ha} width={gw / 2 - 2} height={ha} fill={INK} />
      <rect x={gx + gw / 2} y={height - hb} width={gw / 2 - 2} height={hb} fill={FAINT} />
    </g> })}
  </Svg>
}

function barTimeline(props) { return bar(props) }

function scatter({ series = [], width = 200, height = 200, state, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x); const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [4, width - 4])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 4, 4])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
    {series.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r="2" fill={toneFor(state)} />)}
  </Svg>
}

function composition({ values = [], width = 200, height = 16, ariaLabel }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => { const value = Math.max(0, v.value ?? v); const w = (value / total) * width; const r = <rect key={i} x={cursor} width={w} height={height} fill={i % 2 ? FAINT : INK} />; cursor += w; return r })}
  </Svg>
}

function heatmap({ values = [], width = 160, height = 160, ariaLabel }) {
  const rows = values.length || 1; const cols = values[0]?.length || 1
  const cw = width / cols; const ch = height / rows
  const flat = values.flat(); const max = Math.max(...flat.map(Math.abs), 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((row, r) => row.map((v, c) => <rect key={`${r}-${c}`} x={c * cw} y={r * ch} width={cw - 1} height={ch - 1} fill={INK} opacity={Math.abs(v) / max} />))}
  </Svg>
}

function fan({ series = [], width = 240, height = 60, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, series.length - 1], [2, width - 2])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <path d={series.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${height - (p.median ?? 0.5) * height}`).join(' ')} fill="none" stroke={INK} strokeWidth="1" />
  </Svg>
}

function bullet({ values = [], thresholds = [], width = 160, height = 16, state, ariaLabel }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const x = scaleLinear(domain, [2, width - 2])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={2} x2={width - 2} y1={height / 2} y2={height / 2} stroke={HAIRLINE} strokeWidth="2" />
    <line x1={x(threshold.value)} x2={x(threshold.value)} y1={2} y2={height - 2} stroke={FAINT} />
    <circle cx={x(value)} cy={height / 2} r="3" fill={toneFor(state)} />
  </Svg>
}

function dotPlot({ values = [], width = 200, height = 40, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [4, width - 4])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
    {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r="3" fill={INK} />)}
  </Svg>
}

function waterfall({ values = [], width = 240, height = 80, ariaLabel }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => { const start = cumulative; cumulative += v; const top = height - y(Math.max(start, cumulative)); const h = Math.max(1, y(Math.abs(v))); return <rect key={i} x={i * bw + 1} y={top} width={bw - 2} height={h} fill={v >= 0 ? INK : BREACH} /> })}
  </Svg>
}

function dial({ values = [], domain = [0, 1], width = 100, height = 100, state, ariaLabel }) {
  const value = values[0] ?? 0
  const fraction = Math.max(0, Math.min(1, (value - domain[0]) / ((domain[1] - domain[0]) || 1)))
  const r = width / 2 - 6
  const cx = width / 2; const cy = height / 2
  const circumference = 2 * Math.PI * r
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={HAIRLINE} strokeWidth="1" />
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={toneFor(state)} strokeWidth="2" strokeDasharray={`${circumference * fraction} ${circumference}`} transform={`rotate(-90 ${cx} ${cy})`} />
    <text x={cx} y={cy + 4} fontSize="9" textAnchor="middle" fill={INK}>{domain[0]}–{domain[1]}</text>
  </Svg>
}

function profile({ values = [], width = 200, height = 100, ariaLabel }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const max = Math.max(...sorted.map((v) => Math.abs(v.value ?? v)), 1)
  const x = scaleLinear([0, max], [0, width / 2 - 2])
  const rowHeight = height / (sorted.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={HAIRLINE} />
    {sorted.map((row, i) => { const value = row.value ?? row; const w = x(Math.abs(value)); const cx = width / 2; return <rect key={i} x={value >= 0 ? cx : cx - w} y={i * rowHeight + 1} width={w} height={rowHeight - 2} fill={value >= 0 ? INK : BREACH} /> })}
  </Svg>
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
