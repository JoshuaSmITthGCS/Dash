/**
 * Portfolio performance measured against the only benchmark that matters to the question
 * "should I have just bought the index?" – the same dollars, invested the same day, in the S&P 500.
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
 * Uses the last stored account valuation on each market date as the recorded-value series.
 * Settled external flows are attached to the covered window so the UI can distinguish this
 * observed account path from a backtest that applies today's shares to old closes.
 */
export function actualRecordedValueSeries(snapshots = [], transactions = []) {
  const byDate = new Map()
  snapshots.filter((row) => (row?.marketDate || row?.recordedAt) && Number.isFinite(Number(row.value)))
    .sort((left, right) => String(left.recordedAt || '').localeCompare(String(right.recordedAt || '')))
    .forEach((row) => byDate.set(row.marketDate || String(row.recordedAt).slice(0, 10), Number(row.value)))
  const rows = [...byDate.entries()].sort((left, right) => left[0].localeCompare(right[0]))
  if (rows.length < 2) return null
  const startDate = rows[0][0]
  const endDate = rows.at(-1)[0]
  const settledFlows = transactions.filter((row) => {
    const date = row.effectiveDate || row.date
    return ['deposit', 'external_contribution', 'withdrawal'].includes(row.type)
      && date >= startDate
      && date <= endDate
      && !['pending', 'processing'].includes(row.status)
      && Number.isFinite(Number(row.amount))
  })
  return {
    dates: rows.map(([date]) => date),
    values: rows.map(([, value]) => value),
    settledFlows,
    methodology: `Actual account values recorded in Firestore. ${settledFlows.length} settled external cash flow${settledFlows.length === 1 ? '' : 's'} falls inside this window.`,
  }
}

const average = (values) => values.reduce((sum, value) => sum + value, 0) / values.length

function weekStart(dateText) {
  const date = new Date(`${dateText}T00:00:00Z`)
  const weekday = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() - weekday + 1)
  return date.toISOString().slice(0, 10)
}

function averageGroups(rows, keyForRow) {
  const groups = new Map()
  for (const row of rows) {
    const key = keyForRow(row)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(row.value)
  }
  return [...groups].sort(([left], [right]) => left.localeCompare(right))
    .map(([date, values]) => ({ date, value: average(values) }))
}

function trailingCalendarDays(rows, days) {
  if (!rows.length) return []
  const end = Date.parse(rows.at(-1).date)
  const cutoff = end - days * 24 * 60 * 60 * 1000
  return rows.filter((row) => Date.parse(row.date) >= cutoff)
}

/**
 * Display-resolution hierarchy for the cloud snapshot chart. Raw observations are never
 * overwritten: Today shows every five-minute point, Week and Month give each market day one
 * averaged point, 3 Months gives each week one point, and Year gives each month one point.
 * Weekly/monthly values average the daily averages, so a day with an extra retry never receives
 * more weight merely because it has more stored observations.
 */
export function recordedValueSeriesForPeriod(snapshots = [], period = '1D') {
  const rows = snapshots
    .filter((row) => row?.recordedAt && Number.isFinite(Number(row.value)))
    .map((row) => ({
      recordedAt: row.recordedAt,
      marketDate: row.marketDate || String(row.recordedAt).slice(0, 10),
      value: Number(row.value),
    }))
    .sort((left, right) => String(left.recordedAt).localeCompare(String(right.recordedAt)))
  if (!rows.length) return null

  if (period === '1D') {
    const latestDate = rows.at(-1).marketDate
    const points = rows.filter((row) => row.marketDate === latestDate)
    if (points.length < 2) return null
    return {
      dates: points.map((row) => row.recordedAt),
      values: points.map((row) => row.value),
      frequency: 'five-minute',
      source: 'firestore_portfolio_snapshots',
      methodology: `${points.length} five-minute account-value observations recorded during ${latestDate}.`,
    }
  }

  const daily = averageGroups(rows, (row) => row.marketDate)
  let points
  let frequency
  let methodology
  if (period === '1W') {
    points = trailingCalendarDays(daily, 7)
    frequency = 'daily-average'
    methodology = 'Each point is the average of that trading day’s five-minute portfolio recordings during the trailing week.'
  } else if (period === '1M') {
    points = trailingCalendarDays(daily, 31)
    frequency = 'daily-average'
    methodology = 'Each point is the average of that trading day’s five-minute portfolio recordings during the trailing month.'
  } else if (period === '3M') {
    const trailing = trailingCalendarDays(daily, 93)
    points = averageGroups(trailing.map((row) => ({ ...row, marketDate: row.date })), (row) => weekStart(row.marketDate))
    frequency = 'weekly-average'
    methodology = 'Each point averages the daily portfolio values within that market week during the trailing three months.'
  } else if (period === '1Y') {
    const trailing = trailingCalendarDays(daily, 366)
    points = averageGroups(trailing.map((row) => ({ ...row, marketDate: row.date })), (row) => `${row.marketDate.slice(0, 7)}-01`)
    frequency = 'monthly-average'
    methodology = 'Each point averages the daily portfolio values within that month during the trailing year.'
  } else {
    return null
  }
  if (points.length < 2) return null
  return {
    dates: points.map((row) => row.date),
    values: points.map((row) => row.value),
    frequency,
    source: 'firestore_portfolio_snapshots',
    methodology,
  }
}

