import { describe, expect, it } from 'vitest'
import {
  buildPortfolioPriceData,
  mergePortfolioQuotes,
  normalizePortfolioPosition,
  PER_SHARE_COST,
} from './portfolioPosition'

describe('buildPortfolioPriceData', () => {
  it('uses screen-universe quotes as fallback and prefers full research', () => {
    const screen = [
      { ticker: 'EXPE', price: 298.03, score: 70.4 },
      { ticker: 'CRUS', price: 120 },
    ]
    const research = [{ ticker: 'CRUS', price: 127.33, score: 84.3 }]

    const result = buildPortfolioPriceData(screen, [], research)

    expect(result.EXPE.price).toBe(298.03)
    expect(result.CRUS).toEqual(research[0])
  })
})

describe('mergePortfolioQuotes', () => {
  it('overlays only the price fields while preserving full research data', () => {
    const research = {
      CRUS: { ticker: 'CRUS', name: 'Cirrus Logic', price: 127.33, score: 84.3, history: { closes: [1, 2] } },
    }

    const result = mergePortfolioQuotes(research, {
      CRUS: { ticker: 'CRUS', price: 131.45, previousClose: 127.33, marketTime: '2026-08-04T15:09:19Z' },
    })

    expect(result.CRUS).toMatchObject({
      price: 131.45,
      previousClose: 127.33,
      score: 84.3,
      portfolioQuote: true,
    })
    expect(result.CRUS.history).toEqual({ closes: [1, 2] })
  })
})

describe('normalizePortfolioPosition', () => {
  it('uses the Firestore document id instead of a stale embedded id', () => {
    const { position } = normalizePortfolioPosition('real-document-id', {
      id: 'stale-id', ticker: 'AAPL', shares: 1, costBasis: 100,
    })

    expect(position.id).toBe('real-document-id')
  })

  it.each([
    ['EXPE', 0.164, 50],
    ['CRUS', 1.344, 175.67],
    ['VGT', 1.692, 200],
  ])('repairs the known legacy total-cost record for %s', (ticker, shares, totalCost) => {
    const { position, firestoreUpdates } = normalizePortfolioPosition(`${ticker}-id`, {
      ticker, shares, costBasis: totalCost,
    })

    expect(position.costBasis).toBeCloseTo(totalCost / shares)
    expect(position.costBasisUnit).toBe(PER_SHARE_COST)
    expect(position.costBasisInputMode).toBe('total')
    expect(firestoreUpdates).toMatchObject({ costBasisUnit: PER_SHARE_COST })
  })

  it('does not reinterpret unrelated or explicitly normalized positions', () => {
    const unrelated = normalizePortfolioPosition('one', {
      ticker: 'AAPL', shares: 0.5, costBasis: 200,
    })
    const normalized = normalizePortfolioPosition('two', {
      ticker: 'VGT', shares: 1.692, costBasis: 200, costBasisUnit: PER_SHARE_COST,
    })

    expect(unrelated.position.costBasis).toBe(200)
    expect(unrelated.firestoreUpdates).toBeNull()
    expect(normalized.position.costBasis).toBe(200)
    expect(normalized.firestoreUpdates).toBeNull()
  })
})
