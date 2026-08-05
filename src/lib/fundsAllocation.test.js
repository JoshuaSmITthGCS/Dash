import { describe, expect, it } from 'vitest'
import { allocateFunds } from './fundsAllocation'

const row = (ticker, score, price = 10) => ({ ticker, score, price, name: ticker })

describe('allocateFunds', () => {
  it('rejects a non-positive funds amount', () => {
    expect(allocateFunds([row('A', 90)], 0).available).toBe(false)
    expect(allocateFunds([row('A', 90)], -5).available).toBe(false)
    expect(allocateFunds([row('A', 90)], NaN).available).toBe(false)
  })

  it('rejects an empty or unscored row set', () => {
    expect(allocateFunds([], 1000).available).toBe(false)
    expect(allocateFunds([row('A', null)], 1000).available).toBe(false)
  })

  it('weights higher-scored companies with a disproportionately larger bucket, not an even split', () => {
    const result = allocateFunds([row('HIGH', 90), row('LOW', 45)], 1000)
    expect(result.available).toBe(true)
    const [high, low] = result.buckets
    // Score-squared weighting: 90^2 vs 45^2 is a 4:1 ratio, not the 1:1 an even split would give.
    expect(high.amount).toBeCloseTo(800, 0)
    expect(low.amount).toBeCloseTo(200, 0)
    expect(high.amount).toBeGreaterThan(low.amount * 2)
  })

  it('sums bucket amounts back to the available funds', () => {
    const result = allocateFunds([row('A', 90), row('B', 70), row('C', 55)], 500)
    const total = result.buckets.reduce((sum, bucket) => sum + bucket.amount, 0)
    expect(total).toBeCloseTo(500, 6)
  })

  it('caps the number of buckets at the limit, keeping the top-ranked rows', () => {
    const rows = [row('A', 90), row('B', 80), row('C', 70)]
    const result = allocateFunds(rows, 300, { limit: 2 })
    expect(result.buckets.map((bucket) => bucket.ticker)).toEqual(['A', 'B'])
  })

  it('derives share counts from price where available', () => {
    const result = allocateFunds([row('A', 90, 20)], 1000)
    expect(result.buckets[0].shares).toBeCloseTo(50, 6)
  })

  it('leaves shares null when price is unavailable', () => {
    const result = allocateFunds([row('A', 90, null)], 1000)
    expect(result.buckets[0].shares).toBeNull()
  })
})
