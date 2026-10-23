import { describe, expect, it } from 'vitest'
import { suggestModelTrades } from './modelRebalance'

const research = [
  { ticker: 'AAA', price: 10 },
  { ticker: 'BBB', price: 20 },
  { ticker: 'CCC', price: 5 },
]
const positions = [
  { ticker: 'AAA', shares: 30, currentValue: 300, currentPrice: 10, gain: 50, purchaseDate: '2026-08-01' },
  { ticker: 'CCC', shares: 20, currentValue: 100, currentPrice: 5, gain: -10, purchaseDate: '2026-08-01' },
  { ticker: 'OWN', shares: 1, currentValue: 500, currentPrice: 500, gain: 100, purchaseDate: '2024-01-01' },
]
const base = { positions, research, bookSize: 2, costBps: 10, minTradeUsd: 1, asOf: '2026-09-30' }

describe('suggestModelTrades', () => {
  it('model sleeve mode leaves discretionary holdings alone', () => {
    const plan = suggestModelTrades({ ...base, mode: 'model_sleeve' })
    expect(plan.capital).toBe(400)
    expect(plan.targetPerName).toBe(200)
    expect(plan.trades.find((trade) => trade.ticker === 'OWN')).toBeUndefined()
    const byTicker = Object.fromEntries(plan.trades.map((trade) => [trade.ticker, trade]))
    expect(byTicker.CCC).toMatchObject({ action: 'SELL', amount: 100, flag: 'realizes_loss' })
    expect(byTicker.AAA).toMatchObject({ action: 'TRIM', amount: 100 })
    expect(byTicker.AAA.flag).toBe('short_term_gain')
    expect(byTicker.AAA.realizedGain).toBeCloseTo(50 / 3)
    expect(byTicker.BBB).toMatchObject({ action: 'BUY', amount: 200, shares: 10 })
  })

  it('whole-account mode sells off-model names and flags long-term gains as not short-term', () => {
    const plan = suggestModelTrades({ ...base, mode: 'full_account' })
    const own = plan.trades.find((trade) => trade.ticker === 'OWN')
    expect(own).toMatchObject({ action: 'SELL', amount: 500, shortTerm: false, flag: null })
    expect(plan.capital).toBe(900)
  })

  it('prices cost at the configured bps on both legs', () => {
    const plan = suggestModelTrades({ ...base, mode: 'model_sleeve' })
    expect(plan.totals.estimatedCost).toBeCloseTo((100 + 100 + 200) * 0.001)
    expect(plan.totals.turnoverPct).toBeCloseTo(50)
  })

  it('skips trades smaller than the minimum', () => {
    const plan = suggestModelTrades({ ...base, mode: 'model_sleeve', minTradeUsd: 150 })
    expect(plan.trades.map((trade) => trade.ticker).sort()).toEqual(['BBB', 'CCC'])
  })

  it('explains when there is no model sleeve', () => {
    const plan = suggestModelTrades({ ...base, positions: [positions[2]], mode: 'model_sleeve' })
    expect(plan.available).toBe(false)
    expect(plan.reason).toMatch(/Whole account/)
  })
})
