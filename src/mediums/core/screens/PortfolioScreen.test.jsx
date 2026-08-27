import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import PortfolioScreen from './PortfolioScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { PreferencesProvider } from '../../../lib/PreferencesContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { usePortfolioTracking } from '../../../lib/usePortfolioTracking.js'
import { useFirebaseFinances } from '../../../lib/useFirebaseFinances.js'
import { useAuth } from '../../../lib/FirebaseAuthContext.jsx'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../../../lib/usePortfolioTracking.js', () => ({ usePortfolioTracking: vi.fn() }))
vi.mock('../../../lib/useFirebaseFinances.js', () => ({ useFirebaseFinances: vi.fn() }))
// The real `AuthProvider` (which `PortfolioScreen` wraps its content in, per the standing hard
// rule -- see the module's own comment) makes a real Firebase/solo-session round trip. Mocking
// the module lets tests control `currentUser` without touching that wrapper.
vi.mock('../../../lib/FirebaseAuthContext.jsx', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: vi.fn(),
}))

const fakeChart = vi.fn(({ metricId }) => <svg data-testid="fake-chart" data-metric-id={metricId} />)
const fakeRenderer = { line: fakeChart, bar: fakeChart, dial: fakeChart, fan: fakeChart, profile: fakeChart, heatmap: fakeChart }
const fakeManifest = { components: {}, loadRenderer: () => Promise.resolve(fakeRenderer) }

const reportFixture = { generated_at: '2026-08-25', research: [], screen_universe: [], portfolio_coverage: [], theme_screen: { by_ticker: {} } }

/** A small representative fixture matching `public/data/validation/monte_carlo_projection.json`'s
 * real shape -- `horizons` is an object keyed by day-string, not an array. */
const monteCarloFixture = {
  schema_version: 1, generated_at: '2026-08-25', status: 'ready',
  input: {},
  horizons: {
    30: { terminal_multiple_percentiles: { p5: 0.93, p25: 0.98, p50: 1.02, p75: 1.04, p95: 1.08 } },
    365: { terminal_multiple_percentiles: { p5: 0.75, p25: 0.92, p50: 1.1, p75: 1.3, p95: 1.6 } },
  },
  live_comparison: {},
  disclosure: 'This is a projection built by resampling the historical daily return distribution, not a forecast.',
  model_version: '1.0.0',
  model_metadata: {},
}

/** A published research row whose `getRecommendation()` verdict is TRIM, for suggested-actions tests. */
const trimResearchRow = {
  ticker: 'AAA', name: 'AAA Corp', price: 12, is_etf: false, data_coverage: 0.9,
  recommendation: { action: 'TRIM', suggested_trim_pct: 25, reasons: ['Two of three factors flagged'], agreement_count: 2 },
}
const financesSettingsFixture = {
  schemaVersion: 3, currentAge: 30, retireAge: 65, inflationPct: 2.5, monthlyContribution: 500, currentSavings: 10000,
  retirementEndAge: 95, monthlyWithdrawal: 3000, allocationAggressiveness: 'growth', planningAnnualReturnTargetPct: 15,
  coastFireEnabled: false,
}

function financesFixture(overrides = {}) {
  return {
    settings: financesSettingsFixture, budgetItems: [], pools: [], accounts: [], goals: [], loading: false,
    updateSettings: vi.fn(), addBudgetItem: vi.fn(), removeBudgetItem: vi.fn(), addPool: vi.fn(), removePool: vi.fn(),
    depositToPools: vi.fn(), addAccount: vi.fn(), removeAccount: vi.fn(), updateAccountContribution: vi.fn(),
    addGoal: vi.fn(), removeGoal: vi.fn(), ...overrides,
  }
}

function trackingFixture(overrides = {}) {
  return {
    snapshots: [], activities: [], rebalances: [], trackingState: null, error: '',
    recordSnapshot: vi.fn(), recordActivity: vi.fn(), setLedgerComplete: vi.fn(), recordRebalance: vi.fn(), ...overrides,
  }
}

function dataForFile(file) {
  if (file === 'benchmark-report.json') return { data: { histories: {} }, loading: false }
  if (file === 'validation/monte_carlo_projection.json') return { data: monteCarloFixture, loading: false }
  return { data: reportFixture, loading: false }
}

