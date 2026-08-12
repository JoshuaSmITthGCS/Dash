import modelSettings from '../../pipeline/config/settings.json'

const PERIOD_DAYS = { '1D': 2, '1W': 7, '1M': 31, '3M': 93, '6M': 186, YTD: 'year-to-date', '1Y': 366, All: null }
const analyticsConfig = modelSettings.portfolio_analytics

const finite = (value) => value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))
const clamp = (value, min = 0, max = 100) => Math.max(min, Math.min(max, value))

export const BENCHMARKS = [
  { symbol: 'SPY', label: 'S&P 500', proxy: true, index: 'S&P 500 Index' },
  { symbol: 'QQQ', label: 'Nasdaq-100', proxy: true, index: 'Nasdaq-100 Index' },
  { symbol: 'DIA', label: 'Dow Jones', proxy: true, index: 'Dow Jones Industrial Average' },
  { symbol: 'IWM', label: 'Russell 2000', proxy: true, index: 'Russell 2000 Index' },
  { symbol: 'VTI', label: 'U.S. total market', proxy: true, index: 'CRSP U.S. Total Market Index' },
  { symbol: 'VEA', label: 'Developed ex-U.S.', proxy: true, index: 'FTSE Developed ex U.S. Index' },
  { symbol: 'VWO', label: 'Emerging markets', proxy: true, index: 'FTSE Emerging Markets Index' },
  { symbol: 'VXUS', label: 'Global ex-U.S.', proxy: true, index: 'FTSE Global All Cap ex U.S. Index' },
]

export function benchmarkHistoryFromSnapshot(snapshot) {
  const rows = snapshot?.price_series?.fund
  if (!Array.isArray(rows)) return null
  const usable = rows.filter((row) => row?.date && finite(row.adjusted_close))
  if (usable.length < 2) return null
  return { dates: usable.map((row) => row.date), closes: usable.map((row) => Number(row.adjusted_close)), source: snapshot.benchmark, symbol: snapshot.ticker }
}

export function enrichPortfolio(positions = [], priceData = {}) {
  const enriched = positions.map((position) => {
    const ticker = String(position.ticker || '').trim().toUpperCase()
    const source = priceData[ticker]
    const shares = Number(position.shares)
    const costBasis = Number(position.costBasis)
    const currentPrice = finite(source?.price) ? Number(source.price) : finite(position.snapshotPrice) ? Number(position.snapshotPrice) : null
    const totalCost = finite(shares) && finite(costBasis) ? shares * costBasis : null
    const currentValue = currentPrice == null || !finite(shares) ? null : shares * currentPrice
    const gain = currentValue == null || totalCost == null ? null : currentValue - totalCost
    return { ...position, ticker, shares, costBasis, currentPrice, totalCost, currentValue, gain, gainPct: totalCost > 0 && gain != null ? gain / totalCost * 100 : null, allocationPct: null, priceInfo: source }
  })
  const totalValue = enriched.reduce((sum, row) => sum + (row.currentValue || 0), 0)
  const totalCost = enriched.reduce((sum, row) => sum + (row.totalCost || 0), 0)
  const priced = enriched.filter((row) => row.currentValue != null).length
  return {
    positions: enriched.map((row) => ({ ...row, allocationPct: totalValue > 0 && row.currentValue != null ? row.currentValue / totalValue * 100 : null })),
    totalValue: priced ? totalValue : null,
    totalCost: enriched.some((row) => row.totalCost != null) ? totalCost : null,
    gain: priced && totalCost > 0 ? totalValue - totalCost : null,
    gainPct: priced && totalCost > 0 ? (totalValue - totalCost) / totalCost * 100 : null,
    coveragePct: positions.length ? priced / positions.length * 100 : 0,
  }
}

function closeMap(history) {
  return new Map((history?.dates || []).map((date, index) => [date, history.closes?.[index]]).filter(([, value]) => finite(value)))
}

export function currentHoldingsSeries(positions = [], priceData = {}, anchorDates = []) {
  const dated = anchorDates.length ? anchorDates : [...new Set(positions.flatMap((position) => priceData[position.ticker]?.history?.dates || []))].sort()
  const tracked = positions.map((position) => ({ position, prices: closeMap(priceData[position.ticker]?.history) })).filter((row) => row.prices.size && finite(row.position.shares))
  if (!tracked.length || dated.length < 2) return null
  const rows = dated.map((date) => {
    let value = 0
    let covered = 0
    tracked.forEach(({ position, prices }) => { const price = prices.get(date); if (finite(price)) { value += Number(position.shares) * Number(price); covered += 1 } })
    return covered === tracked.length ? { date, value, coveragePct: positions.length ? covered / positions.length * 100 : 0 } : null
  }).filter(Boolean)
  if (rows.length < 2) return null
  return { dates: rows.map((row) => row.date), values: rows.map((row) => row.value), coverage: rows.map((row) => row.coveragePct), methodology: 'Current quantities applied to historical daily closes. This is not actual historical account value.' }
}

/** Drops every observation before cutoffDate, keeping a series' own shape intact. Used to let
 * risk/performance stats be evaluated only since a given date (e.g. when live tracking
 * actually started), instead of over the full backtested-basket history. */
export function sliceSeriesFrom(series, cutoffDate) {
  if (!series?.dates?.length || !cutoffDate) return series
  const startIndex = series.dates.findIndex((date) => date >= cutoffDate)
  if (startIndex < 0) return null
  return {
    ...series,
    dates: series.dates.slice(startIndex),
    values: series.values ? series.values.slice(startIndex) : undefined,
    coverage: series.coverage ? series.coverage.slice(startIndex) : undefined,
  }
}

export function selectPeriod(series, period = '1M') {
  if (!series?.dates?.length || !series?.values?.length) return null
  const days = PERIOD_DAYS[period] ?? null
  const endMs = Date.parse(series.dates.at(-1))
  const yearStart = `${String(series.dates.at(-1)).slice(0, 4)}-01-01`
  const foundIndex = days === 'year-to-date'
    ? series.dates.findIndex((date) => date >= yearStart)
    : days == null ? 0 : series.dates.findIndex((date) => Date.parse(date) >= endMs - days * 86400000)
  const startIndex = days == null ? 0 : foundIndex < 0 ? Math.max(0, series.dates.length - 2) : foundIndex
  const dates = series.dates.slice(startIndex)
  const values = series.values.slice(startIndex)
  if (values.length < 2) return null
  const start = values[0]
  const end = values.at(-1)
  const dollarReturn = end - start
  return { period, dates, values, startDate: dates[0], endDate: dates.at(-1), startValue: start, endValue: end, dollarReturn, returnPct: start ? dollarReturn / start * 100 : null, high: Math.max(...values), low: Math.min(...values), coveragePct: series.coverage?.slice(startIndex).reduce((sum, value) => sum + value, 0) / values.length || null, methodology: series.methodology }
}

export function latestMarketDayReturn(series) {
  if (!series?.values || series.values.length < 2) return null
  const previous = series.values.at(-2)
  const current = series.values.at(-1)
  return { date: series.dates.at(-1), previousDate: series.dates.at(-2), dollarReturn: current - previous, returnPct: previous ? (current - previous) / previous * 100 : null, currentValue: current }
}

