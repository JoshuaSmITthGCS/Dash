import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MarketsScreen from './MarketsScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const fakeManifest = { components: {} }

const reportFixture = {
  market: { macro: { regime: { label: 'supportive' } } },
  research: [
    {
      ticker: 'AAPL', name: 'Apple Inc.', sector: 'Technology', price: 210,
      analytics_history: { closes: [200, 210] }, technical_detail: { return_20d: 3.5 },
    },
    {
      ticker: 'XOM', name: 'Exxon Mobil', sector: 'Energy', price: 90,
      analytics_history: { closes: [100, 90] }, technical_detail: { return_20d: -2.1 },
    },
  ],
  portfolio_coverage: [],
}

const spyFixture = { price_series: { fund: [{ date: '2026-08-24', adjusted_close: 550 }, { date: '2026-08-25', adjusted_close: 560 }] } }
const flatEtfFixture = { price_series: { fund: [{ date: '2026-08-24', adjusted_close: 100 }, { date: '2026-08-25', adjusted_close: 100 }] } }
const singlePointEtfFixture = { price_series: { fund: [{ date: '2026-08-25', adjusted_close: 560 }] } }

const advisorFixture = {
  market: { status: [{ region: 'United States', market_type: 'Equity', current_status: 'Open', primary_exchanges: 'NYSE, Nasdaq', local_open: '9:30am', local_close: '4:00pm' }] },
  research: [{ ticker: 'AAPL' }],
  news: [
    { ticker: 'AAPL', title: 'Apple beats estimates', summary: 'Strong quarter.', url: 'https://example.com/aapl', published_at: '2026-08-25T12:00:00Z' },
    { ticker: 'ZZZ', title: 'Discovery co. surges', summary: 'New coverage.', url: 'https://example.com/zzz', published_at: '2026-08-24T12:00:00Z' },
  ],
}

function mockUseData(overrides = {}) {
  const byFile = {
    'report.json': { data: reportFixture, loading: false },
    'etf/SPY.json': { data: spyFixture, loading: false, reload: vi.fn().mockResolvedValue(spyFixture) },
    'etf/QQQ.json': { data: flatEtfFixture, loading: false, reload: vi.fn().mockResolvedValue(flatEtfFixture) },
    'etf/DIA.json': { data: flatEtfFixture, loading: false, reload: vi.fn().mockResolvedValue(flatEtfFixture) },
    'etf/IWM.json': { data: flatEtfFixture, loading: false, reload: vi.fn().mockResolvedValue(flatEtfFixture) },
    'advisor.json': { data: advisorFixture, loading: false },
    ...overrides,
  }
  useData.mockImplementation((file) => byFile[file] ?? { data: null, loading: false, reload: vi.fn() })
}

function renderMarkets(path = '/v2/markets') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><MarketsScreen /></MediumProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('MarketsScreen — shared', () => {
  it('renders the session badge from live market data', () => {
    mockUseData()
    renderMarkets()
    expect(screen.getByTestId('market-type')).toHaveTextContent('supportive')
  })

  it('shows the loading state while report.json is in flight', () => {
    useData.mockImplementation(() => ({ data: null, loading: true, reload: vi.fn() }))
    renderMarkets()
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
  })

  it('shows unavailable when market data is absent', () => {
    useData.mockImplementation(() => ({ data: {}, loading: false, reload: vi.fn() }))
    renderMarkets()
    expect(screen.getByRole('alert')).toHaveTextContent('Market data is unavailable')
  })

  it('reads the ?view=news param — resolves the /market vs /markets confusion', () => {
    mockUseData()
    const { container } = renderMarkets('/v2/markets?view=news')
    expect(container.querySelector('[data-view="news"]')).toBeInTheDocument()
  })
})

