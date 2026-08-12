import { describe, expect, it } from 'vitest'
import { accelerationLabel, portfolioAcceleration } from './portfolioAcceleration'

const DAY_MS = 86400000
const START = Date.parse('2025-01-06T00:00:00Z')

/**
 * Builds a portfolio and a benchmark on a shared grid. `spacingDays` lets a test choose the
 * ~weekly cadence of the backtested-basket series or the daily cadence of recorded account
 * values, since the measure has to survive both.
 *
 * The recent leg is the last 91 days before the 7-day skip; `recentEdge` and `priorEdge` are
 * the portfolio's daily excess-return rate on either side of that boundary, and `beta` is
 * how much of the market's move it takes.
 */
function build({ beta = 1, priorEdge = 0, recentEdge = 0, spacingDays = 4, days = 420, marketDrift = 0.0004 } = {}) {
  const dates = []
  const portfolio = []
  const benchmark = []
  let portfolioValue = 100000
  let benchmarkValue = 500
  const boundary = days - 7 - 91
  for (let day = 0; day <= days; day += spacingDays) {
    dates.push(new Date(START + day * DAY_MS).toISOString().slice(0, 10))
    portfolio.push(portfolioValue)
    benchmark.push(benchmarkValue)
    // Alternating market moves and an out-of-phase idiosyncratic wobble, so beta is
    // recoverable and the portfolio has real tracking noise to be measured against.
    const marketMove = marketDrift + (day % (spacingDays * 2) ? 0.0012 : -0.0011)
    const wobble = day % (spacingDays * 3) ? 0.0006 : -0.0013
    const edge = day < boundary ? priorEdge : recentEdge
    benchmarkValue *= (1 + marketMove) ** spacingDays
    portfolioValue *= (1 + beta * marketMove + edge + wobble) ** spacingDays
  }
  return {
    portfolio: { dates, values: portfolio },
    benchmark: { dates, values: benchmark },
  }
}

