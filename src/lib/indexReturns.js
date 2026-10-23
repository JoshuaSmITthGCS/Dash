/**
 * Trailing and calendar-period returns for the portfolio and a fixed set of market indexes,
 * on one shared "as of" close, in the layout of a brokerage "Total returns" table.
 *
 * Every figure is a price-series ratio of two closes, so a cash deposit never enters it: the
 * portfolio series reprices today's exact share counts at historical closes (see
 * currentHoldingsSeries), the same time-weighted construction the chart above uses. A period
 * that reaches back further than a series exists is null ("--"), never a shorter period
 * presented under the longer label.
 */

export const DAILY_COLUMNS = [
  { key: '1D', label: '1 Day' }, { key: 'MTD', label: 'MTD' }, { key: '1M', label: '1 Month' },
  { key: 'QTD', label: 'QTD' }, { key: '3M', label: '3 Month' }, { key: 'YTD', label: 'YTD' },
  { key: '1Y', label: '1 Year' }, { key: '3Y', label: '3 Year' }, { key: '5Y', label: '5 Year' },
  { key: '10Y', label: '10 Year' }, { key: 'LIFE', label: 'Life of available data' },
]
export const MONTHLY_COLUMNS = [
  { key: '1M', label: '1 Month' }, { key: '3M', label: '3 Month' }, { key: 'YTD', label: 'YTD' },
  { key: '1Y', label: '1 Year' }, { key: '3Y', label: '3 Year' }, { key: '5Y', label: '5 Year' },
  { key: '10Y', label: '10 Year' }, { key: 'LIFE', label: 'Life of available data' },
]

// Proxies for the stock/bond blends. The blend weights are the labelled stock share; the rest
// is the named bond proxy, rebalanced at every month-end.
export const INDEX_BLENDS = [
  { id: 'blend-100', label: 'Index Blend 100% Stocks (Taxable Bond)', stockWeight: 1, bond: 'AGG' },
  { id: 'blend-85-t', label: 'Index Blend 85% Stocks (Taxable Bond)', stockWeight: 0.85, bond: 'AGG' },
  { id: 'blend-70-t', label: 'Index Blend 70% Stocks (Taxable Bond)', stockWeight: 0.7, bond: 'AGG' },
  { id: 'blend-85-m', label: 'Index Blend 85% Stocks (Municipal Bond)', stockWeight: 0.85, bond: 'MUB' },
  { id: 'blend-70-m', label: 'Index Blend 70% Stocks (Municipal Bond)', stockWeight: 0.7, bond: 'MUB' },
  { id: 'blend-60-m', label: 'Index Blend 60% Stocks (Municipal Bond)', stockWeight: 0.6, bond: 'MUB' },
]
export const INDEX_ORDER = ['SPY', 'VTI', 'DIA', 'QQQ', 'ACWX', 'AGG', 'MUB', 'BIL']
const BLEND_STOCK_PROXY = 'VTI'

const DAY_MS = 86400000
const isDate = (value) => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
const utc = (date) => Date.parse(`${date}T00:00:00Z`)
const iso = (ms) => new Date(ms).toISOString().slice(0, 10)

function shiftMonths(date, months) {
  const d = new Date(utc(date))
  const day = d.getUTCDate()
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + months)
  const lastDay = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
  d.setUTCDate(Math.min(day, lastDay))
  return iso(d.getTime())
}

/** Last index with dates[index] <= date, or -1. */
function indexAtOrBefore(dates, date) {
  let low = 0
  let high = dates.length - 1
  let found = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    if (dates[mid] <= date) { found = mid; low = mid + 1 } else high = mid - 1
  }
  return found
}

/** Drops null closes so a series is {dates, values} with strictly usable observations. */
export function cleanSeries(dates, values) {
  const out = { dates: [], values: [] }
  ;(dates || []).forEach((date, index) => {
    const value = Number(values?.[index])
    if (isDate(date) && values?.[index] != null && Number.isFinite(value) && value > 0) {
      out.dates.push(date)
      out.values.push(value)
    }
  })
  return out.dates.length >= 2 ? out : null
}

