import { describe, expect, it } from 'vitest'
import {
  assessPositionStopLoss,
  averageTrueRange,
  highWaterMark,
  peakSincePurchase,
  stopLossLevels,
  withStopLoss,
} from './positionRisk'

const history = {
  dates: ['2024-01-05', '2024-02-02', '2024-03-01', '2024-04-05', '2024-05-03'],
  closes: [100, 120, 110, 105, 100],
}

describe('high-water mark', () => {
  it('finds the highest close on or after purchase', () => {
    expect(peakSincePurchase({ purchaseDate: '2024-01-15' }, history)).toBe(120)
  })

  it('can equal the purchase price before a position makes a new high', () => {
    const position = { purchasePrice: 100, currentPrice: 96 }
    expect(highWaterMark(position)).toBe(100)
  })

  it('moves up when the position reaches a new high', () => {
    const position = { highWaterMark: 120, currentPrice: 126 }
    expect(highWaterMark(position)).toBe(126)
    expect(stopLossLevels({ ...position, atr: 4 }).triggeredAction).toBeNull()
  })
})

describe('volatility-scaled position levels', () => {
  it('uses ATR when it is present', () => {
    const levels = stopLossLevels({ highWaterMark: 120, currentPrice: 100, atr: 6 })
    expect(levels.rule).toBe('atr')
    expect(levels.trimPrice).toBeCloseTo(105)
    expect(levels.exitPrice).toBeCloseTo(96)
    expect(levels.triggeredAction).toBe('TRIM')
    expect(levels.explanation).toMatch(/high-water mark/)
  })

  it('uses realized sigma when ATR is missing', () => {
    const levels = stopLossLevels({
      highWaterMark: 100,
      currentPrice: 85,
      annualizedVolatility: 0.8,
    })
    expect(levels.rule).toBe('sigma')
    expect(levels.trimDistancePct).toBeGreaterThanOrEqual(8)
    expect(levels.explanation).toMatch(/realized volatility/)
  })

  it('labels the fixed rule when ATR and sigma are both missing', () => {
    const levels = stopLossLevels({ highWaterMark: 100, currentPrice: 79 })
    expect(levels.rule).toBe('fallback_fixed')
    expect(levels.trimPrice).toBeCloseTo(88)
    expect(levels.exitPrice).toBeCloseTo(80)
    expect(levels.triggeredAction).toBe('SELL')
  })

  it('computes ATR from high, low, and prior close', () => {
    const atr = averageTrueRange({
      highs: [101, 104, 106],
      lows: [99, 100, 101],
      closes: [100, 103, 102],
    }, 2)
    expect(atr).toBeCloseTo(4.5)
  })
})

describe('position and company separation', () => {
  const stoppedPosition = { highWaterMark: 100, currentPrice: 75 }

  it('upgrades Hold when the position exit is more defensive', () => {
    const merged = withStopLoss({ action: 'HOLD', reasons: [], suggestedTrimPct: 0 }, stoppedPosition)
    expect(merged.action).toBe('SELL')
    expect(merged.source).toBe('stop_loss')
    expect(merged.reasons[0]).toMatch(/high-water mark/)
    expect(merged.companyRecommendation.action).toBe('HOLD')
  })

  it('keeps company guidance when it is already equally defensive', () => {
    const base = { action: 'SELL', reasons: ['Thesis broke'], suggestedTrimPct: 100, source: 'pipeline' }
    const merged = withStopLoss(base, stoppedPosition)
    expect(merged.action).toBe('SELL')
    expect(merged.source).toBe('pipeline')
    expect(merged.reasons).toContain('Thesis broke')
  })

  it('returns no position action above both levels', () => {
    expect(assessPositionStopLoss({ highWaterMark: 100, currentPrice: 95 })).toBeNull()
  })
})
