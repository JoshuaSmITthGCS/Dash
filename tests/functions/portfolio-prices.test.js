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

  it('requests extended-hours data and passes through post-market fields when present', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ chart: { result: [{ meta: {
        regularMarketPrice: 227.5,
        chartPreviousClose: 224.1,
        postMarketPrice: 229.8,
        postMarketChange: 2.3,
        postMarketChangePercent: 1.011,
      } }] } }),
    }))

    const result = await fetchPortfolioQuotes(['AAPL'], fetchMock)

    expect(fetchMock.mock.calls[0][0]).toContain('includePrePost=true')
    expect(result.quotes.AAPL).toMatchObject({
      postMarketPrice: 229.8,
      postMarketChange: 2.3,
      postMarketChangePercent: 1.011,
    })
  })

  it('leaves post-market fields null during regular hours, rather than reporting a false 0 move', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ chart: { result: [{ meta: { regularMarketPrice: 50 } }] } }),
    }))

    const result = await fetchPortfolioQuotes(['VTI'], fetchMock)

    expect(result.quotes.VTI.postMarketPrice).toBeNull()
    expect(result.quotes.VTI.postMarketChange).toBeNull()
    expect(result.quotes.VTI.postMarketChangePercent).toBeNull()
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
