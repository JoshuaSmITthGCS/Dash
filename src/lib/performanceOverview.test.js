import { describe, expect, it } from 'vitest'
import { flowsBetween, monthlyBars, monthlyIncome, monthLabel } from './performanceOverview.js'

const series = {
  dates: ['2026-07-28', '2026-07-31', '2026-08-31', '2026-09-30', '2026-10-22'],
  values: [100, 102, 110, 99, 104],
}

describe('monthlyBars', () => {
  it('measures each month from the prior month-end and the first month from the range start', () => {
    const bars = monthlyBars(series)
    expect(bars.map((bar) => bar.label)).toEqual(["Jul '26", "Aug '26", "Sep '26", "Oct '26"])
    expect(bars[0].returnPct).toBeCloseTo(2, 6)
    expect(bars[1].returnPct).toBeCloseTo((110 / 102 - 1) * 100, 6)
    expect(bars[2].returnPct).toBeCloseTo((99 / 110 - 1) * 100, 6)
    expect(bars[3].end).toBe(104)
  })

  it('is empty without two observations', () => {
    expect(monthlyBars({ dates: ['2026-01-01'], values: [1] })).toEqual([])
    expect(monthlyBars(null)).toEqual([])
  })

  it('skips a first month that has a single observation', () => {
    const bars = monthlyBars({ dates: ['2026-07-31', '2026-08-15', '2026-08-31'], values: [100, 105, 110] })
    expect(bars.map((bar) => bar.month)).toEqual(['2026-08'])
    expect(bars[0].returnPct).toBeCloseTo(10, 6)
  })
})

describe('flows', () => {
  const activities = [
    { type: 'deposit', amount: 500, effectiveDate: '2026-08-05' },
    { type: 'withdrawal', amount: 100, effectiveDate: '2026-08-20' },
    { type: 'dividend', amount: 4.5, effectiveDate: '2026-09-10' },
    { type: 'deposit', amount: 999, effectiveDate: '2026-09-11', status: 'pending' },
    { type: 'stock_purchase', amount: 300, effectiveDate: '2026-09-12' },
  ]

  it('sums settled deposits, withdrawals and income inside the window only', () => {
    expect(flowsBetween(activities, '2026-07-31', '2026-10-22')).toMatchObject({ deposits: 500, withdrawals: 100, net: 400, income: 4.5 })
    expect(flowsBetween(activities, '2026-08-31', '2026-10-22').deposits).toBe(0)
  })

  it('buckets income by month', () => {
    const income = monthlyIncome(activities, monthlyBars(series))
    expect(income.find((row) => row.month === '2026-09').income).toBe(4.5)
    expect(income.find((row) => row.month === '2026-08').income).toBe(0)
  })

  it('labels months', () => { expect(monthLabel('2026-10')).toBe("Oct '26") })
})
