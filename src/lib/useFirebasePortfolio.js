import { useState, useEffect } from 'react'
import {
  collection,
  doc,
  getDocs,
  onSnapshot,
  setDoc,
  deleteDoc,
  writeBatch,
} from 'firebase/firestore'
import { db } from './firebase'
import { useAuth } from './FirebaseAuthContext'
import {
  planReferencePortfolioSync,
  REFERENCE_PORTFOLIO,
  REFERENCE_PORTFOLIO_RECORDED_AT,
  REFERENCE_PORTFOLIO_VERSION,
} from './referencePortfolio'
import { normalizePortfolioPosition, PER_SHARE_COST } from './portfolioPosition'

const hiddenStorageKey = (userId) => `valuesignal.hiddenPositions.${userId}`
// DECJ was a typo for DECK, which is a real holding and already tracked separately. No
// provider resolves DECJ, so a position in it can never be priced and it silently subtracted
// from every portfolio measure that needs full coverage. The retirement used to apply only to
// the reference-import document, which left a hand-entered copy in place and unpriceable;
// matching on the ticker alone is what actually clears it.
//
// TTM and AMZM (Round 7 Task 1): the two missing_price_tickers breaching
// data_quality_counters. TTM is the Tata Motors NYSE ADR, delisted January 2025 - no
// provider serves that line anymore. AMZM resolves to nothing at any provider and is most
// likely a typo for AMZN; if the position was real, re-add AMZN with its actual cost basis.
// The matching pipeline-side list is RETIRED_SYMBOLS in pipeline/fetch_advisor.py, which
// stops the refresh from re-seeding either symbol out of the previous run's coverage.
const RETIRED_TICKERS = new Set(['DECJ', 'TTM', 'AMZM'])
const isRetiredReferencePosition = (documentId, stored = {}) =>
  RETIRED_TICKERS.has(String(stored.ticker || '').trim().toUpperCase())

