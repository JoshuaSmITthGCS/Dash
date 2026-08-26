/**
 * Book's chart renderer — custom SVG, print conventions: thin 1px strokes, no fills, small-
 * multiple friendly (cheap, shared-scale). Annotation points carry a small numbered superscript
 * marker; the numbered footnote text renders beneath the plot within the same SVG, per DESIGN.md
 * §5's "daggers/superscripts on the plot" must-include.
 */
import { STATES } from '../../core/states.js'

const INK = 'var(--ink-primary)'
const FAINT = 'var(--ink-faint)'
const BREACH = 'var(--ink-editorial)'
const RULE = 'var(--rule-hairline)'

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

function Svg({ width = 240, height = 100, footnoteRows = 0, ariaLabel, children }) {
  const totalHeight = height + footnoteRows * 11
  return <svg width={width} height={totalHeight} viewBox={`0 0 ${width} ${totalHeight}`} role="img" aria-label={ariaLabel || 'chart'}>{children}</svg>
}

function Footnotes({ annotations = [], plotHeight }) {
  return annotations.map((a, i) => (
    <text key={i} x={4} y={plotHeight + 12 + i * 11} fontSize="9" fontFamily="var(--font-mono)" fill={INK}>
      {`${i + 1}. ${a.label}`}
    </text>
  ))
}

function Markers({ annotations = [], x, y }) {
  return annotations.map((a, i) => (
    <text key={i} x={x(a.x) + 3} y={y(a.y ?? 0) - 3} fontSize="8" fill={INK}>{i + 1}</text>
  ))
}

function line({ series, values, width = 240, height = 100, thresholds = [], annotations = [], state, ariaLabel, metricId }) {
  const data = seriesData(series, values)
  if (!data.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([0, data.length - 1], [8, width - 8])
  const y = scaleLinear([Math.min(...data), Math.max(...data)], [height - 8, 8])
  const points = data.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  return <Svg width={width} height={height} footnoteRows={annotations.length} ariaLabel={ariaLabel}>
    {thresholds.map((t, i) => <line key={i} x1={0} x2={width} y1={y(t.value)} y2={y(t.value)} stroke={RULE} strokeDasharray="1,2" />)}
    <polyline points={points} fill="none" stroke={toneFor(state)} strokeWidth="1" />
    <Markers annotations={annotations} x={x} y={y} metricId={metricId} />
    <Footnotes annotations={annotations} plotHeight={height} />
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
    <line x1={0} x2={width} y1={height - 2} y2={height - 2} stroke={RULE} />
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
    <line x1={0} x2={width} y1={height - 2} y2={height - 2} stroke={RULE} />
    {values.map(([a, b], i) => {
      const ha = y(Math.abs(a || 0)); const hb = y(Math.abs(b || 0)); const gx = i * gw
      return <g key={i}>
        <rect x={gx + 2} y={height - 2 - ha} width={gw / 2 - 4} height={ha} fill="none" stroke={INK} strokeWidth="1" />
        <rect x={gx + gw / 2 + 1} y={height - 2 - hb} width={gw / 2 - 4} height={hb} fill="none" stroke={FAINT} strokeWidth="1" strokeDasharray="2,1" />
      </g>
    })}
  </Svg>
}

function barTimeline(props) { return bar(props) }

function scatter({ series = [], width = 200, height = 200, state, ariaLabel }) {
  if (!series.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const xs = series.map((p) => p.x); const ys = series.map((p) => p.y)
  const x = scaleLinear([Math.min(...xs), Math.max(...xs)], [8, width - 8])
  const y = scaleLinear([Math.min(...ys), Math.max(...ys)], [height - 8, 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={RULE} />
    <line x1={width / 2} x2={width / 2} y1={8} y2={height - 8} stroke={RULE} />
    {series.map((p, i) => <circle key={i} cx={x(p.x)} cy={y(p.y)} r="2.5" fill="none" stroke={toneFor(state)} strokeWidth="1" />)}
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
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    {values.map((row, r) => row.map((v, c) => <rect key={`${r}-${c}`} x={c * cw} y={r * ch} width={cw - 1} height={ch - 1} fill="none" stroke={RULE} strokeWidth="1" />))}
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
    <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={RULE} strokeWidth="1" />
    <line x1={x(threshold.value)} x2={x(threshold.value)} y1={4} y2={height - 4} stroke={FAINT} strokeWidth="1" />
    <circle cx={x(value)} cy={height / 2} r="3" fill="none" stroke={toneFor(state)} strokeWidth="1" />
  </Svg>
}

function dotPlot({ values = [], width = 200, height = 60, ariaLabel }) {
  if (!values.length) return <Svg width={width} height={height} ariaLabel={ariaLabel} />
  const x = scaleLinear([Math.min(...values), Math.max(...values)], [8, width - 8])
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={8} x2={width - 8} y1={height / 2} y2={height / 2} stroke={RULE} />
    {values.map((v, i) => <circle key={i} cx={x(v)} cy={height / 2} r="2.5" fill="none" stroke={INK} strokeWidth="1" />)}
  </Svg>
}

function waterfall({ values = [], width = 240, height = 100, ariaLabel }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const y = scaleLinear([0, max], [0, height - 10])
  const bw = width / (values.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={0} x2={width} y1={height - 2} y2={height - 2} stroke={RULE} />
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
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={RULE} strokeWidth="1" />
    <circle cx={cx} cy={cy} r={r} fill="none" stroke={toneFor(state)} strokeWidth="2" strokeDasharray={`${circumference * fraction} ${circumference}`} transform={`rotate(-90 ${cx} ${cy})`} />
    <text x={cx} y={cy + 4} fontSize="10" textAnchor="middle" fill={INK} fontFamily="var(--font-mono)">{domain[0]}–{domain[1]}</text>
  </Svg>
}

function profile({ values = [], width = 200, height = 120, ariaLabel }) {
  const sorted = [...values].sort((a, b) => Math.abs(b.value ?? b) - Math.abs(a.value ?? a))
  const max = Math.max(...sorted.map((v) => Math.abs(v.value ?? v)), 1)
  const x = scaleLinear([0, max], [0, width / 2 - 4])
  const rowHeight = height / (sorted.length || 1)
  return <Svg width={width} height={height} ariaLabel={ariaLabel}>
    <line x1={width / 2} x2={width / 2} y1={0} y2={height} stroke={RULE} />
    {sorted.map((row, i) => {
      const value = row.value ?? row; const w = x(Math.abs(value)); const cx = width / 2
      return <rect key={i} x={value >= 0 ? cx : cx - w} y={i * rowHeight + 2} width={w} height={rowHeight - 4} fill="none" stroke={value >= 0 ? INK : BREACH} strokeWidth="1" />
    })}
  </Svg>
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