export function alignSeries(left, right, period = left?.period || right?.period || 'All') {
  if (!left?.dates?.length || !right?.dates?.length) return null
  const rightValues = new Map(right.dates.map((date, index) => [date, right.values[index]]))
  const rows = left.dates.map((date, index) => ({ date, left: left.values[index], right: rightValues.get(date) })).filter((row) => finite(row.left) && finite(row.right))
  if (rows.length < 2) return null
  const make = (key) => selectPeriod({ dates: rows.map((row) => row.date), values: rows.map((row) => row[key]) }, 'All')
  return { dates: rows.map((row) => row.date), left: { ...make('left'), period }, right: { ...make('right'), period } }
}

/**
 * Put the portfolio and every selected benchmark on the same exact dates and starting
 * dollar value. The returned chart series and opportunity-cost figures therefore cannot
 * disagree: both are calculated from these same normalized observations.
 */
export function compareBenchmarkSeries(portfolioPeriod, benchmarkSeries = []) {
  if (!portfolioPeriod?.dates?.length || !portfolioPeriod?.values?.length) return null
  const usableBenchmarks = benchmarkSeries.filter((series) => series?.symbol && series?.dates?.length && (series.values?.length || series.closes?.length))
  if (!usableBenchmarks.length) return null
  const maps = usableBenchmarks.map((series) => ({
    ...series,
    valuesByDate: new Map(series.dates.map((date, index) => [date, (series.values || series.closes)[index]])),
  }))
  const rows = portfolioPeriod.dates.map((date, index) => ({
    date,
    portfolio: portfolioPeriod.values[index],
    benchmarks: maps.map((series) => series.valuesByDate.get(date)),
  })).filter((row) => finite(row.portfolio) && row.benchmarks.every(finite))
  if (rows.length < 2) return null
  const dates = rows.map((row) => row.date)
  const portfolioValues = rows.map((row) => Number(row.portfolio))
  const startingValue = portfolioValues[0]
  const portfolio = { ...selectPeriod({ dates, values: portfolioValues, methodology: portfolioPeriod.methodology }, 'All'), period: portfolioPeriod.period }
  const benchmarks = maps.map((series, benchmarkIndex) => {
    const raw = rows.map((row) => Number(row.benchmarks[benchmarkIndex]))
    const values = raw.map((value) => startingValue * value / raw[0])
    const period = selectPeriod({ dates, values }, 'All')
    return {
      symbol: series.symbol,
      label: series.label || series.symbol,
      dates,
      values,
      startValue: startingValue,
      endValue: period.endValue,
      returnPct: period.returnPct,
      period: portfolioPeriod.period,
      potentialEarnings: period.endValue - startingValue,
      differenceVsPortfolio: portfolio.endValue - period.endValue,
    }
  })
  return {
    dates,
    portfolio,
    benchmarks,
    startingValue,
    startDate: dates[0],
    endDate: dates.at(-1),
    methodology: 'Portfolio and selected ETF proxies use identical market dates and the same starting dollar value. Potential earnings are ending value minus that shared starting value.',
  }
}

export function intradayPortfolioHigh(points = []) {
  const usable = points.filter((point) => (point?.timestamp || point?.recordedAt) && finite(point.value))
  if (!usable.length) return null
  const high = usable.reduce((best, point) => Number(point.value) > Number(best.value) ? point : best)
  const current = Number(usable.at(-1).value)
  return { value: Number(high.value), timestamp: high.timestamp || high.recordedAt, belowHigh: Number(high.value) - current, observations: usable.length }
}

// 'external_contribution' is logged automatically when a new position is added and the
// purchase is flagged as funded by money outside the tracked account (see the Add Position
// form) -- it counts toward net invested capital exactly like a deposit, without touching
// the tracked uninvested-cash balance, since the money never sat in that bucket. Without
// this, buying a new holding outright looked identical to organic investment gain: the
// account's tracked value jumped by the purchase amount with no offsetting contribution, so
// Modified Dietz (and the contribution-adjusted gain below) credited the strategy for money
// that was simply deposited and immediately spent.
const CONTRIBUTION_TYPES = ['deposit', 'external_contribution']

export function netInvestedCapital(transactions) {
  if (!Array.isArray(transactions) || !transactions.length) return { available: false, value: null, reason: 'Complete contribution and withdrawal history is unavailable.' }
  const external = transactions.filter((row) => [...CONTRIBUTION_TYPES, 'withdrawal'].includes(row.type) && finite(row.amount) && !['pending', 'processing'].includes(row.status))
  if (!external.length || external.some((row) => !(row.effectiveDate || row.date))) return { available: false, value: null, reason: 'Complete dated external cash flows are unavailable.' }
  const deposits = external.filter((row) => CONTRIBUTION_TYPES.includes(row.type)).reduce((sum, row) => sum + Number(row.amount), 0)
  const withdrawals = external.filter((row) => row.type === 'withdrawal').reduce((sum, row) => sum + Number(row.amount), 0)
  return { available: true, value: deposits - withdrawals, deposits, withdrawals, count: external.length, reason: 'External deposits minus external withdrawals.' }
}

export function trailingCashFlowPace(transactions, endDate, historyComplete = false) {
  if (!historyComplete) return { available: false, netContributions: null, reason: 'Confirm the complete deposit and withdrawal history first.' }
  const end = Date.parse(endDate)
  if (!Number.isFinite(end)) return { available: false, netContributions: null, reason: 'A valid report date is required.' }
  const start = end - 365 * 86400000
  const rows = (transactions || []).filter((row) => {
    if (!['deposit', 'withdrawal'].includes(row.type) || !finite(row.amount) || ['pending', 'processing'].includes(row.status)) return false
    const date = Date.parse(row.effectiveDate || row.date)
    return Number.isFinite(date) && date >= start && date <= end
  })
  if (!rows.length) return { available: false, netContributions: null, reason: 'No settled external cash flows fall within the trailing year.' }
  const deposits = rows.filter((row) => row.type === 'deposit').reduce((sum, row) => sum + Number(row.amount), 0)
  const withdrawals = rows.filter((row) => row.type === 'withdrawal').reduce((sum, row) => sum + Number(row.amount), 0)
  return {
    available: true,
    deposits,
    withdrawals,
    netContributions: deposits - withdrawals,
    count: rows.length,
    startDate: new Date(start).toISOString().slice(0, 10),
    endDate,
    reason: 'Settled external deposits minus withdrawals over the trailing 365 days. Pending transfers are excluded.',
  }
}

export function contributionAdjustedPerformance(currentValue, transactions, historyComplete = false) {
  if (!historyComplete) return { available: false, value: null, returnPct: null, reason: 'Confirm the complete deposit and withdrawal history first.' }
  if (!finite(currentValue)) return { available: false, value: null, returnPct: null, reason: 'Current account value is unavailable.' }
  const capital = netInvestedCapital(transactions)
  if (!capital.available || capital.value <= 0) return { ...capital, available: false, returnPct: null }
  const value = Number(currentValue) - capital.value
  return {
    available: true,
    value,
    returnPct: value / capital.value * 100,
    netContributions: capital.value,
    deposits: capital.deposits,
    withdrawals: capital.withdrawals,
    count: capital.count,
    reason: 'Current account value minus net external contributions. The percentage is a simple contribution-adjusted return, not Fidelity’s time-weighted return.',
  }
}

