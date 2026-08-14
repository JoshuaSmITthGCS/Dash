import { describe, expect, it } from 'vitest'
import { afterHoursPortfolioReturn, liveTodayPortfolioReturn } from './afterHoursQuotes'

describe('afterHoursPortfolioReturn', () => {
  it('reports unavailable when no held position has a post-market quote', () => {
    const result = afterHoursPortfolioReturn(
      [{ ticker: 'AAPL', shares: 10 }],
      { AAPL: { price: 227.5 } },
    )
    expect(result.available).toBe(false)
  })

  it('sums dollar moves across positions with a post-market quote', () => {
    const result = afterHoursPortfolioReturn(
      [{ ticker: 'AAPL', shares: 10 }, { ticker: 'MSFT', shares: 5 }],
      {
        AAPL: { price: 227.5, postMarketPrice: 229.8, postMarketChange: 2.3, postMarketChangePercent: 1.011 },
        MSFT: { price: 410, postMarketPrice: 407, postMarketChange: -3, postMarketChangePercent: -0.73 },
      },
    )
    expect(result.available).toBe(true)
    expect(result.dollarReturn).toBeCloseTo(10 * 2.3 + 5 * -3, 6)
    expect(result.coverage).toBe(2)
    expect(result.tickers).toEqual(['AAPL', 'MSFT'])
  })

  it('excludes positions with no post-market quote rather than treating them as flat', () => {
    const result = afterHoursPortfolioReturn(
      [{ ticker: 'AAPL', shares: 10 }, { ticker: 'VTI', shares: 4 }],
      { AAPL: { price: 227.5, postMarketPrice: 229.8, postMarketChange: 2.3 }, VTI: { price: 300 } },
    )
    expect(result.available).toBe(true)
    expect(result.coverage).toBe(1)
    expect(result.dollarReturn).toBeCloseTo(23, 6)
  })

  it('computes a percent return only when every included row has a prior value', () => {
    const withPrior = afterHoursPortfolioReturn(
      [{ ticker: 'AAPL', shares: 10 }],
      { AAPL: { postMarketPrice: 229.8, postMarketChange: 2.3 } },
    )
    expect(withPrior.returnPct).toBeCloseTo((2.3 / 227.5) * 100, 4)

    const withoutPrior = afterHoursPortfolioReturn(
      [{ ticker: 'AAPL', shares: 10 }],
      { AAPL: { postMarketChange: 2.3 } },
    )
    expect(withoutPrior.returnPct).toBeNull()
  })

  it('is case-insensitive matching quote keys to position tickers', () => {
    const result = afterHoursPortfolioReturn(
      [{ ticker: 'aapl', shares: 2 }],
      { AAPL: { postMarketPrice: 229.8, postMarketChange: 2.3 } },
    )
    expect(result.available).toBe(true)
    expect(result.dollarReturn).toBeCloseTo(4.6, 6)
  })
})

describe('liveTodayPortfolioReturn', () => {
  it('uses the exact imported position value and previous-close baseline before live quotes arrive', () => {
    const result = liveTodayPortfolioReturn([{
      ticker: 'AAA', shares: 2, snapshotPrice: 10.1, snapshotValue: 20.19,
      snapshotPreviousClose: 10,
    }], {
      AAA: { price: 10.1, previousClose: 10, positionSnapshot: true },
    })

    expect(result.available).toBe(true)
    expect(result.dollarReturn).toBeCloseTo(0.19, 8)
    expect(result.returnPct).toBeCloseTo(0.95, 8)
  })
})
