import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import HomeScreen from './HomeScreen.jsx'
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
const fakeBar = vi.fn(({ metricId }) => <svg data-testid="fake-bar-chart" data-metric-id={metricId} />)
const fakeManifest = { components: {}, loadRenderer: () => Promise.resolve({ line: fakeLine, composition: fakeComposition, bar: fakeBar }) }

function renderHome() {
  return render(
    <PreferencesProvider>
      <MediumProvider value={fakeManifest}><HomeScreen /></MediumProvider>
    </PreferencesProvider>,
  )
}

// One research row shaped to genuinely clear rankMomentum's and rankBreakoutInProgress's real
// gates (weekReturn > 2, monthReturn > 0, positive acceleration) so those two focused-screen
// cards render real rows, not just their empty state — while rankValueTurnarounds and
// rankReversal legitimately reject it (opposite-signed gates), exercising the empty state too.
const RESEARCH_ROW = {
  ticker: 'AAPL', name: 'Apple Inc.', score: 82, stance: 'ATTRACTIVE', strengths: ['Strong valuation score'],
  is_etf: false, price: 150, sector: 'Technology',
  technical_detail: { return_5d: 6, return_20d: 10, volume_ratio_60d: 1.5 },
}

// Genuinely clears dipWatch's gates (ATTRACTIVE/PROMISING, >=8% off the 52-week high, negative
// 60-day return, and a floor/max band that puts price above the floor and below the recovery
// max) so chart.home.buying-the-dip has one real row to render instead of only its empty state.
const DIP_ROW = {
  ticker: 'MSFT', name: 'Microsoft Corp.', score: 75, stance: 'ATTRACTIVE', is_etf: false, price: 92,
  technical_detail: { pct_from_52w_high: -20, pct_above_52w_low: 5, max_drawdown_252d: -30, return_60d: -5 },
}

const REPORT = {
  generated_at: '2026-08-25T12:00:00Z',
  research: [RESEARCH_ROW],
  screen_universe: [], portfolio_coverage: [], benchmark_history: { dates: [] },
}

function mockDataFiles(overrides = {}) {
  useData.mockImplementation((file) => {
    if (file === 'report.json') return overrides.report ?? { data: REPORT, loading: false }
    if (file === 'validation/signal_metrics.json') return overrides.signalMetrics ?? { data: null, loading: false }
    if (file === 'validation/research_evidence.json') return overrides.researchEvidence ?? { data: null, loading: false }
    if (file === 'etfs.json') return overrides.etfs ?? { data: null, loading: false }
    if (file === 'screens/inside-information.json') return overrides.insideInformation ?? { data: null, loading: false }
    return { data: null, loading: false }
  })
}

