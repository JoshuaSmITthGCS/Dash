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
  referenceIntradaySnapshot,
  referenceSyncRecord,
  referenceTrackingState,
  summarizeReferenceSync,
  REFERENCE_PORTFOLIO_VERSION,
} from './referencePortfolio'
import { normalizePortfolioPosition, PER_SHARE_COST } from './portfolioPosition'
import { buildPortfolioExport, planPortfolioImport } from './portfolioImport'

const hiddenStorageKey = (userId) => `valuesignal.hiddenPositions.${userId}`
// DECJ was a typo for DECK, which is a real holding and already tracked separately. No
// provider resolves DECJ, so a position in it can never be priced and it silently subtracted
// from every portfolio measure that needs full coverage. The retirement used to apply only to
// the reference-import document, which left a hand-entered copy in place and unpriceable;
// matching on the ticker alone is what actually clears it.
//
// TTM and AMZM (Round 7 Task 1): the two missing_price_tickers breaching
// data_quality_counters. TTM is the Tata Motors NYSE ADR, delisted January 2025 - no
// provider serves that line anymore. AMZM resolves to nothing at any provider and was a typo
// for AMZN, which the Aug 25 Fidelity export confirms is a real holding (0.386 shares,
// $99.79 cost) and now carries in REFERENCE_PORTFOLIO. Only the AMZM misspelling stays
// retired; the correctly spelled AMZN is matched by neither set and syncs normally.
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

  // Reconcile the signed-in portfolio to the user's Aug 25 Fidelity positions export. The
  // export is the authoritative invested baseline, so this updates quantities and total cost
  // bases, adds missing symbols, removes symbols no longer present, and stores the export as
  // an invested-only intraday observation. Acquisition dates come from the account's
  // transaction history rather than the export, and a date already stored always wins -- see
  // planReferencePortfolioSync. Money-market cash and pending activity never enter the
  // position collection or the chart snapshot.
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
        batch.set(positionRef, referenceSyncRecord(operation, importedAt), {
          merge: operation.kind === 'update',
        })
      })

      const snapshot = referenceIntradaySnapshot()
      batch.set(
        doc(db, 'portfolios', currentUser.uid, 'intradaySnapshots', snapshot.id),
        snapshot.document,
        { merge: true },
      )
      batch.set(
        doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'),
        referenceTrackingState(importedAt),
        { merge: true },
      )
      await batch.commit()

      return { success: true, ...summarizeReferenceSync(operations), version: REFERENCE_PORTFOLIO_VERSION }
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

  // Written in the same shape importPortfolio reads, so a file this app produces can always
  // be fed back into it -- on this account or another one.
  const exportPortfolio = () => {
    if (!currentUser) return
    const document = buildPortfolioExport(positions, {
      source: `ValueSignal portfolio export · ${currentUser.email || currentUser.uid}`,
    })
    const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = `valuesignal-portfolio-${new Date().toISOString().split('T')[0]}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  /**
   * Writes an already-parsed holdings file to Firestore.
   *
   * Parsing and planning happen in portfolioImport.js before this is called, so the caller can
   * show exactly what will change and this only ever runs against a file already known to be
   * valid. Writes go in batches because Firestore caps one at 500 operations, and each batch
   * is committed in order so a partial failure leaves a prefix of the plan applied rather than
   * an arbitrary scatter of it.
   *
   * The reference-baseline marker is stamped afterwards on purpose: an import is a deliberate
   * statement about what is held, and without the marker the built-in Fidelity baseline would
   * reconcile it away the next time the app loaded.
   */
  const applyPortfolioImport = async (parsed, mode = 'replace') => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    if (!parsed?.ok) return { success: false, error: 'The file has not been validated.' }

    try {
      const importedAt = new Date().toISOString()
      const operations = planPortfolioImport(positions, parsed, mode)
      const root = (name) => collection(db, 'portfolios', currentUser.uid, name)

      for (let index = 0; index < operations.length; index += 450) {
        const batch = writeBatch(db)
        operations.slice(index, index + 450).forEach((operation) => {
          const positionRef = doc(root('positions'), operation.id)
          if (operation.kind === 'remove') {
            batch.delete(positionRef)
            return
          }
          const record = operation.kind === 'add'
            ? { ...operation.record, id: operation.id, importedAt }
            : { ...operation.record, importedAt }
          batch.set(positionRef, record, { merge: operation.kind === 'update' })
        })
        await batch.commit()
      }

      const summary = {
        added: operations.filter((operation) => operation.kind === 'add').length,
        updated: operations.filter((operation) => operation.kind === 'update').length,
        removed: operations.filter((operation) => operation.kind === 'remove').length,
      }
      const closing = writeBatch(db)
      closing.set(doc(root('activity'), `portfolio-imported-${Date.now()}`), {
        type: 'portfolio_imported',
        mode,
        positionCount: parsed.positions.length,
        source: parsed.meta.source || 'uploaded file',
        recordedAt: importedAt,
        ...summary,
      })
      closing.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), {
        referencePortfolioVersion: REFERENCE_PORTFOLIO_VERSION,
        referencePortfolioImportedAt: importedAt,
        lastImportAt: importedAt,
        ledgerComplete: false,
      }, { merge: true })
      await closing.commit()

      return { success: true, ...summary }
    } catch (error) {
      console.error('Failed to import portfolio:', error)
      return { success: false, error: error.message }
    }
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
    applyPortfolioImport,
    syncReferencePortfolio
  }
}
