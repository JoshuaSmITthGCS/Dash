/**
 * Sell/Watch Logic with 2+ Factor Agreement
 *
 * Rule: Only flag Sell/Trim/Watch when at least TWO of these agree:
 * 1. Deteriorating fundamentals
 * 2. Broken technical behavior
 * 3. Persistent + material negative sentiment
 *
 * NEVER trigger on:
 * - Price movement alone
 * - Single headline
 * - One factor in isolation
 */

/**
 * Assess fundamental deterioration
 *
 * @param {Object} stock - Stock data
 * @param {Object} previousData - Previous period data (optional)
 * @returns {Object} { deteriorating: boolean, severity: string, reasons: Array }
 */
export function assessFundamentals(stock, previousData = null) {
  const reasons = []
  let deteriorating = false
  let severity = 'none' // 'none', 'mild', 'moderate', 'severe'

  const fundamentalScore = stock.components?.fundamentals || stock.fundamental_score
  const fundamentalDetail = stock.fundamental_detail || {}

  // Check if fundamental score is declining
  if (previousData && fundamentalScore != null) {
    const previousFundScore = previousData.components?.fundamentals || previousData.fundamental_score
    if (previousFundScore != null && fundamentalScore < previousFundScore - 10) {
      deteriorating = true
      severity = 'moderate'
      reasons.push(`Fundamental score declined ${(previousFundScore - fundamentalScore).toFixed(1)} points`)
    }
  }

  // Check if fundamental score is below threshold
  if (fundamentalScore != null && fundamentalScore < 50) {
    deteriorating = true
    severity = fundamentalScore < 30 ? 'severe' : 'moderate'
    reasons.push(`Low fundamental score: ${fundamentalScore.toFixed(1)}`)
  }

  // Check specific fundamental deterioration
  const valuation = fundamentalDetail.valuation || {}

  // Valuation concerns (but don't trigger sell alone)
  if (valuation.forward_pe > 40 && stock.peg > 3) {
    reasons.push('Extremely high valuation (P/E > 40, PEG > 3)')
  }

  // Profitability concerns
  if (stock.roe != null && stock.roe < 5) {
    deteriorating = true
    reasons.push('Poor return on equity (< 5%)')
  }

  // Financial health concerns
  if (stock.debt_to_equity != null && stock.debt_to_equity > 2.5) {
    deteriorating = true
    reasons.push('High leverage (D/E > 2.5)')
  }

  if (stock.current_ratio != null && stock.current_ratio < 1.0) {
    deteriorating = true
    severity = 'moderate'
    reasons.push('Liquidity concerns (current ratio < 1.0)')
  }

  // Declining growth
  if (stock.revenue_growth_yoy != null && stock.revenue_growth_yoy < -10) {
    deteriorating = true
    severity = 'moderate'
    reasons.push(`Revenue declining ${stock.revenue_growth_yoy.toFixed(1)}%`)
  }

  return {
    deteriorating,
    severity,
    reasons,
    score: fundamentalScore
  }
}

/**
 * Assess broken technical behavior
 *
 * @param {Object} stock - Stock data
 * @returns {Object} { broken: boolean, severity: string, reasons: Array }
 */
export function assessTechnicals(stock) {
  const reasons = []
  let broken = false
  let severity = 'none'

  const technical = stock.technical_detail || {}

  // Major drawdown
  if (technical.return_20d != null && technical.return_20d < -15) {
    broken = true
    severity = technical.return_20d < -25 ? 'severe' : 'moderate'
    reasons.push(`Significant 20-day decline: ${technical.return_20d.toFixed(1)}%`)
  }

  // Extended decline across multiple timeframes
  const return_5d = technical.return_5d || 0
  const return_20d = technical.return_20d || 0
  const return_60d = technical.return_60d || 0

  if (return_5d < -5 && return_20d < -10 && return_60d < -15) {
    broken = true
    severity = 'severe'
    reasons.push('Consistent decline across all timeframes (5D, 20D, 60D negative)')
  }

  // Relative weakness vs SPY
  if (technical.relative_strength_20d != null && technical.relative_strength_20d < -20) {
    broken = true
    severity = 'moderate'
    reasons.push(`Underperforming SPY by ${Math.abs(technical.relative_strength_20d).toFixed(1)}%`)
  }

  // High volatility (if available)
  if (technical.volatility != null && technical.volatility > 50) {
    reasons.push('Elevated volatility')
  }

  return {
    broken,
    severity,
    reasons,
    return_20d: technical.return_20d
  }
}

/**
 * Assess persistent negative sentiment
 *
 * @param {Object} sentimentData - Aggregated sentiment from sentimentEngine
 * @returns {Object} { persistent: boolean, severity: string, reasons: Array }
 */
