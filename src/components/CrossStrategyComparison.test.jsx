import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CrossStrategyComparison from './CrossStrategyComparison.jsx'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))

const measured = (annualized_return) => ({ status: 'success', backtest: { annualized_return } })

describe('CrossStrategyComparison', () => {
  it('plots annualized return for every strategy that has a measured backtest', () => {
    useData.mockImplementation((file) => {
      if (file === 'screens/options-backtest.json') return { data: measured(0.18) }
      if (file === 'screens/covered-calls-backtest.json') return { data: measured(0.09) }
      return { data: { status: 'unavailable' } }
    })

    render(<CrossStrategyComparison />)

    expect(screen.getByText('Multi-day options')).toBeInTheDocument()
    expect(screen.getByText('18.0%')).toBeInTheDocument()
    expect(screen.getByText('Covered call')).toBeInTheDocument()
    expect(screen.getByText('9.0%')).toBeInTheDocument()
  })

  it('splits advanced strategies into its two sub-strategies', () => {
    useData.mockImplementation((file) => {
      if (file === 'screens/advanced-strategies-backtest.json') {
        return { data: { status: 'success', backtest: { iron_condor: { annualized_return: 0.05 }, straddle: { annualized_return: -0.02 } } } }
      }
      if (file === 'screens/options-backtest.json') return { data: measured(0.18) }
      return { data: { status: 'unavailable' } }
    })

    render(<CrossStrategyComparison />)

    expect(screen.getByText('Iron condor')).toBeInTheDocument()
    expect(screen.getByText('Straddle')).toBeInTheDocument()
    expect(screen.getByText('-2.0%')).toBeInTheDocument()
  })

  it('renders nothing when fewer than two strategies have a measured backtest', () => {
    useData.mockImplementation((file) => file === 'screens/options-backtest.json' ? { data: measured(0.18) } : { data: { status: 'unavailable' } })

    const { container } = render(<CrossStrategyComparison />)
    expect(container).toBeEmptyDOMElement()
  })
})
