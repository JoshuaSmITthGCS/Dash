/**
 * Is your portfolio pulling ahead of the market faster than it was?
 *
 * The performance tiles next to this one answer level questions: how far ahead you are, how
 * much risk you took to get there. This answers the derivative question - whether the gap is
 * still widening. A portfolio that beat the index by 8% last quarter and 1% this one is
 * still "ahead", and is losing the argument.
 *
 * Same measure as pipeline/risk_metrics.py's relative_acceleration, which scores individual
 * companies, with one adaptation: that one runs on daily closes, and a portfolio series here
 * may be the backtested basket on the benchmark's ~weekly date grid or a set of irregularly
 * dated account valuations. So everything below is expressed per calendar day and scaled by
 * elapsed time rather than by observation count. On an evenly spaced grid the two reduce to
 * the same arithmetic.
 *
 * Two construction choices carry the measure, and both are the reason a naive version of it
 * is worthless:
 *
 *   1. **Beta-adjusted.** Excess is `portfolio - beta x benchmark`, not `portfolio -
 *      benchmark`. A 1.4-beta book in a rallying market accelerates on a raw difference
 *      without having outrun anything - it was carried. Scaling the market leg by the
 *      portfolio's own measured beta is what separates "I pulled ahead" from "the index
 *      pulled me".
 *   2. **Divided by its own tracking noise.** The published number is a t-statistic, so it
 *      reads the same on a concentrated growth book and a diversified defensive one. +1.0
 *      means a pickup one standard error larger than this portfolio's ordinary wobble
 *      against the index - not one percent.
 *
 * The most recent `skip_days` are excluded. Very short-term moves reverse, and a portfolio
 * that happens to be measured the morning after one bad session should not read as
 * decelerating because of it.
 *
 * One honest limitation on sampling. The percentage-point pickup is invariant to how often
 * the series was sampled - log returns telescope, so a weekly grid and a daily one over the
 * same path give the same number. The t-statistic is not, quite: its denominator is an
 * estimate of tracking noise, and coarse sampling averages away noise that reverses inside
 * an interval, which can make the same pickup look statistically larger on a weekly series
 * than a daily one. For a random walk the two agree in expectation. Read the t-statistic as
 * the headline and `accelerationPct` as the quantity that is sampling-proof.
 */
import modelSettings from '../../pipeline/config/settings.json'
import { alignedIntervals, DAY_MS, finite, isoDay } from './portfolioSeriesMath.js'

const config = modelSettings.portfolio_analytics.acceleration

const unavailable = (reason) => ({ available: false, acceleration: null, reason })

/**
 * Beta of the portfolio against the benchmark, fitted on the same intervals the reading is
 * measured over and weighted by 1/days so a long gap does not count as one observation's
 * worth of evidence. Never defaulted to 1.0 - a portfolio whose beta cannot be measured is
 * reported as unmeasured, because assuming a beta assumes the answer.
 */
function fitBeta(intervals) {
  const totalDays = intervals.reduce((sum, row) => sum + row.days, 0)
  if (!(totalDays > 0)) return null
  const driftPortfolio = intervals.reduce((sum, row) => sum + row.portfolio, 0) / totalDays
  const driftBenchmark = intervals.reduce((sum, row) => sum + row.benchmark, 0) / totalDays
  let covariance = 0
  let variance = 0
  intervals.forEach((row) => {
    const portfolio = row.portfolio - driftPortfolio * row.days
    const benchmark = row.benchmark - driftBenchmark * row.days
    covariance += portfolio * benchmark / row.days
    variance += benchmark * benchmark / row.days
  })
  return variance > 1e-18 ? covariance / variance : null
}

