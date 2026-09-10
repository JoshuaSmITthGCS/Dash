import { describe, expect, it } from 'vitest'
import { historicalCloseOn, planFullReconstruction, planSnapshotCorrection } from './portfolio-snapshot-correction.mjs'

const PRICE_HISTORY = new Map([
  ['LULU', { dates: ['2026-08-25', '2026-09-01', '2026-09-04', '2026-09-08'], closes: [118.33, 118.00, 100.61, 103.19] }],
  ['NTNX', { dates: ['2026-08-25', '2026-09-01', '2026-09-04', '2026-09-08'], closes: [66.44, 66.69, 68.06, 67.49] }],
  ['TSM', { dates: ['2026-08-25', '2026-09-01', '2026-09-04', '2026-09-08'], closes: [200.00, 205.00, 209.84, 212.00] }],
])

describe('historicalCloseOn', () => {
  it('finds the exact date when available', () => {
    expect(historicalCloseOn(PRICE_HISTORY, 'LULU', '2026-09-04')).toBe(100.61)
  })

  it('falls back to the nearest prior date when the exact date is missing (e.g. a weekend)', () => {
    expect(historicalCloseOn(PRICE_HISTORY, 'LULU', '2026-09-06')).toBe(100.61)
  })

  it('returns null for a ticker with no history at all', () => {
    expect(historicalCloseOn(PRICE_HISTORY, 'GHOST', '2026-09-04')).toBeNull()
  })

  it('returns null for a date before any recorded close', () => {
    expect(historicalCloseOn(PRICE_HISTORY, 'LULU', '2026-01-01')).toBeNull()
  })
})

describe('planSnapshotCorrection — the LULU/TSM scenario, using the app\'s own recorded prices', () => {
  // A snapshot recorded Sep 4 while the bug had LULU wrongly present (already sold in reality)
  // and TSM entirely absent (never entered into the app). NTNX correctly absent by this point.
  const buggySnapshot = {
    id: '2026-09-04T15-00', marketDate: '2026-09-04', recordedAt: '2026-09-04T15:00:00.000Z',
    value: 5500.00, unrealizedGain: 100,
    prices: [
      { ticker: 'LULU', shares: 1, price: 100.61, value: 100.61 },
      { ticker: 'AAPL', shares: 5, price: 200, value: 1000 },
    ],
  }
  const correctHoldings = new Map([
    ['AAPL', { shares: 5, costBasisTotal: 500 }],
    ['TSM', { shares: 0.482, costBasisTotal: 199.67 }],
    // LULU and NTNX correctly absent by Sep 4 -- not in this map at all.
  ])

  it('removes the wrongly-included ticker using the price the app itself recorded', () => {
    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, PRICE_HISTORY)
    const removal = result.changes.find((change) => change.ticker === 'LULU')
    expect(removal).toMatchObject({ action: 'remove', shares: 1, price: 100.61 })
  })

  it('adds the wrongly-excluded ticker using a historical close, and flags it as estimated', () => {
    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, PRICE_HISTORY)
    const addition = result.changes.find((change) => change.ticker === 'TSM')
    expect(addition).toMatchObject({ action: 'add', shares: 0.482, price: 209.84, estimated: true })
  })

  it('computes the corrected total as recorded value plus the exact delta', () => {
    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, PRICE_HISTORY)
    // delta = -100.61 (remove LULU) + 0.482*209.84 (add TSM) = -100.61 + 101.14448
    const expectedDelta = -100.61 + 0.482 * 209.84
    expect(result.delta).toBeCloseTo(expectedDelta, 4)
    expect(result.correctedValue).toBeCloseTo(5500 + expectedDelta, 4)
  })

  it('preserves the original value and unrealized gain rather than discarding them', () => {
    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, PRICE_HISTORY)
    expect(result.originalValue).toBe(5500)
    expect(result.originalUnrealizedGain).toBe(100)
  })

  it('recomputes unrealized gain from the correct cost basis, not the old one', () => {
    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, PRICE_HISTORY)
    // correct cost basis total = 500 (AAPL) + 199.67 (TSM) = 699.67
    expect(result.correctedUnrealizedGain).toBeCloseTo(result.correctedValue - 699.67, 4)
  })

  it('leaves AAPL alone entirely -- it was never wrong', () => {
    const result = planSnapshotCorrection(buggySnapshot, correctHoldings, PRICE_HISTORY)
    expect(result.changes.some((change) => change.ticker === 'AAPL')).toBe(false)
  })
})

