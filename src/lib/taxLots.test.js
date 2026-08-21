import { describe, expect, it } from 'vitest'
import { lotCountsByTicker, lotsForTicker, planFifoSale, realizedGainForPlan } from './taxLots.js'

const lot = (id, ticker, shares, costBasis, purchaseDate) => ({ id, ticker, shares, costBasis, purchaseDate })

describe('lotsForTicker', () => {
  it('filters to the ticker and sorts oldest purchase date first', () => {
    const positions = [
      lot('c', 'AAPL', 5, 150, '2026-03-01'),
      lot('a', 'AAPL', 10, 100, '2026-01-01'),
      lot('other', 'MSFT', 20, 200, '2026-01-01'),
      lot('b', 'AAPL', 8, 120, '2026-02-01'),
    ]
    expect(lotsForTicker(positions, 'AAPL').map((row) => row.id)).toEqual(['a', 'b', 'c'])
  })

  it('is case-insensitive on ticker and excludes zero/negative-share rows', () => {
    const positions = [lot('a', 'aapl', 10, 100, '2026-01-01'), lot('b', 'AAPL', 0, 100, '2026-02-01')]
    expect(lotsForTicker(positions, 'AAPL').map((row) => row.id)).toEqual(['a'])
  })
})

describe('planFifoSale', () => {
  const positions = [
    lot('a', 'AAPL', 10, 100, '2026-01-01'),
    lot('b', 'AAPL', 8, 120, '2026-02-01'),
    lot('c', 'AAPL', 5, 150, '2026-03-01'),
  ]

  it('depletes the single oldest lot when it fully covers the sale', () => {
    const plan = planFifoSale(positions, 'AAPL', 6)
    expect(plan.available).toBe(true)
    expect(plan.depletions).toHaveLength(1)
    expect(plan.depletions[0]).toMatchObject({ positionId: 'a', quantity: 6, remainingAfter: 4, costBasisPerUnit: 100 })
  })

  it('spans multiple lots oldest-first when one lot is not enough', () => {
    const plan = planFifoSale(positions, 'AAPL', 15)
    expect(plan.depletions).toEqual([
      expect.objectContaining({ positionId: 'a', quantity: 10, remainingAfter: 0, costBasisPerUnit: 100 }),
      expect.objectContaining({ positionId: 'b', quantity: 5, remainingAfter: 3, costBasisPerUnit: 120 }),
    ])
  })

  it('fully depletes every lot when selling exactly the total held', () => {
    const plan = planFifoSale(positions, 'AAPL', 23)
    expect(plan.depletions).toHaveLength(3)
    expect(plan.depletions.every((row) => row.remainingAfter === 0)).toBe(true)
  })

  it('is unavailable when the requested quantity exceeds total holdings', () => {
    const plan = planFifoSale(positions, 'AAPL', 24)
    expect(plan.available).toBe(false)
    expect(plan.reason).toContain('Only 23 shares')
  })

  it('is unavailable for a ticker with no open lots', () => {
    const plan = planFifoSale(positions, 'ZZZZ', 1)
    expect(plan.available).toBe(false)
    expect(plan.reason).toContain('No open lots')
  })

  it('rejects a non-positive quantity', () => {
    expect(planFifoSale(positions, 'AAPL', 0).available).toBe(false)
    expect(planFifoSale(positions, 'AAPL', -5).available).toBe(false)
  })
})

describe('realizedGainForPlan', () => {
  const positions = [
    lot('a', 'AAPL', 10, 100, '2026-01-01'),
    lot('b', 'AAPL', 8, 120, '2026-02-01'),
  ]

  it('computes proceeds, cost basis, and realized gain per lot and in total', () => {
    const plan = planFifoSale(positions, 'AAPL', 15)
    const gain = realizedGainForPlan(plan, 150)
    // Lot a: 10 @ (150-100) = 500. Lot b: 5 @ (150-120) = 150. Total 650.
    expect(gain.perLot[0].realizedGain).toBeCloseTo(500, 6)
    expect(gain.perLot[1].realizedGain).toBeCloseTo(150, 6)
    expect(gain.totalRealizedGain).toBeCloseTo(650, 6)
    expect(gain.totalProceeds).toBeCloseTo(15 * 150, 6)
    expect(gain.totalCostBasis).toBeCloseTo(10 * 100 + 5 * 120, 6)
  })

  it('supports a loss (negative realized gain)', () => {
    const plan = planFifoSale(positions, 'AAPL', 10)
    const gain = realizedGainForPlan(plan, 80)
    expect(gain.totalRealizedGain).toBeCloseTo(10 * (80 - 100), 6)
  })

  it('returns null for an unavailable plan or a non-finite price', () => {
    const unavailable = planFifoSale(positions, 'AAPL', 999)
    expect(realizedGainForPlan(unavailable, 150)).toBeNull()
    const plan = planFifoSale(positions, 'AAPL', 5)
    expect(realizedGainForPlan(plan, NaN)).toBeNull()
  })
})

describe('lotCountsByTicker', () => {
  it('counts open lots per ticker, ignoring zero-share rows', () => {
    const positions = [
      lot('a', 'AAPL', 10, 100, '2026-01-01'),
      lot('b', 'AAPL', 8, 120, '2026-02-01'),
      lot('c', 'MSFT', 5, 200, '2026-01-01'),
      lot('d', 'MSFT', 0, 200, '2026-02-01'),
    ]
    expect(lotCountsByTicker(positions)).toEqual({ AAPL: 2, MSFT: 1 })
  })
})
