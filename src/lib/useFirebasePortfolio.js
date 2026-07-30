import { useState, useEffect } from 'react'
import {
  collection,
  doc,
  getDocs,
  setDoc,
  deleteDoc,
  query,
  orderBy
} from 'firebase/firestore'
import { db } from './firebase'
import { useAuth } from './FirebaseAuthContext'
import { planReferencePortfolioSync } from './referencePortfolio'

export function useFirebasePortfolio() {
  const { currentUser } = useAuth()
  const [positions, setPositions] = useState([])
  const [loading, setLoading] = useState(true)
  const [migrated, setMigrated] = useState(false)

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
      const q = query(positionsRef, orderBy('purchaseDate', 'desc'))
      const snapshot = await getDocs(q)

      const loadedPositions = []
      snapshot.forEach((doc) => {
        loadedPositions.push({ id: doc.id, ...doc.data() })
      })

      setPositions(loadedPositions)
      return loadedPositions
    } catch (error) {
      console.error('Failed to load positions:', error)
      return []
    }
  }

  // Initialize portfolio on auth change
  useEffect(() => {
    const init = async () => {
      if (!currentUser) {
        setPositions([])
        setLoading(false)
        return
      }

      setLoading(true)

      // Try to migrate from localStorage first
      if (!migrated) {
        await migrateFromLocalStorage(currentUser.uid)
        setMigrated(true)
      }

      // Load from Firestore
      await loadPositions(currentUser.uid)
      setLoading(false)
    }

    init()
  }, [currentUser])

  // Add new position
  const addPosition = async (ticker, shares, costBasis, purchaseDate = new Date().toISOString().split('T')[0]) => {
    if (!currentUser) {
      alert('Please log in to add positions')
      return
    }

    try {
      const positionId = `${ticker.toUpperCase()}-${Date.now()}`
      const newPosition = {
        ticker: ticker.toUpperCase(),
        shares: parseFloat(shares),
        costBasis: parseFloat(costBasis),
        purchaseDate,
        addedAt: new Date().toISOString(),
        id: positionId
      }

      await setDoc(doc(db, 'portfolios', currentUser.uid, 'positions', positionId), newPosition)

      setPositions(prev => [...prev, newPosition])
      return { success: true }
    } catch (error) {
      console.error('Failed to add position:', error)
      return { success: false, error: error.message }
    }
  }

  // Remove position
  const removePosition = async (positionId) => {
    if (!currentUser) return

    try {
      await deleteDoc(doc(db, 'portfolios', currentUser.uid, 'positions', positionId))
      setPositions(prev => prev.filter(p => p.id !== positionId))
      return { success: true }
    } catch (error) {
      console.error('Failed to remove position:', error)
      return { success: false, error: error.message }
    }
  }

  // Update position
  const updatePosition = async (positionId, updates) => {
    if (!currentUser) return

    try {
      const positionRef = doc(db, 'portfolios', currentUser.uid, 'positions', positionId)
      await setDoc(positionRef, updates, { merge: true })

      setPositions(prev => prev.map(p =>
        p.id === positionId ? { ...p, ...updates } : p
      ))
      return { success: true }
    } catch (error) {
      console.error('Failed to update position:', error)
      return { success: false, error: error.message }
    }
  }

  // Merge the user's supplied brokerage snapshot without duplicating symbols already saved.
  // Existing positions keep their shares, cost basis, and dates, but receive newer
  // snapshot metadata and normalized ticker casing.
  // This is explicit rather than automatic because it writes to the signed-in cloud portfolio.
  const syncReferencePortfolio = async () => {
    if (!currentUser) return { success: false, error: 'Please sign in first' }
    try {
      const importedAt = new Date().toISOString()
      const operations = planReferencePortfolioSync(positions)
      const synced = await Promise.all(operations.map(async (operation) => {
        const record = operation.kind === 'add'
          ? { ...operation.record, id: operation.id, purchaseDate: '', importedAt }
          : { ...operation.record, syncedAt: importedAt }
        await setDoc(
          doc(db, 'portfolios', currentUser.uid, 'positions', operation.id),
          record,
          { merge: operation.kind === 'update' }
        )
        return { ...operation, record }
      }))
      const syncedById = new Map(synced.map((operation) => [operation.id, operation.record]))
      setPositions((previous) => {
        const updated = previous.map((position) => syncedById.get(position.id) || position)
        return [
          ...updated,
          ...synced.filter((operation) => operation.kind === 'add').map((operation) => operation.record),
        ]
      })
      const added = synced.filter((operation) => operation.kind === 'add').length
      return { success: true, added, updated: synced.length - added }
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
      alert('Please log in to import portfolio')
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
    addPosition,
    removePosition,
    updatePosition,
    clearAll,
    exportPortfolio,
    importPortfolio,
    syncReferencePortfolio
  }
}
