import { describe, expect, it } from 'vitest'
import {
  alignSeries, compareBenchmarkSeries, concentrationLiquidityScore, currentHoldingsSeries, diversificationScore, enrichPortfolio,
  contributionAdjustedPerformance, intradayPortfolioHigh, latestMarketDayReturn, netInvestedCapital, opportunityCost, performanceRating,
  planningReturnRates, portfolioAnnualizedReturn, portfolioScore, resilienceIndex, scenarioProjection, selectPeriod, trackedAllTimeEarnings,
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
    expect(netInvestedCapital([{ type: 'deposit', amount: 1000, effectiveDate: '2026-01-01' }])).toMatchObject({ deposits: 1000, withdrawals: 0 })
    expect(netInvestedCapital([
      { type: 'deposit', amount: 1000, effectiveDate: '2026-01-01' },
      { type: 'sale_proceeds', amount: 250, effectiveDate: '2026-01-02' },
      { type: 'stock_purchase', amount: 200, effectiveDate: '2026-01-03' },
    ]).value).toBe(1000)
  })

  it('calculates actual account growth from complete external cash flows', () => {
    const rows = [{ type: 'deposit', amount: 2880, effectiveDate: '2026-01-01' }, { type: 'withdrawal', amount: 200, effectiveDate: '2026-02-01' }]
    expect(contributionAdjustedPerformance(2827.96, rows, false).available).toBe(false)
    const result = contributionAdjustedPerformance(2827.96, rows, true)
    expect(result.netContributions).toBe(2680)
    expect(result.value).toBeCloseTo(147.96, 2)
    expect(result.returnPct).toBeCloseTo(5.52, 2)
  })

  it('aligns exact dates before benchmark and opportunity-cost comparisons', () => {
    const aligned = alignSeries({ period: '1M', dates: ['a', 'b', 'c'], values: [100, 105, 110] }, { dates: ['b', 'c', 'd'], values: [200, 204, 210] })
    expect(aligned.dates).toEqual(['b', 'c'])
    const performance = performanceRating(aligned.left, aligned.right)
    expect(performance.available).toBe(true)
    const cost = opportunityCost(aligned.left, aligned.right)
    expect(cost.startDate).toBe('b')
  })

  it('uses one exact-date, equal-start calculation for multi-benchmark charts and potential earnings', () => {
    const comparison = compareBenchmarkSeries(
      { period: '1M', dates: ['a', 'b', 'c'], values: [100, 110, 120], methodology: 'test' },
      [
        { symbol: 'SPY', dates: ['a', 'b', 'c'], closes: [200, 210, 220] },
        { symbol: 'QQQ', dates: ['a', 'b', 'c'], closes: [50, 60, 70] },
      ],
    )
    expect(comparison.dates).toEqual(['a', 'b', 'c'])
    expect(comparison.portfolio.endValue).toBe(120)
    expect(comparison.benchmarks[0]).toMatchObject({ symbol: 'SPY', endValue: 110, potentialEarnings: 10, differenceVsPortfolio: 10 })
    expect(comparison.benchmarks[1]).toMatchObject({ symbol: 'QQQ', endValue: 140, potentialEarnings: 40, differenceVsPortfolio: -20 })
  })

  it('marks sparse resilience and concentrated diversification transparently', () => {
    const sparse = resilienceIndex([100, 101])
    expect(sparse.available).toBe(false)
    const concentrated = diversificationScore([{ ticker: 'AAA', currentValue: 90, priceInfo: { sector: 'Tech', industry: 'Software' } }, { ticker: 'BBB', currentValue: 10, priceInfo: { sector: 'Health', industry: 'Care' } }])
    expect(concentrated.score).toBeLessThan(60)
    expect(concentrated.warnings[0]).toContain('Largest holding')
  })

  it('issues a clearly provisional score without turning missing components into zero', () => {
    const liquidity = concentrationLiquidityScore([{ currentValue: 1000, allocationPct: 100, priceInfo: { average_dollar_volume: 1_000_000 } }])
    expect(liquidity.available).toBe(true)
    const score = portfolioScore({ diversification: { score: 50 }, resilience: { score: null }, performance: { score: 50 }, benchmarkEfficiency: 50, concentrationLiquidity: liquidity, dataCompleteness: 100 })
    expect(score.available).toBe(true)
    expect(score.provisional).toBe(true)
    expect(score.components.resilience).toBeNull()
  })

  it('calculates manual planning scenarios without presenting a forecast', () => {
    expect(scenarioProjection(1000, 10, 2, 100)).toBe(1420)
    expect(scenarioProjection(null, 10, 2)).toBeNull()
  })

  it('derives planning rates from the money-weighted annualized return of current holdings', () => {
    const positions = [{ purchaseDate: '2025-01-01', totalCost: 1000, currentValue: 1100 }]
    const annualized = portfolioAnnualizedReturn(positions, '2026-01-01')
    expect(annualized.available).toBe(true)
    expect(annualized.rate).toBeCloseTo(10, 1)
    const rates = planningReturnRates(positions, [100, 101, 102, 103], '2026-01-01')
    expect(rates.conservative).toBeLessThan(rates.base)
    expect(rates.optimistic).toBeGreaterThan(rates.base)
  })

  it('stores observed intraday highs and only calculates all-time earnings after ledger confirmation', () => {
    expect(intradayPortfolioHigh([{ recordedAt: '2026-08-04T14:00:00Z', value: 100 }, { recordedAt: '2026-08-04T15:00:00Z', value: 110 }])).toMatchObject({ value: 110, observations: 2 })
    const incomplete = trackedAllTimeEarnings({ gain: 20 }, [{ type: 'dividend', amount: 5 }], { trackingStartedAt: '2026-01-01' })
    expect(incomplete.available).toBe(false)
    const complete = trackedAllTimeEarnings({ gain: 20 }, [{ type: 'realized_gain', amount: -4 }, { type: 'dividend', amount: 5 }, { type: 'fee', amount: 1 }], { trackingStartedAt: '2026-01-01', ledgerComplete: true })
    expect(complete.value).toBe(20)
  })
})
