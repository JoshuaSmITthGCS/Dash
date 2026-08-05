import { describe, expect, it } from 'vitest'
import {
  actualRecordedValueSeries,
  benchmarkAlternative,
  benchmarkCloseOn,
  fixedBasisAlternative,
  portfolioFixedBasisVsBenchmark,
  portfolioGrowthSeries,
  portfolioVsBenchmark,
  positionGrowthSeries,
  selectPortfolioHistorySeries,
} from './portfolioPerformance'

const HISTORY = {
  dates: ['2025-01-06', '2025-04-07', '2025-07-07', '2025-10-06', '2026-01-05'],
  closes: [400, 420, 450, 480, 500],
}

describe('actualRecordedValueSeries', () => {
  it('uses the last observation per market date and reports covered settled flows', () => {
    const result = actualRecordedValueSeries([
      { marketDate: '2026-01-02', recordedAt: '2026-01-02T15:00:00Z', value: 100 },
      { marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z', value: 105 },
      { marketDate: '2026-01-03', recordedAt: '2026-01-03T20:00:00Z', value: 120 },
    ], [
      { type: 'deposit', effectiveDate: '2026-01-03', amount: 10 },
      { type: 'deposit', effectiveDate: '2026-01-03', amount: 5, status: 'processing' },
    ])
    expect(result.values).toEqual([105, 120])
    expect(result.settledFlows).toHaveLength(1)
  })

  it('uses the recorded timestamp date when an older snapshot has no market date', () => {
    const result = actualRecordedValueSeries([
      { recordedAt: '2026-01-02T20:00:00Z', value: 105 },
      { recordedAt: '2026-01-03T20:00:00Z', value: 120 },
    ])
    expect(result.dates).toEqual(['2026-01-02', '2026-01-03'])
  })
})

describe('selectPortfolioHistorySeries', () => {
  const backtest = { dates: ['a', 'b'], values: [100, 110] }
  const actual = { dates: ['a', 'b', 'c'], values: [100, 105, 112] }

  it('defaults to the series with greater observation coverage and discloses the choice', () => {
    const result = selectPortfolioHistorySeries(backtest, actual)
    expect(result.mode).toBe('actual')
    expect(result.series).toBe(actual)
    expect(result.defaulted).toBe(true)
    expect(result.note).toContain('Defaulted to Your actual recorded value')
  })

  it('honors an available user selection even when the other series has more coverage', () => {
    const result = selectPortfolioHistorySeries(backtest, actual, 'backtest')
    expect(result.mode).toBe('backtest')
    expect(result.series).toBe(backtest)
    expect(result.defaulted).toBe(false)
  })

  it('uses the backtested series as the disclosed tie breaker', () => {
    const result = selectPortfolioHistorySeries(backtest, { dates: ['a', 'b'], values: [100, 109] })
    expect(result.mode).toBe('backtest')
    expect(result.note).toContain('tie breaker')
  })
})

describe('benchmarkCloseOn', () => {
  it('uses the last close at or before the purchase date', () => {
    expect(benchmarkCloseOn(HISTORY, '2025-05-20')).toBe(420)
    expect(benchmarkCloseOn(HISTORY, '2025-07-07')).toBe(450)
  })

  it('returns nothing for a date before the window rather than guessing', () => {
    expect(benchmarkCloseOn(HISTORY, '2024-06-01')).toBeNull()
  })
})

describe('benchmarkAlternative', () => {
  it('prices the same dollars into the index on the same day', () => {
    const position = { shares: 10, costBasis: 40, purchaseDate: '2025-01-06' }
    const alternative = benchmarkAlternative(position, HISTORY)
    expect(alternative.invested).toBe(400)
    // 400 / 400 = 1 index share, now worth 500.
    expect(alternative.value).toBe(500)
    expect(alternative.gainPct).toBeCloseTo(25, 5)
  })

  it('declines to compare a purchase that predates the window', () => {
    const position = { shares: 10, costBasis: 40, purchaseDate: '2020-01-01' }
    expect(benchmarkAlternative(position, HISTORY)).toBeNull()
  })
})

describe('portfolioVsBenchmark', () => {
  it('totals only the positions it can honestly compare', () => {
    const positions = [
      { shares: 10, costBasis: 40, purchaseDate: '2025-01-06', currentValue: 600 },
      { shares: 5, costBasis: 20, purchaseDate: '2019-01-01', currentValue: 300 },
    ]
    const result = portfolioVsBenchmark(positions, HISTORY)
    expect(result.comparable).toBe(1)
    expect(result.invested).toBe(400)
    expect(result.holdingsValue).toBe(600)
    expect(result.benchmarkValue).toBe(500)
    expect(result.dollarsAhead).toBe(100)
    expect(result.excessReturnPct).toBeCloseTo(25, 5)
  })

  it('returns nothing when no position falls inside the window', () => {
    const positions = [{ shares: 1, costBasis: 1, purchaseDate: '2000-01-01', currentValue: 5 }]
    expect(portfolioVsBenchmark(positions, HISTORY)).toBeNull()
  })
})

describe('portfolioGrowthSeries', () => {
  const priceData = {
    AAA: { history: { closes: [100, 110, 120, 130, 140] } },
    ZZZ: { history: { closes: [10, 11] } }, // wrong length: not on the shared grid
  }

  it('values the holdings from their purchase date and matches the same dated contribution', () => {
    const positions = [
      { ticker: 'AAA', shares: 2, costBasis: 100, purchaseDate: '2025-01-06' },
      { ticker: 'ZZZ', shares: 5, costBasis: 10, purchaseDate: '2025-01-06' },
    ]
    const series = portfolioGrowthSeries(positions, priceData, HISTORY)
    expect(series.holdings).toEqual([200, 220, 240, 260, 280])
    expect(series.benchmark[0]).toBe(200)
    // The index rose 25% over the window, so the same starting dollars end at 250.
    expect(series.benchmark[4]).toBeCloseTo(250, 5)
    expect(series.cash).toEqual([200, 200, 200, 200, 200])
    expect(series.trackedTickers).toEqual(['AAA'])
    expect(series.untrackedCount).toBe(1)
    expect(series.firstInvestmentDate).toBe('2025-01-06')
  })

  it('shows the real jump when a later contribution enters the portfolio', () => {
    const staggeredPrices = {
      AAA: { history: { closes: [100, 110, 120, 130, 140] } },
      BBB: { history: { closes: [50, 55, 60, 65, 70] } },
    }
    const positions = [
      { ticker: 'AAA', shares: 2, costBasis: 100, purchaseDate: '2025-01-06' },
      { ticker: 'BBB', shares: 2, costBasis: 60, purchaseDate: '2025-07-07' },
    ]

    const series = portfolioGrowthSeries(positions, staggeredPrices, HISTORY)

    expect(series.holdings).toEqual([200, 220, 360, 390, 420])
    expect(series.cash).toEqual([200, 200, 320, 320, 320])
    expect(series.benchmark).toEqual([200, 210, 345, 368, 383.33333333333337])
  })

  it('starts the chart at the first investment rather than showing empty prior history', () => {
    const positions = [
      { ticker: 'AAA', shares: 2, costBasis: 120, purchaseDate: '2025-07-07' },
    ]

    const series = portfolioGrowthSeries(positions, priceData, HISTORY)

    expect(series.dates).toEqual(['2025-07-07', '2025-10-06', '2026-01-05'])
    expect(series.holdings).toEqual([240, 260, 280])
    expect(series.cash).toEqual([240, 240, 240])
    expect(series.benchmark[0]).toBe(240)
  })

  it('starts both simulations from identical cost-basis dollars when execution differs from the chart close', () => {
    const positions = [
      { ticker: 'AAA', shares: 2, costBasis: 95, purchaseDate: '2025-01-06' },
    ]

    const series = portfolioGrowthSeries(positions, priceData, HISTORY)

    expect(series.holdings[0]).toBe(190)
    expect(series.benchmark[0]).toBe(190)
    expect(series.cash[0]).toBe(190)
    expect(series.holdings.at(-1)).toBeCloseTo(266, 5)
    expect(series.benchmark.at(-1)).toBeCloseTo(237.5, 5)
  })

  it('returns nothing when no holding has published history', () => {
    expect(portfolioGrowthSeries([
      { ticker: 'ZZZ', shares: 5, costBasis: 10, purchaseDate: '2025-01-06' },
    ], priceData, HISTORY)).toBeNull()
  })

  it('does not invent an investment date for an undated holding', () => {
    expect(portfolioGrowthSeries([
      { ticker: 'AAA', shares: 2, costBasis: 100 },
    ], priceData, HISTORY)).toBeNull()
  })
})

const STOCK_HISTORY = { dates: HISTORY.dates, closes: [50, 55, 60, 66, 75] }

describe('fixedBasisAlternative', () => {
  it('prices a flat basis into the stock and the index on the same purchase day, regardless of what was actually invested', () => {
    const position = { shares: 123, costBasis: 9, purchaseDate: '2025-01-06' }
    const result = fixedBasisAlternative(position, STOCK_HISTORY, HISTORY, 500)
    expect(result.stockValue).toBeCloseTo(750, 5) // 500/50 * 75
    expect(result.benchmarkValue).toBeCloseTo(625, 5) // 500/400 * 500
    expect(result.stockReturnPct).toBeCloseTo(50, 5)
    expect(result.benchmarkReturnPct).toBeCloseTo(25, 5)
    expect(result.dollarsAhead).toBeCloseTo(125, 5)
  })

  it('declines to compare a purchase that predates the window', () => {
    const position = { purchaseDate: '2020-01-01' }
    expect(fixedBasisAlternative(position, STOCK_HISTORY, HISTORY, 500)).toBeNull()
  })

  it('requires a purchase date', () => {
    expect(fixedBasisAlternative({}, STOCK_HISTORY, HISTORY, 500)).toBeNull()
  })
})

describe('portfolioFixedBasisVsBenchmark', () => {
  const priceDataWithDates = { AAA: { history: STOCK_HISTORY } }

  it('totals a flat basis per comparable position rather than actual dollars invested', () => {
    const positions = [
      { ticker: 'AAA', shares: 999, costBasis: 1, purchaseDate: '2025-01-06' },
      { ticker: 'ZZZ', shares: 1, costBasis: 1, purchaseDate: '2020-01-01' },
    ]
    const result = portfolioFixedBasisVsBenchmark(positions, priceDataWithDates, HISTORY, 500)
    expect(result.comparable).toBe(1)
    expect(result.invested).toBe(500)
    expect(result.stockValue).toBeCloseTo(750, 5)
    expect(result.benchmarkValue).toBeCloseTo(625, 5)
    expect(result.dollarsAhead).toBeCloseTo(125, 5)
  })

  it('returns nothing when no position falls inside the window', () => {
    const positions = [{ ticker: 'AAA', purchaseDate: '2000-01-01' }]
    expect(portfolioFixedBasisVsBenchmark(positions, priceDataWithDates, HISTORY, 500)).toBeNull()
  })
})

describe('positionGrowthSeries', () => {
  it('starts a single position at its own purchase date, not the whole window', () => {
    const position = { purchaseDate: '2025-07-07' }
    const series = positionGrowthSeries(position, STOCK_HISTORY, HISTORY, 500)
    expect(series.dates).toEqual(['2025-07-07', '2025-10-06', '2026-01-05'])
    expect(series.stock[0]).toBeCloseTo(500, 5)
    expect(series.stock.at(-1)).toBeCloseTo(625, 5) // 500/60 * 75
    expect(series.benchmark[0]).toBeCloseTo(500, 5)
    expect(series.benchmark.at(-1)).toBeCloseTo(555.56, 2) // 500/450 * 500
  })

  it('requires a purchase date', () => {
    expect(positionGrowthSeries({}, STOCK_HISTORY, HISTORY, 500)).toBeNull()
  })

  it('bails out when the stock history is not on the shared grid', () => {
    const position = { purchaseDate: '2025-01-06' }
    const misaligned = { dates: HISTORY.dates, closes: [50, 55] }
    expect(positionGrowthSeries(position, misaligned, HISTORY, 500)).toBeNull()
  })
})
