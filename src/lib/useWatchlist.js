import { useEffect, useState } from 'react'
import { collection, deleteDoc, doc, onSnapshot, setDoc } from 'firebase/firestore'
import { db } from './firebase'
import { useAuth } from './FirebaseAuthContext'

const LEGACY_KEY = 'valuesignal.watchlist'
const migratedKey = (userId) => `valuesignal.watchlistMigrated.${userId}`

function legacyTickers() {
  try {
    const raw = JSON.parse(localStorage.getItem(LEGACY_KEY))
    if (!Array.isArray(raw)) return []
    // Search.jsx's WATCH_KEY reader tolerates {ticker} objects too, so match that leniency here.
    return raw.map((item) => String(typeof item === 'string' ? item : item?.ticker || '').trim().toUpperCase()).filter(Boolean)
  } catch {
    return []
  }
}

/**
 * Firestore-backed watchlist, following useFirebasePortfolio.js's pattern: one-time
 * localStorage migration, live onSnapshot subscription so a change on one device reaches
 * every other signed-in device without a reload.
 *
 * Each item is { ticker, addedAt, dipPrice, goodBuyPrice, note, source }. Price targets are
 * optional and user-editable -- see src/lib/watchlistPriceTargets.js for the suggested
 * starting values this hook does not itself compute (that stays a pure function the caller
 * runs against published research, so this hook has no opinion on scoring).
 */
export function useWatchlist() {
  const { currentUser } = useAuth()
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [migrated, setMigrated] = useState(false)

  const migrateFromLocalStorage = async (userId) => {
    const key = migratedKey(userId)
    if (localStorage.getItem(key)) return
    const tickers = legacyTickers()
    if (tickers.length) {
      await Promise.allSettled(tickers.map((ticker) => setDoc(doc(db, 'watchlists', userId, 'items', ticker), {
        ticker, addedAt: new Date().toISOString(), dipPrice: null, goodBuyPrice: null, note: '',
        source: 'localStorage_migration',
      }, { merge: true })))
    }
    localStorage.setItem(key, 'true')
  }

  useEffect(() => {
    if (!currentUser) {
      setItems([])
      setLoading(false)
      return undefined
    }
    const userId = currentUser.uid
    setLoading(true)
    if (!migrated) migrateFromLocalStorage(userId).finally(() => setMigrated(true))
    const unsubscribe = onSnapshot(collection(db, 'watchlists', userId, 'items'), (snapshot) => {
      const loaded = []
      snapshot.forEach((snapshotDoc) => loaded.push({ ...snapshotDoc.data(), ticker: snapshotDoc.id }))
      loaded.sort((left, right) => String(right.addedAt || '').localeCompare(String(left.addedAt || '')))
      setItems(loaded)
      setLoading(false)
    }, (error) => {
      console.error('Watchlist subscription failed:', error)
      setLoading(false)
    })
    return unsubscribe
  }, [currentUser, migrated])

  const addTicker = async (ticker, targets = {}) => {
    if (!currentUser) return { success: false, error: 'Please sign in first' }
    const normalized = String(ticker || '').trim().toUpperCase()
    if (!normalized) return { success: false, error: 'No ticker provided' }
    try {
      await setDoc(doc(db, 'watchlists', currentUser.uid, 'items', normalized), {
        ticker: normalized, addedAt: new Date().toISOString(),
        dipPrice: targets.dipPrice ?? null, goodBuyPrice: targets.goodBuyPrice ?? null,
        note: targets.note || '', source: targets.source || 'manual',
      }, { merge: true })
      return { success: true }
    } catch (error) {
      console.error('Failed to add to watchlist:', error)
      return { success: false, error: error.message }
    }
  }

  const removeTicker = async (ticker) => {
    if (!currentUser) return { success: false, error: 'Please sign in first' }
    try {
      await deleteDoc(doc(db, 'watchlists', currentUser.uid, 'items', String(ticker).toUpperCase()))
      return { success: true }
    } catch (error) {
      console.error('Failed to remove from watchlist:', error)
      return { success: false, error: error.message }
    }
  }

  const updateTargets = async (ticker, updates) => {
    if (!currentUser) return { success: false, error: 'Please sign in first' }
    const normalized = String(ticker || '').trim().toUpperCase()
    try {
      await setDoc(doc(db, 'watchlists', currentUser.uid, 'items', normalized), {
        ...updates, updatedAt: new Date().toISOString(),
      }, { merge: true })
      return { success: true }
    } catch (error) {
      console.error('Failed to update watchlist targets:', error)
      return { success: false, error: error.message }
    }
  }

  const isWatched = (ticker) => items.some((item) => item.ticker === String(ticker || '').toUpperCase())

  return { items, loading, addTicker, removeTicker, updateTargets, isWatched }
}
