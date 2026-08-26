import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import PortfolioScreen from './PortfolioScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))

const fakeManifest = { components: {} }

function renderPortfolio(path = '/v2/portfolio') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><PortfolioScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('PortfolioScreen', () => {
  beforeEach(() => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25', research: [], screen_universe: [], portfolio_coverage: [] }, loading: false })
  })

  it('shows the no-positions empty state', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    renderPortfolio()
    expect(screen.getByText('No positions yet. Add a position to start tracking.')).toBeInTheDocument()
  })

  it('reads the ?view= param', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio('/v2/portfolio?view=diversification')
    expect(container.querySelector('[data-view="diversification"]')).toBeInTheDocument()
  })

  it('falls back to summary for an unknown view param', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio('/v2/portfolio?view=not-a-real-view')
    expect(container.querySelector('[data-view="summary"]')).toBeInTheDocument()
  })

  it('applies the KPI-row capability id', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio()
    expect(container.querySelector('[data-capability-id="figure.portfolio.kpi-row"]')).toBeInTheDocument()
  })

  it('renders the shell chrome on every view', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio()
    expect(container.querySelector('[data-capability-id="nav.portfolio.sub-tabs"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.portfolio.firebase-sync-pill"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.portfolio.hold-not-shown"]')).toBeInTheDocument()
  })

  describe('with holdings', () => {
    const positions = [{ id: 'p1', ticker: 'AAA', shares: 10, costBasis: 5, snapshotPrice: 10, purchaseDate: '2024-01-01' }]

    beforeEach(() => {
      useFirebasePortfolio.mockReturnValue({ positions, loading: false, exportPortfolio: vi.fn(), syncState: { connected: true } })
    })

    it('summary view: renders the four summary metric rows and the holdings grid', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=summary')
      ;['metric.report.strategy-return-twr', 'metric.report.money-weighted-xirr', 'metric.report.portfolio-score', 'metric.report.versus-sp500-return']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
      expect(container.querySelector('[data-capability-id="figure.portfolio.holdings-grid"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="column.portfolio.benchmark-table"]')).toBeInTheDocument()
      expect(screen.getByTestId('holdings-grid')).toHaveTextContent('AAA')
    })

    it('data view: renders the structural rows and the standard-measures metric rows', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=data')
      ;['nav.portfolio.analytics-view-tabs', 'control.portfolio.analytics-scope', 'export.portfolio.data-overview-menu',
        'figure.portfolio.move-explanation', 'figure.portfolio.holdings-data-quality', 'figure.portfolio.fund-cost-overview',
        'figure.portfolio.time-to-valid-metric', 'figure.portfolio.performance-metrics-overview']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
      ;['metric.report.sharpe-naive', 'metric.report.sortino-naive', 'metric.report.calmar', 'metric.report.maximum-drawdown',
        'metric.report.acceleration', 'metric.report.up-capture-spy', 'metric.report.batting-average-spy',
        'metric.report.week-excess', 'metric.report.portfolio-volatility', 'metric.report.active-share']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('data view: mounts the signal-metrics embed only in the algorithm analytics view', () => {
      useData.mockImplementation((file) => {
        if (file === 'validation/signal_metrics.json') {
          return {
            data: {
              summary: { ready: 1, breached: 0, total: 1 },
              groups: [{ id: 'signal', letter: 'A', title: 'Signal quality', requires_live_sample: false }],
              metrics: [{ id: 'rank_ic_5d', group: 'signal', label: 'Rank IC (5d)', value: 0.02, display: '0.02', reads: 'x', breached: false, status: 'ready', observations: 60, required_observations: null }],
            },
            loading: false,
          }
        }
        return { data: { generated_at: '2026-08-25', research: [], screen_universe: [], portfolio_coverage: [] }, loading: false }
      })
      const noEmbed = renderPortfolio('/v2/portfolio?view=data&analytics=overview')
      expect(noEmbed.container.querySelector('[data-capability-id="chart.portfolio.signal-metrics-embed"]')).not.toBeInTheDocument()
      noEmbed.unmount()
      const { container } = renderPortfolio('/v2/portfolio?view=data&analytics=algorithm')
      expect(container.querySelector('[data-capability-id="chart.portfolio.signal-metrics-embed"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="metric.report.rank-ic-5d"]')).toBeInTheDocument()
    })

    it('diversification view: computes a real score for a single-holding portfolio', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=diversification')
      const scoreEl = container.querySelector('[data-capability-id="metric.report.diversification-score"]')
      expect(scoreEl).toBeInTheDocument()
      expect(scoreEl).not.toHaveTextContent('Unavailable')
      ;['figure.diversification.score-dial', 'figure.diversification.effective-bet-summary', 'chart.diversification.score-components',
        'chart.diversification.sector-allocation', 'figure.diversification.industry-concentration', 'chart.diversification.holdings-by-allocation']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('performance view: renders the TWR/XIRR/bridge structural rows and the cash-flow form', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=performance')
      ;['control.portfolio.performance-compare-over', 'figure.portfolio.xirr-kpi', 'figure.portfolio.reconciliation-bridge',
        'control.portfolio.ledger-complete-checkbox', 'control.portfolio.cash-flow-ledger']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })
  })
})
