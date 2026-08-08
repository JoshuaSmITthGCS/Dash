import { describe, expect, it } from 'vitest'
import { bullBearScore } from './bullBearScore'
import {
  activeThemes, rankAnalystConviction, rankBreakoutInProgress, rankCatalyst, rankEmergingGrowth,
  rankGrowingEtfs, rankMomentum, rankReversal, rankThemeExposure, rankValueTurnarounds,
  STRATEGY_LENSES, isStrategyLens, lensCoverage, lensReason, rankByLens, rankTailwind,
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

  it('flags but does not drop a turnaround whose recent earnings surprise was sharply negative', () => {
    const cleanValue = row('CLEAN', {
      history: { closes: [...Array(51).fill(100), 101, 104] },
    })
    const badEarnings = row('BADEPS', {
      history: { closes: [...Array(51).fill(100), 101, 104] },
      earnings_surprise: -15,
    })
    const results = rankValueTurnarounds([badEarnings, cleanValue])
    expect(results.map((item) => item.ticker)).toEqual(['CLEAN', 'BADEPS'])
    expect(results.find((item) => item.ticker === 'CLEAN').screen.corroborated).toBe(true)
    const flagged = results.find((item) => item.ticker === 'BADEPS')
    expect(flagged.screen.corroborated).toBe(false)
    expect(flagged.screen.corroborationGaps[0]).toMatch(/deteriorating business/)
  })
})