function settledExternalFlows(transactions = [], startDate = null, endDate = null) {
  const start = startDate == null ? null : Date.parse(startDate)
  const end = endDate == null ? null : Date.parse(endDate)
  return transactions.filter((row) => {
    const date = Date.parse(row.effectiveDate || row.date)
    return [...CONTRIBUTION_TYPES, 'withdrawal'].includes(row.type)
      && finite(row.amount)
      && !['pending', 'processing'].includes(row.status)
      && Number.isFinite(date)
      && (start == null || date >= start)
      && (end == null || date <= end)
  }).map((row) => ({
    date: row.effectiveDate || row.date,
    amount: (CONTRIBUTION_TYPES.includes(row.type) ? 1 : -1) * Number(row.amount),
    type: row.type,
  })).sort((left, right) => left.date.localeCompare(right.date))
}

/**
 * Modified Dietz estimates strategy return without daily valuations:
 * R = (V1 - V0 - sum(CF_i)) / (V0 + sum(w_i * CF_i)), where
 * w_i is the fraction of the measurement period remaining after each external flow.
 * This removes deposit and withdrawal timing from the reported strategy result.
 */
export function modifiedDietzReturn(beginningValue, endingValue, transactions = [], startDate, endDate, historyComplete = false) {
  if (!historyComplete) return { available: false, returnPct: null, reason: 'Confirm the complete deposit and withdrawal history first.' }
  const start = Date.parse(startDate)
  const end = Date.parse(endDate)
  if (!finite(beginningValue) || !finite(endingValue) || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    return { available: false, returnPct: null, reason: 'Two dated account values are required for Modified Dietz.' }
  }
  const flows = settledExternalFlows(transactions, startDate, endDate)
  const duration = end - start
  const weightedFlows = flows.map((flow) => ({
    ...flow,
    weight: (end - Date.parse(flow.date)) / duration,
  }))
  const netExternalFlows = weightedFlows.reduce((sum, flow) => sum + flow.amount, 0)
  const denominator = Number(beginningValue) + weightedFlows.reduce((sum, flow) => sum + flow.weight * flow.amount, 0)
  if (!finite(denominator) || denominator <= 0) return { available: false, returnPct: null, reason: 'Weighted invested capital must be positive.' }
  const gain = Number(endingValue) - Number(beginningValue) - netExternalFlows
  return {
    available: true,
    returnPct: gain / denominator * 100,
    gain,
    beginningValue: Number(beginningValue),
    endingValue: Number(endingValue),
    netExternalFlows,
    weightedCapital: denominator,
    startDate,
    endDate,
    flowCount: weightedFlows.length,
    methodology: 'Modified Dietz weights each settled external cash flow by the fraction of the period it was invested.',
  }
}

function accountValueEndpoints(snapshots = []) {
  const byDay = new Map()
  snapshots.filter((row) => finite(row.value) && (row.recordedAt || row.marketDate))
    .sort((left, right) => String(left.recordedAt || '').localeCompare(String(right.recordedAt || '')))
    .forEach((row) => {
      const date = row.marketDate || String(row.recordedAt).slice(0, 10)
      byDay.set(date, { date, value: Number(row.value) })
    })
  const usable = [...byDay.values()].sort((left, right) => left.date.localeCompare(right.date))
  if (usable.length < 2) return null
  return { first: usable[0], last: usable.at(-1), observations: usable.length }
}

function xnpv(rate, flows) {
  const origin = Date.parse(flows[0].date)
  return flows.reduce((sum, flow) => sum + flow.amount / ((1 + rate) ** ((Date.parse(flow.date) - origin) / 31557600000)), 0)
}

function solveXirr(flows) {
  const spanDays = (Date.parse(flows.at(-1).date) - Date.parse(flows[0].date)) / 86400000
  if (spanDays < analyticsConfig.xirr_minimum_days) return { available: false, rate: null, spanDays, reason: `At least ${analyticsConfig.xirr_minimum_days} days are required for an annualized money-weighted return.` }
  let low = analyticsConfig.xirr_lower_bound
  let high = analyticsConfig.xirr_upper_bound
  let lowValue = xnpv(low, flows)
  const highValue = xnpv(high, flows)
  if (!finite(lowValue) || !finite(highValue) || lowValue * highValue > 0) return { available: false, rate: null, spanDays, reason: 'The dated cash flows do not produce a stable annualized return.' }
  for (let index = 0; index < analyticsConfig.xirr_max_iterations; index += 1) {
    const middle = (low + high) / 2
    const value = xnpv(middle, flows)
    if (Math.abs(value) < analyticsConfig.xirr_tolerance) { low = middle; high = middle; break }
    if (value * lowValue > 0) { low = middle; lowValue = value } else { high = middle }
  }
  return { available: true, rate: ((low + high) / 2) * 100, spanDays }
}

/**
 * XIRR solves NPV = 0 across beginning value, external flows, and ending value.
 * Unlike Modified Dietz, this intentionally includes the size and timing of the user's cash flows.
 */
export function moneyWeightedAccountReturn(snapshots = [], transactions = [], historyComplete = false) {
  if (!historyComplete) return { available: false, rate: null, reason: 'Confirm the complete deposit and withdrawal history first.' }
  const endpoints = accountValueEndpoints(snapshots)
  if (!endpoints) return { available: false, rate: null, reason: 'Two dated recorded account values are required.' }
  const startDate = endpoints.first.date
  const endDate = endpoints.last.date
  const external = settledExternalFlows(transactions, startDate, endDate)
  const flows = [
    { date: startDate, amount: -endpoints.first.value },
    ...external.map((flow) => ({ date: flow.date, amount: -flow.amount })),
    { date: endDate, amount: endpoints.last.value },
  ].sort((left, right) => left.date.localeCompare(right.date))
  const result = solveXirr(flows)
  return {
    ...result,
    startDate,
    endDate,
    observations: endpoints.observations,
    flowCount: external.length,
    methodology: result.available ? 'Annualized XIRR from recorded account values and settled external cash flows.' : undefined,
  }
}

/**
 * Converts a realized return over an arbitrary span into an annual rate: (1+r)^(365/days) - 1.
 * `minimumDays` rejects spans too short to extrapolate responsibly -- the same 30-day floor
 * used elsewhere in this file (see moneyWeightedAccountReturn/solveXirr) before a short
 * account history is stretched into an annual figure. A handful of days of noise compounded
 * to a full year produces a wildly overstated (or understated) rate.
 */
