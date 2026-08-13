import { useEffect, useState } from 'react'
import { collection, doc, increment, onSnapshot, setDoc, writeBatch } from 'firebase/firestore'
import { db } from './firebase.js'
import { useAuth } from './FirebaseAuthContext.jsx'
import { FIDELITY_CASH_FLOWS } from './referenceCashFlows.js'

function marketDate(iso = new Date().toISOString()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(iso))
}

export function usePortfolioTracking() {
  const { currentUser } = useAuth()
  const [snapshots, setSnapshots] = useState([])
  const [activities, setActivities] = useState([])
  const [trackingState, setTrackingState] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!currentUser) {
      setSnapshots([]); setActivities([]); setTrackingState(null); setError('')
      return undefined
    }
    const userId = currentUser.uid
    const stopState = onSnapshot(doc(db, 'portfolios', userId, 'tracking', 'state'), (snapshot) => {
      setTrackingState(snapshot.exists() ? snapshot.data() : null)
    }, (reason) => setError(reason.message))
    const stopSnapshots = onSnapshot(collection(db, 'portfolios', userId, 'intradaySnapshots'), (snapshot) => {
      setSnapshots(snapshot.docs.map((item) => ({ id: item.id, ...item.data() })).sort((a, b) => String(a.recordedAt).localeCompare(String(b.recordedAt))))
    }, (reason) => setError(reason.message))
    const stopActivities = onSnapshot(collection(db, 'portfolios', userId, 'activity'), (snapshot) => {
      setActivities(snapshot.docs.map((item) => ({ id: item.id, ...item.data() })).sort((a, b) => String(b.effectiveDate || b.recordedAt).localeCompare(String(a.effectiveDate || a.recordedAt))))
    }, (reason) => setError(reason.message))
    return () => { stopState(); stopSnapshots(); stopActivities() }
  }, [currentUser])

  const derivedStartedAt = trackingState?.trackingStartedAt || activities.map((row) => row.recordedAt).filter(Boolean).sort()[0] || null
  const effectiveTrackingState = (trackingState || derivedStartedAt)
    ? { ...trackingState, trackingStartedAt: derivedStartedAt }
    : null

  const ensureTrackingStarted = async () => {
    if (!currentUser) return
    const startedAt = derivedStartedAt || new Date().toISOString()
    await setDoc(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), { trackingStartedAt: startedAt }, { merge: true })
    setTrackingState((current) => ({ ...current, trackingStartedAt: startedAt }))
  }

  const recordSnapshot = async ({ value, coveragePct, source, recordedAt = new Date().toISOString() }) => {
    if (!currentUser || !Number.isFinite(Number(value))) return { success: false, error: 'A Firebase connection and portfolio value are required.' }
    try {
      await ensureTrackingStarted()
      const id = recordedAt.slice(0, 16).replace(/[:.]/g, '-')
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'intradaySnapshots', id), {
        value: Number(value), coveragePct: Number(coveragePct) || 0, source,
        recordedAt, marketDate: marketDate(recordedAt),
      }, { merge: true })
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  const recordActivity = async ({ type, amount, effectiveDate, note = '' }) => {
    const cashMovement = ['deposit', 'withdrawal', 'sale_proceeds', 'stock_purchase'].includes(type)
    const cashIncrease = ['deposit', 'sale_proceeds'].includes(type)
    // Counted toward net invested capital (see portfolioAnalytics.js CONTRIBUTION_TYPES) but
    // never touches the tracked uninvested-cash balance -- the money went straight into the
    // position, it never sat as cash.
    const contributionOnly = type === 'external_contribution'
    const numericAmount = Number(amount)
    if (!currentUser || !['deposit', 'withdrawal', 'sale_proceeds', 'stock_purchase', 'realized_gain', 'dividend', 'fee', 'external_contribution'].includes(type) || !Number.isFinite(numericAmount) || ((cashMovement || contributionOnly) && numericAmount <= 0)) return { success: false, error: 'Choose an activity type and enter a valid amount. Cash movements must be greater than zero.' }
    if (cashMovement && !cashIncrease && numericAmount > Number(effectiveTrackingState?.cashBalance || 0)) return { success: false, error: 'That amount is larger than the tracked uninvested cash balance. Set the current balance first if Dash is behind.' }
    try {
      await ensureTrackingStarted()
      const recordedAt = new Date().toISOString()
      const batch = writeBatch(db)
      batch.set(doc(db, 'portfolios', currentUser.uid, 'activity', `${type}-${Date.now()}`), {
        type, amount: numericAmount, effectiveDate, note, recordedAt,
        source: cashMovement ? 'manual_cash_tracker' : contributionOnly ? 'add_position_new_money' : 'manual_earnings_ledger',
      })
      if (cashMovement) batch.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), {
        cashBalance: increment(cashIncrease ? numericAmount : -numericAmount),
        cashTrackingEnabled: true,
        cashBalanceUpdatedAt: recordedAt,
      }, { merge: true })
      await batch.commit()
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  const setCashBalance = async ({ amount, effectiveDate, note = '' }) => {
    const numericAmount = Number(amount)
    if (!currentUser || !Number.isFinite(numericAmount) || numericAmount < 0) return { success: false, error: 'Enter a valid cash balance of zero or more.' }
    try {
      await ensureTrackingStarted()
      const recordedAt = new Date().toISOString()
      const batch = writeBatch(db)
      batch.set(doc(db, 'portfolios', currentUser.uid, 'activity', `cash-balance-${Date.now()}`), {
        type: 'cash_balance_adjustment', amount: numericAmount,
        previousAmount: Number(effectiveTrackingState?.cashBalance || 0), effectiveDate, note,
        recordedAt, source: 'manual_cash_reconciliation',
      })
      batch.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), {
        cashBalance: numericAmount, cashTrackingEnabled: true,
        cashBalanceAsOf: effectiveDate, cashBalanceUpdatedAt: recordedAt,
      }, { merge: true })
      await batch.commit()
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  const syncReferenceCashFlows = async () => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    try {
      const importedAt = new Date().toISOString()
      await Promise.all(FIDELITY_CASH_FLOWS.map((row) => setDoc(
        doc(db, 'portfolios', currentUser.uid, 'activity', row.id),
        { ...row, recordedAt: importedAt, source: 'user_provided_fidelity_history' },
        { merge: true },
      )))
      const patch = {
        cashFlowHistoryComplete: true,
        fidelityHistoryImported: true,
        fidelityHistoryImportedAt: importedAt,
        trackingStartedAt: derivedStartedAt || importedAt,
        cashBalance: trackingState?.cashTrackingEnabled ? Number(trackingState.cashBalance || 0) : 0.42,
        cashTrackingEnabled: true,
        cashBalanceAsOf: trackingState?.cashTrackingEnabled ? trackingState.cashBalanceAsOf || marketDate(importedAt) : '2026-08-04',
        cashBalanceUpdatedAt: trackingState?.cashTrackingEnabled ? trackingState.cashBalanceUpdatedAt || importedAt : importedAt,
      }
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), patch, { merge: true })
      setTrackingState((current) => ({ ...current, ...patch }))
      return { success: true, count: FIDELITY_CASH_FLOWS.length }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  const setLedgerComplete = async (ledgerComplete) => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    try {
      await ensureTrackingStarted()
      const patch = { ledgerComplete: Boolean(ledgerComplete), ledgerConfirmedAt: ledgerComplete ? new Date().toISOString() : null }
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), patch, { merge: true })
      setTrackingState((current) => ({ ...current, ...patch }))
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  return { snapshots, activities, trackingState: effectiveTrackingState, error, recordSnapshot, recordActivity, setCashBalance, setLedgerComplete, syncReferenceCashFlows }
}

export { marketDate }
