import { describe, expect, it } from 'vitest'
import {
  constructedBenchmarkFit,
  deflatedSharpe,
  executionStatistics,
  minimumTrackRecordLength,
  performanceStatistics,
  probabilisticSharpe,
  sampleDeviation,
  timeToValidMetric,
} from './portfolioStatistics.js'

function weekdayDates(count, start = '2024-01-02') {
  const dates = []
  let value = Date.parse(`${start}T00:00:00Z`)
  while (dates.length < count) {
    const day = new Date(value).getUTCDay()
    if (day !== 0 && day !== 6) dates.push(new Date(value).toISOString().slice(0, 10))
    value += 86_400_000
  }
  return dates
}

function deterministicReturns(count, seed) {
  return Array.from({ length: count }, (_, index) => Math.sin((index + 1) * seed) * 0.01)
}

function seriesFromReturns(returns, dates) {
  const values = [100]
  for (const value of returns) values.push(values.at(-1) * (1 + value))
  return { dates, values }
}

describe('portfolio statistical inference', () => {
  it('matches the closed-form PSR and MinTRL worked inputs', () => {
    const input = { sharpePerPeriod: 0.1, observations: 100, skewness: 0, kurtosis: 3 }
    expect(probabilisticSharpe(input).value).toBeCloseTo(0.8395254, 6)
    expect(minimumTrackRecordLength({ ...input, confidence: 0.95 }).observations).toBe(272)
  })

  it('deflates against the registered-trial distribution and names a missing variance', () => {
    const input = { sharpePerPeriod: 0.1, observations: 100, skewness: 0, kurtosis: 3, trialCount: 50 }
    expect(deflatedSharpe({ ...input, trialSharpeVariance: 0.0025 })).toMatchObject({ available: true, trialCount: 50 })
    expect(deflatedSharpe({ ...input, trialSharpeVariance: 0.0025 }).value).toBeCloseTo(0.4454693, 6)
    expect(deflatedSharpe(input)).toMatchObject({ available: false, reason: 'Variance of Sharpes across registered trials is not recorded.' })
  })

  it('reduces naive Sharpe on a positively autocorrelated synthetic daily series', () => {
    const dates = weekdayDates(620)
    const returns = []
    let previous = 0
    let seed = 12345
    const random = () => {
      seed = (1664525 * seed + 1013904223) >>> 0
      return seed / 4294967296
    }
    for (let index = 0; index < dates.length - 1; index += 1) {
      let standardized = -6
      for (let draw = 0; draw < 12; draw += 1) standardized += random()
      const innovation = standardized * 0.003 + 0.0002
      previous = 0.65 * previous + innovation
      returns.push(previous)
    }
    const values = [100]
    returns.forEach((value) => values.push(values.at(-1) * (1 + value)))
    const result = performanceStatistics({ dates, values, frequency: 'daily' })
    expect(result.available).toBe(true)
    expect(result.loFactor.available).toBe(true)
    expect(result.loAdjustedSharpe).toBeLessThan(result.naiveSharpe)
    expect(result.autocorrelation1).toBeGreaterThan(0.4)
  })

  it('refuses inference on the sparse display grid', () => {
    const result = performanceStatistics({ dates: ['2025-01-02', '2025-02-03', '2025-03-03'], values: [100, 101, 102], frequency: 'irregular' })
    expect(result.available).toBe(false)
    expect(result.reason).toContain('compact chart grid')
  })
})

describe('execution statistics', () => {
  it('solves the per-trade cost where net Sharpe is zero', () => {
    const result = executionStatistics({
      returns: [0.002, 0.001, 0.003, 0.002],
      rebalances: [
        { date: '2025-01-02', beforeWeights: { A: 1, B: 0 }, afterWeights: { A: 0.5, B: 0.5 } },
        { date: '2026-01-02', beforeWeights: { A: 0.5, B: 0.5 }, afterWeights: { A: 0, B: 1 } },
      ],
    })
    const net = result.netReturnsAtCost(result.breakEvenCostBps)
    const mean = net.reduce((sum, value) => sum + value, 0) / net.length
    expect(mean).toBeCloseTo(0, 12)
    expect(sampleDeviation(net)).toBeGreaterThan(0)
  })

  it('does not infer turnover from returns', () => {
    expect(executionStatistics({ returns: [0.01, -0.01] })).toMatchObject({ available: false })
    expect(executionStatistics({ returns: [0.01, -0.01] }).reason).toContain('Position-level')
  })
})

