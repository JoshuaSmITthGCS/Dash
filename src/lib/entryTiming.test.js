import { describe, expect, it } from 'vitest'
import { dipWatch } from './dipWatch'
import { entryTiming } from './entryTiming'

const WEEK_HIGH = 100
const WEEK_LOW = 55
const MAX_DRAWDOWN_252D = -22

function stock(price, overrides = {}) {
  return {
    ticker: 'TEST',
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

describe('entryTiming', () => {
  it('is Buy Now for a buy-worthy stock that is not currently in a decline', () => {
    // 98 is only 2% off the 52-week high and 60-day return is positive - not dipWatch-eligible.
    const result = entryTiming(stock(98, {
      technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 },
    }))
    expect(result.verdict).toBe('buy_now')
  })

  it('is Set Low Alert for a buy-worthy stock currently down from its highs', () => {
    const result = entryTiming(stock(81))
    expect(result.verdict).toBe('set_low_alert')
    expect(result.alertPrice).toBeGreaterThan(0)
    expect(result.alertPrice).toBeLessThan(81)
  })

  it('suggests dipWatch\'s own floor/max as the alert and recovery prices, not separate numbers', () => {
    const example = stock(81)
    const result = entryTiming(example)
    const watch = dipWatch(example)
    expect(result.alertPrice).toBe(watch.floor)
    expect(result.recoveryPrice).toBe(watch.max)
  })

  it('is null for an ETF', () => {
    expect(entryTiming(stock(81, { is_etf: true }))).toBeNull()
  })

  it('is null for a stance the platform does not treat as buy-worthy', () => {
    expect(entryTiming(stock(81, { stance: 'MIXED' }))).toBeNull()
    expect(entryTiming(stock(98, {
      stance: 'CAUTION',
      technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 },
    }))).toBeNull()
  })

  it('is null when guidance is already Trim or Sell, even if buy-worthy by stance', () => {
    expect(entryTiming(stock(81, { recommendation: { action: 'SELL' } }))).toBeNull()
    expect(entryTiming(stock(81, { recommendation: { action: 'TRIM' } }))).toBeNull()
  })

  it('is null for a missing stock', () => {
    expect(entryTiming(null)).toBeNull()
  })
})
