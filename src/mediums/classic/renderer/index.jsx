/**
 * Classic's chart renderer — a thin adapter layer mapping the shared `chartContract` props onto
 * the existing hand-rolled SVG components' own APIs, rather than rewriting them (DESIGN.md §12
 * chart renderer + performance plan). Where an existing generic-enough component exists it is
 * imported and reused directly; the four types with no existing generic-shaped primitive (bar,
 * composition, bullet, waterfall) are small new implementations using the existing token set
 * (`var(--positive)`/`var(--negative)`/`var(--surface-tertiary)`, etc.) rather than a new chart
 * library — see NOTES.md for the direct-reuse-vs-new-but-token-consistent split.
 */
import GrowthChartImpl from '../../../components/GrowthChart.jsx'
import SparklineImpl from '../../../components/Sparkline.jsx'
import PairedBarChartImpl from '../../../components/PairedBarChart.jsx'
import BarTimelineImpl from '../../../components/BarTimeline.jsx'
import ScatterChartImpl from '../../../components/ScatterChart.jsx'
import ProjectionFanChartImpl from '../../../components/ProjectionFanChart.jsx'
import DotPlotImpl from '../../../components/DotPlot.jsx'
import ScoreGaugeImpl from '../../../components/ScoreGauge.jsx'
import CorrelationHeatmapImpl from '../../../components/CorrelationHeatmap.jsx'
import ResearchRadarChartImpl from '../../../components/ResearchRadarChart.jsx'
import { ratio, money } from '../../../lib/formatters.js'
import { STATES } from '../../core/states.js'

const POSITIVE = 'var(--positive)'
const NEGATIVE = 'var(--negative)'
const NEUTRAL = 'var(--text-secondary)'
const SURFACE = 'var(--surface-tertiary)'

function toneFor(state) {
  if (state?.state === STATES.BREACHED) return NEGATIVE
  if (state?.state === STATES.UNAVAILABLE) return NEUTRAL
  return POSITIVE
}

function seriesData(series = [], values = []) { return series.length ? series.map((p) => p.y ?? p.value) : values }

/** GrowthChart wants `dates` + `series: [{values, label, color}]` — adapts the shared flat shape. */
function line({ series = [], values, ariaLabel, state }) {
  const data = seriesData(series, values)
  if (!data.length) return null
  const dates = series.length ? series.map((p, i) => p.x ?? String(i)) : data.map((_, i) => String(i))
  // GrowthChartImpl requires a per-series `color` (no internal default — its own real callers
  // always pass one); omitting it left the SVG stroke unset, which a11y.spec.mjs's chart-ink
  // contrast check caught rendering as literal black against Classic's near-black background.
  return <GrowthChartImpl dates={dates} series={[{ values: data, label: ariaLabel || 'value', color: toneFor(state) }]} valueFormatter={ratio} minimal />
}

function sparkline({ series, values, ariaLabel }) {
  const data = seriesData(series, values)
  return <SparklineImpl values={data} label={ariaLabel || 'trend'} height={40} />
}

/** No exact single-series bar primitive exists generically — a small new SVG using existing tokens. */
function bar({ values = [], width = 240, height = 100, state, ariaLabel }) {
  const max = Math.max(...values.map(Math.abs), 1)
  const bw = width / (values.length || 1)
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'chart'}>
      {values.map((v, i) => {
        const h = (Math.abs(v) / max) * (height - 10)
        return <rect key={i} x={i * bw + 2} y={height - 2 - h} width={bw - 4} height={h} fill={toneFor(state)} rx="2" />
      })}
    </svg>
  )
}

function pairedBar({ values = [], ariaLabel }) {
  const groups = values.map((pair, i) => ({ label: String(i), values: Array.isArray(pair) ? pair : [pair] }))
  return <PairedBarChartImpl groups={groups} yFormatter={ratio} caption={ariaLabel} />
}

function barTimeline({ values = [], ariaLabel }) {
  const points = values.map((v, i) => ({ label: String(i), value: v }))
  return <BarTimelineImpl points={points} yFormatter={ratio} caption={ariaLabel} />
}

function scatter({ series = [], ariaLabel, quadrant, legend, xLabel, yLabel }) {
  return <ScatterChartImpl points={series} xFormatter={ratio} yFormatter={ratio} caption={ariaLabel} quadrant={quadrant} legend={legend} xLabel={xLabel} yLabel={yLabel} />
}

/** No generic allocation/composition primitive exists — a small new stacked bar using existing tokens. */
function composition({ values = [], width = 200, height = 24, ariaLabel }) {
  const total = values.reduce((sum, v) => sum + Math.max(0, v.value ?? v), 0) || 1
  let cursor = 0
  const tones = [POSITIVE, NEUTRAL, NEGATIVE]
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'composition'}>
      {values.map((v, i) => { const value = Math.max(0, v.value ?? v); const w = (value / total) * width; const r = <rect key={i} x={cursor} width={w} height={height} fill={tones[i % tones.length]} />; cursor += w; return r })}
    </svg>
  )
}

