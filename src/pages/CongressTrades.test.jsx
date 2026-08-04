import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CongressTrades from './CongressTrades'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const trade = (overrides = {}) => ({
  chamber: 'senate', representative: 'Jane Doe', district: null, symbol: 'AAPL',
  transaction_type: 'Purchase', amount: '$15,001 - $50,000', amount_upper: 50000,
  transaction_date: '2026-06-01', disclosure_date: '2026-08-01',
  filing_delay_days: 61, flags: ['LATE_FILING'],
  ...overrides,
})

describe('CongressTrades page', () => {
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

    render(<MemoryRouter><CongressTrades /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: /Politics/ })).toBeVisible()
    expect(screen.getByText('Jane Doe')).toBeVisible()
    expect(screen.getByText('John Smith')).toBeVisible()
    expect(screen.getByText((_, el) => el.className === 'chip' && el.textContent === 'Late filing')).toBeVisible()
    expect(screen.getByText((_, el) => el.className === 'chip' && el.textContent === 'Options trade')).toBeVisible()
  })

  it('filters by chamber', () => {
    useData.mockReturnValue({
      data: {
        results: [
          trade({ representative: 'Jane Doe', chamber: 'senate' }),
          trade({ representative: 'John Smith', chamber: 'house' }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><CongressTrades /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Chamber'), { target: { value: 'house' } })

    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument()
    expect(screen.getByText('John Smith')).toBeVisible()
  })

  it('shows an honest empty state when nothing has been collected yet', () => {
    useData.mockReturnValue({ data: { results: [] }, loading: false, error: null })
    render(<MemoryRouter><CongressTrades /></MemoryRouter>)
    expect(screen.getByText(/No disclosures collected yet/)).toBeVisible()
  })

  it('shows a filter-specific empty state when filters exclude every row', () => {
    useData.mockReturnValue({ data: { results: [trade({ chamber: 'senate' })] }, loading: false, error: null })
    render(<MemoryRouter><CongressTrades /></MemoryRouter>)
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

    render(<MemoryRouter><CongressTrades /></MemoryRouter>)

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
          trade({ representative: 'Laggard', return_since_purchase_pct: 2 }),
          trade({ representative: 'Winner', return_since_purchase_pct: 45 }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><CongressTrades /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'performance' } })

    const names = screen.getAllByText(/Laggard|Winner/).map((el) => el.textContent)
    expect(names.indexOf('Winner')).toBeLessThan(names.indexOf('Laggard'))
  })
})
