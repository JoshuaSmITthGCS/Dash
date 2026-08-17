import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { InsideInformationView, mergeResearchStock } from './StockDetailModal.jsx'

describe('mergeResearchStock', () => {
  it('adds deep research fields without replacing a newer route price', () => {
    const supplied = {
      ticker: 'AAPL', price: 210,
      analysis_v2: { structural: { effective_score: 80 } },
    }
    const fullResearch = {
      research: [{
        ticker: 'AAPL', price: 200, modifiers: { total: 2 }, explainability: { attribution: {} },
        analysis_v2: { structural: { effective_score: 79 }, timeliness: { effective_score: 62 } },
      }],
    }

    expect(mergeResearchStock(supplied, fullResearch)).toMatchObject({
      price: 210,
      modifiers: { total: 2 },
      explainability: { attribution: {} },
      analysis_v2: {
        structural: { effective_score: 80 },
        timeliness: { effective_score: 62 },
      },
    })
  })

  it('keeps a lightweight row unchanged when no deeper row exists', () => {
    const supplied = { ticker: 'NEW', price: 12 }
    expect(mergeResearchStock(supplied, { research: [] })).toBe(supplied)
  })
})

describe('InsideInformationView', () => {
  it('renders nothing for a ticker with no notable disclosed activity', () => {
    const { container } = render(<MemoryRouter><InsideInformationView info={undefined} /></MemoryRouter>)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the institutional flag and combined score', () => {
    render(<MemoryRouter><InsideInformationView info={{
      score: 3.5, institutional_flag: 'CLUSTER_ACCUMULATION', congress_flags: [],
    }} /></MemoryRouter>)

    expect(screen.getByText('Curated managers accumulating')).toBeVisible()
    expect(screen.getByText(/3.5/)).toBeVisible()
    expect(screen.getByRole('link', { name: /Inside Information screen/ })).toHaveAttribute(
      'href', '/screens/inside-information')
  })

  it('shows Congressional flags with human-readable labels', () => {
    render(<MemoryRouter><InsideInformationView info={{
      score: 1.2, institutional_flag: null, congress_flags: ['EXTRAORDINARY_BUY', 'CLUSTER_TRADE'],
    }} /></MemoryRouter>)

    expect(screen.getByText('First trade in a small, unfamiliar company')).toBeVisible()
    expect(screen.getByText('3+ representatives, 14-day span')).toBeVisible()
  })
})
