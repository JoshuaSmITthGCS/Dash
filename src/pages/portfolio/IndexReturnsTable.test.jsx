import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import IndexReturnsTable from './IndexReturnsTable.jsx'

const HISTORY = {
  as_of: '2026-04-02',
  dates: ['2025-12-31', '2026-03-31', '2026-04-01', '2026-04-02'],
  symbols: {
    SPY: { label: 'S&P 500® Index', closes: [100, 110, 111, 112] },
    AGG: { label: 'U.S. Aggregate Bond', closes: [50, 49, 49, 49] },
  },
}
vi.mock('../../lib/useData', () => ({ useData: () => ({ data: HISTORY, loading: false, error: null }) }))

const PORTFOLIO = { dates: HISTORY.dates, values: [1000, 1100, 1110, 1120] }

describe('IndexReturnsTable', () => {
  it('shows the portfolio beside the indexes with an as-of close and "--" for unreachable periods', () => {
    render(<IndexReturnsTable portfolioSeries={PORTFOLIO} />)
    expect(screen.getByText(/Prior day performance as of Apr-02-2026/)).toBeInTheDocument()
    const spy = screen.getByRole('row', { name: /^S&P 500® Index/ })
    expect(within(spy).getAllByText('+12.00%').length).toBeGreaterThan(0)
    expect(within(spy).getAllByText('--').length).toBeGreaterThan(0)
    expect(screen.getByRole('row', { name: /Difference vs S&P 500® Index/ })).toBeInTheDocument()
  })

  it('switches to the prior month-end when Monthly is chosen', () => {
    render(<IndexReturnsTable portfolioSeries={PORTFOLIO} />)
    fireEvent.click(screen.getByLabelText('Monthly'))
    expect(screen.getByText(/Prior month end performance as of Mar-31-2026/)).toBeInTheDocument()
  })

  it('renders the compact Summary card with a link to the full table', () => {
    render(<MemoryRouter><IndexReturnsTable portfolioSeries={PORTFOLIO} compact /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Full table' })).toHaveAttribute('href', '/portfolio/performance')
    expect(screen.queryByLabelText('Monthly')).not.toBeInTheDocument()
  })
})