export function annualizeReturnPct(returnPct, startDate, endDate, minimumDays = 0) {
  const start = Date.parse(startDate)
  const end = Date.parse(endDate)
  if (!finite(returnPct) || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null
  const elapsedDays = (end - start) / 86400000
  if (elapsedDays < minimumDays) return null
  const growth = 1 + Number(returnPct) / 100
  if (growth <= 0) return null
  const annualized = growth ** (365 / elapsedDays) - 1
  return Number.isFinite(annualized) ? annualized * 100 : null
}

export function portfolioReturnSummary(snapshots = [], transactions = [], historyComplete = false) {
  const endpoints = accountValueEndpoints(snapshots)
  const strategy = endpoints
    ? modifiedDietzReturn(endpoints.first.value, endpoints.last.value, transactions, endpoints.first.date, endpoints.last.date, historyComplete)
    : { available: false, returnPct: null, reason: 'Two dated recorded account values are required.' }
  return {
    strategy,
    moneyWeighted: moneyWeightedAccountReturn(snapshots, transactions, historyComplete),
    explanation: 'Strategy return reduces the effect of cash-flow timing. Your return includes when deposits and withdrawals entered the account.',
  }
}

export function portfolioAnnualizedReturn(positions = [], endDate = new Date().toISOString().slice(0, 10)) {
  const allCurrentValue = positions.reduce((sum, row) => sum + (finite(row.currentValue) ? Number(row.currentValue) : 0), 0)
  const dated = positions.filter((row) => row.purchaseDate && row.purchaseDate <= endDate && finite(row.totalCost) && row.totalCost > 0 && finite(row.currentValue))
  const currentValue = dated.reduce((sum, row) => sum + Number(row.currentValue), 0)
  if (!dated.length || !currentValue) return { available: false, rate: null, reason: 'Dated cost basis and current values are required.' }
  const coveragePct = allCurrentValue > 0 ? currentValue / allCurrentValue * 100 : 0
  if (coveragePct < analyticsConfig.annualized_return_minimum_coverage_pct) return { available: false, rate: null, coveragePct, reason: `At least ${analyticsConfig.annualized_return_minimum_coverage_pct}% of current portfolio value needs a dated cost basis for a reliable annualized return.` }
  const flows = [...dated.map((row) => ({ date: row.purchaseDate, amount: -Number(row.totalCost) })), { date: endDate, amount: currentValue }].sort((a, b) => a.date.localeCompare(b.date))
  const spanDays = (Date.parse(endDate) - Date.parse(flows[0].date)) / 86400000
  if (spanDays < analyticsConfig.xirr_minimum_days) return { available: false, rate: null, reason: `At least ${analyticsConfig.xirr_minimum_days} days of dated holding history are required.` }
  const result = solveXirr(flows)
  return result.available
    ? { ...result, coveragePct, startDate: flows[0].date, endDate, methodology: 'Money-weighted annualized return for currently held positions using entered purchase dates, cost basis, and latest stored values.' }
    : result
}

export function trackedAllTimeEarnings(portfolio, activities = [], trackingState = null) {
  if (!trackingState?.trackingStartedAt) return { available: false, value: null, reason: 'Earnings tracking has not started.' }
  if (!trackingState.ledgerComplete) return { available: false, value: null, reason: `Activity is being stored from ${trackingState.trackingStartedAt.slice(0, 10)}, but the prior realized-gain, dividend, and fee history has not been confirmed complete.` }
  if (!finite(portfolio?.gain)) return { available: false, value: null, reason: 'Current unrealized gain is unavailable.' }
  const total = (type) => activities.filter((row) => row.type === type && finite(row.amount)).reduce((sum, row) => sum + Number(row.amount), 0)
  const components = { unrealized: Number(portfolio.gain), realized: total('realized_gain'), dividends: total('dividend'), fees: total('fee') }
  return { available: true, value: components.unrealized + components.realized + components.dividends - components.fees, components, reason: 'Current unrealized gain plus recorded realized gains and dividends, minus recorded fees.' }
}

function herfindahl(weights = []) {
  return weights.reduce((sum, weight) => sum + Number(weight) ** 2, 0)
}

function effectiveCount(weights = []) {
  const value = herfindahl(weights)
  return value > 0 ? 1 / value : null
}

/**
 * Converts HHI into a 0..100 breadth score through its reciprocal effective count.
 * Unlike linear penalties on the largest holding, this uses every portfolio weight and
 * reaches 100 at the configured effective-count target.
 */
function hhiBreadthScore(weights, target) {
  const count = effectiveCount(weights)
  if (count == null) return null
  return clamp((count - 1) / (target - 1) * 100)
}

function normalizeSectorWeights(raw) {
  if (!raw || typeof raw !== 'object') return null
  const rows = Object.entries(raw).filter(([, value]) => finite(value) && Number(value) > 0)
  if (!rows.length) return null
  const total = rows.reduce((sum, [, value]) => sum + Number(value), 0)
  return Object.fromEntries(rows.map(([label, value]) => [
    label.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()),
    Number(value) / total,
  ]))
}

function normalizeHoldingWeights(raw) {
  const rows = Array.isArray(raw)
    ? raw.map((row) => [row.ticker || row.symbol || row.holding_symbol, row.weight ?? row.pct ?? row.holding_percent])
    : Object.entries(raw || {})
  const usable = rows
    .map(([ticker, value]) => [String(ticker || '').toUpperCase(), Number(value)])
    .filter(([ticker, value]) => ticker && finite(value) && value > 0)
  if (!usable.length) return null
  const scale = usable.some(([, value]) => value > 1) ? 100 : 1
  return usable.map(([ticker, value]) => ({ ticker, weight: value / scale }))
}

/**
 * Decomposes each ETF allocation across its published sector weights before aggregating.
 * Missing fund exposures stay in one explicit unknown bucket and are flagged, rather than
 * being mislabeled as a standalone ETF sector that appears diversified.
 */
export function sectorLookThrough(positions = [], etfs = []) {
  const rows = Array.isArray(etfs) ? etfs : etfs?.etfs || []
  const byTicker = new Map(rows.map((row) => [String(row.ticker || '').toUpperCase(), row]))
  const total = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0)
    .reduce((sum, row) => sum + Number(row.currentValue), 0)
  if (!total) return { exposures: [], positionExposures: [], unavailableEtfs: [], unresolvedDollars: 0, coveragePct: 0 }
  const exposures = new Map()
  const positionExposures = new Map()
  const unavailableEtfs = []
  let unresolvedDollars = 0
  let coveredWeight = 0
  const add = (label, weight) => exposures.set(label, (exposures.get(label) || 0) + weight)
  const addPosition = (ticker, weight, source) => {
    const current = positionExposures.get(ticker) || { ticker, weight: 0, sources: [] }
    current.weight += weight
    if (!current.sources.includes(source)) current.sources.push(source)
    positionExposures.set(ticker, current)
  }
  positions.filter((row) => finite(row.currentValue) && row.currentValue > 0).forEach((position) => {
    const allocation = Number(position.currentValue) / total
    const ticker = String(position.ticker || '').toUpperCase()
    const etf = byTicker.get(ticker)
    if (!etf) {
      add(position.priceInfo?.sector || 'Unclassified', allocation)
      addPosition(ticker, allocation, 'direct')
      coveredWeight += allocation
      return
    }
    const sectorWeights = normalizeSectorWeights(etf.sector_weights)
    if (!sectorWeights) {
      add('ETF look-through unavailable', allocation)
      unavailableEtfs.push(ticker)
      unresolvedDollars += Number(position.currentValue)
      addPosition(`Unresolved ${ticker}`, allocation, ticker)
      return
    }
    Object.entries(sectorWeights).forEach(([sector, weight]) => add(sector, allocation * weight))
    const holdings = normalizeHoldingWeights(etf.top_holdings)
    if (holdings) {
      let disclosedWeight = 0
      holdings.forEach((holding) => {
        disclosedWeight += holding.weight
        addPosition(holding.ticker, allocation * holding.weight, ticker)
      })
      if (disclosedWeight < 1) addPosition(`Other ${ticker} holdings`, allocation * (1 - disclosedWeight), ticker)
    } else {
      addPosition(`Unresolved ${ticker}`, allocation, ticker)
    }
    coveredWeight += allocation
  })
  return {
    exposures: [...exposures.entries()].map(([label, weight]) => ({ label, pct: weight * 100 }))
      .sort((left, right) => right.pct - left.pct),
    unavailableEtfs,
    unresolvedDollars,
    positionExposures: [...positionExposures.values()].map((row) => ({
      ticker: row.ticker,
      pct: row.weight * 100,
      sources: row.sources,
    })).sort((left, right) => right.pct - left.pct),
    coveragePct: coveredWeight * 100,
  }
}

