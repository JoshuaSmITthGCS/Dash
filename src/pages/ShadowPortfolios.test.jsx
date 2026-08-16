import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ShadowPortfolios from './ShadowPortfolios.jsx'
import { useData } from '../lib/useData.js'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))

describe('ShadowPortfolios', () => {
  it('shows realized prospective metrics and explicit collection gates', () => {
    useData.mockReturnValue({
      loading: false,
      error: null,
      data: {
        strategies: [
          {
            strategy: 'Existing production model', net_return: 1.3528, cagr: null,
            sharpe: null, sortino: null, max_drawdown: -0.1358, turnover: 90,
            snapshots: 4, observations: 2, window_start: '2026-08-03', window_end: '2026-08-05',
            cost_bps: 20, annualized_metrics_minimum_observations: 20,
            evidence_status: 'Accumulating · 2 immutable net-of-cost returns',
          },
          {
            strategy: 'Structural + tactical model', snapshots: 0, observations: 0,
            evidence_status: 'Collection wired · awaiting first eligible portfolio',
          },
        ],
      },
    })

    render(<MemoryRouter><ShadowPortfolios /></MemoryRouter>)
    expect(screen.getByText('Reporting now').nextSibling).toHaveTextContent('1')
    expect(screen.getByText('1.35%')).toBeInTheDocument()
    expect(screen.getAllByText('2/20 returns').length).toBeGreaterThanOrEqual(3)
    expect(screen.getAllByText('Not started').length).toBeGreaterThan(0)
    expect(screen.getByText(/Annualized statistics remain gated until 20/)).toBeInTheDocument()
  })

  it('reports the shared window separately from each strategy own window', () => {
    useData.mockReturnValue({
      loading: false,
      error: null,
      data: {
        aligned_window: { observations: 3, window_start: '2026-08-03', window_end: '2026-08-07' },
        strategies: [
          {
            strategy: 'SPY benchmark', net_return: 3.0728, snapshots: 8, observations: 4,
            window_start: '2026-07-31', window_end: '2026-08-07', composition_change: 0,
            aligned: { net_return: 1.626, observations: 3 },
            evidence_status: 'Accumulating · 4 immutable net-of-cost returns',
          },
          {
            strategy: 'Momentum sleeve', net_return: 0.9615, snapshots: 6, observations: 3,
            window_start: '2026-08-03', window_end: '2026-08-07', composition_change: 15,
            aligned: { net_return: 0.9471, observations: 3 },
            evidence_status: 'Accumulating · 3 immutable net-of-cost returns',
          },
        ],
      },
    })

    render(<MemoryRouter><ShadowPortfolios /></MemoryRouter>)
    // The own-window numbers still differ because the windows do; the aligned pair is the
    // comparison the reader is pointed at.
    expect(screen.getAllByText('3.07%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('1.63%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('0.95%').length).toBeGreaterThan(0)
    expect(screen.getByText(/covers only the 3 sessions every reporting strategy was in the market for/)).toBeInTheDocument()
    expect(screen.getAllByText('15.00% not traded').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Automatic ranking overview')).toHaveTextContent(
      'SPY benchmark ranks #1 of 2 on aligned net return at +1.63% over 3 shared sessions',
    )
    expect(screen.getByLabelText('Automatic ranking overview')).toHaveTextContent(
      'Treat the order as an early read; annualized statistics need 20 matched returns.',
    )
  })

  it('plots a risk/return scatter point for every strategy with both aligned return and drawdown', () => {
    useData.mockReturnValue({
      loading: false,
      error: null,
      data: {
        aligned_window: { observations: 3, window_start: '2026-08-03', window_end: '2026-08-07' },
        strategies: [
          {
            strategy: 'SPY benchmark', net_return: 3.0728, snapshots: 8, observations: 4,
            max_drawdown: -8.2, aligned: { net_return: 1.626, observations: 3 },
            evidence_status: 'Accumulating',
          },
          {
            strategy: 'Momentum sleeve', net_return: 0.9615, snapshots: 6, observations: 3,
            max_drawdown: -12.4, aligned: { net_return: 0.9471, observations: 3 },
            evidence_status: 'Accumulating',
          },
        ],
      },
    })

    render(<MemoryRouter><ShadowPortfolios /></MemoryRouter>)
    expect(screen.getByRole('img', { name: /Max drawdown versus Aligned net return scatter, 2 points/ })).toBeInTheDocument()
  })

  it('does not offer an aligned figure for a strategy that has not started', () => {
    useData.mockReturnValue({
      loading: false,
      error: null,
      data: {
        aligned_window: { observations: 0 },
        strategies: [{
          strategy: 'Quality-value sleeve', snapshots: 0, observations: 0,
          evidence_status: 'Collection wired · awaiting first eligible portfolio',
        }],
      },
    })

    render(<MemoryRouter><ShadowPortfolios /></MemoryRouter>)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Not started').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Automatic ranking overview')).toHaveTextContent('No comparable ranking yet')
  })
})
