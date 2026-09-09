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
  referenceSyncMerges,
  referenceSyncRecord,
  referenceTrackingState,
  seededTickersAfter,
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

// A ticker the user has sold out of completely. Stored per ticker (not per lot) because the
// question every consumer asks is "do I still own this?", and answered from Firestore rather
// than inferred from the absence of a position: absence is exactly what the Fidelity baseline
// sync treats as "missing, re-add it". See planReferencePortfolioSync's closedTickers.
const closedPositionId = (ticker) => String(ticker || '').trim().toUpperCase()

export function useFirebasePortfolio() {
  const { currentUser } = useAuth()
  const [positions, setPositions] = useState([])
  const [closedPositions, setClosedPositions] = useState([])
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
      setClosedPositions([])
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
    const unsubscribeClosed = onSnapshot(collection(db, 'portfolios', userId, 'closedPositions'), (snapshot) => {
      setClosedPositions(snapshot.docs
        .map((item) => ({ id: item.id, ...item.data() }))
        .sort((left, right) => String(right.saleDate || right.closedAt || '').localeCompare(String(left.saleDate || left.closedAt || ''))))
    }, (error) => {
      console.error('Closed-position subscription failed:', error)
    })
    return () => { unsubscribe(); unsubscribeClosed() }
  }, [currentUser, migrated])

  const closedTickers = closedPositions.map((row) => closedPositionId(row.ticker || row.id))

  // Marks a ticker as sold out of, so no later baseline sync re-creates it. Written by the
  // sell flows the moment a sale takes the last share; cleared by a fresh buy below.
  const recordClosedPosition = async (ticker, { saleDate = null, realizedGain = null, shares = null, price = null } = {}) => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    const id = closedPositionId(ticker)
    if (!id) return { success: false, error: 'A ticker is required.' }
    try {
      await setDoc(doc(db, 'portfolios', currentUser.uid, 'closedPositions', id), {
        ticker: id,
        saleDate: saleDate || new Date().toISOString().split('T')[0],
        closedAt: new Date().toISOString(),
        ...(Number.isFinite(Number(realizedGain)) ? { realizedGain: Number(realizedGain) } : {}),
        ...(Number.isFinite(Number(shares)) ? { shares: Number(shares) } : {}),
        ...(Number.isFinite(Number(price)) ? { price: Number(price) } : {}),
      }, { merge: true })
      return { success: true }
    } catch (error) {
      console.error('Failed to record closed position:', error)
      return { success: false, error: error.message }
    }
  }

  // Reopens a ticker: a buy, or an undo of a sale recorded by mistake.
  const clearClosedPosition = async (ticker) => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    const id = closedPositionId(ticker)
    if (!id) return { success: false, error: 'A ticker is required.' }
    try {
      await deleteDoc(doc(db, 'portfolios', currentUser.uid, 'closedPositions', id))
      return { success: true }
    } catch (error) {
      console.error('Failed to clear closed position:', error)
      return { success: false, error: error.message }
    }
  }

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
      batch.delete(doc(db, 'portfolios', currentUser.uid, 'closedPositions', closedPositionId(ticker)))
      await batch.commit()
      return { success: true }
    } catch (error) {
      console.error('Failed to add position:', error)
      return { success: false, error: error.message }
    }
  }

  // `sale: true` marks a removal that is the last leg of a recorded sale rather than a bare
  // "take this off my list". The difference matters to the cash-flow ledger: a bare removal
  // makes shares disappear with no proceeds recorded anywhere, which is exactly the state
  // ledgerComplete exists to deny, but a sale books its own realized_gain row on the way
  // through. Resetting the flag on a sale switched the money-weighted and time-weighted
  // returns off after every complete exit, and left the user re-ticking a deposits-and-
  // withdrawals checkbox that the sale had not invalidated.
  const removePosition = async (positionId, { sale = false } = {}) => {
    if (!currentUser) return

    try {
      const removed = positions.find((position) => position.id === positionId)
      const batch = writeBatch(db)
      batch.delete(doc(db, 'portfolios', currentUser.uid, 'positions', positionId))
      batch.set(doc(db, 'portfolios', currentUser.uid, 'activity', `position-removed-${Date.now()}`), {
        type: 'position_removed', ticker: removed?.ticker || null, shares: removed?.shares || null,
        recordedAt: new Date().toISOString(),
        source: sale ? 'sale_completed' : 'manual_holding_removal',
        note: sale
          ? 'Last shares of this lot sold. Proceeds are recorded as a realized_gain activity row.'
          : 'Removal is not treated as a sale. Realized proceeds must be recorded separately.',
      })
      if (!sale) {
        batch.set(doc(db, 'portfolios', currentUser.uid, 'tracking', 'state'), { ledgerComplete: false }, { merge: true })
      }
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

  // Seeds the signed-in portfolio from the user's Aug 25 Fidelity positions export, and
  // stores that export as an invested-only intraday observation for the value history.
  //
  // Seeding, not reconciling: the export is a photograph of one morning, and this Firestore
  // collection is the record of what is actually held. So this only ever hands over a
  // holding the account has never been given -- it does not restate a share count, a cost
  // basis or a date, and it never deletes. A ticker sold (closedTickers) or already
  // delivered once and since removed (seededTickers) is left alone permanently. The one
  // write onto an existing holding is a purchase-date backfill, which fills a blank rather
  // than overruling a stored answer. Money-market cash and pending activity never enter the
  // position collection or the chart snapshot.
  const syncReferencePortfolio = async ({ seededTickers = [] } = {}) => {
    if (!currentUser) return { success: false, error: 'Firebase is not connected.' }
    try {
      const importedAt = new Date().toISOString()
      const operations = planReferencePortfolioSync(positions, undefined, {
        closedTickers, seededTickers, mode: 'seed',
      })
      const batch = writeBatch(db)
      operations.forEach((operation) => {
        const positionRef = doc(db, 'portfolios', currentUser.uid, 'positions', operation.id)
        if (operation.kind === 'remove') {
          batch.delete(positionRef)
          return
        }
        batch.set(positionRef, referenceSyncRecord(operation, importedAt), {
          merge: referenceSyncMerges(operation),
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
        referenceTrackingState(importedAt, seededTickersAfter(operations, seededTickers)),
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
    closedPositions,
    closedTickers,
    loading,
    syncState,
    addPosition,
    removePosition,
    updatePosition,
    recordClosedPosition,
    clearClosedPosition,
    clearAll,
    exportPortfolio,
    applyPortfolioImport,
    syncReferencePortfolio
  }
}
