const OUTLOOK_BANDS = [
  { minimum: 80, label: 'Very Bullish', key: 'very-bullish', rank: 6 },
  { minimum: 70, label: 'Bullish', key: 'bullish', rank: 5 },
  { minimum: 60, label: 'Leaning Bullish', key: 'leaning-bullish', rank: 4 },
  { minimum: 50, label: 'Neutral', key: 'neutral', rank: 3 },
  { minimum: 40, label: 'Leaning Bearish', key: 'leaning-bearish', rank: 2 },
  { minimum: 30, label: 'Bearish', key: 'bearish', rank: 1 },
  { minimum: 0, label: 'Very Bearish', key: 'very-bearish', rank: 0 },
]

export function getOutlook(score) {
  if (!Number.isFinite(score)) return null
  return OUTLOOK_BANDS.find((band) => score >= band.minimum) || OUTLOOK_BANDS.at(-1)
}

