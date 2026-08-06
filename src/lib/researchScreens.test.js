import { describe, expect, it } from 'vitest'
import { bullBearScore } from './bullBearScore'
import {
  activeThemes, rankFastGrowth, rankGrowingEtfs, rankMomentum, rankReversal, rankThemeExposure, rankValueTurnarounds,
} from './researchScreens'

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
  it('ranks ETFs against each other by overall score, best first, no pass/fail bar', () => {
    const laggard = row('BND', { scores: { overall: 34.1 } })
    const leader = row('SMH', { scores: { overall: 77.9 } })
    const middling = row('VTI', { scores: { overall: 55.2 } })

    expect(rankGrowingEtfs([laggard, leader, middling]).map((item) => item.ticker))
      .toEqual(['SMH', 'VTI', 'BND'])
  })

  it('skips ETFs without a computed overall score', () => {
    const scored = row('QQQ', { scores: { overall: 60 } })
    const unscored = row('IBIT', { scores: {} })

    expect(rankGrowingEtfs([unscored, scored]).map((item) => item.ticker)).toEqual(['QQQ'])
  })
})

describe('momentum screen uses the rebuilt technical fields', () => {
  it('prefers 12-1 momentum over the retired trend field', () => {
    const base = row('X').technical_detail
    const strongMomentum = row('MOM', {
      technical_detail: { ...base, return_5d: 3, trend: 10, momentum_12_1: 95 },
    })
    const weakMomentum = row('LAG', {
      technical_detail: { ...base, return_5d: 3, trend: 95, momentum_12_1: 10 },
    })
    expect(rankMomentum([weakMomentum, strongMomentum]).map((item) => item.ticker))
      .toEqual(['MOM', 'LAG'])
  })

  it('still ranks snapshots that predate the rebuild', () => {
    const legacy = row('OLD', {
      technical_detail: { return_20d: 8, return_5d: 2, trend: 80, risk: 70 },
    })
    expect(rankMomentum([legacy]).map((item) => item.ticker)).toEqual(['OLD'])
  })
})

describe('short-term reversal screen', () => {
  const reversalRow = (ticker, overrides = {}) => row(ticker, {
    technical_detail: { return_20d: -8, return_5d: 3, drawdown_60d: -15 },
    ...overrides,
  })

  it('requires a medium-term pullback that has just turned up this week', () => {
    const bouncing = reversalRow('BOUNCE')
    const stillFalling = reversalRow('DOWN', { technical_detail: { return_20d: -8, return_5d: -1, drawdown_60d: -15 } })
    const noPullback = reversalRow('UP', { technical_detail: { return_20d: 8, return_5d: 3, drawdown_60d: -2 } })

    expect(rankReversal([bouncing, stillFalling, noPullback]).map((item) => item.ticker))
      .toEqual(['BOUNCE'])
  })

  it('excludes a bounce with weak fundamentals rather than call it a reversal candidate', () => {
    const weak = reversalRow('WEAK', { components: { fundamentals: 30, market_behavior: 40, news_sentiment: 50 } })
    const solid = reversalRow('SOLID')
    expect(rankReversal([weak, solid]).map((item) => item.ticker)).toEqual(['SOLID'])
  })

  it('ranks a deeper pullback with a stronger bounce higher', () => {
    const sharperBounce = reversalRow('SHARP', { technical_detail: { return_20d: -12, return_5d: 6, drawdown_60d: -20 } })
    const mildBounce = reversalRow('MILD', { technical_detail: { return_20d: -4, return_5d: 1, drawdown_60d: -6 } })
    expect(rankReversal([mildBounce, sharperBounce]).map((item) => item.ticker))
      .toEqual(['SHARP', 'MILD'])
  })
})

