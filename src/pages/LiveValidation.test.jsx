import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LiveValidation from './LiveValidation.jsx'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))

const accumulating = {
  periods_accumulated: 0,
  minimum_periods: 24,
  status: 'accumulating',
  status_message: 'accumulating, 0 of 24 periods',
  mean_rank_ic: null,
  confidence_interval_95: [null, null],
  icir: null,
  bucket_returns: { 5: { buckets: [], monotonic: false } },
}

const signalMetrics = {
  groups: [
    { id: 'signal', letter: 'A', title: 'Signal quality', summary: 'Does it predict.', requires_live_sample: false },
    { id: 'monitoring', letter: 'F', title: 'Drift alarms', summary: 'Live against backtest.', requires_live_sample: true },
  ],
  cadence: [{ frequency: 'Weekly', items: 'Rolling IC, turnover' }],
  live_sample: { days: 2, refreshes: 7, first_date: '2026-08-05', last_date: '2026-08-06' },
  summary: { total: 2, ready: 1, breached: 0, sample_free_total: 1, sample_free_ready: 1, needs_sample_total: 1 },
  metrics: [
    { id: 'rank_ic_21d', group: 'signal', label: 'Rank IC (21d)', value: 0.031, display: '0.031',
      breached: false, requires_live_sample: false, status: 'ready', observations: 58 },
    { id: 'feature_psi', group: 'monitoring', label: 'Feature distribution PSI', value: null,
      breached: false, requires_live_sample: true, status: 'accumulating',
      status_message: '2 live days recorded.', observations: 2, required_observations: 60 },
  ],
}

describe('LiveValidation', () => {
  beforeEach(() => {
    useData.mockImplementation((name) => {
      if (name.includes('ic_validation')) {
        return { data: {
          snapshot_refreshes: 1,
          variants: {
            champion: { '1M': accumulating },
            challenger: { '1M': accumulating },
          },
        }, loading: false, error: null }
      }
      if (name.includes('signal_metrics')) return { data: signalMetrics, loading: false, error: null }
      return { data: { summary: { passed: 0, failed: 0 }, results: [] }, loading: false, error: null }
    })
  })

  it('renders honest accumulating states with zero realized periods', () => {
    render(<MemoryRouter><LiveValidation /></MemoryRouter>)
    expect(screen.getByText('Champion versus challenger')).toBeInTheDocument()
    expect(screen.getAllByText('accumulating, 0 of 24 periods')).toHaveLength(2)
    expect(screen.queryByText(/^0\.000$/)).not.toBeInTheDocument()
  })

  it('leads with signal metrics split by what a live sample gates', () => {
    render(<MemoryRouter><LiveValidation /></MemoryRouter>)
    expect(screen.getByLabelText('Automatic ranking overview')).toHaveTextContent(
      '21d is the strongest ready horizon at Rank IC 0.031',
    )
    expect(screen.getByLabelText('Automatic ranking overview')).toHaveTextContent(
      '1 of 1 tested horizon clears the published floor. No published thresholds are breached. Live-only evidence spans 2 days.',
    )
    expect(screen.getByText('Computable now')).toBeInTheDocument()
    expect(screen.getByText('Needs live sample')).toBeInTheDocument()
    // The sample-free reading is present while the sample-gated one still counts up.
    expect(screen.getByText('0.031')).toBeInTheDocument()
    expect(screen.getByText('2 live days recorded.')).toBeInTheDocument()
  })

  it('plots champion versus challenger mean rank IC by horizon once both have ready values', () => {
    useData.mockImplementation((name) => {
      if (name.includes('ic_validation')) {
        return { data: {
          snapshot_refreshes: 3,
          variants: {
            champion: { '1M': { ...accumulating, mean_rank_ic: 0.032 }, '3M': { ...accumulating, mean_rank_ic: 0.021 } },
            challenger: { '1M': { ...accumulating, mean_rank_ic: 0.018 }, '3M': { ...accumulating, mean_rank_ic: -0.004 } },
          },
        }, loading: false, error: null }
      }
      if (name.includes('signal_metrics')) return { data: signalMetrics, loading: false, error: null }
      return { data: { summary: { passed: 0, failed: 0 }, results: [] }, loading: false, error: null }
    })

    render(<MemoryRouter><LiveValidation /></MemoryRouter>)
    expect(screen.getByRole('img', { name: /Champion versus Challenger, 2 groups/ })).toBeInTheDocument()
  })

  it('surfaces ETF watchlist and thematic-screen validation alongside the core research score', () => {
    useData.mockImplementation((name) => {
      if (name.includes('ic_validation')) {
        return { data: { snapshot_refreshes: 1, variants: { champion: { '1M': accumulating } } }, loading: false, error: null }
      }
      if (name.includes('signal_metrics')) return { data: signalMetrics, loading: false, error: null }
      if (name.includes('live_etf_validation')) {
        return { data: {
          summary: { passed: 1, failed: 0 },
          results: [{
            ticker: 'VXUS', case: 'international_equity', status: 'pass',
            benchmark: { ticker: 'IXUS', quality_label: 'Investable proxy', confidence: 0.78 },
            one_year: { metrics: { fund_return: 27.13, benchmark_return: 27.27, excess_return: -0.14, beta: 0.99, correlation: 0.999, up_capture: 99.2, down_capture: 99.2 } },
            checks: { proxy_label_honest: true, capture_sample_gate: true },
          }],
        }, loading: false, error: null }
      }
      if (name.includes('theme_metrics')) {
        return { data: {
          snapshot_dates_recorded: 0,
          metrics: {
            theme_exposure_score: { status: 'accumulating', eligible_periods: 0, minimum_icir_periods: 24, mean_rank_ic: null, icir: null, hit_rate: null },
          },
        }, loading: false, error: null }
      }
      return { data: { summary: { passed: 0, failed: 0 }, results: [] }, loading: false, error: null }
    })

    render(<MemoryRouter><LiveValidation /></MemoryRouter>)
    expect(screen.getByText('ETF watchlist benchmark validation')).toBeInTheDocument()
    expect(screen.getByText('VXUS')).toBeInTheDocument()
    expect(screen.getByText('Thematic screen validation')).toBeInTheDocument()
    expect(screen.getByText('Theme Exposure Score')).toBeInTheDocument()
  })
})
