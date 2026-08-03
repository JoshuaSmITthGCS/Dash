import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ETFComparisonChart } from './ETFComparisonChart'
import { parseEtfComparison } from '../lib/etfComparison'

const points = [
  { date: '2025-01-02', fund_index: 100, benchmark_index: 100, relative_index: 100, fund_drawdown: 0, benchmark_drawdown: 0 },
  { date: '2025-02-03', fund_index: 110, benchmark_index: 105, relative_index: 104.76, fund_drawdown: 0, benchmark_drawdown: 0 },
]
const range = (series = points) => ({ status: series.length > 1 ? 'success' : 'unavailable', series,
  metrics: { fund_return: 10, benchmark_return: 5, excess_return: 5, beta: 1.1, correlation: .9,
    fund_max_drawdown: -4, tracking_difference: 5, tracking_error: 2, sharpe: 1.2, sortino: 1.5 },
  observation_count: series.length, actual_start: series[0]?.date, end: series.at(-1)?.date,
  reason_code: series.length > 1 ? null : 'INSUFFICIENT_OBSERVATIONS', quality_flags: [] })
const payload = (overrides = {}) => ({ schema_version: '4.0.0', ticker: 'VTI', status: 'success',
  benchmark: { display_name: 'Total Market proxy', ticker: 'ITOT', type: 'investable_proxy', quality_label: 'Investable proxy', confidence: .8 },
  chart_ranges: { '1M': range(), '1Y': range() }, ...overrides })

describe('ETFComparisonChart', () => {
  it('renders fund and correctly labeled benchmark lines and range metrics', () => {
    const { container } = render(<ETFComparisonChart data={payload()} />)
    expect(screen.getAllByText('VTI').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Total Market proxy').length).toBeGreaterThan(0)
    expect(screen.getByText('+10.00%')).toBeInTheDocument()
    expect(container.querySelectorAll('path').length).toBe(2)
  })

  it('switches range and view without producing a silent chart', () => {
    render(<ETFComparisonChart data={payload()} />)
    fireEvent.click(screen.getByRole('button', { name: '1M' }))
    fireEvent.click(screen.getByRole('button', { name: 'Relative strength' }))
    expect(screen.getByText('VTI relative strength')).toBeInTheDocument()
  })

  it.each([
    ['benchmark missing', []], ['young ETF', points.slice(0, 1)], ['one-point range', points.slice(0, 1)],
    ['null observations', [{ ...points[0], benchmark_index: null }]], ['no overlapping dates', []],
  ])('shows an explicit state for %s', (_, series) => {
    render(<ETFComparisonChart data={payload({ chart_ranges: { '1Y': range(series) } })} />)
    expect(screen.getByText('Benchmark history unavailable for this range')).toBeInTheDocument()
  })

  it('hides tracking labels for a generic market comparison', () => {
    render(<ETFComparisonChart data={payload({ benchmark: { ...payload().benchmark, type: 'generic_market' } })} />)
    expect(screen.queryByText('Tracking difference')).not.toBeInTheDocument()
    expect(screen.queryByText('Tracking error')).not.toBeInTheDocument()
  })
})

describe('ETF schema parsing', () => {
  it('rejects incompatible schema versions', () => {
    expect(() => parseEtfComparison(payload({ schema_version: '3.0.0' }))).toThrow(/Unsupported/)
  })

  it('drops null/non-numeric benchmark observations', () => {
    const parsed = parseEtfComparison(payload({ chart_ranges: { '1Y': range([{ ...points[0], benchmark_index: null }, points[1]]) } }))
    expect(parsed.chart_ranges['1Y'].series).toHaveLength(1)
  })
})
