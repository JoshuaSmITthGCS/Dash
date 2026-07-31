import { describe, expect, it } from 'vitest'
import { assessPortfolioExposure } from './portfolioExposure'

const position = (ticker, value, sector) => ({ ticker, currentValue: value, priceInfo: { sector } })

describe('assessPortfolioExposure', () => {
  it('flags a single position over the guideline', () => {
    const result = assessPortfolioExposure([
      position('AAPL', 3000, 'Technology'),
      position('KO', 500, 'Consumer Defensive'),
      position('JNJ', 500, 'Healthcare'),
    ])
    expect(result.warnings.some((w) => w.type === 'position' && w.label === 'AAPL')).toBe(true)
  })

  it('flags a sector over the guideline even split across tickers', () => {
    const result = assessPortfolioExposure([
      position('AAPL', 2000, 'Technology'),
      position('MSFT', 2000, 'Technology'),
      position('KO', 1000, 'Consumer Defensive'),
    ])
    const sectorWarning = result.warnings.find((w) => w.type === 'sector')
    expect(sectorWarning?.label).toBe('Technology')
  })

  it('stays quiet under a diversified split', () => {
    const result = assessPortfolioExposure([
      position('AAPL', 1000, 'Technology'),
      position('KO', 1000, 'Consumer Defensive'),
      position('JNJ', 1000, 'Healthcare'),
      position('XOM', 1000, 'Energy'),
      position('JPM', 1000, 'Financial Services'),
    ])
    expect(result.warnings).toEqual([])
  })

  it('handles an empty or unpriced portfolio', () => {
    expect(assessPortfolioExposure([])).toMatchObject({ totalValue: 0, warnings: [] })
    expect(assessPortfolioExposure([{ ticker: 'X', currentValue: null }])).toMatchObject({ totalValue: 0 })
  })
})
