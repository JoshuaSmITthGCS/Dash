import { describe, expect, it } from 'vitest'
import {
  alignSeries, concentrationLiquidityScore, currentHoldingsSeries, diversificationScore, enrichPortfolio,
  latestMarketDayReturn, netInvestedCapital, opportunityCost, performanceRating,
  portfolioScore, resilienceIndex, scenarioProjection, selectPeriod,
} from './portfolioAnalytics.js'

describe('portfolio report analytics', () => {
  it('separates entered cost basis from current value and allocation', () => {
    const result = enrichPortfolio([{ ticker: 'AAA', shares: 2, costBasis: 50 }, { ticker: 'BBB', shares: 1, costBasis: 80 }], { AAA: { price: 75 }, BBB: { price: 50 } })
    expect(result.totalCost).toBe(180)
    expect(result.totalValue).toBe(200)
    expect(result.gain).toBe(20)
    expect(result.positions[0].allocationPct).toBe(75)
  })

  it('builds an explicitly current-holdings daily-close backtest and changes data by period', () => {
    const series = currentHoldingsSeries([{ ticker: 'AAA', shares: 2 }], { AAA: { history: { dates: ['2026-06-01', '2026-06-25', '2026-06-30'], closes: [10, 12, 15] } } })
    expect(series.values).toEqual([20, 24, 30])
    expect(series.methodology).toContain('Current quantities')
    expect(selectPeriod(series, '1W').dates).toEqual(['2026-06-25', '2026-06-30'])
    expect(selectPeriod(series, 'All').values).toHaveLength(3)
  })

  it('uses the last two closes for latest market-day return', () => {
    expect(latestMarketDayReturn({ dates: ['a', 'b', 'c'], values: [100, 105, 103] })).toMatchObject({ date: 'c', dollarReturn: -2 })
  })

  it('does not call cost basis invested capital without a cash-flow ledger', () => {
    expect(netInvestedCapital(null).available).toBe(false)
    expect(netInvestedCapital([{ type: 'deposit', amount: 1000, date: '2026-01-01' }, { type: 'withdrawal', amount: 100, date: '2026-02-01' }]).value).toBe(900)
  })

  it('aligns exact dates before benchmark and opportunity-cost comparisons', () => {
    const aligned = alignSeries({ period: '1M', dates: ['a', 'b', 'c'], values: [100, 105, 110] }, { dates: ['b', 'c', 'd'], values: [200, 204, 210] })
    expect(aligned.dates).toEqual(['b', 'c'])
    const performance = performanceRating(aligned.left, aligned.right)
    expect(performance.available).toBe(true)
    const cost = opportunityCost(aligned.left, aligned.right)
    expect(cost.startDate).toBe('b')
  })

  it('marks sparse resilience and concentrated diversification transparently', () => {
    const sparse = resilienceIndex([100, 101])
    expect(sparse.available).toBe(false)
    const concentrated = diversificationScore([{ ticker: 'AAA', currentValue: 90, priceInfo: { sector: 'Tech', industry: 'Software' } }, { ticker: 'BBB', currentValue: 10, priceInfo: { sector: 'Health', industry: 'Care' } }])
    expect(concentrated.score).toBeLessThan(60)
    expect(concentrated.warnings[0]).toContain('Largest holding')
  })

  it('requires real history and liquidity coverage before issuing a portfolio score', () => {
    const liquidity = concentrationLiquidityScore([{ currentValue: 1000, allocationPct: 100, priceInfo: { average_dollar_volume: 1_000_000 } }])
    expect(liquidity.available).toBe(true)
    expect(portfolioScore({ diversification: { score: 50 }, resilience: { score: null }, performance: { score: 50 }, benchmarkEfficiency: 50, concentrationLiquidity: liquidity, dataCompleteness: 100 }).available).toBe(false)
  })

  it('calculates manual planning scenarios without presenting a forecast', () => {
    expect(scenarioProjection(1000, 10, 2, 100)).toBe(1420)
    expect(scenarioProjection(null, 10, 2)).toBeNull()
  })
})
