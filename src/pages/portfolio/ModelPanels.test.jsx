import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ModelAlignment from './ModelAlignment.jsx'
import ModelTrades from './ModelTrades.jsx'
import EvidenceCountdown from './EvidenceCountdown.jsx'

const group = (id, label, weightPct, tickers) => ({
  id, label, count: tickers.length, tickers, value: 100, cost: 90, gain: 10, gainPct: 11.1, weightPct,
  replay: { start: '2026-09-01', end: '2026-09-30', returnPct: 2, excessPct: -1, volatilityPct: 12, maxDrawdownPct: -3 },
})

describe('ModelAlignment', () => {
  it('says which side the live record measures', () => {
    render(<ModelAlignment split={{
      available: true, methodology: 'm',
      groups: [group('model', "In the model's top 40", 40, [{ ticker: 'TSM', rank: 1 }]), group('discretionary', 'Your own picks', 60, [{ ticker: 'QCOM', rank: null }])],
    }} />)
    expect(screen.getByText(/mostly measures you, not the model/)).toBeInTheDocument()
    expect(screen.getByText('TSM #1')).toBeInTheDocument()
  })

  it('renders nothing when unavailable', () => {
    const { container } = render(<ModelAlignment split={{ available: false }} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('ModelTrades', () => {
  const research = [{ ticker: 'AAA', price: 10 }, { ticker: 'BBB', price: 20 }]
  const positions = [
    { ticker: 'AAA', shares: 10, currentValue: 100, currentPrice: 10, gain: 5, purchaseDate: '2026-08-01' },
    { ticker: 'OWN', shares: 1, currentValue: 300, currentPrice: 300, gain: 0, purchaseDate: '2026-08-01' },
  ]

  it('switches between sleeve and whole-account plans', () => {
    render(<ModelTrades positions={positions} research={research} costBps={10} bookSize={2} />)
    expect(screen.queryByRole('rowheader', { name: 'OWN' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/Whole account/))
    expect(screen.getByRole('rowheader', { name: 'OWN' })).toBeInTheDocument()
  })
})

describe('EvidenceCountdown', () => {
  it('lists pending milestones with dated progress', () => {
    render(<EvidenceCountdown countdown={{
      met: [],
      pending: [{ id: 'x', label: 'Headline ratios', unlocks: 'u', observations: 51, required: 60, unit: 'sessions', estimatedDate: '2026-10-13', overdue: false }],
    }} />)
    expect(screen.getByText('Oct 13, 2026')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '51 of 60 sessions' })).toBeInTheDocument()
  })
})
