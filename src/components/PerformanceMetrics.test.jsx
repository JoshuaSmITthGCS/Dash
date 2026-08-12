import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PerformanceMetrics, { performanceMetricTone } from './PerformanceMetrics.jsx'

describe('performance metric tones', () => {
  it('marks high ratios as good and weak ratios as bad', () => {
    expect(performanceMetricTone('sharpe', 0.75)).toBe('positive')
    expect(performanceMetricTone('sharpe', -0.1)).toBe('negative')
    expect(performanceMetricTone('sharpe', 0.25)).toBe('neutral')
  })

  it('treats drawdowns closer to zero as good', () => {
    expect(performanceMetricTone('maxDrawdown', -8)).toBe('positive')
    expect(performanceMetricTone('maxDrawdown', -25)).toBe('negative')
  })

  it('scores acceleration against a standard error, not a percentage', () => {
    expect(performanceMetricTone('acceleration', 1.4)).toBe('positive')
    expect(performanceMetricTone('acceleration', -1.4)).toBe('negative')
    expect(performanceMetricTone('acceleration', 0.3)).toBe('neutral')
  })
})

describe('acceleration tile', () => {
  const reading = {
    available: true, acceleration: 1.62, accelerationPct: 6.4,
    recentExcessPct: 7.6, priorExcessPct: 1.2,
  }

  it('shows the reading in sigma with both quarters behind it', () => {
    render(<PerformanceMetrics metrics={{ available: true, observations: 60 }}
      benchmarkLabel="S&P 500" acceleration={reading} />)
    expect(screen.getByText('Acceleration vs S&P 500')).toBeInTheDocument()
    expect(screen.getByText(/\+1\.62σ/)).toBeInTheDocument()
    expect(screen.getByText(/Pulling ahead faster/)).toBeInTheDocument()
    expect(screen.getByText(/\+7\.6% this quarter vs \+1\.2% last, beta-adjusted/)).toBeInTheDocument()
  })

  it('says why it is unavailable instead of showing a neutral zero', () => {
    render(<PerformanceMetrics metrics={{ available: true, observations: 60 }}
      acceleration={{ available: false, acceleration: null, reason: 'Needs 189 days of overlapping history; 40 available.' }} />)
    const tile = screen.getByText('Acceleration vs benchmark').closest('article')
    expect(tile).toHaveTextContent('Unavailable')
    expect(tile).toHaveTextContent('189 days of overlapping history')
  })
})