describe('fast growth / breakout screen', () => {
  const breakoutRow = (ticker, overrides = {}) => row(ticker, {
    technical_detail: { return_20d: 10, return_5d: 8, volume_ratio_60d: 1.3 },
    ...overrides,
  })

  it('requires a meaningful weekly pop that outpaces the pace set earlier in the month', () => {
    // SNDK-style: nearly flat for three weeks, then +8% in the most recent week.
    const breakout = breakoutRow('BREAK', { technical_detail: { return_20d: 9, return_5d: 8, volume_ratio_60d: 1.3 } })
    // EPAM-style: up a lot for the month, but decelerating - the pop already happened earlier.
    const grinding = breakoutRow('GRIND', { technical_detail: { return_20d: 28, return_5d: 3, volume_ratio_60d: 1.1 } })
    const flat = breakoutRow('FLAT', { technical_detail: { return_20d: 1, return_5d: 1, volume_ratio_60d: 1 } })

    expect(rankFastGrowth([grinding, flat, breakout]).map((item) => item.ticker)).toEqual(['BREAK'])
  })

  it('excludes a weekly pop that is still net negative for the month', () => {
    const stillDown = breakoutRow('DOWN', { technical_detail: { return_20d: -5, return_5d: 3, volume_ratio_60d: 1 } })
    expect(rankFastGrowth([stillDown])).toEqual([])
  })

  it('ranks the sharpest, most volume-confirmed acceleration first', () => {
    const sharper = breakoutRow('SHARP', { technical_detail: { return_20d: 12, return_5d: 12, volume_ratio_60d: 1.6 } })
    const milder = breakoutRow('MILD', { technical_detail: { return_20d: 8, return_5d: 6, volume_ratio_60d: 1.1 } })
    expect(rankFastGrowth([milder, sharper]).map((item) => item.ticker)).toEqual(['SHARP', 'MILD'])
  })

  it('tolerates missing volume data by treating it as neutral', () => {
    const noVolume = breakoutRow('NOVOL', { technical_detail: { return_20d: 9, return_5d: 8, volume_ratio_60d: undefined } })
    expect(rankFastGrowth([noVolume]).map((item) => item.ticker)).toEqual(['NOVOL'])
  })
})

describe('theme exposure screen', () => {
  const themeRow = (ticker, overrides = {}) => ({
    ticker,
    name: `${ticker} Inc`,
    theme_exposure_score: 80,
    fundamental_score: 70,
    opportunity_score: 70,
    eligible: true,
    ...overrides,
  })

  it('ranks by opportunity, not by raw exposure', () => {
    // The purest-play name is not automatically the best idea; exposure has to come with
    // a business that holds up and a price that has not already run.
    const purestButExpensive = themeRow('PURE', {
      theme_exposure_score: 98, opportunity_score: 55,
    })
    const balanced = themeRow('BAL', { theme_exposure_score: 72, opportunity_score: 85 })
    expect(rankThemeExposure({ rows: [purestButExpensive, balanced] })
      .map((item) => item.ticker)).toEqual(['BAL', 'PURE'])
  })

  it('sorts guardrail-excluded names below eligible ones without hiding them', () => {
    const euphoric = themeRow('HYPE', {
      eligible: false, opportunity_score: 99, theme_exposure_score: 99,
    })
    const eligible = themeRow('OK', { opportunity_score: 40 })
    const ranked = rankThemeExposure({ rows: [euphoric, eligible] })
    expect(ranked.map((item) => item.ticker)).toEqual(['OK', 'HYPE'])
    expect(ranked).toHaveLength(2)
  })

  it('skips rows without a computed exposure score', () => {
    const scored = themeRow('AAA')
    const unscored = themeRow('BBB', { theme_exposure_score: null })
    expect(rankThemeExposure({ rows: [unscored, scored] }).map((item) => item.ticker))
      .toEqual(['AAA'])
  })

  it('handles a missing or empty theme screen', () => {
    expect(rankThemeExposure(undefined)).toEqual([])
    expect(rankThemeExposure({ rows: [] })).toEqual([])
  })

  it('lists only themes that actually produced scored rows', () => {
    const screen = {
      themes: [
        { id: 'live', rows: [themeRow('AAA')] },
        { id: 'no_signals', rows: [] },
      ],
    }
    expect(activeThemes(screen).map((theme) => theme.id)).toEqual(['live'])
    expect(activeThemes(undefined)).toEqual([])
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
