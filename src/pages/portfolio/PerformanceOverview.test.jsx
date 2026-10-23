import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PerformanceOverview from './PerformanceOverview.jsx'

const HISTORY = {
  as_of: '2026-10-22',
  dates: ['2026-07-28', '2026-07-31', '2026-08-31', '2026-09-30', '2026-10-22'],
  symbols: { SPY: { label: 'S&P 500® Index', closes: [100, 101, 103, 102, 104] } },
}
vi.mock('../../lib/useData', () => ({ useData: () => ({ data: HISTORY, loading: false, error: null }) }))

const SERIES = { dates: HISTORY.dates, values: [5000, 5100, 5300, 5075, 5360], frequency: 'daily' }
const HOLDINGS = { totalValue: 5360, totalGain: 360, assetAllocation: [{ label: 'Long-term stocks', pct: 80, value: 4288 }, { label: 'ETFs', pct: 20, value: 1072 }] }
const TRACKING = { activities: [{ type: 'dividend', amount: 4.5, effectiveDate: '2026-09-10' }, { type: 'deposit', amount: 400, effectiveDate: '2026-08-05' }] }

const renderOverview = (props = {}) => render(<PerformanceOverview holdings={HOLDINGS} holdingsSeriesFull={SERIES} tracking={TRACKING} period="All" onPeriodChange={vi.fn()} {...props} />)

describe('PerformanceOverview', () => {
  it('shows balance, return, flows and the monthly bars for the range', () => {
    renderOverview()
    expect(screen.getByText('Balance')).toBeInTheDocument()
    expect(screen.getAllByText('+7.20%').length).toBeGreaterThan(0)
    expect(screen.getByText('Net deposits and withdrawals').nextSibling).toHaveTextContent('+$400.00')
    expect(screen.getByRole('img', { name: "Aug '26: +3.92%" })).toBeInTheDocument()
  })

  it('lists your return beside the indexes over the same window', () => {
    renderOverview()
    const card = screen.getByRole('heading', { name: 'Total returns' }).closest('article')
    expect(within(card).getByText('Your return')).toBeInTheDocument()
    expect(within(card).getByText('S&P 500® Index')).toBeInTheDocument()
  })

  it('switches the range from the pills and shows the tooltip on hover', () => {
    const onPeriodChange = vi.fn()
    renderOverview({ onPeriodChange })
    fireEvent.click(screen.getByRole('radio', { name: '3M' }))
    expect(onPeriodChange).toHaveBeenCalledWith('3M')
    fireEvent.mouseEnter(screen.getByRole('img', { name: "Sep '26: -4.25%" }))
    expect(screen.getByRole('status')).toHaveTextContent('Return')
  })

  it('shows dashes for flows when no activity is recorded', () => {
    renderOverview({ tracking: { activities: [] } })
    expect(screen.getByText('Net deposits and withdrawals').nextSibling).toHaveTextContent('--')
  })
})
