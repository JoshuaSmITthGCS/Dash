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

describe('comparison panel', () => {
  const metrics = { available: true, observations: 60, informationRatio: 0.4 }
  const acceleration = { available: true, acceleration: 1.62, accelerationPct: 6.4, recentExcessPct: 7.6, priorExcessPct: 1.2 }
  const capture = {
    available: true, upCapturePct: 88.4, downCapturePct: 61.2, captureSpread: 27.2,
    observations: { up: 140, down: 78 }, upBenchmarkPct: 42.5, downBenchmarkPct: -18.3,
  }
  const batting = {
    available: true, battingAveragePct: 58.3, months: 12, wins: 7, losses: 5,
    averageWinPct: 2.1, averageLossPct: -1.4, winLossRatio: 1.5,
    firstMonth: '2025-08', lastMonth: '2026-07',
  }
  const tileFor = (label) => screen.getByText(label).closest('article')

  it('splits risk from benchmark comparison into two panels', () => {
    render(<PerformanceMetrics metrics={metrics} benchmarkLabel="S&P 500"
      acceleration={acceleration} capture={capture} batting={batting}
      underwater={{ available: true, longestUnderwaterDays: 270, currentUnderwaterDays: 60, stillUnderwater: true, highWaterDate: '2026-05-01' }} />)
    expect(screen.getByRole('heading', { name: 'Risk and performance' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Versus the S&P 500' })).toBeInTheDocument()
    // Information ratio is a benchmark measure, so it belongs in the comparison panel.
    expect(tileFor('Information ratio').closest('section')).toHaveAttribute('aria-labelledby', 'benchmark-comparison-title')
  })

  it('shows acceleration in sigma with both quarters behind it', () => {
    render(<PerformanceMetrics metrics={metrics} acceleration={acceleration} capture={capture} batting={batting} />)
    expect(tileFor('Acceleration')).toHaveTextContent('+1.62σ')
    expect(tileFor('Acceleration')).toHaveTextContent('Pulling ahead faster')
    expect(tileFor('Acceleration')).toHaveTextContent('+7.6% this quarter vs +1.2% last, beta-adjusted')
  })

  it('shows both capture sides and calls the spread', () => {
    render(<PerformanceMetrics metrics={metrics} acceleration={acceleration} capture={capture} batting={batting} />)
    expect(tileFor('Up capture')).toHaveTextContent('88.4%')
    expect(tileFor('Down capture')).toHaveTextContent('61.2%')
    expect(tileFor('Capture spread')).toHaveTextContent('+27.2%')
    expect(tileFor('Capture spread')).toHaveTextContent('Keeping more of the upside than the downside')
    expect(tileFor('Batting average')).toHaveTextContent('Beat the index in 7 of 12 months')
    expect(tileFor('Batting average')).toHaveTextContent('wins 1.5× the size of losses')
  })

  it('reads the underwater spell in months and tones a long one badly', () => {
    render(<PerformanceMetrics metrics={metrics}
      underwater={{ available: true, longestUnderwaterDays: 400, currentUnderwaterDays: 0, stillUnderwater: false, highWaterDate: '2026-08-01' }} />)
    const tile = tileFor('Longest underwater')
    expect(tile).toHaveTextContent('13.1mo')
    expect(tile).toHaveTextContent('Recovered')
    // Lower is better here, so the tone value is negated before it meets the config bounds.
    expect(tile.className).toBe('metric-tone-negative')
  })

  it('says why each measure is unavailable instead of showing a neutral zero', () => {
    render(<PerformanceMetrics metrics={metrics}
      acceleration={{ available: false, acceleration: null, reason: 'Needs 189 days of overlapping history; 40 available.' }}
      capture={{ available: false, reason: 'Needs 8 up and 8 down periods; this window has 30 up and 2 down.' }}
      batting={{ available: false, reason: 'Needs 6 months of overlapping history; 2 available.' }} />)
    expect(tileFor('Acceleration')).toHaveTextContent('189 days of overlapping history')
    expect(tileFor('Up capture')).toHaveTextContent('this window has 30 up and 2 down')
    expect(tileFor('Batting average')).toHaveTextContent('2 available')
    expect(tileFor('Capture spread')).toHaveTextContent('Unavailable')
  })
})
