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
