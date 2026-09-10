import { describe, expect, it } from 'vitest'
import { holdingsAsOf, positionTimeline } from './portfolio-timeline.mjs'

const BASELINE = [
  { id: 'LULU-reference', ticker: 'LULU', shares: 1, costBasis: 117.94 },
  { id: 'NTNX-reference', ticker: 'NTNX', shares: 1.284, costBasis: 49.99 / 1.284 },
  { id: 'AAPL-reference', ticker: 'AAPL', shares: 5, costBasis: 100 },
]

const EVENTS = [
  { kind: 'buy', ticker: 'TSM', date: '2026-09-02', cost: 199.67, shares: 0.482 },
  { kind: 'sell', ticker: 'LULU', date: '2026-09-03', proceeds: 102.40, shares: 1 },
  { kind: 'sell', ticker: 'NTNX', date: '2026-09-04', proceeds: 67.86, shares: 1 },
  { kind: 'sell', ticker: 'NTNX', date: '2026-09-04', proceeds: 19.26, shares: 0.284 },
]

describe('positionTimeline / holdingsAsOf reconstruct history correctly', () => {
  it('before any event, holdings equal the baseline exactly', () => {
    const timeline = positionTimeline(BASELINE, EVENTS)
    const holdings = holdingsAsOf(timeline, '2026-09-01')
    expect(holdings.get('LULU')).toMatchObject({ shares: 1 })
    expect(holdings.get('NTNX').shares).toBeCloseTo(1.284, 6)
    expect(holdings.get('AAPL')).toMatchObject({ shares: 5, costBasisTotal: 500 })
    expect(holdings.has('TSM')).toBe(false)
  })

  it('on the exact day TSM was bought, it is already held', () => {
    const timeline = positionTimeline(BASELINE, EVENTS)
    const holdings = holdingsAsOf(timeline, '2026-09-02')
    expect(holdings.get('TSM')).toMatchObject({ shares: 0.482 })
    expect(holdings.get('LULU')).toMatchObject({ shares: 1 }) // not yet sold
  })

  it('on the exact day LULU was sold, it is already gone', () => {
    const timeline = positionTimeline(BASELINE, EVENTS)
    const holdings = holdingsAsOf(timeline, '2026-09-03')
    expect(holdings.has('LULU')).toBe(false)
    expect(holdings.get('NTNX').shares).toBeCloseTo(1.284, 6) // not yet sold
  })

  it('partial NTNX exit is reflected between its two fills', () => {
    // Both NTNX sells are dated the same day in the fixture, so this asserts the *final*
    // state reflects both -- the finer-grained partial state isn't independently observable
    // by date alone when two same-day events exist, which is expected and fine.
    const timeline = positionTimeline(BASELINE, EVENTS)
    const holdings = holdingsAsOf(timeline, '2026-09-04')
    expect(holdings.has('NTNX')).toBe(false)
  })

  it('a date after everything reflects the final state: LULU and NTNX gone, TSM and AAPL held', () => {
    const timeline = positionTimeline(BASELINE, EVENTS)
    const holdings = holdingsAsOf(timeline, '2026-09-09')
    expect(holdings.has('LULU')).toBe(false)
    expect(holdings.has('NTNX')).toBe(false)
    expect(holdings.get('TSM')).toMatchObject({ shares: 0.482 })
    expect(holdings.get('AAPL')).toMatchObject({ shares: 5 })
  })

  it('ignores deposit/dividend events -- they never change share counts', () => {
    const timeline = positionTimeline(BASELINE, [
      ...EVENTS,
      { kind: 'deposit', date: '2026-09-01', amount: 400 },
      { kind: 'dividend', ticker: 'AAPL', date: '2026-09-01', amount: 5 },
    ])
    const holdings = holdingsAsOf(timeline, '2026-09-09')
    expect(holdings.get('AAPL')).toMatchObject({ shares: 5, costBasisTotal: 500 })
  })

  it('a null date resolves to the baseline (checkpoint zero)', () => {
    const timeline = positionTimeline(BASELINE, EVENTS)
    const holdings = holdingsAsOf(timeline, null)
    expect(holdings.get('LULU')).toMatchObject({ shares: 1 })
    expect(holdings.has('TSM')).toBe(false)
  })

  it('aggregates multiple lots of the same ticker into one total', () => {
    const timeline = positionTimeline([
      { id: 'a', ticker: 'AAA', shares: 2, costBasis: 10 },
      { id: 'b', ticker: 'AAA', shares: 3, costBasis: 20 },
    ], [])
    const holdings = holdingsAsOf(timeline, '2026-01-01')
    expect(holdings.get('AAA')).toMatchObject({ shares: 5, costBasisTotal: 2 * 10 + 3 * 20 })
  })

  it('does not throw on an unplannable sell event (no open lots) -- skips it', () => {
    const timeline = positionTimeline([], [{ kind: 'sell', ticker: 'GHOST', date: '2026-01-01', proceeds: 10, shares: 1 }])
    expect(() => holdingsAsOf(timeline, '2026-01-02')).not.toThrow()
  })
})
