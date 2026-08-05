import modelSettings from '../../pipeline/config/settings.json'
import { bullBearScore } from './bullBearScore'

const config = modelSettings.watchlist_setup

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value))
}

/**
 * Maps a raw signal x onto 0..1 with
 * s(x) = 1 / (1 + exp(-k * (x - center) / width)).
 * The configured center always maps to 0.5 and width controls the soft transition.
 */
function centeredSubscore(value, center, width) {
  if (!finite(value)) return config.neutral_subscore
  return 1 / (1 + Math.exp(-config.transition_slope * (value - center) / width))
}

/**
 * Combines subscores with G = exp(sum(w_i * ln(s_i)) / sum(w_i)).
 * A zero subscore makes the geometric mean zero, so published Sell stays decisive.
 */
function weightedGeometricMean(subscores) {
  const weighted = Object.entries(config.weights)
  const totalWeight = weighted.reduce((sum, [, weight]) => sum + weight, 0)
  if (weighted.some(([key]) => subscores[key] <= 0)) return 0
  return Math.exp(weighted.reduce(
    (sum, [key, weight]) => sum + weight * Math.log(subscores[key]),
    0,
  ) / totalWeight)
}

function setupLabel(score) {
  if (score >= config.labels.strong_min) return 'Strong Setup'
  if (score >= config.labels.workable_min) return 'Workable Setup'
  if (score >= config.labels.weak_min) return 'Weak Setup'
  return 'Avoid'
}

function annualizedVolatility(stock) {
  const value = stock?.technical_detail?.annualized_volatility
  return finite(value) && value > 0
    ? Math.max(value, config.minimum_annualized_volatility_pct)
    : null
}

/**
 * Sets A_i = cap * min(sigma) / sigma_i for covered names.
 * Therefore A_i * sigma_i is equal across names while every A_i remains at or below cap.
 */
export function inverseVolatilityAllocations(stocks = [], budget = null, maxPositionPct = null) {
  const validBudget = finite(budget) && budget > 0
  const validPct = finite(maxPositionPct) && maxPositionPct > 0
  if (!validBudget || !validPct) return {}
  const cap = budget * clamp(maxPositionPct, 0, 100) / 100
  const readings = stocks
    .map((stock) => [stock?.ticker, annualizedVolatility(stock)])
    .filter(([ticker, volatility]) => ticker && volatility != null)
  if (!readings.length) return {}
  const minimum = Math.min(...readings.map(([, volatility]) => volatility))
  return Object.fromEntries(readings.map(([ticker, volatility]) => [
    ticker,
    Math.min(cap, cap * minimum / volatility),
  ]))
}

export function watchlistGuidance(stock, budget = null, maxPositionPct = null, options = {}) {
  if (!stock) return null
  const thesis = bullBearScore(stock)
  const action = String(stock.recommendation?.action || '').toUpperCase()
  const confidence = finite(stock.confidence) ? stock.confidence : null
  const subscoreValues = {
    thesis: centeredSubscore(thesis?.score, config.thesis_center, config.thesis_transition_width),
    research: centeredSubscore(stock.score, config.research_center, config.research_transition_width),
    confidence: centeredSubscore(confidence, config.confidence_center, config.confidence_transition_width),
    guidance: config.guidance_scores[action] ?? config.neutral_subscore,
  }
  const rawSetupScore = clamp(weightedGeometricMean(subscoreValues) * 100, 0, 100)
  const hardBlockReasons = []
  if (confidence != null && confidence < config.hard_confidence_floor) hardBlockReasons.push('Confidence is below the published evidence floor')
  if (action === 'SELL') hardBlockReasons.push('Published guidance is Sell')
  const hardBlocked = hardBlockReasons.length > 0

  const target = finite(stock.analyst_consensus_target) && stock.analyst_consensus_target > 0
    ? stock.analyst_consensus_target
    : null
  const analystCount = finite(stock.analyst_count) ? stock.analyst_count : null
  const validBudget = finite(budget) && budget > 0
  const validPct = finite(maxPositionPct) && maxPositionPct > 0
  const cappedAllocation = validBudget && validPct
    ? budget * clamp(maxPositionPct, 0, 100) / 100
    : 0
  const requestedMode = options.sizingMode || config.default_sizing_mode
  const volatilityAllocation = finite(options.volatilityAllocation)
    ? Math.min(cappedAllocation, Math.max(0, options.volatilityAllocation))
    : null
  const usesVolatility = requestedMode === 'inverse-volatility' && volatilityAllocation != null
  const allocation = hardBlocked ? 0 : (usesVolatility ? volatilityAllocation : cappedAllocation)
  const shares = allocation > 0 && finite(stock.price) && stock.price > 0
    ? Math.floor((allocation / stock.price) * 1000) / 1000
    : 0
  const score = Math.round(rawSetupScore * 10) / 10

  return {
    verdict: hardBlocked ? 'Avoid' : setupLabel(score),
    setupLabel: hardBlocked ? 'Avoid' : setupLabel(score),
    setupScore: score,
    hardBlocked,
    hardBlockReasons,
    eligibleForSizing: !hardBlocked,
    thesisScore: thesis?.score ?? null,
    subscores: [
      { key: 'thesis', label: 'Thesis', value: subscoreValues.thesis, raw: thesis?.score ?? null },
      { key: 'research', label: 'Research', value: subscoreValues.research, raw: finite(stock.score) ? stock.score : null },
      { key: 'confidence', label: 'Confidence', value: subscoreValues.confidence, raw: confidence },
      { key: 'guidance', label: 'Guidance', value: subscoreValues.guidance, raw: action || null },
    ],
    target,
    analystCount,
    targetUpside: target && finite(stock.price) && stock.price > 0
      ? (target / stock.price - 1) * 100
      : null,
    allocation,
    shares,
    sizingMode: usesVolatility ? 'inverse-volatility' : 'capped',
    sizingFallback: requestedMode === 'inverse-volatility' && !usesVolatility,
    annualizedVolatility: annualizedVolatility(stock),
  }
}
