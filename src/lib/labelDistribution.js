/**
 * Label Distribution System
 *
 * Replaces fixed cutoffs with percentile-based distribution calibrated
 * against the actual 120-stock universe. Ensures visible range of labels
 * instead of clustering in middle.
 */

/**
 * Calculate label based on score and universe distribution
 *
 * @param {number} score - Stock's overall score (0-100)
 * @param {Array} universeScores - All scores in the current universe
 * @returns {string} Label: 'Attractive', 'Promising', 'Neutral', 'Caution', or 'Avoid'
 */
export function calculateLabel(score, universeScores = []) {
  if (!score || score < 0) return 'Avoid'
  if (!universeScores || universeScores.length === 0) {
    // Fallback to fixed cutoffs if universe data unavailable
    return calculateLabelFixed(score)
  }

  // Calculate percentile rank of this score in the universe
  const percentile = calculatePercentile(score, universeScores)

  // Distribute labels based on percentiles (not fixed scores)
  // This ensures a visible range even if all scores cluster
  if (percentile >= 80) return 'Attractive'      // Top 20%
  if (percentile >= 55) return 'Promising'       // 55-80th percentile
  if (percentile >= 35) return 'Neutral'         // 35-55th percentile
  if (percentile >= 15) return 'Caution'         // 15-35th percentile
  return 'Avoid'                                  // Bottom 15%
}

/**
 * Calculate percentile rank of a score within a distribution
 *
 * @param {number} score - Target score
 * @param {Array} distribution - Array of all scores
 * @returns {number} Percentile (0-100)
 */
function calculatePercentile(score, distribution) {
  const validScores = distribution.filter(s => s != null && !isNaN(s))
  if (validScores.length === 0) return 50

  const belowCount = validScores.filter(s => s < score).length
  return (belowCount / validScores.length) * 100
}

/**
 * Fallback to fixed cutoffs when universe data unavailable
 * More generous than old system to reduce "Promising" clustering
 */
function calculateLabelFixed(score) {
  if (score >= 85) return 'Attractive'
  if (score >= 70) return 'Promising'
  if (score >= 50) return 'Neutral'
  if (score >= 30) return 'Caution'
  return 'Avoid'
}

/**
 * Get stance description for UI display
 */
export function getStanceDescription(label) {
  const descriptions = {
    'Attractive': 'Strong fundamentals, favorable technicals, positive sentiment',
    'Promising': 'Good fundamentals with room for improvement',
    'Neutral': 'Mixed signals, further research recommended',
    'Caution': 'Weak fundamentals or concerning signals',
    'Avoid': 'Poor fundamentals, negative technicals, or insufficient data'
  }
  return descriptions[label] || descriptions['Neutral']
}

/**
 * Get label color for UI (maps to existing tier classes)
 */
export function getLabelClass(label) {
  const classMap = {
    'Attractive': 'attractive',
    'Promising': 'promising',
    'Neutral': 'neutral',
    'Caution': 'caution',
    'Avoid': 'cool'  // Uses existing "cool" tier styling
  }
  return classMap[label] || 'neutral'
}

/**
 * Analyze label distribution in current universe
 * Returns counts and percentages for debugging/validation
 */
export function analyzeLabelDistribution(stocks) {
  const distribution = {
    'Attractive': 0,
    'Promising': 0,
    'Neutral': 0,
    'Caution': 0,
    'Avoid': 0
  }

  stocks.forEach(stock => {
    const label = stock.stance || 'Neutral'
    if (distribution[label] !== undefined) {
      distribution[label]++
    }
  })

  const total = stocks.length
  const percentages = {}
  Object.keys(distribution).forEach(label => {
    percentages[label] = total > 0
      ? ((distribution[label] / total) * 100).toFixed(1) + '%'
      : '0%'
  })

  return {
    counts: distribution,
    percentages,
    total,
    // Flag if distribution is degenerate (>60% in one bucket)
    isDegenerate: Object.values(distribution).some(count => count > total * 0.6)
  }
}

/**
 * Recalculate labels for entire universe
 * Call this when pipeline runs or scores update
 */
export function recalculateLabels(stocks) {
  if (!stocks || stocks.length === 0) return stocks

  // Extract all valid scores
  const allScores = stocks
    .map(s => s.score)
    .filter(score => score != null && !isNaN(score) && score > 0)

  // Recalculate each stock's label
  return stocks.map(stock => ({
    ...stock,
    stance: calculateLabel(stock.score, allScores),
    stanceDescription: getStanceDescription(calculateLabel(stock.score, allScores))
  }))
}
