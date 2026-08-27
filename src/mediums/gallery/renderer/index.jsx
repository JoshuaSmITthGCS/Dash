/**
 * Gallery's chart renderer — real brush strokes via rough.js (not roughViz, which is D3-v5
 * coupled and would pull a second charting stack). Roughness is low for confident (established)
 * strokes, higher for accumulating/sketch states — Gallery's state-adjacent material device,
 * distinct from its actual confidence channel (transparency, in LabelFrame). Every stroke is
 * seeded from `seedFor(metricId)` so screenshots never churn.
 */
import rough from 'roughjs/bundled/rough.cjs'
import { STATES } from '../../core/states.js'
import { seedFor } from '../../core/seed.js'

const INK = 'var(--ink-primary)'
const FAINT = 'var(--ink-faint)'
const BREACH = 'var(--state-breach)'
const HAIRLINE = 'var(--rule-hairline)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return BREACH
  if (state?.state === STATES.UNAVAILABLE) return FAINT
  return INK
}

function roughnessFor(state) {
  return state?.state === STATES.ACCUMULATING ? 2.2 : 0.9
}

function intSeed(id) {
  // seedFor() gives a repeatable RNG; drawing one float from it and scaling gives rough.js a
  // repeatable integer seed derived from the exact same deterministic source every other
  // medium's material randomness uses.
  return Math.floor(seedFor(id || 'gallery')() * 2 ** 31) || 1
}

const generator = rough.generator()

/** Converts one rough.js Drawable into React <path> elements. */
function RoughPaths({ drawable }) {
  if (!drawable) return null
  return generator.toPaths(drawable).map((p, i) => (
    <path key={i} d={p.d} stroke={p.stroke === 'none' ? undefined : p.stroke} strokeWidth={p.strokeWidth} fill={p.fill || 'none'} />
  ))
}

function scaleLinear(domain, range) {
  const [d0, d1] = domain; const [r0, r1] = range
  const span = d1 - d0 || 1
  return (value) => r0 + ((value - d0) / span) * (r1 - r0)
}

function seriesData(series = [], values = []) { return series.length ? series.map((p) => p.y ?? p.value) : values }

function Svg({ width = 240, height = 100, ariaLabel, children }) {
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>{children}</svg>
}

function line({ series, values, width = 240, height = 100, thresholds = [], state, ariaLabel, metricId }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [8, width - 8])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 8, 8])
  const points = data.map((v, i) => [x(i), y(v)])
  const drawable = generator.curve(points, { stroke: toneFor(state), strokeWidth: 2, roughness: roughnessFor(state), seed: intSeed(metricId), bowing: 1.2 })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {thresholds.map((t, i) => <line key={i} x1={0} x2={width} y1={y(t.value)} y2={y(t.value)} stroke={HAIRLINE} strokeDasharray="2,2" />)}
    <RoughPaths drawable={drawable} />
  </Svg>
}

