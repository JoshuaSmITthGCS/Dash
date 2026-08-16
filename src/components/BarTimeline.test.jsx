import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import BarTimeline from './BarTimeline.jsx'

const POINTS = [
  { id: '2026-06', label: '2026-06', value: 120000 },
  { id: '2026-07', label: '2026-07', value: 340000 },
]

const money = (value) => `$${Math.round(value).toLocaleString('en-US')}`

describe('BarTimeline', () => {
  it('renders a bar per period', () => {
    render(<BarTimeline points={POINTS} yLabel="Disclosed volume" yFormatter={money} />)
    expect(screen.getByRole('img', { name: /Disclosed volume by period, 2 periods/ })).toBeInTheDocument()
  })

  it('shows the hovered period in a live-region readout', () => {
    const { container } = render(<BarTimeline points={POINTS} yLabel="Disclosed volume" yFormatter={money} />)
    fireEvent.focus(container.querySelectorAll('rect')[1])
    expect(container.querySelector('.correlation-readout').textContent).toBe('2026-07: Disclosed volume $340,000')
  })

  it('offers a table view carrying the same values', () => {
    render(<BarTimeline points={POINTS} yLabel="Disclosed volume" yFormatter={money} />)
    fireEvent.click(screen.getByRole('button', { name: 'Table' }))
    const table = screen.getByRole('table')
    expect(table).toHaveTextContent('$340,000')
  })

  it('stops making individual bars keyboard-focusable past the tab-stop limit', () => {
    const many = Array.from({ length: 50 }, (_, index) => ({ id: `p${index}`, label: `p${index}`, value: index + 1 }))
    const { container } = render(<BarTimeline points={many} yLabel="Volume" yFormatter={money} />)
    expect(container.querySelectorAll('rect[tabindex]').length).toBe(0)
    expect(screen.getByText(/use the Table view to reach every period by keyboard/)).toBeInTheDocument()
  })

  it('renders nothing when there are no usable points', () => {
    const { container } = render(<BarTimeline points={[]} yLabel="Volume" />)
    expect(container).toBeEmptyDOMElement()
  })
})
