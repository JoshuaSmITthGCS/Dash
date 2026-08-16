import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ScatterChart from './ScatterChart.jsx'

const POINTS = [
  { id: 'AAA', label: 'Alpha', x: -12, y: 8.5 },
  { id: 'BBB', label: 'Beta', x: -4, y: 3.2 },
]

describe('ScatterChart', () => {
  it('renders a labelled point per entity', () => {
    render(<ScatterChart points={POINTS} xLabel="Max drawdown" yLabel="Net return"
      xFormatter={(v) => `${v}%`} yFormatter={(v) => `${v}%`} />)
    expect(screen.getByRole('img', { name: /Max drawdown versus Net return scatter, 2 points/ })).toBeInTheDocument()
  })

  it('shows the hovered point in a live-region readout', () => {
    const { container } = render(<ScatterChart points={POINTS} xLabel="Max drawdown" yLabel="Net return"
      xFormatter={(v) => `${v}%`} yFormatter={(v) => `${v}%`} />)
    const alphaPoint = container.querySelectorAll('circle')[0]
    fireEvent.focus(alphaPoint)
    expect(container.querySelector('.correlation-readout').textContent)
      .toBe('Alpha: Max drawdown -12%, Net return 8.5%')
    fireEvent.blur(alphaPoint)
    expect(container.querySelector('.correlation-readout').textContent).toMatch(/Hover or tab to a point/)
  })

  it('offers a table view carrying the same values', () => {
    render(<ScatterChart points={POINTS} xLabel="Max drawdown" yLabel="Net return"
      xFormatter={(v) => `${v}%`} yFormatter={(v) => `${v}%`} />)
    expect(screen.queryByRole('table')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Table' }))
    const table = screen.getByRole('table')
    expect(within(table).getByRole('rowheader', { name: 'Alpha' })).toBeInTheDocument()
    expect(within(table).getByText('-12%')).toBeInTheDocument()
    expect(within(table).getByText('8.5%')).toBeInTheDocument()
  })

  it('drops points with non-finite values rather than crashing', () => {
    render(<ScatterChart points={[...POINTS, { id: 'CCC', label: 'Gamma', x: null, y: 5 }]}
      xLabel="Max drawdown" yLabel="Net return" />)
    fireEvent.click(screen.getByRole('button', { name: 'Table' }))
    expect(screen.queryByRole('rowheader', { name: 'Gamma' })).toBeNull()
  })

  it('renders nothing when there are no usable points', () => {
    const { container } = render(<ScatterChart points={[]} xLabel="X" yLabel="Y" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('colors points by tone and shows a legend when categories are provided', () => {
    render(<ScatterChart
      points={[{ id: 'A', label: 'A', x: 1, y: 1, tone: 'high' }, { id: 'B', label: 'B', x: 2, y: 2, tone: 'cool' }]}
      xLabel="Structural" yLabel="Tactical"
      legend={[{ tone: 'high', label: 'High conviction' }, { tone: 'cool', label: 'Avoid' }]}
    />)
    expect(screen.getByText('High conviction')).toBeInTheDocument()
    expect(screen.getByText('Avoid')).toBeInTheDocument()
  })
})
