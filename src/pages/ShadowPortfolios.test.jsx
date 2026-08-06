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
})
