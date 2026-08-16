import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DotPlot from './DotPlot.jsx'

const ROWS = [
  { id: 'a', label: 'Method A', value: 62 },
  { id: 'b', label: 'Method B', value: 41 },
]

describe('DotPlot', () => {
  it('prints the value directly beside each dot', () => {
    render(<DotPlot rows={ROWS} xLabel="Success rate" xFormatter={(v) => `${v}%`} />)
    expect(screen.getByText('62%')).toBeInTheDocument()
    expect(screen.getByText('41%')).toBeInTheDocument()
    expect(screen.getByText('Method A')).toBeInTheDocument()
  })

  it('shows the axis label', () => {
    render(<DotPlot rows={ROWS} xLabel="Success rate" xFormatter={(v) => `${v}%`} />)
    expect(screen.getByText('Success rate')).toBeInTheDocument()
  })

  it('drops rows with a non-finite value rather than crashing', () => {
    render(<DotPlot rows={[...ROWS, { id: 'c', label: 'Method C', value: null }]} xLabel="Success rate" />)
    expect(screen.queryByText('Method C')).toBeNull()
  })

  it('renders nothing when there are no usable rows', () => {
    const { container } = render(<DotPlot rows={[]} xLabel="Success rate" />)
    expect(container).toBeEmptyDOMElement()
  })
})
