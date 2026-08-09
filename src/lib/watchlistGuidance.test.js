import { describe, expect, it } from 'vitest'
import { inverseVolatilityAllocations, watchlistGuidance } from './watchlistGuidance'

const coveredStock = {
  ticker: 'CALM',
  price: 100,
  score: 72,
  data_coverage: 0.8,
  components: { fundamentals: 80, market_behavior: 70, news_sentiment: 60 },
  sentiment_detail: { coverage: 1 },
  technical_detail: { return_20d: 8, risk: 70, annualized_volatility: 20 },
  recommendation: { action: 'HOLD' },
  analyst_consensus_target: 125,
  analyst_count: 18,
}

describe('watchlist guidance', () => {
  it('publishes a continuous setup score and the capped illustrative position', () => {
    const result = watchlistGuidance(coveredStock, 10_000, 5)
    expect(result).toMatchObject({
      setupLabel: 'Strong Setup',
      target: 125,
      targetUpside: 25,
      allocation: 500,
      shares: 5,
      hardBlocked: false,
    })
    expect(result.setupScore).toBeGreaterThan(75)
    expect(result.subscores.map((item) => item.key)).toEqual(['thesis', 'research', 'coverage', 'guidance'])
  })

  it('does not allocate zero when a signal is just below its former threshold', () => {
    const result = watchlistGuidance({
      ...coveredStock,
      score: 64,
      data_coverage: 0.49,
      components: { fundamentals: 54, market_behavior: 54, news_sentiment: 54 },
      technical_detail: { ...coveredStock.technical_detail, return_20d: -8 },
    }, 10_000, 5)
    expect(result.setupScore).toBeGreaterThan(0)
    expect(result.allocation).toBe(500)
    expect(result.hardBlocked).toBe(false)
  })

  it('uses only low confidence and published Sell as hard blocks', () => {
    expect(watchlistGuidance({
      ...coveredStock,
      recommendation: { action: 'TRIM' },
    }, 10_000, 5)).toMatchObject({ allocation: 500, hardBlocked: false })
    expect(watchlistGuidance({ ...coveredStock, data_coverage: 0.44 }, 10_000, 5)).toMatchObject({
      allocation: 0,
      hardBlocked: true,
    })
    expect(watchlistGuidance({
      ...coveredStock,
      recommendation: { action: 'SELL' },
    }, 10_000, 5)).toMatchObject({ setupScore: 0, allocation: 0, hardBlocked: true })
  })

  it('equalizes volatility contribution and retains the per-name cap', () => {
    const volatile = {
      ...coveredStock,
      ticker: 'WILD',
      technical_detail: { ...coveredStock.technical_detail, annualized_volatility: 40 },
    }
    const allocations = inverseVolatilityAllocations([coveredStock, volatile], 10_000, 5)
    expect(allocations).toEqual({ CALM: 500, WILD: 250 })
    expect(allocations.CALM * 20).toBe(allocations.WILD * 40)
    expect(watchlistGuidance(volatile, 10_000, 5, {
      sizingMode: 'inverse-volatility',
      volatilityAllocation: allocations.WILD,
    })).toMatchObject({ allocation: 250, sizingMode: 'inverse-volatility' })
  })

  it('falls back to capped sizing when volatility is unavailable', () => {
    const result = watchlistGuidance({
      ...coveredStock,
      technical_detail: {},
    }, 10_000, 5, { sizingMode: 'inverse-volatility' })
    expect(result).toMatchObject({ allocation: 500, sizingMode: 'capped', sizingFallback: true })
  })

  it('does not invent a Yahoo target when none is published', () => {
    expect(watchlistGuidance({
      ...coveredStock,
      analyst_consensus_target: null,
    })).toMatchObject({ target: null, targetUpside: null })
  })
})
