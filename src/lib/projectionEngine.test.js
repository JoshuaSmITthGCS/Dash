import { describe, expect, it } from 'vitest'
import { annualReturnTargetRange, applyAllocationAssumption, benchmarkCenteredSparseHistory, extendSparsePortfolioHistory, monthlyReturnsFromSeries, normalizeAnnualReturnTarget, parametricMonthlyReturns, projectionConfig, selectProjectionReturnSource, simulateProjection, trailingAnnualizedReturn } from './projectionEngine.js'

function riskProfileFixture(overrides = {}) {
  return {
    available: true,
    observations: 40,
    startDate: '2026-01-01',
    endDate: '2026-02-15',
    annualReturn: 0.2,
    riskFreeRate: 0,
    sharpe: 1.5,
    sortino: 2.0,
    loAdjustedSortino: null,
    loAdjusted: false,
    calmar: 3.0,
    downsideVolAnnual: 0.1,
    upsideVolAnnual: 0.14,
    impliedMaxDrawdown: 0.0667,
    confidence: 'limited',
    ...overrides,
  }
}

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

  it('centers long benchmark history on the observed short portfolio return', () => {
    const fallback = selectProjectionReturnSource(monthlySeries(20), monthlySeries(40), 'VTI')
    expect(fallback).toMatchObject({ available: true, type: 'benchmark-centered-sparse-history', months: 39, benchmarkBased: true })
    expect(fallback.fallbackReason).toContain('below the 36-month gate')
    expect(fallback.fallbackReason).toContain('not repeated or synthesized')

    const portfolio = selectProjectionReturnSource(monthlySeries(37), monthlySeries(40), 'VTI')
    expect(portfolio).toMatchObject({ available: true, type: 'portfolio', months: 36 })
  })

  it('uses the trailing year as an annualized personal baseline', () => {
    const baseline = trailingAnnualizedReturn(monthlySeries(13, 0.02))
    expect(baseline.available).toBe(true)
    expect(baseline.annualizedReturn).toBeCloseTo(1.02 ** 12 - 1)
    expect(baseline.label).toContain('Trailing 1-year')
  })

  it('keeps the selected annual return target at the center when allocation changes volatility', () => {
    const returns = Array.from({ length: 48 }, (_, index) => 0.01 + Math.sin(index) * 0.03)
    const adjusted = applyAllocationAssumption(returns, 'aggressive', 0.15)
    const annualizedCenter = Math.expm1(adjusted.reduce((sum, value) => sum + Math.log1p(value), 0) / adjusted.length * projectionConfig.months_per_year)
    expect(annualizedCenter).toBeCloseTo(0.15)
  })

  it('defaults the target to 15 percent inside the supplied brokerage evidence range', () => {
    const source = {
      baseline: {
        returnTargetEvidence: { lowerPct: 14.6, upperPct: 32.32 },
      },
    }
    expect(annualReturnTargetRange(source)).toMatchObject({
      minimumPct: 14.6,
      maximumPct: 32.4,
      stepPct: 0.1,
      defaultPct: 15,
    })
    expect(normalizeAnnualReturnTarget(null, source)).toBe(15)
    expect(normalizeAnnualReturnTarget(50, source)).toBe(32.4)
  })

  it('retains brokerage evidence while allowing the target to replace its return center', () => {
    const supplied = { available: true, annualizedReturn: 0.3232, annualizedReturnPct: 32.32, label: 'Brokerage trailing 1-year return' }
    const source = selectProjectionReturnSource(monthlySeries(20, -0.01), monthlySeries(60, 0.005), 'VTI', supplied)
    expect(source.baseline).toBe(supplied)
    const centered = applyAllocationAssumption(source.returns, 'growth', 0.15)
    const annualizedCenter = Math.expm1(centered.reduce((sum, value) => sum + Math.log1p(value), 0) / centered.length * projectionConfig.months_per_year)
    expect(annualizedCenter).toBeCloseTo(0.15)
  })

  it('keeps benchmark volatility instead of repeating observed sparse months', () => {
    const portfolio = monthlySeries(20, 0.01)
    const benchmark = monthlySeries(120)
    benchmark.values = benchmark.values.map((_, index) => 100 * (1.006 ** index) * (1 + Math.sin(index * 0.8) * 0.08))
    const legacy = extendSparsePortfolioHistory(portfolio)
    const corrected = benchmarkCenteredSparseHistory(portfolio, benchmark)
    const oldResult = simulateProjection({ monthlyReturns: legacy.returns, currentBalance: 100000, accumulationMonths: 360, seed: 42 })
    const newResult = simulateProjection({ monthlyReturns: corrected.returns, currentBalance: 100000, accumulationMonths: 360, seed: 42 })
    const oldSpread = oldResult.terminalPercentiles.p90 - oldResult.terminalPercentiles.p10
    const newSpread = newResult.terminalPercentiles.p90 - newResult.terminalPercentiles.p10
    expect(newSpread).toBeGreaterThan(oldSpread)
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

  it('measures probability of reaching a named goal with the same paths', () => {
    const result = simulateProjection({
      monthlyReturns: Array(36).fill(0),
      currentBalance: 1000,
      monthlyContribution: 100,
      accumulationMonths: 12,
      targetAmount: 2200,
      seed: 1,
    })
    expect(result.goalProbability).toBe(1)
  })

  it('keeps the complete now-to-plan-end horizon beyond the old seventy-year ceiling', () => {
    const result = simulateProjection({
      monthlyReturns: Array(36).fill(0),
      currentBalance: 1000,
      accumulationMonths: 50 * projectionConfig.months_per_year,
      withdrawalMonths: 25 * projectionConfig.months_per_year,
      seed: 1,
    })
    expect(result.fan.at(-1).year).toBe(75)
  })

  it('completes 5,000 thirty-year paths within the worker budget', () => {
    const monthlyReturns = Array.from({ length: 120 }, (_, index) => 0.006 + Math.sin(index) * 0.025)
    const startedAt = globalThis.performance.now()
    const result = simulateProjection({ monthlyReturns, currentBalance: 100000, monthlyContribution: 500, accumulationMonths: 360, seed: 7 })
    expect(result.available).toBe(true)
    expect(globalThis.performance.now() - startedAt).toBeLessThan(projectionConfig.interaction_budget_ms)
  })
})

