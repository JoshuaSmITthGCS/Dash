import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PortfolioMoveExplanation from './PortfolioMoveExplanation'
import { explainPortfolioMove } from '../lib/portfolioAttribution.js'

const DAY_MS = 24 * 60 * 60 * 1000
const END_DATE = '2026-08-14'

const datedSeries = (count, endPrice, basePrice = 100) => {
  const end = Date.parse(`${END_DATE}T00:00:00Z`)
  const dates = []
  const closes = []
  for (let offset = count - 1; offset >= 0; offset -= 1) {
    dates.push(new Date(end - offset * DAY_MS).toISOString().slice(0, 10))
    closes.push(offset === 0 ? endPrice : basePrice)
  }
  return { dates, closes }
}

const benchmarkHistory = datedSeries(400, 101)
const positions = [{
  ticker: 'AAPL', name: 'Apple Inc', shares: 10, allocationPct: 100,
  priceInfo: { sector: 'Technology', history: datedSeries(400, 110), technical_detail: { beta: 1.2 } },
}]

const attributionFor = (period) => explainPortfolioMove(positions, benchmarkHistory, { period })

describe('PortfolioMoveExplanation', () => {
  it('renders nothing without an attribution', () => {
    const { container } = render(<PortfolioMoveExplanation attribution={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows no period picker when the page does not own the period', () => {
    render(<PortfolioMoveExplanation attribution={attributionFor('1D')} />)
    expect(screen.queryByLabelText('Attribution time range')).toBeNull()
  })

  it('reports the chosen period back to the page', () => {
    const onPeriodChange = vi.fn()
    render(<PortfolioMoveExplanation attribution={attributionFor('1D')} period="1D" onPeriodChange={onPeriodChange} />)

    fireEvent.click(screen.getByRole('button', { name: '3M' }))
    expect(onPeriodChange).toHaveBeenCalledWith('3M')
  })

  it('marks the active period for assistive tech', () => {
    render(<PortfolioMoveExplanation attribution={attributionFor('1M')} period="1M" onPeriodChange={() => {}} />)
    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '1Y' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('states the window actually measured rather than the one requested', () => {
    render(<PortfolioMoveExplanation attribution={attributionFor('1M')} period="1M" onPeriodChange={() => {}} />)
    expect(screen.getByText(/Aug 14, 2026 - 31 calendar days of published closes/)).toBeInTheDocument()
  })

  it('names today rather than a window on the daily view', () => {
    render(<PortfolioMoveExplanation attribution={attributionFor('1D')} period="1D" onPeriodChange={() => {}} />)
    expect(screen.getByText(/Why your portfolio moved today/)).toBeInTheDocument()
    expect(screen.queryByText(/calendar days of published closes/)).toBeNull()
  })

  it('discloses the start-of-window weighting on a longer view', () => {
    render(<PortfolioMoveExplanation attribution={attributionFor('3M')} period="3M" onPeriodChange={() => {}} />)
    expect(screen.getByText(/weighted by what it was worth at the start of the window/)).toBeInTheDocument()
  })

  it('keeps the period picker usable when the window has no data', () => {
    const onPeriodChange = vi.fn()
    render(<PortfolioMoveExplanation attribution={explainPortfolioMove(positions, null, { period: '1Y' })} period="1Y" onPeriodChange={onPeriodChange} />)

    expect(screen.getByText(/market\/idiosyncratic split cannot be computed/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '1D' }))
    expect(onPeriodChange).toHaveBeenCalledWith('1D')
  })
})
