import { describe, expect, it } from 'vitest'
import {
  alignForChart, beatMarketStreak, benchmarkShadowPortfolio, detectMilestones, holdingsVsBenchmark,
  portfolioMood, purchaseTimingSignal, snapshotDailySeries, tradeStats, valueStreak,
} from './traderInsights.js'

describe('snapshotDailySeries and alignForChart', () => {
  it('collapses snapshots to one value per market day, keeping the last', () => {
    const series = snapshotDailySeries([
      { marketDate: '2026-01-01', value: 100 },
      { marketDate: '2026-01-01', value: 105 },
      { marketDate: '2026-01-02', value: 110 },
    ])
    expect(series).toEqual({ dates: ['2026-01-01', '2026-01-02'], values: [105, 110] })
  })

  it('merges two series onto a shared date axis with nulls for gaps', () => {
    const primary = { dates: ['2026-01-01', '2026-01-03'], values: [100, 120] }
    const secondary = { dates: ['2026-01-02', '2026-01-03'], values: [50, 55] }
    const aligned = alignForChart(primary, secondary)
    expect(aligned.dates).toEqual(['2026-01-01', '2026-01-02', '2026-01-03'])
    expect(aligned.primaryValues).toEqual([100, null, 120])
    expect(aligned.secondaryValues).toEqual([null, 50, 55])
  })
})

describe('benchmarkShadowPortfolio', () => {
  it('buys benchmark units at each deposit and sells at each withdrawal', () => {
    const history = { symbol: 'SPY', dates: ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04'], closes: [100, 110, 120, 90] }
    const flows = [
      { type: 'deposit', amount: 1000, effectiveDate: '2026-01-01' },
      { type: 'withdrawal', amount: 220, effectiveDate: '2026-01-03' },
      { type: 'deposit', amount: 100, effectiveDate: '2026-01-04', status: 'processing' },
    ]
    const result = benchmarkShadowPortfolio(flows, history)
    expect(result.available).toBe(true)
    expect(result.values[0]).toBeCloseTo(1000, 5)
    expect(result.values[1]).toBeCloseTo(1100, 5)
    // 10 units bought at $100; the $220 withdrawal sells 220/120 units at that day's $120 close.
    expect(result.values[2]).toBeCloseTo(980, 5)
    expect(result.netContributions).toBe(780)
    expect(result.values[3]).toBeCloseTo(735, 5)
  })

  it('is unavailable without overlapping cash flows or history', () => {
    expect(benchmarkShadowPortfolio([], { dates: ['2026-01-01'], closes: [100] }).available).toBe(false)
    expect(benchmarkShadowPortfolio([{ type: 'deposit', amount: 100, effectiveDate: '2026-01-01' }], null).available).toBe(false)
  })
})

describe('tradeStats', () => {
  it('computes win rate and best/worst from realized-gain activity', () => {
    const activities = [
      { type: 'realized_gain', amount: 50, note: 'AAA' },
      { type: 'realized_gain', amount: -20, note: 'BBB' },
      { type: 'realized_gain', amount: 120, note: 'CCC' },
      { type: 'dividend', amount: 5 },
    ]
    const result = tradeStats(activities)
    expect(result.count).toBe(3)
    expect(result.winCount).toBe(2)
    expect(result.winRate).toBeCloseTo(66.667, 2)
    expect(result.best.note).toBe('CCC')
    expect(result.worst.note).toBe('BBB')
    expect(result.totalRealized).toBe(150)
  })

  it('is unavailable with no realized-gain entries', () => {
    expect(tradeStats([{ type: 'dividend', amount: 5 }]).available).toBe(false)
  })
})

describe('purchaseTimingSignal', () => {
  it('flags a purchase well below the trailing average as a dip buy', () => {
    const history = { dates: ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05', '2026-01-06'], closes: [100, 100, 100, 100, 100, 80] }
    const result = purchaseTimingSignal({ purchaseDate: '2026-01-06' }, history, 5)
    expect(result.available).toBe(true)
    expect(result.label).toBe('Bought the dip')
    expect(result.deltaPct).toBeCloseTo(-20, 5)
  })

  it('is unavailable without a purchase date', () => {
    expect(purchaseTimingSignal({}, { dates: ['2026-01-01'], closes: [100] }).available).toBe(false)
  })
})

describe('holdingsVsBenchmark', () => {
  it('ranks holdings by return since purchase versus the benchmark over the same window', () => {
    const benchmarkHistory = { dates: ['2026-01-01', '2026-02-01'], closes: [100, 110] }
    const positions = [
      { ticker: 'WIN', purchaseDate: '2026-01-01', currentPrice: 150, priceInfo: { history: { dates: ['2026-01-01', '2026-02-01'], closes: [100, 150] } } },
      { ticker: 'LAG', purchaseDate: '2026-01-01', currentPrice: 102, priceInfo: { history: { dates: ['2026-01-01', '2026-02-01'], closes: [100, 102] } } },
    ]
    const result = holdingsVsBenchmark(positions, benchmarkHistory)
    expect(result[0].ticker).toBe('WIN')
    expect(result[0].stockReturnPct).toBeCloseTo(50, 5)
    expect(result[1].ticker).toBe('LAG')
    expect(result[0].deltaPct).toBeGreaterThan(result[1].deltaPct)
  })
})

describe('valueStreak', () => {
  it('counts consecutive same-direction days from the most recent snapshot backward', () => {
    const snapshots = [
      { marketDate: '2026-01-01', value: 100 },
      { marketDate: '2026-01-02', value: 105 },
      { marketDate: '2026-01-03', value: 90 },
      { marketDate: '2026-01-04', value: 95 },
      { marketDate: '2026-01-05', value: 110 },
    ]
    const result = valueStreak(snapshots)
    expect(result.direction).toBe('up')
    expect(result.days).toBe(2)
  })
})

describe('beatMarketStreak', () => {
  it('counts consecutive days the tracked account beat the benchmark day-over-day', () => {
    const snapshots = [
      { marketDate: '2026-01-01', value: 1000 },
      { marketDate: '2026-01-02', value: 1050 },
      { marketDate: '2026-01-03', value: 1100 },
    ]
    const benchmarkHistory = { dates: ['2026-01-01', '2026-01-02', '2026-01-03'], closes: [100, 103, 104] }
    const result = beatMarketStreak(snapshots, benchmarkHistory)
    expect(result.available).toBe(true)
    expect(result.beating).toBe(true)
    expect(result.days).toBe(2)
  })
})

describe('detectMilestones', () => {
  it('finds the first snapshot date that crossed each reached threshold', () => {
    const snapshots = [
      { marketDate: '2026-01-01', value: 400 },
      { marketDate: '2026-01-15', value: 900 },
      { marketDate: '2026-02-01', value: 1200 },
    ]
    const milestones = detectMilestones({ snapshots, trackedAccountValue: 1200 })
    expect(milestones).toEqual([
      { id: 'value-500', label: 'Portfolio reached $500', achievedDate: '2026-01-15' },
      { id: 'value-1000', label: 'Portfolio reached $1,000', achievedDate: '2026-02-01' },
    ])
  })
})

describe('portfolioMood', () => {
  it('reflects contribution-adjusted return and flags low diversification', () => {
    expect(portfolioMood({ returnPct: null }).label).toBe('Just getting started')
    expect(portfolioMood({ returnPct: 25 }).label).toBe('On fire')
    const rough = portfolioMood({ returnPct: -30, diversificationScore: 40 })
    expect(rough.label).toBe('Stormy')
    expect(rough.note).toContain('Concentration is elevated.')
  })
})
