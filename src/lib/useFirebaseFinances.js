import { useState, useEffect } from 'react'
import { collection, doc, getDoc, getDocs, setDoc, deleteDoc, updateDoc, increment } from 'firebase/firestore'
import { db } from './firebase'
import { useAuth } from './FirebaseAuthContext'

const DEFAULT_SETTINGS = {
  currentAge: 30,
  retireAge: 65,
  annualReturnPct: 7,
  inflationPct: 2.5,
  monthlyContribution: 0,
  currentSavings: 0,
}

export function useFirebaseFinances() {
  const { currentUser } = useAuth()
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [budgetItems, setBudgetItems] = useState([])
  const [pools, setPools] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const init = async () => {
      if (!currentUser) {
        setSettings(DEFAULT_SETTINGS)
        setBudgetItems([])
        setPools([])
        setLoading(false)
        return
      }

      setLoading(true)
      try {
        const [settingsSnap, budgetSnap, poolsSnap] = await Promise.all([
          getDoc(doc(db, 'finances', currentUser.uid)),
          getDocs(collection(db, 'finances', currentUser.uid, 'budgetItems')),
          getDocs(collection(db, 'finances', currentUser.uid, 'pools')),
        ])
        setSettings(settingsSnap.exists() ? { ...DEFAULT_SETTINGS, ...settingsSnap.data() } : DEFAULT_SETTINGS)
        setBudgetItems(budgetSnap.docs.map((d) => ({ id: d.id, ...d.data() })))
        setPools(poolsSnap.docs.map((d) => ({ id: d.id, ...d.data() })))
      } catch (error) {
        console.error('Failed to load finances:', error)
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [currentUser])

  const updateSettings = async (partial) => {
    if (!currentUser) return
    const next = { ...settings, ...partial }
    setSettings(next)
    try {
      await setDoc(doc(db, 'finances', currentUser.uid), next, { merge: true })
    } catch (error) {
      console.error('Failed to save finance settings:', error)
    }
  }

  const addBudgetItem = async ({ name, amount, type }) => {
    if (!currentUser) return
    const id = `${type}-${Date.now()}`
    const record = { id, name, amount: parseFloat(amount) || 0, type }
    try {
      await setDoc(doc(db, 'finances', currentUser.uid, 'budgetItems', id), record)
      setBudgetItems((prev) => [...prev, record])
    } catch (error) {
      console.error('Failed to add budget item:', error)
    }
  }

  const removeBudgetItem = async (id) => {
    if (!currentUser) return
    try {
      await deleteDoc(doc(db, 'finances', currentUser.uid, 'budgetItems', id))
      setBudgetItems((prev) => prev.filter((item) => item.id !== id))
    } catch (error) {
      console.error('Failed to remove budget item:', error)
    }
  }

  const addPool = async ({ name, percent }) => {
    if (!currentUser) return
    const id = `pool-${Date.now()}`
    const record = { id, name, percent: parseFloat(percent) || 0, balance: 0 }
    try {
      await setDoc(doc(db, 'finances', currentUser.uid, 'pools', id), record)
      setPools((prev) => [...prev, record])
    } catch (error) {
      console.error('Failed to add pool:', error)
    }
  }

  const removePool = async (id) => {
    if (!currentUser) return
    try {
      await deleteDoc(doc(db, 'finances', currentUser.uid, 'pools', id))
      setPools((prev) => prev.filter((pool) => pool.id !== id))
    } catch (error) {
      console.error('Failed to remove pool:', error)
    }
  }

  // Applies a computed split (from financeSplit.splitAmount) to each pool's running balance.
  const depositToPools = async (shares) => {
    if (!currentUser || !shares.length) return
    try {
      await Promise.all(shares.map(({ id, share }) =>
        updateDoc(doc(db, 'finances', currentUser.uid, 'pools', id), { balance: increment(share) })
      ))
      setPools((prev) => prev.map((pool) => {
        const match = shares.find((share) => share.id === pool.id)
        return match ? { ...pool, balance: (pool.balance || 0) + match.share } : pool
      }))
    } catch (error) {
      console.error('Failed to deposit into pools:', error)
    }
  }

  return {
    settings,
    budgetItems,
    pools,
    loading,
    updateSettings,
    addBudgetItem,
    removeBudgetItem,
    addPool,
    removePool,
    depositToPools,
  }
}
