import { canonicalArtifactState } from './states.js'

/** Canonical artifact state for a client-computed Monte Carlo simulation, which has no `signal_metrics.json` row of its own. */
export function projectionArtifactState(loading, result, error) {
  if (loading && !result) return canonicalArtifactState({ status: 'gated', disclaimer: 'Running the historical simulation off the main thread.' })
  if (error || !result?.available) return canonicalArtifactState({ status: 'unavailable', degraded_reason: error || result?.reason || 'Unavailable.' })
  return canonicalArtifactState({ status: 'success' })
}

/** Shared `fan` (CHART_TYPES) call for a `simulateProjection()` result -- used by the Finances
 * retirement tab, the Planning long-range outcome section, and Home's projection panel. */
export function fanChartCall(renderer, result, { metricId, ariaLabel, state, confidence }) {
  if (!renderer || !result?.fan?.length) return null
  return renderer.fan({
    metricId,
    series: result.fan.map((point) => ({ x: point.year, p10: point.p10, p25: point.p25, median: point.p50, p75: point.p75, p90: point.p90 })),
    unit: 'USD',
    thresholds: [],
    annotations: [],
    state,
    confidence,
    ariaLabel,
    width: 720,
    height: 260,
  })
}
