import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import HoldingsDataQuality from './HoldingsDataQuality.jsx'

describe('HoldingsDataQuality', () => {
  it('renders nothing with no positions', () => {
    const { container } = render(<HoldingsDataQuality portfolioPositions={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('flags a holding with no resolved data source', () => {
    render(<HoldingsDataQuality portfolioPositions={[{ ticker: 'ZZZ', priceInfo: null }]} />)
    expect(screen.getByText('ZZZ')).toBeInTheDocument()
    expect(screen.getByText('Coverage unavailable')).toBeInTheDocument()
    expect(screen.getByText('no source resolved')).toBeInTheDocument()
    expect(screen.getByText('1 of 1 need attention')).toBeInTheDocument()
  })

  it('shows a fresh, well-covered holding with no flags', () => {
    render(<HoldingsDataQuality portfolioPositions={[{
      ticker: 'AAPL',
      priceInfo: {
        data_coverage: 0.82,
        data_quality_violations: [],
        last_polled_at: new Date().toISOString(),
      },
    }]} />)
    expect(screen.getByText('82% coverage')).toBeInTheDocument()
    expect(screen.getByText('No flags')).toBeInTheDocument()
    expect(screen.getByText('All holdings current')).toBeInTheDocument()
  })

  it('surfaces data quality violations distinctly from a low coverage figure', () => {
    render(<HoldingsDataQuality portfolioPositions={[{
      ticker: 'XYZ',
      priceInfo: {
        data_coverage: 0.2,
        data_quality_violations: ['negative EBITDA with a positive EV/EBITDA score'],
        last_polled_at: new Date().toISOString(),
      },
    }]} />)
    expect(screen.getByText('20% coverage')).toBeInTheDocument()
    expect(screen.getByText('1 data quality flag')).toBeInTheDocument()
    expect(screen.getByText('1 of 1 need attention')).toBeInTheDocument()
  })

  it('flags stale data by age', () => {
    render(<HoldingsDataQuality portfolioPositions={[{
      ticker: 'OLD',
      priceInfo: {
        data_coverage: 0.9,
        data_quality_violations: [],
        last_polled_at: new Date(Date.now() - 48 * 3_600_000).toISOString(),
      },
    }]} />)
    expect(screen.getByText(/47h old|48h old/)).toBeInTheDocument()
    expect(screen.getByText('1 of 1 need attention')).toBeInTheDocument()
  })
})
