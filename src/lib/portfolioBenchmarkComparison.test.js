import { describe, expect, it } from 'vitest'
import { battingAverage, captureRatios } from './portfolioBenchmarkComparison'

const DAY_MS = 86400000
const START = Date.parse('2025-01-06T00:00:00Z')

/**
 * A market that genuinely goes both ways, and a portfolio that takes a chosen fraction of
 * each direction. `upBeta` and `downBeta` are the whole point: they let a test build the
 * asymmetry that a single blended ratio cannot see.
 */
function build({ upBeta = 1, downBeta = 1, alphaPerDay = 0, alphaFlipDays = 0, days = 400, spacingDays = 2 } = {}) {
  const dates = []
  const portfolio = []
  const benchmark = []
  let portfolioValue = 100000
  let benchmarkValue = 500
  for (let day = 0; day <= days; day += spacingDays) {
    dates.push(new Date(START + day * DAY_MS).toISOString().slice(0, 10))
    portfolio.push(portfolioValue)
    benchmark.push(benchmarkValue)
    // Roughly two thirds up periods, a realistic mix rather than a clean alternation.
    const marketMove = day % 6 === 0 ? -0.009 : 0.005
    const responded = marketMove > 0 ? upBeta * marketMove : downBeta * marketMove
    // A portfolio with a permanent edge wins every single month, which is no fixture at all
    // for anything that counts wins against losses. Flipping the edge's sign on a slower
    // cycle than the market's produces a record with both in it.
    const edge = alphaFlipDays && Math.floor(day / alphaFlipDays) % 2 ? -alphaPerDay : alphaPerDay
    benchmarkValue *= (1 + marketMove) ** spacingDays
    portfolioValue *= (1 + responded + edge) ** spacingDays
  }
  return { portfolio: { dates, values: portfolio }, benchmark: { dates, values: benchmark } }
}

/** Index of the most recent observation whose benchmark interval rose. A cash-flow test has
 * to know which side of the market its flow lands on, or it asserts against the wrong half. */
function lastRisingIndex(benchmark, notAfter) {
  for (let index = notAfter; index > 1; index -= 1) {
    if (benchmark.values[index] > benchmark.values[index - 1]) return index
  }
  return -1
}

describe('captureRatios', () => {
  it('separates a defensive portfolio from a leveraged one that share a blended ratio', () => {
    // This is the case the panel's other tiles cannot distinguish: both of these beat the
    // index, and only capture says how.
    const defensive = build({ upBeta: 0.75, downBeta: 0.45 })
    const aggressive = build({ upBeta: 1.35, downBeta: 1.3 })
    const shy = captureRatios(defensive.portfolio, defensive.benchmark)
    const bold = captureRatios(aggressive.portfolio, aggressive.benchmark)

    expect(shy.available).toBe(true)
    expect(shy.upCapturePct).toBeLessThan(90)
    expect(shy.downCapturePct).toBeLessThan(60)
    expect(shy.captureSpread).toBeGreaterThan(0)

    expect(bold.upCapturePct).toBeGreaterThan(shy.upCapturePct)
    expect(bold.downCapturePct).toBeGreaterThan(shy.downCapturePct)
  })

  it('reports a negative spread for the defensive trade made backwards', () => {
    // Giving up the upside and taking the downside anyway - the failure mode a low-beta
    // book is actually at risk of, and one no single-number ratio on the page flags.
    const { portfolio, benchmark } = build({ upBeta: 0.6, downBeta: 1.2 })
    const reading = captureRatios(portfolio, benchmark)
    expect(reading.upCapturePct).toBeLessThan(80)
    expect(reading.downCapturePct).toBeGreaterThan(100)
    expect(reading.captureSpread).toBeLessThan(0)
  })

  it('tracks the index at roughly 100/100 when it is the index', () => {
    const { portfolio, benchmark } = build({ upBeta: 1, downBeta: 1 })
    const reading = captureRatios(portfolio, benchmark)
    expect(reading.upCapturePct).toBeGreaterThan(95)
    expect(reading.upCapturePct).toBeLessThan(105)
    expect(reading.downCapturePct).toBeGreaterThan(95)
    expect(reading.downCapturePct).toBeLessThan(105)
    expect(Math.abs(reading.captureSpread)).toBeLessThan(6)
  })

  it('counts both sides and refuses when one of them is missing', () => {
    const { portfolio, benchmark } = build({})
    const reading = captureRatios(portfolio, benchmark)
    expect(reading.observations.up).toBeGreaterThan(0)
    expect(reading.observations.down).toBeGreaterThan(0)
    expect(reading.upBenchmarkPct).toBeGreaterThan(0)
    expect(reading.downBenchmarkPct).toBeLessThan(0)

    // A window with no down periods cannot produce a down capture, and inventing one from
    // the up side would be worse than saying so.
    const rising = { dates: portfolio.dates, values: portfolio.dates.map((_d, i) => 100 * 1.002 ** i) }
    const onlyUp = captureRatios(rising, rising)
    expect(onlyUp.available).toBe(false)
    expect(onlyUp.reason).toMatch(/up and .* down/)
  })

  it('nets a deposit out rather than reading it as upside capture', () => {
    const { portfolio, benchmark } = build({ upBeta: 1, downBeta: 1 })
    const index = lastRisingIndex(benchmark, portfolio.values.length - 6)
    const scale = (portfolio.values[index] + 50000) / portfolio.values[index]
    const injected = portfolio.values.map((value, position) => (position >= index ? value * scale : value))
    const flows = [{ type: 'deposit', effectiveDate: portfolio.dates[index], amount: 50000 }]
    const unadjusted = captureRatios({ ...portfolio, values: injected }, benchmark)
    const adjusted = captureRatios({ ...portfolio, values: injected }, benchmark, { flows })
    expect(unadjusted.upCapturePct).toBeGreaterThan(adjusted.upCapturePct + 10)
    expect(adjusted.upCapturePct).toBeGreaterThan(95)
    expect(adjusted.upCapturePct).toBeLessThan(105)
  })
})