describe('Sharpe/Sortino/Calmar-calibrated Monte Carlo', () => {
  it('draws a deterministic monthly series whose annualized geometric mean matches the risk profile return', () => {
    const profile = riskProfileFixture()
    const returns = parametricMonthlyReturns(profile, 2400, 42)
    expect(returns).toHaveLength(2400)
    const annualizedMean = Math.expm1(returns.reduce((sum, value) => sum + Math.log1p(value), 0) / returns.length * projectionConfig.months_per_year)
    expect(annualizedMean).toBeCloseTo(profile.annualReturn, 1)
  })

  it('is deterministic for a fixed seed and varies with a different one', () => {
    const profile = riskProfileFixture()
    const first = parametricMonthlyReturns(profile, 24, 1)
    const repeat = parametricMonthlyReturns(profile, 24, 1)
    const other = parametricMonthlyReturns(profile, 24, 2)
    expect(first).toEqual(repeat)
    expect(first).not.toEqual(other)
  })

  it('prefers the risk-profile calibration over historical bootstrap when a risk profile is supplied', () => {
    const profile = riskProfileFixture()
    const result = selectProjectionReturnSource(monthlySeries(37), monthlySeries(40), 'VTI', null, profile)
    expect(result).toMatchObject({ available: true, type: 'parametric-risk-profile', riskProfile: profile })
    expect(result.returns.length).toBe(projectionConfig.parametric_calibration.synthetic_months)
    expect(result.fallbackReason).toContain('Sharpe')
  })

  it('falls back to the historical tiers when no risk profile is available yet', () => {
    const result = selectProjectionReturnSource(monthlySeries(37), monthlySeries(40), 'VTI', null, { available: false })
    expect(result).toMatchObject({ available: true, type: 'portfolio' })
  })

  it('feeds the calibrated returns through the same block-bootstrap simulator', () => {
    const profile = riskProfileFixture()
    const source = selectProjectionReturnSource(monthlySeries(37), monthlySeries(40), 'VTI', null, profile)
    const result = simulateProjection({ monthlyReturns: source.returns, currentBalance: 10000, monthlyContribution: 200, accumulationMonths: 120, seed: 3 })
    expect(result.available).toBe(true)
    expect(result.terminalPercentiles.p50).toBeGreaterThan(0)
  })
})
