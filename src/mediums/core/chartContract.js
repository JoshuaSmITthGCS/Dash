/**
 * The shared chart-renderer interface. One interface, twelve implementations — see
 * DESIGN.md's "Chart renderer + performance plan" per theme for what each medium does with it.
 *
 * A medium's manifest exposes `loadRenderer: () => Promise<Renderer>`; a Renderer is an object
 * with one key per CHART_TYPES entry, each a component-like render function. `validateRenderer`
 * is what Phase 3's renderer-distinctness assertion (and any medium's own tests) run against a
 * loaded renderer to confirm nothing is missing.
 *
 * Radar is deliberately absent — banned in every theme (root doc's banned list). The
 * factor-loading profile use case (`ResearchRadarChart` today) is served by `profile` instead:
 * a sorted bar/dot profile of the same loadings, in whatever material the medium uses for bars.
 */
export const CHART_TYPES = Object.freeze([
  'line',        // GrowthChart, TWR-vs-benchmark
  'sparkline',    // inline rows — never used as decorative texture
  'bar',          // sorted comparison
  'pairedBar',    // champion vs challenger, side by side
  'barTimeline',  // monthly/periodic volume
  'scatter',      // quadrant screens (structural vs tactical, drawdown vs return)
  'composition',  // allocation — stacked bar or treemap form (donut retired: 3+ slices banned)
  'heatmap',      // correlation, sector/market heatmap — value-suppressing uncertainty palette
  'fan',          // projection / Monte Carlo fan chart
  'bullet',       // value vs kill_threshold on one scale
  'dotPlot',      // backtest coverage dot plots
  'waterfall',    // score waterfall (Stock Detail Sheet)
  'dial',         // score dial / gauge — MUST render a labeled scale, never a bare gauge
  'profile',      // factor-loading profile — replaces the banned radar chart
])

/**
 * Common props every renderer's chart types accept. Not enforced by the JS runtime (this is a
 * doc-as-code contract, not a prop-types schema) but every medium's renderer functions should
 * destructure from this shape so `core/screens/*` never needs medium-specific branches.
 *
 * {
 *   metricId,                          // stable id, feeds seedFor() for any material randomness
 *   series | values,                   // the data itself
 *   domain, unit,
 *   thresholds: [{ value, label, kind: 'kill' | 'target' | 'band' }],
 *   annotations: [{ x, y, kind: 'circle' | 'underline' | 'arrow' | 'event', label }],  // REQUIRED
 *                                       // by the standing "annotation required" rule whenever a
 *                                       // threshold or explaining event exists for the series
 *   state,                             // a CanonicalState from core/states.js — encode, never re-derive
 *   confidence,                        // a Confidence from core/states.js — encode via the medium's
 *                                       // own channel, never hue, never blur-over-interval
 *   ariaLabel, width, height, onPointTap,
 * }
 */
export const CHART_COMMON_PROP_KEYS = Object.freeze([
  'metricId', 'domain', 'unit', 'thresholds', 'annotations', 'state', 'confidence',
  'ariaLabel', 'width', 'height', 'onPointTap',
])

/**
 * Confirms a loaded renderer implements every contract type. Returns { valid, missing }.
 * Used by each medium's own smoke test and by the Phase 3 renderer-distinctness assertion.
 */
export function validateRenderer(renderer) {
  const missing = CHART_TYPES.filter((type) => typeof renderer?.[type] !== 'function')
  return { valid: missing.length === 0, missing }
}

/**
 * `toTable(props)` — the "charts offer a table-view toggle" rule, implemented once in core
 * rather than twelve times. Returns a plain-object row shape a medium's DataTable-equivalent
 * (or the shared `DataTable` component, reused as an allowlisted primitive) can render directly.
 * Deliberately data-only — no JSX here, so it stays usable from a plain .js test.
 */
export function toTableRows({ series = [], values = [] } = {}) {
  if (Array.isArray(series) && series.length) {
    return series.map((point, index) => ({
      index,
      x: point?.x ?? point?.date ?? point?.label ?? index,
      y: point?.y ?? point?.value ?? point,
    }))
  }
  return values.map((value, index) => ({ index, x: index, y: value }))
}
