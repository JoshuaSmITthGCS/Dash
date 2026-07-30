/**
 * News Sentiment Categorization Engine
 *
 * Implements detailed sentiment analysis with:
 * - Polarity: positive, neutral, negative
 * - Intensity: mild, moderate, severe
 * - Persistence: one-off, recurring, persistent
 * - Source Quality: low, medium, high
 * - Materiality: low, medium, high
 * - Category: earnings, product, regulation, legal, labor, execution,
 *   accounting/fraud, consumer backlash, macro, downgrade, cyber, recall
 *
 * Impact scaling: mild + low-materiality = minimal impact
 *                 persistent + high-materiality + high-quality = significant impact
 */

// News categories with impact weights
export const NEWS_CATEGORIES = {
  'earnings': { weight: 0.9, description: 'Earnings reports, guidance, forecasts' },
  'product': { weight: 0.8, description: 'Product launches, demand signals, market share' },
  'regulation': { weight: 0.7, description: 'Regulatory changes, compliance issues' },
  'legal': { weight: 0.8, description: 'Lawsuits, legal settlements, investigations' },
  'labor': { weight: 0.6, description: 'Union actions, strikes, workforce issues' },
  'execution': { weight: 0.7, description: 'Management changes, strategy shifts, M&A' },
  'accounting': { weight: 0.9, description: 'Accounting irregularities, restatements, fraud' },
  'consumer': { weight: 0.7, description: 'Consumer backlash, boycotts, reputation damage' },
  'macro': { weight: 0.5, description: 'Macro conditions, sector trends, economy-wide' },
  'downgrade': { weight: 0.6, description: 'Analyst downgrades, price target cuts' },
  'cyber': { weight: 0.7, description: 'Cybersecurity breaches, data leaks' },
  'recall': { weight: 0.8, description: 'Product recalls, safety issues' },
  'other': { weight: 0.4, description: 'Uncategorized news' }
}

/**
 * Categorize news article based on content/title
 *
 * @param {Object} article - News article object
 * @returns {string} Category key
 */
export function categorizeNews(article) {
  const text = `${article.title || ''} ${article.summary || ''}`.toLowerCase()

  // Category keywords (ordered by priority - more specific first)
  const categoryPatterns = {
    'accounting': ['fraud', 'restatement', 'accounting', 'gaap', 'sec investigation', 'financial irregularit'],
    'earnings': ['earnings', 'revenue', 'profit', 'eps', 'guidance', 'beat', 'miss', 'quarter'],
    'recall': ['recall', 'safety', 'defect', 'contamination'],
    'cyber': ['breach', 'hack', 'cyberattack', 'data leak', 'ransomware'],
    'legal': ['lawsuit', 'litigation', 'settlement', 'court', 'sue', 'legal action'],
    'regulation': ['regulation', 'regulatory', 'compliance', 'fda', 'approval', 'antitrust'],
    'downgrade': ['downgrade', 'rating cut', 'price target', 'analyst', 'bearish'],
    'product': ['product', 'launch', 'demand', 'sales', 'market share', 'new release'],
    'labor': ['strike', 'union', 'labor', 'workforce', 'layoff', 'hiring'],
    'execution': ['ceo', 'cfo', 'management', 'merger', 'acquisition', 'strategy', 'restructur'],
    'consumer': ['boycott', 'backlash', 'reputation', 'brand damage', 'social media'],
    'macro': ['economy', 'recession', 'inflation', 'interest rate', 'fed', 'sector']
  }

  // Find first matching category
  for (const [category, patterns] of Object.entries(categoryPatterns)) {
    if (patterns.some(pattern => text.includes(pattern))) {
      return category
    }
  }

  return 'other'
}

/**
 * Assess sentiment polarity (-1 to +1)
 *
 * @param {Object} article - News article with sentiment scores
 * @returns {Object} { polarity: 'positive'|'neutral'|'negative', score: number }
 */
export function assessPolarity(article) {
  // Use existing sentiment score if available
  const score = article.overall_sentiment_score ?? article.sentiment ?? 0

  if (score > 0.15) {
    return { polarity: 'positive', score }
  } else if (score < -0.15) {
    return { polarity: 'negative', score }
  } else {
    return { polarity: 'neutral', score }
  }
}

/**
 * Assess intensity based on sentiment magnitude and language
 *
 * @param {Object} article - News article
 * @returns {'mild'|'moderate'|'severe'}
 */
