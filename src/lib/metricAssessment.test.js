import { describe, expect, it } from 'vitest'
import {
  classifyCaptureProfile,
  classifyMetric,
  classifySignalToNoise,
  compareEvidencePeriods,
  evidenceCounts,
  metric,
  sectionAssessment,
} from './metricAssessment.js'

const measured = (input) => ({ observations: 300, minObservations: 20, frequency: 'daily', ...input })

describe('economic metric classification', () => {
  it('classifies Sharpe and drawdown by economic meaning', () => {
    expect(classifyMetric(measured({ id: 'sharpe', name: 'Sharpe', value: 1.1 })).assessment).toBe('positive')
    expect(classifyMetric(measured({ id: 'sharpe', name: 'Sharpe', value: 0.1 })).assessment).toBe('neutral')
    expect(classifyMetric(measured({ id: 'sharpe', name: 'Sharpe', value: -0.1 })).assessment).toBe('negative')
    expect(classifyMetric(measured({ id: 'maximum_drawdown', name: 'Maximum drawdown', value: -4 })).assessment).toBe('positive')
    expect(classifyMetric(measured({ id: 'maximum_drawdown', name: 'Maximum drawdown', value: -14 })).assessment).toBe('neutral')
    expect(classifyMetric(measured({ id: 'maximum_drawdown', name: 'Maximum drawdown', value: -30 })).assessment).toBe('negative')
  })

  it('reads capture as one combined profile', () => {
    expect(classifyCaptureProfile({ upCapture: 95, downCapture: 60, observations: 100 }).assessment).toBe('positive')
    expect(classifyCaptureProfile({ upCapture: 55, downCapture: 85, observations: 100 }).assessment).toBe('negative')
  })

  it('uses descriptive signal-to-noise bands, including direction', () => {
    expect(classifySignalToNoise({ value: 0.8, excessReturn: 3, observations: 20 }).assessment).toBe('neutral')
    expect(classifySignalToNoise({ value: 1.8, excessReturn: 3, observations: 20 }).assessment).toBe('positive')
    expect(classifySignalToNoise({ value: 2.1, excessReturn: -3, observations: 20 }).assessment).toBe('negative')
  })

  it('keeps Active Share neutral and bands tracking risk to its own baseline', () => {
    expect(classifyMetric({ id: 'active_share', name: 'Active share', value: 61, frequency: 'point', descriptive: true }).assessment).toBe('neutral')
    expect(classifyMetric(measured({ id: 'tracking_risk', name: 'Tracking risk', value: 9.2, baseline: 8.5 })).assessment).toBe('neutral')
  })

  it('gates small samples and rejects insignificant factor alpha after momentum and size', () => {
    const gated = classifyMetric({ id: 'sharpe', name: 'Sharpe', value: 2, observations: 19, minObservations: 20, frequency: 'daily' })
    expect(gated).toMatchObject({ assessment: 'insufficient', confidence: 'none' })
    expect(gated.insufficientReason).toContain('have 19')
    expect(classifyMetric(measured({ id: 'carhart4_alpha_t', name: 'Carhart alpha t', value: 1.9, alphaAnnualPct: 5 })).assessment).toBe('negative')
    expect(classifyMetric(measured({ id: 'carhart4_alpha_t', name: 'Carhart alpha t', value: 3.2, alphaAnnualPct: 5 })).assessment).toBe('positive')
  })

  it('does not call PSR below 95% positive', () => {
    expect(classifyMetric(measured({ id: 'psr', name: 'PSR', value: 0.94 })).assessment).not.toBe('positive')
    expect(classifyMetric(measured({ id: 'psr', name: 'PSR', value: 0.96 })).assessment).toBe('positive')
  })
})

describe('section invariants', () => {
  const rows = [
    metric({ id: 'sharpe', name: 'Sharpe', value: 1, family: 'return_efficiency', observations: 300, minObservations: 20 }),
    metric({ id: 'maximum_drawdown', name: 'Maximum drawdown', value: -30, family: 'drawdown_severity', observations: 300, minObservations: 20 }),
    metric({ id: 'psr', name: 'PSR', value: 0.4, family: 'statistical_confidence', observations: 300, minObservations: 20 }),
    metric({ id: 'tail_ratio', name: 'Tail ratio', value: null, family: 'tail_risk', observations: 0, minObservations: 20, missingInput: 'daily tail returns are required' }),
  ]

  it('reconciles raw status counts and excludes insufficient from weighted evidence', () => {
    const counts = evidenceCounts(rows)
    expect(counts.positive + counts.neutral + counts.negative + counts.insufficient).toBe(counts.total)
    const summary = sectionAssessment('standard', rows)
    expect(summary.weighted.positive + summary.weighted.neutral + summary.weighted.negative).toBeCloseTo(1, 12)
    expect(summary.counts.insufficient).toBe(1)
  })

  it('is deterministic and caps a positive section when statistical confidence is negative', () => {
    const otherwiseFavourable = [
      metric({ id: 'sharpe', name: 'Sharpe', value: 1, family: 'return_efficiency', observations: 300, minObservations: 20 }),
      metric({ id: 'maximum_drawdown', name: 'Maximum drawdown', value: -4, family: 'drawdown_severity', observations: 300, minObservations: 20 }),
      metric({ id: 'longest_underwater', name: 'Longest underwater', value: 10, family: 'drawdown_persistence', observations: 300, minObservations: 20, descriptive: true }),
      metric({ id: 'tail_ratio', name: 'Tail ratio', value: 1.4, family: 'tail_risk', observations: 300, minObservations: 20 }),
      metric({ id: 'psr', name: 'PSR', value: 0.4, family: 'statistical_confidence', observations: 300, minObservations: 20 }),
    ]
    const first = sectionAssessment('standard', otherwiseFavourable)
    const second = sectionAssessment('standard', otherwiseFavourable)
    expect(first).toEqual(second)
    expect(first.read).toBe('Inconclusive')
    expect(first.narrative).toBe(second.narrative)
  })

  it('compares only compatible sufficient period metrics without causal language', () => {
    const result = compareEvidencePeriods(rows, rows)
    expect(result.compared).toBe(3)
    expect(result.omitted).toBe(1)
    expect(result.label).toBe('Observed improvement since algorithm launch.')
  })
})
