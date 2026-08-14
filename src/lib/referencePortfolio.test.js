import { describe, expect, it } from 'vitest'
import { planReferencePortfolioSync, REFERENCE_PORTFOLIO } from './referencePortfolio'

describe('planReferencePortfolioSync', () => {
  it('treats the brokerage export as authoritative while preserving a known purchase date', () => {
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
      shares: 0.1,
      costBasis: 983,
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

  it('does not include the retired DECJ reference holding', () => {
    expect(REFERENCE_PORTFOLIO.some((position) => position.ticker === 'DECJ')).toBe(false)
  })

  it('removes holdings that are absent from the authoritative export', () => {
    const operations = planReferencePortfolioSync([
      { id: 'AAA-manual', ticker: 'AAA', shares: 1 },
    ], [{ ticker: 'BBB', shares: 2, costBasis: 10, snapshotPrice: 12 }])

    expect(operations.map((operation) => operation.kind)).toEqual(['add', 'remove'])
    expect(operations[1].id).toBe('AAA-manual')
  })

  it('matches the invested-only Aug 14 Fidelity totals', () => {
    expect(REFERENCE_PORTFOLIO).toHaveLength(39)
    expect(REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.costBasisTotal, 0)).toBeCloseTo(4550, 8)
    expect(REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.snapshotValue, 0)).toBeCloseTo(4660.51, 8)
    expect(REFERENCE_PORTFOLIO.some((position) => ['FZFXX', 'Pending activity'].includes(position.ticker))).toBe(false)
  })
})
