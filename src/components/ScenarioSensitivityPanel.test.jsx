import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ScenarioSensitivityPanel from './ScenarioSensitivityPanel'

const signalMetrics = {
  metrics: [
    {
      id: 'scenario_gfc_2008', label: '2008 Global Financial Crisis', status: 'ready',
      detail: { description: 'S&P 500 all-time high to the post-crisis trough.', spy_return_pct: -55.19 },
    },
    {
      id: 'scenario_hypothetical_spy', label: 'Hypothetical: SPY -30%', status: 'ready',
      detail: { shock_pct: -30, beta_spy: 0.65, projected_return_pct: -19.5 },
    },
  ],
}

function position(ticker, beta, currentValue) {
  return { ticker, currentValue, allocationPct: 10, priceInfo: { name: ticker, sector: 'technology', technical_detail: { beta } } }
}

const holdings = {
  portfolioPositions: [
    position('HIGHBETA', 2.0, 5000),
    position('LOWBETA', 0.2, 5000),
    position('MIDBETA', 1.0, 5000),
  ],
}

describe('ScenarioSensitivityPanel', () => {
  it('says how to publish the projections when signal metrics has not run', () => {
    render(<ScenarioSensitivityPanel holdings={holdings} signalMetrics={null} />)
    expect(screen.getByText(/pipeline\/signal_metrics.py/)).toBeInTheDocument()
  })

  it('says why nothing ranks when no holding has a measured beta', () => {
    const unbetaed = { portfolioPositions: [{ ticker: 'NEWCO', currentValue: 100, priceInfo: {} }] }
    render(<ScenarioSensitivityPanel holdings={unbetaed} signalMetrics={signalMetrics} />)
    expect(screen.getByText('No holding has a measured beta yet')).toBeInTheDocument()
  })

  it('defaults to the first available scenario and ranks the highest-beta holding as most exposed', () => {
    render(<ScenarioSensitivityPanel holdings={holdings} signalMetrics={signalMetrics} />)
    expect(screen.getByRole('tab', { name: '2008 Global Financial Crisis' })).toHaveAttribute('aria-selected', 'true')
    const mostExposed = screen.getByText('Most exposed').closest('.scenario-holding-column')
    expect(mostExposed).toHaveTextContent('HIGHBETA')
  })

  it('switches scenarios on click and re-ranks', () => {
    render(<ScenarioSensitivityPanel holdings={holdings} signalMetrics={signalMetrics} />)
    fireEvent.click(screen.getByRole('tab', { name: 'Hypothetical: SPY -30%' }))
    expect(screen.getByRole('tab', { name: 'Hypothetical: SPY -30%' })).toHaveAttribute('aria-selected', 'true')
    // -30% * 2.0 beta = -60%, the worst projection in this fixture.
    expect(screen.getByText('-60.0%')).toBeInTheDocument()
  })

  it('shows a value-weighted whole-portfolio figure alongside the per-holding ranking', () => {
    render(<ScenarioSensitivityPanel holdings={holdings} signalMetrics={signalMetrics} />)
    expect(screen.getByText('Whole portfolio, value-weighted')).toBeInTheDocument()
  })
})
