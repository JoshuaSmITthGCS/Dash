import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MonteCarloProjectionPanel from './MonteCarloProjectionPanel'

function horizon(days, overrides = {}) {
  return {
    calendar_days: days,
    trading_days: Math.round(days * 252 / 365),
    mean_terminal_multiple: 1.05,
    mean_annualized_return_pct: 12.4,
    terminal_multiple_percentiles: { p5: 0.85, p25: 0.97, p50: 1.05, p75: 1.14, p95: 1.3 },
    annualized_return_percentiles_pct: { p5: -30, p25: -5, p50: 12, p75: 28, p95: 60 },
    confidence_band_width_pct: 90,
    probability_drawdown_exceeds_current_max: 0.12,
    ...overrides,
  }
}

const readyReport = {
  schema_version: 1,
  status: 'ready',
  input: {
    source: 'backtest_daily_returns',
    observations: 1241,
    method: 'block_bootstrap_full_history',
    paths: 10000,
    block_size_days: 21,
    current_max_drawdown_pct: -18.98,
  },
  horizons: {
    30: horizon(30),
    90: horizon(90),
    180: horizon(180),
    365: horizon(365),
  },
  live_comparison: null,
  disclosure: 'This is a projection built by resampling the historical daily return distribution, not a forecast, guarantee, or promise of future performance.',
}

describe('MonteCarloProjectionPanel', () => {
  it('says which command publishes the artifact when it is missing', () => {
    render(<MonteCarloProjectionPanel report={null} error={{ message: 'not found' }} />)
    expect(screen.getByText(/pipeline\/monte_carlo_projection.py/)).toBeInTheDocument()
  })

  it('reports insufficient data honestly rather than a fabricated projection', () => {
    render(<MonteCarloProjectionPanel report={{ status: 'insufficient_data', status_message: 'Needs at least 60 daily returns; 12 available.' }} />)
    expect(screen.getByText('Not enough history to project forward yet')).toBeInTheDocument()
    expect(screen.getByText(/Needs at least 60 daily returns/)).toBeInTheDocument()
  })

  it('always shows the disclosure banner alongside the projection', () => {
    render(<MonteCarloProjectionPanel report={readyReport} />)
    expect(screen.getByRole('note')).toHaveTextContent(/not a forecast, guarantee/)
  })

  it('defaults to the shortest available horizon and switches on click', () => {
    render(<MonteCarloProjectionPanel report={readyReport} />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['30 days', '90 days', '180 days', '365 days'])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(tabs[2])
    expect(screen.getByRole('tab', { name: '180 days' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the mean, the percentile band, and the drawdown probability together', () => {
    render(<MonteCarloProjectionPanel report={readyReport} />)
    expect(screen.getByText('Monte Carlo average')).toBeInTheDocument()
    expect(screen.getAllByText('+5.0%').length).toBeGreaterThanOrEqual(1) // (1.05 - 1) * 100
    expect(screen.getByText('90pp')).toBeInTheDocument()
    expect(screen.getByText('12%')).toBeInTheDocument() // probability, rounded
    expect(screen.getByText('Median')).toBeInTheDocument()
  })

  it('flags a material shift once the live sample is long enough to compare', () => {
    const report = {
      ...readyReport,
      live_comparison: {
        observations: 260,
        material_shift: true,
        material_shift_threshold: 0.25,
        shift_by_horizon: {
          30: { backtest_mean_annualized_return_pct: 12.4, live_mean_annualized_return_pct: -3.1, relative_shift: 1.25 },
          90: { backtest_mean_annualized_return_pct: 12.4, live_mean_annualized_return_pct: -3.1, relative_shift: 1.25 },
          180: { backtest_mean_annualized_return_pct: 12.4, live_mean_annualized_return_pct: -3.1, relative_shift: 1.25 },
          365: { backtest_mean_annualized_return_pct: 12.4, live_mean_annualized_return_pct: -3.1, relative_shift: 1.25 },
        },
      },
    }
    render(<MonteCarloProjectionPanel report={report} />)
    expect(screen.getByText('Material shift once live data is long enough to project from')).toBeInTheDocument()
  })
})