describe('portfolioAcceleration', () => {
  it('reads positive when the portfolio is pulling ahead faster than it was', () => {
    const { portfolio, benchmark } = build({ priorEdge: 0.0001, recentEdge: 0.0016 })
    const reading = portfolioAcceleration(portfolio, benchmark)
    expect(reading.available).toBe(true)
    expect(reading.acceleration).toBeGreaterThan(1)
    expect(reading.recentExcessPct).toBeGreaterThan(reading.priorExcessPct)
    expect(accelerationLabel(reading)).toBe('Pulling ahead faster')
  })

  it('reads negative when a lead is being given back', () => {
    const { portfolio, benchmark } = build({ priorEdge: 0.0018, recentEdge: -0.0002 })
    const reading = portfolioAcceleration(portfolio, benchmark)
    expect(reading.acceleration).toBeLessThan(-1)
    expect(reading.recentExcessPct).toBeLessThan(reading.priorExcessPct)
    expect(accelerationLabel(reading)).toBe('Losing ground fast')
  })

  it('reads flat for a portfolio beating the market at a steady clip', () => {
    // Consistently ahead is not accelerating. This is the whole distinction being drawn:
    // the performance tiles already say how far ahead you are.
    const { portfolio, benchmark } = build({ priorEdge: 0.0012, recentEdge: 0.0012 })
    const reading = portfolioAcceleration(portfolio, benchmark)
    expect(Math.abs(reading.acceleration)).toBeLessThan(0.25)
    expect(accelerationLabel(reading)).toBe('Holding its pace')
  })

  it('does not credit a high-beta book for a market that accelerated under it', () => {
    // A 1.8-beta portfolio that added nothing of its own, in a market whose own pace picks
    // up over the recent leg. Its raw value curve steepens; it outran nothing. A
    // portfolio-minus-index difference would call this acceleration.
    const days = 420
    const boundary = days - 7 - 91
    const dates = []
    const portfolio = []
    const benchmark = []
    let portfolioValue = 100000
    let benchmarkValue = 500
    for (let day = 0; day <= days; day += 4) {
      dates.push(new Date(START + day * DAY_MS).toISOString().slice(0, 10))
      portfolio.push(portfolioValue)
      benchmark.push(benchmarkValue)
      const drift = day < boundary ? 0.0002 : 0.0018
      const marketMove = drift + (day % 8 ? 0.0012 : -0.0011)
      const wobble = day % 12 ? 0.0006 : -0.0013
      benchmarkValue *= (1 + marketMove) ** 4
      portfolioValue *= (1 + 1.8 * marketMove + wobble) ** 4
    }
    const reading = portfolioAcceleration({ dates, values: portfolio }, { dates, values: benchmark })
    expect(reading.available).toBe(true)
    // The raw path really did speed up - that is what makes this the case worth testing.
    const raw = portfolio.at(-3) / portfolio.at(-25) > portfolio.at(-25) / portfolio.at(-47)
    expect(raw).toBe(true)
    expect(reading.beta).toBeGreaterThan(1.5)
    expect(Math.abs(reading.acceleration)).toBeLessThan(1)
  })

  /** Cash arriving in an account gets invested, so it scales the value path from that day
   * rather than sitting on top of it as a constant. Modelling it as a constant addition
   * would quietly damp every later return and put the flow adjustment on trial for a
   * distortion the fixture invented. */
  const applyFlow = (values, index, amount) => {
    const scale = (values[index] + amount) / values[index]
    return values.map((value, position) => (position >= index ? value * scale : value))
  }

  it('does not read a deposit as performance', () => {
    // Without flow adjustment a payday inside the recent leg is a step change in account
    // value that the measure would happily report as blistering acceleration.
    const { portfolio, benchmark } = build({ priorEdge: 0.0006, recentEdge: 0.0006 })
    const depositIndex = portfolio.values.length - 12
    const injected = applyFlow(portfolio.values, depositIndex, 40000)
    const flows = [{ type: 'deposit', effectiveDate: portfolio.dates[depositIndex], amount: 40000 }]

    const unadjusted = portfolioAcceleration({ ...portfolio, values: injected }, benchmark)
    const adjusted = portfolioAcceleration({ ...portfolio, values: injected }, benchmark, { flows })
    expect(unadjusted.acceleration).toBeGreaterThan(1)
    expect(Math.abs(adjusted.acceleration)).toBeLessThan(0.25)
    expect(adjusted.flowsApplied).toBe(1)
  })

  it('nets a withdrawal back in rather than reading it as a collapse', () => {
    const { portfolio, benchmark } = build({ priorEdge: 0.0006, recentEdge: 0.0006 })
    const index = portfolio.values.length - 10
    const drained = applyFlow(portfolio.values, index, -25000)
    const unadjusted = portfolioAcceleration({ ...portfolio, values: drained }, benchmark)
    const flows = [{ type: 'withdrawal', effectiveDate: portfolio.dates[index], amount: 25000 }]
    const adjusted = portfolioAcceleration({ ...portfolio, values: drained }, benchmark, { flows })
    expect(unadjusted.acceleration).toBeLessThan(-1)
    expect(Math.abs(adjusted.acceleration)).toBeLessThan(0.25)
  })

  it('measures the same pickup whether it is handed a daily or a weekly grid', () => {
    // One underlying path, sampled two ways - the backtested basket lands on the
    // benchmark's ~4-day grid while recorded account values can be daily or ragged.
    // The percentage-point pickup is what must not move: log returns telescope, so
    // subsampling cannot change it. The t-statistic is a different matter - see the note
    // on sampling in portfolioAcceleration.js.
    const daily = build({ priorEdge: 0.0002, recentEdge: 0.0015, spacingDays: 1 })
    const keep = (_value, index) => index % 7 === 0 || index === daily.portfolio.dates.length - 1
    const weekly = {
      portfolio: {
        dates: daily.portfolio.dates.filter(keep),
        values: daily.portfolio.values.filter(keep),
      },
      benchmark: {
        dates: daily.benchmark.dates.filter(keep),
        values: daily.benchmark.values.filter(keep),
      },
    }
    const dailyReading = portfolioAcceleration(daily.portfolio, daily.benchmark)
    const weeklyReading = portfolioAcceleration(weekly.portfolio, weekly.benchmark)
    expect(dailyReading.acceleration).toBeGreaterThan(1)
    expect(weeklyReading.acceleration).toBeGreaterThan(1)
    const gap = Math.abs(weeklyReading.accelerationPct - dailyReading.accelerationPct)
    expect(gap / Math.abs(dailyReading.accelerationPct)).toBeLessThan(0.15)
  })

  it('survives a grid that is dense recently and sparse further back', () => {
    // Not hypothetical: the published history grid thins out with age. A real four-holding
    // portfolio on it measured 44 observations in the recent leg against 9 in the prior one.
    // Summing excess per leg would read the densely sampled half as the faster one purely
    // because it has more terms in the sum, so both legs are reduced to rates per day first.
    const daily = build({ priorEdge: 0.0002, recentEdge: 0.0015, spacingDays: 1 })
    const total = daily.portfolio.dates.length
    const ragged = (_value, index) => (index > total * 0.72 ? true : index % 11 === 0)
    const thinned = {
      portfolio: { dates: daily.portfolio.dates.filter(ragged), values: daily.portfolio.values.filter(ragged) },
      benchmark: { dates: daily.benchmark.dates.filter(ragged), values: daily.benchmark.values.filter(ragged) },
    }
    const evenly = portfolioAcceleration(daily.portfolio, daily.benchmark)
    const reading = portfolioAcceleration(thinned.portfolio, thinned.benchmark)
    expect(reading.available).toBe(true)
    expect(reading.observations.recent).toBeGreaterThan(reading.observations.prior * 2)
    expect(reading.acceleration).toBeGreaterThan(1)
    const gap = Math.abs(reading.accelerationPct - evenly.accelerationPct)
    expect(gap / Math.abs(evenly.accelerationPct)).toBeLessThan(0.2)
  })

  it('ignores the skipped window entirely', () => {
    const { portfolio, benchmark } = build({ priorEdge: 0.0006, recentEdge: 0.0006 })
    const shocked = portfolio.values.map((value, index) =>
      (index >= portfolio.values.length - 1 ? value * 0.85 : value))
    const before = portfolioAcceleration(portfolio, benchmark)
    const after = portfolioAcceleration({ ...portfolio, values: shocked }, benchmark)
    expect(after.acceleration).toBeCloseTo(before.acceleration, 10)
  })

  it('says why it cannot answer rather than returning a neutral zero', () => {
    const short = build({ days: 120 })
    const tooShort = portfolioAcceleration(short.portfolio, short.benchmark)
    expect(tooShort.available).toBe(false)
    expect(tooShort.acceleration).toBeNull()
    expect(tooShort.reason).toMatch(/days of overlapping history/)

    expect(portfolioAcceleration(null, null).available).toBe(false)
    expect(accelerationLabel(null)).toBe('Unavailable')

    const { portfolio } = build({})
    const flat = { dates: portfolio.dates, values: portfolio.dates.map(() => 100) }
    expect(portfolioAcceleration(portfolio, flat).available).toBe(false)
  })

  it('reports the window it actually measured', () => {
    const { portfolio, benchmark } = build({ priorEdge: 0.0002, recentEdge: 0.0015 })
    const reading = portfolioAcceleration(portfolio, benchmark)
    expect(reading.legDays).toBe(91)
    expect(reading.skipDays).toBe(7)
    expect(reading.window.measuredEnd < portfolio.dates.at(-1)).toBe(true)
    expect(reading.observations.recent).toBeGreaterThanOrEqual(6)
    expect(reading.observations.prior).toBeGreaterThanOrEqual(6)
    expect(reading.methodology).toContain('Beta measured at')
  })
})
