/**
 * Turning a portfolio value series and a benchmark series into comparable return intervals.
 *
 * Every benchmark-relative measure in this app needs the same three things done first, and
 * done identically, or two panels will quietly disagree about the same portfolio:
 *
 *   1. **Align on shared dates.** A portfolio observation with no benchmark close on the
 *      same day cannot be compared to anything.
 *   2. **Net out external cash.** A deposit raises account value without the strategy having
 *      earned a cent. Left in, a payday reads as a spectacular week.
 *   3. **Carry elapsed time.** The value series is not guaranteed to be daily - it may be
 *      the backtested basket on the benchmark's roughly weekly grid, or a ragged set of
 *      recorded account valuations. A 30-day gap is not one day's worth of risk, and on the
 *      published grid the recent half of a window can hold four times the observations of
 *      the older half purely because the grid thins with age.
 *
 * Returns log returns, which are additive over time: that is what lets a measure compare
 * unequal spans without the longer one mechanically looking larger.
 */

export const DAY_MS = 86400000

export const finite = (value) =>
  value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))

export const dayOf = (date) => Date.parse(`${String(date).slice(0, 10)}T00:00:00Z`)

export const isoDay = (milliseconds) => new Date(milliseconds).toISOString().slice(0, 10)

/**
 * Net settled external cash landing in (after, upTo]. Withdrawals count negative whatever
 * sign the caller stored the amount with, since transaction records are not consistent
 * about it and a withdrawal recorded as a positive number would otherwise be added twice.
 */
export function netFlowBetween(flows, after, upTo) {
  return (flows || []).reduce((sum, flow) => {
    const when = dayOf(flow?.effectiveDate || flow?.date)
    if (!Number.isFinite(when) || when <= after || when > upTo) return sum
    const amount = Number(flow?.amount)
    if (!finite(amount)) return sum
    const withdrawal = String(flow.type || '').includes('withdraw')
    return sum + (withdrawal ? -Math.abs(amount) : Math.abs(amount))
  }, 0)
}

/**
 * Consecutive log returns for the portfolio and the benchmark over their shared dates, each
 * tagged with the calendar days it spans. Intervals, not observations.
 */
export function alignedIntervals(portfolioSeries, benchmarkSeries, flows = []) {
  const benchmarkByDate = new Map()
  ;(benchmarkSeries?.dates || []).forEach((date, index) => {
    const value = benchmarkSeries.values?.[index]
    if (finite(value) && Number(value) > 0) benchmarkByDate.set(String(date).slice(0, 10), Number(value))
  })
  const shared = (portfolioSeries?.dates || [])
    .map((date, index) => ({ date: String(date).slice(0, 10), value: portfolioSeries.values?.[index] }))
    .filter((row) => finite(row.value) && Number(row.value) > 0 && benchmarkByDate.has(row.date))
    .sort((left, right) => left.date.localeCompare(right.date))

  const intervals = []
  for (let index = 1; index < shared.length; index += 1) {
    const from = shared[index - 1]
    const to = shared[index]
    const start = dayOf(from.date)
    const end = dayOf(to.date)
    const days = (end - start) / DAY_MS
    if (!Number.isFinite(days) || days <= 0) continue
    const endValue = Number(to.value) - netFlowBetween(flows, start, end)
    if (!(endValue > 0)) continue
    intervals.push({
      startDate: from.date,
      endDate: to.date,
      end,
      days,
      portfolio: Math.log(endValue / Number(from.value)),
      benchmark: Math.log(benchmarkByDate.get(to.date) / benchmarkByDate.get(from.date)),
    })
  }
  return intervals
}

/**
 * Collapses aligned intervals onto calendar-month boundaries, using the last observation in
 * each month. Frequency-sensitive measures (a hit rate, most obviously) are meaningless
 * without a stated cadence: "beat the index in 8 of 12 months" is a fact a person can hold,
 * while "beat it on 53% of observations" depends entirely on how often the series was
 * sampled.
 */
export function monthlyReturns(intervals) {
  if (!intervals?.length) return []
  const byMonth = new Map()
  intervals.forEach((interval) => {
    const month = interval.endDate.slice(0, 7)
    const existing = byMonth.get(month)
    if (!existing) {
      byMonth.set(month, { month, portfolio: interval.portfolio, benchmark: interval.benchmark })
      return
    }
    existing.portfolio += interval.portfolio
    existing.benchmark += interval.benchmark
  })
  // The first and last calendar months are usually partial. A partial month is still a real
  // comparison over a real span - both legs cover the identical days - so they are kept.
  return [...byMonth.values()].sort((left, right) => left.month.localeCompare(right.month))
}
