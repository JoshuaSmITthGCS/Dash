import { describe, expect, it } from 'vitest'
import { assessPositionStopLoss, peakSincePurchase, stopLossLevels, withStopLoss } from './positionRisk'

const history = {
  dates: ['2024-01-05', '2024-02-02', '2024-03-01', '2024-04-05', '2024-05-03'],
  closes: [100, 120, 90, 80, 78],
}

describe('peakSincePurchase', () => {
  it('finds the highest close on or after the purchase date', () => {
    expect(peakSincePurchase({ purchaseDate: '2024-01-15' }, history)).toBe(120)
  })

  it('ignores closes before the purchase date', () => {
    expect(peakSincePurchase({ purchaseDate: '2024-03-15' }, history)).toBe(80)
  })

  it('returns null without a purchase date', () => {
    expect(peakSincePurchase({}, history)).toBeNull()
  })
})

describe('assessPositionStopLoss', () => {
  it('flags a hard stop-loss once a position is down enough from cost', () => {
    const result = assessPositionStopLoss({
      gainPct: -22, currentPrice: 78, purchaseDate: '2024-01-15', priceInfo: { history },
    })
    expect(result.action).toBe('SELL')
  })

  it('flags a defensive trim on a smaller cost-basis drawdown', () => {
    const result = assessPositionStopLoss({
      gainPct: -14, currentPrice: 86, purchaseDate: '2024-01-15', priceInfo: { history },
    })
    expect(result.action).toBe('TRIM')
  })

  it('flags a trailing stop even while still profitable overall', () => {
    const result = assessPositionStopLoss({
      gainPct: 5, currentPrice: 100, purchaseDate: '2024-01-15',
      priceInfo: { history: { dates: history.dates, closes: [100, 140, 130, 120, 100] } },
    })
    expect(result.action).toBe('TRIM')
    expect(result.reasons[0]).toMatch(/peak/)
  })

  it('stays quiet when neither trigger fires', () => {
    expect(assessPositionStopLoss({
      gainPct: 3, currentPrice: 103, purchaseDate: '2024-01-15',
      priceInfo: { history: { dates: history.dates, closes: [100, 101, 102, 103, 103] } },
    })).toBeNull()
  })

  it('returns null without enough position data', () => {
    expect(assessPositionStopLoss({})).toBeNull()
  })
})

describe('stopLossLevels', () => {
  it('reports the trailing stop as binding once it sits above the cost-basis stop', () => {
    // cost basis 100 -> hard stop 80, trim 88; peak-since-purchase 120 -> trailing stop 102
    const levels = stopLossLevels({
      costBasis: 100, currentPrice: 110, purchaseDate: '2024-01-15', priceInfo: { history },
    })
    expect(levels.costStopPrice).toBeCloseTo(80)
    expect(levels.trailingStopPrice).toBeCloseTo(102)
    expect(levels.bindingPrice).toBeCloseTo(102)
    expect(levels.bindingSource).toBe('trailing')
    expect(levels.distancePct).toBeCloseTo((110 / 102 - 1) * 100)
  })

  it('falls back to the cost-basis stop without enough history for a peak', () => {
    const levels = stopLossLevels({ costBasis: 100, currentPrice: 90, purchaseDate: '2024-01-15' })
    expect(levels.trailingStopPrice).toBeNull()
    expect(levels.bindingPrice).toBeCloseTo(80)
    expect(levels.bindingSource).toBe('cost_basis')
  })

  it('returns null without a cost basis and current price', () => {
    expect(stopLossLevels({})).toBeNull()
  })
})

describe('withStopLoss', () => {
  const stoppedPosition = {
    gainPct: -25, currentPrice: 75, purchaseDate: '2024-01-15', priceInfo: { history },
  }

  it('upgrades a Hold recommendation when the stop-loss is more severe', () => {
    const merged = withStopLoss({ action: 'HOLD', reasons: [], suggestedTrimPct: 0 }, stoppedPosition)
    expect(merged.action).toBe('SELL')
    expect(merged.source).toBe('stop_loss')
    expect(merged.reasons[0]).toMatch(/stop-loss/)
    expect(merged.companyRecommendation.action).toBe('HOLD')
    expect(merged.positionAction).toMatchObject({ action: 'SELL', reasonCode: 'hard_stop_breached' })
  })

  it('leaves a recommendation already at least as severe untouched', () => {
    const base = { action: 'SELL', reasons: ['Thesis broke'], suggestedTrimPct: 100, source: 'pipeline' }
    const merged = withStopLoss(base, stoppedPosition)
    expect(merged.action).toBe('SELL')
    expect(merged.source).toBe('pipeline')
    expect(merged.reasons).toContain('Thesis broke')
  })

  it('passes through unchanged when no stop-loss triggers', () => {
    const base = { action: 'HOLD', reasons: [] }
    const quiet = { gainPct: 2, currentPrice: 102, purchaseDate: '2024-01-15', priceInfo: { history: { dates: history.dates, closes: [100, 101, 102, 102, 102] } } }
    expect(withStopLoss(base, quiet)).toBe(base)
  })
})
