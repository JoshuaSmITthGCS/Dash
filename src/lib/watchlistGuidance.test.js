import { describe, expect, it } from 'vitest'
import { watchlistGuidance } from './watchlistGuidance'

const coveredStock = {
  price: 100,
  score: 72,
  confidence: 0.8,
  components: { fundamentals: 80, market_behavior: 70, news_sentiment: 60 },
  sentiment_detail: { coverage: 1 },
  technical_detail: { return_20d: 8, risk: 70 },
  recommendation: { action: 'HOLD' },
  analyst_consensus_target: 125,
  analyst_count: 18,
}

describe('watchlist guidance', () => {
  it('shows a buy setup with a capped illustrative position', () => {
    expect(watchlistGuidance(coveredStock, 10_000, 5)).toMatchObject({
      verdict: 'BUY SETUP',
      target: 125,
      targetUpside: 25,
      allocation: 500,
      shares: 5,
    })
  })

  it('shows no allocation when evidence says not to buy yet', () => {
    expect(watchlistGuidance({
      ...coveredStock,
      technical_detail: { ...coveredStock.technical_detail, return_20d: -8 },
    }, 10_000, 5)).toMatchObject({
      verdict: "DON'T BUY YET",
      allocation: 0,
      shares: 0,
    })
  })

  it('does not invent a Yahoo target when none is published', () => {
    expect(watchlistGuidance({
      ...coveredStock,
      analyst_consensus_target: null,
    })).toMatchObject({ target: null, targetUpside: null })
  })
})

