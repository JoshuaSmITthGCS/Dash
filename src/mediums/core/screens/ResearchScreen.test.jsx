import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ResearchScreen from './ResearchScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { useWatchlist } from '../../../lib/useWatchlist.js'
import { useAlerts } from '../../../lib/useAlerts.js'
import { useAuth } from '../../../lib/FirebaseAuthContext.jsx'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../../../lib/useWatchlist.js', () => ({ useWatchlist: vi.fn() }))
vi.mock('../../../lib/useAlerts.js', () => ({ useAlerts: vi.fn() }))
vi.mock('../../../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn(), AuthProvider: ({ children }) => children }))

const fakeManifest = { components: {} }

function renderResearch(initialPath = '/v2/research') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <MediumProvider value={fakeManifest}><ResearchScreen /></MediumProvider>
    </MemoryRouter>
  )
}

const REPORT = { research: [{ ticker: 'AAPL', name: 'Apple Inc.', score: 82 }, { ticker: 'MSFT', name: 'Microsoft', score: 75 }] }

// Clears the confidence gate (isActionable/allowsConviction) and the ATTRACTIVE/PROMISING
// entry-timing eligibility so column.research.timing renders a real verdict, not '–'.
const stock = (overrides = {}) => ({
  ticker: 'AAPL', name: 'Apple Inc.', sector: 'Technology', is_etf: false,
  score: 82, data_coverage: 0.9, stance: 'ATTRACTIVE', price: 200,
  components: { fundamentals: 78 }, technical_detail: { return_20d: 3.4 },
  history: { closes: [198, 200], dates: ['2026-08-24', '2026-08-25'] },
  recommendation: { action: 'HOLD' },
  strengths: ['Strong balance sheet'], risks: ['Regulatory scrutiny'],
  ...overrides,
})