describe('constructedBenchmarkFit', () => {
  const dates = weekdayDates(31)
  const returnsA = deterministicReturns(30, 0.7)
  const returnsB = deterministicReturns(30, 1.3)
  const candidateA = { symbol: 'AAA', label: 'Asset A', ...seriesFromReturns(returnsA, dates) }
  const candidateB = { symbol: 'BBB', label: 'Asset B', ...seriesFromReturns(returnsB, dates) }

  it('concentrates weight on the single candidate that matches the portfolio exactly', () => {
    const portfolio = seriesFromReturns(returnsA, dates)
    const fit = constructedBenchmarkFit(portfolio, [candidateA, candidateB])
    expect(fit.available).toBe(true)
    expect(fit.weights.find((row) => row.symbol === 'AAA').weight).toBeCloseTo(1, 2)
    expect(fit.weights.find((row) => row.symbol === 'BBB').weight).toBeCloseTo(0, 2)
    expect(fit.correlation).toBeCloseTo(1, 3)
    expect(fit.trackingErrorPct).toBeCloseTo(0, 2)
  })

  it('splits weight between two candidates that together explain the portfolio exactly', () => {
    const blended = returnsA.map((value, index) => 0.5 * value + 0.5 * returnsB[index])
    const portfolio = seriesFromReturns(blended, dates)
    const fit = constructedBenchmarkFit(portfolio, [candidateA, candidateB])
    expect(fit.weights.find((row) => row.symbol === 'AAA').weight).toBeCloseTo(0.5, 2)
    expect(fit.weights.find((row) => row.symbol === 'BBB').weight).toBeCloseTo(0.5, 2)
    expect(fit.correlation).toBeCloseTo(1, 3)
  })

  it('always returns non-negative weights summing to 1, even for an unrelated portfolio', () => {
    const portfolio = seriesFromReturns(deterministicReturns(30, 2.1), dates)
    const fit = constructedBenchmarkFit(portfolio, [candidateA, candidateB])
    expect(fit.weights.reduce((sum, row) => sum + row.weight, 0)).toBeCloseTo(1, 6)
    fit.weights.forEach((row) => expect(row.weight).toBeGreaterThanOrEqual(0))
  })

  it('is unavailable with fewer than two usable candidates', () => {
    const portfolio = seriesFromReturns(returnsA, dates)
    expect(constructedBenchmarkFit(portfolio, [candidateA]).available).toBe(false)
    expect(constructedBenchmarkFit(portfolio, []).available).toBe(false)
  })

  it('is unavailable with too few overlapping observations', () => {
    const shortDates = weekdayDates(10)
    const shortReturns = deterministicReturns(9, 0.7)
    const shortA = { symbol: 'AAA', ...seriesFromReturns(shortReturns, shortDates) }
    const shortB = { symbol: 'BBB', ...seriesFromReturns(deterministicReturns(9, 1.3), shortDates) }
    const portfolio = seriesFromReturns(shortReturns, shortDates)
    const fit = constructedBenchmarkFit(portfolio, [shortA, shortB])
    expect(fit.available).toBe(false)
    expect(fit.reason).toContain('21 overlapping returns')
  })
})

describe('timeToValidMetric', () => {
  it('is unavailable when the observation count is missing', () => {
    expect(timeToValidMetric(null, '2026-08-14').available).toBe(false)
  })

  it('reports the floor already met once observations reach it', () => {
    expect(timeToValidMetric(60, '2026-08-14')).toMatchObject({
      available: true, met: true, observations: 60, floor: 60, remainingSessions: 0,
    })
  })

  it('projects the next-session estimate as a lower bound, skipping weekends', () => {
    expect(timeToValidMetric(59, '2026-08-14')).toMatchObject({
      available: true, met: false, observations: 59, floor: 60, remainingSessions: 1,
      estimatedDate: '2026-08-17',
    })
    expect(timeToValidMetric(55, '2026-08-14')).toMatchObject({
      remainingSessions: 5, estimatedDate: '2026-08-21',
    })
    expect(timeToValidMetric(34, '2026-08-14', 60)).toMatchObject({
      remainingSessions: 26, estimatedDate: '2026-09-21',
    })
  })

  it('has no estimated date without a last-observed date to project from', () => {
    expect(timeToValidMetric(10, null)).toMatchObject({ available: true, met: false, estimatedDate: null })
  })
})
