import { useEffect, useRef, useState } from 'react'
import { doc, onSnapshot, setDoc } from 'firebase/firestore'
import { db } from './firebase.js'
import { useAuth } from './FirebaseAuthContext.jsx'
import { projectionConfig } from './projectionEngine.js'
import { mostRecentWeeklyRefreshMs, refreshBoundaryLabel } from './marketCalendar.js'

function calibrationDocRef(uid) {
  const config = projectionConfig.parametric_calibration
  return doc(db, 'portfolios', uid, config.collection_path, config.document_id)
}

/**
 * Freezes the Monte Carlo risk profile between calibrations so the plan doesn't reshuffle
 * with every intraday price tick - a retirement plan whose basis visibly changes every time
 * the page reloads is worse than one held steady. Recalibrates automatically once the most
 * recent weekly refresh boundary (Friday market close by default) has passed since the last
 * calibration, or as soon as a new position/deposit-like activity lands (`lastActivityAt`
 * moves forward), whichever comes first - both checked lazily on the next page load, since
 * there is no per-user backend job to push it earlier - and exposes a manual override for
 * the same recalibration.
 */
export function usePortfolioMonteCarloCalibration(riskProfile, lastActivityAt) {
  const { currentUser } = useAuth()
  const [cached, setCached] = useState(null)
  const [loading, setLoading] = useState(true)
  const writingRef = useRef(false)

  useEffect(() => {
    if (!currentUser) { setCached(null); setLoading(false); return undefined }
    setLoading(true)
    const unsubscribe = onSnapshot(calibrationDocRef(currentUser.uid), (snapshot) => {
      setCached(snapshot.exists() ? snapshot.data() : null)
      setLoading(false)
    }, () => setLoading(false))
    return unsubscribe
  }, [currentUser])

  const weeklyBoundaryMs = mostRecentWeeklyRefreshMs()
  const staleByWeeklyClose = !cached?.computedAt || Date.parse(cached.computedAt) < weeklyBoundaryMs
  const staleByActivity = Boolean(lastActivityAt) && Boolean(cached?.basisLastActivityAt) && lastActivityAt > cached.basisLastActivityAt
  const isStale = !cached || staleByWeeklyClose || staleByActivity

  const persist = async (profile) => {
    if (!currentUser || !profile?.available || writingRef.current) return
    writingRef.current = true
    try {
      const record = { ...profile, computedAt: new Date().toISOString(), basisLastActivityAt: lastActivityAt || null }
      await setDoc(calibrationDocRef(currentUser.uid), record)
      setCached(record)
    } finally {
      writingRef.current = false
    }
  }

  // Recomputes only when the profile's own content changes or staleness flips - not on every
  // render, which would fire a Firestore write per keystroke on an unrelated lever.
  useEffect(() => {
    if (loading || !currentUser || !riskProfile?.available || !isStale) return
    persist(riskProfile)
  }, [loading, currentUser, riskProfile?.available, riskProfile?.annualReturn, riskProfile?.observations, riskProfile?.endDate, isStale])

  const active = cached && !isStale ? cached : (riskProfile?.available ? riskProfile : null)
  const refreshLabel = refreshBoundaryLabel()
  const staleReason = !cached ? null
    : staleByActivity ? 'a new position or deposit-like activity'
      : staleByWeeklyClose ? `this week's ${refreshLabel}`
        : null
  return {
    riskProfile: active,
    calibratedAt: cached?.computedAt || null,
    staleReason,
    refreshLabel,
    stale: isStale,
    loading,
    recalibrate: () => persist(riskProfile),
  }
}
