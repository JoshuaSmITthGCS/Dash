// Everything that *writes* to the stored portfolio: the add form, inline edit, sell entry,
// removal, and the one-time Fidelity reference sync — plus the status line all of them
// report through. Kept apart from the read-only view models so the render path stays pure.

import { useEffect, useRef, useState } from 'react'
import { REFERENCE_PORTFOLIO_LABEL, REFERENCE_PORTFOLIO_VERSION, seededTickersFromTrackingState } from '../../lib/referencePortfolio.js'
import { costWeights } from '../../lib/portfolioAnalytics.js'
import { planFifoSale, realizedGainForPlan } from '../../lib/taxLots.js'
import { perShareCost } from './format.js'

const today = () => new Date().toISOString().split('T')[0]

// Records one turnover-relevant rebalance event: the portfolio's cost-basis weight vector
// immediately before and after this specific add/edit/remove/sell. Fire-and-forget -- a
// rebalance-ledger write failing should never block the position mutation it's describing.
function captureRebalance(tracking, date, before, after) {
  if (!tracking?.recordRebalance) return
  tracking.recordRebalance({ date, beforeWeights: costWeights(before), afterWeights: costWeights(after) })
}

// Until a live quote lands, a holding's displayed value is read from the brokerage export's
// stored snapshotValue rather than recomputed (see buildHoldingsModel in portfolioModels.js
// and enrichPortfolio in portfolioAnalytics.js). Both that value and costBasisTotal are
// quantity-derived, so any write that changes the share count has to restate them: without
// this an edit or a sale commits to Firestore correctly and the tile still renders the
// pre-edit dollars, which reads as the form having silently failed to save. The snapshot's
// per-share price is still valid, so it is repriced rather than dropped.
function snapshotFieldsForShares(position, shares, costBasis) {
  const snapshotPrice = Number(position?.snapshotPrice)
  return {
    snapshotValue: Number.isFinite(snapshotPrice) ? shares * snapshotPrice : null,
    costBasisTotal: Number.isFinite(costBasis) ? shares * costBasis : null,
  }
}

// Shares of `ticker` still open across every lot once `soldByPositionId` is applied. A sale
// that takes this to zero is a closed position, and has to be recorded as one -- otherwise
// the next Fidelity baseline sync sees a ticker it expects, does not find it, and adds it
// back. That is the whole of the "I sold it and it reappeared" bug.
export function remainingSharesAfterSale(positions, ticker, soldByPositionId) {
  const target = String(ticker || '').trim().toUpperCase()
  return positions
    .filter((row) => String(row.ticker || '').trim().toUpperCase() === target)
    .reduce((sum, row) => sum + Math.max(0, Number(row.shares || 0) - Number(soldByPositionId[row.id] || 0)), 0)
}