export function portfolioAcceleration(portfolioSeries, benchmarkSeries, options = {}) {
  const legDays = Number(options.legDays ?? config.leg_days)
  const skipDays = Number(options.skipDays ?? config.skip_days)
  const minimumPerLeg = Number(options.minimumIntervalsPerLeg ?? config.minimum_intervals_per_leg)
  const flows = Array.isArray(options.flows) ? options.flows : []

  const intervals = alignedIntervals(portfolioSeries, benchmarkSeries, flows)
  if (intervals.length < 2) {
    return unavailable('Portfolio and benchmark history do not overlap on enough dates.')
  }

  const lastDay = intervals.at(-1).end
  const measuredEnd = lastDay - skipDays * DAY_MS
  const legBoundary = measuredEnd - legDays * DAY_MS
  const priorStart = measuredEnd - 2 * legDays * DAY_MS
  if (intervals[0].end > priorStart) {
    const covered = Math.round((lastDay - intervals[0].end) / DAY_MS)
    return unavailable(`Needs ${2 * legDays + skipDays} days of overlapping history; ${covered} available.`)
  }

  // Each interval belongs to the leg its end date falls in. Everything from priorStart to
  // measuredEnd is used and nothing outside it is, so the skipped window cannot reach the
  // reading - not through the legs and not through beta.
  const measured = intervals.filter((row) => row.end > priorStart && row.end <= measuredEnd)
  const recent = measured.filter((row) => row.end > legBoundary)
  const prior = measured.filter((row) => row.end <= legBoundary)
  if (recent.length < minimumPerLeg || prior.length < minimumPerLeg) {
    return unavailable(`Each half of the window needs ${minimumPerLeg} observations; this window has ${recent.length} recent and ${prior.length} prior.`)
  }

  const beta = fitBeta(measured)
  if (beta == null) {
    return unavailable('The benchmark did not move enough over this window to measure a beta against.')
  }

  const excess = measured.map((row) => ({ ...row, excess: row.portfolio - beta * row.benchmark }))
  const totalOf = (rows, key) => rows.reduce((sum, row) => sum + row[key], 0)
  const recentRows = excess.filter((row) => row.end > legBoundary)
  const priorRows = excess.filter((row) => row.end <= legBoundary)
  const recentDays = totalOf(recentRows, 'days')
  const priorDays = totalOf(priorRows, 'days')
  if (!(recentDays > 0) || !(priorDays > 0)) return unavailable('Window halves cover no elapsed time.')

  // Rates, not sums: the two halves cover the same nominal span but need not hold the same
  // number of observations or the same covered days, and comparing raw sums across unequal
  // spans would read the longer half as the faster one.
  const recentRate = totalOf(recentRows, 'excess') / recentDays
  const priorRate = totalOf(priorRows, 'excess') / priorDays

  const drift = totalOf(excess, 'excess') / totalOf(excess, 'days')
  const dispersion = excess.reduce((sum, row) => {
    const residual = row.excess - drift * row.days
    return sum + residual * residual / row.days
  }, 0) / excess.length
  const dailyDeviation = Math.sqrt(dispersion)
  if (!(dailyDeviation > 0)) {
    return unavailable('This portfolio has not deviated from the benchmark at all over the window.')
  }

  const change = (recentRate - priorRate) * legDays
  const standardError = dailyDeviation * legDays * Math.sqrt(1 / recentDays + 1 / priorDays)
  const asPct = (rate) => (Math.exp(rate * legDays) - 1) * 100
  const recentExcessPct = asPct(recentRate)
  const priorExcessPct = asPct(priorRate)

  return {
    available: true,
    acceleration: change / standardError,
    accelerationPct: recentExcessPct - priorExcessPct,
    recentExcessPct,
    priorExcessPct,
    beta,
    legDays,
    skipDays,
    observations: { recent: recentRows.length, prior: priorRows.length },
    window: {
      priorStart: isoDay(priorStart),
      legBoundary: isoDay(legBoundary),
      measuredEnd: isoDay(measuredEnd),
    },
    flowsApplied: flows.length,
    methodology: `Beta-adjusted excess return over the ${legDays} days to ${isoDay(measuredEnd)}, less the same over the ${legDays} days before it, divided by this portfolio's own tracking noise. The most recent ${skipDays} days are excluded. Beta measured at ${beta.toFixed(2)}.`,
    reason: null,
  }
}

/** Plain-language read of a t-statistic, for a tile that has room for four words. */
export function accelerationLabel(reading) {
  if (!reading?.available || !finite(reading.acceleration)) return 'Unavailable'
  const value = reading.acceleration
  if (value >= 1) return 'Pulling ahead faster'
  if (value > 0.25) return 'Edging ahead'
  if (value >= -0.25) return 'Holding its pace'
  if (value > -1) return 'Slipping back'
  return 'Losing ground fast'
}
