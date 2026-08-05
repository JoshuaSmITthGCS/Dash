import { describe, expect, it } from 'vitest'
import { extendSparsePortfolioHistory, monthlyReturnsFromSeries, selectProjectionReturnSource, simulateProjection } from './projectionEngine.js'

function monthlySeries(months, monthlyReturn = 0.01) {
  const dates = []
  const values = []
  let value = 100
  for (let index = 0; index < months; index += 1) {
    dates.push(new Date(Date.UTC(2020, index + 1, 0)).toISOString().slice(0, 10))
    values.push(value)
    value *= 1 + monthlyReturn
  }
  return { dates, values }
}

describe('historical block bootstrap projections', () => {
  it('reduces daily observations to one month-end value before calculating returns', () => {
    const result = monthlyReturnsFromSeries({
      dates: ['2025-01-02', '2025-01-31', '2025-02-03', '2025-02-28', '2025-03-31'],
      values: [90, 100, 80, 110, 121],
    })
    expect(result.returns).toHaveLength(2)
    expect(result.returns[0]).toBeCloseTo(0.1)
    expect(result.returns[1]).toBeCloseTo(0.1)
  })

  it('annualizes and extends a shorter portfolio history to the three-year model window', () => {
    const fallback = selectProjectionReturnSource(monthlySeries(20), monthlySeries(40), 'VTI')
    expect(fallback).toMatchObject({ available: true, type: 'portfolio-annualized-extension', months: 36, synthetic: true })
    expect(fallback.fallbackReason).toContain('below the 36-month gate')
    expect(fallback.fallbackReason).toContain('repeated to 36 months')

    const portfolio = selectProjectionReturnSource(monthlySeries(37), monthlySeries(40), 'VTI')
    expect(portfolio).toMatchObject({ available: true, type: 'portfolio', months: 36 })
  })

  it('annualizes the longest first-to-last return instead of hiding a sparse projection', () => {
    const extension = extendSparsePortfolioHistory({ dates: ['2025-01-01', '2025-07-01'], values: [100, 110] })
    expect(extension.months).toBe(36)
    expect(extension.elapsedDays).toBe(181)
    expect(extension.annualizedReturn).toBeCloseTo((1.1 ** (365.25 / 181)) - 1)
  })

  it('keeps the benchmark fallback when portfolio history spans less than 30 days', () => {
    const result = selectProjectionReturnSource(
      { dates: ['2025-01-01', '2025-01-10'], values: [100, 101] },
      monthlySeries(40),
      'VTI',
    )
    expect(result).toMatchObject({ available: true, type: 'benchmark-fallback', label: 'VTI monthly returns' })
  })

  it('returns five terminal percentiles from at least 5,000 paths', () => {
    const result = simulateProjection({
      monthlyReturns: Array(36).fill(0),
      currentBalance: 1000,
      monthlyContribution: 100,
      accumulationMonths: 12,
      seed: 42,
    })
    expect(result.pathCount).toBe(5000)
    expect(result.retirementPercentiles).toEqual({ p10: 2200, p25: 2200, p50: 2200, p75: 2200, p90: 2200 })
    expect(result.fan).toHaveLength(2)
  })

  it('measures whether savings survive the inflation-aware monthly withdrawal phase', () => {
    const failed = simulateProjection({
      monthlyReturns: Array(36).fill(0),
      currentBalance: 1200,
      accumulationMonths: 12,
      withdrawalMonths: 12,
      monthlyWithdrawal: 100,
      inflationPct: 0,
      seed: 1,
    })
    const survived = simulateProjection({
      monthlyReturns: Array(36).fill(0),
      currentBalance: 1201,
      accumulationMonths: 12,
      withdrawalMonths: 12,
      monthlyWithdrawal: 100,
      inflationPct: 0,
      seed: 1,
    })
    expect(failed.successProbability).toBe(0)
    expect(survived.successProbability).toBe(1)
  })

  it('completes 5,000 thirty-year paths within the worker budget', () => {
    const monthlyReturns = Array.from({ length: 120 }, (_, index) => 0.006 + Math.sin(index) * 0.025)
    const startedAt = globalThis.performance.now()
    const result = simulateProjection({ monthlyReturns, currentBalance: 100000, monthlyContribution: 500, accumulationMonths: 360, seed: 7 })
    expect(result.available).toBe(true)
    expect(globalThis.performance.now() - startedAt).toBeLessThan(400)
  })
})
