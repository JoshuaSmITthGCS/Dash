import { describe, expect, it } from 'vitest'
import { planReferencePortfolioSync } from './referencePortfolio'

describe('planReferencePortfolioSync', () => {
  it('refreshes snapshot fields without replacing user position data', () => {
    const positions = [{
      id: 'MU-existing',
      ticker: 'MU',
      shares: 2,
      costBasis: 90,
      purchaseDate: '2026-01-10',
    }]
    const reference = [{
      ticker: 'MU',
      shares: 0.1,
      costBasis: 983,
      snapshotPrice: 105,
      snapshotSource: 'Brokerage snapshot',
    }]

    const [operation] = planReferencePortfolioSync(positions, reference)

    expect(operation.kind).toBe('update')
    expect(operation.id).toBe('MU-existing')
    expect(operation.record).toMatchObject({
      shares: 2,
      costBasis: 90,
      purchaseDate: '2026-01-10',
      snapshotPrice: 105,
      snapshotSource: 'Brokerage snapshot',
    })
  })

  it('matches ticker case without changing the brokerage symbol', () => {
    const positions = [{ id: 'DECJ-reference', ticker: 'decj', shares: 1, costBasis: 100 }]
    const reference = [{ ticker: 'DECJ', snapshotPrice: 110, snapshotSource: 'Brokerage snapshot' }]

    const [operation] = planReferencePortfolioSync(positions, reference)

    expect(operation.kind).toBe('update')
    expect(operation.id).toBe('DECJ-reference')
    expect(operation.record.ticker).toBe('DECJ')
  })
})
