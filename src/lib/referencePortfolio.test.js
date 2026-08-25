import { describe, expect, it } from 'vitest'
import {
  planReferencePortfolioSync,
  REFERENCE_PORTFOLIO,
  REFERENCE_PORTFOLIO_RECORDED_AT,
} from './referencePortfolio'

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

  it('matches the invested-only Aug 25 Fidelity totals', () => {
    expect(REFERENCE_PORTFOLIO).toHaveLength(46)
    expect(REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.costBasisTotal, 0)).toBeCloseTo(5549.26, 8)
    expect(REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.snapshotValue, 0)).toBeCloseTo(5668.16, 8)
    expect(REFERENCE_PORTFOLIO.some((position) => ['FZFXX', 'Pending activity'].includes(position.ticker))).toBe(false)
  })

  // The seven the Aug 14 baseline did not have. Their combined cost basis is the exact
  // difference between the two exports ($5,549.26 - $4,550.00), and the transaction history
  // shows all seven bought on Aug 21 -- after that snapshot, not dropped from it.
  it('carries the holdings bought after the Aug 14 baseline', () => {
    const restored = ['AMP', 'AMZN', 'DELL', 'ETN', 'MPC', 'THC', 'TWLO']
    const byTicker = new Map(REFERENCE_PORTFOLIO.map((position) => [position.ticker, position]))

    restored.forEach((ticker) => expect(byTicker.get(ticker)).toBeDefined())
    expect(restored.reduce((sum, ticker) => sum + byTicker.get(ticker).costBasisTotal, 0))
      .toBeCloseTo(999.26, 8)
    expect(REFERENCE_PORTFOLIO
      .filter((position) => !restored.includes(position.ticker))
      .reduce((sum, position) => sum + position.costBasisTotal, 0)).toBeCloseTo(4550, 8)
  })

  // Acquisition dates come from the account's transaction history. The export date says only
  // when these prices were observed, and writing it to a purchaseDate would backdate or
  // forward-date every holding and corrupt every since-purchase measure that reads it.
  describe('purchase dates come from the transaction history, never the export date', () => {
    it('dates an added holding from the history rather than the export', () => {
      const [operation] = planReferencePortfolioSync([], [{
        ticker: 'AMZN', shares: 0.386, costBasis: 258.52, purchaseDate: '2026-08-21',
        snapshotPrice: 262.0725, snapshotRecordedAt: REFERENCE_PORTFOLIO_RECORDED_AT,
      }])

      expect(operation.kind).toBe('add')
      expect(operation.record.purchaseDate).toBe('2026-08-21')
      expect(operation.record.snapshotRecordedAt).toBe(REFERENCE_PORTFOLIO_RECORDED_AT)
    })

    it('leaves an added holding undated when the history does not reach it', () => {
      const [operation] = planReferencePortfolioSync([], [{
        ticker: 'VOO', shares: 0.146, costBasis: 633.36, purchaseDate: null,
        snapshotPrice: 701.8493,
      }])

      expect(operation.record.purchaseDate).toBe('')
    })

    it('lets a date already stored win over the history', () => {
      const [operation] = planReferencePortfolioSync([{
        id: 'twlo-1', ticker: 'TWLO', shares: 0.5, costBasis: 180, purchaseDate: '2026-03-02',
      }], [{ ticker: 'TWLO', shares: 0.906, costBasis: 220.63, purchaseDate: '2026-08-21' }])

      expect(operation.record.purchaseDate).toBe('2026-03-02')
      expect(operation.record.shares).toBe(0.906) // every other field still overwritten
    })

    it('backfills a holding stored without a date', () => {
      const [operation] = planReferencePortfolioSync([{
        id: 'thc-reference', ticker: 'THC', shares: 0.719, costBasis: 278.11, purchaseDate: '',
      }], [{ ticker: 'THC', shares: 0.719, costBasis: 278.11, purchaseDate: '2026-08-21' }])

      expect(operation.record.purchaseDate).toBe('2026-08-21')
    })

    it('never dates a shipped holding from the export day', () => {
      const exportDay = REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 10)
      REFERENCE_PORTFOLIO.forEach((position) => {
        expect(position.purchaseDate).not.toBe(exportDay)
        if (position.purchaseDate !== null) {
          expect(position.purchaseDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
          expect(position.purchaseDate < exportDay).toBe(true)
        }
      })
    })

    // BSX and VOO were bought before the supplied history window, so they are the only two
    // that stay undated -- a guessed date would be worse than no date.
    it('dates 44 of the 46 holdings and names the two it cannot', () => {
      const undated = REFERENCE_PORTFOLIO.filter((position) => position.purchaseDate === null)
      expect(undated.map((position) => position.ticker)).toEqual(['BSX', 'VOO'])
    })

    // The seven the Aug 14 baseline lacked were bought Aug 21, a week after it was taken --
    // they were never missing from it, and their buys are exactly the cost-basis difference.
    it('dates the seven holdings absent from the Aug 14 baseline to their Aug 21 buys', () => {
      const augustTwentyFirst = REFERENCE_PORTFOLIO
        .filter((position) => position.purchaseDate === '2026-08-21')
      expect(augustTwentyFirst.map((position) => position.ticker))
        .toEqual(['AMP', 'AMZN', 'DELL', 'ETN', 'MPC', 'THC', 'TWLO'])
      expect(augustTwentyFirst.reduce((sum, position) => sum + position.costBasisTotal, 0))
        .toBeCloseTo(999.26, 8)
    })
  })

  // Fidelity's positions view reports quantity, cost and value but no previous close, so the
  // per-share price is derived. Guarding the round-trip keeps a mistyped quantity or value
  // from silently producing a position that reprices wrongly.
  it('derives a per-share price that reproduces the exported market value', () => {
    REFERENCE_PORTFOLIO.forEach((position) => {
      expect(position.snapshotPrice * position.shares).toBeCloseTo(position.snapshotValue, 2)
      expect(position.costBasis * position.shares).toBeCloseTo(position.costBasisTotal, 8)
      expect(position.snapshotPreviousClose).toBeNull()
    })
  })
})
