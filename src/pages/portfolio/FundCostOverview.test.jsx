import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FundCostOverview from './FundCostOverview.jsx'

describe('FundCostOverview', () => {
  it('renders nothing when the portfolio holds no funds', () => {
    const { container } = render(<FundCostOverview fundCost={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the weighted expense ratio, fund count, and fund value', () => {
    render(<FundCostOverview fundCost={{ expenseRatioPct: 0.0725, fundValue: 10000, fundCount: 2 }} />)
    expect(screen.getByText('0.07%')).toBeInTheDocument()
    expect(screen.getByText(/weighted expense ratio across 2 funds/)).toBeInTheDocument()
    expect(screen.getByText(/\$10,000/)).toBeInTheDocument()
  })

  it('uses singular "fund" for exactly one fund holding', () => {
    render(<FundCostOverview fundCost={{ expenseRatioPct: 0.03, fundValue: 5000, fundCount: 1 }} />)
    expect(screen.getByText(/weighted expense ratio across 1 fund\b/)).toBeInTheDocument()
  })
})
