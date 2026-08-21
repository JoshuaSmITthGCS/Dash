import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TimeToValidMetric from './TimeToValidMetric.jsx'

describe('TimeToValidMetric', () => {
  it('renders nothing when the tracker is unavailable', () => {
    const { container } = render(<TimeToValidMetric timeToValidMetric={{ available: false }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the countdown and estimated date while the floor is unmet', () => {
    render(<TimeToValidMetric timeToValidMetric={{
      available: true, met: false, observations: 34, floor: 60, remainingSessions: 26,
      estimatedDate: '2026-09-21', methodology: 'test methodology',
    }} />)
    expect(screen.getByText('34')).toBeInTheDocument()
    expect(screen.getByText(/of 60 observations collected/)).toBeInTheDocument()
    expect(screen.getByText(/26 more market sessions needed/)).toBeInTheDocument()
    expect(screen.getByText(/Sep 21, 2026/)).toBeInTheDocument()
    expect(screen.getByText('test methodology')).toBeInTheDocument()
  })

  it('reports the floor already met without a session countdown', () => {
    render(<TimeToValidMetric timeToValidMetric={{ available: true, met: true, observations: 60, floor: 60, remainingSessions: 0 }} />)
    expect(screen.getByText(/reached/)).toBeInTheDocument()
    expect(screen.queryByText(/more market session/)).not.toBeInTheDocument()
  })

  it('uses singular "session" for exactly one remaining session', () => {
    render(<TimeToValidMetric timeToValidMetric={{
      available: true, met: false, observations: 59, floor: 60, remainingSessions: 1, estimatedDate: '2026-08-17',
    }} />)
    expect(screen.getByText(/1 more market session needed\b/)).toBeInTheDocument()
  })
})
