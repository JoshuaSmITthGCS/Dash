import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Holdings from './Holdings.jsx'

const holdings = {
  basis: 500,
  versusIndex: [],
  fixedBasisTotal: 0,
  benchmarkHistory: null,
  portfolioStats: { positions: [] },
}

function formsStub(overrides = {}) {
  return {
    showAddForm: true,
    setShowAddForm: vi.fn(),
    formData: { ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: '2026-09-09' },
    handleSubmit: vi.fn(),
    sellingId: null,
    lotSellTicker: null,
    closedPositions: [],
    reopenClosedPosition: vi.fn(),
    handlePurchaseDateChange: vi.fn(),
    ...overrides,
  }
}

function renderHoldings(forms) {
  return render(
    <Holdings holdings={holdings} sortedPositions={[]} positionCount={0}
      sort={{ sort: { key: 'value', direction: 'desc' }, selectedLabel: 'Value', onSortKey: vi.fn(), onToggleDirection: vi.fn() }}
      viewMode="holdings" onViewModeChange={vi.fn()} essentialOnly onEssentialOnlyChange={vi.fn()}
      forms={forms} onSelectStock={vi.fn()} />,
  )
}

describe('Add New Position form', () => {
  it('keeps every field as it is typed and submits them together', () => {
    const handleSubmit = vi.fn()
    renderHoldings(formsStub({ handleSubmit }))

    fireEvent.change(screen.getByLabelText('Ticker'), { target: { value: 'lulu' } })
    fireEvent.change(screen.getByLabelText('Shares'), { target: { value: '1.5' } })
    fireEvent.change(screen.getByLabelText(/Cost basis per share/), { target: { value: '117.94' } })

    expect(screen.getByLabelText('Ticker').value).toBe('LULU')
    expect(screen.getByLabelText('Shares').value).toBe('1.5')
    expect(screen.getByLabelText(/Cost basis per share/).value).toBe('117.94')

    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(handleSubmit).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      ticker: 'LULU', shares: '1.5', costBasis: '117.94', costMode: 'share', purchaseDate: '2026-09-09',
    }))
  })
})

describe('closed positions', () => {
  it('lists a sold ticker so a recorded sale is visible, with an undo', () => {
    const reopenClosedPosition = vi.fn()
    renderHoldings(formsStub({
      closedPositions: [{ ticker: 'LULU', saleDate: '2026-09-02', shares: 1, price: 130, realizedGain: 12.06 }],
      reopenClosedPosition,
    }))
    expect(screen.getByText('LULU')).toBeTruthy()
    expect(screen.getByText(/Sold 2026-09-02/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(reopenClosedPosition).toHaveBeenCalledWith('LULU')
  })

  it('shows nothing when no position has been closed', () => {
    renderHoldings(formsStub())
    expect(screen.queryByText(/position closed/)).toBeNull()
  })
})