function returnMap(history) {
  const dates = history?.dates || []
  const closes = history?.closes || []
  const values = new Map()
  for (let index = 1; index < Math.min(dates.length, closes.length); index += 1) {
    if (!finite(closes[index]) || !finite(closes[index - 1]) || Number(closes[index - 1]) <= 0) continue
    values.set(dates[index], Number(closes[index]) / Number(closes[index - 1]) - 1)
  }
  return values
}

function mean(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function sampleDeviation(values) {
  if (values.length < 2) return null
  const average = mean(values)
  return Math.sqrt(values.reduce((sum, value) => sum + (value - average) ** 2, 0) / (values.length - 1))
}

function correlation(left, right) {
  const leftMean = mean(left)
  const rightMean = mean(right)
  const numerator = left.reduce((sum, value, index) => sum + (value - leftMean) * (right[index] - rightMean), 0)
  const leftScale = Math.sqrt(left.reduce((sum, value) => sum + (value - leftMean) ** 2, 0))
  const rightScale = Math.sqrt(right.reduce((sum, value) => sum + (value - rightMean) ** 2, 0))
  return leftScale && rightScale ? numerator / (leftScale * rightScale) : 0
}

function symmetricEigenvalues(input) {
  const matrix = input.map((row) => [...row])
  const size = matrix.length
  for (let iteration = 0; iteration < analyticsConfig.eigenvalue_max_iterations * size * size; iteration += 1) {
    let row = 0
    let column = 1
    let largest = 0
    for (let left = 0; left < size; left += 1) {
      for (let right = left + 1; right < size; right += 1) {
        if (Math.abs(matrix[left][right]) > largest) {
          largest = Math.abs(matrix[left][right])
          row = left
          column = right
        }
      }
    }
    if (largest < analyticsConfig.eigenvalue_tolerance) break
    const angle = Math.atan2(2 * matrix[row][column], matrix[column][column] - matrix[row][row]) / 2
    const cosine = Math.cos(angle)
    const sine = Math.sin(angle)
    const rowDiagonal = matrix[row][row]
    const columnDiagonal = matrix[column][column]
    const offDiagonal = matrix[row][column]
    matrix[row][row] = cosine ** 2 * rowDiagonal - 2 * sine * cosine * offDiagonal + sine ** 2 * columnDiagonal
    matrix[column][column] = sine ** 2 * rowDiagonal + 2 * sine * cosine * offDiagonal + cosine ** 2 * columnDiagonal
    matrix[row][column] = 0
    matrix[column][row] = 0
    for (let index = 0; index < size; index += 1) {
      if (index === row || index === column) continue
      const first = matrix[index][row]
      const second = matrix[index][column]
      matrix[index][row] = cosine * first - sine * second
      matrix[row][index] = matrix[index][row]
      matrix[index][column] = sine * first + cosine * second
      matrix[column][index] = matrix[index][column]
    }
  }
  return matrix.map((row, index) => row[index])
}

/**
 * Builds a common-date trailing return matrix, then uses the eigenvalue concentration of
 * sqrt(W) * Corr * sqrt(W). Its reciprocal HHI is the effective number of independent bets.
 * Diversification ratio is weighted standalone volatility divided by portfolio volatility.
 */
/**
 * Ledoit-Wolf-style shrinkage of a sample covariance matrix toward a diagonal target
 * (variances kept, off-diagonal covariances pulled toward zero).
 *
 * correlationDiversification's covarianceMatrix is the raw sample estimate, which is noisy
 * and often near-singular for a portfolio with more holdings than return observations --
 * exactly the regime a portfolio-construction optimizer (research contract section 12) needs
 * a stable matrix for. `intensity` of 0 returns the sample matrix unchanged; 1 returns a pure
 * diagonal matrix (all cross-asset covariance zeroed). This is a fixed-intensity shrinkage,
 * not the data-driven optimal intensity Ledoit-Wolf's original estimator solves for -- that
 * would need enough return history to estimate reliably, which this portfolio-sized problem
 * (tens of holdings, hundreds of daily returns) usually does not have. 0.2 is a commonly used
 * moderate default in the shrinkage literature, not a fitted value for this dataset.
 */
export function shrinkCovarianceMatrix(covarianceMatrix, intensity = 0.2) {
  if (!Array.isArray(covarianceMatrix) || !covarianceMatrix.length) return covarianceMatrix
  const clampedIntensity = Math.max(0, Math.min(1, intensity))
  return covarianceMatrix.map((row, rowIndex) => row.map((value, columnIndex) => (
    rowIndex === columnIndex ? value : value * (1 - clampedIntensity)
  )))
}

export function correlationDiversification(positions = []) {
  const requestedTickers = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0).map((row) => row.ticker)
  let eligible = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0)
    .map((row) => ({ row, returns: returnMap(row.priceInfo?.history) }))
    .filter((item) => item.returns.size >= analyticsConfig.correlation_minimum_observations)
  while (eligible.length >= 2) {
    const commonDates = [...eligible[0].returns.keys()]
      .filter((date) => eligible.every((item) => item.returns.has(date)))
      .sort().slice(-analyticsConfig.correlation_lookback_days)
    if (commonDates.length >= analyticsConfig.correlation_minimum_observations) {
      const series = eligible.map((item) => commonDates.map((date) => item.returns.get(date)))
      const total = eligible.reduce((sum, item) => sum + Number(item.row.currentValue), 0)
      const weights = eligible.map((item) => Number(item.row.currentValue) / total)
      const matrix = series.map((left, leftIndex) => series.map((right, rightIndex) => leftIndex === rightIndex ? 1 : correlation(left, right)))
      const weightedMatrix = matrix.map((row, rowIndex) => row.map((value, columnIndex) => value * Math.sqrt(weights[rowIndex] * weights[columnIndex])))
      const eigenvalues = symmetricEigenvalues(weightedMatrix).map((value) => Math.max(0, value))
      const eigenTotal = eigenvalues.reduce((sum, value) => sum + value, 0)
      const normalizedEigenvalues = eigenvalues.map((value) => value / eigenTotal)
      const effectiveBets = Math.min(eligible.length, 1 / herfindahl(normalizedEigenvalues))
      const volatilities = series.map((values) => sampleDeviation(values) * Math.sqrt(analyticsConfig.trading_days_per_year))
      const portfolioVariance = weights.reduce((outer, leftWeight, leftIndex) => outer + weights.reduce(
        (inner, rightWeight, rightIndex) => inner + leftWeight * rightWeight * volatilities[leftIndex] * volatilities[rightIndex] * matrix[leftIndex][rightIndex],
        0,
      ), 0)
      const portfolioVolatility = Math.sqrt(Math.max(0, portfolioVariance))
      const weightedAverageVolatility = weights.reduce((sum, weight, index) => sum + weight * volatilities[index], 0)
      return {
        available: true,
        tickers: eligible.map((item) => item.row.ticker),
        observations: commonDates.length,
        matrix,
        covarianceMatrix: matrix.map((row, rowIndex) => row.map((value, columnIndex) => (
          value * volatilities[rowIndex] * volatilities[columnIndex]
        ))),
        dates: commonDates,
        returnSeries: series,
        weights,
        effectiveBets,
        diversificationRatio: portfolioVolatility > 0 ? weightedAverageVolatility / portfolioVolatility : null,
        portfolioVolatility: portfolioVolatility * 100,
        excludedTickers: requestedTickers.filter((ticker) => !eligible.some((item) => item.row.ticker === ticker)),
      }
    }
    eligible = eligible.slice().sort((left, right) => right.returns.size - left.returns.size).slice(0, -1)
  }
  return { available: false, effectiveBets: null, diversificationRatio: null, tickers: [], excludedTickers: requestedTickers, observations: 0, reason: `At least two holdings need ${analyticsConfig.correlation_minimum_observations} common daily returns.` }
}

