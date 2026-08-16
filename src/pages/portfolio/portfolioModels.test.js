import { describe, expect, it } from 'vitest'
import {
  asValueSeries,
  buildBenchmarkModel,
  buildHoldingsModel,
  buildPriceModel,
  sliceSeriesBefore,
} from './portfolioModels.js'

const report = (overrides = {}) => ({
  generated_at: '2026-08-14T16:00:00.000Z',
  research: [{ ticker: 'AAPL', name: 'Apple', price: 200, score: 70, sector: 'Technology', history: { dates: ['2026-08-13', '2026-08-14'], closes: [190, 200] } }],
  portfolio_coverage: [],
  screen_universe: [],
  ...overrides,
})

describe('buildPriceModel', () => {
  it('prefers a quote refresh that is newer than the published report', () => {
    const model = buildPriceModel({
      data: report(),
      positions: [{ ticker: 'AAPL', shares: 2, costBasis: 100 }],
      quotes: { fetchedAt: '2026-08-14T19:00:00.000Z', quotes: { AAPL: { price: 205 }, SPY: { price: 600 } } },
    })

    expect(model.priceData.AAPL.price).toBe(205)
    expect(model.pricesUpdatedAt).toBe('2026-08-14T19:00:00.000Z')
    expect(model.benchmarkQuote).toMatchObject({ price: 600, portfolioQuote: true })
  })

  it('ignores a stale quote refresh and keeps the published price', () => {
    const model = buildPriceModel({
      data: report(),
      positions: [{ ticker: 'AAPL', shares: 2, costBasis: 100 }],
      quotes: { fetchedAt: '2026-08-13T19:00:00.000Z', quotes: { AAPL: { price: 205 }, SPY: { price: 600 } } },
    })

    expect(model.priceData.AAPL.price).toBe(200)
    expect(model.pricesUpdatedAt).toBe('2026-08-14T16:00:00.000Z')
    expect(model.benchmarkQuote).toBeNull()
  })
})

describe('buildHoldingsModel', () => {
  const positions = [{ id: 'a', ticker: 'aapl', shares: 2, costBasis: 100, purchaseDate: '2026-08-13' }]
  const priceData = { AAPL: { ticker: 'AAPL', name: 'Apple', price: 200, sector: 'Technology', history: { dates: ['2026-08-13', '2026-08-14'], closes: [190, 200] } } }

  it('enriches each position with value, gain, and allocation', () => {
    const model = buildHoldingsModel({ data: report(), positions, priceData, etfData: { etfs: [] } })

    expect(model.portfolioStats.totalCost).toBe(200)
    expect(model.portfolioStats.totalValue).toBe(400)
    expect(model.portfolioStats.totalGain).toBe(200)
    const [holding] = model.portfolioPositions
    expect(holding.ticker).toBe('AAPL')
    expect(holding.gainPct).toBe(100)
    expect(holding.allocationPct).toBe(100)
  })

  it('leaves value and gain null rather than zero when no price is known', () => {
    const model = buildHoldingsModel({ data: report(), positions, priceData: {}, etfData: { etfs: [] } })
    const [holding] = model.portfolioPositions

    expect(holding.currentValue).toBeNull()
    expect(holding.gain).toBeNull()
    expect(holding.gainPct).toBeNull()
    expect(holding.recommendation).toBeNull()
    expect(model.portfolioStats.totalValue).toBe(0)
  })

  it('splits allocation by role, keeping ETFs out of the stock buckets', () => {
    const model = buildHoldingsModel({
      data: report(),
      positions: [...positions, { id: 'b', ticker: 'SPY', shares: 1, costBasis: 500 }],
      priceData: { ...priceData, SPY: { ticker: 'SPY', price: 600, is_etf: true } },
      etfData: { etfs: [{ ticker: 'SPY' }] },
    })

    expect(Object.fromEntries(model.assetAllocation.map((row) => [row.label, row.value])))
      .toEqual({ 'Long-term stocks': 400, ETFs: 600 })
  })

  it('attaches guidance and a stop level to a priced holding, and lists only SELLs as actionable', () => {
    const model = buildHoldingsModel({ data: report(), positions, priceData, etfData: { etfs: [] } })
    const [holding] = model.portfolioPositions

    expect(holding.recommendation).toHaveProperty('action')
    expect(holding.stopLoss).not.toBeNull()
    expect(model.actionable).toEqual(model.portfolioPositions.filter((row) => row.recommendation?.action === 'SELL'))
  })

  it('falls back to a $500 hypothetical basis when the report omits one', () => {
    expect(buildHoldingsModel({ data: report(), positions, priceData, etfData: { etfs: [] } }).basis).toBe(500)
    expect(buildHoldingsModel({ data: report({ hypothetical_basis: 1000 }), positions, priceData, etfData: { etfs: [] } }).basis).toBe(1000)
  })
})

describe('buildBenchmarkModel', () => {
  const snapshotFor = (symbol) => ({
    ticker: symbol,
    price_series: {
      fund: [
        { date: '2026-08-13', adjusted_close: 100 },
        { date: '2026-08-14', adjusted_close: 101 },
      ],
    },
  })

  it('names the selected benchmark and keeps the four fit candidates', () => {
    const model = buildBenchmarkModel({
      data: report({ benchmark_analytics_history: { dates: ['2026-08-13'], values: [100], symbol: 'SPY' } }),
      snapshots: {
        spy: snapshotFor('SPY'), rsp: snapshotFor('RSP'), iwm: snapshotFor('IWM'), ijr: snapshotFor('IJR'),
        selected: snapshotFor('IWM'),
      },
    })

    expect(model.candidateInputs.map((row) => row.symbol)).toEqual(['SPY', 'RSP', 'IWM', 'IJR'])
    expect(model.selectedBenchmarkSymbol).toBe('IWM')
    expect(model.selectedBenchmarkLabel).toBe('Russell 2000')
  })

  it('falls back to the report series, then to SPY, when no snapshot is published', () => {
    const empty = { spy: null, rsp: null, iwm: null, ijr: null, selected: null }

    expect(buildBenchmarkModel({ data: report(), snapshots: empty }).selectedBenchmarkSymbol).toBe('SPY')
    expect(buildBenchmarkModel({ data: report(), snapshots: empty }).candidateInputs).toEqual([])
  })
})

describe('series helpers', () => {
  it('trims a value series to the most recent N points', () => {
    const series = asValueSeries({ dates: ['a', 'b', 'c'], values: [1, 2, 3] }, 2)

    expect(series).toMatchObject({ dates: ['b', 'c'], values: [2, 3], frequency: 'daily' })
  })

  it('reads a closes-shaped history as values', () => {
    expect(asValueSeries({ dates: ['a', 'b'], closes: [4, 5] }).values).toEqual([4, 5])
  })

  it('returns nothing for an empty history', () => {
    expect(asValueSeries(null)).toBeNull()
    expect(asValueSeries({ dates: [] })).toBeNull()
  })

  it('cuts a series off before a date, but only when two points survive', () => {
    const series = { dates: ['2026-01-01', '2026-01-02', '2026-01-03'], values: [1, 2, 3] }

    expect(sliceSeriesBefore(series, '2026-01-03')).toMatchObject({ dates: ['2026-01-01', '2026-01-02'], values: [1, 2] })
    expect(sliceSeriesBefore(series, '2026-01-02')).toBeNull()
  })
})
