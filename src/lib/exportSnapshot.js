// Assembles a single, self-describing JSON snapshot of everything on the Data overview page
// -- every holding, every performance/risk/benchmark/signal-quality metric, and the research
// pipeline's own tear sheet and forward projection -- for a user who wants to hand this to
// another AI assistant or external tool rather than read it as cards.
//
// Deliberately wholesale rather than hand-picked: reshaping field-by-field risks silently
// dropping a metric the next model needs, and "every single metric" was the ask. Every
// section below is one of this app's own already-assembled models, unchanged, just labeled.

import { ANALYTICS_SCOPES } from '../pages/portfolio/format.js'

// Round 7 Task 5: below this many observations, the performance block's headline ratios
// (Sharpe/Sortino/annualized return) are annualized off a sample too short to mean anything
// - the same export was shipping Sharpe 5.75 on 24 daily returns next to a deflated Sharpe
// of 0.238 with nothing telling a reader which to believe. Display-layer only: no number
// changes, the block just says so out loud. The floor is a reporting choice, not a
// statistical law - adjust here if a different threshold is preferred.
export const SAMPLE_SIZE_WARNING_FLOOR = 60

function annotateSmallSample(analytics) {
  const performance = analytics?.performance
  const observations = Number(performance?.observations)
  if (!performance || !Number.isFinite(observations) || observations >= SAMPLE_SIZE_WARNING_FLOOR) {
    return analytics || null
  }
  return {
    ...analytics,
    performance: {
      ...performance,
      sample_size_warning: `Computed from only ${observations} observations (reporting floor: `
        + `${SAMPLE_SIZE_WARNING_FLOOR}). Headline ratios in this block (Sharpe, Sortino, `
        + 'annualized return) are not yet statistically meaningful at this sample size. For the '
        + 'honest view, read deflated_sharpe and probabilistic_sharpe in signal_metrics_report, '
        + 'which account for sample length and the number of configurations tried.',
    },
  }
}

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
    portfolio_analytics: annotateSmallSample(analytics),
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
