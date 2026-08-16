import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PairedBarChart from './PairedBarChart.jsx'

const GROUPS = [
  { label: '1M', values: [0.032, 0.018] },
  { label: '3M', values: [-0.008, 0.011] },
]

const formatIc = (value) => value.toFixed(3)

describe('PairedBarChart', () => {
  it('renders a bar per series per group, including negative values', () => {
    render(<PairedBarChart groups={GROUPS} seriesLabels={['Champion', 'Challenger']} yFormatter={formatIc} />)
    expect(screen.getByRole('img', { name: /Champion versus Challenger, 2 groups/ })).toBeInTheDocument()
  })

  it('shows the hovered bar in a live-region readout', () => {
    const { container } = render(<PairedBarChart groups={GROUPS} seriesLabels={['Champion', 'Challenger']} yFormatter={formatIc} />)
    const firstBar = container.querySelector('rect')
    fireEvent.focus(firstBar)
    expect(container.querySelector('.correlation-readout').textContent).toMatch(/Champion, 1M: 0\.032/)
  })

  it('offers a table view with one column per series', () => {
    render(<PairedBarChart groups={GROUPS} seriesLabels={['Champion', 'Challenger']} yFormatter={formatIc} />)
    fireEvent.click(screen.getByRole('button', { name: 'Table' }))
    const table = screen.getByRole('table')
    expect(within(table).getByRole('rowheader', { name: '1M' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Champion' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'Challenger' })).toBeInTheDocument()
    expect(within(table).getByText('-0.008')).toBeInTheDocument()
  })

  it('renders a legend for both series in fixed order', () => {
    render(<PairedBarChart groups={GROUPS} seriesLabels={['Champion', 'Challenger']} yFormatter={formatIc} />)
    expect(screen.getByText('Champion')).toBeInTheDocument()
    expect(screen.getByText('Challenger')).toBeInTheDocument()
  })

  it('renders nothing when no group has a finite value', () => {
    const { container } = render(<PairedBarChart groups={[{ label: '1M', values: [null, null] }]} seriesLabels={['A', 'B']} />)
    expect(container).toBeEmptyDOMElement()
  })
})
