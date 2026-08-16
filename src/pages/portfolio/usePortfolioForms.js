// Everything that *writes* to the stored portfolio: the add form, inline edit, sell entry,
// removal, and the one-time Fidelity reference sync — plus the status line all of them
// report through. Kept apart from the read-only view models so the render path stays pure.

import { useEffect, useRef, useState } from 'react'
import { REFERENCE_PORTFOLIO_VERSION } from '../../lib/referencePortfolio.js'
import { perShareCost } from './format.js'

const today = () => new Date().toISOString().split('T')[0]

export function usePortfolioForms({ portfolio, tracking, previewPortfolio }) {
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
    setSyncMessage(`${formData.ticker} saved to your cloud portfolio.`)
    setFormData({ ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: today() })
    setShowAddForm(false)
  }

  const handleReferenceSync = async () => {
    setSyncMessage('Syncing…')
    const result = await syncReferencePortfolio()
    setSyncMessage(result.success
      ? `${result.added} added · ${result.updated} updated · ${result.removed} removed from the Aug 14 Fidelity baseline`
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
    } else setSyncMessage('Position removed from the cloud portfolio on every connected device.')
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
      ? await updatePosition(pos.id, { shares: remainingShares })
      : await removePosition(pos.id)
    if (positionResult?.success === false) {
      setSellSaving(false)
      setSyncMessage(`Could not save sale: ${positionResult.error || 'Unknown error'}`)
      return
    }
    await tracking.recordActivity({ type: 'realized_gain', amount: realizedGain, effectiveDate: sellForm.saleDate, note: `${pos.ticker} sale` })
    setSellSaving(false)
    cancelSell()
    setSyncMessage(`Sold ${sharesSold} ${pos.ticker} share${sharesSold === 1 ? '' : 's'} at $${price.toFixed(2)} · ${realizedGain >= 0 ? '+' : '−'}$${Math.abs(realizedGain).toFixed(2)} realized.`)
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
    })
    setEditSaving(false)
    if (result?.success === false) {
      setSyncMessage(`Could not save changes: ${result.error || 'Unknown error'}`)
      return
    }
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
  }
}
