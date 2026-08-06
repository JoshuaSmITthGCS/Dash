import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PortfolioChartOverlay, { portfolioPeriodCopy } from './PortfolioChartOverlay.jsx'

describe('PortfolioChartOverlay', () => {
  const money = (value) => `$${Number(value).toFixed(2)}`

  it('shows the ending value and selected-period gain in one summary', () => {
    render(<PortfolioChartOverlay
      summary={{ endValue: 3092.27, dollarReturn: -34.43, returnPct: -1.1 }}
      period="1D"
      money={money}
      seriesLabel="Backtested basket"
      holdings={28}
      coveragePct={100}
    />)

    expect(screen.getByText('$3092.27')).toBeInTheDocument()
    expect(screen.getByText('−$34.43')).toBeInTheDocument()
    expect(screen.getByText('−1.10% today')).toBeInTheDocument()
    expect(screen.getByText(/28 holdings · 100% price coverage/)).toBeInTheDocument()
  })

  it('uses human period labels for every chart selection', () => {
    expect(portfolioPeriodCopy('1W')).toBe('past week')
    expect(portfolioPeriodCopy('1M')).toBe('past month')
    expect(portfolioPeriodCopy('YTD')).toBe('year to date')
    expect(portfolioPeriodCopy('All')).toBe('all recorded dates')
  })
})
