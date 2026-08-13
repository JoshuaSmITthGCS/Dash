import { describe, expect, it } from 'vitest'
import { shortTermVerdict, shortTermView } from './portfolioShortTermView'

const DAY_MS = 86400000
const START = Date.parse('2025-01-06T00:00:00Z')

/**
 * `days` is the total history available, which is the variable that matters most here:
 * this panel exists so that an account with three weeks of data gets an answer rather than
 * a wall of "Unavailable". `recentEdge` applies over the final `recentDays` only, so a test
 * can put a move inside the week without disturbing the baseline behind it.
 */
function build({ days = 400, spacingDays = 1, wobble = 0.004, edge = 0, recentEdge = 0, recentDays = 0, beta = 1 } = {}) {
  const dates = []
  const portfolio = []
  const benchmark = []
  let portfolioValue = 100000
  let benchmarkValue = 500
  for (let day = 0; day <= days; day += spacingDays) {
    dates.push(new Date(START + day * DAY_MS).toISOString().slice(0, 10))
    portfolio.push(portfolioValue)
    benchmark.push(benchmarkValue)
    const marketMove = 0.0004 + (day % 6 === 0 ? -0.009 : 0.005)
    // Period 7 against the market's period 6 - coprime, so the wobble is genuinely
    // idiosyncratic. On a period that shares a factor with the market's, every down day is
    // also a wobble-down day, the "noise" is market exposure wearing a disguise, and beta
    // comes back at 2.0 for a fixture built with beta 1. It is measuring correctly; the
    // fixture was lying to it.
    const noise = (day % 7) < 3 ? wobble : -0.75 * wobble
    const extra = recentDays && day > days - recentDays ? recentEdge : 0
    benchmarkValue *= (1 + marketMove) ** spacingDays
    portfolioValue *= (1 + beta * marketMove + edge + extra + noise) ** spacingDays
  }
  return { portfolio: { dates, values: portfolio }, benchmark: { dates, values: benchmark } }
}

const windowOf = (reading, days) => reading.windows.find((row) => row.days === days)

describe('shortTermView', () => {
  it('answers the week and the month with the portfolio and index side by side', () => {
    const { portfolio, benchmark } = build({})
    const reading = shortTermView(portfolio, benchmark)
    expect(reading.available).toBe(true)
    const week = windowOf(reading, 7)
    expect(week.available).toBe(true)
    expect(week.coveredDays).toBeLessThanOrEqual(7)
    expect(Number.isFinite(week.portfolioPct)).toBe(true)
    expect(Number.isFinite(week.benchmarkPct)).toBe(true)
    expect(windowOf(reading, 30).coveredDays).toBeLessThanOrEqual(30)
  })

  it('calls a move inside the portfolio’s normal wobble what it is', () => {
    // No edge at all: whatever the last week did, it was noise, and the panel must say so
    // rather than reporting a number that invites a conclusion.
    const { portfolio, benchmark } = build({ wobble: 0.006 })
    const week = windowOf(shortTermView(portfolio, benchmark), 7)
    expect(week.beyondNoise).toBe(false)
    expect(shortTermVerdict(week)).toBe('Mostly noise · descriptive band')
  })

  it('clears the floor when the move is genuinely larger than the noise', () => {
    const { portfolio, benchmark } = build({ wobble: 0.002, recentEdge: 0.02, recentDays: 7 })
    const week = windowOf(shortTermView(portfolio, benchmark), 7)
    expect(week.beyondNoise).toBe(true)
    expect(week.excessPct).toBeGreaterThan(week.noiseFloorPct)
    expect(shortTermVerdict(week)).toBe('Strong recent positive deviation')
  })

  it('scales the noise floor with the length of the window', () => {
    // A month of drift is noisier in absolute terms than a week of it. A fixed threshold
    // would call the same 2% meaningful over a month and meaningless over a week, or worse,
    // the reverse.
    const { portfolio, benchmark } = build({})
    const reading = shortTermView(portfolio, benchmark)
    expect(windowOf(reading, 30).noiseFloorPct).toBeGreaterThan(windowOf(reading, 7).noiseFloorPct)
  })

  it('answers the week for an account far too new for anything else on the page', () => {
    // Three weeks of history on a two-day grid: ten intervals, under the twenty this
    // requires before it will fit a beta. Acceleration needs 189 days and batting average
    // six months; both correctly refuse. This must not.
    const { portfolio, benchmark } = build({ days: 21, spacingDays: 2 })
    const reading = shortTermView(portfolio, benchmark)
    expect(reading.available).toBe(true)
    expect(windowOf(reading, 7).available).toBe(true)
    // And it says so plainly rather than adjusting a week by a three-week beta.
    expect(reading.betaAdjusted).toBe(false)
    expect(reading.methodology).toMatch(/not yet enough history to measure a beta/)
  })

  it('declines only the windows it cannot cover, not the whole panel', () => {
    const { portfolio, benchmark } = build({ days: 400, spacingDays: 11 })
    const reading = shortTermView(portfolio, benchmark)
    const week = windowOf(reading, 7)
    expect(week.available).toBe(false)
    expect(week.reason).toMatch(/of 3 observations so far/)
    // The month still has enough intervals on an 11-day grid, and is unaffected by the
    // week's refusal.
    expect(windowOf(reading, 30).available).toBe(true)
  })

  it('adjusts by a baseline beta rather than one fitted to the short window', () => {
    const { portfolio, benchmark } = build({ beta: 1.6 })
    const reading = shortTermView(portfolio, benchmark)
    expect(reading.betaAdjusted).toBe(true)
    expect(reading.beta).toBeGreaterThan(1.4)
    expect(reading.methodology).toMatch(/fitted over the trailing 180 days/)
  })

  it('counts the current streak in observations and the days they span', () => {
    const { portfolio, benchmark } = build({ edge: 0.004, wobble: 0.0001 })
    const reading = shortTermView(portfolio, benchmark)
    expect(reading.streak.direction).toBe('ahead')
    expect(reading.streak.observations).toBeGreaterThan(1)
    // Days, not just a count: on a ragged grid "5 in a row" can mean a week or a month.
    expect(reading.streak.days).toBeGreaterThanOrEqual(reading.streak.observations)
  })

  it('reports recent tracking risk against its own baseline', () => {
    const calm = build({ wobble: 0.001 })
    const reading = shortTermView(calm.portfolio, calm.benchmark)
    expect(reading.recentTrackingRiskPct).toBeGreaterThan(0)
    expect(reading.baselineTrackingRiskPct).toBeGreaterThan(0)
  })

  it('says why rather than answering when there is nothing to compare', () => {
    expect(shortTermView(null, null).available).toBe(false)
    const { portfolio } = build({})
    expect(shortTermView(portfolio, { dates: ['2025-01-06'], values: [500] }).available).toBe(false)
    expect(shortTermVerdict(null)).toBe('Not enough history yet')
  })
})
