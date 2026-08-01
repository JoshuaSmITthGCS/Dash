import { describe, expect, it } from 'vitest'
import { summarizeBudget, splitAmount } from './financeSplit'

describe('summarizeBudget', () => {
  it('totals income and expenses into a leftover figure', () => {
    const items = [
      { type: 'income', amount: 4000 },
      { type: 'income', amount: 500 },
      { type: 'expense', amount: 1800 },
      { type: 'expense', amount: 600 },
    ]
    expect(summarizeBudget(items)).toEqual({ income: 4500, expenses: 2400, leftover: 2100 })
  })

  it('handles an empty budget', () => {
    expect(summarizeBudget([])).toEqual({ income: 0, expenses: 0, leftover: 0 })
  })
})

describe('splitAmount', () => {
  it('divides an amount proportionally across pool percentages', () => {
    const pools = [
      { id: 'a', percent: 50 },
      { id: 'b', percent: 30 },
      { id: 'c', percent: 20 },
    ]
    const result = splitAmount(1000, pools)
    expect(result.map((pool) => pool.share)).toEqual([500, 300, 200])
  })

  it('normalizes against pool percentages that do not sum to 100', () => {
    const pools = [{ id: 'a', percent: 25 }, { id: 'b', percent: 25 }]
    const result = splitAmount(100, pools)
    expect(result.map((pool) => pool.share)).toEqual([50, 50])
  })

  it('returns zero shares when there is nothing to split', () => {
    const pools = [{ id: 'a', percent: 50 }]
    expect(splitAmount(0, pools).map((pool) => pool.share)).toEqual([0])
    expect(splitAmount(100, []).length).toBe(0)
  })
})