describe('HomeScreen', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: null, authError: '', retryAuth: vi.fn() })
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    useWatchlist.mockReturnValue({ items: [] })
    fakeLine.mockClear()
    fakeComposition.mockClear()
    fakeBar.mockClear()
  })

  it('shows the loading state while the report is loading', () => {
    useData.mockReturnValue({ data: null, loading: true })
    renderHome()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows the no-advisor-dataset empty state when the report has no research rows', () => {
    useData.mockImplementation((file) => file === 'report.json'
      ? { data: { research: [] }, loading: false }
      : { data: null, loading: false })
    renderHome()
    expect(screen.getByRole('alert')).toHaveTextContent('No advisor dataset is available yet.')
  })

  it('renders the as-of eyebrow and evidence strip from live data — never hardcoded counts', async () => {
    mockDataFiles({
      signalMetrics: { data: { summary: { ready: 44, breached: 9, total: 64 }, live_sample: { days: 18 } }, loading: false },
      researchEvidence: { data: { headline: { ic_periods_accumulated: 0, ic_periods_required: 24 } }, loading: false },
    })
    renderHome()
    // as-of lives inside HomePortfolioPanel, lazy-loaded (Phase 4, NOTES.md) — resolves async
    // even in tests, since React.lazy() always returns a promise.
    await waitFor(() => expect(screen.getByTestId('as-of')).toHaveTextContent('1 names covered'))
    expect(screen.getByTestId('evidence-strip')).toHaveTextContent('44 ready · 9 breached')
    expect(screen.getByTestId('evidence-strip')).toHaveTextContent('18d live')
    expect(screen.getByTestId('promotion-disclosure')).toHaveTextContent('0 of the 24')
  })

  it('shows the cloud-offline state instead of a portfolio value when signed out', async () => {
    mockDataFiles()
    const { container } = renderHome()
    await waitFor(() => expect(screen.getByText('Cloud portfolio is offline')).toBeInTheDocument())
    expect(container.querySelector('[data-capability-id="state.home.cloud-offline"]')).toBeInTheDocument()
    expect(screen.queryByTestId('portfolio-value')).not.toBeInTheDocument()
  })

  it('shows the no-holdings state when signed in with no positions', async () => {
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' }, authError: '', retryAuth: vi.fn() })
    mockDataFiles()
    const { container } = renderHome()
    await waitFor(() => expect(container.querySelector('[data-capability-id="state.home.no-holdings"]')).toBeInTheDocument())
    expect(screen.getByText('Add holdings to unlock your report')).toBeInTheDocument()
  })

  it('applies the first-viewport capability ids', async () => {
    mockDataFiles()
    const { container } = renderHome()
    await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.portfolio-hero"]')).toBeInTheDocument())
    expect(container.querySelector('[data-capability-id="chart.home.growth-chart"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.chrome.no-signal-promoted"]')).toBeInTheDocument()
  })

  it('renders the top-signal figure from the highest-scoring research row', () => {
    mockDataFiles()
    const { container } = renderHome()
    const node = container.querySelector('[data-capability-id="figure.home.top-signal"]')
    expect(node).toBeInTheDocument()
    expect(within(node).getByTestId('top-signal-ticker')).toHaveTextContent('AAPL')
    expect(within(node).getByTestId('top-signal-score')).toHaveTextContent('82/100')
    expect(within(node).getByTestId('top-signal-score')).toHaveTextContent('ATTRACTIVE')
  })

  it('renders the focused-screen-cards figure with both populated and empty per-card states', () => {
    mockDataFiles({ etfs: { data: null, loading: true } })
    const { container } = renderHome()
    const figure = container.querySelector('[data-capability-id="figure.home.focused-screen-cards"]')
    expect(figure).toBeInTheDocument()
    // Momentum and breakout-in-progress genuinely clear their gates for RESEARCH_ROW.
    const momentumCard = figure.querySelector('[data-screen-card="momentum"]')
    expect(within(momentumCard).getByText('AAPL')).toBeInTheDocument()
    // Reversal's gate (monthReturn < 0) is the opposite sign of the fixture — a real empty state.
    const reversalCard = figure.querySelector('[data-screen-card="matrix"]')
    expect(reversalCard.querySelector('[data-capability-id="state.home.screen-card-empty"]')).toBeInTheDocument()
    // The ETF card was mocked as still loading.
    const etfCard = figure.querySelector('[data-screen-card="etfs"]')
    expect(etfCard.querySelector('[data-capability-id="state.home.screen-card-loading"]')).toBeInTheDocument()
  })

  it('renders the inside-information card, its populated rows, and its empty state', () => {
    mockDataFiles({
      insideInformation: { data: { results: [{ ticker: 'TSLA', institutional_flag: 'CLUSTER_ACCUMULATION', congress_flags: [] }] }, loading: false },
    })
    const { container } = renderHome()
    const node = container.querySelector('[data-capability-id="figure.home.inside-information-card"]')
    expect(node).toBeInTheDocument()
    expect(within(node).getByText('TSLA')).toBeInTheDocument()
    expect(within(node).getByText('Managers accumulating')).toBeInTheDocument()
  })

  it('shows the no-notable-activity state when the inside-information screen has no rows', () => {
    mockDataFiles()
    const { container } = renderHome()
    const node = container.querySelector('[data-capability-id="figure.home.inside-information-card"]')
    expect(node.querySelector('[data-capability-id="state.home.no-notable-activity"]')).toBeInTheDocument()
  })

  it('renders the screen-disclaimer disclosure', () => {
    mockDataFiles()
    const { container } = renderHome()
    expect(container.querySelector('[data-capability-id="disclosure.home.screen-disclaimer"]'))
      .toHaveTextContent('Research screens, not trade instructions')
  })

  it('renders the chart-unavailable state and the methodology-footer disclosure when no chart can be built', async () => {
    mockDataFiles()
    const { container } = renderHome()
    await waitFor(() => expect(container.querySelector('[data-capability-id="state.home.chart-unavailable"]')).toBeInTheDocument())
    expect(container.querySelector('[data-capability-id="disclosure.home.methodology-footer"]'))
      .toHaveTextContent('do not reconstruct trades, deposits, withdrawals')
  })

  it('wires the privacy-eye, chart-period, and top5-rank-mode controls for a signed-in holder', async () => {
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' }, authError: '', retryAuth: vi.fn() })
    useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'AAPL', shares: 10, costBasis: 100 }], loading: false })
    mockDataFiles()
    const { container } = renderHome()

    await waitFor(() => expect(screen.getByTestId('portfolio-value')).toBeInTheDocument())
    expect(screen.getByTestId('portfolio-value')).toHaveTextContent('$1500.00')

    const privacyToggle = container.querySelector('[data-capability-id="control.home.privacy-eye"]')
    expect(privacyToggle).toBeInTheDocument()
    privacyToggle.click()
    await waitFor(() => expect(screen.getByTestId('portfolio-value')).toHaveTextContent('••••'))

    expect(container.querySelector('[data-capability-id="control.home.chart-period"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="control.home.top5-rank-mode"]')).toBeInTheDocument()
    expect(screen.getByTestId('top-5-holdings')).toHaveTextContent('AAPL')
  })

  it('renders the buying-the-dip empty state when no name clears the screen', () => {
    mockDataFiles()
    const { container } = renderHome()
    const node = container.querySelector('[data-capability-id="chart.home.buying-the-dip"]')
    expect(node).toBeInTheDocument()
    expect(node.querySelector('[data-testid="buying-the-dip-empty"]')).toBeInTheDocument()
  })

  it('renders the buying-the-dip bar chart and rows for a name that clears dipWatch\'s gates', async () => {
    mockDataFiles({ report: { data: { ...REPORT, research: [RESEARCH_ROW, DIP_ROW] }, loading: false } })
    const { container } = renderHome()
    const node = container.querySelector('[data-capability-id="chart.home.buying-the-dip"]')
    await waitFor(() => expect(within(node).getByTestId('buying-the-dip-chart')).toBeInTheDocument())
    expect(fakeBar).toHaveBeenCalled()
    expect(within(node).getByTestId('buying-the-dip-rows')).toHaveTextContent('MSFT')
  })

  describe('HomeScreen — signed-in Firebase-backed figures', () => {
    // Real price history on both the anchor dates and the holding lets currentHoldingsSeries
    // build a genuine two-point series, so chart.home.growth-chart and chart.home.allocation
    // exercise their `renderer.line`/`renderer.composition` calls rather than only their
    // chart-unavailable fallback (already covered above).
    const CHART_REPORT = {
      generated_at: '2026-08-25T12:00:00Z',
      research: [{
        ticker: 'AAPL', name: 'Apple Inc.', score: 82, stance: 'ATTRACTIVE', is_etf: false,
        price: 160, sector: 'Technology',
        history: { dates: ['2026-08-20', '2026-08-21'], closes: [150, 160] },
      }],
      screen_universe: [], portfolio_coverage: [],
      benchmark_history: { dates: ['2026-08-20', '2026-08-21'] },
    }

    beforeEach(() => {
      useAuth.mockReturnValue({ currentUser: { uid: 'u1' }, authError: '', retryAuth: vi.fn() })
      useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'AAPL', shares: 10, costBasis: 100 }], loading: false })
    })

    it('renders chart.home.growth-chart through the shared renderer once a real series builds', async () => {
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(screen.getByTestId('growth-chart')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="chart.home.growth-chart"]')
      expect(within(node).getByTestId('fake-line-chart')).toBeInTheDocument()
      expect(fakeLine).toHaveBeenCalled()
      expect(fakeLine.mock.calls.at(-1)[0].metricId).toBe('home-growth-chart')
    })

    it('renders chart.home.allocation through renderer.composition from sector allocation', async () => {
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(container.querySelector('[data-capability-id="chart.home.allocation"]')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="chart.home.allocation"]')
      await waitFor(() => expect(within(node).getByTestId('fake-composition-chart')).toBeInTheDocument())
      expect(within(node).getByTestId('allocation-bars')).toHaveTextContent('Technology')
    })

    it('renders figure.home.performance-evidence-summary with an overall read', async () => {
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.performance-evidence-summary"]')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="figure.home.performance-evidence-summary"]')
      expect(within(node).getByTestId('evidence-summary-overall')).toHaveTextContent('Overall evidence:')
    })

    it('renders figure.home.action-needed with the no-action-needed copy when nothing clears the gate', async () => {
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.action-needed"]')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="figure.home.action-needed"]')
      expect(within(node).getByTestId('action-needed-count')).toHaveTextContent('0')
    })

    it('renders figure.home.watchlist-preview from useWatchlist matched against report.research', async () => {
      useWatchlist.mockReturnValue({ items: [{ ticker: 'AAPL', addedAt: '2026-08-01' }] })
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.watchlist-preview"]')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="figure.home.watchlist-preview"]')
      await waitFor(() => expect(within(node).getByTestId('watchlist-preview-rows')).toHaveTextContent('AAPL'))
    })

    it('shows the watchlist-preview empty state with no followed tickers', async () => {
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.watchlist-preview"]')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="figure.home.watchlist-preview"]')
      expect(within(node).getByTestId('watchlist-preview-empty')).toBeInTheDocument()
    })

    it('shows the opportunity-cost empty state with no benchmark-report.json comparison available', async () => {
      mockDataFiles({ report: { data: CHART_REPORT, loading: false } })
      const { container } = renderHome()
      await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.opportunity-cost"]')).toBeInTheDocument())
      const node = container.querySelector('[data-capability-id="figure.home.opportunity-cost"]')
      expect(within(node).getByTestId('opportunity-cost-empty')).toBeInTheDocument()
    })
  })
})
