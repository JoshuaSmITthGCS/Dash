import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import BacktestComparison from './BacktestComparison.jsx'
import { useData } from '../lib/useData.js'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))

const payload = {
  generated_at: '2026-08-13T06:00:00Z',
  methods_total: 4,
  interpretation: 'Success rates may be ranked only inside a comparable group.',
  comparable_groups: {
    held_portfolio: 'Lump-sum portfolios rebalanced on a schedule. Directly comparable.',
    option_trades: 'Per-trade option simulations. Comparable with each other only.',
  },
  success_rate_definitions: {},
  methods: [
    {
      id: 'research_score_monthly', label: 'Research score, top 20 monthly', status: 'measured',
      family: 'portfolio', comparable_group: 'held_portfolio',
      features: ['fundamentals', 'valuation'], success_rate: 0.65,
      success_rate_basis: 'rebalance_periods_positive', beat_benchmark_rate: 0.5333,
      total_return_pct: 69.4781, excess_return_pct: -12.9939, cagr_pct: 11.1,
      sharpe: 0.72, max_drawdown_pct: -24.1, periods_measured: 60,
      window_start: '2021-08-31', window_end: '2026-08-11', caveats: ['Survivorship bias.'],
    },
    {
      id: 'swing_only', label: 'Swing signals only', status: 'measured',
      family: 'portfolio', comparable_group: 'held_portfolio',
      features: ['earnings drift', 'volume'], success_rate: 0.543,
      success_rate_basis: 'rebalance_periods_positive', beat_benchmark_rate: 0.4702,
      total_return_pct: 61.48, excess_return_pct: -16.58, cagr_pct: 17.27,
      sharpe: 0.927, max_drawdown_pct: -26.72, periods_measured: 151,
      window_start: '2023-08-14', window_end: '2026-08-11', caveats: [],
    },
    {
      id: 'political_institutional_only', label: 'Political + institutional trades only',
      status: 'insufficient_disclosure_history', family: 'portfolio',
      comparable_group: 'held_portfolio', features: ['congressional disclosures'],
      success_rate: null, success_rate_basis: 'rebalance_periods_positive',
      excess_return_pct: null, periods_measured: 0, periods_in_cash: 59,
      status_detail: '1 of 60 monthly rebalances carried a qualifying disclosure.',
      caveats: ['Two 13F quarter-ends exist in the store.'],
    },
    {
      id: 'covered_call', label: 'Covered call', status: 'measured', family: 'options',
      comparable_group: 'option_trades', features: ['option pricing'], success_rate: 0.6064,
      success_rate_basis: 'trades_profitable', periods_measured: 11620,
      total_return_pct: 12.0, max_drawdown_pct: -8.0, caveats: [],
    },
  ],
  feature_rollup: [
    { feature: 'fundamentals', success_rate_basis: 'rebalance_periods_positive', methods: 1,
      method_labels: ['Research score, top 20 monthly'], mean_success_rate: 0.65,
      minimum_success_rate: 0.65, maximum_success_rate: 0.65 },
  ],
}

const renderPage = (data = payload) => {
  useData.mockReturnValue({ loading: false, error: null, data })
  return render(<MemoryRouter><BacktestComparison /></MemoryRouter>)
}

describe('BacktestComparison', () => {
  it('groups methods so option win rates are never tabled beside portfolio period rates', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Held portfolios' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Option strategies' })).toBeInTheDocument()
  })

  it('labels every success rate with the definition it was measured under', () => {
    renderPage()

    expect(screen.getAllByText('periods positive').length).toBeGreaterThan(0)
    expect(screen.getAllByText('trades profitable').length).toBeGreaterThan(0)
  })

  it('reports a cash-heavy strategy as untraded rather than as a zero percent success rate', () => {
    renderPage()

    expect(screen.getByText(/Held cash in 59 of 59 periods/)).toBeInTheDocument()
    expect(screen.getAllByText('Insufficient history').length).toBeGreaterThan(0)
  })

  it('ranks within a group by success rate', () => {
    renderPage()

    const rows = screen.getAllByRole('row').map((row) => row.textContent)
    const research = rows.findIndex((text) => text.includes('Research score, top 20 monthly'))
    const swing = rows.findIndex((text) => text.includes('Swing signals only'))
    expect(research).toBeGreaterThan(-1)
    expect(research).toBeLessThan(swing)
  })

  it('surfaces the feature rollup with its method count so a single-method average is visible', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Success rate by feature' })).toBeInTheDocument()
    expect(screen.getByText('fundamentals')).toBeInTheDocument()
  })

  it('states that the feature rollup is co-occurrence and not attribution', () => {
    renderPage()

    expect(screen.getByText(/co-occurrence across methods, not attribution/)).toBeInTheDocument()
  })

  it('shows an error state rather than an empty table when the payload fails to load', () => {
    useData.mockReturnValue({ loading: false, error: new Error('boom'), data: null })
    render(<MemoryRouter><BacktestComparison /></MemoryRouter>)

    expect(screen.getByRole('alert')).toHaveTextContent('Backtest comparison unavailable')
  })

  it('never lets an unmeasured strategy lead the table on a one-observation success rate', () => {
    renderPage({
      ...payload,
      methods: payload.methods.map((row) => row.id === 'political_institutional_only'
        ? { ...row, success_rate: 1, periods_measured: 1 } : row),
    })

    const rows = screen.getAllByRole('row').map((row) => row.textContent)
    const pending = rows.findIndex((text) => text.includes('Political + institutional'))
    const measured = rows.findIndex((text) => text.includes('Research score, top 20 monthly'))
    expect(measured).toBeLessThan(pending)
  })
})