/**
 * Every stored observation from the latest market date, preserving its timestamp instead of
 * collapsing the day to one close. This is display-only intraday account value: external cash
 * flows and trading activity can move the line as well as prices, so it is never substituted
 * into return statistics.
 */
export function intradayRecordedValueSeries(snapshots = []) {
  const series = recordedValueSeriesForPeriod(snapshots, '1D')
  return series ? { ...series, frequency: 'intraday' } : null
}

export const PORTFOLIO_HISTORY_LABELS = {
  actual: 'Your actual recorded value',
  backtest: "Today's basket, backtested",
}

/**
 * Chooses the historical series with the most observations until the user overrides it.
 * Keeping the rule here makes the default deterministic and testable across desktop and mobile.
 */
export function selectPortfolioHistorySeries(backtestedSeries, actualSeries, requestedMode = null) {
  const seriesByMode = { backtest: backtestedSeries, actual: actualSeries }
  const backtestObservations = backtestedSeries?.dates?.length || 0
  const actualObservations = actualSeries?.dates?.length || 0
  const requestedSeries = seriesByMode[requestedMode]
  const mode = requestedSeries
    ? requestedMode
    : actualObservations > backtestObservations
      ? 'actual'
      : backtestObservations
        ? 'backtest'
        : actualObservations
          ? 'actual'
          : 'backtest'
  const selectedSeries = seriesByMode[mode] || null
  const selectedObservations = selectedSeries?.dates?.length || 0
  const defaultReason = actualObservations === backtestObservations
    ? 'both series have equal observation coverage and the backtested view is the tie breaker'
    : 'it has the greater available observation coverage'
  const note = requestedSeries
    ? `Showing ${PORTFOLIO_HISTORY_LABELS[mode]} by your selection. ${selectedObservations} observations are available.`
    : `Defaulted to ${PORTFOLIO_HISTORY_LABELS[mode]} because ${defaultReason}. ${selectedObservations} observations are available.`
  return {
    mode,
    series: selectedSeries,
    selectedObservations,
    observations: { actual: actualObservations, backtest: backtestObservations },
    defaulted: !requestedSeries,
    note,
  }
}

