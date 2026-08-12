import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MetricSections from './MetricSections'

describe('MetricSections', () => {
  it('shows acceleration versus the market as a signed sigma reading', () => {
    render(<MetricSections stock={{ technical_detail: { relative_acceleration: 1.42 } }} />)
    expect(screen.getByText('Acceleration vs market')).toBeInTheDocument()
    expect(screen.getByText('+1.42σ')).toBeInTheDocument()
  })

  it('signs a decelerating reading', () => {
    render(<MetricSections stock={{ technical_detail: { relative_acceleration: -0.8 } }} />)
    expect(screen.getByText('-0.80σ')).toBeInTheDocument()
  })

  it('omits the row rather than showing a neutral zero when it could not be measured', () => {
    // relative_acceleration is null for any name without two quarters of overlapping
    // history against the index, or whose beta could not be estimated. An absent
    // measurement must read as absent, not as "no acceleration".
    render(<MetricSections stock={{ technical_detail: { relative_acceleration: null } }} />)
    expect(screen.queryByText('Acceleration vs market')).not.toBeInTheDocument()
  })
})
