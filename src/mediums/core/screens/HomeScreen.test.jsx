import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import HomeScreen from './HomeScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { useAuth } from '../../../lib/FirebaseAuthContext.jsx'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../../../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn(), AuthProvider: ({ children }) => children }))

const fakeManifest = { components: {} }

function renderHome() {
  return render(<MediumProvider value={fakeManifest}><HomeScreen /></MediumProvider>)
}

const REPORT = {
  generated_at: '2026-08-25T12:00:00Z',
  research: [{ ticker: 'AAPL', name: 'Apple Inc.', score: 82 }],
  screen_universe: [], portfolio_coverage: [], benchmark_history: { dates: [] },
}

describe('HomeScreen', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: null })
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
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
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: REPORT, loading: false }
      if (file === 'validation/signal_metrics.json') return { data: { summary: { ready: 44, breached: 9, total: 64 }, live_sample: { days: 18 } }, loading: false }
      if (file === 'validation/research_evidence.json') return { data: { headline: { ic_periods_accumulated: 0, ic_periods_required: 24 } }, loading: false }
      return { data: null, loading: false }
    })
    renderHome()
    // as-of lives inside HomePortfolioPanel, lazy-loaded (Phase 4, NOTES.md) — resolves async
    // even in tests, since React.lazy() always returns a promise.
    await waitFor(() => expect(screen.getByTestId('as-of')).toHaveTextContent('1 names covered'))
    expect(screen.getByTestId('evidence-strip')).toHaveTextContent('44 ready · 9 breached')
    expect(screen.getByTestId('evidence-strip')).toHaveTextContent('18d live')
    expect(screen.getByTestId('promotion-disclosure')).toHaveTextContent('0 of the 24')
  })

  it('shows a sign-in prompt instead of a portfolio value when signed out', async () => {
    useData.mockImplementation((file) => file === 'report.json' ? { data: REPORT, loading: false } : { data: null, loading: false })
    renderHome()
    await waitFor(() => expect(screen.getByText(/Sign in and add holdings/)).toBeInTheDocument())
    expect(screen.queryByTestId('portfolio-value')).not.toBeInTheDocument()
  })

  it('applies the first-viewport capability ids', async () => {
    useData.mockImplementation((file) => file === 'report.json' ? { data: REPORT, loading: false } : { data: null, loading: false })
    const { container } = renderHome()
    await waitFor(() => expect(container.querySelector('[data-capability-id="figure.home.portfolio-hero"]')).toBeInTheDocument())
    expect(container.querySelector('[data-capability-id="chart.home.growth-chart"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.chrome.no-signal-promoted"]')).toBeInTheDocument()
  })
})
