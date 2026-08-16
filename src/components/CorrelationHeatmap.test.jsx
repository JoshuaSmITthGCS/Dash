import { render, screen, fireEvent, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CorrelationHeatmap from './CorrelationHeatmap.jsx'

const TICKERS = ['SYF', 'HIG', 'NEM']
const MATRIX = [
  [1, 0.23, 0.11],
  [0.23, 1, -0.15],
  [0.11, -0.15, 1],
]

const draw = () => render(
  <CorrelationHeatmap tickers={TICKERS} matrix={MATRIX} observations={250} caption="Pairwise correlation" />,
)

describe('CorrelationHeatmap', () => {
  it('gives every off-diagonal cell an accessible name carrying the number and its meaning', () => {
    draw()
    expect(screen.getByRole('img', { name: 'SYF and HIG: 0.23, moves loosely together' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'HIG and NEM: -0.15, moves loosely opposite' })).toBeInTheDocument()
  })

  it('calls a near-zero pair independent rather than weakly correlated', () => {
    render(<CorrelationHeatmap tickers={['A', 'B']} matrix={[[1, 0.02], [0.02, 1]]} observations={250} />)
    expect(screen.getByRole('img', { name: 'A and B: 0.02, moves independently' })).toBeInTheDocument()
  })

  it('prints the value in the cell, so colour is never the only encoding', () => {
    draw()
    expect(screen.getAllByText('0.23').length).toBe(2)
  })

  it('offers a table view carrying the same numbers', () => {
    draw()
    expect(screen.queryByRole('table')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Table' }))
    const table = screen.getByRole('table')
    expect(within(table).getAllByText('0.23').length).toBe(2)
    expect(within(table).getByRole('rowheader', { name: 'SYF' })).toBeInTheDocument()
  })

  it('reports the hovered pair in a live region', () => {
    draw()
    fireEvent.mouseEnter(screen.getByRole('img', { name: /SYF and HIG/ }))
    expect(screen.getByText(/SYF and HIG: 0.23 — moves loosely together/)).toBeInTheDocument()
  })

  it('renders nothing when there is no matrix to draw', () => {
    const { container } = render(<CorrelationHeatmap tickers={[]} matrix={[]} observations={0} />)
    expect(container.firstChild).toBeNull()
  })
})