/**
 * Stock/bond blend rebalanced at each month-end, as an indexed value series on the dates both
 * legs share. Null when either leg is missing.
 */
export function blendSeries(stock, bond, stockWeight) {
  if (!stock || !bond) return null
  const bondByDate = new Map(bond.dates.map((date, index) => [date, bond.values[index]]))
  const dates = []
  const values = []
  let previous = null
  let level = 100
  stock.dates.forEach((date, index) => {
    const bondValue = bondByDate.get(date)
    if (bondValue == null) return
    const stockValue = stock.values[index]
    if (previous) {
      const rebalanced = previous.month !== date.slice(0, 7)
      // Weights are reset at the first session of a new month, so the month's return uses
      // the target mix at that month's opening close.
      const weight = rebalanced || previous.weight == null ? stockWeight : previous.weight
      const stockGrowth = stockValue / previous.stock
      const bondGrowth = bondValue / previous.bond
      const growth = weight * stockGrowth + (1 - weight) * bondGrowth
      level *= growth
      previous = { month: date.slice(0, 7), stock: stockValue, bond: bondValue, weight: weight * stockGrowth / growth }
    } else {
      previous = { month: date.slice(0, 7), stock: stockValue, bond: bondValue, weight: stockWeight }
    }
    dates.push(date)
    values.push(level)
  })
  return dates.length >= 2 ? { dates, values } : null
}

/** Start date a period measures from, given the as-of close and the index trading calendar. */
export function periodStartDate(key, asOf, calendar) {
  switch (key) {
    case '1D': {
      const at = indexAtOrBefore(calendar, asOf)
      return at > 0 ? calendar[at - 1] : null
    }
    case 'MTD': return iso(utc(`${asOf.slice(0, 7)}-01`) - DAY_MS)
    case 'QTD': {
      const quarterMonth = Math.floor((Number(asOf.slice(5, 7)) - 1) / 3) * 3 + 1
      return iso(utc(`${asOf.slice(0, 4)}-${String(quarterMonth).padStart(2, '0')}-01`) - DAY_MS)
    }
    case 'YTD': return iso(utc(`${asOf.slice(0, 4)}-01-01`) - DAY_MS)
    case '1M': return shiftMonths(asOf, -1)
    case '3M': return shiftMonths(asOf, -3)
    case '1Y': return shiftMonths(asOf, -12)
    case '3Y': return shiftMonths(asOf, -36)
    case '5Y': return shiftMonths(asOf, -60)
    case '10Y': return shiftMonths(asOf, -120)
    default: return null
  }
}

/**
 * Return of one series between two dates. Null unless the series genuinely covers the start
 * (an observation on or before it) and the end. Windows over a year are annualised on request.
 */
export function returnBetween(series, startDate, endDate, { annualize = false } = {}) {
  if (!series || !isDate(startDate) || !isDate(endDate) || startDate >= endDate) return null
  const startIndex = indexAtOrBefore(series.dates, startDate)
  const endIndex = indexAtOrBefore(series.dates, endDate)
  if (startIndex < 0 || endIndex <= startIndex) return null
  const start = series.values[startIndex]
  const end = series.values[endIndex]
  if (!(start > 0) || !(end > 0)) return null
  const growth = end / start
  const days = (utc(series.dates[endIndex]) - utc(series.dates[startIndex])) / DAY_MS
  if (annualize && days > 366) return (growth ** (365.25 / days) - 1) * 100
  return (growth - 1) * 100
}

function lifeReturn(series, endDate, annualize) {
  if (!series) return null
  const startDate = series.dates[0]
  const pct = returnBetween(series, startDate, endDate, { annualize })
  return pct == null ? null : { pct, since: startDate }
}

