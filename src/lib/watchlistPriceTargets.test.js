import { describe, expect, it } from 'vitest'
import { suggestDipBuyPrice, suggestGoodBuyPrice, suggestPriceTargets } from './watchlistPriceTargets.js'

describe('suggestDipBuyPrice', () => {
  it('scales the discount from the stock\'s own volatility', () => {
    const calm = { price: 100, technical_detail: { annualized_volatility: 15 } }
    const wild = { price: 100, technical_detail: { annualized_volatility: 60 } }

    const calmResult = suggestDipBuyPrice(calm)
    const wildResult = suggestDipBuyPrice(wild)

    expect(calmResult.price).toBeLessThan(100)
    expect(wildResult.distancePct).toBeGreaterThan(calmResult.distancePct)
  })

  it('bounds the distance so a near-zero-volatility name still gets a real cushion', () => {
    const result = suggestDipBuyPrice({ price: 100, technical_detail: { annualized_volatility: 1 } })
    expect(result.distancePct).toBeGreaterThanOrEqual(5.0)
  })

  it('bounds the distance so a wildly volatile name does not get an unreachable target', () => {
    const result = suggestDipBuyPrice({ price: 100, technical_detail: { annualized_volatility: 500 } })
    expect(result.distancePct).toBeLessThanOrEqual(20.0)
  })

  it('is honest about missing volatility data rather than guessing', () => {
    const result = suggestDipBuyPrice({ price: 100, technical_detail: {} })
    expect(result.price).toBeNull()
    expect(result.derivation).toMatch(/no annualized volatility/i)
  })

  it('is null for a stock with no usable price', () => {
    expect(suggestDipBuyPrice({ price: null })).toBeNull()
    expect(suggestDipBuyPrice(null)).toBeNull()
  })

  it('every result explains its own derivation', () => {
    const result = suggestDipBuyPrice({ price: 100, technical_detail: { annualized_volatility: 25 } })
    expect(result.derivation).toContain('%')
    expect(result.derivation.toLowerCase()).toContain('heuristic')
  })
})

describe('suggestGoodBuyPrice', () => {
  it('applies a discount when priced richer than the fair percentile', () => {
    const rich = { price: 100, valuation_percentile: { ordinal: 16.7, tier: 'most_expensive_third' } }
    const result = suggestGoodBuyPrice(rich)

    expect(result.discountPct).toBeGreaterThan(0)
    expect(result.price).toBeLessThan(100)
  })

  it('does not invent a discount for a name already cheap relative to peers', () => {
    const cheap = { price: 100, valuation_percentile: { ordinal: 83.3, tier: 'cheapest_third' } }
    const result = suggestGoodBuyPrice(cheap)

    expect(result.discountPct).toBe(0)
    expect(result.price).toBe(100)
  })

  it('supports the flat sector_valuation_percentile field as a fallback source', () => {
    const result = suggestGoodBuyPrice({ price: 100, sector_valuation_percentile: 16.7 })
    expect(result.discountPct).toBeGreaterThan(0)
  })

  it('is honest about missing percentile data rather than guessing', () => {
    const result = suggestGoodBuyPrice({ price: 100 })
    expect(result.price).toBeNull()
    expect(result.derivation).toMatch(/no peer valuation tier/i)
  })

  it('bounds the maximum discount', () => {
    const veryRich = { price: 100, valuation_percentile: { ordinal: 16.7, tier: 'most_expensive_third' } }
    const result = suggestGoodBuyPrice(veryRich)
    expect(result.discountPct).toBeLessThanOrEqual(25.0)
  })
})

describe('suggestPriceTargets', () => {
  it('returns both targets together', () => {
    const stock = {
      price: 100,
      technical_detail: { annualized_volatility: 25 },
      valuation_percentile: { ordinal: 16.7, tier: 'most_expensive_third' },
    }
    const result = suggestPriceTargets(stock)
    expect(result.dipBuy.price).toBeLessThan(100)
    expect(result.goodBuy.price).toBeLessThan(100)
  })
})
