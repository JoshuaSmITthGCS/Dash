/**
 * Evidence Strength Calculator
 *
 * Replaces "Confidence" with honest assessment of data quality.
 * Based on: metric coverage, data freshness, factor agreement, stale/null inputs
 * NOT based on same weights driving the score itself.
 */

/**
 * Calculate evidence strength (0-1)
 *
 * @param {Object} stock - Stock data object
 * @param {Object} options - Configuration options
 * @returns {number} Evidence strength (0-1)
 */
export function calculateEvidenceStrength(stock, options = {}) {
  const {
    requiredMetrics = [
      'price', 'market_cap', 'peg', 'forward_pe', 'price_to_sales',
      'roe', 'profit_margin', 'debt_to_equity', 'current_ratio',
      'revenue_growth_yoy', 'earnings_growth_yoy'
    ],
    freshnessThresholdHours = 36,
    factorWeights = {
      coverage: 0.40,      // Metric coverage
      freshness: 0.25,     // Data freshness
      agreement: 0.25,     // Factor agreement
      nullPenalty: 0.10    // Penalty for critical nulls
    }
  } = options

  // 1. Metric Coverage (40%)
  const coverageScore = calculateCoverage(stock, requiredMetrics)

  // 2. Data Freshness (25%)
  const freshnessScore = calculateFreshness(stock, freshnessThresholdHours)

  // 3. Factor Agreement (25%)
  const agreementScore = calculateAgreement(stock)

  // 4. Null Penalty (10%)
  const nullPenaltyScore = calculateNullPenalty(stock)

  // Weighted combination
  const evidenceStrength =
    coverageScore * factorWeights.coverage +
    freshnessScore * factorWeights.freshness +
    agreementScore * factorWeights.agreement +
    nullPenaltyScore * factorWeights.nullPenalty

  return Math.max(0, Math.min(1, evidenceStrength))
}

/**
 * Calculate metric coverage (% of required metrics present)
 */
function calculateCoverage(stock, requiredMetrics) {
  let presentCount = 0

  requiredMetrics.forEach(metric => {
    const value = getNestedValue(stock, metric)
    if (value != null && value !== '' && !isNaN(value)) {
      presentCount++
    }
  })

  return presentCount / requiredMetrics.length
}

/**
 * Calculate data freshness (how recent is the data)
 */
function calculateFreshness(stock, thresholdHours) {
  const generatedAt = stock.generated_at || stock.timestamp

  if (!generatedAt) {
    return 0.5 // Unknown freshness - neutral score
  }

  try {
    const dataAge = Date.now() - new Date(generatedAt).getTime()
    const ageHours = dataAge / (1000 * 60 * 60)

    if (ageHours <= thresholdHours) {
      return 1.0 // Fresh data
    } else if (ageHours <= thresholdHours * 2) {
      return 0.7 // Moderately stale
    } else if (ageHours <= thresholdHours * 4) {
      return 0.4 // Very stale
    } else {
      return 0.2 // Ancient data
    }
  } catch {
    return 0.5 // Parse error - neutral score
  }
}

/**
 * Calculate factor agreement (do fundamentals, technicals, sentiment agree?)
 */
function calculateAgreement(stock) {
  const components = stock.components || {}

  const fundamentals = components.fundamentals
  const technicals = components.market_behavior
  const sentiment = components.news_sentiment

  // Need at least 2 factors to measure agreement
  const availableFactors = [fundamentals, technicals, sentiment]
    .filter(f => f != null && !isNaN(f))

  if (availableFactors.length < 2) {
    return 0.5 // Insufficient factors - neutral score
  }

  // Calculate standard deviation (low = high agreement)
  const mean = availableFactors.reduce((a, b) => a + b, 0) / availableFactors.length
  const variance = availableFactors.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / availableFactors.length
  const stdDev = Math.sqrt(variance)

  // Map std dev to 0-1 score (lower std dev = better agreement)
  // Typical std dev range: 0-30 for scores on 0-100 scale
  const agreementScore = Math.max(0, 1 - (stdDev / 30))

  return agreementScore
}

/**
 * Calculate penalty for critical null/stale inputs
 */
function calculateNullPenalty(stock) {
  const criticalFields = [
    'price',
    'market_cap',
    stock.fundamental_detail?.valuation,
    stock.technical_detail?.return_20d
  ]

  let nullCount = 0
  criticalFields.forEach(field => {
    if (field == null || field === '' || (typeof field === 'object' && Object.keys(field).length === 0)) {
      nullCount++
    }
  })

  // Return 1.0 if no nulls, decrease linearly
  return Math.max(0, 1 - (nullCount / criticalFields.length))
}

/**
 * Get nested value from object (e.g., "fundamental_detail.peg")
 */
function getNestedValue(obj, path) {
  return path.split('.').reduce((current, key) => current?.[key], obj)
}

/**
 * Get evidence strength label for UI display
 */
export function getEvidenceLabel(strength) {
  if (strength >= 0.85) return 'Excellent'
  if (strength >= 0.70) return 'Strong'
  if (strength >= 0.50) return 'Moderate'
  if (strength >= 0.30) return 'Limited'
  return 'Weak'
}

/**
 * Get evidence strength description
 */
export function getEvidenceDescription(strength) {
  const label = getEvidenceLabel(strength)
  const descriptions = {
    'Excellent': 'Comprehensive data, fresh, factors agree',
    'Strong': 'Most metrics present, recent data, good agreement',
    'Moderate': 'Some gaps in data or moderate staleness',
    'Limited': 'Significant data gaps or disagreement between factors',
    'Weak': 'Sparse data, very stale, or major disagreements'
  }
  return descriptions[label] || descriptions['Moderate']
}

/**
 * Calculate detailed breakdown for debugging
 */
export function getEvidenceBreakdown(stock, options = {}) {
  const requiredMetrics = options.requiredMetrics || [
    'price', 'market_cap', 'peg', 'forward_pe', 'price_to_sales',
    'roe', 'profit_margin', 'debt_to_equity', 'current_ratio',
    'revenue_growth_yoy', 'earnings_growth_yoy'
  ]

  return {
    overall: calculateEvidenceStrength(stock, options),
    breakdown: {
      coverage: calculateCoverage(stock, requiredMetrics),
      freshness: calculateFreshness(stock, options.freshnessThresholdHours || 36),
      agreement: calculateAgreement(stock),
      nullPenalty: calculateNullPenalty(stock)
    },
    label: getEvidenceLabel(calculateEvidenceStrength(stock, options)),
    description: getEvidenceDescription(calculateEvidenceStrength(stock, options))
  }
}
