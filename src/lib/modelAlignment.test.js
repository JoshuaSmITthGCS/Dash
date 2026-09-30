import { describe, expect, it } from 'vitest'
import { modelRanks, splitHoldingsByModel } from './modelAlignment'

const research = [{ ticker: 'AAA' }, { ticker: 'BBB' }, { ticker: 'CCC' }]
const history = (closes) => ({ dates: ['2026-09-01', '2026-09-02', '2026-09-03'], closes, frequency: 'daily' })
const priceData = {
  AAA: { analytics_history: history([10, 11, 12]) },
  ZZZ: { analytics_history: history([20, 19, 18]) },
}
const positions = [
  { ticker: 'aaa', shares: 10, currentValue: 120, totalCost: 100 },
  { ticker: 'ZZZ', shares: 10, currentValue: 180, totalCost: 200 },
]
const benchmarkHistory = { dates: ['2026-09-01', '2026-09-02', '2026-09-03'], closes: [100, 100, 101] }

describe('modelRanks', () => {
  it('ranks by published order, one-based', () => {
    expect(modelRanks(research).get('BBB')).toBe(2)
  })
})

describe('splitHoldingsByModel', () => {
  it('splits holdings by membership in the ranked list, not by action flags', () => {
    const split = splitHoldingsByModel({ positions, research, priceData, benchmarkHistory })
    const [model, own] = split.groups
    expect(model.tickers).toEqual([{ ticker: 'AAA', rank: 1 }])
    expect(own.tickers).toEqual([{ ticker: 'ZZZ', rank: null }])
    expect(model.weightPct).toBeCloseTo(40)
    expect(own.gainPct).toBeCloseTo(-10)
  })

  it('replays each group over the benchmark dates and reports excess return', () => {
    const [model, own] = splitHoldingsByModel({ positions, research, priceData, benchmarkHistory }).groups
    expect(model.replay.returnPct).toBeCloseTo(20)
    expect(model.replay.excessPct).toBeCloseTo(19)
    expect(own.replay.returnPct).toBeCloseTo(-10)
  })

  it('is unavailable without a ranked list or holdings', () => {
    expect(splitHoldingsByModel({ positions, research: [] }).available).toBe(false)
    expect(splitHoldingsByModel({ positions: [], research }).available).toBe(false)
  })
})
