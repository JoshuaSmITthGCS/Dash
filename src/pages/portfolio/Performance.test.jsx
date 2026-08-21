import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Performance from './Performance.jsx'

const HOLDINGS = {
  totalValue: 10000,
  totalGain: 1000,
  positions: [{ ticker: 'AAA', currentValue: 10000 }],
  growth: null,
  versusIndex: null,
}

const BENCHMARKS = {
  analyticsBenchmarkSeries: null,
  selectedBenchmarkSymbol: 'SPY',
  selectedBenchmarkLabel: 'S&P 500',
  candidateInputs: [],
}

function tracking(overrides = {}) {
  return {
    snapshots: [],
    activities: [],
    trackingState: null,
    recordSnapshot: vi.fn().mockResolvedValue({ success: true }),
    recordActivity: vi.fn().mockResolvedValue({ success: true }),
    setLedgerComplete: vi.fn().mockResolvedValue({ success: true }),
    ...overrides,
  }
}

function renderPerformance(props = {}) {
  return render(<Performance
    holdings={HOLDINGS}
    holdingsSeriesFull={null}
    benchmarks={BENCHMARKS}
    performancePeriod="All"
    onPerformancePeriodChange={vi.fn()}
    tracking={tracking()}
    {...props}
  />)
}

describe('Performance page', () => {
  it('shows the money-weighted return as accumulating when there is no recorded history', () => {
    renderPerformance()
    expect(screen.getByText(/Money-weighted return \(XIRR\) is accumulating/)).toBeInTheDocument()
    expect(screen.queryByText('Money-weighted return (XIRR)')).not.toBeInTheDocument()
  })

  it('shows a real money-weighted return once enough recorded history and a confirmed ledger exist', () => {
    const track = tracking({
      snapshots: [
        { value: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
        { value: 1650, marketDate: '2026-02-15', recordedAt: '2026-02-15T20:00:00Z' },
      ],
      activities: [{ type: 'deposit', amount: 500, effectiveDate: '2026-01-20' }],
      trackingState: { ledgerComplete: true },
    })
    renderPerformance({ tracking: track })
    expect(screen.getByText('Money-weighted return (XIRR)')).toBeInTheDocument()
  })

  it('records a cash flow through the ledger form', async () => {
    const track = tracking()
    renderPerformance({ tracking: track })
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'withdrawal' } })
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '250' } })
    fireEvent.change(screen.getByLabelText('Date'), { target: { value: '2026-03-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Record' }))
    await waitFor(() => expect(track.recordActivity).toHaveBeenCalledWith({
      type: 'withdrawal', amount: 250, effectiveDate: '2026-03-01',
    }))
  })

  it('refuses to record a cash flow with a non-positive amount', () => {
    const track = tracking()
    renderPerformance({ tracking: track })
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Record' }))
    expect(track.recordActivity).not.toHaveBeenCalled()
    expect(screen.getByText('Enter a positive amount and a date.')).toBeInTheDocument()
  })

  it('confirms the ledger complete toggle', () => {
    const track = tracking()
    renderPerformance({ tracking: track })
    fireEvent.click(screen.getByRole('checkbox'))
    expect(track.setLedgerComplete).toHaveBeenCalledWith(true)
  })

  it('auto-records a snapshot of the current total value and unrealized gain once per market day', async () => {
    const track = tracking()
    renderPerformance({ tracking: track })
    await waitFor(() => expect(track.recordSnapshot).toHaveBeenCalledWith(
      expect.objectContaining({ value: 10000, coveragePct: 100, source: 'performance_view', unrealizedGain: 1000 }),
    ))
  })

  it('does not re-record a snapshot already present for today', async () => {
    const { marketDate } = await import('../../lib/usePortfolioTracking.js')
    const today = marketDate()
    const track = tracking({ snapshots: [{ value: 9000, marketDate: today, recordedAt: `${today}T12:00:00Z` }] })
    renderPerformance({ tracking: track })
    await new Promise((resolve) => setTimeout(resolve, 10))
    expect(track.recordSnapshot).not.toHaveBeenCalled()
  })

  describe('reconciliation bridge', () => {
    it('shows an accumulating message with fewer than two unrealized-gain-tagged snapshots', () => {
      renderPerformance()
      expect(screen.getByText(/Reconciliation bridge is accumulating/)).toBeInTheDocument()
    })

    it('shows a reconciled bridge when every line balances to the recorded ending NAV', () => {
      const track = tracking({
        snapshots: [
          { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
          { value: 10540, unrealizedGain: 1200, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
        ],
        activities: [
          { type: 'deposit', amount: 200, effectiveDate: '2026-01-02' },
          { type: 'dividend', amount: 50, effectiveDate: '2026-01-02' },
          { type: 'fee', amount: 10, effectiveDate: '2026-01-02' },
          { type: 'realized_gain', amount: 100, effectiveDate: '2026-01-02' },
        ],
      })
      renderPerformance({ tracking: track })
      expect(screen.getByText('Reconciled')).toBeInTheDocument()
    })

    it('flags a failed reconciliation when the recorded ending NAV does not match', () => {
      const track = tracking({
        snapshots: [
          { value: 10000, unrealizedGain: 1000, marketDate: '2026-01-01', recordedAt: '2026-01-01T20:00:00Z' },
          { value: 10600, unrealizedGain: 1200, marketDate: '2026-01-02', recordedAt: '2026-01-02T20:00:00Z' },
        ],
        activities: [{ type: 'deposit', amount: 200, effectiveDate: '2026-01-02' }],
      })
      renderPerformance({ tracking: track })
      expect(screen.getByText('Reconciliation failed')).toBeInTheDocument()
    })
  })

  it('renders without a tracking prop at all', () => {
    renderPerformance({ tracking: undefined })
    expect(screen.getByText('Comparison history is still building')).toBeInTheDocument()
  })
})
