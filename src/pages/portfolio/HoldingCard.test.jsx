import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import HoldingCard from './HoldingCard.jsx'

const POS = {
  id: 'AAPL', ticker: 'AAPL', dayMove: { pct: 1.2 }, currentPrice: 190, priceInfo: { name: 'Apple Inc.' },
  allocationPct: 5, currentValue: 1900, gainPct: 12, rating: 2, recommendation: { action: 'hold' },
  trendValues: [1, 2, 3], shares: 10, costBasis: 150, quoteSource: 'live', stopLoss: null,
}

function forms(editingId) {
  return {
    editingId, editForm: { shares: '10', costMode: 'share', costBasis: '150', purchaseDate: '2026-01-01' },
    setEditForm: vi.fn(), editSaving: false, startEdit: vi.fn(), cancelEdit: vi.fn(), saveEdit: vi.fn(),
    sellingId: null, startSell: vi.fn(), removingId: null, handleRemove: vi.fn(), startLotSell: vi.fn(),
  }
}

describe('HoldingCard edit sheet', () => {
  it('renders the cost-basis unit select at the 11px floor, not smaller', () => {
    render(<HoldingCard pos={POS} essentialOnly={false} forms={forms('AAPL')} onSelectStock={vi.fn()} />)
    const select = screen.getByDisplayValue('$/share')
    expect(select).toHaveClass('field-mode-select')
    expect(select).not.toHaveAttribute('style')
  })
})

describe('HoldingCard FIFO cross-lot sell trigger (B3)', () => {
  it('does not show the cross-lot sell button for a ticker held in a single lot', () => {
    render(<HoldingCard pos={POS} essentialOnly={false} forms={forms(null)} onSelectStock={vi.fn()} lotCount={1} />)
    expect(screen.queryByText(/Sell across/)).not.toBeInTheDocument()
  })

  it('shows the cross-lot sell button when the ticker spans more than one lot, and wires it to the ticker', () => {
    const formsValue = forms(null)
    render(<HoldingCard pos={POS} essentialOnly={false} forms={formsValue} onSelectStock={vi.fn()} lotCount={3} />)
    const button = screen.getByText('Sell across 3 lots')
    button.click()
    expect(formsValue.startLotSell).toHaveBeenCalledWith('AAPL')
  })
})
