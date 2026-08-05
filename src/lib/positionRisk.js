/** Volatility-scaled position rules referenced only to the post-purchase high-water mark. */

import modelSettings from '../../pipeline/config/settings.json'

export const POSITION_RISK_DEFAULTS = modelSettings.position_risk

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

const clamp = (value, low, high) => Math.max(low, Math.min(high, value))

/** Highest recorded close on or after the purchase date. */
export function peakSincePurchase(position, history) {
  const dates = history?.dates || []
  const closes = history?.closes || []
  const purchaseDate = String(position?.purchaseDate || '').slice(0, 10)
  if (!purchaseDate) return null
  const window = closes.filter((close, index) => dates[index] >= purchaseDate && finite(close))
  return window.length ? Math.max(...window) : null
}

/** Highest observed price for the position, including a new high at the current price. */
export function highWaterMark(position) {
  const observedPeak = peakSincePurchase(position, position?.priceInfo?.history)
  const candidates = [
    position?.highWaterMark,
    position?.purchasePrice,
    observedPeak,
    position?.currentPrice,
  ].filter((value) => finite(value) && value > 0)
  return candidates.length ? Math.max(...candidates) : null
}

/** Wilder-style average true range from daily high, low, and close series. */
export function averageTrueRange(history, lookback = POSITION_RISK_DEFAULTS.atr_lookback_days) {
  const highs = history?.highs || []
  const lows = history?.lows || []
  const closes = history?.closes || []
  if (highs.length !== lows.length || highs.length !== closes.length || closes.length < 2) return null
  const ranges = []
  for (let index = 1; index < closes.length; index += 1) {
    if (![highs[index], lows[index], closes[index - 1]].every(finite)) continue
    ranges.push(Math.max(
      highs[index] - lows[index],
      Math.abs(highs[index] - closes[index - 1]),
      Math.abs(lows[index] - closes[index - 1]),
    ))
  }
  const window = ranges.slice(-lookback)
  return window.length ? window.reduce((sum, value) => sum + value, 0) / window.length : null
}

/** Annualized realized volatility from the latest daily closes. */
export function realizedSigma(history, lookback = POSITION_RISK_DEFAULTS.sigma_lookback_days, tradingDays = POSITION_RISK_DEFAULTS.trading_days_per_year) {
  const closes = (history?.closes || []).filter((value) => finite(value) && value > 0).slice(-(lookback + 1))
  if (closes.length < 3) return null
  const returns = closes.slice(1).map((value, index) => value / closes[index] - 1)
  const average = returns.reduce((sum, value) => sum + value, 0) / returns.length
  const variance = returns.reduce((sum, value) => sum + (value - average) ** 2, 0) / (returns.length - 1)
  return Math.sqrt(variance) * Math.sqrt(tradingDays)
}

function publishedSigma(position, config) {
  const value = position?.annualizedVolatility
    ?? position?.priceInfo?.technical_detail?.annualized_volatility
  if (finite(value) && value > 0) return value > 3 ? value / 100 : value
  return realizedSigma(
    position?.priceInfo?.history,
    config.sigma_lookback_days,
    config.trading_days_per_year,
  )
}

function distanceModel(position, high, config) {
  const atr = position?.atr
    ?? position?.priceInfo?.atr
    ?? position?.priceInfo?.technical_detail?.atr
    ?? averageTrueRange(position?.priceInfo?.history, config.atr_lookback_days)
  if (finite(atr) && atr > 0) {
    return {
      rule: 'atr',
      input: atr,
      trimRaw: config.atr_multiple_trim * atr / high * 100,
      exitRaw: config.atr_multiple_exit * atr / high * 100,
    }
  }
  const sigma = publishedSigma(position, config)
  if (finite(sigma) && sigma > 0) {
    const dailySigma = sigma / Math.sqrt(config.trading_days_per_year)
    return {
      rule: 'sigma',
      input: sigma,
      trimRaw: config.atr_multiple_trim * dailySigma * 100,
      exitRaw: config.atr_multiple_exit * dailySigma * 100,
    }
  }
  return {
    rule: 'fallback_fixed',
    input: null,
    trimRaw: config.fallback_trim_pct,
    exitRaw: config.fallback_exit_pct,
  }
}

