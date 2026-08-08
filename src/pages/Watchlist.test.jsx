import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Watchlist from './Watchlist'
import { useData } from '../lib/useData'
import { useWatchlist } from '../lib/useWatchlist.js'
import { useAlerts } from '../lib/useAlerts.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../lib/useWatchlist.js', () => ({ useWatchlist: vi.fn() }))
vi.mock('../lib/useAlerts.js', () => ({ useAlerts: vi.fn() }))
vi.mock('../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn() }))
vi.mock('../lib/PreferencesContext.jsx', () => ({ usePreferences: vi.fn() }))

// Clears rankMomentum's gate: positive 5-day and 20-day return, plus the technical fields
// its rankScore reads.
const momentumStock = {
  ticker: 'MOM', name: 'Momentum Co', price: 100, score: 72, confidence: 0.8,
  components: { fundamentals: 80, market_behavior: 70, news_sentiment: 60 },
  technical_detail: {
    return_20d: 12, return_5d: 4, momentum_12_1: 65, relative_strength: 60,
    volume_confirmation: 55, risk_adjusted: 55, annualized_volatility: 20,
  },
  recommendation: { action: 'BUY' },
  analyst_consensus_target: 130, analyst_count: 10,
  history: { closes: [90, 95, 100] },
}

// Clears rankReversal's gate: positive 5-day bounce inside a negative 20-day drawdown, with
// a fundamentals score at or above the 50 floor.
const reversalStock = {
  ticker: 'REV', name: 'Reversal Co', price: 50, score: 55, confidence: 0.6,
  components: { fundamentals: 60, market_behavior: 40, news_sentiment: 50 },
  technical_detail: { return_20d: -10, return_5d: 3, drawdown_60d: -20, annualized_volatility: 25 },
  recommendation: { action: 'HOLD' },
  analyst_consensus_target: 55, analyst_count: 8,
  history: { closes: [60, 55, 50] },
}

// Flat technicals clear neither screen's gate, but a high score/confidence/BUY guidance
// gives it the best setup-quality score of the three - used to prove the value sort.
const neutralStock = {
  ticker: 'NEU', name: 'Neutral Co', price: 200, score: 90, confidence: 0.9,
  components: { fundamentals: 90, market_behavior: 50, news_sentiment: 50 },
  technical_detail: { return_20d: 0, return_5d: 0, annualized_volatility: 15 },
  recommendation: { action: 'BUY' },
  analyst_consensus_target: 202, analyst_count: 12,
  history: { closes: [200, 200, 200] },
}

const cardOrder = () => [...document.querySelectorAll('.watchlist-card-head strong')].map((node) => node.textContent)

describe('Watchlist filtering and sorting', () => {
  beforeEach(() => {
    localStorage.clear()
    useAlerts.mockReturnValue({ createRule: vi.fn() })
    usePreferences.mockReturnValue({ preferences: { watchlistSizingMode: 'capped' } })
  })

  it('prompts sign-in instead of the grid when signed out', () => {
    useAuth.mockReturnValue({ currentUser: null })
    useWatchlist.mockReturnValue({ items: [], loading: false, isWatched: () => false, addTicker: vi.fn(), removeTicker: vi.fn(), updateTargets: vi.fn() })
    useData.mockReturnValue({ data: { research: [] }, loading: false, reload: vi.fn() })

    render(<MemoryRouter><Watchlist /></MemoryRouter>)

    expect(screen.getByText(/Sign in to save a watchlist/)).toBeVisible()
  })

  it('shows a match count per research screen and filters the grid to the selected one', () => {
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' } })
    useWatchlist.mockReturnValue({
      items: [
        { ticker: 'NEU', addedAt: '2026-01-03' },
        { ticker: 'MOM', addedAt: '2026-01-02' },
        { ticker: 'REV', addedAt: '2026-01-01' },
      ],
      loading: false, isWatched: () => true, addTicker: vi.fn(), removeTicker: vi.fn(), updateTargets: vi.fn(),
    })
    useData.mockReturnValue({ data: { research: [momentumStock, reversalStock, neutralStock] }, loading: false, reload: vi.fn() })

    render(<MemoryRouter><Watchlist /></MemoryRouter>)

    expect(cardOrder()).toEqual(['NEU', 'MOM', 'REV'])
    expect(screen.getByRole('button', { name: /^Momentum \(1\)$/ })).toBeVisible()
    expect(screen.getByRole('button', { name: /^Reversal \(1\)$/ })).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: /^Momentum \(1\)$/ }))

    expect(cardOrder()).toEqual(['MOM'])
    expect(screen.queryByText('REV')).not.toBeInTheDocument()
    expect(screen.queryByText('NEU')).not.toBeInTheDocument()
    expect(screen.getByText(/of 3 shown/)).toBeVisible()
  })

  it('sorting by setup quality puts the highest-scoring name first, independent of add order', () => {
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' } })
    useWatchlist.mockReturnValue({
      items: [
        { ticker: 'REV', addedAt: '2026-01-03' },
        { ticker: 'MOM', addedAt: '2026-01-02' },
        { ticker: 'NEU', addedAt: '2026-01-01' },
      ],
      loading: false, isWatched: () => true, addTicker: vi.fn(), removeTicker: vi.fn(), updateTargets: vi.fn(),
    })
    useData.mockReturnValue({ data: { research: [momentumStock, reversalStock, neutralStock] }, loading: false, reload: vi.fn() })

    render(<MemoryRouter><Watchlist /></MemoryRouter>)

    expect(cardOrder()).toEqual(['REV', 'MOM', 'NEU'])

    fireEvent.change(screen.getByLabelText('Sort watchlist'), { target: { value: 'setup' } })

    expect(cardOrder()[0]).toBe('NEU')
  })
})
