import { describe, expect, it } from 'vitest'
import { nextPortfolioSort, sortPortfolioPositions } from './portfolioSort'

describe('portfolio sorting', () => {
  const positions = [
    { ticker: 'ZZZ', currentValue: null, gainPct: null, priceInfo: null },
    { ticker: 'AAA', currentValue: 50, gainPct: -2, priceInfo: { score: 40, name: 'Alpha' } },
    { ticker: 'BBB', currentValue: 200, gainPct: 12, priceInfo: { score: 80, name: 'Beta' } },
  ]

  it('sorts numeric columns and keeps unavailable values last', () => {
    expect(sortPortfolioPositions(positions, 'value', 'desc').map((row) => row.ticker))
      .toEqual(['BBB', 'AAA', 'ZZZ'])
  })

  it('defaults numbers to descending and toggles an active column', () => {
    expect(nextPortfolioSort({ key: 'ticker', direction: 'asc' }, 'score'))
      .toEqual({ key: 'score', direction: 'desc' })
    expect(nextPortfolioSort({ key: 'score', direction: 'desc' }, 'score'))
      .toEqual({ key: 'score', direction: 'asc' })
  })
})