/** Last session of the month before `asOf`'s month, on the index calendar. */
export function priorMonthEnd(calendar, asOf) {
  const monthStart = `${asOf.slice(0, 7)}-01`
  const at = indexAtOrBefore(calendar, iso(utc(monthStart) - DAY_MS))
  return at >= 0 ? calendar[at] : null
}

/**
 * The full table: one portfolio row plus every index/blend row, for the chosen frequency.
 *
 *  history      public/data/index-history.json
 *  portfolio    {dates, values} value series on any calendar (null when unavailable)
 *  frequency    'daily' | 'monthly' | 'custom'
 *  growth       'annualized' | 'cumulative'
 *  custom       {start, end} ISO dates, used when frequency is 'custom'
 */
export function buildReturnsTable({ history, portfolio, frequency = 'daily', growth = 'annualized', custom = null }) {
  const calendar = history?.dates
  if (!Array.isArray(calendar) || calendar.length < 2) return null
  const lastClose = history.as_of || calendar.at(-1)
  const annualize = growth === 'annualized'

  let asOf = lastClose
  let columns = DAILY_COLUMNS
  if (frequency === 'monthly') {
    asOf = priorMonthEnd(calendar, lastClose) || lastClose
    columns = MONTHLY_COLUMNS
  } else if (frequency === 'custom') {
    const start = custom?.start
    const end = custom?.end
    if (!isDate(start) || !isDate(end) || start >= end) return { asOf: lastClose, columns: [], rows: [], invalidCustom: true }
    asOf = end > lastClose ? lastClose : end
    columns = [{ key: 'CUSTOM', label: `${start} to ${asOf}` }]
  }

  const symbols = history.symbols || {}
  const series = {}
  for (const symbol of Object.keys(symbols)) series[symbol] = cleanSeries(calendar, symbols[symbol].closes)

  // A portfolio series that stops before the as-of close would be measured to an older date
  // than every index beside it, so it reads "--" rather than a quietly mismatched number.
  const portfolioCurrent = portfolio?.dates?.length && portfolio.dates.at(-1) >= asOf ? portfolio : null

  const rowDefs = []
  for (const blend of INDEX_BLENDS) {
    const values = blendSeries(series[BLEND_STOCK_PROXY], series[blend.bond], blend.stockWeight)
    if (values) rowDefs.push({ id: blend.id, label: blend.label, group: 'blend', series: values })
  }
  for (const symbol of INDEX_ORDER) {
    if (series[symbol]) rowDefs.push({ id: symbol, label: symbols[symbol].label, group: 'index', symbol, series: series[symbol] })
  }

  const valuesFor = (seriesValue, { lifeAllowed }) => {
    const out = {}
    if (!seriesValue) { for (const { key } of columns) out[key] = null; return out }
    for (const { key } of columns) {
      if (key === 'LIFE') {
        out.LIFE = lifeAllowed ? lifeReturn(seriesValue, asOf, annualize) : null
      } else if (key === 'CUSTOM') {
        const pct = returnBetween(seriesValue, custom.start, asOf)
        out.CUSTOM = pct == null ? null : { pct }
      } else {
        const start = periodStartDate(key, asOf, calendar)
        const pct = returnBetween(seriesValue, start, asOf, { annualize })
        out[key] = pct == null ? null : { pct }
      }
    }
    return out
  }

  return {
    asOf,
    lastClose,
    columns,
    portfolioStale: Boolean(portfolio) && !portfolioCurrent,
    portfolio: portfolio ? { id: 'portfolio', label: 'Your portfolio', values: valuesFor(portfolioCurrent, { lifeAllowed: true }) } : null,
    rows: rowDefs.map((row) => ({ id: row.id, label: row.label, group: row.group, symbol: row.symbol, values: valuesFor(row.series, { lifeAllowed: false }) })),
  }
}
