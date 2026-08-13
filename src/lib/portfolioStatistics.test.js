import { describe, expect, it } from 'vitest'
import {
  deflatedSharpe,
  executionStatistics,
  minimumTrackRecordLength,
  performanceStatistics,
  probabilisticSharpe,
  sampleDeviation,
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
