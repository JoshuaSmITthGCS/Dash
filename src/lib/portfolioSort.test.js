import { describe, expect, it } from 'vitest'
import { getOutlook } from './outlook'
import { nextPortfolioSort, sortPortfolioPositions } from './portfolioSort'

describe('portfolio outlook', () => {
  it.each([
    [20, 'Very Bearish'],
    [30, 'Bearish'],
    [40, 'Leaning Bearish'],
    [50, 'Neutral'],
    [60, 'Leaning Bullish'],
    [70, 'Bullish'],
    [80, 'Very Bullish'],
  ])('maps score %s to %s', (score, label) => {
    expect(getOutlook(score)?.label).toBe(label)
  })

  it('does not invent an outlook when a score is unavailable', () => {
    expect(getOutlook(null)).toBeNull()
  })
})

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

  it('sorts by the seven-level outlook', () => {
    expect(sortPortfolioPositions(positions, 'outlook', 'asc').map((row) => row.ticker))
      .toEqual(['AAA', 'BBB', 'ZZZ'])
  })

  it('defaults numbers to descending and toggles an active column', () => {
    expect(nextPortfolioSort({ key: 'ticker', direction: 'asc' }, 'score'))
      .toEqual({ key: 'score', direction: 'desc' })
    expect(nextPortfolioSort({ key: 'score', direction: 'desc' }, 'score'))
      .toEqual({ key: 'score', direction: 'asc' })
  })
})

