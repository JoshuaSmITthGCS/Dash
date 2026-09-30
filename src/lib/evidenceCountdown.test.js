import { describe, expect, it } from 'vitest'
import { evidenceMilestones } from './evidenceCountdown'

const signalMetrics = {
  metrics: [
    { id: 'omega', group: 'distribution', label: 'Omega ratio', observations: 35, required_observations: 120 },
    { id: 'skew', group: 'distribution', label: 'Skew', observations: 35, required_observations: 120 },
    { id: 'feature_psi', group: 'monitoring', label: 'PSI', observations: 45, required_observations: 60 },
    { id: 'live_vs_backtest_ic', group: 'monitoring', observations: 0, required_observations: 24 },
  ],
}
const inputs = {
  today: '2026-09-30',
  timeToValidMetric: { available: true, met: false, observations: 51, floor: 60, estimatedDate: '2026-10-13' },
  signalMetrics,
  factor: { available: false, observations: 0, requiredObservations: 24 },
  prospective: { harness_start_date: '2026-09-01', expected_completion_at_monthly_frequency: '2028-09-01' },
}

describe('evidenceMilestones', () => {
  it('dates every pending milestone and sorts soonest first', () => {
    const { pending } = evidenceMilestones(inputs)
    expect(pending.map((row) => row.id)).toEqual([
      'prospective_first_ic', 'headline_ratios', 'feature_psi', 'distribution_shape',
      'prospective_icir', 'account_factor_loadings',
    ])
    const byId = Object.fromEntries(pending.map((row) => [row.id, row]))
    expect(byId.headline_ratios.estimatedDate).toBe('2026-10-13')
    expect(byId.prospective_first_ic.estimatedDate).toBe('2026-10-01')
    expect(byId.prospective_icir.estimatedDate).toBe('2028-09-01')
    expect(byId.feature_psi.estimatedDate).toBe('2026-10-21')
    expect(byId.distribution_shape.unlocks).toBe('Omega ratio, Skew')
  })

  it('moves a reached floor to met and flags a passed estimate as overdue', () => {
    const { met, pending } = evidenceMilestones({
      ...inputs,
      today: '2026-10-20',
      timeToValidMetric: { available: true, observations: 60, floor: 60 },
    })
    expect(met.map((row) => row.id)).toContain('headline_ratios')
    expect(pending.find((row) => row.id === 'prospective_first_ic').overdue).toBe(true)
  })

  it('returns nothing to show when no report is loaded', () => {
    expect(evidenceMilestones({ today: '2026-09-30' }).pending).toEqual([])
  })
})
