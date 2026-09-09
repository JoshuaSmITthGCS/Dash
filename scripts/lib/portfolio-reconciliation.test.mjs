import { describe, expect, it } from 'vitest'
import { eventActivityIds, planActivityReconciliation } from './portfolio-reconciliation.mjs'

// The exact Sep 1-4, 2026 delta for account Z32641125, on top of the Aug 25 seed. This is the
// real fixture (scripts/fixtures/fidelity-activity-since-seed.json) inlined so a change to that
// file can't silently change what this test asserts.
const REAL_DELTA_EVENTS = [
  { kind: 'dividend', ticker: 'SCHW', date: '2026-08-28', amount: 0.63 },
  { kind: 'deposit', date: '2026-09-01', amount: 400 },
  { kind: 'dividend', ticker: 'COP', date: '2026-09-01', amount: 0.35 },
  { kind: 'dividend', ticker: 'SIGI', date: '2026-09-01', amount: 0.89 },
  { kind: 'buy', ticker: 'TSM', date: '2026-09-02', cost: 199.67, shares: 0.482 },
  { kind: 'dividend', ticker: 'DINO', date: '2026-09-02', amount: 0.61 },
  { kind: 'sell', ticker: 'LULU', date: '2026-09-03', proceeds: 102.40, shares: 1 },
  { kind: 'dividend', ticker: 'AGO', date: '2026-09-03', amount: 0.23 },
  { kind: 'sell', ticker: 'NTNX', date: '2026-09-04', proceeds: 67.86, shares: 1 },
  { kind: 'sell', ticker: 'NTNX', date: '2026-09-04', proceeds: 19.26, shares: 0.284 },
]

const SEED_POSITIONS = [
  { id: 'LULU-reference', ticker: 'LULU', shares: 1, costBasis: 117.94, purchaseDate: '2026-07-30' },
  { id: 'NTNX-reference', ticker: 'NTNX', shares: 1.284, costBasis: 49.99 / 1.284, purchaseDate: '2026-03-12' },
  { id: 'AAPL-reference', ticker: 'AAPL', shares: 5, costBasis: 100, purchaseDate: '2026-07-23' },
]

describe('planActivityReconciliation on the real Sep 1-4 delta', () => {
  it('closes LULU with the exact realized loss reported by Fidelity', () => {
    const { writes, errors } = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    expect(errors).toEqual([])
    const gain = writes.find((write) => write.collection === 'activity' && write.data.type === 'realized_gain' && write.data.ticker === 'LULU')
    expect(gain.data.amount).toBeCloseTo(-15.54, 2)
    const proceeds = writes.find((write) => write.collection === 'activity' && write.data.type === 'sale_proceeds' && write.data.ticker === 'LULU')
    expect(proceeds.data.amount).toBeCloseTo(102.40, 2)
    const closed = writes.find((write) => write.collection === 'closedPositions' && write.id === 'LULU')
    expect(closed).toBeTruthy()
    expect(closed.data.saleDate).toBe('2026-09-03')
    const positionDelete = writes.find((write) => write.collection === 'positions' && write.id === 'LULU-reference')
    expect(positionDelete.op).toBe('delete')
  })

  it('closes NTNX across its two fills with the exact combined realized gain', () => {
    const { writes, errors } = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    expect(errors).toEqual([])
    const gains = writes.filter((write) => write.collection === 'activity' && write.data.type === 'realized_gain' && write.data.ticker === 'NTNX')
    expect(gains).toHaveLength(2)
    const total = gains.reduce((sum, write) => sum + write.data.amount, 0)
    expect(total).toBeCloseTo(37.13, 1)
    // Only the second (final) fill should close the position -- the first still leaves shares.
    const closedWrites = writes.filter((write) => write.collection === 'closedPositions' && write.id === 'NTNX')
    expect(closedWrites).toHaveLength(1)
  })

  it('adds TSM as a new position at the exact cost basis', () => {
    const { writes, positionsAfter } = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    const tsmPosition = writes.find((write) => write.collection === 'positions' && write.op === 'set' && write.data.ticker === 'TSM')
    expect(tsmPosition.data.shares).toBeCloseTo(0.482, 6)
    expect(tsmPosition.data.costBasis * tsmPosition.data.shares).toBeCloseTo(199.67, 2)
    expect(tsmPosition.data.purchaseDate).toBe('2026-09-02')
    expect(positionsAfter.some((position) => position.ticker === 'TSM')).toBe(true)
  })

  it('leaves AAPL and every other untouched holding alone', () => {
    const { writes } = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    expect(writes.some((write) => write.collection === 'positions' && (write.id === 'AAPL-reference' || write.data?.ticker === 'AAPL'))).toBe(false)
  })

  it('records every dividend and the deposit as their own activity rows', () => {
    const { writes, summary } = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    expect(summary.dividend).toBe(5)
    expect(summary.deposit).toBe(1)
    const deposit = writes.find((write) => write.data?.type === 'deposit')
    expect(deposit.data.amount).toBe(400)
    const scwDividend = writes.find((write) => write.data?.type === 'dividend' && write.data.ticker === 'SCHW')
    expect(scwDividend.data.effectiveDate).toBe('2026-08-28')
  })

  it('total realized gain across the whole delta matches the transcribed total (+$21.59)', () => {
    const { writes } = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    const total = writes
      .filter((write) => write.data?.type === 'realized_gain')
      .reduce((sum, write) => sum + write.data.amount, 0)
    expect(total).toBeCloseTo(21.59, 1)
  })
})

