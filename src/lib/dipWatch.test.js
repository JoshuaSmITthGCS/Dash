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

describe('dipWatch support cross-check', () => {
  it('is null when the pipeline has not published a support_resistance reading', () => {
    expect(dipWatch(stock(81)).support).toBeNull()
  })

  it('confirms when price sits within the confirmation band of the computed support level', () => {
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
    const result = dipWatch(example)
    expect(result.support).toEqual({
      price: 79, distancePct: 2.5, touchCount: 3, isNear: true,
    })
  })

  it('does not confirm when the computed support level is too far below to count', () => {
    const example = stock(81, {
      technical_detail: {
        pct_from_52w_high: (81 / WEEK_HIGH - 1) * 100,
        pct_above_52w_low: (81 / WEEK_LOW - 1) * 100,
        max_drawdown_252d: MAX_DRAWDOWN_252D,
        return_60d: -12,
        support_resistance: {
          nearest_support: 60, support_distance_pct: 35, support_touch_count: 1,
        },
      },
    })
    expect(dipWatch(example).support.isNear).toBe(false)
  })
})

describe('dipWatch near-term blending', () => {
  // A fixed "today" so the 60-day window is deterministic regardless of when the suite
  // runs - the code anchors to the data's own latest date, not the real clock.
  const TODAY = '2026-08-01'
  const daysBefore = (offset) => {
    const date = new Date(TODAY)
    date.setUTCDate(date.getUTCDate() - offset)
    return date.toISOString().slice(0, 10)
  }

  function historyWithRange({ outOfWindowLow, outOfWindowHigh, recentLow, recentHigh }) {
    return {
      dates: [daysBefore(120), daysBefore(90), daysBefore(45), daysBefore(20), daysBefore(5), daysBefore(0)],
      closes: [outOfWindowLow, outOfWindowHigh, recentHigh, recentLow, (recentLow + recentHigh) / 2, (recentLow + recentHigh) / 2],
    }
  }

  it('blends the recent 60-day range with the long-term read', () => {
    const withHistory = dipWatch(stock(81, {
      history: historyWithRange({ outOfWindowLow: 20, outOfWindowHigh: 500, recentLow: 70, recentHigh: 90 }),
    }))
    const withoutHistory = dipWatch(stock(81))
    // 0.6 * recent + 0.4 * long-term, per the weights in dipWatch.js.
    expect(withHistory.floor).toBeCloseTo(70 * 0.6 + withoutHistory.floor * 0.4, 1)
    expect(withHistory.max).toBeCloseTo(90 * 1.02 * 0.6 + withoutHistory.max * 0.4, 1)
  })

  it('ignores closes older than the 60-day window', () => {
    const result = dipWatch(stock(81, {
      // The out-of-window extremes (20 and 500) would blow the floor/max far outside a
      // sane range if they leaked into the recent-window calculation.
      history: historyWithRange({ outOfWindowLow: 20, outOfWindowHigh: 500, recentLow: 70, recentHigh: 90 }),
    }))
    expect(result.floor).toBeGreaterThan(40)
    expect(result.max).toBeLessThan(150)
  })
})
