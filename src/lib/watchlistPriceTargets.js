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

const TIER_PHRASES = {
  cheapest_third: 'the cheapest third of its peer group',
  middle_third: 'the middle third of its peer group',
  most_expensive_third: 'the most expensive third of its peer group',
}

/**
 * A peer-tier-based discount. The input is a tier midpoint from peer_groups.TIER_MIDPOINTS,
 * not a measured percentile -- the ranked quantity is a composite of discrete valuation
 * bands, and peer groups below the minimum sample publish no tier at all, so those names get
 * no suggested discount rather than one derived from a number nobody can support. A name in
 * the cheapest third gets good_buy == current price: there is no invented discount for a name
 * already priced reasonably against its peers.
 */
export function suggestGoodBuyPrice(stock) {
  if (!stock || !finite(stock.price) || stock.price <= 0) return null
  const ordinal = stock.valuation_percentile?.ordinal ?? stock.sector_valuation_percentile
  const tier = stock.valuation_percentile?.tier
  if (!finite(ordinal)) {
    return {
      price: null,
      discountPct: null,
      derivation: 'No peer valuation tier published for this name: its peer group is below the minimum sample needed to rank against.',
    }
  }
  const gap = Math.max(0, config.good_buy.fair_valuation_percentile - ordinal)
  const discountPct = clamp(gap * config.good_buy.discount_pct_per_percentile_point, 0, config.good_buy.max_discount_pct)
  const price = Math.round(stock.price * (1 - discountPct / 100) * 100) / 100
  const where = TIER_PHRASES[tier] || 'its peer group'
  return {
    price,
    discountPct,
    derivation: discountPct > 0
      ? `Valuation score sits in ${where}, so a ${discountPct.toFixed(1)}% discount is suggested before calling this a good entry. Ranks this model's valuation composite, not a price multiple.`
      : `Valuation score already sits in ${where} -- the current price is already a reasonable entry by this measure.`,
  }
}

/** Both targets at once, for the watchlist add flow. */
export function suggestPriceTargets(stock) {
  return {
    dipBuy: suggestDipBuyPrice(stock),
    goodBuy: suggestGoodBuyPrice(stock),
  }
}
