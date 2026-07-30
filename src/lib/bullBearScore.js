const FACTORS = [
  ['Fundamentals', 0.4, (stock) => stock.components?.fundamentals],
  ['Price behavior', 0.3, (stock) => stock.components?.market_behavior],
  [
    'News sentiment',
    0.2,
    (stock) => stock.components?.news_sentiment,
    (stock) => (stock.sentiment_detail?.coverage || 0) > 0,
  ],
  ['Risk quality', 0.1, (stock) => stock.technical_detail?.risk],
]

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value))

export function bullBearScore(stock) {
  const available = FACTORS
    .map(([label, weight, read, isAvailable]) => ({
      label,
      weight,
      value: read(stock),
      available: !isAvailable || isAvailable(stock),
    }))
    .filter((factor) => factor.available && Number.isFinite(factor.value))

  if (!available.length) return null
  const availableWeight = available.reduce((sum, factor) => sum + factor.weight, 0)
  const composite = available.reduce(
    (sum, factor) => sum + factor.value * factor.weight,
    0,
  ) / availableWeight

  return {
    score: clamp(Math.round((composite - 50) / 10), -5, 5),
    composite: Math.round(composite * 10) / 10,
    coverage: Math.round((availableWeight / FACTORS.reduce((sum, factor) => sum + factor[1], 0)) * 100),
    factors: available,
  }
}