describe('MarketsScreen — ?view=indexes', () => {
  it('renders the time-range control with the ledger capability id', () => {
    mockUseData()
    const { container } = renderMarkets()
    const control = container.querySelector('[data-capability-id="control.markets.time-range"]')
    expect(control).toBeInTheDocument()
    expect(control.querySelector('select')).toBeInTheDocument()
  })

  it('updates the ?range= param when the time-range control changes', () => {
    mockUseData()
    const { container } = renderMarkets()
    const select = container.querySelector('[data-capability-id="control.markets.time-range"] select')
    fireEvent.change(select, { target: { value: '1M' } })
    expect(select.value).toBe('1M')
  })

  it('renders the five-card stat grid from report.json', () => {
    mockUseData()
    renderMarkets()
    expect(screen.getByTestId('stat-index-leader')).toHaveTextContent('SPY')
    expect(screen.getByTestId('stat-hot-sector')).toHaveTextContent('Technology')
    expect(screen.getByTestId('stat-cold-sector')).toHaveTextContent('Energy')
    expect(screen.getByTestId('stat-top-stock')).toHaveTextContent('AAPL')
    expect(screen.getByTestId('stat-worst-stock')).toHaveTextContent('XOM')
  })

  it('renders the index strip with every covered index', () => {
    mockUseData()
    renderMarkets()
    expect(screen.getByTestId('index-SPY')).toHaveTextContent('SPY')
    expect(screen.getByTestId('index-QQQ')).toHaveTextContent('QQQ')
    expect(screen.getByTestId('index-DIA')).toHaveTextContent('DIA')
    expect(screen.getByTestId('index-IWM')).toHaveTextContent('IWM')
  })

  it('shows the chart caption disclosure when there are enough points', () => {
    mockUseData()
    renderMarkets()
    expect(screen.getByTestId('chart-caption')).toHaveTextContent('SPY adjusted closes through 2026-08-25.')
  })

  it('shows the two-observations-needed state when no index has two usable closes', () => {
    mockUseData({
      'etf/SPY.json': { data: singlePointEtfFixture, loading: false, reload: vi.fn().mockResolvedValue({}) },
      'etf/QQQ.json': { data: singlePointEtfFixture, loading: false, reload: vi.fn().mockResolvedValue({}) },
      'etf/DIA.json': { data: singlePointEtfFixture, loading: false, reload: vi.fn().mockResolvedValue({}) },
      'etf/IWM.json': { data: singlePointEtfFixture, loading: false, reload: vi.fn().mockResolvedValue({}) },
    })
    renderMarkets()
    expect(screen.getByTestId('two-observations-needed')).toHaveTextContent('Two market observations are required')
  })

  it('records an intraday observation into localStorage on mount', () => {
    mockUseData()
    renderMarkets()
    const stored = JSON.parse(localStorage.getItem('valuesignal.marketIntraday.v1'))
    expect(stored.SPY).toHaveLength(1)
    expect(stored.SPY[0].price).toBe(560)
  })

  it('renders the direct-lookup control and finds a covered ticker', () => {
    mockUseData()
    const { container } = renderMarkets()
    const input = container.querySelector('[data-capability-id="control.markets.direct-lookup"] input')
    expect(input).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'AAPL' } })
    expect(screen.getByTestId('lookup-result')).toHaveTextContent('AAPL')
    expect(screen.getByTestId('lookup-20d')).toHaveTextContent('+3.5')
  })

  it('updates the ?q= param as the lookup query changes', () => {
    mockUseData()
    const { container } = renderMarkets()
    const input = container.querySelector('[data-capability-id="control.markets.direct-lookup"] input')
    fireEvent.change(input, { target: { value: 'MSFT' } })
    expect(input.value).toBe('MSFT')
  })

  it('shows the no-lookup-match state for an uncovered ticker', () => {
    mockUseData()
    const { container } = renderMarkets()
    const input = container.querySelector('[data-capability-id="control.markets.direct-lookup"] input')
    fireEvent.change(input, { target: { value: 'ZZZZ' } })
    expect(screen.getByTestId('no-lookup-match')).toHaveTextContent('No covered ticker matched')
  })
})

describe('MarketsScreen — ?view=news', () => {
  it('shows the news-loading state', () => {
    useData.mockImplementation((file) => (
      file === 'advisor.json' ? { data: null, loading: true, reload: vi.fn() } : { data: reportFixture, loading: false, reload: vi.fn() }
    ))
    renderMarkets('/v2/markets?view=news')
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
  })

  it('renders the status callout from advisor.json', () => {
    mockUseData()
    renderMarkets('/v2/markets?view=news')
    expect(screen.getByTestId('status-callout')).toHaveTextContent('U.S. equities: Open')
  })

  it('splits news into published-research and discovery grids', () => {
    mockUseData()
    renderMarkets('/v2/markets?view=news')
    const published = screen.getByTestId('published-news')
    const discovery = screen.getByTestId('discovery-news')
    expect(published).toHaveTextContent('Apple beats estimates')
    expect(discovery).toHaveTextContent('Discovery co. surges')
  })

  it('renders the news-sort control and re-sorts on change', () => {
    mockUseData()
    const { container } = renderMarkets('/v2/markets?view=news')
    const select = container.querySelector('[data-capability-id="control.markets.news-sort"] select')
    expect(select).toBeInTheDocument()
    fireEvent.change(select, { target: { value: 'sentiment' } })
    expect(select.value).toBe('sentiment')
  })

  it('shows the no-recent-articles state when no published-research news matches', () => {
    mockUseData({ 'advisor.json': { data: { ...advisorFixture, research: [] }, loading: false } })
    renderMarkets('/v2/markets?view=news')
    expect(screen.getByTestId('no-recent-articles')).toHaveTextContent('No recent articles matched')
  })

  it('shows the no-company-news state when advisor.json has no news', () => {
    mockUseData({ 'advisor.json': { data: { ...advisorFixture, news: [] }, loading: false } })
    renderMarkets('/v2/markets?view=news')
    expect(screen.getByTestId('no-company-news')).toHaveTextContent('No company news returned in this refresh.')
  })

  it('shows the news-empty state when advisor.json itself is unavailable', () => {
    mockUseData({ 'advisor.json': { data: null, loading: false } })
    renderMarkets('/v2/markets?view=news')
    expect(screen.getByTestId('news-empty')).toBeInTheDocument()
  })

  it('renders the supporting-evidence and not-a-buy-signal disclosures', () => {
    mockUseData()
    renderMarkets('/v2/markets?view=news')
    expect(screen.getByTestId('news-supporting-evidence')).toHaveTextContent('supporting evidence')
    expect(screen.getByTestId('news-not-buy-signal')).toHaveTextContent('not a buy signal by itself')
  })
})