export function useFirebasePortfolio() {
  const { currentUser } = useAuth()
  const [positions, setPositions] = useState([])
  const [loading, setLoading] = useState(true)
  const [migrated, setMigrated] = useState(false)
  const [syncState, setSyncState] = useState({ connected: false, lastSyncedAt: null, error: '' })

  // Migrate from localStorage to Firestore (one-time)
  const migrateFromLocalStorage = async (userId) => {
    try {
      // Check if already migrated
      const migratedKey = `valuesignal.migrated.${userId}`
      if (localStorage.getItem(migratedKey)) {
        return false // Already migrated
      }

      // Look for old localStorage data
      const oldKeys = Object.keys(localStorage).filter(key =>
        key.startsWith('valuesignal.portfolio.')
      )

      if (oldKeys.length === 0) {
        localStorage.setItem(migratedKey, 'true')
        return false // No data to migrate
      }

      // Ask user for confirmation
      const shouldMigrate = window.confirm(
        'Found existing portfolio data in this browser. Would you like to sync it to your cloud account?'
      )

      if (!shouldMigrate) {
        localStorage.setItem(migratedKey, 'true')
        return false
      }

      // Migrate data
      let migratedCount = 0
      for (const key of oldKeys) {
        try {
          const data = JSON.parse(localStorage.getItem(key))
          if (Array.isArray(data)) {
            // Migrate each position
            for (const position of data) {
              const positionId = position.id || `${position.ticker}-${Date.now()}-${Math.random()}`
              await setDoc(doc(db, 'portfolios', userId, 'positions', positionId), {
                ...position,
                id: positionId,
                migratedAt: new Date().toISOString()
              })
              migratedCount++
            }
          }
        } catch (e) {
          console.error('Failed to migrate position:', e)
        }
      }

      // Mark as migrated
      localStorage.setItem(migratedKey, 'true')

      if (migratedCount > 0) {
        alert(`Successfully migrated ${migratedCount} positions to cloud storage!`)
      }

      return true
    } catch (error) {
      console.error('Migration error:', error)
      return false
    }
  }

  // Load positions from Firestore
  const loadPositions = async (userId) => {
    try {
      const positionsRef = collection(db, 'portfolios', userId, 'positions')
      // Firestore orderBy excludes documents where the ordered field is missing. Some
      // migrated and brokerage-synced positions predate purchaseDate, so ordering in the
      // query made otherwise valid holdings disappear from the portfolio.
      const snapshot = await getDocs(positionsRef)

      const loadedPositions = []
      const repairWrites = []
      snapshot.forEach((snapshotDoc) => {
        if (isRetiredReferencePosition(snapshotDoc.id, snapshotDoc.data())) {
          repairWrites.push(deleteDoc(snapshotDoc.ref))
          return
        }
        const { position, firestoreUpdates } = normalizePortfolioPosition(
          snapshotDoc.id,
          snapshotDoc.data(),
        )
        loadedPositions.push(position)
        if (firestoreUpdates) {
          repairWrites.push(setDoc(snapshotDoc.ref, firestoreUpdates, { merge: true }))
        }
      })
      // The repaired value is already used in memory. Persist it best-effort so all devices
      // converge without making a transient write failure hide the rest of the portfolio.
      await Promise.allSettled(repairWrites)
      loadedPositions.sort((left, right) =>
        String(right.purchaseDate || right.addedAt || '').localeCompare(
          String(left.purchaseDate || left.addedAt || '')
        ))

      setPositions(loadedPositions)
      return loadedPositions
    } catch (error) {
      console.error('Failed to load positions:', error)
      return []
    }
  }

  // Subscribe instead of reading once: changes committed on one signed-in device now
  // reach every other device using the same Firebase account without a reload.
  useEffect(() => {
    if (!currentUser) {
      setPositions([])
      setLoading(false)
      setSyncState({ connected: false, lastSyncedAt: null, error: '' })
      return undefined
    }
    const userId = currentUser.uid
    setLoading(true)
    try { localStorage.removeItem(hiddenStorageKey(userId)) } catch { /* legacy cleanup only */ }
    if (!migrated) migrateFromLocalStorage(userId).finally(() => setMigrated(true))
    const unsubscribe = onSnapshot(collection(db, 'portfolios', userId, 'positions'), async (snapshot) => {
      const loadedPositions = []
      const repairWrites = []
      snapshot.forEach((snapshotDoc) => {
        if (isRetiredReferencePosition(snapshotDoc.id, snapshotDoc.data())) {
          repairWrites.push(deleteDoc(snapshotDoc.ref))
          return
        }
        const { position, firestoreUpdates } = normalizePortfolioPosition(snapshotDoc.id, snapshotDoc.data())
        loadedPositions.push(position)
        if (firestoreUpdates) repairWrites.push(setDoc(snapshotDoc.ref, firestoreUpdates, { merge: true }))
      })
      await Promise.allSettled(repairWrites)
      loadedPositions.sort((left, right) => String(right.purchaseDate || right.addedAt || '').localeCompare(String(left.purchaseDate || left.addedAt || '')))
      setPositions(loadedPositions)
      setLoading(false)
      setSyncState({ connected: true, lastSyncedAt: new Date().toISOString(), error: '' })
    }, (error) => {
      console.error('Portfolio subscription failed:', error)
      setLoading(false)
      setSyncState({ connected: false, lastSyncedAt: null, error: error.message })
    })
    return unsubscribe
  }, [currentUser, migrated])

  // Add new position
  const addPosition = async (ticker, shares, costBasis, purchaseDate = new Date().toISOString().split('T')[0], costBasisInputMode = 'share') => {
    if (!currentUser) {
      alert('Firebase is not connected. Reconnect cloud data before adding positions.')
      return
    }

    try {
      const positionId = `${ticker.toUpperCase()}-${Date.now()}`
      const newPosition = {
        ticker: ticker.toUpperCase(),
        shares: parseFloat(shares),
        costBasis: parseFloat(costBasis),
        costBasisUnit: PER_SHARE_COST,
        costBasisInputMode,
        purchaseDate,
        addedAt: new Date().toISOString(),
        id: positionId
      }

      const batch = writeBatch(db)
      batch.set(doc(db, 'portfolios', currentUser.uid, 'positions', positionId), newPosition)
      batch.set(doc(db, 'portfolios', currentUser.uid, 'activity', `position-added-${Date.now()}`), {
        type: 'position_added', ticker: newPosition.ticker, shares: newPosition.shares,
        pricePerShare: newPosition.costBasis, amount: newPosition.shares * newPosition.costBasis,
        effectiveDate: purchaseDate, recordedAt: new Date().toISOString(), source: 'manual_holding_entry',
      })
      batch.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), {
        lastActivityAt: new Date().toISOString(), ledgerComplete: false,
      }, { merge: true })
      await batch.commit()
      return { success: true }
    } catch (error) {
      console.error('Failed to add position:', error)
      return { success: false, error: error.message }
    }
  }

  const removePosition = async (positionId) => {
    if (!currentUser) return

    try {
      const removed = positions.find((position) => position.id === positionId)
      const batch = writeBatch(db)
      batch.delete(doc(db, 'portfolios', currentUser.uid, 'positions', positionId))
      batch.set(doc(db, 'portfolios', currentUser.uid, 'activity', `position-removed-${Date.now()}`), {
        type: 'position_removed', ticker: removed?.ticker || null, shares: removed?.shares || null,
        recordedAt: new Date().toISOString(), source: 'manual_holding_removal',
        note: 'Removal is not treated as a sale. Realized proceeds must be recorded separately.',
      })
      batch.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), { ledgerComplete: false }, { merge: true })
      await batch.commit()
      return { success: true }
    } catch (error) {
      console.error('Firestore delete failed:', error)
      setSyncState((current) => ({ ...current, connected: false, error: error.message }))
      return { success: false, error: error.message }
    }
  }

  // Update position
  const updatePosition = async (positionId, updates) => {
    if (!currentUser) return

    try {
      const positionRef = doc(db, 'portfolios', currentUser.uid, 'positions', positionId)
      const batch = writeBatch(db)
      batch.set(positionRef, { ...updates, updatedAt: new Date().toISOString() }, { merge: true })
      batch.set(doc(db, 'portfolios', currentUser.uid, 'activity', `position-updated-${Date.now()}`), {
        type: 'position_updated', positionId,
        ticker: positions.find((position) => position.id === positionId)?.ticker || null,
        updates, recordedAt: new Date().toISOString(), source: 'manual_holding_edit',
      })
      await batch.commit()
      return { success: true }
    } catch (error) {
      console.error('Failed to update position:', error)
      return { success: false, error: error.message }
    }
  }

  // Reconcile the signed-in portfolio to the user's Aug 14 Fidelity positions export. The
  // export is the authoritative invested baseline, so this updates quantities and total cost
  // bases, adds missing symbols, removes symbols no longer present, and stores the export as
  // an invested-only intraday observation. Money-market cash and pending activity never enter
  // the position collection or the chart snapshot.
  const syncReferencePortfolio = async () => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    try {
      const importedAt = new Date().toISOString()
      const operations = planReferencePortfolioSync(positions)
      const batch = writeBatch(db)
      operations.forEach((operation) => {
        const positionRef = doc(db, 'portfolios', currentUser.uid, 'positions', operation.id)
        if (operation.kind === 'remove') {
          batch.delete(positionRef)
          return
        }
        const record = operation.kind === 'add'
          ? { ...operation.record, id: operation.id, purchaseDate: '', importedAt }
          : { ...operation.record, syncedAt: importedAt }
        batch.set(positionRef, record, { merge: operation.kind === 'update' })
      })

      const investedValue = REFERENCE_PORTFOLIO.reduce((sum, position) => sum + position.snapshotValue, 0)
      const prices = REFERENCE_PORTFOLIO.map((position) => ({
        ticker: position.ticker,
        shares: position.shares,
        price: position.snapshotPrice,
        value: position.snapshotValue,
        previousClose: position.snapshotPreviousClose,
        marketTime: REFERENCE_PORTFOLIO_RECORDED_AT,
      }))
      const snapshotId = REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 16).replace(/[:.]/g, '-')
      batch.set(doc(db, 'portfolios', currentUser.uid, 'intradaySnapshots', snapshotId), {
        value: investedValue,
        investedValue,
        coveragePct: 100,
        source: 'fidelity_positions_export',
        recordedAt: REFERENCE_PORTFOLIO_RECORDED_AT,
        marketDate: REFERENCE_PORTFOLIO_RECORDED_AT.slice(0, 10),
        positionCount: REFERENCE_PORTFOLIO.length,
        prices,
      }, { merge: true })
      batch.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), {
        referencePortfolioVersion: REFERENCE_PORTFOLIO_VERSION,
        referencePortfolioImportedAt: importedAt,
      }, { merge: true })
      await batch.commit()

      return {
        success: true,
        added: operations.filter((operation) => operation.kind === 'add').length,
        updated: operations.filter((operation) => operation.kind === 'update').length,
        removed: operations.filter((operation) => operation.kind === 'remove').length,
        version: REFERENCE_PORTFOLIO_VERSION,
      }
    } catch (error) {
      console.error('Failed to sync reference portfolio:', error)
      return { success: false, error: error.message }
    }
  }

  // Clear all positions
  const clearAll = async () => {
    if (!currentUser) return

    const confirmed = window.confirm('Are you sure you want to delete all positions? This cannot be undone.')
    if (!confirmed) return

    try {
      const positionsRef = collection(db, 'portfolios', currentUser.uid, 'positions')
      const snapshot = await getDocs(positionsRef)

      const deletePromises = []
      snapshot.forEach((doc) => {
        deletePromises.push(deleteDoc(doc.ref))
      })

      await Promise.all(deletePromises)
      setPositions([])
      return { success: true }
    } catch (error) {
      console.error('Failed to clear positions:', error)
      return { success: false, error: error.message }
    }
  }

  // Export portfolio (same as before, but from Firestore data)
  const exportPortfolio = () => {
    if (!currentUser) return

    const data = {
      exportDate: new Date().toISOString(),
      userId: currentUser.uid,
      userEmail: currentUser.email,
      positions
    }

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `valuesignal-portfolio-${new Date().toISOString().split('T')[0]}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Import portfolio
  const importPortfolio = async (file) => {
    if (!currentUser) {
      alert('Firebase is not connected. Reconnect cloud data before importing a portfolio.')
      return
    }

    const reader = new FileReader()
    reader.onload = async (e) => {
      try {
        const data = JSON.parse(e.target.result)
        if (!data.positions || !Array.isArray(data.positions)) {
          alert('Invalid portfolio file format')
          return
        }

        const confirmed = window.confirm(
          `Import ${data.positions.length} positions? This will add to your existing portfolio.`
        )
        if (!confirmed) return

        // Import positions to Firestore
        for (const position of data.positions) {
          const positionId = position.id || `${position.ticker}-${Date.now()}-${Math.random()}`
          await setDoc(doc(db, 'portfolios', currentUser.uid, 'positions', positionId), {
            ...position,
            id: positionId,
            importedAt: new Date().toISOString()
          })
        }

        // Reload positions
        await loadPositions(currentUser.uid)
        alert('Portfolio imported successfully!')
      } catch (error) {
        console.error('Import error:', error)
        alert('Failed to import portfolio: ' + error.message)
      }
    }
    reader.readAsText(file)
  }

  return {
    positions,
    loading,
    syncState,
    addPosition,
    removePosition,
    updatePosition,
    clearAll,
    exportPortfolio,
    importPortfolio,
    syncReferencePortfolio
  }
}