/** Consecutive weekday ISO dates -- enough (90) to clear both the 60-common-observation floor
 * `correlationDiversification` requires and the 60-return window `rollingSharpe` needs a
 * non-empty output from. */
function weekdayDates(count, start = Date.UTC(2026, 0, 2)) {
  const dates = []
  const cursor = new Date(start)
  while (dates.length < count) {
    const day = cursor.getUTCDay()
    if (day !== 0 && day !== 6) dates.push(cursor.toISOString().slice(0, 10))
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return dates
}
const richDates = weekdayDates(90)
const richCloses = (base, phase) => richDates.map((_, i) => base * (1 + i * 0.0015 + Math.sin(i / 5 + phase) * 0.01))
const richAaaCloses = richCloses(50, 0)
const richBbbCloses = richCloses(80, 1.4)
const richSpyCloses = richCloses(400, 0.3)

/** Two priced, native-daily holdings with published beta and theme rows -- the substrate the
 * rolling-Sharpe, correlation-heatmap, theme-exposure-grid, monte-carlo-panel-embed, and
 * scenario-sensitivity rows all read real (non-"insufficient history") content from. */
const richReportFixture = {
  generated_at: richDates.at(-1),
  research: [
    {
      ticker: 'AAA', price: richAaaCloses.at(-1), name: 'AAA Corp', sector: 'Technology', industry: 'Software',
      analytics_history: { dates: richDates, closes: richAaaCloses, frequency: 'daily' },
      technical_detail: { beta: 1.2 },
    },
    {
      ticker: 'BBB', price: richBbbCloses.at(-1), name: 'BBB Inc', sector: 'Healthcare', industry: 'Biotech',
      analytics_history: { dates: richDates, closes: richBbbCloses, frequency: 'daily' },
      technical_detail: { beta: 0.7 },
    },
  ],
  screen_universe: [],
  portfolio_coverage: [],
  theme_screen: {
    by_ticker: {
      AAA: [{ theme_id: 'digital_payments', display_name: 'Digital Payments', theme_exposure_score: 82, eligible: true }],
      BBB: [{ theme_id: 'genomics', display_name: 'Genomics', theme_exposure_score: 65, eligible: true }],
    },
  },
}
const richSpySnapshot = {
  ticker: 'SPY', benchmark: 'S&P 500',
  price_series: { fund: richDates.map((date, i) => ({ date, adjusted_close: richSpyCloses[i] })) },
}
const richPositions = [
  { id: 'p1', ticker: 'AAA', shares: 10, costBasis: 40, purchaseDate: '2024-01-01' },
  { id: 'p2', ticker: 'BBB', shares: 5, costBasis: 60, purchaseDate: '2024-01-01' },
]
const richSignalMetrics = {
  summary: { ready: 1, breached: 0, total: 1 },
  groups: [],
  metrics: [{
    id: 'scenario_gfc_2008', group: 'scenario', label: 'GFC 2008', value: null, display: null, reads: 'x',
    breached: false, status: 'ready', observations: null, required_observations: null,
    detail: { spy_return_pct: -38, description: 'A repeat of the 2008 financial crisis.' },
  }],
}
function dataForRichFile(file) {
  if (file === 'report.json') return { data: richReportFixture, loading: false }
  if (file === 'benchmark-report.json') return { data: { histories: {} }, loading: false }
  if (file === 'etf/SPY.json') return { data: richSpySnapshot, loading: false }
  if (file === 'validation/monte_carlo_projection.json') return { data: monteCarloFixture, loading: false }
  if (file === 'validation/signal_metrics.json') return { data: richSignalMetrics, loading: false }
  return { data: null, loading: false }
}

function renderPortfolio(path = '/v2/portfolio') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <PreferencesProvider>
        <MediumProvider value={fakeManifest}><PortfolioScreen /></MediumProvider>
      </PreferencesProvider>
    </MemoryRouter>
  )
}

