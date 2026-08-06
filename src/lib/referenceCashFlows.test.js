import { describe, expect, it } from 'vitest'
import { fidelityProjectionBaseline, FIDELITY_CASH_FLOWS, FIDELITY_REFERENCE_SNAPSHOT, summarizeCashFlows } from './referenceCashFlows.js'

describe('Fidelity reference cash history', () => {
  it('matches the complete user-provided deposit and withdrawal screenshots', () => {
    expect(FIDELITY_CASH_FLOWS).toHaveLength(9)
    expect(new Set(FIDELITY_CASH_FLOWS.map((row) => row.id)).size).toBe(9)
    expect(summarizeCashFlows()).toEqual({ deposits: 2780, withdrawals: 200, netContributions: 2580, pendingDeposits: 100 })
  })

  it('reconciles the supplied account snapshot without confusing it with time-weighted return', () => {
    expect(FIDELITY_REFERENCE_SNAPSHOT.totalAccountValue - summarizeCashFlows().netContributions).toBeCloseTo(238.41, 2)
    expect(FIDELITY_REFERENCE_SNAPSHOT.periodReturns).toEqual({ '1D': 1.4, '1M': 4.45, YTD: 14.6, '1Y': 32.32 })
  })

  it('publishes the supplied brokerage returns as projection target evidence', () => {
    expect(fidelityProjectionBaseline([{ snapshotSource: 'User-provided brokerage snapshot' }])).toMatchObject({
      annualizedReturn: 0.3232,
      annualizedReturnPct: 32.32,
      source: 'brokerage-reported',
      returnTargetEvidence: {
        lowerPct: 14.6,
        lowerLabel: 'Fidelity year-to-date return',
        upperPct: 32.32,
        upperLabel: 'Fidelity trailing 1-year return',
      },
    })
    expect(fidelityProjectionBaseline([])).toBeNull()
  })
})
