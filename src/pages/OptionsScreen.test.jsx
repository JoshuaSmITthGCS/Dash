import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OptionsScreen from './OptionsScreen'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../components/BacktestSummary.jsx', () => ({ default: () => null }))
vi.mock('../components/CrossStrategyComparison.jsx', () => ({ default: () => null }))
vi.mock('../components/WatchlistToggleButton.jsx', () => ({ default: () => null }))

const row = (overrides = {}) => ({
  rank: 1, ticker: 'AAA', sector: 'Technology', option_type: 'call', strike: 100, price: 105,
  expiration: '2026-10-01', days_to_expiration: 16, implied_volatility: 0.3,
  implied_realized_vol_ratio: 1.1, spread_pct: 0.02, open_interest: 500, score: 1.5,
  mid: 5.0, eligibility: true, ...overrides,
})

const renderScreen = () => render(<MemoryRouter><OptionsScreen /></MemoryRouter>)

describe('OptionsScreen since-flagged track record', () => {
  it('shows the modeled P&L percent and date since a contract first ranked top 10', () => {
    useData.mockImplementation((file) => file === 'screens/options.json'
      ? { data: { status: 'success', results: [row({
          track_record: { date_predicted: '2026-09-10', pnl_dollars: 42.5, pnl_pct_of_capital: 8.5 },
        })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen()
    expect(screen.getByRole('columnheader', { name: 'Since flagged' })).toBeVisible()
    expect(screen.getByText('+8.5% since 2026-09-10')).toBeInTheDocument()
  })

  it('shows a dash when a contract is not currently in the top 10', () => {
    useData.mockImplementation((file) => file === 'screens/options.json'
      ? { data: { status: 'success', results: [row({ track_record: { date_predicted: null } })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen()
    const tableRow = screen.getByText('AAA').closest('tr')
    expect(within(tableRow).getByTitle("Not currently in this screen's top 10.")).toHaveTextContent('–')
  })

  it('shows the field on the mobile card too', () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: true, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }))
    useData.mockImplementation((file) => file === 'screens/options.json'
      ? { data: { status: 'success', results: [row({
          track_record: { date_predicted: '2026-09-10', pnl_dollars: 42.5, pnl_pct_of_capital: 8.5 },
        })] }, loading: false, error: null }
      : { data: {}, loading: false, error: null })
    renderScreen()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText('+8.5% since 2026-09-10')).toBeInTheDocument()
  })
})
