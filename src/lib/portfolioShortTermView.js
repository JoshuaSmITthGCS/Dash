/**
 * Fast reads: what the portfolio has done against the index over days and weeks, and
 * whether any of it means anything yet.
 *
 * Everything else on this page is gated behind real history - acceleration wants two
 * quarters plus a skip, batting average wants six months, capture wants the market to have
 * gone both ways. Those gates are correct for what those measures claim. But they leave a
 * newer account staring at a panel of "Unavailable", and they answer nothing about this
 * week.
 *
 * The problem with short windows is not that they are unavailable, it is that they are
 * mostly noise, and a +2.4% week reported on its own invites a conclusion it cannot
 * support. So every window here is reported next to its own **noise floor**: how large a
 * move would have to be, given this portfolio's own tracking noise, before it is
 * distinguishable from nothing happening. A reading inside the floor is labelled as inside
 * the floor. That is what makes a one-week number safe to publish rather than misleading.
 *
 * Each window reports independently. A portfolio with three weeks of history gets a real
 * answer for the week and an honest "not yet" for the month, instead of one gate refusing
 * everything.
 */
import { alignedIntervals, DAY_MS } from './portfolioSeriesMath.js'
import modelSettings from '../../pipeline/config/settings.json'

const config = modelSettings.portfolio_analytics.short_term_view
const TRADING_DAYS = modelSettings.portfolio_analytics.trading_days_per_year

const pctFromLog = (value) => (Math.exp(value) - 1) * 100

/**
 * Beta over the longest window available up to `baselineDays`, so the excess is adjusted by
 * a stable number rather than one re-estimated from three weeks of data. Returns null when
 * it cannot be measured; the caller then falls back to a raw difference and says so, since
 * a raw portfolio-minus-index difference over one week is still a real fact - just not a
 * market-adjusted one.
 */
function baselineBeta(intervals) {
  if (intervals.length < config.minimum_intervals_for_beta) return null
  const totalDays = intervals.reduce((sum, row) => sum + row.days, 0)
  if (!(totalDays > 0)) return null
  const driftPortfolio = intervals.reduce((sum, row) => sum + row.portfolio, 0) / totalDays
  const driftBenchmark = intervals.reduce((sum, row) => sum + row.benchmark, 0) / totalDays
  let covariance = 0
  let variance = 0
  intervals.forEach((row) => {
    covariance += (row.portfolio - driftPortfolio * row.days) * (row.benchmark - driftBenchmark * row.days) / row.days
    variance += (row.benchmark - driftBenchmark * row.days) ** 2 / row.days
  })
  return variance > 1e-18 ? covariance / variance : null
}

/** Daily standard deviation of excess return, scaled for irregular interval lengths. */
function dailyTrackingDeviation(rows) {
  if (rows.length < 2) return null
  const totalDays = rows.reduce((sum, row) => sum + row.days, 0)
  if (!(totalDays > 0)) return null
  const drift = rows.reduce((sum, row) => sum + row.excess, 0) / totalDays
  const dispersion = rows.reduce(
    (sum, row) => sum + (row.excess - drift * row.days) ** 2 / row.days, 0,
  ) / rows.length
  const deviation = Math.sqrt(dispersion)
  return deviation > 0 ? deviation : null
}