export function assessIntensity(article) {
  const score = Math.abs(article.overall_sentiment_score ?? article.sentiment ?? 0)
  const text = `${article.title || ''} ${article.summary || ''}`.toLowerCase()

  // Severe keywords
  const severeWords = ['crisis', 'collapse', 'plunge', 'surge', 'soar', 'crash', 'scandal']
  const hasSevereLanguage = severeWords.some(word => text.includes(word))

  if (score > 0.5 || hasSevereLanguage) {
    return 'severe'
  } else if (score > 0.25) {
    return 'moderate'
  } else {
    return 'mild'
  }
}

/**
 * Assess persistence by analyzing multiple articles about same stock
 *
 * @param {Array} articles - All articles for this stock (recent)
 * @param {Object} currentArticle - Article being assessed
 * @returns {'one-off'|'recurring'|'persistent'}
 */
export function assessPersistence(articles, currentArticle) {
  if (!articles || articles.length <= 1) {
    return 'one-off'
  }

  const category = categorizeNews(currentArticle)
  const polarity = assessPolarity(currentArticle).polarity

  // Count articles with same category and polarity in last 7 days
  const weekAgo = Date.now() - (7 * 24 * 60 * 60 * 1000)
  const relatedArticles = articles.filter(article => {
    if (!article.time_published) return false
    const articleDate = new Date(article.time_published).getTime()
    if (articleDate < weekAgo) return false

    return categorizeNews(article) === category &&
           assessPolarity(article).polarity === polarity
  })

  if (relatedArticles.length >= 5) {
    return 'persistent'  // 5+ similar articles in a week
  } else if (relatedArticles.length >= 2) {
    return 'recurring'   // 2-4 similar articles
  } else {
    return 'one-off'     // Single article
  }
}

/**
 * Assess source quality based on outlet reputation
 *
 * @param {Object} article - News article
 * @returns {'low'|'medium'|'high'}
 */
export function assessSourceQuality(article) {
  const source = (article.source || '').toLowerCase()

  const highQualitySources = [
    'wall street journal', 'wsj', 'financial times', 'ft',
    'bloomberg', 'reuters', 'associated press', 'ap',
    'new york times', 'nyt', 'washington post', 'economist'
  ]

  const mediumQualitySources = [
    'cnbc', 'marketwatch', 'seeking alpha', 'barron', 'forbes',
    'business insider', 'yahoo finance', 'benzinga'
  ]

  if (highQualitySources.some(src => source.includes(src))) {
    return 'high'
  } else if (mediumQualitySources.some(src => source.includes(src))) {
    return 'medium'
  } else {
    return 'low'
  }
}

/**
 * Assess materiality based on category and content
 *
 * @param {Object} article - News article
 * @param {string} category - News category
 * @returns {'low'|'medium'|'high'}
 */
export function assessMateriality(article, category) {
  const text = `${article.title || ''} ${article.summary || ''}`.toLowerCase()

  // High materiality indicators
  const highMaterialityKeywords = [
    'guidance', 'revenue', 'profit', 'earnings', 'fraud', 'investigation',
    'recall', 'breach', 'lawsuit', 'settlement', 'ceo', 'strategy'
  ]

  // Low materiality indicators
  const lowMaterialityKeywords = [
    'minor', 'small', 'slight', 'limited', 'modest'
  ]

  const hasHighKeywords = highMaterialityKeywords.some(word => text.includes(word))
  const hasLowKeywords = lowMaterialityKeywords.some(word => text.includes(word))

  // Category-based materiality (some categories inherently more material)
  const highMaterialityCategories = ['earnings', 'accounting', 'legal', 'recall']
  const lowMaterialityCategories = ['macro', 'other']

  if (hasHighKeywords || highMaterialityCategories.includes(category)) {
    return 'high'
  } else if (hasLowKeywords || lowMaterialityCategories.includes(category)) {
    return 'low'
  } else {
    return 'medium'
  }
}

/**
 * Calculate sentiment impact on score
 *
 * @param {Object} analysis - Full sentiment analysis
 * @returns {number} Impact multiplier (0-1)
 */
export function calculateSentimentImpact(analysis) {
  const {
    polarity,
    intensity,
    persistence,
    sourceQuality,
    materiality
  } = analysis

  // Base impact from polarity and intensity
  let impact
  if (polarity === 'negative') {
    impact = intensity === 'severe' ? 0.6 : intensity === 'moderate' ? 0.4 : 0.2
  } else if (polarity === 'positive') {
    impact = intensity === 'severe' ? 0.3 : intensity === 'moderate' ? 0.2 : 0.1
  } else {
    impact = 0.05 // Neutral has minimal impact
  }

  // Persistence multiplier
  const persistenceMultiplier = {
    'persistent': 1.5,
    'recurring': 1.2,
    'one-off': 1.0
  }[persistence]

  // Source quality multiplier
  const sourceMultiplier = {
    'high': 1.3,
    'medium': 1.1,
    'low': 0.8
  }[sourceQuality]

  // Materiality multiplier
  const materialityMultiplier = {
    'high': 1.4,
    'medium': 1.0,
    'low': 0.6
  }[materiality]

  // Combined impact
  const totalImpact = impact * persistenceMultiplier * sourceMultiplier * materialityMultiplier

  // Negative news has asymmetric impact (hurts more than positive helps)
  const finalImpact = polarity === 'negative'
    ? Math.min(1.0, totalImpact * 1.2)
    : Math.min(0.6, totalImpact)

  return finalImpact
}

