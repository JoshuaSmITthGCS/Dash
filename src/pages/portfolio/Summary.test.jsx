import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Summary from './Summary.jsx'

const HOLDINGS = {
  portfolioStats: { totalValue: 5000, positions: [] },
  assetAllocation: [],
  sectorAllocation: [],
  actionable: [],
  exposure: { warnings: [], maxPositionPct: 10, maxSectorPct: 30 },
  basis: 500,
  versusIndex: [],
  fixedBasisTotal: 0,
  benchmarkHistory: null,
}

function renderSummary(activities) {
  return render(
    <MemoryRouter>
      <Summary
        holdings={HOLDINGS}
        positions={[]}
        priceData={{}}
        holdingsSeriesFull={null}
        trackingSnapshots={[]}
        trackingActivities={activities}
        quotesRefreshing={false}
        summaryPeriod="1D"
        onSummaryPeriodChange={vi.fn()}
        suggestedActionsOpen={false}
        onSuggestedActionsToggle={vi.fn()}
        onSelectStock={vi.fn()}
        sortedPositions={[]}
        sort={{ sort: { key: 'value', direction: 'desc' }, selectedLabel: 'Value', onSortKey: vi.fn(), onToggleDirection: vi.fn() }}
        viewMode="holdings"
        onViewModeChange={vi.fn()}
        essentialOnly
        onEssentialOnlyChange={vi.fn()}
        forms={{ showAddForm: false, setShowAddForm: vi.fn(), closedPositions: [], reopenClosedPosition: vi.fn(), sellingId: null, lotSellTicker: null, formData: {}, handleSubmit: vi.fn(), handlePurchaseDateChange: vi.fn() }}
      />
    </MemoryRouter>,
  )
}

describe('Summary realized KPI', () => {
  it('reports the profit a recorded sale actually booked, which no holdings figure can show', () => {
    renderSummary([
      { type: 'realized_gain', amount: 12.06, effectiveDate: '2026-09-02', note: 'LULU sale' },
      { type: 'realized_gain', amount: -4, effectiveDate: '2026-08-01', note: 'XYZ sale' },
    ])
    expect(screen.getByText('Realized · 2 sales')).toBeTruthy()
    expect(screen.getByText('+$8.06')).toBeTruthy()
    expect(screen.getByText(/most recently 2026-09-02/)).toBeTruthy()
  })

  it('says so plainly when no sale has been recorded, rather than showing a zero', () => {
    renderSummary([])
    expect(screen.getByText('None recorded')).toBeTruthy()
  })
})
