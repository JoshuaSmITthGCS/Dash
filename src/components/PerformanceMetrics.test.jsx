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

  it('keeps only the three highest-priority measures visible before disclosure', () => {
    const { container } = render(<PerformanceMetrics metrics={metrics} benchmarkLabel="S&P 500"
      acceleration={acceleration} capture={capture} batting={batting} />)
    const standard = container.querySelector('[aria-labelledby="standard-performance-title"]')
    expect(standard.querySelector(':scope > .metric-card-grid').children).toHaveLength(3)
    expect(standard.querySelector('.analytics-detail')).not.toHaveAttribute('open')
    expect(standard.querySelector('.analytics-detail > summary')).toHaveTextContent(/Show \d+ more measures/)
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

  it('carries tracking error in the information ratio tile, being its denominator', () => {
    render(<PerformanceMetrics metrics={metrics} risk={{ trackingErrorPct: 6.2, activeSharePct: 91.4 }} />)
    expect(tileFor('Information ratio')).toHaveTextContent('6.2% tracking error')
    expect(tileFor('Active share')).toHaveTextContent('91.4%')
  })

  it('says why each measure is unavailable instead of showing a neutral zero', () => {
    render(<PerformanceMetrics metrics={metrics}
      acceleration={{ available: false, acceleration: null, reason: 'Needs 189 days of overlapping history; 40 available.' }}
      capture={{ available: false, reason: 'Needs 8 up and 8 down periods; this window has 30 up and 2 down.' }}
      batting={{ available: false, reason: 'Needs 6 months of overlapping history; 2 available.' }} />)
    expect(tileFor('Acceleration')).toHaveTextContent('189 days of overlapping history')
    expect(tileFor('Up capture')).toHaveTextContent('this window has 30 up and 2 down')
    expect(tileFor('Batting average')).toHaveTextContent('2 available')
    expect(tileFor('Capture spread')).toHaveTextContent('Insufficient')
  })
})

describe('short-term panel', () => {
  const metrics = { available: true, observations: 60 }
  const shortTerm = {
    available: true,
    methodology: 'Excess is beta-adjusted at 0.84, fitted over the trailing 180 days.',
    windows: [
      { days: 7, available: true, excessPct: 2.6, portfolioPct: 3.1, benchmarkPct: 0.5, noiseFloorPct: 1.2, beyondNoise: true },
      { days: 30, available: true, excessPct: 0.4, portfolioPct: 4.0, benchmarkPct: 3.6, noiseFloorPct: 2.4, beyondNoise: false },
    ],
    streak: { direction: 'ahead', observations: 4, days: 9 },
    recentTrackingRiskPct: 8.3, baselineTrackingRiskPct: 6.1,
  }
  const tileFor = (label) => screen.getByText(label).closest('article')

  it('reports the week and month against the index with the noise floor beside them', () => {
    render(<PerformanceMetrics metrics={metrics} shortTerm={shortTerm} />)
    expect(screen.getByRole('heading', { name: 'Short-term view' })).toBeInTheDocument()
    expect(tileFor('Past week vs index')).toHaveTextContent('+2.6%')
    expect(tileFor('Past week vs index')).toHaveTextContent('You +3.1% · index +0.5%')
    expect(tileFor('Noise floor (month)')).toHaveTextContent('±2.4%')
    expect(tileFor('Current streak')).toHaveTextContent('Periods ahead of the index, spanning 9d')
    expect(tileFor('Recent tracking risk')).toHaveTextContent('6.1% baseline')
  })

  it('only colours a move that cleared its own noise floor', () => {
    render(<PerformanceMetrics metrics={metrics} shortTerm={shortTerm} />)
    // +2.6% beat a 1.2% floor, so it earns a colour.
    expect(tileFor('Past week vs index').className).toBe('metric-tone-positive')
    // +0.4% against a 2.4% floor is the ordinary wobble, and must not read as a win.
    expect(tileFor('Past month vs index').className).toBe('metric-tone-neutral')
    expect(tileFor('Noise floor (month)')).toHaveTextContent('Mostly noise')
  })

  it('declines a single window without taking the panel down with it', () => {
    render(<PerformanceMetrics metrics={metrics} shortTerm={{
      ...shortTerm,
      windows: [
        { days: 7, available: true, excessPct: 1.0, portfolioPct: 1.2, benchmarkPct: 0.2, noiseFloorPct: 1.4, beyondNoise: false },
        { days: 30, available: false, reason: '2 of 3 observations so far' },
      ],
    }} />)
    expect(tileFor('Past week vs index')).toHaveTextContent('+1.0%')
    expect(tileFor('Past month vs index')).toHaveTextContent('2 of 3 observations so far')
    expect(tileFor('Past month vs index').className).toBe('metric-tone-unavailable')
  })
})
