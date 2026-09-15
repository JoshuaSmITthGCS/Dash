import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import StrategyScreen from './StrategyScreen'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../components/BacktestSummary.jsx', () => ({ default: () => null }))
vi.mock('../components/WatchlistToggleButton.jsx', () => ({ default: () => null }))

const row = (overrides = {}) => ({
  rank: 1, ticker: 'AAA', sector: 'Technology', price: 100, expiration: '2026-10-01',
  days_to_expiration: 16, capital_required: 10000, score: 1.5, eligibility: true,
  legs: [{ action: 'sell', option_type: 'call', strike: 105, mid: 3.0 }],
  metrics: {}, ...overrides,
})

const renderScreen = (id) => render(<MemoryRouter><StrategyScreen id={id} /></MemoryRouter>)

describe('StrategyScreen since-flagged track record', () => {
  it('shows the modeled P&L percent and date on covered-call, a live-refreshing screen', () => {
    useData.mockImplementation((file) => file === 'screens/covered-calls.json'
      ? { data: { status: 'success', results: [row({
          track_record: { date_predicted: '2026-09-10', pnl_dollars: 85, pnl_pct_of_capital: 8.5 },
        })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen('covered-call')
    expect(screen.getByRole('columnheader', { name: 'Since flagged' })).toBeVisible()
    expect(screen.getByText('+8.5% since 2026-09-10')).toBeInTheDocument()
  })

  it('shows a dash when a position is not currently in the top 10', () => {
    useData.mockImplementation((file) => file === 'screens/cash-secured-puts.json'
      ? { data: { status: 'success', results: [row({ track_record: { date_predicted: null } })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen('cash-secured-put')
    const tableRow = screen.getByText('AAA').closest('tr')
    expect(within(tableRow).getByTitle("Not currently in this screen's top 10.")).toHaveTextContent('–')
  })

  it('does not add the column for a screen that never refreshes live', () => {
    useData.mockImplementation((file) => file === 'screens/protective-puts.json'
      ? { data: { status: 'success', results: [row({ legs: [{ action: 'buy', option_type: 'put', strike: 95, mid: 2.0 }] })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen('protective-put')
    expect(screen.queryByRole('columnheader', { name: 'Since flagged' })).toBeNull()
  })

  it('shows the field on the mobile card too', () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: true, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }))
    useData.mockImplementation((file) => file === 'screens/short-term-trades.json'
      ? { data: { status: 'success', results: [row({
          track_record: { date_predicted: '2026-09-10', pnl_dollars: 85, pnl_pct_of_capital: 8.5 },
        })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen('short-term-trades')
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText('+8.5% since 2026-09-10')).toBeInTheDocument()
  })
})
