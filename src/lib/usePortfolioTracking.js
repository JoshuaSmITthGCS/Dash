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
    if (!currentUser || !Number.isFinite(Number(value))) return { success: false, error: 'A signed-in account and portfolio value are required.' }
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
    if (!currentUser || !['realized_gain', 'dividend', 'fee'].includes(type) || !Number.isFinite(Number(amount))) return { success: false, error: 'Choose an activity type and enter a valid amount.' }
    try {
      await ensureTrackingStarted()
      const recordedAt = new Date().toISOString()
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'activity', `${type}-${Date.now()}`), {
        type, amount: Number(amount), effectiveDate, note, recordedAt, source: 'manual_earnings_ledger',
      })
      return { success: true }
    } catch (reason) {
      setError(reason.message)
      return { success: false, error: reason.message }
    }
  }

  const setLedgerComplete = async (ledgerComplete) => {
    if (!currentUser) return { success: false, error: 'Sign in first.' }
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

  return { snapshots, activities, trackingState: effectiveTrackingState, error, recordSnapshot, recordActivity, setLedgerComplete }
}

export { marketDate }
