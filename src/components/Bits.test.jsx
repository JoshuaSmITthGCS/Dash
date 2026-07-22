import { render, screen } from '@testing-library/react'

import { MetricPills } from './Bits.jsx'

describe('MetricPills', () => {
  it('shows valuation, profitability, cash, risk, and coverage metrics', () => {
    render(<MetricPills peg={0.9} forward_pe={18} price_to_sales={2.2} price_to_book={2.5}
      return_on_equity={0.18} free_cash_flow_yield={0.06} debt_to_equity={0.7}
      current_ratio={1.6} fundamental_coverage={1} />)

    for (const label of ['PEG', 'Fwd P/E', 'P/S', 'P/B', 'ROE', 'FCF yield', 'D/E', 'Current', 'Coverage']) {
      expect(screen.getByText(label)).toBeVisible()
    }
    expect(screen.getByText('18.0%')).toBeVisible()
    expect(screen.getByText('6.0%')).toBeVisible()
    expect(screen.getByText('100%')).toBeVisible()
  })

  it('does not apply company ratios to ETFs', () => {
    render(<MetricPills isEtf />)
    expect(screen.getByText(/corporate fundamentals N\/A/)).toBeVisible()
  })
})
