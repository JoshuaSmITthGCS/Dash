/**
 * Month-by-month view of a value series plus the cash flows around it, for the Performance
 * overview chart and its income card.
 *
 * Bars are each calendar month's change in the value series from the prior month's last close
 * (the first month in range starts at the range's first observation). Because the value series
 * reprices today's shares, these are time-weighted: a deposit never shows up as a gain.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DEPOSIT_TYPES = ['deposit', 'external_contribution']
const INCOME_TYPES = ['dividend', 'interest']
const settled = (row) => !['pending', 'processing'].includes(row?.status)
const activityDate = (row) => String(row?.effectiveDate || row?.date || '').slice(0, 10)
const amount = (row) => Number(row?.amount)

export const monthLabel = (month) => `${MONTHS[Number(month.slice(5, 7)) - 1]} '${month.slice(2, 4)}`

/** [{month, label, startDate, endDate, start, end, returnPct, change}] for each month in range. */
export function monthlyBars(series) {
  if (!series?.dates?.length || series.dates.length < 2) return []
  const bars = []
  let previousEnd = series.values[0]
  let previousDate = series.dates[0]
  let index = 0
  while (index < series.dates.length) {
    const month = series.dates[index].slice(0, 7)
    let last = index
    while (last + 1 < series.dates.length && series.dates[last + 1].startsWith(month)) last += 1
    const end = series.values[last]
    const startsAtRange = bars.length === 0
    // A one-observation first month has nothing to measure against.
    if (!(startsAtRange && last === index) && previousEnd > 0) {
      bars.push({
        month, label: monthLabel(month), startDate: previousDate, endDate: series.dates[last],
        start: previousEnd, end, returnPct: (end / previousEnd - 1) * 100, change: end - previousEnd,
      })
    }
    previousEnd = end
    previousDate = series.dates[last]
    index = last + 1
  }
  return bars
}

/** Settled external flows and income dated inside [startDate, endDate]. */
export function flowsBetween(activities, startDate, endDate) {
  const rows = (activities || []).filter((row) => {
    const date = activityDate(row)
    return settled(row) && Number.isFinite(amount(row)) && date && date > startDate && date <= endDate
  })
  const sum = (types) => rows.filter((row) => types.includes(row.type)).reduce((total, row) => total + amount(row), 0)
  const deposits = sum(DEPOSIT_TYPES)
  const withdrawals = sum(['withdrawal'])
  return { deposits, withdrawals, net: deposits - withdrawals, income: sum(INCOME_TYPES), count: rows.length }
}

/** Income received in each month of the range, oldest first, including empty months. */
export function monthlyIncome(activities, bars) {
  return bars.map((bar) => ({
    month: bar.month,
    label: bar.label,
    income: flowsBetween(activities, bar.startDate, bar.endDate).income,
  }))
}
