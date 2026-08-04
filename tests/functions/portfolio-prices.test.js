import { describe, expect, it, vi } from 'vitest'
import { fetchPortfolioQuotes, parseSymbols } from '../../netlify/functions/portfolio-prices.mjs'

describe('parseSymbols', () => {
  it('normalizes, validates, and deduplicates portfolio tickers', () => {
    expect(parseSymbols(JSON.stringify({
      symbols: [' vgt ', 'CRUS', 'vgt', '$BAD', '', 'MOG.A'],
    }))).toEqual(['VGT', 'CRUS', 'MOG.A'])
  })
})

describe('fetchPortfolioQuotes', () => {
  it('returns available quotes and reports individual provider failures', async () => {
    const fetchMock = vi.fn(async (url) => {
      if (url.includes('CRUS')) return { ok: false, status: 429 }
      return {
        ok: true,
        json: async () => ({ chart: { result: [{ meta: {
          regularMarketPrice: 119.29,
          chartPreviousClose: 115.14,
          regularMarketTime: 1_785_857_340,
          longName: 'Vanguard Information Technology ETF',
          currency: 'USD',
        } }] } }),
      }
    })

    const result = await fetchPortfolioQuotes(['VGT', 'CRUS'], fetchMock)

    expect(result.quotes.VGT).toMatchObject({
      ticker: 'VGT',
      price: 119.29,
      previousClose: 115.14,
      currency: 'USD',
    })
    expect(result.failed).toEqual([{ symbol: 'CRUS', error: 'quote provider returned 429' }])
  })

  it('uses Yahoo dash notation without changing the portfolio ticker', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ chart: { result: [{ meta: { regularMarketPrice: 50 } }] } }),
    }))

    const result = await fetchPortfolioQuotes(['MOG.A'], fetchMock)

    expect(fetchMock.mock.calls[0][0]).toContain('/MOG-A?')
    expect(result.quotes['MOG.A'].ticker).toBe('MOG.A')
  })
})
