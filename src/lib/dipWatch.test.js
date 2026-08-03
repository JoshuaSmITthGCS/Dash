import { describe, expect, it } from 'vitest'
import { dipWatch } from './dipWatch'

// Fixed 52-week high/low and worst 1-year drawdown, with price the only thing that varies
// between cases - pct_from_52w_high and pct_above_52w_low are derived from it exactly the
// way the pipeline would report them for that same high/low at a different current price.
const WEEK_HIGH = 100
const WEEK_LOW = 55
const MAX_DRAWDOWN_252D = -22

function stock(price, overrides = {}) {
  return {
    stance: 'ATTRACTIVE',
    price,
    recommendation: { action: 'HOLD' },
    technical_detail: {
      pct_from_52w_high: (price / WEEK_HIGH - 1) * 100,
      pct_above_52w_low: (price / WEEK_LOW - 1) * 100,
      max_drawdown_252d: MAX_DRAWDOWN_252D,
      return_60d: -12,
    },
    ...overrides,
  }
}

describe('dipWatch', () => {
  it('returns a floor below the max and below the 52-week high', () => {
    const result = dipWatch(stock(81))
    expect(result).not.toBeNull()
    expect(result.floor).toBeGreaterThan(0)
    expect(result.max).toBeGreaterThan(result.floor)
    expect(result.floor).toBeLessThan(WEEK_HIGH)
  })

  it('is null for a stance the platform does not treat as buy-worthy', () => {
    expect(dipWatch(stock(81, { stance: 'MIXED' }))).toBeNull()
    expect(dipWatch(stock(81, { stance: 'CAUTION' }))).toBeNull()
  })

  it('is null when a sell/trim signal is already active', () => {
    expect(dipWatch(stock(81, { recommendation: { action: 'SELL' } }))).toBeNull()
    expect(dipWatch(stock(81, { recommendation: { action: 'TRIM' } }))).toBeNull()
  })

  it('is null when the stock is not actually down from its highs', () => {
    expect(dipWatch(stock(98, { technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 } }))).toBeNull()
  })

  it('is null without enough price-history context', () => {
    expect(dipWatch(stock(81, { technical_detail: {} }))).toBeNull()
    expect(dipWatch(stock(null))).toBeNull()
  })

  it('flags near_floor when price sits close to the estimated bottom', () => {
    const { floor } = dipWatch(stock(81))
    expect(dipWatch(stock(floor * 1.02)).status).toBe('near_floor')
  })

  it('flags in_range between the floor and the recovery level', () => {
    const { floor, max } = dipWatch(stock(81))
    expect(dipWatch(stock((floor + max) / 2)).status).toBe('in_range')
  })

  it('flags recovering once price clears the recovery level', () => {
    const { max } = dipWatch(stock(81))
    // A recent bounce can clear the recovery level while the 60-day return is still
    // negative from the preceding decline - that combination is exactly what should read
    // as "recovering", not get excluded by the eligibility gate.
    const price = max * 1.03
    expect(dipWatch(stock(price, {
      technical_detail: {
        pct_from_52w_high: (price / WEEK_HIGH - 1) * 100,
        pct_above_52w_low: (price / WEEK_LOW - 1) * 100,
        max_drawdown_252d: MAX_DRAWDOWN_252D,
        return_60d: -3,
      },
    })).status).toBe('recovering')
  })
})