function historicalExpectedShortfall(returns, confidence) {
  if (!returns.length) return null
  const tailCount = Math.max(1, Math.ceil(returns.length * (1 - confidence)))
  return mean([...returns].sort((left, right) => left - right).slice(0, tailCount)) * 100
}

function normalizedWeightMap(raw) {
  const entries = Array.isArray(raw)
    ? raw.map((row) => [row.ticker || row.symbol, row.weight ?? row.pct])
    : Object.entries(raw || {})
  const usable = entries.map(([ticker, value]) => [String(ticker || '').toUpperCase(), Number(value)])
    .filter(([ticker, value]) => ticker && finite(value) && value >= 0)
  if (!usable.length) return null
  const scale = usable.some(([, value]) => value > 1) ? 100 : 1
  return new Map(usable.map(([ticker, value]) => [ticker, value / scale]))
}

/**
 * Euler decomposition of annualized portfolio volatility, plus historical tail loss and
 * benchmark-relative measures. Risk contributions reconcile to 100% apart from rounding.
 */
export function portfolioRiskDecomposition(positions = [], options = {}) {
  const correlationResult = correlationDiversification(positions)
  if (!correlationResult.available) return { available: false, reason: correlationResult.reason, contributions: [] }
  const { covarianceMatrix, weights, returnSeries, dates, tickers } = correlationResult
  const covarianceTimesWeights = covarianceMatrix.map((row) => row.reduce(
    (sum, value, index) => sum + value * weights[index], 0,
  ))
  const variance = weights.reduce((sum, weight, index) => sum + weight * covarianceTimesWeights[index], 0)
  const volatility = Math.sqrt(Math.max(0, variance))
  const componentRisks = weights.map((weight, index) => (
    volatility > 0 ? weight * covarianceTimesWeights[index] / volatility : 0
  ))
  const componentTotal = componentRisks.reduce((sum, value) => sum + value, 0)
  const contributions = tickers.map((ticker, index) => ({
    ticker,
    weightPct: weights[index] * 100,
    marginalContributionToRiskPct: volatility > 0 ? covarianceTimesWeights[index] / volatility * 100 : 0,
    componentContributionToRiskPct: componentRisks[index] * 100,
    percentContributionToRisk: componentTotal ? componentRisks[index] / componentTotal * 100 : 0,
  })).sort((left, right) => right.percentContributionToRisk - left.percentContributionToRisk)
  const portfolioReturns = dates.map((_, dateIndex) => returnSeries.reduce(
    (sum, series, holdingIndex) => sum + weights[holdingIndex] * series[dateIndex], 0,
  ))

  let trackingErrorPct = null
  const benchmarkReturns = returnMap(options.benchmarkHistory)
  if (benchmarkReturns.size) {
    const activeReturns = dates.map((date, index) => (
      benchmarkReturns.has(date) ? portfolioReturns[index] - benchmarkReturns.get(date) : null
    )).filter(finite)
    if (activeReturns.length >= analyticsConfig.correlation_minimum_observations) {
      trackingErrorPct = sampleDeviation(activeReturns) * Math.sqrt(analyticsConfig.trading_days_per_year) * 100
    }
  }

  let activeSharePct = null
  const benchmarkWeights = normalizedWeightMap(options.benchmarkWeights)
  if (benchmarkWeights) {
    const lookThrough = sectorLookThrough(positions, options.etfs || [])
    const portfolioWeights = new Map(lookThrough.positionExposures
      .filter((row) => !row.ticker.startsWith('Other ') && !row.ticker.startsWith('Unresolved '))
      .map((row) => [row.ticker, row.pct / 100]))
    const coveredPct = [...portfolioWeights.values()].reduce((sum, value) => sum + value, 0) * 100
    if (coveredPct >= analyticsConfig.active_share_minimum_coverage_pct) {
      const symbols = new Set([...portfolioWeights.keys(), ...benchmarkWeights.keys()])
      activeSharePct = [...symbols].reduce((sum, ticker) => (
        sum + Math.abs((portfolioWeights.get(ticker) || 0) - (benchmarkWeights.get(ticker) || 0))
      ), 0) * 50
    }
  }

  return {
    available: true,
    observations: dates.length,
    portfolioVolatilityPct: volatility * 100,
    expectedShortfall95Pct: historicalExpectedShortfall(portfolioReturns, analyticsConfig.expected_shortfall_confidence),
    trackingErrorPct,
    activeSharePct,
    contributions,
  }
}

