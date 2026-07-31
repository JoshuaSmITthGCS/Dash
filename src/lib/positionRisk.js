/**
 * Position-level stop-loss / trailing-drawdown checks.
 *
 * getRecommendation() judges whether a company's own thesis is intact — fundamentals,
 * price behavior, and sentiment on the stock itself. It has no idea what you paid. A
 * thesis can still be "fine" while a specific entry has moved far enough against you,
 * or given back enough of its gain, to warrant a defensive rule on its own.
 */

const DEFAULTS = {
  costBasisSell: -20, // % below your average cost -> hard stop-loss
  costBasisTrim: -12, // % below your average cost -> defensive trim
  trailingStopTrim: -15, // % below the peak close since purchase -> protect gains
}

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/** Highest weekly close on or after the purchase date. */
export function peakSincePurchase(position, history) {
  const dates = history?.dates || []
  const closes = history?.closes || []
  const purchaseDate = String(position?.purchaseDate || '').slice(0, 10)
  if (!purchaseDate) return null
  const window = closes.filter((close, index) => dates[index] >= purchaseDate && finite(close))
  return window.length ? Math.max(...window) : null
}

/**
 * @param {Object} position - Needs gainPct (% vs cost basis), currentPrice, purchaseDate,
 *   and priceInfo.history (dates/closes) to check the trailing stop.
 */
export function assessPositionStopLoss(position, thresholds = {}) {
  const { costBasisSell, costBasisTrim, trailingStopTrim } = { ...DEFAULTS, ...thresholds }
  if (!finite(position?.gainPct) || !finite(position?.currentPrice)) return null

  const peak = peakSincePurchase(position, position.priceInfo?.history)
  const drawdownFromPeak = finite(peak) && peak > 0
    ? (position.currentPrice / peak - 1) * 100
    : null

  const reasons = []
  let action = null
  let severity = 'none'

  if (position.gainPct <= costBasisSell) {
    action = 'SELL'
    severity = 'severe'
    reasons.push(`Down ${Math.abs(position.gainPct).toFixed(1)}% from your average cost, past the ${Math.abs(costBasisSell)}% stop-loss`)
  } else if (position.gainPct <= costBasisTrim) {
    action = 'TRIM'
    severity = 'moderate'
    reasons.push(`Down ${Math.abs(position.gainPct).toFixed(1)}% from your average cost`)
  }

  if (finite(drawdownFromPeak) && drawdownFromPeak <= trailingStopTrim) {
    if (!action) {
      action = 'TRIM'
      severity = 'moderate'
    }
    reasons.push(`Down ${Math.abs(drawdownFromPeak).toFixed(1)}% from its $${peak.toFixed(2)} peak since you bought it`)
  }

  if (!action) return null
  return {
    action,
    severity,
    reasons,
    drawdownFromCostPct: position.gainPct,
    drawdownFromPeakPct: drawdownFromPeak,
    peakSincePurchase: peak,
  }
}

/**
 * Where the stops actually sit in dollars, and how far away the current price is —
 * computed for every position, not just ones that have already triggered, so the level
 * is visible before you need it rather than only after.
 *
 * @param {Object} position - Needs costBasis, currentPrice, purchaseDate, priceInfo.history.
 */
export function stopLossLevels(position, thresholds = {}) {
  const { costBasisSell, costBasisTrim, trailingStopTrim } = { ...DEFAULTS, ...thresholds }
  if (!finite(position?.costBasis) || !finite(position?.currentPrice) || position.costBasis <= 0) return null

  const peak = peakSincePurchase(position, position.priceInfo?.history)
  const costStopPrice = position.costBasis * (1 + costBasisSell / 100)
  const costTrimPrice = position.costBasis * (1 + costBasisTrim / 100)
  const trailingStopPrice = finite(peak) ? peak * (1 + trailingStopTrim / 100) : null

  // Price falling from above hits whichever floor sits highest first — that's the one
  // that's actually binding right now, cost-basis stop or trailing stop.
  const floors = [costStopPrice, trailingStopPrice].filter(finite)
  const bindingPrice = floors.length ? Math.max(...floors) : null
  const bindingSource = bindingPrice === trailingStopPrice ? 'trailing' : 'cost_basis'
  const distancePct = finite(bindingPrice) && bindingPrice > 0
    ? (position.currentPrice / bindingPrice - 1) * 100
    : null

  return {
    costStopPrice, costTrimPrice, trailingStopPrice, peak,
    bindingPrice, bindingSource, distancePct,
  }
}

const ACTION_RANK = { HOLD: 0, WATCH: 1, TRIM: 2, SELL: 3 }
const STOP_LOSS_TRIM = { HOLD: 0, WATCH: 0, TRIM: 33, SELL: 100 }

/**
 * Combine the stock's own recommendation with a position-specific stop-loss check,
 * keeping whichever action is more defensive and always surfacing the stop-loss reason
 * so it reads as "your entry," not "the business."
 */
export function withStopLoss(recommendation, position, thresholds = {}) {
  const stopLoss = assessPositionStopLoss(position, thresholds)
  if (!stopLoss) return recommendation

  const base = recommendation || { action: 'HOLD', reasons: [], suggestedTrimPct: 0, agreementCount: 0 }
  const upgraded = ACTION_RANK[stopLoss.action] > (ACTION_RANK[base.action] ?? 0)

  return {
    ...base,
    action: upgraded ? stopLoss.action : base.action,
    suggestedTrimPct: Math.max(base.suggestedTrimPct || 0, STOP_LOSS_TRIM[stopLoss.action] || 0),
    summary: upgraded
      ? stopLoss.reasons[0]
      : base.summary,
    reasons: [...stopLoss.reasons, ...(base.reasons || [])],
    stopLossTrigger: stopLoss,
    source: upgraded ? 'stop_loss' : base.source,
  }
}
