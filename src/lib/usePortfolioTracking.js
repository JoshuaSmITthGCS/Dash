import { useEffect, useState } from 'react'
import { collection, doc, onSnapshot, setDoc } from 'firebase/firestore'
import { db } from './firebase.js'
import { useAuth } from './FirebaseAuthContext.jsx'

function marketDate(iso = new Date().toISOString()) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date(iso))
}

export function usePortfolioTracking() {
  const { currentUser } = useAuth()
  const [snapshots, setSnapshots] = useState([])
  const [activities, setActivities] = useState([])
  const [rebalances, setRebalances] = useState([])
  const [trackingState, setTrackingState] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!currentUser) {
      setSnapshots([]); setActivities([]); setRebalances([]); setTrackingState(null); setError('')
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
    const stopRebalances = onSnapshot(collection(db, 'portfolios', userId, 'rebalances'), (snapshot) => {
      setRebalances(snapshot.docs.map((item) => ({ id: item.id, ...item.data() })).sort((a, b) => String(a.date || '').localeCompare(String(b.date || ''))))
    }, (reason) => setError(reason.message))
    return () => { stopState(); stopSnapshots(); stopActivities(); stopRebalances() }
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

  const recordSnapshot = async ({ value, coveragePct, source, unrealizedGain, recordedAt = new Date().toISOString() }) => {
    if (!currentUser || !Number.isFinite(Number(value))) return { success: false, error: 'A Firebase connection and portfolio value are required.' }
    try {
      await ensureTrackingStarted()
      const id = recordedAt.slice(0, 16).replace(/[:.]/g, '-')
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'intradaySnapshots', id), {
        value: Number(value), coveragePct: Number(coveragePct) || 0, source,
        // Recorded alongside value, not derived later, so the reconciliation bridge
        // (portfolioReconciliationBridge, src/lib/portfolioAnalytics.js) has an unrealized-gain
        // figure at the exact instant each snapshot was taken, not just today's live one.
        ...(Number.isFinite(Number(unrealizedGain)) ? { unrealizedGain: Number(unrealizedGain) } : {}),
        recordedAt, marketDate: marketDate(recordedAt),
      }, { merge: true })
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  const recordActivity = async ({ type, amount, effectiveDate, note = '' }) => {
    const numericAmount = Number(amount)
    if (!currentUser || !['realized_gain', 'dividend', 'fee', 'deposit', 'withdrawal'].includes(type) || !Number.isFinite(numericAmount)) return { success: false, error: 'Choose a supported activity type and enter a valid amount.' }
    try {
      await ensureTrackingStarted()
      const recordedAt = new Date().toISOString()
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'activity', `${type}-${Date.now()}`), {
        type, amount: numericAmount, effectiveDate, note, recordedAt,
        source: 'manual_earnings_ledger',
      })
      return { success: true }
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

  // Captured once per add/edit/remove/sell -- see usePortfolioForms.js's four call sites --
  // so executionStatistics() (src/lib/portfolioStatistics.js) has real turnover input instead
  // of the empty list that silently made every turnover figure read "Insufficient" before this.
  const recordRebalance = async ({ date, beforeWeights, afterWeights }) => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    try {
      await ensureTrackingStarted()
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'rebalances', `${date}-${Date.now()}`), {
        date, beforeWeights, afterWeights, recordedAt: new Date().toISOString(),
      })
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  return {
    snapshots, activities, rebalances, trackingState: effectiveTrackingState, error,
    recordSnapshot, recordActivity, setLedgerComplete, recordRebalance,
  }
}

export { marketDate }
