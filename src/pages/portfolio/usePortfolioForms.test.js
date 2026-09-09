import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { usePortfolioForms } from './usePortfolioForms.js'
import { REFERENCE_PORTFOLIO_VERSION } from '../../lib/referencePortfolio.js'

function setup({ positions = [], portfolioOverrides = {}, trackingOverrides = {}, preview = true } = {}) {
  const portfolio = {
    addPosition: vi.fn().mockResolvedValue({ success: true }),
    removePosition: vi.fn().mockResolvedValue({ success: true }),
    updatePosition: vi.fn().mockResolvedValue({ success: true }),
    recordClosedPosition: vi.fn().mockResolvedValue({ success: true }),
    clearClosedPosition: vi.fn().mockResolvedValue({ success: true }),
    closedPositions: [],
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
  const { result } = renderHook(() => usePortfolioForms({ portfolio, tracking, previewPortfolio: preview, positions }))
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

    expect(portfolio.removePosition).toHaveBeenCalledWith('lot-a', { sale: true })
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

describe('a completed exit is recorded so no baseline sync re-adds it', () => {
  it('marks the ticker closed when the last share of the only lot is sold', async () => {
    const existing = [{ id: 'lulu', ticker: 'LULU', shares: 1, costBasis: 117.94, currentPrice: 130 }]
    const { result, portfolio } = setup({ positions: existing })
    act(() => { result.current.startSell(existing[0]) })
    act(() => { result.current.setSellForm({ shares: '1', price: '130', saleDate: '2026-09-02' }) })
    await act(async () => { await result.current.saveSell(existing[0]) })
    expect(portfolio.removePosition).toHaveBeenCalledWith('lulu', { sale: true })
    expect(portfolio.recordClosedPosition).toHaveBeenCalledWith('LULU', expect.objectContaining({
      saleDate: '2026-09-02', shares: 1, price: 130,
    }))
  })

  it('does not mark the ticker closed while another lot of it is still open', async () => {
    const existing = [
      { id: 'lot-a', ticker: 'LULU', shares: 1, costBasis: 117.94, purchaseDate: '2026-07-30' },
      { id: 'lot-b', ticker: 'LULU', shares: 2, costBasis: 121, purchaseDate: '2026-08-30' },
    ]
    const { result, portfolio } = setup({ positions: existing })
    act(() => { result.current.startSell(existing[0]) })
    act(() => { result.current.setSellForm({ shares: '1', price: '130', saleDate: '2026-09-02' }) })
    await act(async () => { await result.current.saveSell(existing[0]) })
    expect(portfolio.recordClosedPosition).not.toHaveBeenCalled()
  })

  it('marks the ticker closed when a cross-lot sale empties every lot', async () => {
    const existing = [
      { id: 'lot-a', ticker: 'LULU', shares: 1, costBasis: 100, purchaseDate: '2026-07-30' },
      { id: 'lot-b', ticker: 'LULU', shares: 2, costBasis: 120, purchaseDate: '2026-08-30' },
    ]
    const { result, portfolio } = setup({ positions: existing })
    act(() => { result.current.startLotSell('LULU') })
    act(() => { result.current.setLotSellForm({ shares: '3', price: '130', saleDate: '2026-09-02' }) })
    await act(async () => { await result.current.saveLotSell() })
    expect(portfolio.recordClosedPosition).toHaveBeenCalledWith('LULU', expect.objectContaining({ saleDate: '2026-09-02' }))
  })
})

describe('submitTrade (the sticky trade bar)', () => {
  const held = [
    { id: 'lot-a', ticker: 'LULU', shares: 1, costBasis: 100, purchaseDate: '2026-07-30' },
    { id: 'lot-b', ticker: 'LULU', shares: 2, costBasis: 130, purchaseDate: '2026-08-30' },
  ]

  it('sells FIFO across lots, books the realized gain on the date given, and closes the ticker', async () => {
    const { result, portfolio, tracking } = setup({ positions: held })
    let outcome
    await act(async () => {
      outcome = await result.current.submitTrade({ side: 'sell', ticker: 'lulu', shares: '3', price: '140', date: '2026-09-02' })
    })
    expect(outcome.success).toBe(true)
    expect(portfolio.removePosition).toHaveBeenCalledWith('lot-a', { sale: true })
    expect(portfolio.removePosition).toHaveBeenCalledWith('lot-b', { sale: true })
    // (140-100)*1 + (140-130)*2 = 60
    expect(tracking.recordActivity).toHaveBeenCalledWith(expect.objectContaining({
      type: 'realized_gain', amount: 60, effectiveDate: '2026-09-02',
    }))
    expect(portfolio.recordClosedPosition).toHaveBeenCalledWith('LULU', expect.objectContaining({ saleDate: '2026-09-02' }))
  })

  it('refuses to sell more shares than are held, without touching any position', async () => {
    const { result, portfolio } = setup({ positions: held })
    let outcome
    await act(async () => {
      outcome = await result.current.submitTrade({ side: 'sell', ticker: 'LULU', shares: '9', price: '140', date: '2026-09-02' })
    })
    expect(outcome.success).toBe(false)
    expect(portfolio.updatePosition).not.toHaveBeenCalled()
    expect(portfolio.removePosition).not.toHaveBeenCalled()
  })

  it('buys as a new lot dated when the buy actually happened', async () => {
    const { result, portfolio } = setup({ positions: [] })
    await act(async () => {
      await result.current.submitTrade({ side: 'buy', ticker: 'lulu', shares: '2', price: '150', date: '2026-09-08' })
    })
    expect(portfolio.addPosition).toHaveBeenCalledWith('LULU', 2, 150, '2026-09-08', 'share')
  })

  it('rejects a zero or missing quantity before writing anything', async () => {
    const { result, portfolio } = setup({ positions: held })
    let outcome
    await act(async () => {
      outcome = await result.current.submitTrade({ side: 'buy', ticker: 'LULU', shares: '', price: '150', date: '2026-09-08' })
    })
    expect(outcome.success).toBe(false)
    expect(portfolio.addPosition).not.toHaveBeenCalled()
  })
})

describe('the one-time Fidelity baseline sync', () => {
  const connected = { syncState: { connected: true } }

  it('waits for the tracking document to load before deciding the account has never synced', async () => {
    const { portfolio } = setup({
      portfolioOverrides: connected,
      trackingOverrides: { trackingState: null, trackingLoaded: false },
      preview: false,
    })
    expect(portfolio.syncReferencePortfolio).not.toHaveBeenCalled()
  })

  it('does not re-apply the baseline once the loaded tracking state says this version was applied', async () => {
    const { portfolio } = setup({
      portfolioOverrides: connected,
      trackingOverrides: { trackingState: { referencePortfolioVersion: REFERENCE_PORTFOLIO_VERSION }, trackingLoaded: true },
      preview: false,
    })
    expect(portfolio.syncReferencePortfolio).not.toHaveBeenCalled()
  })

  it('applies the baseline once when the loaded tracking state has no version marker', async () => {
    const { portfolio } = setup({
      portfolioOverrides: connected,
      trackingOverrides: { trackingState: null, trackingLoaded: true },
      preview: false,
    })
    expect(portfolio.syncReferencePortfolio).toHaveBeenCalledTimes(1)
  })
})

describe('a sale does not invalidate the cash-flow ledger confirmation', () => {
  it('marks the removal as a sale when a sale closes the lot', async () => {
    const existing = [{ id: 'aaa', ticker: 'AAA', shares: 2, costBasis: 20, currentPrice: 25 }]
    const { result, portfolio } = setup({ positions: existing })
    act(() => { result.current.startSell(existing[0]) })
    act(() => { result.current.setSellForm({ shares: '2', price: '25', saleDate: '2026-04-01' }) })
    await act(async () => { await result.current.saveSell(existing[0]) })
    expect(portfolio.removePosition).toHaveBeenCalledWith('aaa', { sale: true })
  })

  it('leaves a bare Remove as a removal, which is not a sale', async () => {
    const existing = [{ id: 'aaa', ticker: 'AAA', shares: 2, costBasis: 20 }]
    const { result, portfolio } = setup({ positions: existing })
    await act(async () => { await result.current.handleRemove('aaa') })
    expect(portfolio.removePosition).toHaveBeenCalledWith('aaa')
  })
})

describe('the manual "add missing holdings" button', () => {
  it('passes the seeded-once ledger through, so nothing already delivered comes back', async () => {
    const { result, portfolio } = setup({
      trackingOverrides: { trackingState: { referencePortfolioSeeded: ['LULU', 'MU'] }, trackingLoaded: true },
      portfolioOverrides: {
        syncReferencePortfolio: vi.fn().mockResolvedValue({ success: true, added: 0, updated: 0, removed: 0 }),
      },
    })
    await act(async () => { await result.current.handleReferenceSync() })
    expect(portfolio.syncReferencePortfolio).toHaveBeenCalledWith({ seededTickers: ['LULU', 'MU'] })
  })

  it('says plainly that nothing changed rather than reporting a sync', async () => {
    const { result } = setup({
      portfolioOverrides: {
        syncReferencePortfolio: vi.fn().mockResolvedValue({ success: true, added: 0, updated: 0, removed: 0 }),
      },
    })
    await act(async () => { await result.current.handleReferenceSync() })
    expect(result.current.syncMessage).toContain('Your cloud portfolio is the record')
  })

  it('reports what it added without implying anything was overwritten', async () => {
    const { result } = setup({
      portfolioOverrides: {
        syncReferencePortfolio: vi.fn().mockResolvedValue({ success: true, added: 2, updated: 1, removed: 0 }),
      },
    })
    await act(async () => { await result.current.handleReferenceSync() })
    expect(result.current.syncMessage).toContain('2 holdings added')
    expect(result.current.syncMessage).toContain('Nothing already in your portfolio was changed')
  })
})
