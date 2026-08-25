import { fireEvent, render, screen } from '@testing-library/react'
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
})