export function shortTermView(portfolioSeries, benchmarkSeries, options = {}) {
  const windowDays = options.windowDays || config.window_days
  const minimumIntervals = Number(options.minimumIntervals ?? config.minimum_intervals)
  const intervals = alignedIntervals(portfolioSeries, benchmarkSeries, options.flows || [])
  if (intervals.length < 2) {
    return { available: false, reason: 'Portfolio and benchmark history do not overlap on enough dates.' }
  }

  const lastDay = intervals.at(-1).end
  const baselineFrom = lastDay - config.baseline_days * DAY_MS
  const baselineRows = intervals.filter((row) => row.end > baselineFrom)
  const beta = baselineBeta(baselineRows)
  const withExcess = (rows) => rows.map((row) => ({
    ...row,
    // Falls back to a plain difference when beta is not yet measurable. Still a real
    // reading, and the caller labels it as unadjusted rather than implying otherwise.
    excess: row.portfolio - (beta == null ? 1 : beta) * row.benchmark,
  }))
  const baseline = withExcess(baselineRows)
  const dailyDeviation = dailyTrackingDeviation(baseline)

  const windows = windowDays.map((days) => {
    const rows = withExcess(intervals.filter((row) => row.end > lastDay - days * DAY_MS))
    const coveredDays = rows.reduce((sum, row) => sum + row.days, 0)
    if (rows.length < minimumIntervals || !(coveredDays > 0)) {
      return {
        days,
        available: false,
        reason: `${rows.length} of ${minimumIntervals} observations so far`,
      }
    }
    const excess = rows.reduce((sum, row) => sum + row.excess, 0)
    // The floor scales with the square root of the window: a month's worth of drift is
    // noisier in absolute terms than a week's, so the same 2% means different things.
    const floor = dailyDeviation == null ? null : dailyDeviation * Math.sqrt(coveredDays)
    return {
      days,
      available: true,
      coveredDays: Math.round(coveredDays),
      observations: rows.length,
      portfolioPct: pctFromLog(rows.reduce((sum, row) => sum + row.portfolio, 0)),
      benchmarkPct: pctFromLog(rows.reduce((sum, row) => sum + row.benchmark, 0)),
      excessPct: pctFromLog(excess),
      noiseFloorPct: floor == null ? null : pctFromLog(floor),
      // |t| > 1 is a deliberately low bar and is not a significance claim. It is the line
      // between "this is larger than this portfolio's ordinary wobble" and "this is the
      // ordinary wobble", which is the only honest thing a one-week number can say.
      beyondNoise: floor == null ? null : Math.abs(excess) > floor,
      betaAdjusted: beta != null,
      reason: null,
    }
  })

  // Consecutive most-recent intervals on the same side of the index. Counted in
  // observations and reported with the days they span, because on a ragged grid "5 in a
  // row" can mean a week or a month.
  const ordered = withExcess(intervals)
  let streakCount = 0
  let streakDays = 0
  const direction = ordered.at(-1).excess >= 0 ? 'ahead' : 'behind'
  for (let index = ordered.length - 1; index >= 0; index -= 1) {
    const side = ordered[index].excess >= 0 ? 'ahead' : 'behind'
    if (side !== direction) break
    streakCount += 1
    streakDays += ordered[index].days
  }

  const recentRows = withExcess(intervals.filter((row) => row.end > lastDay - config.tracking_risk_days * DAY_MS))
  const recentDeviation = dailyTrackingDeviation(recentRows)
  const annualize = (value) => (value == null ? null : value * Math.sqrt(TRADING_DAYS) * 100)

  return {
    available: true,
    windows,
    beta,
    betaAdjusted: beta != null,
    streak: { direction, observations: streakCount, days: Math.round(streakDays) },
    recentTrackingRiskPct: annualize(recentDeviation),
    baselineTrackingRiskPct: annualize(dailyDeviation),
    baselineObservations: baseline.length,
    methodology: beta == null
      ? 'Excess is a plain portfolio-minus-index difference: there is not yet enough history to measure a beta to adjust it by.'
      : `Excess is beta-adjusted at ${beta.toFixed(2)}, fitted over the trailing ${config.baseline_days} days. The noise floor is one standard error of this portfolio's own tracking noise over the same window length.`,
    reason: null,
  }
}

/** Short label for a window tile: what the number is actually saying. */
export function shortTermVerdict(window) {
  if (!window?.available) return window?.reason || 'Not enough history yet'
  if (!(window.noiseFloorPct > 0)) return 'Noise floor unavailable'
  const ratio = Math.abs(window.excessPct) / window.noiseFloorPct
  if (ratio < 0.5) return 'Mostly noise · descriptive band'
  if (ratio < 1) return 'Inside this portfolio’s normal wobble'
  if (ratio < 1.5) return 'Possible signal, not decisive'
  if (ratio < 2) return window.excessPct >= 0 ? 'Meaningful positive deviation' : 'Meaningful negative deviation'
  return window.excessPct >= 0 ? 'Strong recent positive deviation' : 'Strong recent negative deviation'
}
