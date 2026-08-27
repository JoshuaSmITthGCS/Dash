/**
 * Chalkboard's chart renderer — chalk strokes via rough.js. Roughness/bowing are bound to the
 * metric's `confidenceOf()` level (DESIGN.md §9: heavy, confident strokes for high confidence,
 * light and sketchy for low) — a variable distinct from the four-state encoding, mirroring
 * LabelFrame's chalk-pressure device. Axes/gridlines are drawn with the same rough.js generator
 * (never a perfectly straight `<line>`), per the "freehand axes, ruled but never perfectly
 * straight" must-include. Arrow annotations render as rough.js arrow strokes. Every stroke is
 * seeded from `seedFor(metricId)` so screenshots never churn.
 */
import rough from 'roughjs/bundled/rough.cjs'
import { STATES } from '../../core/states.js'
import { seedFor } from '../../core/seed.js'

const CHALK = 'var(--chalk-white)'
const FAINT = 'var(--ink-faint)'
const ALERT = 'var(--chalk-alert)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return ALERT
  if (state?.state === STATES.UNAVAILABLE) return FAINT
  return CHALK
}

// Confidence, not state, drives stroke weight and roughness — a low-confidence established
// metric still draws faint, per DESIGN.md's explicit distinction from "accumulating".
function roughnessFor(confidence) {
  const level = confidence?.level ?? 1
  return 0.6 + (1 - level) * 2.2
}

function strokeWidthFor(confidence) {
  const level = confidence?.level ?? 1
  return 1 + level * 1.5
}

function intSeed(id) {
  return Math.floor(seedFor(id || 'chalkboard')() * 2 ** 31) || 1
}

const generator = rough.generator()

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

function freehandAxis(x1, y1, x2, y2, seedKey) {
  return generator.line(x1, y1, x2, y2, { stroke: FAINT, strokeWidth: 1, roughness: 1.4, seed: intSeed(seedKey) })
}

function arrowAnnotation(x1, y1, x2, y2, seedKey) {
  const shaft = generator.line(x1, y1, x2, y2, { stroke: CHALK, strokeWidth: 1.5, roughness: 1.2, seed: intSeed(seedKey) })
  const angle = Math.atan2(y2 - y1, x2 - x1)
  const headLen = 6
  const h1 = generator.line(x2, y2, x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6), { stroke: CHALK, roughness: 1.2, seed: intSeed(`${seedKey}-h1`) })
  const h2 = generator.line(x2, y2, x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6), { stroke: CHALK, roughness: 1.2, seed: intSeed(`${seedKey}-h2`) })
  return [shaft, h1, h2]
}

function Annotations({ annotations = [], x, y, metricId }) {
  return annotations.map((a, i) => {
    if (a.kind === 'arrow' && a.toX != null) {
      return arrowAnnotation(x(a.x), y(a.y ?? 0), x(a.toX), y(a.toY ?? a.y ?? 0), `${metricId}-arrow-${i}`)
        .map((d, j) => <RoughPaths key={`${i}-${j}`} drawable={d} />)
    }
    if (a.kind === 'circle') {
      const d = generator.circle(x(a.x), y(a.y ?? 0), 10, { stroke: ALERT, roughness: 1, seed: intSeed(`${metricId}-circle-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    }
    if (a.kind === 'underline') {
      const d = generator.line(x(a.x) - 8, y(a.y ?? 0) + 6, x(a.x) + 8, y(a.y ?? 0) + 6, { stroke: CHALK, roughness: 1, seed: intSeed(`${metricId}-underline-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    }
    return null
  })
}

function Svg({ width = 240, height = 100, ariaLabel, children }) {
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>{children}</svg>
}

function line({ series, values, width = 240, height = 100, thresholds = [], annotations, state, confidence, ariaLabel, metricId }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [8, width - 8])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 8, 8])
  const points = data.map((v, i) => [x(i), y(v)])
  const drawable = generator.curve(points, { stroke: toneFor(state), strokeWidth: strokeWidthFor(confidence), roughness: roughnessFor(confidence), seed: intSeed(metricId), bowing: roughnessFor(confidence) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(8, height - 8, width - 8, height - 8, `${metricId}-axis-x`)} />
    {thresholds.map((t, i) => <RoughPaths key={i} drawable={freehandAxis(0, y(t.value), width, y(t.value), `${metricId}-threshold-${i}`)} />)}
    <RoughPaths drawable={drawable} />
    <Annotations annotations={annotations} x={x} y={y} metricId={metricId} />
  </Svg>
}

function sparkline({ series, values, width = 60, height = 20, state, confidence, ariaLabel, metricId }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [2, width - 2])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 2, 2])
  const points = data.map((v, i) => [x(i), y(v)])
  const drawable = generator.curve(points, { stroke: toneFor(state), strokeWidth: strokeWidthFor(confidence) * 0.7, roughness: roughnessFor(confidence) * 0.6, seed: intSeed(metricId) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}><RoughPaths drawable={drawable} /></Svg>
}

