import { describe, expect, it } from 'vitest'
import { nextPortfolioSort, sortPortfolioPositions } from './portfolioSort'

describe('portfolio sorting', () => {
  const positions = [
    { ticker: 'ZZZ', currentValue: null, allocationPct: null, gainPct: null, priceInfo: null },
    { ticker: 'AAA', currentValue: 50, allocationPct: 20, gainPct: -2, priceInfo: { score: 40, name: 'Alpha' } },
    { ticker: 'BBB', currentValue: 200, allocationPct: 80, gainPct: 12, priceInfo: { score: 80, name: 'Beta' } },
  ]

  it('sorts numeric columns and keeps unavailable values last', () => {
    expect(sortPortfolioPositions(positions, 'value', 'desc').map((row) => row.ticker))
      .toEqual(['BBB', 'AAA', 'ZZZ'])
  })

  it('sorts holdings by allocation descending by default', () => {
    expect(sortPortfolioPositions(positions, 'allocation', 'desc').map((row) => row.ticker))
      .toEqual(['BBB', 'AAA', 'ZZZ'])
  })

  it('sorts holdings by rating and keeps unrated positions last', () => {
    const rated = [
      { ticker: 'FLAT', rating: 0 },
      { ticker: 'WORST', rating: -5 },
      { ticker: 'BEST', rating: 5 },
      { ticker: 'UNRATED', rating: null },
    ]
    expect(sortPortfolioPositions(rated, 'rating', 'desc').map((row) => row.ticker))
      .toEqual(['BEST', 'FLAT', 'WORST', 'UNRATED'])
  })

  it('sorts position signals by action severity', () => {
    const signals = [
      { ticker: 'HOLD', recommendation: { action: 'HOLD' } },
      { ticker: 'SELL', recommendation: { action: 'SELL' } },
      { ticker: 'WATCH', recommendation: { action: 'WATCH' } },
    ]

    expect(sortPortfolioPositions(signals, 'signal', 'desc').map((row) => row.ticker))
      .toEqual(['SELL', 'WATCH', 'HOLD'])
  })

  it('defaults numbers to descending and toggles an active column', () => {
    expect(nextPortfolioSort({ key: 'ticker', direction: 'asc' }, 'score'))
      .toEqual({ key: 'score', direction: 'desc' })
    expect(nextPortfolioSort({ key: 'score', direction: 'desc' }, 'score'))
      .toEqual({ key: 'score', direction: 'asc' })
  })
})