describe('momentum screen', () => {
  it('requires positive weekly and monthly performance', () => {
    const rising = row('UP', { technical_detail: { ...row('X').technical_detail, return_5d: 4 } })
    const falling = row('DOWN', { technical_detail: { ...row('X').technical_detail, return_5d: -2 } })

    expect(rankMomentum([falling, rising]).map((item) => item.ticker)).toEqual(['UP'])
  })

  it('flags but does not drop a pop that sits inside a longer 60/252-day downtrend', () => {
    const base = row('X').technical_detail
    const broadBased = row('BROAD', { technical_detail: { ...base, return_5d: 3, return_60d: 5, return_252d: 10 } })
    const oneWeekPop = row('POP', { technical_detail: { ...base, return_5d: 3, return_60d: -20, return_252d: -30 } })
    const results = rankMomentum([oneWeekPop, broadBased])
    expect(results.map((item) => item.ticker)).toEqual(['BROAD', 'POP'])
    expect(results.find((item) => item.ticker === 'BROAD').screen.corroborated).toBe(true)
    const flagged = results.find((item) => item.ticker === 'POP')
    expect(flagged.screen.corroborated).toBe(false)
    expect(flagged.screen.corroborationGaps[0]).toMatch(/longer 60\/252-day downtrend/)
  })

  it('does not penalize missing longer-horizon data, only an actual opposing trend', () => {
    const base = row('X').technical_detail
    const noLongerData = row('NEW', { technical_detail: { ...base, return_5d: 3 } })
    const [result] = rankMomentum([noLongerData])
    expect(result.screen.corroborated).toBe(true)
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

  it('flags but does not drop a bounce that followed a sharply negative earnings surprise', () => {
    const cleanBounce = reversalRow('CLEAN')
    const earningsDriven = reversalRow('EPS', { earnings_surprise: -12 })
    const results = rankReversal([earningsDriven, cleanBounce])
    expect(results.map((item) => item.ticker)).toEqual(['CLEAN', 'EPS'])
    expect(results.find((item) => item.ticker === 'CLEAN').screen.corroborated).toBe(true)
    const flagged = results.find((item) => item.ticker === 'EPS')
    expect(flagged.screen.corroborated).toBe(false)
    expect(flagged.screen.corroborationGaps[0]).toMatch(/earnings surprise/)
  })

  it('elevated short interest offers an alternate, squeeze-consistent reason for the bounce', () => {
    const squeeze = reversalRow('SQZ', { earnings_surprise: -12, short_percent_of_float: 0.08 })
    const [result] = rankReversal([squeeze])
    expect(result.screen.corroborated).toBe(true)
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

    expect(rankBreakoutInProgress([grinding, flat, breakout]).map((item) => item.ticker)).toEqual(['BREAK'])
  })

  it('excludes a weekly pop that is still net negative for the month', () => {
    const stillDown = breakoutRow('DOWN', { technical_detail: { return_20d: -5, return_5d: 3, volume_ratio_60d: 1 } })
    expect(rankBreakoutInProgress([stillDown])).toEqual([])
  })

  it('ranks the sharpest, most volume-confirmed acceleration first', () => {
    const sharper = breakoutRow('SHARP', { technical_detail: { return_20d: 12, return_5d: 12, volume_ratio_60d: 1.6 } })
    const milder = breakoutRow('MILD', { technical_detail: { return_20d: 8, return_5d: 6, volume_ratio_60d: 1.1 } })
    expect(rankBreakoutInProgress([milder, sharper]).map((item) => item.ticker)).toEqual(['SHARP', 'MILD'])
  })

  it('tolerates missing volume data by treating it as neutral', () => {
    const noVolume = breakoutRow('NOVOL', { technical_detail: { return_20d: 9, return_5d: 8, volume_ratio_60d: undefined } })
    expect(rankBreakoutInProgress([noVolume]).map((item) => item.ticker)).toEqual(['NOVOL'])
  })
})

describe('emerging growth screen (prospective, unvalidated)', () => {
  const emergingRow = (ticker, overrides = {}) => row(ticker, {
    technical_detail: { return_5d: 1, relative_strength_20d: 3 },
    fundamental_detail: { revenue_growth: 0.15, operating_margin_trend: 0.02 },
    history: { closes: Array.from({ length: 80 }, (_, index) => 100 + index * 0.1) },
    ...overrides,
  })

  it('qualifies a name with real growth and early strength that has not yet popped', () => {
    const candidate = emergingRow('EARLY')
    expect(rankEmergingGrowth([candidate]).map((item) => item.ticker)).toEqual(['EARLY'])
  })

  it('every result is explicitly labeled prospective_unvalidated', () => {
    const candidate = emergingRow('EARLY')
    const [result] = rankEmergingGrowth([candidate])
    expect(result.research_status).toBe('prospective_unvalidated')
  })

  it('excludes anything the breakout screen would already catch, so the two screens do not overlap', () => {
    const alreadyBroken = emergingRow('BROKE', { technical_detail: { return_5d: 8, relative_strength_20d: 6 } })
    expect(rankEmergingGrowth([alreadyBroken])).toEqual([])
  })

  it('excludes names without a real, meaningful revenue growth rate', () => {
    const noGrowth = emergingRow('FLAT', { fundamental_detail: { revenue_growth: 0.01 } })
    const negativeGrowth = emergingRow('SHRINK', { fundamental_detail: { revenue_growth: -0.05 } })
    expect(rankEmergingGrowth([noGrowth, negativeGrowth])).toEqual([])
  })

  it('excludes names without positive early relative strength', () => {
    const weak = emergingRow('WEAK', { technical_detail: { return_5d: 1, relative_strength_20d: -2 } })
    expect(rankEmergingGrowth([weak])).toEqual([])
  })

  it('does not require estimate revision data to qualify or rank', () => {
    const withoutRevisions = emergingRow('NOREV')
    const [result] = rankEmergingGrowth([withoutRevisions])
    expect(result).toBeTruthy()
    expect(result.screen.revisionBreadth).toBeNull()
  })

  it('ranks stronger growth and strength higher', () => {
    const stronger = emergingRow('STRONG', {
      fundamental_detail: { revenue_growth: 0.30, operating_margin_trend: 0.05 },
      technical_detail: { return_5d: 1, relative_strength_20d: 8 },
    })
    const milder = emergingRow('MILD', {
      fundamental_detail: { revenue_growth: 0.08, operating_margin_trend: 0.0 },
      technical_detail: { return_5d: 1, relative_strength_20d: 1 },
    })
    expect(rankEmergingGrowth([milder, stronger]).map((item) => item.ticker)).toEqual(['STRONG', 'MILD'])
  })
})

describe('short-term catalyst screen', () => {
  const catalystRow = (ticker, overrides = {}) => row(ticker, {
    components: { fundamentals: 40, market_behavior: 60, news_sentiment: 50 },
    insider_activity: { available: false, points: 0 },
    technical_detail: { return_5d: 0 },
    ...overrides,
  })

  it('a weak long-term research score can still clear this screen on a real catalyst', () => {
    // The whole point: fundamentals are deliberately a small weight, not a gate.
    const buying = catalystRow('BUY', {
      components: { fundamentals: 35, market_behavior: 55, news_sentiment: 78 },
      insider_activity: { available: true, points: 4 },
      technical_detail: { return_5d: 3 },
    })
    expect(rankCatalyst([buying]).map((item) => item.ticker)).toEqual(['BUY'])
  })

  it('excludes a quiet stock with only neutral news and no insider activity', () => {
    const quiet = catalystRow('QUIET')
    expect(rankCatalyst([quiet])).toEqual([])
  })

  it('opportunistic insider selling is a catalyst too, and it ranks below buying', () => {
    const buying = catalystRow('BUY', {
      insider_activity: { available: true, points: 4 },
      technical_detail: { return_5d: 2 },
    })
    const selling = catalystRow('SELL', {
      insider_activity: { available: true, points: -3 },
      technical_detail: { return_5d: -1 },
    })
    expect(rankCatalyst([selling, buying]).map((item) => item.ticker)).toEqual(['BUY', 'SELL'])
  })

  it('fresh bullish news alone is enough of a catalyst without insider data', () => {
    const news = catalystRow('NEWS', {
      components: { fundamentals: 50, market_behavior: 50, news_sentiment: 85 },
      technical_detail: { return_5d: 2 },
    })
    expect(rankCatalyst([news]).map((item) => item.ticker)).toEqual(['NEWS'])
  })

  it('flags but does not drop insider buying from a single trader with no track record', () => {
    const soleTrader = catalystRow('SOLO', {
      insider_activity: { available: true, points: 4, buy_cluster: { insider_count: 1, pattern_confidence: 0.3 } },
      technical_detail: { return_5d: 3 },
    })
    const corroboratedCluster = catalystRow('CLUSTER', {
      insider_activity: { available: true, points: 4, buy_cluster: { insider_count: 3, pattern_confidence: 0.9 } },
      technical_detail: { return_5d: 3 },
    })
    const results = rankCatalyst([soleTrader, corroboratedCluster])
    expect(results.map((item) => item.ticker)).toEqual(['CLUSTER', 'SOLO'])
    expect(results.find((item) => item.ticker === 'CLUSTER').screen.corroborated).toBe(true)
    const flagged = results.find((item) => item.ticker === 'SOLO')
    expect(flagged.screen.corroborated).toBe(false)
    expect(flagged.screen.corroborationGaps[0]).toMatch(/single trader/)
  })

  it('flags but does not drop a catalyst resting on a single low-quality news source', () => {
    const thinNews = catalystRow('THIN', {
      components: { fundamentals: 50, market_behavior: 50, news_sentiment: 85 },
      technical_detail: { return_5d: 2 },
      sentiment_summary: { article_count: 1, best_source_quality_tier: 'aggregator_syndicated' },
    })
    const qualityNews = catalystRow('QUALITY', {
      components: { fundamentals: 50, market_behavior: 50, news_sentiment: 85 },
      technical_detail: { return_5d: 2 },
      sentiment_summary: { article_count: 1, best_source_quality_tier: 'established_press' },
    })
    const results = rankCatalyst([thinNews, qualityNews])
    expect(results.map((item) => item.ticker)).toEqual(['QUALITY', 'THIN'])
    const flagged = results.find((item) => item.ticker === 'THIN')
    expect(flagged.screen.corroborated).toBe(false)
    expect(flagged.screen.corroborationGaps[0]).toMatch(/low-quality source/)
  })

  it('two or more articles corroborates news even from aggregator-only sources', () => {
    const twoArticles = catalystRow('TWO', {
      components: { fundamentals: 50, market_behavior: 50, news_sentiment: 85 },
      technical_detail: { return_5d: 2 },
      sentiment_summary: { article_count: 2, best_source_quality_tier: 'aggregator_syndicated' },
    })
    const [result] = rankCatalyst([twoArticles])
    expect(result.screen.corroborated).toBe(true)
  })
})

describe('analyst conviction screen', () => {
  const convictionRow = (ticker, overrides = {}) => row(ticker, {
    analyst_count: 8,
    analyst_rating: 3,
    analyst_target_upside: 0,
    ...overrides,
  })

  it('requires at least three analysts, matching the backend expectations-modifier floor', () => {
    const thin = convictionRow('THIN', { analyst_count: 2, analyst_rating: 1.2, analyst_target_upside: 30 })
    expect(rankAnalystConviction([thin])).toEqual([])
  })

  it('ranks a bullish rating and strong consensus upside above a cautious, low-upside name', () => {
    const bullish = convictionRow('BULL', { analyst_rating: 1.4, analyst_target_upside: 25 })
    const cautious = convictionRow('BEAR', { analyst_rating: 4.2, analyst_target_upside: -8 })
    expect(rankAnalystConviction([cautious, bullish]).map((item) => item.ticker)).toEqual(['BULL', 'BEAR'])
  })

  it('a weak fundamentals score does not disqualify a name with strong analyst conviction', () => {
    const weakFundamentalsStrongConviction = convictionRow('WEAK', {
      components: { fundamentals: 25, market_behavior: 50, news_sentiment: 50 },
      analyst_rating: 1.3, analyst_target_upside: 22,
    })
    expect(rankAnalystConviction([weakFundamentalsStrongConviction]).map((item) => item.ticker))
      .toEqual(['WEAK'])
  })

  it('flags but does not drop a large consensus upside on a name already expensive for its sector', () => {
    const coherent = convictionRow('COHERENT', {
      analyst_rating: 1.5, analyst_target_upside: 20, sector_valuation_percentile: 40,
    })
    const staleTarget = convictionRow('STALE', {
      analyst_rating: 1.5, analyst_target_upside: 20, sector_valuation_percentile: 92,
    })
    const results = rankAnalystConviction([staleTarget, coherent])
    expect(results.map((item) => item.ticker)).toEqual(['COHERENT', 'STALE'])
    expect(results.find((item) => item.ticker === 'COHERENT').screen.corroborated).toBe(true)
    const flagged = results.find((item) => item.ticker === 'STALE')
    expect(flagged.screen.corroborated).toBe(false)
    expect(flagged.screen.corroborationGaps[0]).toMatch(/most expensive decile/)
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

describe('invariant: no stock screen ever includes an ETF', () => {
  // A fund holds no per-security fundamentals or technical_detail shaped for one company,
  // so it can never legitimately clear a stock screen. Every screen below must exclude
  // is_etf rows even if a caller passes a mixed array.
  const strongEtfShapedAsAStock = row('SPY_LIKE', {
    is_etf: true,
    components: { fundamentals: 99, market_behavior: 99, news_sentiment: 99 },
    fundamental_categories: { valuation: 99 },
    technical_detail: {
      return_5d: 10, return_20d: 20, relative_strength_20d: 10, trend: 99,
      relative_strength: 99, volume_confirmation: 99, risk: 99, drawdown_60d: -1,
      volume_ratio_60d: 2,
    },
    history: { closes: [...Array(51).fill(100), 105, 120] },
  })
  const genuineStock = row('AAPL', {
    technical_detail: { return_5d: 3, return_20d: 3, relative_strength_20d: 1 },
  })
  const strongEtfWithCatalystInputs = row('ETF_CATALYST', {
    ...strongEtfShapedAsAStock,
    insider_activity: { available: true, points: 5 },
    analyst_count: 10, analyst_rating: 1.1, analyst_target_upside: 40,
  })
  const genuineCatalystStock = row('MSFT', {
    components: { fundamentals: 50, market_behavior: 50, news_sentiment: 80 },
    insider_activity: { available: true, points: 3 },
    technical_detail: { return_5d: 2 },
    analyst_count: 8, analyst_rating: 1.5, analyst_target_upside: 15,
  })

  it.each([
    ['rankValueTurnarounds', rankValueTurnarounds],
    ['rankMomentum', rankMomentum],
    ['rankReversal', rankReversal],
    ['rankBreakoutInProgress', rankBreakoutInProgress],
    ['rankCatalyst', rankCatalyst],
    ['rankAnalystConviction', rankAnalystConviction],
  ])('%s excludes ETF rows even when the ETF would otherwise dominate the ranking', (name, screenFn) => {
    const pool = name === 'rankCatalyst' || name === 'rankAnalystConviction'
      ? [strongEtfWithCatalystInputs, genuineCatalystStock]
      : [strongEtfShapedAsAStock, genuineStock]
    const results = screenFn(pool, 5)

    expect(results.some((item) => item.is_etf)).toBe(false)
  })

  it('rankEmergingGrowth excludes an ETF that would otherwise clear every gate', () => {
    const etfThatWouldQualify = row('FUND_LIKE', {
      is_etf: true,
      technical_detail: { return_5d: 1, relative_strength_20d: 5 },
      fundamental_detail: { revenue_growth: 0.2, operating_margin_trend: 0.03 },
      history: { closes: Array.from({ length: 80 }, (_, index) => 100 + index * 0.1) },
    })
    const genuineCandidate = row('REALCO', {
      technical_detail: { return_5d: 1, relative_strength_20d: 3 },
      fundamental_detail: { revenue_growth: 0.15, operating_margin_trend: 0.02 },
      history: { closes: Array.from({ length: 80 }, (_, index) => 100 + index * 0.1) },
    })

    const results = rankEmergingGrowth([etfThatWouldQualify, genuineCandidate], 5)

    expect(results.some((item) => item.is_etf)).toBe(false)
    expect(results.map((item) => item.ticker)).toEqual(['REALCO'])
  })
})

describe('strategy lens registry', () => {
  const catalystRow = (ticker, overrides = {}) => row(ticker, {
    components: { fundamentals: 60, news_sentiment: 80 },
    technical_detail: { return_5d: 3, return_20d: 6 },
    ...overrides,
  })

  it('ranks tailwind on the best theme opportunity and drops names with no scored exposure', () => {
    const connected = row('CONNECTED', {
      theme_exposure: [
        { theme_id: 'ai', display_name: 'AI Infrastructure', theme_exposure_score: 90, opportunity_score: 70, eligible: true },
        { theme_id: 'grid', display_name: 'Grid', theme_exposure_score: 40, opportunity_score: 88, eligible: true },
      ],
    })
    const unconnected = row('PLAIN', { theme_exposure: [] })

    const ranked = rankTailwind([connected, unconnected], 5)

    expect(ranked.map((item) => item.ticker)).toEqual(['CONNECTED'])
    expect(ranked[0].screen.rankScore).toBe(88)
    expect(ranked[0].screen.themeName).toBe('Grid')
  })

  it('flags a theme name the exposure layer excluded on valuation grounds rather than hiding it', () => {
    const euphoric = row('RICH', {
      theme_exposure: [{ display_name: 'AI', theme_exposure_score: 100, opportunity_score: 60, eligible: false }],
    })

    const [ranked] = rankTailwind([euphoric], 5)

    expect(ranked.screen.corroborated).toBe(false)
    expect(ranked.screen.corroborationGaps.join(' ')).toMatch(/valuation/)
  })

  it('lensCoverage names the single input that excludes the most rows', () => {
    // Reversal needs a 60-day drawdown, which only fully polled rows carry. Reporting
    // that is the difference between "few good candidates" and "most of the universe was
    // never evaluated".
    const complete = row('FULL', {
      components: { fundamentals: 70 },
      technical_detail: { return_5d: 4, return_20d: -8, drawdown_60d: -20 },
    })
    const noDrawdown = row('PARTIAL', {
      components: { fundamentals: 70 },
      technical_detail: { return_5d: 4, return_20d: -8 },
    })

    const coverage = lensCoverage([complete, noDrawdown, { ...noDrawdown, ticker: 'PARTIAL2' }], 'reversal')

    expect(coverage.scanned).toBe(3)
    expect(coverage.evaluable).toBe(1)
    expect(coverage.missingInputs).toBe(2)
    expect(coverage.binding.label).toBe('60-day drawdown')
    expect(coverage.binding.present).toBe(1)
  })

  it('lensCoverage counts a row as evaluable under an any-of lens when one input resolves', () => {
    const newsOnly = catalystRow('NEWS', { insider_activity: { available: false } })
    const dark = catalystRow('DARK', {
      components: { fundamentals: 60 }, insider_activity: { available: false },
    })

    const coverage = lensCoverage([newsOnly, dark], 'catalyst')

    expect(coverage.evaluable).toBe(1)
    expect(coverage.inputs.find((input) => input.label === 'Form 4 insider activity').present).toBe(0)
  })

  it('lensReason states the measurements that made a row qualify', () => {
    const bouncing = row('BOUNCE', {
      components: { fundamentals: 63 },
      technical_detail: { return_5d: 6.6, return_20d: -10.4, drawdown_60d: -27.7 },
    })

    const [ranked] = rankByLens([bouncing], 'reversal', 20)

    expect(lensReason(ranked, 'reversal')).toBe(
      'down 10.4% over 20 days · 27.7% below its 60-day high · but +6.6% this week · fundamentals 63',
    )
  })

  it('rankByLens returns only rows that clear the bar, never a padded ordering', () => {
    const qualifies = row('UP', { technical_detail: { return_5d: 3, return_20d: 8, momentum_12_1: 70 } })
    const falls = row('DOWN', { technical_detail: { return_5d: -3, return_20d: -8 } })

    expect(rankByLens([qualifies, falls], 'momentum', 20).map((item) => item.ticker)).toEqual(['UP'])
  })

  it('every lens is selectable, ranks, and can explain a row it returned', () => {
    expect(Object.keys(STRATEGY_LENSES).every((key) => isStrategyLens(key))).toBe(true)
    expect(isStrategyLens('score')).toBe(false)
    for (const [key, lens] of Object.entries(STRATEGY_LENSES)) {
      expect(typeof lens.rank, key).toBe('function')
      expect(lens.inputs.length, key).toBeGreaterThan(0)
      expect(lensCoverage([row('ANY')], key).scanned, key).toBe(1)
    }
  })
})
