import { describe, expect, it } from 'vitest'
import { performanceMetricTone } from './PerformanceMetrics.jsx'

describe('performance metric tones', () => {
  it('marks high ratios as good and weak ratios as bad', () => {
    expect(performanceMetricTone('sharpe', 0.75)).toBe('positive')
    expect(performanceMetricTone('sharpe', -0.1)).toBe('negative')
    expect(performanceMetricTone('sharpe', 0.25)).toBe('neutral')
  })

  it('treats drawdowns closer to zero as good', () => {
    expect(performanceMetricTone('maxDrawdown', -8)).toBe('positive')
    expect(performanceMetricTone('maxDrawdown', -25)).toBe('negative')
  })
})