/**
 * Analyze news article with full categorization
 *
 * @param {Object} article - News article
 * @param {Array} allArticles - All articles for persistence analysis
 * @returns {Object} Full analysis
 */
export function analyzeArticle(article, allArticles = []) {
  const category = categorizeNews(article)
  const { polarity, score } = assessPolarity(article)
  const intensity = assessIntensity(article)
  const persistence = assessPersistence(allArticles, article)
  const sourceQuality = assessSourceQuality(article)
  const materiality = assessMateriality(article, category)

  const impact = calculateSentimentImpact({
    polarity,
    intensity,
    persistence,
    sourceQuality,
    materiality,
    category
  })

  return {
    category,
    polarity,
    polarityScore: score,
    intensity,
    persistence,
    sourceQuality,
    materiality,
    impact,
    categoryWeight: NEWS_CATEGORIES[category]?.weight || 0.4,
    description: NEWS_CATEGORIES[category]?.description || 'Uncategorized',
    timestamp: article.time_published || article.timestamp
  }
}

/**
 * Aggregate sentiment for all articles about a stock
 *
 * @param {Array} articles - All news articles for the stock
 * @returns {Object} Aggregated sentiment analysis
 */
export function aggregateSentiment(articles) {
  if (!articles || articles.length === 0) {
    return {
      overallImpact: 0,
      avgPolarity: 0,
      dominantCategory: 'none',
      articles: [],
      breakdown: {}
    }
  }

  const analyses = articles.map(article => analyzeArticle(article, articles))

  // Calculate weighted average impact
  const totalImpact = analyses.reduce((sum, a) => sum + a.impact, 0)
  const overallImpact = totalImpact / analyses.length

  // Calculate average polarity
  const avgPolarity = analyses.reduce((sum, a) => sum + a.polarityScore, 0) / analyses.length

  // Find dominant category
  const categoryCounts = {}
  analyses.forEach(a => {
    categoryCounts[a.category] = (categoryCounts[a.category] || 0) + 1
  })
  const dominantCategory = Object.keys(categoryCounts).reduce((a, b) =>
    categoryCounts[a] > categoryCounts[b] ? a : b
  )

  // Breakdown by category
  const breakdown = {}
  analyses.forEach(a => {
    if (!breakdown[a.category]) {
      breakdown[a.category] = {
        count: 0,
        avgImpact: 0,
        avgPolarity: 0
      }
    }
    breakdown[a.category].count++
    breakdown[a.category].avgImpact += a.impact
    breakdown[a.category].avgPolarity += a.polarityScore
  })

  // Average the breakdowns
  Object.keys(breakdown).forEach(cat => {
    breakdown[cat].avgImpact /= breakdown[cat].count
    breakdown[cat].avgPolarity /= breakdown[cat].count
  })

  return {
    overallImpact,
    avgPolarity,
    dominantCategory,
    dominantCategoryDescription: NEWS_CATEGORIES[dominantCategory]?.description,
    articles: analyses,
    breakdown,
    totalArticles: articles.length
  }
}

/**
 * Generate audit log entry for sentiment penalty
 *
 * @param {Object} sentimentData - Aggregated sentiment
 * @returns {string} Human-readable audit log
 */
export function generateSentimentAuditLog(sentimentData) {
  const { dominantCategory, overallImpact, avgPolarity, totalArticles } = sentimentData

  const impactText = overallImpact > 0.5 ? 'significant' :
                     overallImpact > 0.25 ? 'moderate' :
                     overallImpact > 0.1 ? 'minor' : 'minimal'

  const polarityText = avgPolarity > 0.15 ? 'positive' :
                       avgPolarity < -0.15 ? 'negative' : 'neutral'

  return `${totalArticles} articles analyzed. ` +
         `Dominant category: ${dominantCategory} (${NEWS_CATEGORIES[dominantCategory]?.description}). ` +
         `Overall ${polarityText} sentiment with ${impactText} impact (${(overallImpact * 100).toFixed(1)}% score adjustment).`
}
