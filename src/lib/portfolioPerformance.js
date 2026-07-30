/**
 * Portfolio performance measured against the only benchmark that matters to the question
 * "should I have just bought the index?" — the same dollars, invested the same day, in the S&P 500.
 */

/** Last benchmark close at or before a date. Null when the date predates the charted window. */
export function benchmarkCloseOn(history, date) {
  const dates = history?.dates || []
  const closes = history?.closes || []
  if (!dates.length || !date) return null
  const target = String(date).slice(0, 10)
  let match = null
  for (let index = 0; index < dates.length; index += 1) {
    if (dates[index] <= target && closes[index] != null) match = closes[index]
  }
  return match
}

export function latestBenchmarkClose(history) {
  const closes = (history?.closes || []).filter((value) => value != null)
  return closes.length ? closes[closes.length - 1] : null
}

/**
 * What one position would be worth had the same money gone into the index on the same day.
 * Returns null when the purchase predates the published benchmark window, rather than
 * quietly comparing against the wrong entry price.
 */
export function benchmarkAlternative(position, history) {
  const entry = benchmarkCloseOn(history, position.purchaseDate)
  const now = latestBenchmarkClose(history)
  if (!entry || !now) return null
  const invested = position.shares * position.costBasis
  const value = (invested / entry) * now
  return {
    invested,
    value,
    gain: value - invested,
    gainPct: (value / invested - 1) * 100,
  }
}

/** Portfolio-wide holdings value against the index, position by position. */
export function portfolioVsBenchmark(positions, history) {
  let holdings = 0
  let benchmark = 0
  let invested = 0
  let comparable = 0
  for (const position of positions) {
    const alternative = benchmarkAlternative(position, history)
    if (!alternative) continue
    comparable += 1
    invested += alternative.invested
    benchmark += alternative.value
    holdings += position.currentValue
  }
  if (!comparable) return null
  return {
    comparable,
    invested,
    holdingsValue: holdings,
    benchmarkValue: benchmark,
    dollarsAhead: holdings - benchmark,
    holdingsReturnPct: (holdings / invested - 1) * 100,
    benchmarkReturnPct: (benchmark / invested - 1) * 100,
    excessReturnPct: ((holdings - benchmark) / invested) * 100,
  }
}

/**
 * Three aligned series for the comparison chart: the market value of what is actually held,
 * the value of the same starting dollars tracking the index, and those dollars left as cash.
 *
 * All three lines start from the portfolio's value at the beginning of the window, so the chart
 * answers "did these holdings beat the index over this period" without pretending to know
 * about contributions made mid-window.
 */
export function portfolioGrowthSeries(positions, priceData, history) {
  const dates = history?.dates || []
  const benchmarkCloses = history?.closes || []
  if (dates.length < 2) return null

  const tracked = positions.filter((position) => priceData[position.ticker]?.history?.closes?.length === dates.length)
  if (!tracked.length) return null

  const holdings = dates.map((_, index) => {
    let total = 0
    let priced = 0
    for (const position of tracked) {
      const close = priceData[position.ticker].history.closes[index]
      if (close == null) continue
      total += close * position.shares
      priced += 1
    }
    return priced ? total : null
  })

  const firstIndex = holdings.findIndex((value) => value != null)
  if (firstIndex < 0 || benchmarkCloses[firstIndex] == null) return null
  const basis = holdings[firstIndex]
  const benchmark = benchmarkCloses.map((close, index) => (
    close == null || index < firstIndex ? null : (basis / benchmarkCloses[firstIndex]) * close
  ))
  const cash = dates.map((_, index) => (index < firstIndex ? null : basis))

  return {
    dates,
    holdings,
    benchmark,
    cash,
    trackedTickers: tracked.map((position) => position.ticker),
    untrackedCount: positions.length - tracked.length,
  }
}