describe('planSnapshotCorrection — no correction needed', () => {
  it('returns null when the snapshot already matches the correct holdings', () => {
    const cleanSnapshot = {
      marketDate: '2026-09-08', value: 1512, unrealizedGain: 50,
      prices: [{ ticker: 'AAPL', shares: 5, price: 200, value: 1000 }, { ticker: 'TSM', shares: 0.482, price: 209.84, value: 101.14 }],
    }
    const correctHoldings = new Map([
      ['AAPL', { shares: 5, costBasisTotal: 500 }],
      ['TSM', { shares: 0.482, costBasisTotal: 199.67 }],
    ])
    expect(planSnapshotCorrection(cleanSnapshot, correctHoldings, PRICE_HISTORY)).toBeNull()
  })
})

describe('planSnapshotCorrection — blocked rather than guessed', () => {
  it('refuses a snapshot with no prices array at all, and says why', () => {
    const oldSnapshot = { marketDate: '2026-09-04', value: 5500 }
    const result = planSnapshotCorrection(oldSnapshot, new Map([['AAPL', { shares: 5, costBasisTotal: 500 }]]), PRICE_HISTORY)
    expect(result.blocked).toBe(true)
    expect(result.mode).toBe('no_prices')
  })

  it('reports a specific blocker when a wrongly-excluded ticker has no historical close available', () => {
    const snapshot = { marketDate: '2026-09-04', value: 1000, prices: [{ ticker: 'AAPL', shares: 5, price: 200 }] }
    const correctHoldings = new Map([
      ['AAPL', { shares: 5, costBasisTotal: 500 }],
      ['GHOST', { shares: 1, costBasisTotal: 50 }], // no price history for GHOST anywhere
    ])
    const result = planSnapshotCorrection(snapshot, correctHoldings, PRICE_HISTORY)
    expect(result.blocked).toBe(true)
    expect(result.blockers[0]).toContain('GHOST')
  })

  it('reports a specific blocker when a wrongly-included ticker has no price to remove it by', () => {
    const snapshot = { marketDate: '2026-09-04', value: 1000, prices: [{ ticker: 'MYSTERY', shares: 3 }] } // no price field
    const result = planSnapshotCorrection(snapshot, new Map(), PRICE_HISTORY)
    expect(result.blocked).toBe(true)
    expect(result.blockers[0]).toContain('MYSTERY')
  })
})

describe('planFullReconstruction — the fallback for pre-prices snapshots', () => {
  it('builds a total from historical closes alone and marks it estimated', () => {
    const snapshot = { marketDate: '2026-09-04', value: 9999 } // old recorded value is irrelevant here
    const correctHoldings = new Map([
      ['AAPL', { shares: 5, costBasisTotal: 500 }],
      ['TSM', { shares: 0.482, costBasisTotal: 199.67 }],
    ])
    const priceHistory = new Map([...PRICE_HISTORY, ['AAPL', { dates: ['2026-09-04'], closes: [200] }]])
    const result = planFullReconstruction(snapshot, correctHoldings, priceHistory)
    expect(result.blocked).toBe(false)
    expect(result.estimated).toBe(true)
    expect(result.correctedValue).toBeCloseTo(5 * 200 + 0.482 * 209.84, 4)
    expect(result.originalValue).toBe(9999)
  })

  it('is blocked, not silently wrong, when a held ticker has no historical close at all', () => {
    const snapshot = { marketDate: '2026-09-04', value: 1000 }
    const correctHoldings = new Map([['GHOST', { shares: 1, costBasisTotal: 50 }]])
    const result = planFullReconstruction(snapshot, correctHoldings, PRICE_HISTORY)
    expect(result.blocked).toBe(true)
    expect(result.blockers[0]).toContain('GHOST')
  })

  it('skips a ticker with zero shares rather than pricing a phantom holding', () => {
    const snapshot = { marketDate: '2026-09-04', value: 1000 }
    const correctHoldings = new Map([['AAPL', { shares: 0, costBasisTotal: 0 }]])
    const priceHistory = new Map([['AAPL', { dates: ['2026-09-04'], closes: [200] }]])
    const result = planFullReconstruction(snapshot, correctHoldings, priceHistory)
    expect(result.correctedValue).toBe(0)
  })
})