function heatmap({ values = [], labels, ariaLabel }) {
  const tickers = labels?.length === values.length ? labels : values.map((_, i) => `#${i + 1}`)
  return <CorrelationHeatmapImpl tickers={tickers} matrix={values} observations={values.length} caption={ariaLabel} />
}

// ProjectionFanChartImpl requires a value formatter with no default -- unit-aware here since
// callers publish both USD projections (retirement/Home) and bare ratios (Monte Carlo terminal
// multiples, unit 'x'), and a dollar sign on a 1.02x multiple would misrepresent the value.
function fan({ series = [], unit }) {
  // ProjectionFanChartImpl's axis labels read `.year` directly (never derives it from `.month`)
  // -- every fan caller now sets it explicitly (see fanChart.js/PortfolioScreen.jsx), `p.x`
  // remains a fallback only for a caller that hasn't. `.days` is optional -- only the Monte
  // Carlo panel's sub-year horizons set it, so its points label "30d"/"90d" instead of every
  // point under a year rounding down to the same "Year 0".
  const points = series.map((p, i) => ({ month: p.x ?? i, year: p.year ?? p.x ?? i, days: p.days, p10: p.p10 ?? p.low, p50: p.median ?? p.y, p90: p.p90 ?? p.high }))
  const formatValue = unit === 'USD' ? money : (value) => `${ratio(value)}${unit ? unit : ''}`
  return <ProjectionFanChartImpl fan={points} money={formatValue} />
}

/** No exact bullet primitive exists generically — a small new SVG using the existing token set. */
function bullet({ values = [], thresholds = [], width = 200, height = 28, state, ariaLabel }) {
  const value = values[0] ?? 0
  const threshold = thresholds.find((t) => t.kind === 'kill')
  if (threshold == null) return null
  const domain = [Math.min(0, value, threshold.value), Math.max(value, threshold.value) * 1.2 || 1]
  const scale = (v) => 4 + ((v - domain[0]) / ((domain[1] - domain[0]) || 1)) * (width - 8)
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'bullet chart'}>
      <line x1={4} x2={width - 4} y1={height / 2} y2={height / 2} stroke={SURFACE} strokeWidth="4" />
      <line x1={scale(threshold.value)} x2={scale(threshold.value)} y1={4} y2={height - 4} stroke={NEGATIVE} strokeWidth="2" />
      <circle cx={scale(value)} cy={height / 2} r="6" fill={toneFor(state)} />
    </svg>
  )
}

function dotPlot({ values = [], ariaLabel }) {
  const rows = values.map((v, i) => ({ id: i, label: String(i), value: v }))
  return <DotPlotImpl rows={rows} xFormatter={ratio} caption={ariaLabel} />
}

/** No exact waterfall primitive with the shared generic prop shape exists — a small new SVG. */
function waterfall({ values = [], width = 240, height = 100, ariaLabel }) {
  let cumulative = 0
  const max = values.reduce((sum, v) => sum + Math.abs(v), 0) || 1
  const bw = width / (values.length || 1)
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel || 'waterfall'}>
      {values.map((v, i) => {
        const start = cumulative; cumulative += v
        const y = (val) => height - ((val / max) * (height - 10))
        const top = y(Math.max(start, cumulative)); const h = Math.max(1, Math.abs(y(start) - y(cumulative)))
        return <rect key={i} x={i * bw + 2} y={top} width={bw - 4} height={h} fill={v >= 0 ? POSITIVE : NEGATIVE} rx="2" />
      })}
    </svg>
  )
}

function dial({ values = [], ariaLabel, state }) {
  const score = Math.max(0, Math.min(100, values[0] ?? 0))
  return <ScoreGaugeImpl score={score} available={state?.state !== STATES.UNAVAILABLE} label={ariaLabel || ''} provisional={state?.state === STATES.ACCUMULATING} />
}

/**
 * `profile` replaces the banned radar chart everywhere except here: Classic is grandfathered
 * (see NOTES.md and the master's own banned-list self-audit exception) because the existing
 * `ResearchRadarChart` is a ported, unmodified component, not new work. Adapts the shared
 * `values: [{label, value}]` shape into the `stock.fundamental_categories` object it expects.
 */
function profile({ values = [] }) {
  const fundamental_categories = Object.fromEntries(values.map((v, i) => [v.label ?? `factor_${i}`, v.value ?? v]))
  return <ResearchRadarChartImpl stock={{ fundamental_categories }} />
}

export default { line, sparkline, bar, pairedBar, barTimeline, scatter, composition, heatmap, fan, bullet, dotPlot, waterfall, dial, profile }
