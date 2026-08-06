import modelSettings from '../../pipeline/config/settings.json'

// Distinct from src/lib/dipWatch.js, which is deliberately narrower: it only activates for
// stances the platform already treats as buy-worthy and only while the stock is currently
// declining. These functions are general-purpose -- any watchlisted name gets a suggestion,
// regardless of current stance or trend, because a watchlist name has not been rated
// "attractive and falling" yet; that's the whole point of watching it.
const config = modelSettings.watchlist_price_targets

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value))
}

/**
 * A volatility-scaled distance below the current price -- the same ATR/sigma-scaling
 * philosophy as positionRisk.js's stop-loss levels, but anchored to the current price
 * (a watchlist name has no purchase high-water-mark to measure from). Bounded so a
 * near-zero-volatility name doesn't produce a meaningless 1% "dip" and a wildly volatile
 * name doesn't produce an unreachable 60% one.
 */
export function suggestDipBuyPrice(stock) {
  if (!stock || !finite(stock.price) || stock.price <= 0) return null
  const volatilityPct = stock.technical_detail?.annualized_volatility
  if (!finite(volatilityPct) || volatilityPct <= 0) {
    return {
      price: null,
      distancePct: null,
      derivation: 'No annualized volatility published for this name yet -- cannot scale a dip distance without it.',
    }
  }
  const distancePct = clamp(
    volatilityPct * config.dip_buy.volatility_multiple,
    config.dip_buy.min_distance_pct,
    config.dip_buy.max_distance_pct,
  )
  return {
    price: Math.round(stock.price * (1 - distancePct / 100) * 100) / 100,
    distancePct,
    derivation: `${distancePct.toFixed(1)}% below the current price of $${stock.price.toFixed(2)}, scaled from this name's ${volatilityPct.toFixed(0)}% annualized volatility (${config.dip_buy.min_distance_pct}-${config.dip_buy.max_distance_pct}% bounds). A heuristic entry cushion, not a prediction that the price will reach it.`,
  }
}

/**
 * A valuation-percentile-based discount: only applies when this name is priced richer than
 * its own configured "fair" percentile against sector/industry peers (peer_groups.py
 * desirability_percentile, where a higher percentile means cheaper than more peers). A name
 * already at or above the fair percentile gets good_buy == current price -- there is no
 * invented discount for a name that is already reasonably priced.
 */
export function suggestGoodBuyPrice(stock) {
  if (!stock || !finite(stock.price) || stock.price <= 0) return null
  const percentile = stock.valuation_percentile?.value ?? stock.sector_valuation_percentile
  if (!finite(percentile)) {
    return {
      price: null,
      discountPct: null,
      derivation: 'No sector-relative valuation percentile published for this name yet.',
    }
  }
  const gap = Math.max(0, config.good_buy.fair_valuation_percentile - percentile)
  const discountPct = clamp(gap * config.good_buy.discount_pct_per_percentile_point, 0, config.good_buy.max_discount_pct)
  const price = Math.round(stock.price * (1 - discountPct / 100) * 100) / 100
  return {
    price,
    discountPct,
    derivation: discountPct > 0
      ? `Cheaper than ${percentile.toFixed(0)}% of peers today (fair is ${config.good_buy.fair_valuation_percentile.toFixed(0)}%), so a ${discountPct.toFixed(1)}% discount is suggested before calling this a good entry.`
      : `Already cheaper than ${percentile.toFixed(0)}% of peers, at or above the ${config.good_buy.fair_valuation_percentile.toFixed(0)}% fair threshold -- the current price is already a reasonable entry by this measure.`,
  }
}

/** Both targets at once, for the watchlist add flow. */
export function suggestPriceTargets(stock) {
  return {
    dipBuy: suggestDipBuyPrice(stock),
    goodBuy: suggestGoodBuyPrice(stock),
  }
}
