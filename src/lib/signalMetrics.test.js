import { describe, expect, it } from 'vitest'
import { sampleProgress } from './signalMetrics'

describe('sampleProgress', () => {
  it('shows progress toward the floor while accumulating', () => {
    expect(sampleProgress({ observations: 12, required_observations: 24 })).toBe('12 of 24 observations')
  })

  it('drops the denominator once the floor is met', () => {
    expect(sampleProgress({ observations: 57, required_observations: 24 })).toBe('57 observations')
  })

  it('handles metrics with no floor or no count', () => {
    expect(sampleProgress({ observations: 5, required_observations: null })).toBe('5 observations')
    expect(sampleProgress({ observations: null })).toBeNull()
  })
})
