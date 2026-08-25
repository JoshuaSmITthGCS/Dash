import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { usePortfolioForms } from './usePortfolioForms.js'

function setup({ positions = [], portfolioOverrides = {}, trackingOverrides = {} } = {}) {
  const portfolio = {
    addPosition: vi.fn().mockResolvedValue({ success: true }),
    removePosition: vi.fn().mockResolvedValue({ success: true }),
    updatePosition: vi.fn().mockResolvedValue({ success: true }),
    syncReferencePortfolio: vi.fn().mockResolvedValue({ success: true }),
    syncState: { connected: false },
    ...portfolioOverrides,
  }
  const tracking = {
    trackingState: {},
    recordActivity: vi.fn().mockResolvedValue({ success: true }),
    recordRebalance: vi.fn().mockResolvedValue({ success: true }),
    ...trackingOverrides,
  }
  const { result } = renderHook(() => usePortfolioForms({ portfolio, tracking, previewPortfolio: true, positions }))
  return { result, portfolio, tracking }
}

describe('usePortfolioForms rebalance capture (B2/turnover)', () => {
  it('records a rebalance event when a position is added', async () => {
    const existing = [{ id: 'aaa', ticker: 'AAA', shares: 10, costBasis: 20 }]
    const { result, tracking } = setup({ positions: existing })
    act(() => {
      result.current.setFormData({ ticker: 'BBB', shares: '5', costBasis: '40', costMode: 'share', purchaseDate: '2026-03-01' })
    })
    await act(async () => {
      await result.current.handleSubmit({ preventDefault: () => {} })
    })
    expect(tracking.recordRebalance).toHaveBeenCalledTimes(1)
    const call = tracking.recordRebalance.mock.calls[0][0]
    // Before: 100% AAA. After: 200 AAA-dollars + 200 BBB-dollars = 50/50.
    expect(call.beforeWeights).toMatchObject({ AAA: 1 })
    expect(call.afterWeights.AAA).toBeCloseTo(0.5, 6)
    expect(call.afterWeights.BBB).toBeCloseTo(0.5, 6)
  })

  it('records a rebalance event when a position is removed', async () => {
    const existing = [
      { id: 'aaa', ticker: 'AAA', shares: 10, costBasis: 20 },
      { id: 'bbb', ticker: 'BBB', shares: 5, costBasis: 40 },
    ]
    const { result, tracking } = setup({ positions: existing })
    await act(async () => { await result.current.handleRemove('bbb') })
    expect(tracking.recordRebalance).toHaveBeenCalledTimes(1)
    const call = tracking.recordRebalance.mock.calls[0][0]
    expect(call.beforeWeights).toMatchObject({ AAA: 0.5, BBB: 0.5 })
    expect(call.afterWeights).toMatchObject({ AAA: 1 })
    expect(call.afterWeights.BBB).toBeUndefined()
  })

  it('records a rebalance event when a position is edited', async () => {
    const existing = [
      { id: 'aaa', ticker: 'AAA', shares: 10, costBasis: 20 },
      { id: 'bbb', ticker: 'BBB', shares: 5, costBasis: 40 },
    ]
    const { result, tracking } = setup({ positions: existing })
    act(() => { result.current.startEdit(existing[0]) })
    act(() => { result.current.setEditForm({ shares: '30', costBasis: '20', costMode: 'share', purchaseDate: '2026-01-01' }) })
    await act(async () => { await result.current.saveEdit('aaa') })
    expect(tracking.recordRebalance).toHaveBeenCalledTimes(1)
    const call = tracking.recordRebalance.mock.calls[0][0]
    // Before: 200/400 = 50%. After edit AAA to 30*20=600: 600/(600+200) = 75%.
    expect(call.beforeWeights.AAA).toBeCloseTo(0.5, 6)
    expect(call.afterWeights.AAA).toBeCloseTo(0.75, 6)
  })

  it('records a rebalance event on a partial sell, keeping the remaining shares', async () => {
    const existing = [{ id: 'aaa', ticker: 'AAA', shares: 10, costBasis: 20, currentPrice: 25 }]
    const { result, tracking } = setup({ positions: existing })
    act(() => { result.current.startSell(existing[0]) })
    act(() => { result.current.setSellForm({ shares: '4', price: '25', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveSell(existing[0]) })
    expect(tracking.recordRebalance).toHaveBeenCalledTimes(1)
    const call = tracking.recordRebalance.mock.calls[0][0]
    expect(call.date).toBe('2026-04-01')
    // Remaining 6 shares * $20 cost basis still weights 100% (only one ticker held).
    expect(call.afterWeights).toMatchObject({ AAA: 1 })
  })

  it('records a rebalance event on a full sell, removing the position', async () => {
    const existing = [
      { id: 'aaa', ticker: 'AAA', shares: 10, costBasis: 20, currentPrice: 25 },
      { id: 'bbb', ticker: 'BBB', shares: 5, costBasis: 40 },
    ]
    const { result, tracking } = setup({ positions: existing })
    act(() => { result.current.startSell(existing[0]) })
    act(() => { result.current.setSellForm({ shares: '10', price: '25', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveSell(existing[0]) })
    const call = tracking.recordRebalance.mock.calls[0][0]
    expect(call.afterWeights).toMatchObject({ BBB: 1 })
    expect(call.afterWeights.AAA).toBeUndefined()
  })

  it('does not record a rebalance when the mutation itself fails', async () => {
    const existing = [{ id: 'aaa', ticker: 'AAA', shares: 10, costBasis: 20 }]
    const { result, tracking, portfolio } = setup({
      positions: existing,
      portfolioOverrides: { removePosition: vi.fn().mockResolvedValue({ success: false, error: 'offline' }) },
    })
    await act(async () => { await result.current.handleRemove('aaa') })
    expect(portfolio.removePosition).toHaveBeenCalled()
    expect(tracking.recordRebalance).not.toHaveBeenCalled()
  })
})

describe('FIFO cross-lot sell (B3)', () => {
  const twoLots = [
    { id: 'lot-a', ticker: 'AAPL', shares: 10, costBasis: 100, purchaseDate: '2026-01-01' },
    { id: 'lot-b', ticker: 'AAPL', shares: 8, costBasis: 120, purchaseDate: '2026-02-01' },
  ]

  it('previews the FIFO plan as the share count is typed, before confirming', () => {
    const { result } = setup({ positions: twoLots })
    act(() => { result.current.startLotSell('AAPL') })
    expect(result.current.lotSellPlan.available).toBe(false) // no shares entered yet
    act(() => { result.current.setLotSellForm({ ...result.current.lotSellForm, shares: '15' }) })
    expect(result.current.lotSellPlan.available).toBe(true)
    expect(result.current.lotSellPlan.depletions.map((row) => row.positionId)).toEqual(['lot-a', 'lot-b'])
  })

  it('depletes the oldest lot fully and the next partially, updating both position documents', async () => {
    const { result, portfolio, tracking } = setup({ positions: twoLots })
    act(() => { result.current.startLotSell('AAPL') })
    act(() => { result.current.setLotSellForm({ shares: '15', price: '150', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveLotSell() })

    expect(portfolio.removePosition).toHaveBeenCalledWith('lot-a')
    // costBasisTotal/snapshotValue are restated because the remaining quantity changed;
    // this lot carries no snapshot price, so there is no snapshot value left to reprice.
    expect(portfolio.updatePosition).toHaveBeenCalledWith('lot-b', {
      shares: 3, costBasisTotal: 360, snapshotValue: null,
    })
    // Lot a: 10 @ (150-100)=500. Lot b: 5 @ (150-120)=150. Total 650.
    expect(tracking.recordActivity).toHaveBeenCalledWith(expect.objectContaining({
      type: 'realized_gain', amount: 650, effectiveDate: '2026-04-01',
    }))
    expect(tracking.recordActivity.mock.calls[0][0].note).toContain('across 2 lots')
    expect(result.current.lotSellTicker).toBeNull() // sheet closes on success
  })

  it('records one rebalance event spanning both depleted lots', async () => {
    const withMsft = [...twoLots, { id: 'msft', ticker: 'MSFT', shares: 5, costBasis: 40 }]
    const { result, tracking } = setup({ positions: withMsft })
    act(() => { result.current.startLotSell('AAPL') })
    act(() => { result.current.setLotSellForm({ shares: '15', price: '150', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveLotSell() })
    expect(tracking.recordRebalance).toHaveBeenCalledTimes(1)
    const call = tracking.recordRebalance.mock.calls[0][0]
    // Only 3 AAPL shares (lot-b's remainder) plus MSFT survive.
    expect(call.afterWeights.MSFT).toBeGreaterThan(0)
  })

  it('rejects a sale larger than total holdings without touching any position', async () => {
    const { result, portfolio, tracking } = setup({ positions: twoLots })
    act(() => { result.current.startLotSell('AAPL') })
    act(() => { result.current.setLotSellForm({ shares: '999', price: '150', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveLotSell() })
    expect(portfolio.updatePosition).not.toHaveBeenCalled()
    expect(portfolio.removePosition).not.toHaveBeenCalled()
    expect(tracking.recordActivity).not.toHaveBeenCalled()
  })

  it('rejects an invalid sale price without touching any position', async () => {
    const { result, portfolio } = setup({ positions: twoLots })
    act(() => { result.current.startLotSell('AAPL') })
    act(() => { result.current.setLotSellForm({ shares: '5', price: '0', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveLotSell() })
    expect(portfolio.updatePosition).not.toHaveBeenCalled()
  })

  it('stops and reports the error if a mid-plan position update fails', async () => {
    const { result, tracking } = setup({
      positions: twoLots,
      portfolioOverrides: { removePosition: vi.fn().mockResolvedValue({ success: false, error: 'offline' }) },
    })
    act(() => { result.current.startLotSell('AAPL') })
    act(() => { result.current.setLotSellForm({ shares: '15', price: '150', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveLotSell() })
    expect(tracking.recordActivity).not.toHaveBeenCalled()
    expect(result.current.lotSellTicker).toBe('AAPL') // sheet stays open on failure
  })

  it('cancelLotSell clears the ticker and resets the form', () => {
    const { result } = setup({ positions: twoLots })
    act(() => { result.current.startLotSell('AAPL') })
    act(() => { result.current.setLotSellForm({ ...result.current.lotSellForm, shares: '5' }) })
    act(() => { result.current.cancelLotSell() })
    expect(result.current.lotSellTicker).toBeNull()
    expect(result.current.lotSellForm.shares).toBe('')
  })
})

// A brokerage-synced holding renders its stored snapshotValue until a live quote arrives, so
// a write that changes the share count without restating that value looks like a form that
// silently refused to save.
describe('usePortfolioForms snapshot restatement on quantity writes', () => {
  const synced = () => [{
    id: 'hig', ticker: 'HIG', shares: 1.394, costBasis: 143.45, costBasisTotal: 199.97,
    snapshotPrice: 138.9742, snapshotValue: 193.73, purchaseDate: '',
  }]

  it('reprices the stored snapshot value when the edit form changes shares', async () => {
    const { result, portfolio } = setup({ positions: synced() })
    act(() => { result.current.startEdit(synced()[0]) })
    act(() => { result.current.setEditForm({ shares: '2.788', costBasis: '143.45', costMode: 'share', purchaseDate: '' }) })
    await act(async () => { await result.current.saveEdit('hig') })

    const [, updates] = portfolio.updatePosition.mock.calls[0]
    expect(updates.shares).toBe(2.788)
    expect(updates.snapshotValue).toBeCloseTo(2.788 * 138.9742, 6)
    expect(updates.costBasisTotal).toBeCloseTo(2.788 * 143.45, 6)
  })

  it('reprices the stored snapshot value on a partial sale', async () => {
    const { result, portfolio } = setup({ positions: synced() })
    act(() => { result.current.startSell(synced()[0]) })
    act(() => { result.current.setSellForm({ shares: '0.394', price: '140', saleDate: '2026-08-25' }) })
    await act(async () => { await result.current.saveSell(synced()[0]) })

    const [, updates] = portfolio.updatePosition.mock.calls[0]
    expect(updates.shares).toBeCloseTo(1, 6)
    expect(updates.snapshotValue).toBeCloseTo(1 * 138.9742, 6)
  })

  it('drops the stored snapshot value when the holding has no snapshot price', async () => {
    const manual = [{ id: 'man', ticker: 'MAN', shares: 4, costBasis: 10, snapshotValue: 60 }]
    const { result, portfolio } = setup({ positions: manual })
    act(() => { result.current.startEdit(manual[0]) })
    act(() => { result.current.setEditForm({ shares: '8', costBasis: '10', costMode: 'share', purchaseDate: '' }) })
    await act(async () => { await result.current.saveEdit('man') })

    const [, updates] = portfolio.updatePosition.mock.calls[0]
    expect(updates.snapshotValue).toBeNull()
    expect(updates.costBasisTotal).toBe(80)
  })
})
