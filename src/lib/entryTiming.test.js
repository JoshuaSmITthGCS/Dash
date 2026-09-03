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
    // A real published row always carries a confidence measurement; entry timing is gated
    // on it, so a fixture without one is not a row the pipeline could ever produce.
    data_coverage: 0.82,
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

  it('calls out a computed support level confirming the dip floor, when one is near', () => {
    const example = stock(81, {
      technical_detail: {
        pct_from_52w_high: (81 / WEEK_HIGH - 1) * 100,
        pct_above_52w_low: (81 / WEEK_LOW - 1) * 100,
        max_drawdown_252d: MAX_DRAWDOWN_252D,
        return_60d: -12,
        support_resistance: {
          nearest_support: 79, support_distance_pct: 2.5, support_touch_count: 3,
        },
      },
    })

    const result = entryTiming(example)

    expect(result.supportConfirmed).toBe(true)
    expect(result.reason).toMatch(/tested 3x before/)
  })

  it('says nothing extra when no computed support level is near', () => {
    const result = entryTiming(stock(81))

    expect(result.supportConfirmed).toBe(false)
    expect(result.reason).not.toMatch(/support level/)
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

  it('withholds Buy Now when confidence is below the actionable floor', () => {
    // The screenshot case: a row showing "Data coverage 0%" also showed "BUY NOW".
    const result = entryTiming(stock(98, {
      data_coverage: 0.2,
      technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 },
    }))

    expect(result.verdict).toBe('insufficient_data')
    expect(result.reason).toMatch(/below the 40% floor/i)
  })

  it('withholds Buy Now when the row publishes no coverage measurement at all', () => {
    // A lightweight universe row: absent evidence, not measured-and-fine.
    const lightweight = stock(98, {
      technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 },
    })
    delete lightweight.data_coverage

    const result = entryTiming(lightweight)

    expect(result.verdict).toBe('insufficient_data')
    expect(result.reason).toMatch(/no data-coverage measurement/i)
  })

  it('says why it is withholding rather than rendering an empty timing cell', () => {
    // The row is buy-worthy by stance, so a blank cell reads as an oversight and invites the
    // reader to fill the gap themselves.
    const result = entryTiming(stock(98, {
      data_coverage: 0.2,
      technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 },
    }))

    expect(result.label).toBe('No timing call')
    expect(result.reason).toMatch(/not enough resolved evidence/i)
  })

  it('still says nothing at all for a name the platform is telling you to sell', () => {
    // Different case entirely: this is not "we cannot tell", it is "not a buy candidate".
    expect(entryTiming(stock(81, { data_coverage: 0.2, recommendation: { action: 'SELL' } }))).toBeNull()
    expect(entryTiming(stock(81, { data_coverage: 0.2, stance: 'MIXED' }))).toBeNull()
  })

  it('downgrades Buy Now to Review at moderate confidence', () => {
    const result = entryTiming(stock(98, {
      data_coverage: 0.65,
      technical_detail: { pct_from_52w_high: -2, pct_above_52w_low: 78, return_60d: 5 },
    }))
    expect(result.verdict).toBe('review')
    expect(result.reason).toMatch(/moderate/i)
  })
})