function sparkline({ series, values, width = 60, height = 20, state, ariaLabel, metricId }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [2, width - 2])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 2, 2])
  const points = data.map((v, i) => [x(i), y(v)])
  const drawable = generator.curve(points, { stroke: toneFor(state), strokeWidth: 1.5, roughness: 0.6, seed: intSeed(metricId) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><RoughPaths drawable={drawable} /></Svg>
}

function bar({ values = [], width = 240, height = 100, state, ariaLabel, metricId }) {
  const max = Math.max(...values.map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => {
      const h = y(Math.abs(v))
      const d = generator.rectangle(i * bw + 2, height - h, bw - 4, h, { stroke: toneFor(state), fill: toneFor(state), fillStyle: 'hachure', roughness: roughnessFor(state), seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function pairedBar({ values = [], width = 240, height = 100, ariaLabel, metricId }) {
  const max = Math.max(...values.flat().map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height])
  const gw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map(([a, b], i) => {
      const ha = y(Math.abs(a || 0)); const hb = y(Math.abs(b || 0)); const gx = i * gw
      const da = generator.rectangle(gx + 2, height - ha, gw / 2 - 4, ha, { stroke: INK, fill: INK, fillStyle: 'hachure', roughness: 0.9, seed: intSeed(`${metricId}-a-${i}`) })
      const db = generator.rectangle(gx + gw / 2 + 1, height - hb, gw / 2 - 4, hb, { stroke: FAINT, fill: FAINT, fillStyle: 'hachure', roughness: 0.9, seed: intSeed(`${metricId}-b-${i}`) })
      return <g key={i}><RoughPaths drawable={da} /><RoughPaths drawable={db} /></g>
    })}
  </Svg>
}

function barTimeline(props) { return bar(props) }

function scatter({ series = [], width = 200, height = 200, state, ariaLabel, metricId }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x); const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [8, width - 8])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 8, 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
    <line x1={width / 2} x2={width / 2} y1={8} y2={height - 8} stroke={HAIRLINE} />
    {series.map((p, i) => {
      const d = generator.circle(x(p.x), y(p.y), 8, { stroke: toneFor(state), fill: toneFor(state), fillStyle: 'solid', roughness: 1, seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function composition({ values = [], width = 200, height = 24, ariaLabel }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  const tones = [INK, FAINT, HAIRLINE, BREACH]
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => { const value = Math.max(0, v.value ?? v); const w = (value / total) * width; const r = <rect key={i} x={cursor} width={w} height={height} fill={tones[i % tones.length]} />; cursor += w; return r })}
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

function fan({ series = [], width = 240, height = 100, ariaLabel, metricId }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, series.length - 1], [4, width - 4])
  const points = series.map((p, i) => [x(i), height - (p.median ?? 0.5) * height])
  const d = generator.curve(points, { stroke: INK, strokeWidth: 2, roughness: 0.9, seed: intSeed(metricId) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><RoughPaths drawable={d} /></Svg>
}

function bullet({ values = [], thresholds = [], width = 200, height = 28, state, ariaLabel }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const x = scaleLinear(domain, [4, width - 4])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={HAIRLINE} strokeWidth="3" />
    <line x1={x(threshold.value)} x2={x(threshold.value)} y1={4} y2={height - 4} stroke={FAINT} strokeWidth="2" />
    <circle cx={x(value)} cy={height / 2} r="5" fill={toneFor(state)} />
  </Svg>
}

function dotPlot({ values = [], width = 200, height = 60, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [8, width - 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={HAIRLINE} />
    {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r="4" fill={INK} />)}
  </Svg>
}

function waterfall({ values = [], width = 240, height = 100, ariaLabel, metricId }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => {
      const start = cumulative; cumulative += v
      const top = height - y(Math.max(start, cumulative)); const h = Math.max(1, y(Math.abs(v)))
      const tone = v >= 0 ? INK : BREACH
      const d = generator.rectangle(i * bw + 2, top, bw - 4, h, { stroke: tone, fill: tone, fillStyle: 'hachure', roughness: 1, seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function dial({ values = [], domain = [0, 1], width = 120, height = 120, state, ariaLabel, metricId }) {
  const value = values[0] ?? 0
  const fraction = Math.max(0, Math.min(1, (value - domain[0]) / ((domain[1] - domain[0]) || 1)))
  const r = width / 2 - 10
  const cx = width / 2; const cy = height / 2
  const circumference = 2 * Math.PI * r
  const outline = generator.circle(cx, cy, r * 2, { stroke: FAINT, roughness: 0.7, seed: intSeed(metricId) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={outline} />
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={toneFor(state)} strokeWidth="4" strokeDasharray={`${circumference * fraction} ${circumference}`} transform={`rotate(-90 ${cx} ${cy})`} opacity="0.85" />
    <text x={cx} y={cy + 4} fontSize="10" textAnchor="middle" fill={INK}>{domain[0]}–{domain[1]}</text>
  </Svg>
}

function profile({ values = [], width = 200, height = 120, ariaLabel, metricId }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const max = Math.max(...sorted.map((v) => Math.abs(v.value ?? v)), 1)
  const x = scaleLinear([0, max], [0, width / 2 - 4])
  const rowHeight = height / (sorted.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={HAIRLINE} />
    {sorted.map((row, i) => {
      const value = row.value ?? row; const w = x(Math.abs(value)); const cx = width / 2
      const tone = value >= 0 ? INK : BREACH
      const d = generator.rectangle(value >= 0 ? cx : cx - w, i * rowHeight + 2, w, rowHeight - 4, { stroke: tone, fill: tone, fillStyle: 'hachure', roughness: 0.9, seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