function explanation(levels, config) {
  const reference = `$${levels.highWaterMark.toFixed(2)} high-water mark`
  if (levels.rule === 'atr') {
    return `Trim at $${levels.trimPrice.toFixed(2)} and exit at $${levels.exitPrice.toFixed(2)}, both measured from the ${reference}. The ${levels.trimDistancePct.toFixed(1)}% and ${levels.exitDistancePct.toFixed(1)}% distances use ${config.atr_multiple_trim}x and ${config.atr_multiple_exit}x ATR for this name. Wider levels are intentional when normal price movement is larger.`
  }
  if (levels.rule === 'sigma') {
    return `Trim at $${levels.trimPrice.toFixed(2)} and exit at $${levels.exitPrice.toFixed(2)}, both measured from the ${reference}. The distances use ${config.sigma_lookback_days}-day realized volatility because ATR is unavailable. Wider levels are intentional when normal price movement is larger.`
  }
  return `Trim at $${levels.trimPrice.toFixed(2)} and exit at $${levels.exitPrice.toFixed(2)}, both measured from the ${reference}. Price-range and realized-volatility inputs are unavailable, so the rule uses the configured fixed fallback.`
}

/**
 * Compute trim and exit levels as ``high_water * (1 - clamped_distance_pct)``.
 * Cost basis is deliberately absent from the formula and remains display-only elsewhere.
 */
export function stopLossLevels(position, thresholds = {}) {
  const config = { ...POSITION_RISK_DEFAULTS, ...thresholds }
  if (!finite(position?.currentPrice) || position.currentPrice <= 0) return null
  const high = highWaterMark(position)
  if (!finite(high) || high <= 0) return null
  const model = distanceModel(position, high, config)
  const trimDistancePct = clamp(model.trimRaw, config.min_stop_distance_pct, config.max_stop_distance_pct)
  const exitDistancePct = clamp(model.exitRaw, config.min_stop_distance_pct, config.max_stop_distance_pct)
  const trimPrice = high * (1 - trimDistancePct / 100)
  const exitPrice = high * (1 - exitDistancePct / 100)
  const triggeredAction = position.currentPrice <= exitPrice ? 'SELL' : position.currentPrice <= trimPrice ? 'TRIM' : null
  const bindingPrice = triggeredAction === 'SELL' ? exitPrice : trimPrice
  const levels = {
    rule: model.rule,
    volatilityInput: model.input,
    highWaterMark: high,
    trimDistancePct,
    exitDistancePct,
    trimPrice,
    exitPrice,
    bindingPrice,
    bindingSource: model.rule,
    distancePct: (position.currentPrice / bindingPrice - 1) * 100,
    triggeredAction,
  }
  return { ...levels, explanation: explanation(levels, config) }
}

export function assessPositionStopLoss(position, thresholds = {}) {
  const levels = stopLossLevels(position, thresholds)
  if (!levels?.triggeredAction) return null
  const selling = levels.triggeredAction === 'SELL'
  const threshold = selling ? levels.exitPrice : levels.trimPrice
  const reasons = [
    `Current price $${position.currentPrice.toFixed(2)} is below the $${threshold.toFixed(2)} ${selling ? 'exit' : 'trim'} level measured from the $${levels.highWaterMark.toFixed(2)} high-water mark`,
    levels.explanation,
  ]
  return {
    ...levels,
    action: levels.triggeredAction,
    severity: selling ? 'severe' : 'moderate',
    reasons,
    drawdownFromPeakPct: (position.currentPrice / levels.highWaterMark - 1) * 100,
    peakSincePurchase: levels.highWaterMark,
  }
}

const ACTION_RANK = { HOLD: 0, WATCH: 1, TRIM: 2, SELL: 3 }
const STOP_LOSS_TRIM = { HOLD: 0, WATCH: 0, TRIM: 33, SELL: 100 }

/** Keep the more defensive of independent company guidance and position risk. */
export function withStopLoss(recommendation, position, thresholds = {}) {
  const stopLoss = assessPositionStopLoss(position, thresholds)
  if (!stopLoss) return recommendation
  const base = recommendation || { action: 'HOLD', reasons: [], suggestedTrimPct: 0, agreementCount: 0 }
  const upgraded = ACTION_RANK[stopLoss.action] > (ACTION_RANK[base.action] ?? 0)
  return {
    ...base,
    action: upgraded ? stopLoss.action : base.action,
    suggestedTrimPct: Math.max(base.suggestedTrimPct || 0, STOP_LOSS_TRIM[stopLoss.action] || 0),
    summary: upgraded ? stopLoss.reasons[0] : base.summary,
    reasons: [...stopLoss.reasons, ...(base.reasons || [])],
    stopLossTrigger: stopLoss,
    companyRecommendation: base,
    positionAction: {
      action: stopLoss.action,
      suggestedTrimPct: STOP_LOSS_TRIM[stopLoss.action] || 0,
      reasonCode: stopLoss.severity === 'severe' ? 'hard_stop_breached' : 'defensive_stop_breached',
      reasons: stopLoss.reasons,
    },
    source: upgraded ? 'stop_loss' : base.source,
  }
}