describe('idempotency — the second run must be a no-op', () => {
  it('produces zero writes when every event\'s activity ids already exist', () => {
    const first = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS)
    const existingActivityIds = new Set(
      first.writes.filter((write) => write.collection === 'activity').map((write) => write.id),
    )
    const second = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS, { existingActivityIds })
    expect(second.writes).toEqual([])
    expect(second.summary.skipped).toBe(REAL_DELTA_EVENTS.length)
  })

  it('re-applies only the events whose ids are missing, when a partial run already happened', () => {
    const first = planActivityReconciliation(SEED_POSITIONS, [REAL_DELTA_EVENTS[0], REAL_DELTA_EVENTS[1]])
    const existingActivityIds = new Set(first.writes.filter((write) => write.collection === 'activity').map((write) => write.id))
    const second = planActivityReconciliation(SEED_POSITIONS, REAL_DELTA_EVENTS, { existingActivityIds })
    expect(second.summary.skipped).toBe(2)
    expect(second.summary.dividend + second.summary.deposit + second.summary.buy + second.summary.sell)
      .toBe(REAL_DELTA_EVENTS.length - 2)
  })
})

describe('eventActivityIds', () => {
  it('is deterministic and distinct per event', () => {
    const ids = REAL_DELTA_EVENTS.flatMap(eventActivityIds)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('does not depend on object identity or key order', () => {
    const a = { kind: 'sell', ticker: 'LULU', date: '2026-09-03', proceeds: 102.40, shares: 1 }
    const b = { shares: 1, proceeds: 102.40, date: '2026-09-03', ticker: 'LULU', kind: 'sell' }
    expect(eventActivityIds(a)).toEqual(eventActivityIds(b))
  })
})

describe('validation refuses to guess', () => {
  it('rejects a buy with no share count rather than silently skipping it', () => {
    const { errors, writes } = planActivityReconciliation([], [{ kind: 'buy', ticker: 'TSM', date: '2026-09-02', cost: 199.67 }])
    expect(errors).toHaveLength(1)
    expect(errors[0]).toContain('shares')
    expect(writes).toEqual([])
  })

  it('rejects a sell of a ticker with no open lots', () => {
    const { errors } = planActivityReconciliation([], [{ kind: 'sell', ticker: 'GHOST', date: '2026-09-03', proceeds: 10, shares: 1 }])
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatch(/no open lots/i)
  })

  it('rejects selling more shares than are held', () => {
    const { errors } = planActivityReconciliation(
      [{ id: 'x', ticker: 'AAA', shares: 1, costBasis: 10 }],
      [{ kind: 'sell', ticker: 'AAA', date: '2026-09-03', proceeds: 10, shares: 5 }],
    )
    expect(errors).toHaveLength(1)
  })

  it('rejects a negative or zero amount', () => {
    const { errors } = planActivityReconciliation([], [{ kind: 'deposit', date: '2026-09-01', amount: -50 }])
    expect(errors).toHaveLength(1)
  })

  it('still processes valid events in the same file when one event is invalid', () => {
    const { errors, summary } = planActivityReconciliation([], [
      { kind: 'deposit', date: '2026-09-01', amount: 100 },
      { kind: 'buy', ticker: 'TSM', date: '2026-09-02', cost: 199.67 }, // missing shares
    ])
    expect(errors).toHaveLength(1)
    expect(summary.deposit).toBe(1)
  })
})

describe('multi-fill sequencing within one file', () => {
  it('a buy followed by a sell of the same ticker in the same file sees the new lot', () => {
    const { errors, writes } = planActivityReconciliation([], [
      { kind: 'buy', ticker: 'NEW', date: '2026-09-01', cost: 100, shares: 2 },
      { kind: 'sell', ticker: 'NEW', date: '2026-09-02', proceeds: 60, shares: 1 },
    ])
    expect(errors).toEqual([])
    const closed = writes.some((write) => write.collection === 'closedPositions' && write.id === 'NEW')
    expect(closed).toBe(false) // only 1 of 2 shares sold
  })

  it('events are applied in date order regardless of file order', () => {
    const { errors } = planActivityReconciliation([], [
      { kind: 'sell', ticker: 'NEW', date: '2026-09-02', proceeds: 60, shares: 1 },
      { kind: 'buy', ticker: 'NEW', date: '2026-09-01', cost: 100, shares: 2 },
    ])
    expect(errors).toEqual([])
  })
})