describe('PortfolioScreen', () => {
  beforeEach(() => {
    useData.mockImplementation(dataForFile)
    usePortfolioTracking.mockReturnValue(trackingFixture())
    useFirebaseFinances.mockReturnValue(financesFixture())
    useAuth.mockReturnValue({ currentUser: { uid: 'test-user' }, userProfile: {}, loading: false, authError: '', retryAuth: vi.fn() })
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

  it('insights view: shows the loading state while unauthenticated', () => {
    useAuth.mockReturnValue({ currentUser: null, userProfile: {}, loading: true, authError: '', retryAuth: vi.fn() })
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio('/v2/portfolio?view=insights')
    expect(container.querySelector('[data-capability-id="state.insights.loading"]')).toBeInTheDocument()
  })

  it('insights view: shows the no-holdings state once authenticated', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio('/v2/portfolio?view=insights')
    expect(container.querySelector('[data-capability-id="state.insights.no-holdings"]')).toBeInTheDocument()
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

    it('summary view: clicking a holdings-grid ticker opens the Stock Detail Sheet via ?ticker=', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=summary')
      fireEvent.click(screen.getByTestId('holdings-grid').querySelector('button'))
      expect(container.querySelector('[data-capability-id="detail.stock.dialog-shell"]')).toBeInTheDocument()
    })

    it('summary view: does not render a suggested action for a HOLD-only portfolio', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=summary')
      expect(container.querySelector('[data-capability-id="control.portfolio.suggested-actions-toggle"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="figure.portfolio.suggested-actions-list"]')).toHaveTextContent('No sell/trim actions need review right now.')
      expect(container.querySelector('#sell-signals')).toBeInTheDocument()
    })

    it('summary view: renders a suggested action for a TRIM/SELL position, and "Why" opens the Stock Detail Sheet', () => {
      useData.mockImplementation((file) => {
        if (file === 'report.json') return { data: { ...reportFixture, research: [trimResearchRow] }, loading: false }
        return dataForFile(file)
      })
      const { container } = renderPortfolio('/v2/portfolio?view=summary')
      const list = container.querySelector('[data-capability-id="figure.portfolio.suggested-actions-list"]')
      expect(list).toHaveTextContent('AAA')
      expect(list).toHaveTextContent('TRIM')
      fireEvent.click(screen.getByText('Why'))
      expect(container.querySelector('[data-capability-id="detail.stock.dialog-shell"]')).toBeInTheDocument()
    })

    it('data view: renders the structural rows and the standard-measures metric rows', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=data')
      ;['nav.portfolio.analytics-view-tabs', 'control.portfolio.analytics-scope', 'export.data-overview.copy-metrics',
        'export.data-overview.download-json', 'export.portfolio.export-portfolio-json',
        'figure.portfolio.move-explanation', 'figure.portfolio.holdings-data-quality', 'figure.portfolio.fund-cost-overview',
        'figure.portfolio.time-to-valid-metric', 'figure.portfolio.performance-metrics-overview']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
      ;['metric.report.sharpe-naive', 'metric.report.sortino-naive', 'metric.report.calmar', 'metric.report.maximum-drawdown',
        'metric.report.acceleration', 'metric.report.up-capture-spy', 'metric.report.batting-average-spy',
        'metric.report.week-excess', 'metric.report.portfolio-volatility', 'metric.report.active-share']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('data view: copies the full snapshot to the clipboard and reports status', async () => {
      Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
      renderPortfolio('/v2/portfolio?view=data')
      fireEvent.click(screen.getByText('Copy all metrics to clipboard'))
      await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1))
      const payload = JSON.parse(navigator.clipboard.writeText.mock.calls[0][0])
      expect(payload.holdings.positions).toEqual(positions)
      expect(await screen.findByText('Copied to clipboard')).toBeInTheDocument()
    })

    it('data view: reports a clipboard failure rather than silently doing nothing', async () => {
      Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } })
      renderPortfolio('/v2/portfolio?view=data')
      fireEvent.click(screen.getByText('Copy all metrics to clipboard'))
      expect(await screen.findByText('Copy failed')).toBeInTheDocument()
    })

    it('data view: triggers a JSON download of the full snapshot', () => {
      globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock')
      globalThis.URL.revokeObjectURL = vi.fn()
      renderPortfolio('/v2/portfolio?view=data')
      fireEvent.click(screen.getByText('Download all metrics (JSON)'))
      expect(globalThis.URL.createObjectURL).toHaveBeenCalledTimes(1)
      expect(screen.getByText('Download started')).toBeInTheDocument()
    })

    it('data view: exportPortfolio button stays wired to the useFirebasePortfolio export, separate from the snapshot download', () => {
      const exportPortfolio = vi.fn()
      useFirebasePortfolio.mockReturnValue({ positions, loading: false, exportPortfolio, syncState: { connected: true } })
      const { container } = renderPortfolio('/v2/portfolio?view=data')
      fireEvent.click(screen.getByText('Export portfolio'))
      expect(exportPortfolio).toHaveBeenCalledTimes(1)
      expect(container.querySelector('[data-capability-id="export.portfolio.export-portfolio-json"]')).toBeInTheDocument()
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
        return dataForFile(file)
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

    it('diversification view: shows the theme-exposure-unavailable note when the report has no theme data for held tickers', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=diversification')
      expect(container.querySelector('[data-capability-id="state.diversification.theme-exposure-unavailable"]'))
        .toHaveTextContent('Theme exposure is unavailable in the current research snapshot.')
      expect(container.querySelector('[data-capability-id="chart.diversification.theme-exposure-grid"]')).not.toBeInTheDocument()
    })

    it('performance view: renders the TWR/XIRR/bridge structural rows and the cash-flow form', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=performance')
      ;['control.portfolio.performance-compare-over', 'figure.portfolio.xirr-kpi', 'figure.portfolio.reconciliation-bridge',
        'control.portfolio.ledger-complete-checkbox', 'control.portfolio.cash-flow-ledger']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('insights view: renders the recap hero, comparison state, and trader/timing panels', async () => {
      const { container, findByTestId } = renderPortfolio('/v2/portfolio?view=insights')
      await findByTestId('fake-chart').catch(() => null) // let useRenderer's async loadRenderer settle if it mounted a chart
      ;['figure.insights.mood-hero', 'export.insights.share-today', 'disclosure.insights.index-comparison-methodology',
        'figure.insights.as-a-trader', 'figure.insights.purchase-timing']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
      // No benchmark histories in the fixture, so the cash-flow-aware comparison can't build.
      expect(container.querySelector('[data-capability-id="state.insights.not-enough-history"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="state.insights.no-realized-sales"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="state.insights.entry-timing-insufficient"]')).toBeInTheDocument()
    })

    it('finances view: budget tab renders the KPI row, tab nav, and budget form', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=finances')
      ;['figure.finances.kpi-row', 'nav.finances.tabs', 'control.finances.budget-add-form',
        'state.finances.no-income-items', 'state.finances.no-expense-items', 'action.finances.use-as-retirement-contribution']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('finances view: retirement tab renders assumptions, IRS note, and the account form', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=finances&tab=retirement')
      ;['control.finances.retirement-assumptions', 'control.finances.return-target-slider', 'disclosure.finances.irs-limit-note',
        'control.finances.account-add-form', 'state.finances.no-accounts', 'figure.finances.retirement-kpi-row']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('finances view: pools tab renders the pool form and empty state', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=finances&tab=pools')
      expect(container.querySelector('[data-capability-id="control.finances.pool-add-form"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="state.finances.no-pools"]')).toBeInTheDocument()
      expect(container.querySelector('[data-capability-id="control.finances.deposit-split-preview"]')).toBeInTheDocument()
    })

    it('finances view: pool-bars and contribution-room-bars render through the chart renderer once data exists', () => {
      useFirebaseFinances.mockReturnValue(financesFixture({
        pools: [{ id: 'pool1', name: 'Emergency fund', percent: 40, balance: 1200 }],
        accounts: [{ id: 'acct1', name: 'Fidelity 401(k)', type: '401k', annualContribution: 5000 }],
      }))
      const { container } = renderPortfolio('/v2/portfolio?view=finances&tab=pools')
      expect(container.querySelector('[data-capability-id="chart.finances.pool-bars"]')).toBeInTheDocument()
      const retirement = renderPortfolio('/v2/portfolio?view=finances&tab=retirement')
      expect(retirement.container.querySelector('[data-capability-id="chart.finances.contribution-room-bars"]')).toBeInTheDocument()
    })

    it('planning view: renders the success gauge, live levers, and goal form', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=planning')
      ;['chart.planning.success-probability-gauge', 'figure.planning.dotted-median-target-panel', 'control.planning.track-current-holdings',
        'figure.planning.coast-fire-panel', 'control.planning.track-coast-fire', 'figure.planning.lever-deltas',
        'control.planning.return-target-lever', 'control.planning.contribution-lever', 'control.planning.retirement-age-lever',
        'control.planning.withdrawal-lever', 'control.planning.aggressiveness-select', 'chart.planning.sequence-risk-panel',
        'figure.planning.goals-section', 'control.planning.goal-form', 'disclosure.planning.assumption-not-forecast']
        .forEach((id) => expect(container.querySelector(`[data-capability-id="${id}"]`)).toBeInTheDocument())
    })

    it('planning view: shows the waiting-on-history state before 20 daily observations exist', () => {
      const { container } = renderPortfolio('/v2/portfolio?view=planning')
      expect(container.querySelector('[data-capability-id="state.planning.waiting-on-history"]')).toBeInTheDocument()
    })
  })

  describe('with rich price history (two priced holdings, 90 daily closes)', () => {
    beforeEach(() => {
      useData.mockImplementation(dataForRichFile)
      useFirebasePortfolio.mockReturnValue({ positions: richPositions, loading: false, exportPortfolio: vi.fn(), syncState: { connected: true } })
    })

    // `useRenderer()` resolves `manifest.loadRenderer()` in a `useEffect`, and this fixture's
    // 90-day correlation/rolling-Sharpe/factor-regression arithmetic runs synchronously in the
    // render before that -- comfortably under RTL's default 1000ms in isolation, but not always
    // inside the full suite, so these use a longer explicit timeout rather than the default.
    const FIND_CHART_OPTS = { timeout: 5000 }

    it('data view, historical tab: renders a real rolling-Sharpe line chart, not the insufficient-history message', async () => {
      const { container, findAllByTestId } = renderPortfolio('/v2/portfolio?view=data&analytics=historical')
      await findAllByTestId('fake-chart', {}, FIND_CHART_OPTS)
      const section = container.querySelector('[data-capability-id="chart.portfolio.rolling-sharpe-historical"]')
      expect(section.querySelector('[data-testid="fake-chart"]')).toHaveAttribute('data-metric-id', 'portfolio-rolling-sharpe-60')
      expect(section).not.toHaveTextContent('Rolling Sharpe is insufficient')
    })

    it('diversification view: renders a real correlation heatmap for two correlatable holdings', async () => {
      const { container, findAllByTestId } = renderPortfolio('/v2/portfolio?view=diversification')
      await findAllByTestId('fake-chart', {}, FIND_CHART_OPTS)
      const section = container.querySelector('[data-capability-id="chart.diversification.correlation-heatmap"]')
      expect(section.querySelector('[data-testid="fake-chart"]')).toHaveAttribute('data-metric-id', 'diversification-correlation-heatmap')
    })

    it('diversification view: renders the theme-exposure grid from report.json theme_screen.by_ticker, not the unavailable note', async () => {
      const { container, findAllByTestId } = renderPortfolio('/v2/portfolio?view=diversification')
      await findAllByTestId('fake-chart', {}, FIND_CHART_OPTS)
      const section = container.querySelector('[data-capability-id="chart.diversification.theme-exposure-grid"]')
      expect(section).toHaveTextContent('Digital Payments')
      expect(section).toHaveTextContent('Genomics')
      expect(container.querySelector('[data-capability-id="state.diversification.theme-exposure-unavailable"]')).not.toBeInTheDocument()
    })

    it('data view, algorithm tab: renders the Monte Carlo panel from validation/monte_carlo_projection.json', async () => {
      const { container, findAllByTestId } = renderPortfolio('/v2/portfolio?view=data&analytics=algorithm')
      await findAllByTestId('fake-chart', {}, FIND_CHART_OPTS)
      const section = container.querySelector('[data-capability-id="chart.portfolio.monte-carlo-panel-embed"]')
      expect(section.querySelector('[data-testid="fake-chart"]')).toHaveAttribute('data-metric-id', 'portfolio-monte-carlo-panel')
      expect(section).toHaveTextContent(monteCarloFixture.disclosure)
    })

    it('data view, algorithm tab: renders scenario sensitivity ranking real holdings by published beta', async () => {
      const { container, findAllByTestId } = renderPortfolio('/v2/portfolio?view=data&analytics=algorithm')
      await findAllByTestId('fake-chart', {}, FIND_CHART_OPTS)
      const section = container.querySelector('[data-capability-id="chart.portfolio.scenario-sensitivity"]')
      expect(section).toHaveTextContent('GFC 2008')
      expect(section).toHaveTextContent('AAA')
      expect(section).toHaveTextContent('BBB')
      expect(section).toHaveTextContent('Projected portfolio impact')
    })
  })
})
