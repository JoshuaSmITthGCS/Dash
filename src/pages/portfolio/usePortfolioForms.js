// Everything that *writes* to the stored portfolio: the add form, inline edit, sell entry,
// removal, and the one-time Fidelity reference sync — plus the status line all of them
// report through. Kept apart from the read-only view models so the render path stays pure.

import { useEffect, useRef, useState } from 'react'
import { REFERENCE_PORTFOLIO_VERSION } from '../../lib/referencePortfolio.js'
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

export function usePortfolioForms({ portfolio, tracking, previewPortfolio, positions = [] }) {
  const {
    addPosition,
    removePosition,
    updatePosition,
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
    if (previewPortfolio || !syncState.connected || referenceReady || referencePortfolioSyncStarted.current) return
    referencePortfolioSyncStarted.current = true
    syncReferencePortfolio().then((result) => {
      if (result?.success) setSyncMessage(`Fidelity snapshot applied: ${result.added} added · ${result.updated} updated · ${result.removed} removed.`)
      else {
        referencePortfolioSyncStarted.current = false
        setSyncMessage(`Could not apply Fidelity positions: ${result?.error || 'Unknown error'}`)
      }
    })
  }, [previewPortfolio, syncReferencePortfolio, syncState.connected, tracking.trackingState?.referencePortfolioVersion])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.ticker || !formData.shares || !formData.costBasis) {
      alert('Please fill in all required fields')
      return
    }
    const shares = parseFloat(formData.shares)
    const costBasis = perShareCost(formData.costBasis, shares, formData.costMode)
    if (!Number.isFinite(costBasis) || costBasis <= 0) {
      alert('Enter a valid share count and cost')
      return
    }
    const result = await addPosition(formData.ticker, shares, costBasis, formData.purchaseDate, formData.costMode)
    if (result?.success === false) {
      setSyncMessage(`Could not sync position: ${result.error}`)
      return
    }
    captureRebalance(tracking, today(), positions, [...positions, { ticker: formData.ticker, shares, costBasis }])
    setSyncMessage(`${formData.ticker} saved to your cloud portfolio.`)
    setFormData({ ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: today() })
    setShowAddForm(false)
  }

  const handleReferenceSync = async () => {
    setSyncMessage('Syncing…')
    const result = await syncReferencePortfolio()
    setSyncMessage(result.success
      ? `${result.added} added · ${result.updated} updated · ${result.removed} removed from the Aug 25 Fidelity baseline`
      : `Sync failed: ${result.error}`)
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
      : await removePosition(pos.id)
    if (positionResult?.success === false) {
      setSellSaving(false)
      setSyncMessage(`Could not save sale: ${positionResult.error || 'Unknown error'}`)
      return
    }
    const afterSell = remainingShares > 0.0000001
      ? positions.map((row) => (row.id === pos.id ? { ...row, shares: remainingShares } : row))
      : positions.filter((row) => row.id !== pos.id)
    captureRebalance(tracking, sellForm.saleDate, positions, afterSell)
    await tracking.recordActivity({ type: 'realized_gain', amount: realizedGain, effectiveDate: sellForm.saleDate, note: `${pos.ticker} sale` })
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
        : await removePosition(depletion.positionId)
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
    await tracking.recordActivity({
      type: 'realized_gain', amount: gain.totalRealizedGain, effectiveDate: lotSellForm.saleDate,
      note: `${lotSellTicker} FIFO sale across ${plan.depletions.length} lot${plan.depletions.length === 1 ? '' : 's'}: ${lotSummary}`,
    })
    setLotSellSaving(false)
    const closedTicker = lotSellTicker
    const soldQuantity = plan.totalQuantity
    cancelLotSell()
    setSyncMessage(`Sold ${soldQuantity} ${closedTicker} share${soldQuantity === 1 ? '' : 's'} at $${price.toFixed(2)} `
      + `across ${plan.depletions.length} lot${plan.depletions.length === 1 ? '' : 's'} · `
      + `${gain.totalRealizedGain >= 0 ? '+' : '−'}$${Math.abs(gain.totalRealizedGain).toFixed(2)} realized.`)
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
    syncMessage,
    showAddForm, setShowAddForm, formData, setFormData, handleSubmit,
    handleReferenceSync, handlePurchaseDateChange,
    removingId, handleRemove,
    editingId, editForm, setEditForm, editSaving, startEdit, cancelEdit, saveEdit,
    sellingId, sellForm, setSellForm, sellSaving, startSell, cancelSell, saveSell,
    lotSellTicker, lotSellForm, setLotSellForm, lotSellSaving, lotSellPlan,
    startLotSell, cancelLotSell, saveLotSell,
  }
}
