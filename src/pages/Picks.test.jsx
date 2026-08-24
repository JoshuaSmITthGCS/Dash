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
  // Above the 0.75 conviction band: entry-timing verdicts and action labels are gated on
  // confidence, so a fixture below it would never carry either.
  score: 62, data_coverage: 0.82, stance: 'PROMISING', price: 200,
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
      if (file === 'report.json') {
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
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [etf()] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Filter by asset type'), { target: { value: 'stock' } })

    expect(screen.queryByRole('region', { name: 'ETFs' })).not.toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeVisible()
  })

  it('filtering to ETFs only hides the Stocks section entirely', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
      return { data: { etfs: [etf()] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Filter by asset type'), { target: { value: 'etf' } })

    expect(screen.queryByRole('region', { name: 'Stocks' })).not.toBeInTheDocument()
    expect(screen.getByText('VOO')).toBeVisible()
  })

  describe('sector filter toggle', () => {
    const techStock = stock({ ticker: 'AAPL', name: 'Apple Inc.', sector: 'Technology' })
    const healthStock = stock({ ticker: 'JNJ', name: 'Johnson & Johnson', sector: 'Healthcare' })

    beforeEach(() => {
      useData.mockImplementation((file) => {
        if (file === 'report.json') return { data: { research: [techStock, healthStock] }, loading: false }
        return { data: { etfs: [] }, loading: false }
      })
    })

    it('shows every sector by default, with the toggle off and no checkboxes visible', () => {
      render(<MemoryRouter><Picks /></MemoryRouter>)

      expect(screen.getByText('AAPL')).toBeVisible()
      expect(screen.getByText('JNJ')).toBeVisible()
      expect(screen.queryByLabelText('Technology')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Healthcare')).not.toBeInTheDocument()
    })

    it('turning the toggle on seeds every sector checked, so nothing disappears yet', () => {
      render(<MemoryRouter><Picks /></MemoryRouter>)

      fireEvent.click(screen.getByLabelText(/Filter by sector/))

      expect(screen.getByLabelText('Technology')).toBeChecked()
      expect(screen.getByLabelText('Healthcare')).toBeChecked()
      expect(screen.getByText('AAPL')).toBeVisible()
      expect(screen.getByText('JNJ')).toBeVisible()
    })

    it('unchecking one sector removes only that sector\'s names', () => {
      render(<MemoryRouter><Picks /></MemoryRouter>)
      fireEvent.click(screen.getByLabelText(/Filter by sector/))

      fireEvent.click(screen.getByLabelText('Healthcare'))

      expect(screen.getByText('AAPL')).toBeVisible()
      expect(screen.queryByText('JNJ')).not.toBeInTheDocument()
    })

    it('turning the toggle back off restores the unfiltered view regardless of checkbox state', () => {
      render(<MemoryRouter><Picks /></MemoryRouter>)
      const masterToggle = screen.getByLabelText(/Filter by sector/)
      fireEvent.click(masterToggle)
      fireEvent.click(screen.getByLabelText('Healthcare'))
      expect(screen.queryByText('JNJ')).not.toBeInTheDocument()

      fireEvent.click(masterToggle)

      expect(screen.getByText('AAPL')).toBeVisible()
      expect(screen.getByText('JNJ')).toBeVisible()
      expect(screen.queryByLabelText('Technology')).not.toBeInTheDocument()
    })

    it('re-enabling the toggle re-seeds every sector checked, discarding the prior partial selection', () => {
      // Documents the chosen persistence behavior (reset-to-all-checked, not restore-last-selection).
      render(<MemoryRouter><Picks /></MemoryRouter>)
      const masterToggle = screen.getByLabelText(/Filter by sector/)
      fireEvent.click(masterToggle)
      fireEvent.click(screen.getByLabelText('Healthcare'))
      fireEvent.click(masterToggle)

      fireEvent.click(masterToggle)

      expect(screen.getByLabelText('Healthcare')).toBeChecked()
      expect(screen.getByText('JNJ')).toBeVisible()
    })
  })

  it('the bucket planner allocates across stocks only by default, never blending in an ETF score', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [stock({ score: 62 })] }, loading: false }
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
      if (file === 'report.json') return { data: { research: [stock()] }, loading: false }
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
      if (file === 'report.json') {
        return { data: { research: [stock({ score: 90 })], screen_universe: [screenOnly] }, loading: false }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)

    const stocksSection = screen.getByRole('region', { name: 'Stocks' })
    expect(within(stocksSection).getAllByText('AAPL').length).toBeGreaterThan(0)
    expect(within(stocksSection).getAllByText('MU').length).toBeGreaterThan(0)
  })

  it('a ranking model returns its own screened list, not the research leaderboard re-sorted', () => {
    // The bug this guards: selecting a lens used to re-sort the same rows, so a published
    // leader with no catalyst at all still sat in the list (just lower down), and the top
    // of the page still looked like the fundamentals leaderboard. A lens is a screen - a
    // name that does not clear its bar is absent, not ranked last.
    const strongCatalyst = {
      ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
      components: { fundamentals: 50 },
      technical_detail: { return_5d: 4, return_20d: 5 },
      evidence_summary: {
        event_count: 1, news_score: 92, dominant_age_trading_days: 0,
        insider_score: 84, insider_freshest_age_trading_days: 2,
        expectation_score: 80, expectation_inputs_resolved: 3,
      },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') {
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

    const table = within(document.querySelector('.research-table tbody'))
    const tickers = table.getAllByRole('row').map((row) => row.textContent)
    expect(tickers.some((text) => text.includes('MU'))).toBe(true)
    expect(tickers.some((text) => text.includes('AAPL'))).toBe(false)
  })

  it('renders 15 columns by default and 17 when a ranking model is active', () => {
    useData.mockImplementation((file) => {
      if (file === 'report.json') {
        return {
          data: {
            research: [stock({ score: 90 })],
            screen_universe: [{
              ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
              components: { fundamentals: 50 }, technical_detail: { return_5d: 4, return_20d: 5 },
              evidence_summary: { event_count: 1, news_score: 92, dominant_age_trading_days: 0 },
            }],
          },
          loading: false,
        }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    const headerCount = () => within(document.querySelector('.research-table thead')).getAllByRole('columnheader').length
    expect(headerCount()).toBe(15)

    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'catalyst' } })
    expect(headerCount()).toBe(17)
  })

  it('a model list is capped at the top 20 even when far more names clear the gate', () => {
    const qualifier = (index) => ({
      ticker: `T${index}`, name: `Ticker ${index}`, sector: 'Technology', industry: 'Semiconductors',
      score: 50, components: { fundamentals: 60 },
      technical_detail: {
        return_5d: 1 + index / 100, return_20d: 5, return_60d: 8,
        momentum_12_1: 60, momentum_12_1_pct: 10 + index, volume_confirmation: 60,
        risk_adjusted: 60, drawdown_60d: -8, pct_from_52w_high: -5,
      },
    })
    useData.mockImplementation((file) => {
      if (file === 'report.json') {
        return {
          data: { research: [], screen_universe: Array.from({ length: 40 }, (_, index) => qualifier(index)) },
          loading: false,
        }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'momentum' } })

    expect(within(document.querySelector('.research-table tbody')).getAllByRole('row')).toHaveLength(20)
    expect(screen.getByText(/Showing the top 20 of 40 companies that clear it/)).toBeVisible()
  })

  it('states which components produced the score under the active model', () => {
    // "Some of these are not even showing why they are reversals" - the Reversal chip used
    // to be the whole explanation.
    const bouncing = {
      ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
      components: { fundamentals: 63 },
      technical_detail: { return_5d: 6.6, return_20d: -10.4, drawdown_60d: -27.7 },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [], screen_universe: [bouncing] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'reversal' } })

    expect(screen.getAllByText(/volatility-scaled price shock/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/statistical overextension/i).length).toBeGreaterThan(0)
  })

  it('counts the reasons the rest of the universe did not clear the gate', () => {
    // A short list because the data is dark and a short list because few names are
    // attractive look identical otherwise.
    const scorable = {
      ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
      components: { fundamentals: 63 },
      technical_detail: { return_5d: 6.6, return_20d: -10.4, drawdown_60d: -27.7 },
    }
    const noDrawdown = {
      ticker: 'NDD', name: 'No Drawdown Co', sector: 'Technology', score: 50,
      components: { fundamentals: 70 },
      technical_detail: { return_5d: 4, return_20d: -8 },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [], screen_universe: [scorable, noDrawdown] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'reversal' } })

    expect(screen.getByText(/1 of 2 did not clear the gate/)).toBeVisible()
    expect(screen.getAllByText(/no 60-day drawdown published for this row/).length).toBeGreaterThan(0)
  })

  it('never shows an action label beside a row with no data coverage', () => {
    // Straight from the screenshot: VRT displayed "Data coverage 0%", "HOLD" and "BUY NOW"
    // at the same time.
    const lightweight = {
      ticker: 'VRT', name: 'Vertiv Holdings', sector: 'Industrials', score: 63,
      stance: 'PROMISING', price: 100,
      components: { fundamentals: 65 },
      technical_detail: { return_20d: -14.6, pct_from_52w_high: -2, pct_above_52w_low: 129, return_60d: 5 },
      recommendation: { action: 'HOLD', agreement_count: 2 },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [], screen_universe: [lightweight] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)

    expect(screen.queryByText('Buy Now')).not.toBeInTheDocument()
    expect(screen.getAllByText(/INSUFFICIENT DATA/).length).toBeGreaterThan(0)
    // And it says so where Buy Now used to be, rather than leaving an unexplained blank.
    expect(screen.getAllByText('No timing call').length).toBeGreaterThan(0)
  })

  it('shows a missing data coverage as – rather than a measured 0%', () => {
    // A lightweight universe row has no confidence at all; rendering it as 0% reads as
    // "we measured this and it is terrible."
    const lightweight = {
      ticker: 'MU', name: 'Micron', sector: 'Technology', score: 50,
      components: { fundamentals: 63 }, technical_detail: { return_20d: -10.4 },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [], screen_universe: [lightweight] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)

    const table = document.querySelector('.research-table')
    expect(within(table).queryByText('0%')).not.toBeInTheDocument()
    expect(within(table).getAllByText('Lighter data').length).toBeGreaterThan(0)
  })

  it('a well-evidenced catalyst outranks a thin one with a higher raw reading', () => {
    // Confidence shrinkage: a 99 resting on one stray headline must not outrank a 78 backed
    // by news, insider activity and revisions that all resolved.
    const thinButHighReading = {
      ticker: 'THIN', name: 'Thin Co', sector: 'Technology', score: 50,
      components: { fundamentals: 50 },
      technical_detail: { return_5d: 5, return_20d: 2 },
      evidence_summary: { event_count: 1, news_score: 99, dominant_age_trading_days: 0 },
    }
    const wellEvidenced = {
      ticker: 'SOLID', name: 'Solid Co', sector: 'Technology', score: 50,
      components: { fundamentals: 50 },
      technical_detail: { return_5d: 1, return_20d: 2 },
      evidence_summary: {
        event_count: 3, news_score: 78, dominant_age_trading_days: 0,
        insider_score: 80, insider_freshest_age_trading_days: 1,
        expectation_score: 76, expectation_inputs_resolved: 3,
      },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') {
        return { data: { research: [], screen_universe: [thinButHighReading, wellEvidenced] }, loading: false }
      }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'catalyst' } })

    const tickers = within(document.querySelector('.research-table tbody'))
      .getAllByRole('row').map((row) => row.textContent)
    expect(tickers.findIndex((text) => text.includes('SOLID')))
      .toBeLessThan(tickers.findIndex((text) => text.includes('THIN')))
    expect(within(document.querySelector('.research-table')).getAllByText('Thin evidence').length)
      .toBeGreaterThan(0)
  })

  it('the Thin evidence chip does not appear under a plain column sort', () => {
    const thin = {
      ticker: 'THIN', name: 'Thin Co', sector: 'Technology', score: 50,
      components: { fundamentals: 50 },
      technical_detail: { return_5d: 5, return_20d: 2 },
      evidence_summary: { event_count: 1, news_score: 95 },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [], screen_universe: [thin] }, loading: false }
      return { data: { etfs: [] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    // Default is a column sort - no model ran, so there is no model confidence to warn about.
    expect(screen.queryByText('Thin evidence')).not.toBeInTheDocument()
  })

  it('never scores a fund under a per-security model, even when its row omits the ETF flag', () => {
    // The lightweight screen_universe projection used to drop `is_etf`, so VOO competed in
    // screens that gate on per-security fundamentals no fund reports - and briefly was the
    // only name clearing the catalyst screen in the published dataset.
    const fundWithoutFlag = {
      ticker: 'VOO', name: 'Vanguard S&P 500 ETF', sector: 'Diversified', score: 70,
      components: { fundamentals: 60 },
      technical_detail: { return_5d: 3, return_20d: 5 },
      evidence_summary: { event_count: 1, news_score: 90, dominant_age_trading_days: 0 },
    }
    useData.mockImplementation((file) => {
      if (file === 'report.json') return { data: { research: [], screen_universe: [fundWithoutFlag] }, loading: false }
      return { data: { etfs: [etf()] }, loading: false }
    })

    render(<MemoryRouter><Picks /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort research'), { target: { value: 'catalyst' } })

    expect(document.querySelector('.research-table')).toBeNull()
    expect(screen.getByText(/No company clears this model's gate/)).toBeVisible()
  })

  it('shows Set Low Alert and creates a below-price alert rule for a pick currently down from its highs', async () => {
    const createRule = vi.fn().mockResolvedValue({ success: true })
    useAlerts.mockReturnValue({ createRule })
    useData.mockImplementation((file) => {
      if (file === 'report.json') {
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