export function diversificationScore(positions = [], options = {}) {
  const priced = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0)
  const total = priced.reduce((sum, row) => sum + Number(row.currentValue), 0)
  if (!total) return { available: false, score: null, coveragePct: 0, components: {}, warnings: [] }
  const weights = priced.map((row) => ({ ...row, pct: Number(row.currentValue) / total * 100 })).sort((a, b) => b.pct - a.pct)
  const fractions = weights.map((row) => row.pct / 100)
  const groupFractions = (field) => Object.values(weights.reduce((result, row) => {
    const key = row.priceInfo?.[field] || 'Unclassified'
    result[key] = (result[key] || 0) + row.pct / 100
    return result
  }, {})).sort((left, right) => right - left)
  const lookThrough = sectorLookThrough(priced, options.etfs || [])
  const sectorFractions = lookThrough.exposures.map((row) => row.pct / 100)
  const industryFractions = groupFractions('industry')
  const correlationResult = correlationDiversification(priced)
  const holdingHhi = herfindahl(fractions)
  const components = {
    holdingHhi: hhiBreadthScore(fractions, analyticsConfig.diversification_target_effective_holdings),
    sectorHhi: hhiBreadthScore(sectorFractions, analyticsConfig.diversification_target_effective_sectors),
    industryHhi: hhiBreadthScore(industryFractions, analyticsConfig.diversification_target_effective_industries),
    effectiveBets: correlationResult.available
      ? clamp((correlationResult.effectiveBets - 1) / (analyticsConfig.diversification_target_effective_holdings - 1) * 100)
      : null,
    diversificationRatio: correlationResult.available && correlationResult.diversificationRatio != null
      ? clamp((correlationResult.diversificationRatio - 1) / (analyticsConfig.diversification_ratio_target - 1) * 100)
      : null,
  }
  const availableComponents = Object.entries(components).filter(([, value]) => finite(value))
  const scoreWeights = analyticsConfig.diversification_score_weights
  const availableWeight = availableComponents.reduce((sum, [key]) => sum + scoreWeights[key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)], 0)
  const score = Math.round(availableComponents.reduce((sum, [key, value]) => sum + value * scoreWeights[key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)], 0) / availableWeight)
  const largest = weights[0]?.pct || 100
  const topFive = weights.slice(0, 5).reduce((sum, row) => sum + row.pct, 0)
  const largestSector = lookThrough.exposures[0]?.pct || 0
  const warnings = []
  if (largest > analyticsConfig.largest_holding_warning_pct) warnings.push(`Largest holding is ${largest.toFixed(1)}% of portfolio`)
  if (largestSector > analyticsConfig.largest_sector_warning_pct) warnings.push(`Largest look-through sector is ${largestSector.toFixed(1)}%`)
  if (topFive > analyticsConfig.top_five_warning_pct) warnings.push(`Top five positions represent ${topFive.toFixed(1)}%`)
  if (lookThrough.unavailableEtfs.length) warnings.push(`ETF look-through unavailable for ${lookThrough.unavailableEtfs.join(', ')}`)
  if (correlationResult.available && correlationResult.excludedTickers.length) warnings.push(`Correlation history unavailable for ${correlationResult.excludedTickers.join(', ')}`)
  return {
    available: true,
    score,
    coveragePct: priced.length / positions.length * 100,
    components,
    warnings,
    weights,
    sectors: sectorFractions.map((value) => value * 100),
    sectorExposures: lookThrough.exposures,
    industries: industryFractions.map((value) => value * 100),
    hhi: holdingHhi,
    effectiveHoldings: 1 / holdingHhi,
    rawHoldingCount: priced.length,
    effectiveBets: correlationResult.effectiveBets,
    diversificationRatio: correlationResult.diversificationRatio,
    correlation: correlationResult,
    lookThrough,
    provisional: priced.length < 5 || !correlationResult.available || correlationResult.excludedTickers.length > 0 || lookThrough.unavailableEtfs.length > 0,
  }
}

export function maximumDrawdown(values = []) { let peak = null; let worst = 0; values.filter(finite).forEach((raw) => { const value = Number(raw); peak = peak == null ? value : Math.max(peak, value); if (peak) worst = Math.min(worst, (value / peak - 1) * 100) }); return values.length > 1 ? worst : null }
/**
 * How long the portfolio has spent below its own high-water mark, in calendar days.
 *
 * maximumDrawdown answers how deep the hole was. It does not answer how long you were in
 * it, and those are different experiences of the same number: a 20% fall recovered in three
 * weeks and a 20% fall you sat underwater in for fourteen months are not the same portfolio
 * to hold. Duration is also the part people underestimate in advance and feel most acutely
 * at the time.
 *
 * Takes dates alongside values because the series is not guaranteed to be evenly spaced -
 * counting observations would report a ragged grid's sparse stretches as short ones.
 */
export function underwaterProfile(series) {
  const rows = (series?.dates || [])
    .map((date, index) => ({ date: String(date).slice(0, 10), value: Number(series.values?.[index]) }))
    .filter((row) => finite(row.value) && row.value > 0 && Number.isFinite(Date.parse(row.date)))
    .sort((left, right) => left.date.localeCompare(right.date))
  if (rows.length < 2) return { available: false, reason: 'Two dated portfolio values are required.' }

  const dayGap = (from, to) => Math.round((Date.parse(to) - Date.parse(from)) / 86400000)
  let peak = rows[0]
  let peakOfWorst = null
  let worst = 0
  let longestUnderwaterDays = 0
  let recoveryDaysForWorst = null
  let currentSpellStart = null

  rows.forEach((row) => {
    if (row.value >= peak.value) {
      if (currentSpellStart) {
        longestUnderwaterDays = Math.max(longestUnderwaterDays, dayGap(currentSpellStart.date, row.date))
        // Only the deepest fall's recovery time is reported; a portfolio has many small
        // dips and one of them being slow to mend is not the fact worth surfacing.
        if (peakOfWorst && currentSpellStart.date === peakOfWorst.date) {
          recoveryDaysForWorst = dayGap(currentSpellStart.date, row.date)
        }
        currentSpellStart = null
      }
      peak = row
      return
    }
    if (!currentSpellStart) currentSpellStart = peak
    const depth = (row.value / peak.value - 1) * 100
    if (depth < worst) {
      worst = depth
      peakOfWorst = peak
      recoveryDaysForWorst = null
    }
  })

  const last = rows.at(-1)
  const currentUnderwaterDays = currentSpellStart ? dayGap(currentSpellStart.date, last.date) : 0
  return {
    available: true,
    longestUnderwaterDays: Math.max(longestUnderwaterDays, currentUnderwaterDays),
    currentUnderwaterDays,
    currentDrawdownPct: (last.value / peak.value - 1) * 100,
    deepestDrawdownPct: worst,
    // Null while the deepest fall has not been recovered yet - which is itself the answer,
    // and must not be shown as a zero-day recovery.
    recoveryDaysForDeepest: recoveryDaysForWorst,
    stillUnderwater: Boolean(currentSpellStart),
    highWaterDate: peak.date,
    observations: rows.length,
    reason: null,
  }
}

export function annualizedVolatility(values = []) { const returns = values.slice(1).map((value, index) => finite(value) && finite(values[index]) && values[index] ? Number(value) / Number(values[index]) - 1 : null).filter(finite); if (returns.length < 2) return null; const mean = returns.reduce((a, b) => a + b, 0) / returns.length; const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1); return Math.sqrt(variance) * Math.sqrt(analyticsConfig.trading_days_per_year) * 100 }

export function resilienceIndex(values = [], diversification = null) {
  if (values.length < 20) return { available: false, score: null, provisional: true, coverage: values.length, reason: 'At least 20 daily observations are required.' }
  const drawdown = maximumDrawdown(values); const volatility = annualizedVolatility(values)
  const drawdownScore = clamp(100 + (drawdown || 0) * 2.5); const volatilityScore = clamp(100 - Math.max(0, (volatility || 0) - 10) * 2.2); const concentrationScore = diversification?.score ?? 50
  return { available: true, score: Math.round(drawdownScore * .45 + volatilityScore * .35 + concentrationScore * .2), provisional: values.length < 60, coverage: values.length, components: { drawdown: drawdownScore, downsideVolatility: volatilityScore, concentration: concentrationScore }, maxDrawdown: drawdown, volatility }
}

function periodReturns(values = []) {
  return values.slice(1).map((value, index) => finite(value) && finite(values[index]) && Number(values[index]) > 0
    ? Number(value) / Number(values[index]) - 1
    : null).filter(finite)
}

function annualizedGrowth(values, periods) {
  if (values.length < 2 || Number(values[0]) <= 0 || Number(values.at(-1)) <= 0 || periods <= 0) return null
  return ((Number(values.at(-1)) / Number(values[0])) ** (analyticsConfig.trading_days_per_year / periods) - 1) * 100
}

