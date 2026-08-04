import { describe, expect, it } from 'vitest'
import { FIDELITY_CASH_FLOWS, FIDELITY_REFERENCE_SNAPSHOT, summarizeCashFlows } from './referenceCashFlows.js'

describe('Fidelity reference cash history', () => {
  it('matches the complete user-provided deposit and withdrawal screenshots', () => {
    expect(FIDELITY_CASH_FLOWS).toHaveLength(9)
    expect(new Set(FIDELITY_CASH_FLOWS.map((row) => row.id)).size).toBe(9)
    expect(summarizeCashFlows()).toEqual({ deposits: 2880, withdrawals: 200, netContributions: 2680 })
  })

  it('reconciles the supplied account snapshot without confusing it with time-weighted return', () => {
    expect(FIDELITY_REFERENCE_SNAPSHOT.totalAccountValue - summarizeCashFlows().netContributions).toBeCloseTo(147.96, 2)
    expect(FIDELITY_REFERENCE_SNAPSHOT.periodReturns['1Y']).toBe(32.2)
  })
})
