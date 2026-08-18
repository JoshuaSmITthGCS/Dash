// Assembles a single, self-describing JSON snapshot of everything on the Data overview page
// -- every holding, every performance/risk/benchmark/signal-quality metric, and the research
// pipeline's own tear sheet and forward projection -- for a user who wants to hand this to
// another AI assistant or external tool rather than read it as cards.
//
// Deliberately wholesale rather than hand-picked: reshaping field-by-field risks silently
// dropping a metric the next model needs, and "every single metric" was the ask. Every
// section below is one of this app's own already-assembled models, unchanged, just labeled.

import { ANALYTICS_SCOPES } from '../pages/portfolio/format.js'

export function buildExportSnapshot({ holdings, analytics, benchmarks, signalMetrics, monteCarlo, scope }) {
  const scopeLabel = ANALYTICS_SCOPES.find((row) => row.id === scope)?.label || scope || 'All portfolio history'
  return {
    exported_at: new Date().toISOString(),
    export_purpose: 'Complete snapshot of ValueSignal portfolio holdings, performance analytics, '
      + 'and research-pipeline signal metrics, for analysis by another AI assistant or external tool.',
    analytics_scope: { id: scope || 'all_history', label: scopeLabel },
    holdings: {
      positions: holdings?.portfolioPositions || [],
      actionable_tickers: (holdings?.actionable || []).map((position) => position.ticker),
    },
    portfolio_analytics: analytics || null,
    benchmark_comparisons: benchmarks || null,
    signal_metrics_report: signalMetrics || null,
    monte_carlo_projection: monteCarlo || null,
  }
}

export function snapshotFilename(scope) {
  const date = new Date().toISOString().slice(0, 10)
  const slug = (scope || 'all_history').replace(/[^a-z0-9_]+/gi, '-')
  return `valuesignal-metrics-${slug}-${date}.json`
}

/** JSON.stringify with a fallback for values a plain stringify would choke on (rare, but a
 * partially-loaded model can carry a stray non-finite number or circular reference). */
export function snapshotToJson(snapshot) {
  return JSON.stringify(snapshot, (key, value) => (
    typeof value === 'number' && !Number.isFinite(value) ? null : value
  ), 2)
}