function bar({ values = [], width = 240, height = 100, state, confidence, ariaLabel, metricId }) {
  const max = Math.max(...values.map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height - 10])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(0, height - 2, width, height - 2, `${metricId}-axis`)} />
    {values.map((v, i) => {
      const h = y(Math.abs(v))
      const d = generator.rectangle(i * bw + 3, height - 2 - h, bw - 6, h, { stroke: toneFor(state), fill: toneFor(state), fillStyle: 'hachure', roughness: roughnessFor(confidence), seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function pairedBar({ values = [], width = 240, height = 100, confidence, ariaLabel, metricId }) {
  const max = Math.max(...values.flat().map(Math.abs), 1)
  const y = scaleLinear([0, max], [0, height - 10])
  const gw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(0, height - 2, width, height - 2, `${metricId}-axis`)} />
    {values.map(([a, b], i) => {
      const ha = y(Math.abs(a || 0)); const hb = y(Math.abs(b || 0)); const gx = i * gw
      const da = generator.rectangle(gx + 2, height - 2 - ha, gw / 2 - 4, ha, { stroke: CHALK, fill: CHALK, fillStyle: 'hachure', roughness: roughnessFor(confidence), seed: intSeed(`${metricId}-a-${i}`) })
      const db = generator.rectangle(gx + gw / 2 + 1, height - 2 - hb, gw / 2 - 4, hb, { stroke: FAINT, fill: FAINT, fillStyle: 'hachure', roughness: roughnessFor(confidence), seed: intSeed(`${metricId}-b-${i}`) })
      return <g key={i}><RoughPaths drawable={da} /><RoughPaths drawable={db} /></g>
    })}
  </Svg>
}

function barTimeline(props) { return bar(props) }

function scatter({ series = [], width = 200, height = 200, state, confidence, ariaLabel, metricId }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x); const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [8, width - 8])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 8, 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(8, height / 2, width - 8, height / 2, `${metricId}-axis-x`)} />
    <RoughPaths drawable={freehandAxis(width / 2, 8, width / 2, height - 8, `${metricId}-axis-y`)} />
    {series.map((p, i) => {
      const d = generator.circle(x(p.x), y(p.y), 8, { stroke: toneFor(state), fill: toneFor(state), fillStyle: 'solid', roughness: roughnessFor(confidence), seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function composition({ values = [], width = 200, height = 24, ariaLabel, metricId }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  const tones = [CHALK, FAINT, ALERT]
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((v, i) => {
      const value = Math.max(0, v.value ?? v); const w = (value / total) * width
      const d = generator.rectangle(cursor, 0, w, height, { stroke: tones[i % tones.length], fill: tones[i % tones.length], fillStyle: 'hachure', roughness: 0.9, seed: intSeed(`${metricId}-${i}`) })
      cursor += w
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function heatmap({ values = [], width = 160, height = 160, ariaLabel }) {
  const rows = values.length || 1; const cols = values[0]?.length || 1
  const cw = width / cols; const ch = height / rows
  const flat = values.flat(); const max = Math.max(...flat.map(Math.abs), 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((row, r) => row.map((v, c) => <rect key={`${r}-${c}`} x={c * cw} y={r * ch} width={cw - 1} height={ch - 1} fill={CHALK} opacity={Math.abs(v) / max} />))}
  </Svg>
}

function fan({ series = [], width = 240, height = 100, confidence, ariaLabel, metricId }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, series.length - 1], [4, width - 4])
  const points = series.map((p, i) => [x(i), height - (p.median ?? 0.5) * height])
  const d = generator.curve(points, { stroke: CHALK, strokeWidth: strokeWidthFor(confidence), roughness: roughnessFor(confidence), seed: intSeed(metricId) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(4, height - 4, width - 4, height - 4, `${metricId}-axis`)} />
    <RoughPaths drawable={d} />
  </Svg>
}

function bullet({ values = [], thresholds = [], width = 200, height = 28, state, ariaLabel, metricId }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const x = scaleLinear(domain, [4, width - 4])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(4, height / 2, width - 4, height / 2, `${metricId}-axis`)} />
    <line x1={x(threshold.value)} x2={x(threshold.value)} y1={4} y2={height - 4} stroke={ALERT} strokeWidth="2" strokeDasharray="2,2" />
    <circle cx={x(value)} cy={height / 2} r="5" fill={toneFor(state)} />
  </Svg>
}

function dotPlot({ values = [], width = 200, height = 60, ariaLabel, metricId }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [8, width - 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(8, height / 2, width - 8, height / 2, `${metricId}-axis`)} />
    {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r="4" fill={CHALK} />)}
  </Svg>
}

function waterfall({ values = [], width = 240, height = 100, confidence, ariaLabel, metricId }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height - 10])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(0, height - 2, width, height - 2, `${metricId}-axis`)} />
    {values.map((v, i) => {
      const start = cumulative; cumulative += v
      const top = height - 2 - y(Math.max(start, cumulative)); const h = Math.max(1, y(Math.abs(v)))
      const tone = v >= 0 ? CHALK : ALERT
      const d = generator.rectangle(i * bw + 2, top, bw - 4, h, { stroke: tone, fill: tone, fillStyle: 'hachure', roughness: roughnessFor(confidence), seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

function dial({ values = [], domain = [0, 1], width = 120, height = 120, state, confidence, ariaLabel, metricId }) {
  const value = values[0] ?? 0
  const fraction = Math.max(0, Math.min(1, (value - domain[0]) / ((domain[1] - domain[0]) || 1)))
  const r = width / 2 - 10
  const cx = width / 2; const cy = height / 2
  const circumference = 2 * Math.PI * r
  const outline = generator.circle(cx, cy, r * 2, { stroke: FAINT, roughness: roughnessFor(confidence), seed: intSeed(metricId) })
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={outline} />
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={toneFor(state)} strokeWidth="4" strokeDasharray={`${circumference * fraction} ${circumference}`} transform={`rotate(-90 ${cx} ${cy})`} opacity="0.9" />
    <text x={cx} y={cy + 4} fontSize="10" textAnchor="middle" fill={CHALK} fontFamily="var(--font-mono)">{domain[0]}–{domain[1]}</text>
  </Svg>
}

function profile({ values = [], width = 200, height = 120, confidence, ariaLabel, metricId }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const max = Math.max(...sorted.map((v) => Math.abs(v.value ?? v)), 1)
  const x = scaleLinear([0, max], [0, width / 2 - 4])
  const rowHeight = height / (sorted.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <RoughPaths drawable={freehandAxis(width / 2, 0, width / 2, height, `${metricId}-axis`)} />
    {sorted.map((row, i) => {
      const value = row.value ?? row; const w = x(Math.abs(value)); const cx = width / 2
      const tone = value >= 0 ? CHALK : ALERT
      const d = generator.rectangle(value >= 0 ? cx : cx - w, i * rowHeight + 2, w, rowHeight - 4, { stroke: tone, fill: tone, fillStyle: 'hachure', roughness: roughnessFor(confidence), seed: intSeed(`${metricId}-${i}`) })
      return <RoughPaths key={i} drawable={d} />
    })}
  </Svg>
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