describe('battingAverage', () => {
  it('counts the months a portfolio actually beat the index', () => {
    const { portfolio, benchmark } = build({ alphaPerDay: 0.0008 })
    const reading = battingAverage(portfolio, benchmark)
    expect(reading.available).toBe(true)
    expect(reading.battingAveragePct).toBeGreaterThan(80)
    expect(reading.wins + reading.losses).toBeLessThanOrEqual(reading.months)
    expect(reading.averageWinPct).toBeGreaterThan(0)
  })

  it('reads under half for a portfolio quietly losing to the index', () => {
    const { portfolio, benchmark } = build({ alphaPerDay: -0.0008 })
    const reading = battingAverage(portfolio, benchmark)
    expect(reading.battingAveragePct).toBeLessThan(20)
    expect(reading.averageLossPct).toBeLessThan(0)
  })

  it('is a monthly count, not a per-observation one', () => {
    // The same portfolio sampled twice as often must give the same answer - a hit rate that
    // moves with sampling frequency is not a fact about the portfolio.
    const dense = build({ alphaPerDay: 0.0004, spacingDays: 1 })
    const sparse = build({ alphaPerDay: 0.0004, spacingDays: 4 })
    const denseReading = battingAverage(dense.portfolio, dense.benchmark)
    const sparseReading = battingAverage(sparse.portfolio, sparse.benchmark)
    expect(denseReading.months).toBe(sparseReading.months)
    expect(Math.abs(denseReading.battingAveragePct - sparseReading.battingAveragePct)).toBeLessThan(10)
  })

  it('sizes wins against losses so a sub-50% record can still be explained', () => {
    const { portfolio, benchmark } = build({ alphaPerDay: 0.0012, alphaFlipDays: 60 })
    const reading = battingAverage(portfolio, benchmark)
    expect(reading.wins).toBeGreaterThan(0)
    expect(reading.losses).toBeGreaterThan(0)
    expect(reading.winLossRatio).toBeGreaterThan(0)
    expect(reading.averageWinPct).toBeGreaterThan(0)
    expect(reading.averageLossPct).toBeLessThan(0)
    expect(reading.methodology).toContain(reading.firstMonth)
  })

  it('says how much history it is missing instead of answering anyway', () => {
    const short = build({ days: 40 })
    const reading = battingAverage(short.portfolio, short.benchmark)
    expect(reading.available).toBe(false)
    expect(reading.reason).toMatch(/months of overlapping history/)
    expect(battingAverage(null, null).available).toBe(false)
  })
})
