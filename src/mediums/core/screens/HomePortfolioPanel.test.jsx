import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import HomePortfolioPanel from './HomePortfolioPanel.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { PreferencesProvider } from '../../../lib/PreferencesContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { useWatchlist } from '../../../lib/useWatchlist.js'
import { useAuth } from '../../../lib/FirebaseAuthContext.jsx'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../../../lib/useWatchlist.js', () => ({ useWatchlist: vi.fn() }))
vi.mock('../../../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn(), AuthProvider: ({ children }) => children }))

const fakeLine = vi.fn(({ metricId }) => <svg data-testid="fake-line-chart" data-metric-id={metricId} />)
const fakeComposition = vi.fn(({ metricId }) => <svg data-testid="fake-composition-chart" data-metric-id={metricId} />)
const fakeManifest = { components: {}, loadRenderer: () => Promise.resolve({ line: fakeLine, composition: fakeComposition }) }

// AAPL carries genuine daily history on both benchmark-history anchor dates so
// currentHoldingsSeries builds a real two-point series (exercises chart.home.growth-chart and
// chart.home.allocation's renderer calls); MSFT is unpriced deliberately (no `price`/`history`)
// so it never enters priceData and stays untracked, matching real thin-coverage portfolios.
const REPORT = {
  generated_at: '2026-08-25T12:00:00Z',
  research: [
    {
      ticker: 'AAPL', name: 'Apple Inc.', score: 82, stance: 'ATTRACTIVE', is_etf: false,
      price: 160, sector: 'Technology', data_coverage: 0.9,
      recommendation: { action: 'TRIM', suggested_trim_pct: 33, reasons: ['Weak momentum'] },
      history: { dates: ['2026-08-20', '2026-08-21'], closes: [150, 160] },
    },
    { ticker: 'MSFT', name: 'Microsoft Corp.', score: 70, is_etf: false, dayChange: 1.2 },
  ],
  screen_universe: [], portfolio_coverage: [],
  benchmark_history: { dates: ['2026-08-20', '2026-08-21'] },
}

const BENCHMARK_REPORT = {
  histories: {
    SPY: { dates: ['2026-08-20', '2026-08-21'], closes: [500, 505] },
  },
}

function mockDataFiles(overrides = {}) {
  useData.mockImplementation((file) => {
    if (file === 'benchmark-report.json') return overrides.benchmarkReport ?? { data: BENCHMARK_REPORT, loading: false }
    return { data: null, loading: false }
  })
}

function renderPanel(report = REPORT) {
  return render(
    <PreferencesProvider>
      <MediumProvider value={fakeManifest}><HomePortfolioPanel report={report} /></MediumProvider>
    </PreferencesProvider>,
  )
}

describe('HomePortfolioPanel', () => {
  beforeEach(() => {
    fakeLine.mockClear()
    fakeComposition.mockClear()
    useWatchlist.mockReturnValue({ items: [] })
    mockDataFiles()
  })

  it('shows the cloud-offline state when signed out — no benchmark-report.json fetch happens', () => {
    useAuth.mockReturnValue({ currentUser: null, authError: '', retryAuth: vi.fn() })
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPanel()
    expect(container.querySelector('[data-capability-id="state.home.cloud-offline"]')).toBeInTheDocument()
    expect(useData).not.toHaveBeenCalledWith('benchmark-report.json')
  })

  describe('signed in with a priced AAPL holding', () => {
    beforeEach(() => {
      useAuth.mockReturnValue({ currentUser: { uid: 'u1' }, authError: '', retryAuth: vi.fn() })
      useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'AAPL', shares: 10, costBasis: 100 }], loading: false })
    })

    it('renders chart.home.growth-chart through renderer.line once a real series builds', async () => {
      const { container } = renderPanel()
      await waitFor(() => expect(screen.getByTestId('growth-chart')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="chart.home.growth-chart"]')
      expect(within(node).getByTestId('fake-line-chart')).toBeInTheDocument()
      const props = fakeLine.mock.calls.at(-1)[0]
      expect(props.metricId).toBe('home-growth-chart')
      expect(props.series.length).toBeGreaterThan(1)
      expect(props.unit).toBe('USD')
    })

    it('renders chart.home.allocation through renderer.composition with the real sector split', async () => {
      const { container } = renderPanel()
      const node = container.querySelector('[data-capability-id="chart.home.allocation"]')
      await waitFor(() => expect(within(node).getByTestId('fake-composition-chart')).toBeInTheDocument())
      expect(within(node).getByTestId('allocation-bars')).toHaveTextContent('Technology')
      expect(within(node).getByTestId('allocation-bars')).toHaveTextContent('100.0%')
      const props = fakeComposition.mock.calls.at(-1)[0]
      expect(props.values).toEqual([{ value: 100, label: 'Technology' }])
    })

    it('renders figure.home.action-needed with a real TRIM recommendation', async () => {
      const { container } = renderPanel()
      const node = container.querySelector('[data-capability-id="figure.home.action-needed"]')
      await waitFor(() => expect(within(node).getByTestId('action-needed-count')).toHaveTextContent('1'))
      expect(within(node).getByTestId('action-needed-note')).toHaveTextContent('AAPL')
    })

    it('renders figure.home.watchlist-preview matched against report.research', async () => {
      useWatchlist.mockReturnValue({ items: [{ ticker: 'MSFT', addedAt: '2026-08-01' }] })
      const { container } = renderPanel()
      const node = container.querySelector('[data-capability-id="figure.home.watchlist-preview"]')
      await waitFor(() => expect(within(node).getByTestId('watchlist-preview-rows')).toHaveTextContent('MSFT'))
    })

    it('renders figure.home.opportunity-cost from a real benchmark-report.json comparison', async () => {
      const { container } = renderPanel()
      const node = container.querySelector('[data-capability-id="figure.home.opportunity-cost"]')
      await waitFor(() => expect(within(node).getByTestId('opportunity-cost')).toBeInTheDocument())
      expect(within(node).getByTestId('opportunity-cost')).toHaveTextContent('SPY proxy')
    })

    it('renders figure.home.performance-evidence-summary with an overall read', async () => {
      const { container } = renderPanel()
      const node = container.querySelector('[data-capability-id="figure.home.performance-evidence-summary"]')
      await waitFor(() => expect(within(node).getByTestId('evidence-summary-overall')).toHaveTextContent('Overall evidence:'))
    })
  })
})