/** Last usable close at or before a date for any aligned price history. */
export function closeOnDates(dates, closes, date) {
  const target = String(date || '').slice(0, 10)
  let match = null
  for (let index = 0; index < dates.length; index += 1) {
    if (dates[index] <= target && Number.isFinite(closes[index])) match = closes[index]
  }
  return match
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
 * What a fixed dollar amount – not what was actually invested – would be worth today if it had
 * gone into this position's stock, and separately into the S&P 500, both on its purchase date.
 * Answers "if I'd put the same $X into every pick on the day I actually bought it, how did
 * picking this stock do against just buying the index?" rather than reporting real dollars.
 */
export function fixedBasisAlternative(position, stockHistory, benchmarkHistory, basis = 500) {
  const purchaseDate = String(position.purchaseDate || '').slice(0, 10)
  if (!purchaseDate) return null
  const stockDates = stockHistory?.dates || []
  const stockCloses = stockHistory?.closes || []
  const stockEntry = closeOnDates(stockDates, stockCloses, purchaseDate)
  const stockNow = closeOnDates(stockDates, stockCloses, stockDates[stockDates.length - 1])
  const benchmarkEntry = benchmarkCloseOn(benchmarkHistory, purchaseDate)
  const benchmarkNow = latestBenchmarkClose(benchmarkHistory)
  if (!stockEntry || !stockNow || !benchmarkEntry || !benchmarkNow) return null
  const stockValue = (basis / stockEntry) * stockNow
  const benchmarkValue = (basis / benchmarkEntry) * benchmarkNow
  return {
    basis,
    purchaseDate,
    stockValue,
    benchmarkValue,
    stockReturnPct: (stockValue / basis - 1) * 100,
    benchmarkReturnPct: (benchmarkValue / basis - 1) * 100,
    dollarsAhead: stockValue - benchmarkValue,
  }
}

/** Portfolio-wide totals for the fixed-basis calculator: the same $X on each position's own purchase day. */
export function portfolioFixedBasisVsBenchmark(positions, priceData, benchmarkHistory, basis = 500) {
  let stock = 0
  let benchmark = 0
  let comparable = 0
  for (const position of positions) {
    const alternative = fixedBasisAlternative(position, priceData[position.ticker]?.history, benchmarkHistory, basis)
    if (!alternative) continue
    comparable += 1
    stock += alternative.stockValue
    benchmark += alternative.benchmarkValue
  }
  if (!comparable) return null
  const invested = comparable * basis
  return {
    comparable,
    invested,
    stockValue: stock,
    benchmarkValue: benchmark,
    dollarsAhead: stock - benchmark,
    stockReturnPct: (stock / invested - 1) * 100,
    benchmarkReturnPct: (benchmark / invested - 1) * 100,
  }
}

/**
 * Growth-of-$X series for a single position from its purchase date forward, for the stock and
 * the benchmark side by side. Unlike `portfolioGrowthSeries`, this draws one position starting
 * at its own purchase date rather than the whole portfolio from its earliest one.
 */
export function positionGrowthSeries(position, stockHistory, benchmarkHistory, basis = 500) {
  const dates = benchmarkHistory?.dates || []
  const benchmarkCloses = benchmarkHistory?.closes || []
  const stockCloses = stockHistory?.closes || []
  const purchaseDate = String(position.purchaseDate || '').slice(0, 10)
  if (!purchaseDate || dates.length < 2 || stockCloses.length !== dates.length) return null
  const activationIndex = dates.findIndex((date) => date >= purchaseDate)
  const stockEntry = closeOnDates(dates, stockCloses, purchaseDate)
  const benchmarkEntry = benchmarkCloseOn(benchmarkHistory, purchaseDate)
  if (activationIndex < 0 || !stockEntry || !benchmarkEntry) return null
  return {
    dates: dates.slice(activationIndex),
    stock: stockCloses.slice(activationIndex).map((close) =>
      Number.isFinite(close) ? (basis / stockEntry) * close : null),
    benchmark: benchmarkCloses.slice(activationIndex).map((close) =>
      Number.isFinite(close) ? (basis / benchmarkEntry) * close : null),
  }
}

/**
 * Three aligned series for the comparison chart: the market value of what is actually held,
 * the value of identical contributions tracking the index, and those contributions held as cash.
 *
 * Each position enters on its recorded purchase date. This intentionally produces jumps when
 * several positions were purchased together: hiding those cash flows would overstate or
 * understate performance.
 */
export function portfolioGrowthSeries(positions, priceData, history) {
  const dates = history?.dates || []
  const benchmarkCloses = history?.closes || []
  if (dates.length < 2) return null

  const tracked = positions.flatMap((position) => {
    const stockHistory = priceData[position.ticker]?.history
    const closes = stockHistory?.closes
    const stockDates = stockHistory?.dates || dates
    const purchaseDate = String(position.purchaseDate || '').slice(0, 10)
    const activationIndex = dates.findIndex((date) => date >= purchaseDate)
    const benchmarkEntry = benchmarkCloseOn(history, purchaseDate)
    const stockEntry = closeOnDates(stockDates, closes || [], purchaseDate)
    const invested = Number(position.shares) * Number(position.costBasis)
    if (
      !purchaseDate
      || activationIndex < 0
      || closes?.length !== dates.length
      || !benchmarkEntry
      || !stockEntry
      || !Number.isFinite(invested)
      || invested <= 0
    ) return []
    return [{
      ...position,
      closes,
      purchaseDate,
      activationIndex,
      benchmarkEntry,
      stockEntry,
      invested,
    }]
  })
  if (!tracked.length) return null

  const holdings = dates.map((_, index) => {
    let total = 0
    let active = 0
    for (const position of tracked) {
      if (index < position.activationIndex) continue
      const close = position.closes[index]
      if (!Number.isFinite(close)) return null
      total += (position.invested / position.stockEntry) * close
      active += 1
    }
    return active ? total : null
  })

  const benchmark = dates.map((_, index) => {
    const close = benchmarkCloses[index]
    if (!Number.isFinite(close)) return null
    const active = tracked.filter((position) => index >= position.activationIndex)
    if (!active.length) return null
    return active.reduce(
      (total, position) => total + (position.invested / position.benchmarkEntry) * close,
      0
    )
  })

  const cash = dates.map((_, index) => {
    const active = tracked.filter((position) => index >= position.activationIndex)
    return active.length
      ? active.reduce((total, position) => total + position.invested, 0)
      : null
  })
  const firstActiveIndex = Math.min(...tracked.map((position) => position.activationIndex))

  return {
    dates: dates.slice(firstActiveIndex),
    holdings: holdings.slice(firstActiveIndex),
    benchmark: benchmark.slice(firstActiveIndex),
    cash: cash.slice(firstActiveIndex),
    trackedTickers: tracked.map((position) => position.ticker),
    untrackedCount: positions.length - tracked.length,
    firstInvestmentDate: tracked
      .map((position) => position.purchaseDate)
      .sort()[0],
  }
}
