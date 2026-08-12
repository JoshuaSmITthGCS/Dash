/**
 * How your portfolio behaves against the index, split by which way the index went.
 *
 * The ratio tiles already on this page (Sharpe, Sortino, information ratio) each compress a
 * whole return distribution into one number, which is exactly what makes them hard to act
 * on: a 0.4 information ratio does not tell you whether you are winning by keeping up in
 * rallies or by losing less in selloffs. Those are opposite portfolios with the same score.
 *
 * Capture ratios split the record in two and answer it directly. A defensive book - and the
 * research model that feeds this app skews defensive, averaging well under a 1.0 beta - is
 * *supposed* to give up some of the upside in exchange for taking less of the downside. Up
 * and down capture are how you find out whether that trade is actually being made, or
 * whether you are giving up the upside and taking the downside anyway.
 *
 * Batting average answers a different question again: frequency, not magnitude. Capture is
 * dominated by the biggest moves; batting average counts months. Winning 4 months in 12 with
 * three enormous wins and losing 8 small ones is a real strategy, and a fragile one, and the
 * two measures together are what make it visible.
 */
import { alignedIntervals, monthlyReturns } from './portfolioSeriesMath.js'
import modelSettings from '../../pipeline/config/settings.json'

const config = modelSettings.portfolio_analytics.benchmark_comparison

const pctFromLog = (value) => (Math.exp(value) - 1) * 100

/**
 * Cumulative up and down capture, in percent.
 *
 * Up capture is what fraction of the index's gains you kept, measured only over the
 * intervals when the index rose; down capture is what fraction of its losses you took. Both
 * are cumulative (total portfolio log return over those intervals against the index's total
 * over the same intervals) rather than a ratio of averages, because the intervals are not
 * evenly spaced and an average over ragged spans weights a one-day move the same as a
 * three-week one.
 *
 * Read them together. Up 95 / down 70 is the defensive trade working. Up 70 / down 95 is
 * the same trade backwards, and no single-number ratio on this page would have told you.
 */
export function captureRatios(portfolioSeries, benchmarkSeries, options = {}) {
  const minimumPerSide = Number(options.minimumIntervalsPerSide ?? config.minimum_intervals_per_side)
  const intervals = alignedIntervals(portfolioSeries, benchmarkSeries, options.flows || [])
  if (intervals.length < 2) {
    return { available: false, reason: 'Portfolio and benchmark history do not overlap on enough dates.' }
  }
  const up = intervals.filter((row) => row.benchmark > 0)
  const down = intervals.filter((row) => row.benchmark < 0)
  if (up.length < minimumPerSide || down.length < minimumPerSide) {
    return {
      available: false,
      reason: `Needs ${minimumPerSide} up and ${minimumPerSide} down periods; this window has ${up.length} up and ${down.length} down.`,
    }
  }
  const total = (rows, key) => rows.reduce((sum, row) => sum + row[key], 0)
  const upBenchmark = total(up, 'benchmark')
  const downBenchmark = total(down, 'benchmark')
  // Guard the denominators rather than trusting the counts: enough up intervals can still
  // net to nothing in a chopping market, and dividing by that produces a spectacular
  // meaningless number.
  if (!(upBenchmark > 1e-9) || !(downBenchmark < -1e-9)) {
    return { available: false, reason: 'The benchmark netted to no move in one direction over this window.' }
  }
  const upCapturePct = total(up, 'portfolio') / upBenchmark * 100
  const downCapturePct = total(down, 'portfolio') / downBenchmark * 100
  return {
    available: true,
    upCapturePct,
    downCapturePct,
    // The number that actually settles the argument: how much more of the upside you keep
    // than of the downside you take. Positive is the whole point of active risk.
    captureSpread: upCapturePct - downCapturePct,
    observations: { up: up.length, down: down.length },
    upBenchmarkPct: pctFromLog(upBenchmark),
    downBenchmarkPct: pctFromLog(downBenchmark),
    methodology: `Cumulative portfolio return against cumulative benchmark return, over the ${up.length} periods the benchmark rose and the ${down.length} it fell.`,
    reason: null,
  }
}

/**
 * How often you beat the index, by calendar month, plus the size of a typical win against a
 * typical loss.
 *
 * Monthly rather than per observation on purpose. A hit rate has no meaning without a stated
 * cadence - the same portfolio "beats the index 53% of the time" daily and "7 months in 12"
 * monthly, and only one of those is a sentence a person can act on. Monthly bucketing also
 * makes the answer independent of how densely the underlying series happens to be sampled.
 */
export function battingAverage(portfolioSeries, benchmarkSeries, options = {}) {
  const minimumMonths = Number(options.minimumMonths ?? config.minimum_months)
  const months = monthlyReturns(alignedIntervals(portfolioSeries, benchmarkSeries, options.flows || []))
  if (months.length < minimumMonths) {
    return {
      available: false,
      reason: `Needs ${minimumMonths} months of overlapping history; ${months.length} available.`,
    }
  }
  const scored = months.map((month) => ({ ...month, excess: month.portfolio - month.benchmark }))
  const wins = scored.filter((month) => month.excess > 0)
  const losses = scored.filter((month) => month.excess < 0)
  const meanPct = (rows) => (rows.length
    ? pctFromLog(rows.reduce((sum, row) => sum + row.excess, 0) / rows.length)
    : null)
  return {
    available: true,
    battingAveragePct: wins.length / scored.length * 100,
    months: scored.length,
    wins: wins.length,
    losses: losses.length,
    averageWinPct: meanPct(wins),
    averageLossPct: meanPct(losses),
    // Win size against loss size. Above 1 means the months you win are bigger than the ones
    // you lose, which is how a sub-50% batting average can still be a winning record.
    winLossRatio: wins.length && losses.length
      ? Math.abs(meanPct(wins) / meanPct(losses))
      : null,
    firstMonth: scored[0].month,
    lastMonth: scored.at(-1).month,
    methodology: `Calendar months in which the portfolio's return exceeded the benchmark's, ${scored[0].month} to ${scored.at(-1).month}. The first and last months may be partial; both legs cover the same days either way.`,
    reason: null,
  }
}