describe('ResearchScreen', () => {
  beforeEach(() => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false, addPosition: vi.fn() })
    useWatchlist.mockReturnValue({
      items: [], loading: false, isWatched: () => false, addTicker: vi.fn(), removeTicker: vi.fn(), updateTargets: vi.fn(),
    })
    useAlerts.mockReturnValue({ createRule: vi.fn() })
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' }, authError: null, retryAuth: vi.fn() })
  })

  it('reads the ?q= param on mount — the Alerts deep-link fix', () => {
    useData.mockReturnValue({ data: REPORT, loading: false })
    renderResearch('/v2/research?q=MSFT')
    expect(screen.getByTestId('result-count')).toHaveTextContent('1 result')
    expect(within(screen.getByTestId('research-results')).getByText(/MSFT/)).toBeInTheDocument()
  })

  it('shows every result with no query', () => {
    useData.mockReturnValue({ data: REPORT, loading: false })
    renderResearch()
    expect(screen.getByTestId('result-count')).toHaveTextContent('2 results')
  })

  it('shows the empty state for a query matching nothing', () => {
    useData.mockReturnValue({ data: REPORT, loading: false })
    renderResearch('/v2/research?q=ZZZZ')
    expect(document.querySelector('[data-capability-id="state.research.empty"]')).toHaveTextContent('No companies match those filters.')
  })

  it('renders the ranked pool with per-column capability ids and per-row actions', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch()
    const row = screen.getByTestId('research-row-AAPL')
    expect(row.querySelector('[data-capability-id="column.research.rank"]')).toHaveTextContent('#1')
    expect(row.querySelector('[data-capability-id="column.research.stance"]')).toHaveTextContent('ATTRACTIVE')
    expect(row.querySelector('[data-capability-id="column.research.fundamentals"]')).toHaveTextContent('78')
    expect(row.querySelector('[data-capability-id="column.research.20d-return"]')).toBeInTheDocument()
    expect(row.querySelector('[data-capability-id="column.research.confidence"]')).toHaveTextContent('90%')
    expect(row.querySelector('[data-capability-id="disclosure.research.as-of-line"]')).toBeInTheDocument()
    expect(row.querySelector('[data-capability-id="action.research.buy-100"]')).toBeInTheDocument()
    expect(row.querySelector('[data-capability-id="control.research.watchlist-toggle"]')).toBeInTheDocument()
  })

  it('filtering by sector updates the URL and narrows the pool', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') {
        return { data: { research: [stock(), stock({ ticker: 'XOM', name: 'Exxon', sector: 'Energy' })] }, loading: false }
      }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch()
    const toggle = screen.getByRole('checkbox', { name: /Filter by sector/ })
    fireEvent.click(toggle)
    const group = screen.getByRole('group', { name: 'Sectors to include' })
    fireEvent.click(within(group).getByLabelText('Energy'))
    expect(screen.queryByTestId('research-row-XOM')).not.toBeInTheDocument()
    expect(screen.getByTestId('research-row-AAPL')).toBeInTheDocument()
  })

  it('selecting a ranking model shows the model coverage panel and model-score-why column', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch()
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'fundamentals' } })
    expect(document.querySelector('[data-capability-id="figure.research.model-summary"]')).toBeInTheDocument()
  })

  it('an ETF-only filter under an active ranking model shows the mismatch state', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [{ ticker: 'VOO', name: 'Vanguard S&P 500', scores: { overall: 90 }, price: 400 }] }, loading: false }
    })
    renderResearch('/v2/research?sort=fundamentals&assetType=etf')
    expect(document.querySelector('[data-capability-id="state.research.etf-model-mismatch"]')).toBeInTheDocument()
  })

  it('opens an inline research detail panel and closes it', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch()
    fireEvent.click(within(screen.getByTestId('research-row-AAPL')).getByText('Open research'))
    expect(screen.getByTestId('research-detail')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Close research detail'))
    expect(screen.queryByTestId('research-detail')).not.toBeInTheDocument()
  })

  it('switches to the watchlist view and shows the signed-out state when no user', () => {
    useAuth.mockReturnValue({ currentUser: null, authError: 'Not signed in', retryAuth: vi.fn() })
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch()
    fireEvent.click(screen.getByTestId('view-tab-watchlist'))
    expect(document.querySelector('[data-capability-id="state.research.watchlist-signed-out"]')).toHaveTextContent('Not signed in')
  })

  it('shows the watchlist empty state when signed in with no saved names', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch('/v2/research?view=watchlist')
    expect(document.querySelector('[data-capability-id="state.research.watchlist-empty"]')).toBeInTheDocument()
  })

  it('renders a saved watchlist name with its price-target editor and lens chips', () => {
    useWatchlist.mockReturnValue({
      items: [{ ticker: 'AAPL', addedAt: '2026-08-01', dipPrice: null, goodBuyPrice: null }],
      loading: false, isWatched: () => true, addTicker: vi.fn(), removeTicker: vi.fn(), updateTargets: vi.fn(),
    })
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch('/v2/research?view=watchlist')
    expect(screen.getByTestId('watchlist-row-AAPL')).toBeInTheDocument()
    expect(document.querySelector('[data-capability-id="control.research.price-target-editor"]')).toBeInTheDocument()
    expect(document.querySelector('[data-capability-id="figure.research.watchlist-lens-chips"]')).toBeInTheDocument()
  })

  it('a saved ticker with no published research shows the no-quote state', () => {
    useWatchlist.mockReturnValue({
      items: [{ ticker: 'ZZZZ', addedAt: '2026-08-01', dipPrice: null, goodBuyPrice: null }],
      loading: false, isWatched: () => true, addTicker: vi.fn(), removeTicker: vi.fn(), updateTargets: vi.fn(),
    })
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })
    renderResearch('/v2/research?view=watchlist')
    expect(document.querySelector('[data-capability-id="state.research.watchlist-no-quote"]')).toBeInTheDocument()
  })
})
