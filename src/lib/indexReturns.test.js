import { describe, expect, it } from 'vitest'
import { blendSeries, buildReturnsTable, cleanSeries, periodStartDate, priorMonthEnd, returnBetween } from './indexReturns.js'

const calendar = ['2025-12-30', '2025-12-31', '2026-01-02', '2026-02-27', '2026-03-31', '2026-04-01', '2026-04-02']
const history = (closes) => ({ as_of: '2026-04-02', dates: calendar, symbols: closes })

describe('period starts', () => {
  it('measures calendar periods from the prior period-end and 1D from the prior session', () => {
    expect(periodStartDate('1D', '2026-04-02', calendar)).toBe('2026-04-01')
    expect(periodStartDate('MTD', '2026-04-02', calendar)).toBe('2026-03-31')
    expect(periodStartDate('QTD', '2026-04-02', calendar)).toBe('2026-03-31')
    expect(periodStartDate('YTD', '2026-04-02', calendar)).toBe('2025-12-31')
    expect(periodStartDate('3M', '2026-05-31', calendar)).toBe('2026-02-28')
  })

  it('finds the last session of the prior month', () => {
    expect(priorMonthEnd(calendar, '2026-04-02')).toBe('2026-03-31')
  })
})

describe('returnBetween', () => {
  const series = { dates: ['2024-01-02', '2026-01-02'], values: [100, 121] }

  it('is null when the series does not reach back to the start', () => {
    expect(returnBetween(series, '2023-06-01', '2026-01-02')).toBeNull()
  })

  it('annualises windows over a year and leaves shorter ones cumulative', () => {
    expect(returnBetween(series, '2024-01-02', '2026-01-02')).toBeCloseTo(21, 5)
    expect(returnBetween(series, '2024-01-02', '2026-01-02', { annualize: true })).toBeCloseTo(10, 0)
    const short = { dates: ['2026-01-02', '2026-04-02'], values: [100, 110] }
    expect(returnBetween(short, '2026-01-02', '2026-04-02', { annualize: true })).toBeCloseTo(10, 5)
  })
})

describe('cleanSeries and blends', () => {
  it('drops null and non-positive closes', () => {
    expect(cleanSeries(['2026-01-01', '2026-01-02', '2026-01-03'], [10, null, 12]).values).toEqual([10, 12])
  })

  it('a 100% stock blend equals the stock series', () => {
    const stock = { dates: ['2026-01-02', '2026-01-05', '2026-02-02'], values: [100, 110, 99] }
    const bond = { dates: stock.dates, values: [50, 50, 50] }
    const blend = blendSeries(stock, bond, 1)
    expect(blend.values.at(-1) / blend.values[0]).toBeCloseTo(0.99, 6)
  })
})

describe('buildReturnsTable', () => {
  const closes = {
    SPY: { label: 'S&P 500® Index', closes: [100, 100, 100, 105, 110, 111, 112] },
    AGG: { label: 'U.S. Aggregate Bond', closes: [null, 50, 50, 50, 50, 50, 50] },
  }
  const portfolio = { dates: calendar, values: [1000, 1000, 1000, 1050, 1100, 1110, 1120] }

  it('computes the daily layout against the shared as-of close', () => {
    const table = buildReturnsTable({ history: history(closes), portfolio })
    expect(table.asOf).toBe('2026-04-02')
    const spy = table.rows.find((row) => row.id === 'SPY')
    expect(spy.values['1D'].pct).toBeCloseTo((112 / 111 - 1) * 100, 6)
    expect(spy.values.YTD.pct).toBeCloseTo(12, 6)
    expect(spy.values['10Y']).toBeNull()
    expect(spy.values.LIFE).toBeNull()
    expect(table.portfolio.values.YTD.pct).toBeCloseTo(12, 6)
    expect(table.portfolio.values.LIFE.since).toBe('2025-12-30')
  })

  it('uses the prior month-end for the monthly layout', () => {
    const table = buildReturnsTable({ history: history(closes), portfolio, frequency: 'monthly' })
    expect(table.asOf).toBe('2026-03-31')
    expect(table.columns.map((column) => column.key)).not.toContain('1D')
    expect(table.rows.find((row) => row.id === 'SPY').values.YTD.pct).toBeCloseTo(10, 6)
  })

  it('supports a custom window and rejects an inverted one', () => {
    const table = buildReturnsTable({ history: history(closes), portfolio, frequency: 'custom', custom: { start: '2026-01-02', end: '2026-03-31' } })
    expect(table.rows.find((row) => row.id === 'SPY').values.CUSTOM.pct).toBeCloseTo(10, 6)
    expect(buildReturnsTable({ history: history(closes), portfolio, frequency: 'custom', custom: { start: '2026-03-31', end: '2026-01-02' } }).invalidCustom).toBe(true)
  })

  it('blanks the portfolio row when its series stops before the as-of close', () => {
    const stale = { dates: calendar.slice(0, 5), values: [1000, 1000, 1000, 1050, 1100] }
    const table = buildReturnsTable({ history: history(closes), portfolio: stale })
    expect(table.portfolioStale).toBe(true)
    expect(table.portfolio.values.YTD).toBeNull()
  })

  it('omits blend rows whose proxies are missing', () => {
    const table = buildReturnsTable({ history: history(closes), portfolio })
    expect(table.rows.some((row) => row.group === 'blend')).toBe(false)
  })
})
