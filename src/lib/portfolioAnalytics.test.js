import { describe, expect, it } from 'vitest'
import {
  alignSeries, compareBenchmarkSeries, concentrationLiquidityScore, correlationDiversification, currentHoldingsSeries, diversificationScore, enrichPortfolio,
  contributionAdjustedPerformance, intradayPortfolioHigh, latestMarketDayReturn, modifiedDietzReturn, netInvestedCapital, opportunityCost, performanceMetrics,
  portfolioAnnualizedReturn, portfolioRiskDecomposition, portfolioScore, resilienceIndex, sectorLookThrough, selectPeriod, trackedAllTimeEarnings, trailingCashFlowPace,
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
    expect(selectPeriod({ dates: ['2025-12-31', '2026-01-02', '2026-06-30'], values: [18, 19, 30] }, 'YTD').dates).toEqual(['2026-01-02', '2026-06-30'])
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

  it('calculates Modified Dietz for a worked mid-period deposit example', () => {
    const result = modifiedDietzReturn(100, 165, [
      { type: 'deposit', amount: 50, effectiveDate: '2026-01-06' },
    ], '2026-01-01', '2026-01-11', true)
    expect(result.returnPct).toBeCloseTo(12, 8)
    expect(result.weightedCapital).toBe(125)
  })

  it('excludes processing transfers from actual gains and the observed contribution pace', () => {
    const rows = [
      { type: 'deposit', amount: 60, effectiveDate: '2025-08-04' },
      { type: 'deposit', amount: 200, effectiveDate: '2026-02-13' },
      { type: 'withdrawal', amount: 200, effectiveDate: '2026-03-30' },
      { type: 'deposit', amount: 2500, effectiveDate: '2026-08-03' },
      { type: 'deposit', amount: 100, effectiveDate: '2026-08-04', status: 'processing' },
    ]
    const performance = contributionAdjustedPerformance(2818.41, rows, true)
    expect(performance.netContributions).toBe(2560)
    expect(performance.value).toBeCloseTo(258.41, 2)
    expect(trailingCashFlowPace(rows, '2026-08-04', true)).toMatchObject({ deposits: 2760, withdrawals: 200, netContributions: 2560, count: 4 })
  })

  it('aligns exact dates before benchmark and opportunity-cost comparisons', () => {
    const aligned = alignSeries({ period: '1M', dates: ['a', 'b', 'c'], values: [100, 105, 110] }, { dates: ['b', 'c', 'd'], values: [200, 204, 210] })
    expect(aligned.dates).toEqual(['b', 'c'])
    const longLeft = { values: Array.from({ length: 25 }, (_, index) => 100 + index), period: '1M' }
    const longRight = { values: Array.from({ length: 25 }, (_, index) => 100 + index * 0.8), period: '1M' }
    const performance = performanceMetrics(longLeft, longRight)
    expect(performance.available).toBe(true)
    expect(performance.score).toBeNull()
    expect(performance.rating).toBeUndefined()
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

  it('computes HHI and effective holdings for a hand-calculated four-position case', () => {
    const positions = [40, 30, 20, 10].map((currentValue, index) => ({
      ticker: `P${index}`,
      currentValue,
      priceInfo: { sector: `S${index}`, industry: `I${index}` },
    }))
    const result = diversificationScore(positions)
    expect(result.hhi).toBeCloseTo(0.3, 10)
    expect(result.effectiveHoldings).toBeCloseTo(10 / 3, 10)
    expect(result.rawHoldingCount).toBe(4)
  })

  it('collapses perfectly correlated holdings to one effective bet', () => {
    const dates = Array.from({ length: 70 }, (_, index) => `2026-01-${String(index + 1).padStart(2, '0')}`)
    const closes = dates.map((_, index) => 100 * (1.01 ** index))
    const positions = ['AAA', 'BBB'].map((ticker) => ({
      ticker,
      currentValue: 50,
      priceInfo: { history: { dates, closes } },
    }))
    const result = correlationDiversification(positions)
    expect(result.available).toBe(true)
    expect(result.effectiveBets).toBeCloseTo(1, 6)
    expect(result.diversificationRatio).toBeCloseTo(1, 6)
  })

  it('looks through an ETF before aggregating direct sector exposure', () => {
    const positions = [
      { ticker: 'VOO', currentValue: 50, priceInfo: { sector: 'ETF' } },
      { ticker: 'MSFT', currentValue: 50, priceInfo: { sector: 'Technology' } },
    ]
    const result = sectorLookThrough(positions, [{
      ticker: 'VOO',
      sector_weights: { technology: 0.6, healthcare: 0.4 },
    }])
    expect(result.exposures).toEqual([
      { label: 'Technology', pct: 80 },
      { label: 'Healthcare', pct: 20 },
    ])
    expect(result.unavailableEtfs).toEqual([])
  })

  it('combines an ETF constituent with the same direct position', () => {
    const result = sectorLookThrough([
      { ticker: 'VOO', currentValue: 50, priceInfo: { sector: 'ETF' } },
      { ticker: 'NVDA', currentValue: 50, priceInfo: { sector: 'Technology' } },
    ], [{
      ticker: 'VOO',
      sector_weights: { technology: 1 },
      top_holdings: [{ ticker: 'NVDA', weight: 0.1 }, { ticker: 'MSFT', weight: 0.2 }],
    }])
    expect(result.positionExposures.find((row) => row.ticker === 'NVDA').pct).toBeCloseTo(55, 10)
    expect(result.positionExposures.find((row) => row.ticker === 'MSFT').pct).toBeCloseTo(10, 10)
    expect(result.positionExposures.find((row) => row.ticker === 'Other VOO holdings').pct).toBeCloseTo(35, 10)
  })

  it('flags an ETF when sector look-through is unavailable', () => {
    const result = sectorLookThrough([
      { ticker: 'VOO', currentValue: 100, priceInfo: { sector: 'ETF' } },
    ], [{ ticker: 'VOO', sector_weights: null }])
    expect(result.unavailableEtfs).toEqual(['VOO'])
    expect(result.exposures[0].label).toBe('ETF look-through unavailable')
    expect(result.unresolvedDollars).toBe(100)
  })

  it('reconciles percent contribution to total risk to 100%', () => {
    const dates = Array.from({ length: 90 }, (_, index) => `d-${index}`)
    const makeCloses = (phase) => dates.map((_, index) => 100 * (1 + index * 0.001 + Math.sin(index + phase) * 0.01))
    const positions = [
      { ticker: 'AAA', currentValue: 60, priceInfo: { history: { dates, closes: makeCloses(0) } } },
      { ticker: 'BBB', currentValue: 40, priceInfo: { history: { dates, closes: makeCloses(1) } } },
    ]
    const result = portfolioRiskDecomposition(positions)
    expect(result.available).toBe(true)
    expect(result.contributions.reduce((sum, row) => sum + row.percentContributionToRisk, 0)).toBeCloseTo(100, 8)
    expect(result.expectedShortfall95Pct).toBeLessThan(0)
  })

  it('publishes active share only when benchmark constituent weights are available', () => {
    const dates = Array.from({ length: 90 }, (_, index) => `d-${index}`)
    const positions = [
      { ticker: 'AAA', currentValue: 60, priceInfo: { history: { dates, closes: dates.map((_, index) => 100 + index + Math.sin(index)) } } },
      { ticker: 'BBB', currentValue: 40, priceInfo: { history: { dates, closes: dates.map((_, index) => 100 + index + Math.cos(index)) } } },
    ]
    expect(portfolioRiskDecomposition(positions).activeSharePct).toBeNull()
    expect(portfolioRiskDecomposition(positions, { benchmarkWeights: { AAA: 0.5, BBB: 0.5 } }).activeSharePct).toBeCloseTo(10, 10)
  })

  it('issues a clearly provisional score without turning missing components into zero', () => {
    const liquidity = concentrationLiquidityScore([{ currentValue: 1000, allocationPct: 100, priceInfo: { average_dollar_volume: 1_000_000 } }])
    expect(liquidity.available).toBe(true)
    const score = portfolioScore({ diversification: { score: 50 }, resilience: { score: null }, performance: { score: 50 }, benchmarkEfficiency: 50, concentrationLiquidity: liquidity, dataCompleteness: 100 })
    expect(score.available).toBe(true)
    expect(score.provisional).toBe(true)
    expect(score.components.resilience).toBeNull()
  })

  it('derives a money-weighted annualized return from current holdings', () => {
    const positions = [{ purchaseDate: '2025-01-01', totalCost: 1000, currentValue: 1100 }]
    const annualized = portfolioAnnualizedReturn(positions, '2026-01-01')
    expect(annualized.available).toBe(true)
    expect(annualized.rate).toBeCloseTo(10, 1)
  })

  it('stores observed intraday highs and only calculates all-time earnings after ledger confirmation', () => {
    expect(intradayPortfolioHigh([{ recordedAt: '2026-08-04T14:00:00Z', value: 100 }, { recordedAt: '2026-08-04T15:00:00Z', value: 110 }])).toMatchObject({ value: 110, observations: 2 })
    const incomplete = trackedAllTimeEarnings({ gain: 20 }, [{ type: 'dividend', amount: 5 }], { trackingStartedAt: '2026-01-01' })
    expect(incomplete.available).toBe(false)
    const complete = trackedAllTimeEarnings({ gain: 20 }, [{ type: 'realized_gain', amount: -4 }, { type: 'dividend', amount: 5 }, { type: 'fee', amount: 1 }], { trackingStartedAt: '2026-01-01', ledgerComplete: true })
    expect(complete.value).toBe(20)
  })
})