export function usePortfolioForms({ portfolio, tracking, previewPortfolio, positions = [] }) {
  const {
    addPosition,
    removePosition,
    updatePosition,
    recordClosedPosition,
    clearClosedPosition,
    closedPositions = [],
    syncReferencePortfolio,
    syncState,
  } = portfolio

  const [syncMessage, setSyncMessage] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState({ ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: today() })
  const [removingId, setRemovingId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ shares: '', costBasis: '', costMode: 'share', purchaseDate: '' })
  const [editSaving, setEditSaving] = useState(false)
  const [sellingId, setSellingId] = useState(null)
  const [sellForm, setSellForm] = useState({ shares: '', price: '', saleDate: today() })
  const [sellSaving, setSellSaving] = useState(false)
  // A ticker (not a single position id): FIFO-across-lots sale (B3), additive to the
  // existing single-row Sell above -- clicking Sell on one specific position row already
  // constitutes specific identification of that one lot and is untouched by this.
  const [lotSellTicker, setLotSellTicker] = useState(null)
  const [lotSellForm, setLotSellForm] = useState({ shares: '', price: '', saleDate: today() })
  const [lotSellSaving, setLotSellSaving] = useState(false)
  const referencePortfolioSyncStarted = useRef(false)

  // Apply the user's authoritative Fidelity position export once on the signed-in account.
  // The version marker prevents later manual portfolio edits from being overwritten.
  useEffect(() => {
    const referenceReady = tracking.trackingState?.referencePortfolioVersion === REFERENCE_PORTFOLIO_VERSION
    // trackingLoaded, not just trackingState: the positions listener and the tracking-state
    // listener resolve independently, and this used to fire in the window between them, when
    // trackingState was still null only because it had not been read yet. That re-applied the
    // whole Aug 25 baseline on an already-synced account -- restoring sold and trimmed share
    // counts -- on any page load where positions answered first.
    if (previewPortfolio || !syncState.connected || !tracking.trackingLoaded
      || referenceReady || referencePortfolioSyncStarted.current) return
    referencePortfolioSyncStarted.current = true
    syncReferencePortfolio({ seededTickers: seededTickersFromTrackingState(tracking.trackingState) }).then((result) => {
      if (result?.success) setSyncMessage(result.added || result.updated
        ? `Opening holdings seeded from the ${REFERENCE_PORTFOLIO_LABEL} Fidelity snapshot: ${result.added} added${result.updated ? ` · ${result.updated} purchase date${result.updated === 1 ? '' : 's'} filled in` : ''}.`
        : `Your cloud portfolio is already the record. The ${REFERENCE_PORTFOLIO_LABEL} snapshot's prices were recorded as a dated observation; no holding was changed.`)
      else {
        referencePortfolioSyncStarted.current = false
        setSyncMessage(`Could not apply Fidelity positions: ${result?.error || 'Unknown error'}`)
      }
    })
  }, [previewPortfolio, syncReferencePortfolio, syncState.connected, tracking.trackingLoaded,
    tracking.trackingState?.referencePortfolioVersion])

  // `draft` is passed by AddPositionForm, which keeps its own fields so a keystroke does not
  // re-render the whole portfolio page (and the ~900-row model it derives) between the key
  // and the character. Falls back to the hook's own formData for callers that drive the
  // fields through setFormData.
  const handleSubmit = async (e, draft) => {
    e?.preventDefault?.()
    const entry = draft || formData
    if (!entry.ticker || !entry.shares || !entry.costBasis) {
      alert('Please fill in all required fields')
      return
    }
    const shares = parseFloat(entry.shares)
    const costBasis = perShareCost(entry.costBasis, shares, entry.costMode)
    if (!Number.isFinite(costBasis) || costBasis <= 0) {
      alert('Enter a valid share count and cost')
      return
    }
    const result = await addPosition(entry.ticker, shares, costBasis, entry.purchaseDate, entry.costMode)
    if (result?.success === false) {
      setSyncMessage(`Could not sync position: ${result.error}`)
      return
    }
    captureRebalance(tracking, today(), positions, [...positions, { ticker: entry.ticker, shares, costBasis }])
    setSyncMessage(`${entry.ticker} saved to your cloud portfolio.`)
    setFormData({ ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: today() })
    setShowAddForm(false)
  }

  // The manual equivalent of the seeding run above. It cannot restate or delete anything, so
  // on an account that has already been seeded the honest answer is usually "nothing to do" --
  // which is the point: the snapshot is history, and this collection is the record.
  const handleReferenceSync = async () => {
    setSyncMessage(`Checking the ${REFERENCE_PORTFOLIO_LABEL} snapshot for holdings you have never been given…`)
    const result = await syncReferencePortfolio({
      seededTickers: seededTickersFromTrackingState(tracking.trackingState),
    })
    if (!result.success) {
      setSyncMessage(`Could not read the snapshot: ${result.error}`)
      return
    }
    setSyncMessage(result.added || result.updated
      ? `${result.added} holding${result.added === 1 ? '' : 's'} added from the ${REFERENCE_PORTFOLIO_LABEL} snapshot`
        + `${result.updated ? ` · ${result.updated} missing purchase date${result.updated === 1 ? '' : 's'} filled in` : ''}.`
        + ' Nothing already in your portfolio was changed.'
      : `Nothing to add. Your cloud portfolio is the record — the ${REFERENCE_PORTFOLIO_LABEL} snapshot cannot overwrite, restore or remove anything in it. `
        + 'Its prices were recorded as a dated observation, which is how a refreshed export moves your holdings\' prices forward.')
  }

  const handlePurchaseDateChange = async (positionId, purchaseDate) => {
    const result = await updatePosition(positionId, { purchaseDate })
    setSyncMessage(result?.success ? 'Purchase date saved' : `Could not save date: ${result?.error || 'Unknown error'}`)
  }

  const handleRemove = async (positionId) => {
    if (removingId) return
    setRemovingId(positionId)
    const result = await removePosition(positionId)
    setRemovingId(null)
    if (result?.success === false) {
      setSyncMessage(`Could not remove position: ${result.error || 'Unknown error'}`)
    } else {
      captureRebalance(tracking, today(), positions, positions.filter((row) => row.id !== positionId))
      setSyncMessage('Position removed from the cloud portfolio on every connected device.')
    }
  }

  // Both halves of a sale's ledger entry, always written together.
  //
  // The realized gain is the profit. The proceeds are the money: tracked NAV is invested
  // holdings only, so selling moves the position's market value out of what is measured, and
  // unless that is recorded the shares just vanish from the account value. Every consumer then
  // reads the drop as a loss -- the time-weighted return charts a cliff, the money-weighted
  // return charges the strategy for it, and the reconciliation bridge fails by the full
  // proceeds. See SALE_PROCEEDS_TYPE in portfolioAnalytics.js.
  const recordSale = async ({ ticker, proceeds, realizedGain, saleDate, shares, note }) => {
    await tracking.recordActivity({
      type: 'realized_gain', amount: realizedGain, effectiveDate: saleDate, note,
    })
    await tracking.recordActivity({
      type: 'sale_proceeds', amount: proceeds, effectiveDate: saleDate,
      note: `${shares} ${ticker} share${shares === 1 ? '' : 's'} sold. Proceeds left your holdings; this is not a withdrawal from the account.`,
    })
  }

  // Every sale funnels through here once its position writes have committed: if the ticker
  // has no open shares left anywhere, it is a closed position and gets recorded as one.
  const closeIfFullyExited = async (ticker, soldByPositionId, details) => {
    const remaining = remainingSharesAfterSale(positions, ticker, soldByPositionId)
    if (remaining > 0.0000001) return
    await recordClosedPosition?.(ticker, details)
  }

  const startSell = (pos) => {
    setSellingId(pos.id)
    setSellForm({ shares: String(pos.shares ?? ''), price: pos.currentPrice != null ? String(pos.currentPrice) : '', saleDate: today() })
  }

  const cancelSell = () => {
    setSellingId(null)
    setSellForm({ shares: '', price: '', saleDate: today() })
  }

  // Selling adjusts (or removes) the position and records only the realized result. Proceeds
  // are not tracked as a cash balance; charts continue to reprice the remaining holdings only.
  const saveSell = async (pos) => {
    const sharesSold = parseFloat(sellForm.shares)
    const price = parseFloat(sellForm.price)
    if (!Number.isFinite(sharesSold) || sharesSold <= 0 || sharesSold > pos.shares || !Number.isFinite(price) || price <= 0 || !sellForm.saleDate) {
      setSyncMessage('Enter a valid share count (up to what you hold), sale price, and date')
      return
    }
    setSellSaving(true)
    const proceeds = sharesSold * price
    const realizedGain = proceeds - sharesSold * pos.costBasis
    const remainingShares = pos.shares - sharesSold
    const positionResult = remainingShares > 0.0000001
      ? await updatePosition(pos.id, {
        shares: remainingShares,
        ...snapshotFieldsForShares(pos, remainingShares, pos.costBasis),
      })
      : await removePosition(pos.id, { sale: true })
    if (positionResult?.success === false) {
      setSellSaving(false)
      setSyncMessage(`Could not save sale: ${positionResult.error || 'Unknown error'}`)
      return
    }
    const afterSell = remainingShares > 0.0000001
      ? positions.map((row) => (row.id === pos.id ? { ...row, shares: remainingShares } : row))
      : positions.filter((row) => row.id !== pos.id)
    captureRebalance(tracking, sellForm.saleDate, positions, afterSell)
    await recordSale({
      ticker: pos.ticker, proceeds, realizedGain, saleDate: sellForm.saleDate,
      shares: sharesSold, note: `${pos.ticker} sale`,
    })
    await closeIfFullyExited(pos.ticker, { [pos.id]: sharesSold }, {
      saleDate: sellForm.saleDate, realizedGain, shares: sharesSold, price,
    })
    setSellSaving(false)
    cancelSell()
    setSyncMessage(`Sold ${sharesSold} ${pos.ticker} share${sharesSold === 1 ? '' : 's'} at $${price.toFixed(2)} · ${realizedGain >= 0 ? '+' : '−'}$${Math.abs(realizedGain).toFixed(2)} realized.`)
  }

  const startLotSell = (ticker) => {
    setLotSellTicker(ticker)
    setLotSellForm({ shares: '', price: '', saleDate: today() })
  }

  const cancelLotSell = () => {
    setLotSellTicker(null)
    setLotSellForm({ shares: '', price: '', saleDate: today() })
  }

  // Recomputed on every render, not cached in state: it's a pure function of the current
  // form input and the live positions list, and needs to update as the user types a share
  // count so the sheet can show which lots that quantity would actually draw from before
  // they confirm.
  const lotSellPlan = lotSellTicker
    ? planFifoSale(positions, lotSellTicker, parseFloat(lotSellForm.shares))
    : null

  // Sells a quantity of a ticker across as many of its lots as it takes, oldest first (FIFO,
  // the IRS default absent specific identification -- see src/lib/taxLots.js). Each affected
  // lot is updated or removed exactly the way the single-lot saveSell above already does;
  // this just applies that per-position update across more than one document when the sale
  // is larger than any single lot.
  const saveLotSell = async () => {
    const price = parseFloat(lotSellForm.price)
    if (!Number.isFinite(price) || price <= 0 || !lotSellForm.saleDate) {
      setSyncMessage('Enter a valid sale price and date')
      return
    }
    const plan = planFifoSale(positions, lotSellTicker, parseFloat(lotSellForm.shares))
    if (!plan.available) {
      setSyncMessage(plan.reason)
      return
    }
    setLotSellSaving(true)
    for (const depletion of plan.depletions) {
      const lot = positions.find((row) => row.id === depletion.positionId)
      const result = depletion.remainingAfter > 0.0000001
        ? await updatePosition(depletion.positionId, {
          shares: depletion.remainingAfter,
          ...snapshotFieldsForShares(lot, depletion.remainingAfter, lot?.costBasis),
        })
        : await removePosition(depletion.positionId, { sale: true })
      if (result?.success === false) {
        setLotSellSaving(false)
        setSyncMessage(`Could not save sale: ${result.error || 'Unknown error'}`)
        return
      }
    }
    const afterSell = positions
      .map((row) => {
        const depletion = plan.depletions.find((item) => item.positionId === row.id)
        if (!depletion) return row
        return depletion.remainingAfter > 0.0000001 ? { ...row, shares: depletion.remainingAfter } : null
      })
      .filter(Boolean)
    captureRebalance(tracking, lotSellForm.saleDate, positions, afterSell)
    const gain = realizedGainForPlan(plan, price)
    const lotSummary = gain.perLot
      .map((row) => `${row.quantity} @ $${row.costBasisPerUnit.toFixed(2)} (${row.purchaseDate || 'undated lot'})`)
      .join('; ')
    await recordSale({
      ticker: lotSellTicker, proceeds: gain.totalProceeds, realizedGain: gain.totalRealizedGain,
      saleDate: lotSellForm.saleDate, shares: plan.totalQuantity,
      note: `${lotSellTicker} FIFO sale across ${plan.depletions.length} lot${plan.depletions.length === 1 ? '' : 's'}: ${lotSummary}`,
    })
    await closeIfFullyExited(
      lotSellTicker,
      Object.fromEntries(plan.depletions.map((row) => [row.positionId, row.quantity])),
      { saleDate: lotSellForm.saleDate, realizedGain: gain.totalRealizedGain, shares: plan.totalQuantity, price },
    )
    setLotSellSaving(false)
    const closedTicker = lotSellTicker
    const soldQuantity = plan.totalQuantity
    cancelLotSell()
    setSyncMessage(`Sold ${soldQuantity} ${closedTicker} share${soldQuantity === 1 ? '' : 's'} at $${price.toFixed(2)} `
      + `across ${plan.depletions.length} lot${plan.depletions.length === 1 ? '' : 's'} · `
      + `${gain.totalRealizedGain >= 0 ? '+' : '−'}$${Math.abs(gain.totalRealizedGain).toFixed(2)} realized.`)
  }

  // One entry point for a trade typed anywhere in the app -- today that is the sticky trade
  // bar in the stock research modal (src/components/TradeBar.jsx), which is reachable from
  // any holding tile without first expanding it. Buys add a lot; sells deplete FIFO across
  // every lot of the ticker, exactly as the Sell-across-lots sheet does, and record the
  // realized result and (on a full exit) the closed position. `date` is free: a sale entered
  // days after the fact books its realized gain on the day it actually happened.
  const submitTrade = async ({ side, ticker, shares, price, date }) => {
    const symbol = String(ticker || '').trim().toUpperCase()
    const quantity = parseFloat(shares)
    const pricePerShare = parseFloat(price)
    const tradeDate = date || today()
    if (!symbol) return { success: false, error: 'A ticker is required.' }
    if (!Number.isFinite(quantity) || quantity <= 0) return { success: false, error: 'Enter a positive share count.' }
    if (!Number.isFinite(pricePerShare) || pricePerShare <= 0) return { success: false, error: 'Enter a valid price per share.' }

    if (side === 'buy') {
      const result = await addPosition(symbol, quantity, pricePerShare, tradeDate, 'share')
      if (result?.success === false) return { success: false, error: result.error || 'Could not save this buy.' }
      captureRebalance(tracking, tradeDate, positions, [...positions, { ticker: symbol, shares: quantity, costBasis: pricePerShare }])
      const message = `Bought ${quantity} ${symbol} share${quantity === 1 ? '' : 's'} at $${pricePerShare.toFixed(2)} on ${tradeDate}.`
      setSyncMessage(message)
      return { success: true, message }
    }

    const plan = planFifoSale(positions, symbol, quantity)
    if (!plan.available) return { success: false, error: plan.reason }
    for (const depletion of plan.depletions) {
      const lot = positions.find((row) => row.id === depletion.positionId)
      const result = depletion.remainingAfter > 0.0000001
        ? await updatePosition(depletion.positionId, {
          shares: depletion.remainingAfter,
          ...snapshotFieldsForShares(lot, depletion.remainingAfter, lot?.costBasis),
        })
        : await removePosition(depletion.positionId, { sale: true })
      if (result?.success === false) return { success: false, error: result.error || 'Could not save this sale.' }
    }
    const afterSell = positions
      .map((row) => {
        const depletion = plan.depletions.find((item) => item.positionId === row.id)
        if (!depletion) return row
        return depletion.remainingAfter > 0.0000001 ? { ...row, shares: depletion.remainingAfter } : null
      })
      .filter(Boolean)
    captureRebalance(tracking, tradeDate, positions, afterSell)
    const gain = realizedGainForPlan(plan, pricePerShare)
    await recordSale({
      ticker: symbol, proceeds: gain.totalProceeds, realizedGain: gain.totalRealizedGain,
      saleDate: tradeDate, shares: quantity,
      note: `${symbol} sale (${plan.depletions.length} lot${plan.depletions.length === 1 ? '' : 's'}, FIFO)`,
    })
    await closeIfFullyExited(
      symbol,
      Object.fromEntries(plan.depletions.map((row) => [row.positionId, row.quantity])),
      { saleDate: tradeDate, realizedGain: gain.totalRealizedGain, shares: quantity, price: pricePerShare },
    )
    const message = `Sold ${quantity} ${symbol} share${quantity === 1 ? '' : 's'} at $${pricePerShare.toFixed(2)} on ${tradeDate} · `
      + `${gain.totalRealizedGain >= 0 ? '+' : '−'}$${Math.abs(gain.totalRealizedGain).toFixed(2)} realized.`
    setSyncMessage(message)
    return { success: true, message }
  }

  // Undo of a recorded exit: only clears the "do not re-add this" marker, since the sale
  // itself already moved the shares and the realized gain into the ledger. Buying the ticker
  // again clears it too (see addPosition), so this is for a sale entered by mistake.
  const reopenClosedPosition = async (ticker) => {
    const result = await clearClosedPosition?.(ticker)
    setSyncMessage(result?.success === false
      ? `Could not reopen ${ticker}: ${result.error || 'Unknown error'}`
      : `${String(ticker).toUpperCase()} is no longer marked as sold. Add the position back to hold it again.`)
    return result
  }

  const startEdit = (pos) => {
    const costMode = pos.costBasisInputMode === 'total' ? 'total' : 'share'
    setEditingId(pos.id)
    setEditForm({
      shares: String(pos.shares ?? ''),
      costBasis: String(costMode === 'total' ? pos.shares * pos.costBasis : pos.costBasis ?? ''),
      costMode,
      purchaseDate: pos.purchaseDate || '',
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditForm({ shares: '', costBasis: '', costMode: 'share', purchaseDate: '' })
  }

  const saveEdit = async (positionId) => {
    const shares = parseFloat(editForm.shares)
    const costBasis = perShareCost(editForm.costBasis, shares, editForm.costMode)
    if (!Number.isFinite(shares) || shares <= 0 || !Number.isFinite(costBasis) || costBasis <= 0) {
      setSyncMessage('Shares and cost basis must be positive numbers')
      return
    }
    setEditSaving(true)
    const result = await updatePosition(positionId, {
      shares,
      costBasis,
      costBasisUnit: 'per_share',
      costBasisInputMode: editForm.costMode,
      purchaseDate: editForm.purchaseDate,
      ...snapshotFieldsForShares(positions.find((row) => row.id === positionId), shares, costBasis),
    })
    setEditSaving(false)
    if (result?.success === false) {
      setSyncMessage(`Could not save changes: ${result.error || 'Unknown error'}`)
      return
    }
    captureRebalance(tracking, today(), positions,
      positions.map((row) => (row.id === positionId ? { ...row, shares, costBasis } : row)))
    setSyncMessage('Position updated')
    cancelEdit()
  }

  return {
    syncMessage, setSyncMessage,
    showAddForm, setShowAddForm, formData, setFormData, handleSubmit,
    handleReferenceSync, handlePurchaseDateChange,
    removingId, handleRemove,
    editingId, editForm, setEditForm, editSaving, startEdit, cancelEdit, saveEdit,
    sellingId, sellForm, setSellForm, sellSaving, startSell, cancelSell, saveSell,
    lotSellTicker, lotSellForm, setLotSellForm, lotSellSaving, lotSellPlan,
    startLotSell, cancelLotSell, saveLotSell,
    submitTrade, closedPositions, reopenClosedPosition,
  }
}
