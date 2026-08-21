import { describe, expect, it } from 'vitest'
import { buildExportSnapshot, SAMPLE_SIZE_WARNING_FLOOR, snapshotFilename, snapshotToJson } from './exportSnapshot'

describe('buildExportSnapshot', () => {
  const baseArgs = {
    holdings: { portfolioPositions: [{ ticker: 'AAPL', shares: 10 }], actionable: [{ ticker: 'AAPL' }] },
    analytics: { performance: { sharpe: 1.2 } },
    benchmarks: { selectedBenchmarkLabel: 'S&P 500' },
    signalMetrics: { metrics: [{ id: 'pbo', value: 0.2 }] },
    monteCarlo: { status: 'ready' },
    scope: 'since_algorithm',
  }

  it('carries every section through unchanged', () => {
    const snapshot = buildExportSnapshot(baseArgs)
    expect(snapshot.holdings.positions).toEqual(baseArgs.holdings.portfolioPositions)
    expect(snapshot.holdings.actionable_tickers).toEqual(['AAPL'])
    expect(snapshot.portfolio_analytics).toBe(baseArgs.analytics)
    expect(snapshot.benchmark_comparisons).toBe(baseArgs.benchmarks)
    expect(snapshot.signal_metrics_report).toBe(baseArgs.signalMetrics)
    expect(snapshot.monte_carlo_projection).toBe(baseArgs.monteCarlo)
  })

  it('stamps a sample_size_warning on a performance block with too few observations (Round 7 Task 5)', () => {
    // The real defect case: Sharpe 5.75 / Sortino 12.46 / 89.8% annualized on 24
    // observations shipping in the same file as deflated Sharpe 0.238, unannotated.
    const analytics = {
      performance: { available: true, observations: 24, sharpe: 5.75, sortino: 12.46, annualizedReturn: 89.8 },
      statistics: { available: true },
    }
    const snapshot = buildExportSnapshot({ ...baseArgs, analytics })
    const performance = snapshot.portfolio_analytics.performance
    expect(performance.sample_size_warning).toContain('only 24 observations')
    expect(performance.sample_size_warning).toContain('not yet statistically meaningful')
    expect(performance.sample_size_warning).toContain('deflated_sharpe')
    // Display-only: every number is untouched, and sibling blocks keep their identity.
    expect(performance.sharpe).toBe(5.75)
    expect(performance.sortino).toBe(12.46)
    expect(performance.annualizedReturn).toBe(89.8)
    expect(snapshot.portfolio_analytics.statistics).toBe(analytics.statistics)
  })

  it('leaves a performance block at or above the floor unannotated', () => {
    const analytics = { performance: { available: true, observations: SAMPLE_SIZE_WARNING_FLOOR, sharpe: 1.1 } }
    const snapshot = buildExportSnapshot({ ...baseArgs, analytics })
    expect(snapshot.portfolio_analytics).toBe(analytics)
    expect(snapshot.portfolio_analytics.performance.sample_size_warning).toBeUndefined()
  })

  it('does not invent a warning when there is no performance block or no observation count', () => {
    expect(buildExportSnapshot({ ...baseArgs, analytics: null }).portfolio_analytics).toBeNull()
    const noCount = { performance: { available: false, reason: 'daily portfolio returns are required' } }
    expect(buildExportSnapshot({ ...baseArgs, analytics: noCount }).portfolio_analytics).toBe(noCount)
  })

  it('labels the currently selected scope in plain language', () => {
    const snapshot = buildExportSnapshot(baseArgs)
    expect(snapshot.analytics_scope).toEqual({ id: 'since_algorithm', label: 'Since algorithm activation' })
  })

  it('defaults to all-history when no scope is given', () => {
    const snapshot = buildExportSnapshot({ ...baseArgs, scope: undefined })
    expect(snapshot.analytics_scope.id).toBe('all_history')
  })

  it('tolerates missing holdings or analytics rather than throwing', () => {
    const snapshot = buildExportSnapshot({})
    expect(snapshot.holdings.positions).toEqual([])
    expect(snapshot.portfolio_analytics).toBeNull()
  })

  it('stamps an ISO export timestamp and a stated purpose', () => {
    const snapshot = buildExportSnapshot(baseArgs)
    expect(() => new Date(snapshot.exported_at).toISOString()).not.toThrow()
    expect(snapshot.export_purpose).toMatch(/AI assistant/)
  })
})

describe('snapshotFilename', () => {
  it('is a safe filename carrying the scope and today\'s date', () => {
    const name = snapshotFilename('since_algorithm')
    expect(name).toMatch(/^valuesignal-metrics-since_algorithm-\d{4}-\d{2}-\d{2}\.json$/)
  })

  it('falls back to all_history when no scope is given', () => {
    expect(snapshotFilename(undefined)).toMatch(/^valuesignal-metrics-all_history-/)
  })
})

describe('snapshotToJson', () => {
  it('produces parseable JSON', () => {
    const json = snapshotToJson({ a: 1, b: [1, 2, 3] })
    expect(JSON.parse(json)).toEqual({ a: 1, b: [1, 2, 3] })
  })

  it('replaces non-finite numbers with null rather than emitting invalid JSON', () => {
    const json = snapshotToJson({ value: Infinity, other: NaN, fine: 1.5 })
    expect(JSON.parse(json)).toEqual({ value: null, other: null, fine: 1.5 })
  })
})
