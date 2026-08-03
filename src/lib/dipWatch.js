// Buy-the-dip watch: for a stock the platform already rates as attractive but that is
// currently down from its highs, estimate a floor (likely bottom) and a recovery level
// (where the downtrend looks over), so timing an entry has a concrete price band instead
// of "sometime, somewhere lower."
//
// Deliberately narrow: this only activates for stances the platform already treats as
// buy-worthy, and only while the stock is actually declining - it is not a general-purpose
// price target.

const ELIGIBLE_STANCES = new Set(['ATTRACTIVE', 'PROMISING'])
const DOWN_FROM_HIGH_THRESHOLD = -8 // % off the 52-week high before this is "currently going down"
const RECOVERY_GAIN_OFF_FLOOR = 0.20 // the conventional "+20% off the low" threshold for a new uptrend
const NEAR_FLOOR_BAND = 0.05 // within 5% of the floor counts as "at the bottom"

function round2(value) {
  return value == null ? null : Math.round(value * 100) / 100
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
  // A second, pattern-based floor estimate: if this decline goes on to match the worst
  // 1-year drawdown on record, this is where it bottoms. Blended with the observed
  // 52-week low rather than trusting either alone.
  const drawdownFloor = max_drawdown_252d != null ? weekHigh * (1 + max_drawdown_252d / 100) : null
  const floor = round2(drawdownFloor != null ? (weekLow + drawdownFloor) / 2 : weekLow)
  if (floor == null || floor <= 0) return null
  const max = round2(floor * (1 + RECOVERY_GAIN_OFF_FLOOR))

  const status = price >= max ? 'recovering' : price <= floor * (1 + NEAR_FLOOR_BAND) ? 'near_floor' : 'in_range'

  return {
    floor,
    max,
    status,
    distanceToFloorPct: round2(((price - floor) / floor) * 100),
    distanceToMaxPct: round2(((max - price) / price) * 100),
  }
}
