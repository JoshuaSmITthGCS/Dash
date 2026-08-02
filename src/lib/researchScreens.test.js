import { describe, expect, it } from 'vitest'
import { bullBearScore } from './bullBearScore'
import { rankGrowingEtfs, rankMomentum, rankValueTurnarounds } from './researchScreens'

const row = (ticker, overrides = {}) => ({
  ticker,
  components: { fundamentals: 80, market_behavior: 70, news_sentiment: 50 },
  fundamental_categories: { valuation: 85 },
  technical_detail: {
    return_20d: 12,
    relative_strength_20d: 5,
    trend: 75,
    relative_strength: 65,
    volume_confirmation: 60,
    risk: 70,
  },
  history: { closes: Array.from({ length: 53 }, (_, index) => 100 + index * 0.2) },
  ...overrides,
})

describe('value turnaround screen', () => {
  it('requires value, fundamentals, proximity to the low, and a positive week', () => {
    const eligible = row('VALUE', {
      history: { closes: [...Array(51).fill(100), 101, 104] },
    })
    const expensive = row('RICH', {
      fundamental_categories: { valuation: 40 },
    })

    expect(rankValueTurnarounds([expensive, eligible]).map((item) => item.ticker))
      .toEqual(['VALUE'])
  })
})

describe('momentum screen', () => {
  it('requires positive weekly and monthly performance', () => {
    const rising = row('UP', { technical_detail: { ...row('X').technical_detail, return_5d: 4 } })
    const falling = row('DOWN', { technical_detail: { ...row('X').technical_detail, return_5d: -2 } })

    expect(rankMomentum([falling, rising]).map((item) => item.ticker)).toEqual(['UP'])
  })
})

describe('growing ETF screen', () => {
  it('ranks ETFs against each other by growth score, best first, no pass/fail bar', () => {
    const laggard = row('BND', { growth_score: -1.1 })
    const leader = row('SMH', { growth_score: 11.3 })
    const middling = row('VTI', { growth_score: 2.4 })

    expect(rankGrowingEtfs([laggard, leader, middling]).map((item) => item.ticker))
      .toEqual(['SMH', 'VTI', 'BND'])
  })

  it('skips ETFs without a computed growth score', () => {
    const scored = row('QQQ', { growth_score: 5 })
    const unscored = row('IBIT', { growth_score: undefined })

    expect(rankGrowingEtfs([unscored, scored]).map((item) => item.ticker)).toEqual(['QQQ'])
  })
})

describe('bull/bear thesis score', () => {
  it('maps the weighted evidence onto the zero to ten scale', () => {
    expect(bullBearScore({
      components: { fundamentals: 90, market_behavior: 80, news_sentiment: 70 },
      sentiment_detail: { coverage: 1 },
      technical_detail: { risk: 60 },
    })).toMatchObject({ score: 8, composite: 80, coverage: 100 })
  })

  it('does not count placeholder sentiment as real evidence', () => {
    expect(bullBearScore({
      components: { fundamentals: 90, market_behavior: 80, news_sentiment: 50 },
      sentiment_detail: { coverage: 0 },
      technical_detail: { risk: 60 },
    })).toMatchObject({ score: 8.3, composite: 82.5, coverage: 80 })
  })

  it('returns no score when evidence is unavailable', () => {
    expect(bullBearScore({})).toBeNull()
  })
})
