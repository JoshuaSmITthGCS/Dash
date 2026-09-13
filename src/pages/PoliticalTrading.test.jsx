import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PoliticalTrading from './PoliticalTrading'
import { useData } from '../lib/useData'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn() }))

const trade = (overrides = {}) => ({
  chamber: 'senate', representative: 'Jane Doe', district: null, symbol: 'AAPL',
  transaction_type: 'Purchase', amount: '$15,001 - $50,000', amount_upper: 50000,
  transaction_date: '2026-06-01', disclosure_date: '2026-08-01',
  filing_delay_days: 61, flags: ['LATE_FILING'],
  ...overrides,
})

describe('PoliticalTrading page', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: null })
  })

  it('renders disclosures with their flags', () => {
    useData.mockReturnValue({
      data: {
        schema_version: '1.0.0', model_version: 'congress-trades-v1.0.0',
        history_days: 200,
        results: [
          trade(),
          trade({ representative: 'John Smith', chamber: 'house', symbol: 'MSFT', flags: ['OPTIONS_TRADE'] }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: /Political/ })).toBeVisible()
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
    expect(screen.getAllByText('MSFT').length).toBeGreaterThan(0)
    expect(screen.queryByText(/^Jane Doe$/)).not.toBeInTheDocument()
    screen.getAllByText(/AAPL|MSFT/)
      .filter((element) => element.closest('summary'))
      .forEach((element) => fireEvent.click(element.closest('summary')))
    expect(screen.getAllByText(/Jane Doe/).some((element) => element.closest('details')?.open)).toBe(true)
    expect(screen.getAllByText(/John Smith/).some((element) => element.closest('details')?.open)).toBe(true)
    expect(screen.getByText((_, el) => el.className === 'chip' && el.textContent === 'Late filing')).toBeVisible()
    expect(screen.getByText((_, el) => el.className === 'chip' && el.textContent === 'Options trade')).toBeVisible()
  })

  it('plots disclosed volume by month, summing the reported amount-range midpoint', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ transaction_date: '2026-06-01', amount_lower: 15000, amount_upper: 50000 }), // midpoint 32500
          trade({ symbol: 'MSFT', transaction_date: '2026-06-15', amount_lower: 1000, amount_upper: 15000 }), // midpoint 8000
          trade({ symbol: 'GOOG', transaction_date: '2026-07-01', amount_lower: 50000, amount_upper: 100000 }), // midpoint 75000
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByRole('img', { name: /Disclosed volume by period, 2 periods/ })).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Table' })[0])
    expect(screen.getByText('$40,500')).toBeInTheDocument() // 32500 + 8000, June
    expect(screen.getByText('$75,000')).toBeInTheDocument() // July
  })

  it('filters by chamber', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ representative: 'Jane Doe', chamber: 'senate' }),
          trade({ representative: 'John Smith', chamber: 'house', symbol: 'MSFT' }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Chamber'), { target: { value: 'house' } })

    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
    expect(screen.getAllByText('MSFT').length).toBeGreaterThan(0)
    const ticker = screen.getAllByText('MSFT').find((element) => element.closest('summary'))
    fireEvent.click(ticker.closest('summary'))
    expect(screen.getAllByText(/John Smith/).some((element) => element.closest('details')?.open)).toBe(true)
  })

  it('shows an honest empty state when nothing has been collected yet', () => {
    useData.mockReturnValue({ data: { results: [] }, loading: false, error: null })
    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    expect(screen.getByText(/No disclosures collected yet/)).toBeVisible()
  })

  it('shows a filter-specific empty state when filters exclude every row', () => {
    useData.mockReturnValue({ data: { results: [trade({ chamber: 'senate' })] }, loading: false, error: null })
    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Chamber'), { target: { value: 'house' } })
    expect(screen.getByText('No disclosures match these filters.')).toBeVisible()
  })

  it('renders the summary tiles from the published summary block', () => {
    useData.mockReturnValue({
      data: {
        results: [trade()],
        summary: { trades: 36880, filings_estimated: 1774, volume_upper: 2313000000, politicians: 205, issuers: 3085 },
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText('36,880')).toBeVisible()
    expect(screen.getByText('1,774')).toBeVisible()
    expect(screen.getByText('$2.313B')).toBeVisible()
    expect(screen.getByText('205')).toBeVisible()
    expect(screen.getByText('3,085')).toBeVisible()
  })

  it('sorts by performance since purchase and shows the price move', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ representative: 'Laggard', symbol: 'LAG', return_since_purchase_pct: 2 }),
          trade({ representative: 'Winner', symbol: 'WIN', return_since_purchase_pct: 45 }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'performance' } })

    const rows = screen.getAllByRole('row').filter((row) => /WIN|LAG/.test(row.textContent))
    expect(rows[0]).toHaveTextContent('WIN')
  })
  it('renders the politician leaderboard panel, ranked, with backfill coverage', () => {
    useData.mockReturnValue({
      data: {
        results: [trade()],
        politician_performance: {
          price_backfill: { equity_buys_total: 1812, equity_buys_priced: 308, coverage_pct: 17.0 },
          leaderboard: [
            { politician: 'Winner', rank: 1, performance_score: 0.9, win_rate: 0.83,
              avg_alpha_pct: 8.4, n_priced_buys: 12, confidence: 'high' },
            { politician: 'Runner Up', rank: 2, performance_score: 0.5, win_rate: 0.6,
              avg_alpha_pct: 2.1, n_priced_buys: 4, confidence: 'medium' },
          ],
        },
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText('Most profitable politicians')).toBeVisible()
    expect(screen.getByText('Winner')).toBeVisible()
    expect(screen.getByText('Runner Up')).toBeVisible()
    expect(screen.getByText('83%')).toBeVisible()
    expect(screen.getByText(/308 of 1,812 disclosed equity buys priced so far \(17%\)/)).toBeVisible()
    const rows = screen.getAllByRole('row').filter((row) => /Winner|Runner Up/.test(row.textContent))
    expect(rows[0]).toHaveTextContent('Winner')
    expect(rows[1]).toHaveTextContent('Runner Up')
  })

  it('omits the leaderboard panel entirely when nothing has been priced yet', () => {
    useData.mockReturnValue({ data: { results: [trade()] }, loading: false, error: null })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.queryByText('Most profitable politicians')).not.toBeInTheDocument()
  })

  it('shows a weighted signal badge and its underlying performance stats on expand', () => {
    useData.mockReturnValue({
      data: {
        results: [trade({ representative: 'Jane Doe', signal_strength: 0.92, performance_score: 0.9 })],
        politician_performance: {
          leaderboard: [{
            politician: 'Jane Doe', n_priced_buys: 12, avg_alpha_pct: 8.4,
            win_rate: 0.83, performance_score: 0.9, confidence: 'high', rank: 1,
          }],
        },
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    const badge = screen.getAllByText('Strong').find((element) => element.closest('summary'))
    expect(badge).toBeVisible()
    fireEvent.click(badge.closest('summary'))
    const detail = within(badge.closest('details'))
    expect(detail.getByText('83% beat S&P')).toBeVisible()
    expect(detail.getByText(/avg alpha \+8.4pp.*12 priced buys.*high confidence/)).toBeVisible()
  })

  it('labels a filer with no priced buys yet as having no track record, not a false zero', () => {
    useData.mockReturnValue({
      data: { results: [trade({ representative: 'New Filer', signal_strength: 0.1 })] },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    const badge = screen.getAllByText('Weak').find((element) => element.closest('summary'))
    fireEvent.click(badge.closest('summary'))

    expect(screen.getByText('No priced track record yet')).toBeVisible()
  })

  it('sorts by weighted signal strength', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ representative: 'Weak Filer', symbol: 'LOW', signal_strength: 0.1 }),
          trade({ representative: 'Strong Filer', symbol: 'HIGH', signal_strength: 0.95 }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'signal' } })

    const rows = screen.getAllByRole('row').filter((row) => /HIGH|LOW/.test(row.textContent))
    expect(rows[0]).toHaveTextContent('HIGH')
  })

  it('filters by signal tier', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ representative: 'Weak Filer', symbol: 'LOW', signal_strength: 0.1 }),
          trade({ representative: 'Strong Filer', symbol: 'HIGH', signal_strength: 0.95 }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Signal'), { target: { value: 'strong' } })

    expect(screen.queryByText('LOW')).not.toBeInTheDocument()
    expect(screen.getAllByText('HIGH').length).toBeGreaterThan(0)
  })

  it('says the feed failed rather than implying a quiet week', () => {
    useData.mockReturnValue({
      data: {
        status: 'unavailable', reason_code: 'CONGRESS_DISCLOSURE_FEED_UNAVAILABLE',
        collection: { failures: ['senate-latest: FMP senate-latest request failed with HTTP 403'] },
        results: [],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText(/Disclosure feed unavailable/)).toBeVisible()
    expect(screen.getByText(/HTTP 403/)).toBeVisible()
  })

  it('distinguishes an empty publish window from nothing ever collected', () => {
    useData.mockReturnValue({
      data: {
        status: 'unavailable', reason_code: 'NO_DISCLOSURES_IN_PUBLISH_WINDOW',
        publish_window_days: 120, results: [],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText(/No disclosures filed in the trailing 120 days/)).toBeVisible()
  })

  it('keeps the plain waiting message when collection simply has not started', () => {
    useData.mockReturnValue({
      data: { status: 'unavailable', reason_code: 'NO_DISCLOSURES_COLLECTED_YET', results: [] },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText(/No disclosures collected yet/)).toBeVisible()
  })
  it('flags a run that reached only some sources, rather than presenting it as complete', () => {
    useData.mockReturnValue({
      data: {
        status: 'partial', reason_code: 'SOME_SOURCES_UNAVAILABLE',
        collection: { failures: ['fmp-senate: FMP senate-latest request failed with HTTP 402'] },
        results: [trade({ representative: 'Jane Doe' })],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByRole('alert')).toHaveTextContent(/HTTP 402/)
    expect(screen.getByText('Collected from some sources only')).toBeVisible()
    expect(screen.getAllByText(/Jane Doe/).length).toBeGreaterThan(0)
  })

  it('offers a re-run control to a signed-in user, since no other refresh collects this screen', () => {
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' } })
    useData.mockReturnValue({ data: { results: [trade()] }, loading: false, error: null })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByRole('button', { name: /Re-run collection/ })).toBeEnabled()
  })

  it('hides the re-run control when nobody is signed in', () => {
    useData.mockReturnValue({ data: { results: [trade()] }, loading: false, error: null })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.queryByRole('button', { name: /Re-run collection/ })).toBeNull()
  })

  it('shows an executive-branch disclosure with its office and agency, not a district', () => {
    useData.mockReturnValue({
      data: {
        results: [trade({
          chamber: 'executive', representative: 'Donald J Trump', district: null,
          office: 'President', agency: 'White House Office', symbol: 'AAPL',
        })],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
    fireEvent.click(screen.getByText('AAPL').closest('summary'))

    expect(screen.getByText(/President.*White House Office/)).toBeVisible()
    fireEvent.change(screen.getByLabelText('Chamber'), { target: { value: 'executive' } })
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
  })

  it('renders the top signals panel from the published signals block', () => {
    useData.mockReturnValue({
      data: {
        results: [trade()],
        signals: [
          { ticker: 'AAPL', direction: 'BUY', representative: 'Donald J Trump',
            chamber: 'executive', office: 'President', agency: 'White House Office',
            flags: ['CLUSTER_TRADE'], rank: 1 },
          { ticker: 'MSFT', direction: 'SELL', representative: 'Jane Doe',
            chamber: 'senate', district: 'NC05', flags: [], rank: 2 },
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText('Top disclosed signals')).toBeVisible()
    expect(screen.getByText('BUY')).toBeVisible()
    expect(screen.getByText('SELL')).toBeVisible()
    expect(screen.getByText(/Donald J Trump.*President.*White House Office/)).toBeVisible()
    expect(screen.getByText(/Jane Doe.*senate.*NC05/)).toBeVisible()
  })

  it('omits the signals panel entirely when nothing published qualifies', () => {
    useData.mockReturnValue({ data: { results: [trade()], signals: [] }, loading: false, error: null })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.queryByText('Top disclosed signals')).not.toBeInTheDocument()
  })

  it('renders the top-10 unusual-stocks panel from the published top_tickers block', () => {
    useData.mockReturnValue({
      data: {
        results: [trade()],
        top_tickers: [
          { rank: 1, ticker: 'WEIRD', asset_description: 'Weird Co', trade_count: 3,
            buy_count: 3, sell_count: 0, unique_politicians: 3,
            politicians: ['Jane Doe', 'John Smith', 'Ana Lee'],
            disclosed_volume_midpoint: 105000, max_single_trade_amount_upper: 50000,
            flags: ['CLUSTER_TRADE'] },
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.getByText('Top 10 unusual stocks')).toBeVisible()
    expect(screen.getByText('WEIRD')).toBeVisible()
    fireEvent.click(screen.getByText('WEIRD').closest('summary'))
    expect(screen.getByText('Weird Co')).toBeVisible()
    fireEvent.click(screen.getByText('3').closest('summary'))
    expect(screen.getByText(/Jane Doe, John Smith, Ana Lee/)).toBeVisible()
    expect(screen.getByText((_, el) => el.className === 'chip' && el.textContent === 'Cluster trade')).toBeVisible()
  })

  it('omits the top-tickers panel entirely when nothing published qualifies', () => {
    useData.mockReturnValue({ data: { results: [trade()], top_tickers: [] }, loading: false, error: null })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.queryByText('Top 10 unusual stocks')).not.toBeInTheDocument()
  })

  it('leads with the top picks panel: the largest buy from each highest-ranked filer', () => {
    useData.mockReturnValue({
      data: {
        results: [
          // Top Trader's biggest buy is the small, recent one is a decoy - size wins over recency.
          trade({ representative: 'Top Trader', symbol: 'SMALL', transaction_date: '2026-08-01',
            amount_upper: 15000, excess_return_vs_spy_pct: 12.4 }),
          trade({ representative: 'Top Trader', symbol: 'BIG', transaction_date: '2026-01-01', amount_upper: 5000000 }),
          trade({ representative: 'Second Trader', symbol: 'AAPL', transaction_date: '2026-07-15', amount_upper: 50000 }),
          trade({ representative: 'Second Trader', symbol: 'SOLD', transaction_type: 'Sale (Full)', amount_upper: 5000000 }),
          trade({ representative: 'Exec Trader', chamber: 'executive', symbol: 'MSFT', amount_upper: 5000000 }),
        ],
        politician_performance: {
          leaderboard: [
            { politician: 'Top Trader', rank: 1, performance_score: 0.9, win_rate: 0.8,
              avg_alpha_pct: 20, n_priced_buys: 10, confidence: 'high' },
            { politician: 'Second Trader', rank: 2, performance_score: 0.7, win_rate: 0.6,
              avg_alpha_pct: 5, n_priced_buys: 6, confidence: 'medium' },
            { politician: 'Exec Trader', rank: 3, performance_score: 0.5, win_rate: 0.5,
              avg_alpha_pct: 3, n_priced_buys: 4, confidence: 'low' },
          ],
        },
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    const panel = screen.getByLabelText('Top 10 picks from high-alpha traders')
    expect(panel).toHaveTextContent(/largest disclosed buy/i)
    expect(panel).toHaveTextContent('BIG')
    expect(panel).not.toHaveTextContent('SMALL') // smaller buy from the same trader loses to the bigger one
    expect(panel).toHaveTextContent('AAPL')
    expect(panel).not.toHaveTextContent('SOLD') // a sale is not a pick
    expect(panel).not.toHaveTextContent('MSFT') // executive-branch filer excluded

    // Renders before the leaderboard panel further down the page.
    const headings = screen.getAllByRole('heading', { level: 2 }).map((el) => el.textContent)
    expect(headings.indexOf('Top 10 picks from high-alpha traders'))
      .toBeLessThan(headings.indexOf('Most profitable politicians'))
  })

  it('never repeats a ticker: a lower-ranked filer falls through to their next-largest buy', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ representative: 'Top Trader', symbol: 'NVDA', transaction_date: '2026-08-01', amount_upper: 5000000 }),
          // Second Trader's biggest buy duplicates NVDA, already claimed by the higher-ranked filer.
          trade({ representative: 'Second Trader', symbol: 'NVDA', transaction_date: '2026-07-01', amount_upper: 1000000 }),
          trade({ representative: 'Second Trader', symbol: 'AMD', transaction_date: '2026-06-01', amount_upper: 50000 }),
        ],
        politician_performance: {
          leaderboard: [
            { politician: 'Top Trader', rank: 1, performance_score: 0.9, win_rate: 0.8,
              avg_alpha_pct: 20, n_priced_buys: 10, confidence: 'high' },
            { politician: 'Second Trader', rank: 2, performance_score: 0.7, win_rate: 0.6,
              avg_alpha_pct: 5, n_priced_buys: 6, confidence: 'medium' },
          ],
        },
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    const panel = screen.getByLabelText('Top 10 picks from high-alpha traders')
    expect(panel).toHaveTextContent('Top Trader')
    expect(panel).toHaveTextContent('Second Trader')
    expect(within(panel).getAllByText('NVDA').length).toBe(1)
    expect(panel).toHaveTextContent('AMD')
  })

  it('omits the top picks panel when no leaderboard filer has a disclosed buy', () => {
    useData.mockReturnValue({
      data: {
        results: [trade({ representative: 'Jane Doe', transaction_type: 'Sale (Full)' })],
        politician_performance: {
          leaderboard: [{ politician: 'Jane Doe', rank: 1, performance_score: 0.9,
            win_rate: 0.8, avg_alpha_pct: 20, n_priced_buys: 10, confidence: 'high' }],
        },
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)

    expect(screen.queryByText('Top 10 picks from high-alpha traders')).not.toBeInTheDocument()
  })
})

describe('PoliticalTrading tracking panels', () => {
  const profile = (overrides = {}) => ({
    politician: 'Rohit Khanna', canonical_name: 'ro khanna', chambers: ['house'],
    name_variants: [], trades: 388, buys: 200, sells: 188, distinct_symbols: 41,
    disclosed_volume_midpoint: 4_090_000, largest_trade_amount_upper: 100000,
    avg_filing_delay_days: 21.4, late_filings: 3, late_filing_rate: 0.1,
    committee_overlap_trades: 17, committees: ['Armed Services'],
    first_trade_date: '2026-01-02', last_trade_date: '2026-08-30',
    tracked: true, tracked_tiers: ['activity', 'jurisdiction'],
    performance: { avg_alpha_pct: 4.2, win_rate: 0.55, n_priced_buys: 30, confidence: 'high' },
    external: { return_2025_pct: 12.6, trades_2025: 4284 },
    rank: 1, ...overrides,
  })

  const timingRow = (overrides = {}) => ({
    ticker: 'NVDA', asset_description: 'NVIDIA Corp', representative: 'Rohit Khanna',
    chamber: 'house', transaction_type: 'Purchase', transaction_date: '2026-03-01',
    disclosure_date: '2026-03-20', amount: '$50,001 - $100,000', filing_delay_days: 19,
    return_since_purchase_pct: 40, excess_return_vs_spy_pct: 28.5,
    committee_overlap: { committees: ['Armed Services'], sector: 'Technology', basis: 'market_sector' },
    components: { size: 1, committee_overlap: 1, excess_return: 0.8, filing_delay: 0 },
    components_unavailable: ['news_proximity'], unusual_score: 0.72, rank: 1, ...overrides,
  })

  const payload = (overrides = {}) => ({
    schema_version: '1.5.0', model_version: 'congress-trades-v1.6.0', history_days: 150,
    results: [trade({ representative: 'Rohit Khanna', excess_return_vs_spy_pct: 28.5 })],
    politician_activity: [profile()],
    tracking: { tracked_filers: 21, committee_profiles: 67, external_reference_politicians: 48 },
    unusual_timing: {
      config: { max_per_filer: 2 }, weights: {}, news_component_active: false,
      candidates: 3622, results: [timingRow()],
    },
    ...overrides,
  })

  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: null })
  })

  const renderWith = (data) => {
    useData.mockReturnValue({ data, loading: false, error: null })
    render(<MemoryRouter><PoliticalTrading /></MemoryRouter>)
  }

  it('ranks filers by disclosed activity, separately from the performance leaderboard', () => {
    renderWith(payload())
    const panel = screen.getByLabelText('Most active political traders')
    expect(panel).toHaveTextContent('388 (200b / 188s)')
    expect(panel).toHaveTextContent('41')
    expect(panel).toHaveTextContent('$4.1M')
    expect(panel).toHaveTextContent('21.4d')
  })

  it('says how many filers have curated committee data, so a blank column is not a finding', () => {
    renderWith(payload())
    expect(screen.getByLabelText('Most active political traders'))
      .toHaveTextContent(/curated by hand for 67 filer\(s\).*never "no overlap"/)
  })

  it('shows a dash rather than a zero when a filer has no curated committees', () => {
    renderWith(payload({
      politician_activity: [profile({ committees: [], committee_overlap_trades: 0 })],
    }))
    expect(screen.getByLabelText('Most active political traders')).not.toHaveTextContent('In their jurisdiction0')
  })

  it('narrows only its own table when tracked filers are filtered', () => {
    renderWith(payload({
      politician_activity: [profile(), profile({
        politician: 'Jane Doe', canonical_name: 'jane doe', tracked: false,
        tracked_tiers: [], external: null, performance: null, rank: 2,
      })],
    }))
    const panel = screen.getByLabelText('Most active political traders')
    expect(panel).toHaveTextContent('Jane Doe')
    fireEvent.click(screen.getByLabelText(/Show tracked filers only/))
    expect(screen.getByLabelText('Most active political traders')).not.toHaveTextContent('Jane Doe')
    // The disclosure table below keeps its own, independent filter.
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
  })

  it('labels the external return as third-party and names its source', () => {
    renderWith(payload({
      politician_performance: {
        leaderboard: [{
          politician: 'Rohit Khanna', n_priced_buys: 30, avg_alpha_pct: 4.2, win_rate: 0.55,
          performance_score: 0.6, confidence: 'high', rank: 1,
          external_return_2025_pct: 12.6, tracked: true, tracked_tiers: ['activity'],
        }],
        external_source: {
          publisher: 'Unusual Whales', publication: 'Congress Trading Report 2025',
          as_of: '2025-12-29', benchmark_symbol: 'SPY', benchmark_return_pct: 16.8,
          methodology: 'Estimated from disclosure midpoints.',
        },
      },
    }))
    const panel = screen.getByLabelText('Most profitable politicians')
    expect(panel).toHaveTextContent('2025 return (external)')
    expect(panel).toHaveTextContent('+12.6%')
    expect(panel).toHaveTextContent(/Unusual Whales.*as of 2025-12-29.*not produced by this pipeline/)
  })

  it('ranks unusual disclosures by what is unusual about them, not by a verdict', () => {
    renderWith(payload())
    const panel = screen.getByLabelText('Disclosures unusual on several axes')
    expect(panel).toHaveTextContent('0.72')
    expect(panel).toHaveTextContent('Size 100%')
    expect(panel).toHaveTextContent('Committee jurisdiction 100%')
    expect(panel).toHaveTextContent('Beat the S&P 80%')
    // A component measured at zero is not worth a chip; only what is actually unusual.
    expect(panel).not.toHaveTextContent('Disclosure lag')
    expect(panel).toHaveTextContent(/not a finding of wrongdoing/i)
  })

  it('says an inactive news component is unmeasured rather than scoring it as zero', () => {
    renderWith(payload())
    expect(screen.getByLabelText('Disclosures unusual on several axes'))
      .toHaveTextContent(/news feed is not live.*unmeasured, not zero/)
  })

  it('omits the news caveat when the feed is live', () => {
    renderWith(payload({
      unusual_timing: { ...payload().unusual_timing, news_component_active: true },
    }))
    expect(screen.getByLabelText('Disclosures unusual on several axes'))
      .not.toHaveTextContent(/unmeasured, not zero/)
  })

  it('filters the disclosure table to one filer', () => {
    renderWith(payload({
      results: [
        trade({ representative: 'Rohit Khanna', symbol: 'NVDA' }),
        trade({ representative: 'Jane Doe', symbol: 'AAPL' }),
      ],
    }))
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
    fireEvent.change(screen.getByLabelText('Filer'), { target: { value: 'Rohit Khanna' } })
    expect(screen.getAllByText('NVDA').length).toBeGreaterThan(0)
    expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
  })

  it('shows excess return against the S&P beside the raw return', () => {
    // The unusual-timing panel renders the same figure, so it is emptied here to keep the
    // assertion pinned to the disclosure table's own column.
    renderWith(payload({
      results: [trade({ return_since_purchase_pct: 40, excess_return_vs_spy_pct: 28.5 })],
      unusual_timing: { ...payload().unusual_timing, results: [] },
    }))
    expect(screen.getByText(/\+40/)).toBeVisible()
    expect(screen.getByText(/\+28\.5/)).toBeVisible()
  })

  it('renders nothing for the new panels when the payload predates them', () => {
    renderWith({ schema_version: '1.4.0', results: [trade()] })
    expect(screen.queryByLabelText('Most active political traders')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Disclosures unusual on several axes')).not.toBeInTheDocument()
  })
})
