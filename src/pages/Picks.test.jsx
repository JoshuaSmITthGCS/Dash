import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Picks from './Picks'
import { useData } from '../lib/useData'
import { useAlerts } from '../lib/useAlerts'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useWatchlist } from '../lib/useWatchlist'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../lib/useFirebasePortfolio', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../lib/useWatchlist', () => ({ useWatchlist: vi.fn() }))
vi.mock('../lib/useAlerts', () => ({ useAlerts: vi.fn() }))

const stock = (overrides = {}) => ({
  ticker: 'AAPL', name: 'Apple Inc.', sector: 'Technology', is_etf: false,
  score: 62, confidence: 0.44, stance: 'PROMISING', price: 200,
  components: { fundamentals: 65 }, technical_detail: { return_20d: 3 },
  history: { closes: [200, 201] },
  ...overrides,
})

const etf = (overrides = {}) => ({
  ticker: 'VOO', name: 'Vanguard S&P 500 ETF', sector: 'Diversified',
  scores: { overall: 91, quality: 88, performance: 85 }, quality_score: 88,
  returns: { '1m': 2 }, price: 500,
  ...overrides,
})

describe('Picks research page', () => {
  beforeEach(() => {
    useFirebasePortfolio.mockReturnValue({
      positions: [], loading: false, addPosition: vi.fn(),
    })
    useWatchlist.mockReturnValue({
      items: [], loading: false, isWatched: () => false, addTicker: vi.fn(), removeTicker: vi.fn(),
    })
    useAlerts.mockReturnValue({ createRule: vi.fn() })
  })

  it('never sorts a stock and an ETF into the same ranked pool', () => {
    // A fund-model score of 91 must not let an ETF outrank a fundamentals-scored stock of
    // 62 in one shared list -- the two numbers come from incompatible models.
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') {
        return { data: { research: [stock({ score: 62 })] }, loading: false }
      }
      return { data: { etfs: [etf({ scores: { overall: 91, quality: 88, performance: 85 } })] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)

    const stocksSection = screen.getByRole('region', { name: 'Stocks' })
    const etfsSection = screen.getByRole('region', { name: 'ETFs' })
    expect(within(stocksSection).getByText('AAPL')).toBeVisible()
    expect(within(stocksSection).queryByText('VOO')).not.toBeInTheDocument()
    expect(within(etfsSection).getByText('VOO')).toBeVisible()
    expect(within(etfsSection).queryByText('AAPL')).not.toBeInTheDocument()
  })

  it('filtering to Stocks only hides the ETF section entirely', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [etf()] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Filter by asset type'), { target: { value: 'stock' } })

    expect(screen.queryByRole('region', { name: 'ETFs' })).not.toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeVisible()
  })

  it('filtering to ETFs only hides the Stocks section entirely', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [etf()] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Filter by asset type'), { target: { value: 'etf' } })

    expect(screen.queryByRole('region', { name: 'Stocks' })).not.toBeInTheDocument()
    expect(screen.getByText('VOO')).toBeVisible()
  })

  it('the bucket planner allocates across stocks only by default, never blending in an ETF score', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: { research: [stock({ score: 62 })] }, loading: false }
      return { data: { etfs: [etf({ scores: { overall: 91, quality: 88, performance: 85 } })] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByPlaceholderText('Available funds'), { target: { value: '1000' } })

    expect(screen.getByText(/top 1 stocks/)).toBeVisible()
    const bucketList = document.querySelector('.allocation-bucket-list')
    expect(within(bucketList).getByText('AAPL')).toBeVisible()
    expect(within(bucketList).queryByText('VOO')).not.toBeInTheDocument()
  })

  it('shows Buy Now for a buy-worthy pick that is not currently in a decline', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)

    expect(screen.getAllByText('Buy Now').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Set Low Alert/)).not.toBeInTheDocument()
  })

  it('includes a screen-only company (not on the published leaderboard) in the stock pool', () => {
    // The whole point of the strategy lenses: a name that is not a top-40 fundamentals
    // score should still be reachable, not silently dropped because it never made
    // data.research.
    const screenOnly = {
      ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
      components: { fundamentals: 50, news_sentiment: 90 },
      technical_detail: { return_5d: 3, return_20d: 5 },
      insider_activity: { available: true, points: 4 },
    }
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') {
        return { data: { research: [stock({ score: 90 })], screen_universe: [screenOnly] }, loading: false }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)

    const stocksSection = screen.getByRole('region', { name: 'Stocks' })
    expect(within(stocksSection).getAllByText('AAPL').length).toBeGreaterThan(0)
    expect(within(stocksSection).getAllByText('MU').length).toBeGreaterThan(0)
  })

  it('the Short-term catalyst sort can rank a screen-only company above a published leader', () => {
    const strongCatalyst = {
      ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
      components: { fundamentals: 50, news_sentiment: 92 },
      technical_detail: { return_5d: 4, return_20d: 5 },
      insider_activity: { available: true, points: 4 },
    }
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') {
        return {
          data: {
            research: [stock({ score: 90, components: { fundamentals: 90, news_sentiment: 50 } })],
            screen_universe: [strongCatalyst],
          },
          loading: false,
        }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'catalyst' } })

    const tickers = within(document.querySelector('.research-table tbody'))
      .getAllByRole('row').map((row) => row.textContent)
    expect(tickers.findIndex((text) => text.includes('MU')))
      .toBeLessThan(tickers.findIndex((text) => text.includes('AAPL')))
  })

  it('shows Set Low Alert and creates a below-price alert rule for a pick currently down from its highs', async () => {
    const createRule = vi.fn().mockResolvedValue({ success: true })
    useAlerts.mockReturnValue({ createRule })
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') {
        return {
          data: {
            research: [stock({
              price: 81,
              technical_detail: { return_20d: 3, pct_from_52w_high: -19, pct_above_52w_low: 47.3, max_drawdown_252d: -22, return_60d: -12 },
            })],
          },
          loading: false,
        }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    const [alertButton] = screen.getAllByRole('button', { name: /Set Low Alert/ })
    fireEvent.click(alertButton)

    expect(createRule).toHaveBeenCalledWith(expect.objectContaining({
      type: 'price_cross', ticker: 'AAPL', direction: 'below',
    }))
  })
})