export function riskFreeAnnualRate(payload) {
  const selected = analyticsConfig.risk_free_series
  const reading = payload?.market?.macro?.regime?.risk_free_rates?.[selected]
  return {
    annualPct: finite(reading?.annual_percent) ? Number(reading.annual_percent) : analyticsConfig.risk_free_fallback_annual_pct,
    series: reading?.series_id || selected,
    asOf: reading?.as_of || null,
    fallback: !finite(reading?.annual_percent),
  }
}

/**
 * Reports standard return and risk measures directly. Sharpe uses the configured FRED
 * risk-free rate, Sortino uses downside deviation, Calmar divides annualized return by
 * maximum drawdown, and information ratio annualizes active return over tracking error.
 */
export function performanceMetrics(portfolioPeriod, benchmarkPeriod = null, riskFreeAnnualPct = analyticsConfig.risk_free_fallback_annual_pct) {
  if (!portfolioPeriod?.values?.length) return { available: false, score: null, reason: 'Portfolio return history is required.' }
  const portfolioReturns = periodReturns(portfolioPeriod.values)
  if (portfolioReturns.length < analyticsConfig.performance_minimum_observations) {
    return { available: false, score: null, observations: portfolioReturns.length, reason: `At least ${analyticsConfig.performance_minimum_observations} daily returns are required.` }
  }
  const riskFreeDaily = (1 + Number(riskFreeAnnualPct) / 100) ** (1 / analyticsConfig.trading_days_per_year) - 1
  const excess = portfolioReturns.map((value) => value - riskFreeDaily)
  const excessDeviation = sampleDeviation(excess)
  const downsideDeviation = Math.sqrt(mean(excess.map((value) => Math.min(0, value) ** 2)))
  const annualizedReturn = annualizedGrowth(portfolioPeriod.values, portfolioReturns.length)
  const maxDrawdown = maximumDrawdown(portfolioPeriod.values)
  const peak = Math.max(...portfolioPeriod.values.filter(finite).map(Number))
  const currentDrawdown = peak > 0 ? (Number(portfolioPeriod.values.at(-1)) / peak - 1) * 100 : null
  let informationRatio = null
  if (benchmarkPeriod?.values?.length === portfolioPeriod.values.length) {
    const benchmarkReturns = periodReturns(benchmarkPeriod.values)
    if (benchmarkReturns.length === portfolioReturns.length) {
      const active = portfolioReturns.map((value, index) => value - benchmarkReturns[index])
      const trackingError = sampleDeviation(active)
      informationRatio = trackingError ? mean(active) / trackingError * Math.sqrt(analyticsConfig.trading_days_per_year) : null
    }
  }
  const sharpe = excessDeviation ? mean(excess) / excessDeviation * Math.sqrt(analyticsConfig.trading_days_per_year) : null
  const sortino = downsideDeviation ? mean(excess) / downsideDeviation * Math.sqrt(analyticsConfig.trading_days_per_year) : null
  const calmar = annualizedReturn != null && maxDrawdown < 0 ? annualizedReturn / Math.abs(maxDrawdown) : null
  return {
    available: true,
    score: null,
    observations: portfolioReturns.length,
    sharpe,
    sortino,
    calmar,
    informationRatio,
    annualizedReturn,
    maxDrawdown,
    currentDrawdown,
    riskFreeAnnualPct: Number(riskFreeAnnualPct),
    period: portfolioPeriod.period,
    reason: informationRatio == null ? 'Benchmark information ratio is unavailable for this period.' : `Information ratio versus the selected benchmark is ${informationRatio.toFixed(2)}.`,
  }
}

export function concentrationLiquidityScore(positions = []) {
  const weighted = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0 && finite(row.allocationPct))
  if (!weighted.length) return { available: false, score: null, reason: 'Priced position weights are required.' }
  const liquid = weighted.filter((row) => finite(row.priceInfo?.average_dollar_volume) && row.priceInfo.average_dollar_volume > 0)
  const coveragePct = liquid.reduce((sum, row) => sum + row.allocationPct, 0)
  const largest = Math.max(...weighted.map((row) => row.allocationPct))
  const concentration = clamp(100 - Math.max(0, largest - 10) * 2.5)
  if (coveragePct < 80) return { available: true, score: Math.round(concentration), provisional: true, coveragePct, components: { concentration, liquidity: null }, reason: 'Liquidity coverage is below 80%, so this provisional component reflects concentration only.' }
  const liquidity = liquid.reduce((sum, row) => {
    const daysAtTenPctAdv = row.currentValue / (Number(row.priceInfo.average_dollar_volume) * .1)
    return sum + clamp(100 - Math.max(0, daysAtTenPctAdv - 1) * 12) * row.allocationPct / coveragePct
  }, 0)
  return { available: true, score: Math.round(concentration * .55 + liquidity * .45), coveragePct, components: { concentration, liquidity }, reason: 'Combines largest-position concentration with estimated days to liquidate at 10% of published average dollar volume.' }
}

export function opportunityCost(portfolioPeriod, benchmarkPeriod) {
  if (!portfolioPeriod || !benchmarkPeriod || !portfolioPeriod.startValue || !benchmarkPeriod.startValue) return null
  const benchmarkEndingValue = portfolioPeriod.startValue * (benchmarkPeriod.endValue / benchmarkPeriod.startValue)
  const difference = portfolioPeriod.endValue - benchmarkEndingValue
  return { portfolioEndingValue: portfolioPeriod.endValue, benchmarkEndingValue, difference, differencePct: benchmarkEndingValue ? difference / benchmarkEndingValue * 100 : null, startDate: portfolioPeriod.startDate > benchmarkPeriod.startDate ? portfolioPeriod.startDate : benchmarkPeriod.startDate, endDate: portfolioPeriod.endDate < benchmarkPeriod.endDate ? portfolioPeriod.endDate : benchmarkPeriod.endDate, methodology: 'Approximation from the earliest common date using current holdings and no external cash-flow adjustments.' }
}

export function portfolioScore({ diversification, resilience, performance, benchmarkEfficiency, concentrationLiquidity, dataCompleteness = 0 }) {
  if (!finite(diversification?.score)) return { available: false, score: null, provisional: false, reason: 'Priced position weights are required.' }
  const values = { diversification: diversification.score, resilience: resilience?.score, riskAdjustedPerformance: performance?.score, benchmarkEfficiency, concentrationLiquidity: concentrationLiquidity?.score, dataCompleteness }
  const weights = { diversification: .25, resilience: .25, riskAdjustedPerformance: .2, benchmarkEfficiency: .15, concentrationLiquidity: .1, dataCompleteness: .05 }
  const available = Object.entries(values).filter(([, value]) => finite(value))
  const availableWeight = available.reduce((sum, [key]) => sum + weights[key], 0)
  if (available.length < 3 || availableWeight <= 0) return { available: false, score: null, provisional: true, reason: 'At least three real portfolio components are required.' }
  const score = Math.round(available.reduce((sum, [key, value]) => sum + Number(value) * weights[key], 0) / availableWeight)
  const ranked = available.slice().sort((a, b) => b[1] - a[1])
  return { available: true, score, provisional: available.length < Object.keys(values).length || Boolean(diversification.provisional || resilience?.provisional || concentrationLiquidity?.provisional || dataCompleteness < 100), components: values, strongest: ranked[0][0], weakest: ranked.at(-1)[0], reason: available.length < Object.keys(values).length ? `Provisional score reweighted across ${available.length} available real-data components. Missing components are not treated as zero.` : 'All six components available.' }
}
