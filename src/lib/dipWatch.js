// Buy-the-dip watch: for a stock the platform already rates as attractive but that is
// currently down from its highs, estimate a floor (likely bottom) and a recovery level
// (where the downtrend looks over), so timing an entry has a concrete price band instead
// of "sometime, somewhere lower."
//
// Levels are blended from two horizons: a near-term read (the last 60 days of actual
// closes) that tracks real recent support/resistance the way a chart would, and a
// longer-term read (the 52-week range plus the worst 1-year drawdown) that keeps the
// near-term number honest against how far this name has actually fallen before. A level
// worth setting a real broker alert on should track both.
//
// Deliberately narrow: this only activates for stances the platform already treats as
// buy-worthy, and only while the stock is actually declining - it is not a general-purpose
// price target.

const ELIGIBLE_STANCES = new Set(['ATTRACTIVE', 'PROMISING'])
const DOWN_FROM_HIGH_THRESHOLD = -8 // % off the 52-week high before this is "currently going down"
const RECOVERY_GAIN_OFF_FLOOR = 0.20 // the conventional "+20% off the low" threshold for a new uptrend
const NEAR_FLOOR_BAND = 0.05 // within 5% of the floor counts as "at the bottom"
const RECENT_WINDOW_DAYS = 60
const RECENT_WEIGHT = 0.6 // how much the near-term read counts against the long-term one
const BREAKOUT_BUFFER = 0.02 // require clearing the recent high by a bit, not just touching it

function round2(value) {
  return value == null ? null : Math.round(value * 100) / 100
}

// Real high/low over the trailing window, anchored to the data's own latest date rather
// than the device clock - this is committed pipeline data that can be a few days old.
function recentHighLow(history, days) {
  const dates = history?.dates
  const closes = history?.closes
  if (!Array.isArray(dates) || !Array.isArray(closes) || dates.length === 0) return null
  const anchor = new Date(dates[dates.length - 1]).getTime()
  if (!Number.isFinite(anchor)) return null
  const cutoff = anchor - days * 24 * 60 * 60 * 1000
  const window = closes.filter((_, index) => new Date(dates[index]).getTime() >= cutoff)
  if (window.length === 0) return null
  return { high: Math.max(...window), low: Math.min(...window) }
}

export function dipWatch(stock) {
  if (!stock || !ELIGIBLE_STANCES.has(stock.stance)) return null
  if (['TRIM', 'SELL'].includes(stock.recommendation?.action)) return null

  const price = stock.price
  const technical = stock.technical_detail || {}
  const { pct_from_52w_high, pct_above_52w_low, max_drawdown_252d, return_60d } = technical
  if (price == null || price <= 0 || pct_from_52w_high == null || pct_above_52w_low == null) return null

  const isDown = pct_from_52w_high <= DOWN_FROM_HIGH_THRESHOLD && (return_60d == null || return_60d < 0)
  if (!isDown) return null

  const weekHigh = price / (1 + pct_from_52w_high / 100)
  const weekLow = price / (1 + pct_above_52w_low / 100)
  // If the current decline goes on to match the worst 1-year drawdown on record, this is
  // where it bottoms - a second, pattern-based floor estimate to blend with the observed
  // 52-week low rather than trusting either alone.
  const drawdownFloor = max_drawdown_252d != null ? weekHigh * (1 + max_drawdown_252d / 100) : null
  const longTermFloor = drawdownFloor != null ? (weekLow + drawdownFloor) / 2 : weekLow
  const longTermMax = longTermFloor * (1 + RECOVERY_GAIN_OFF_FLOOR)

  const recent = recentHighLow(stock.history, RECENT_WINDOW_DAYS)
  const floor = round2(recent
    ? recent.low * RECENT_WEIGHT + longTermFloor * (1 - RECENT_WEIGHT)
    : longTermFloor)
  const max = round2(recent
    ? recent.high * (1 + BREAKOUT_BUFFER) * RECENT_WEIGHT + longTermMax * (1 - RECENT_WEIGHT)
    : longTermMax)
  if (floor == null || floor <= 0 || max == null || max <= floor) return null

  const status = price >= max ? 'recovering' : price <= floor * (1 + NEAR_FLOOR_BAND) ? 'near_floor' : 'in_range'

  return {
    floor,
    max,
    status,
    distanceToFloorPct: round2(((price - floor) / floor) * 100),
    distanceToMaxPct: round2(((max - price) / price) * 100),
  }
}