export function assessSentiment(sentimentData) {
  const reasons = []
  let persistent = false
  let severity = 'none'

  if (!sentimentData || !sentimentData.articles || sentimentData.articles.length === 0) {
    return { persistent: false, severity: 'none', reasons: [] }
  }

  // Check for persistent negative sentiment
  const negativeArticles = sentimentData.articles.filter(a =>
    a.polarity === 'negative' && a.persistence !== 'one-off'
  )

  if (negativeArticles.length >= 3) {
    persistent = true
    severity = negativeArticles.some(a => a.materiality === 'high') ? 'severe' : 'moderate'
    reasons.push(`${negativeArticles.length} persistent negative articles`)
  }

  // Check for high-impact negative events
  const severeNegative = sentimentData.articles.filter(a =>
    a.polarity === 'negative' &&
    a.intensity === 'severe' &&
    a.materiality === 'high'
  )

  if (severeNegative.length >= 1) {
    persistent = true
    severity = 'severe'
    reasons.push(`High-impact negative event: ${severeNegative[0].category}`)
  }

  // Check dominant category
  const { dominantCategory, avgPolarity, overallImpact } = sentimentData

  if (avgPolarity < -0.3 && overallImpact > 0.4) {
    persistent = true
    severity = 'moderate'
    reasons.push(`Strongly negative ${dominantCategory} news (impact: ${(overallImpact * 100).toFixed(0)}%)`)
  }

  return {
    persistent,
    severity,
    reasons,
    dominantCategory: sentimentData.dominantCategory,
    impact: sentimentData.overallImpact
  }
}

/**
 * Determine sell/watch recommendation based on factor agreement
 *
 * @param {Object} stock - Stock data
 * @param {Object} previousData - Previous period data (optional)
 * @param {Object} sentimentData - Aggregated sentiment data
 * @returns {Object} Recommendation with justification
 */
export function getSellWatchRecommendation(stock, previousData = null, sentimentData = null) {
  const fundamentals = assessFundamentals(stock, previousData)
  const technicals = assessTechnicals(stock)
  const sentiment = assessSentiment(sentimentData)

  // Count how many factors are signaling problems
  const factors = [
    { name: 'fundamentals', ...fundamentals },
    { name: 'technicals', ...technicals },
    { name: 'sentiment', ...sentiment }
  ]

  const concernedFactors = factors.filter(f =>
    (f.deteriorating || f.broken || f.persistent)
  )

  // Require 2+ factors to agree
  if (concernedFactors.length < 2) {
    return {
      action: 'HOLD',
      confidence: 'high',
      reason: 'No multi-factor agreement for sell signal',
      factors: factors.map(f => ({
        name: f.name,
        status: f.deteriorating || f.broken || f.persistent ? 'concerning' : 'normal',
        severity: f.severity,
        reasons: f.reasons
      }))
    }
  }

  // Determine severity of recommendation
  const severityLevels = concernedFactors.map(f => f.severity)
  const hasSevere = severityLevels.includes('severe')
  const hasMultipleModerate = severityLevels.filter(s => s === 'moderate').length >= 2

  let action = 'WATCH'
  let confidence = 'moderate'

  if (hasSevere && concernedFactors.length >= 2) {
    action = 'SELL'
    confidence = 'high'
  } else if (hasMultipleModerate || concernedFactors.length >= 3) {
    action = 'TRIM'
    confidence = 'high'
  }

  // Build justification
  const factorSummary = concernedFactors
    .map(f => `${f.name} (${f.severity})`)
    .join(', ')

  const allReasons = concernedFactors
    .flatMap(f => f.reasons)
    .slice(0, 5) // Limit to top 5 reasons

  return {
    action, // 'HOLD', 'WATCH', 'TRIM', 'SELL'
    confidence, // 'moderate', 'high'
    reason: `${concernedFactors.length} factors agree: ${factorSummary}`,
    factors: factors.map(f => ({
      name: f.name,
      status: f.deteriorating || f.broken || f.persistent ? 'concerning' : 'normal',
      severity: f.severity,
      reasons: f.reasons
    })),
    topReasons: allReasons,
    agreementCount: concernedFactors.length
  }
}

/**
 * Get human-readable action label and description
 */
export function getActionLabel(action) {
  const labels = {
    'HOLD': {
      label: 'Hold',
      description: 'Maintain current position',
      color: 'success'
    },
    'WATCH': {
      label: 'Watch',
      description: 'Monitor closely, consider defensive position sizing',
      color: 'warning'
    },
    'TRIM': {
      label: 'Trim',
      description: 'Reduce position by 25-50%',
      color: 'caution'
    },
    'SELL': {
      label: 'Sell',
      description: 'Exit position, redeploy capital',
      color: 'danger'
    }
  }

  return labels[action] || labels['HOLD']
}

/**
 * Format sell/watch analysis for UI display
 */
export function formatSellWatchAnalysis(recommendation) {
  const actionInfo = getActionLabel(recommendation.action)

  return {
    ...recommendation,
    ...actionInfo,
    summary: `${actionInfo.label}: ${recommendation.reason}`,
    detailedAnalysis: recommendation.factors.map(f => ({
      factor: f.name.charAt(0).toUpperCase() + f.name.slice(1),
      status: f.status,
      severity: f.severity,
      concerns: f.reasons.join('. ')
    }))
  }
}
