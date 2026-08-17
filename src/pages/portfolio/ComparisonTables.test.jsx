import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BenchmarkTable, FixedBasisTable } from './ComparisonTables.jsx'

function setViewport(matches) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }))
}

const POSITIONS = [
  {
    id: 'AAA', ticker: 'AAA', purchaseDate: '2026-01-01', totalCost: 1000, currentValue: 1200, gainPct: 20,
    versusBenchmark: { value: 1100, gainPct: 10 },
  },
  {
    id: 'BBB', ticker: 'BBB', purchaseDate: '', totalCost: 500, currentValue: 480, gainPct: -4,
    versusBenchmark: null,
  },
]

describe('BenchmarkTable', () => {
  it('renders one row per position with an editable purchase-date input', () => {
    setViewport(false)
    const onChange = vi.fn()
    render(<BenchmarkTable sortedPositions={POSITIONS} versusIndex={null} onPurchaseDateChange={onChange} />)
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(3) // header + 2 positions, no TOTAL
    const dateInput = screen.getByLabelText('AAA purchase date')
    fireEvent.change(dateInput, { target: { value: '2026-02-01' } })
    expect(onChange).toHaveBeenCalledWith('AAA', '2026-02-01')
  })

  it('shows a dash, not a crash, when a position has no benchmark comparison', () => {
    setViewport(false)
    render(<BenchmarkTable sortedPositions={POSITIONS} versusIndex={null} onPurchaseDateChange={vi.fn()} />)
    const bbbRow = screen.getByText('BBB').closest('tr')
    expect(within(bbbRow).getAllByText('–').length).toBeGreaterThan(0)
  })

  it('appends a bold TOTAL row when versusIndex is provided', () => {
    setViewport(false)
    render(<BenchmarkTable sortedPositions={POSITIONS} onPurchaseDateChange={vi.fn()} versusIndex={{
      invested: 1500, holdingsValue: 1680, holdingsReturnPct: 12, benchmarkValue: 1600,
      benchmarkReturnPct: 6.7, dollarsAhead: 80,
    }} />)
    const totalRow = screen.getByText('TOTAL').closest('tr')
    expect(totalRow).toHaveClass('comparison-total-row')
  })

  it('renders the empty state instead of a table when there are no positions', () => {
    setViewport(false)
    render(<BenchmarkTable sortedPositions={[]} versusIndex={null} onPurchaseDateChange={vi.fn()} />)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText(/No positions yet/)).toBeInTheDocument()
  })
})

describe('FixedBasisTable', () => {
  it('renders the empty state instead of a table when there are no positions', () => {
    setViewport(false)
    render(<FixedBasisTable sortedPositions={[]} fixedBasisTotal={null} basis={1000}
      benchmarkHistory={null} positionCount={0} onPurchaseDateChange={vi.fn()} />)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText(/No positions yet/)).toBeInTheDocument()
  })
})
