import { describe, expect, it, vi } from 'vitest'
import { fetchPortfolioQuotes } from './portfolio-prices.mjs'

function yahooResponse(chart) {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue({ chart: { result: [chart] } }),
  }
}

describe('fetchPortfolioQuotes', () => {
  it('derives post-market fields from extended-hours candles when Yahoo meta omits them', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(yahooResponse({
      meta: {
        regularMarketPrice: 100,
        regularMarketTime: 1_720_000_000,
        postMarketPrice: null,
        postMarketChange: null,
        postMarketChangePercent: null,
        currentTradingPeriod: { post: { start: 1_720_000_000, end: 1_720_014_400 } },
      },
      timestamp: [1_719_999_940, 1_720_000_060, 1_720_000_120],
      indicators: { quote: [{ close: [100, 101, 102.5] }] },
    }))

    const result = await fetchPortfolioQuotes(['AAPL'], fetchImpl)

    expect(result.quotes.AAPL).toMatchObject({
      price: 100,
      postMarketPrice: 102.5,
      postMarketChange: 2.5,
      postMarketChangePercent: 2.5,
      postMarketTime: new Date(1_720_000_120 * 1000).toISOString(),
    })
  })

  it('does not mistake a pre-market candle for an after-hours quote', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(yahooResponse({
      meta: {
        regularMarketPrice: 100,
        regularMarketTime: 1_720_000_000,
        currentTradingPeriod: { post: { start: 1_720_020_000, end: 1_720_034_400 } },
      },
      timestamp: [1_720_010_000],
      indicators: { quote: [{ close: [101] }] },
    }))

    const result = await fetchPortfolioQuotes(['AAPL'], fetchImpl)

    expect(result.quotes.AAPL).toMatchObject({
      postMarketPrice: null,
      postMarketChange: null,
      postMarketChangePercent: null,
      postMarketTime: null,
    })
  })
})
