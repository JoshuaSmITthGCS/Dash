import { useState, useEffect } from 'react'
import { useAuth } from './AuthContext'

const PORTFOLIO_KEY_PREFIX = 'valuesignal.portfolio.'

// Default positions for the main user (from screenshots)
const DEFAULT_POSITIONS = {
  'main-user': [
    { ticker: 'ACN', shares: 10, costBasis: 350.25, purchaseDate: '2026-06-15' },
    { ticker: 'ADBE', shares: 8, costBasis: 485.50, purchaseDate: '2026-06-10' },
    { ticker: 'BAC', shares: 50, costBasis: 38.75, purchaseDate: '2026-05-20' },
    { ticker: 'AGO', shares: 25, costBasis: 65.20, purchaseDate: '2026-06-01' },
    { ticker: 'COP', shares: 20, costBasis: 115.80, purchaseDate: '2026-05-15' },
    { ticker: 'OXY', shares: 30, costBasis: 58.90, purchaseDate: '2026-06-05' },
    { ticker: 'MSFT', shares: 15, costBasis: 420.30, purchaseDate: '2026-05-10' },
    { ticker: 'AMAT', shares: 12, costBasis: 185.40, purchaseDate: '2026-06-20' },
    { ticker: 'META', shares: 6, costBasis: 515.75, purchaseDate: '2026-05-25' },
    { ticker: 'QCOM', shares: 18, costBasis: 165.20, purchaseDate: '2026-06-08' },
    { ticker: 'DECK', shares: 5, costBasis: 850.00, purchaseDate: '2026-05-30' },
    { ticker: 'CI', shares: 8, costBasis: 325.60, purchaseDate: '2026-06-12' },
    { ticker: 'VOO', shares: 20, costBasis: 485.25, purchaseDate: '2026-05-05' },
    { ticker: 'MU', shares: 25, costBasis: 95.50, purchaseDate: '2026-06-18' },
    { ticker: 'NTNX', shares: 30, costBasis: 58.75, purchaseDate: '2026-06-25' },
    { ticker: 'BSX', shares: 35, costBasis: 72.30, purchaseDate: '2026-05-28' },
    { ticker: 'INTU', shares: 4, costBasis: 625.80, purchaseDate: '2026-06-02' },
    { ticker: 'SCHW', shares: 40, costBasis: 68.90, purchaseDate: '2026-05-12' },
    { ticker: 'EOG', shares: 22, costBasis: 128.40, purchaseDate: '2026-06-22' },
  ]
}

export function usePortfolio() {
  const { user } = useAuth()
  const [positions, setPositions] = useState([])
  const [hasLoadedDefaults, setHasLoadedDefaults] = useState(false)

  const getStorageKey = () => {
    return user ? `${PORTFOLIO_KEY_PREFIX}${user.id}` : `${PORTFOLIO_KEY_PREFIX}guest`
  }

  useEffect(() => {
    if (!user) {
      setPositions([])
      setHasLoadedDefaults(false)
      return
    }

    // Load portfolio from localStorage
    try {
      const key = getStorageKey()
      const stored = localStorage.getItem(key)

      if (stored) {
        setPositions(JSON.parse(stored))
        setHasLoadedDefaults(true)
      } else if (user.id.startsWith('user-') && !hasLoadedDefaults) {
        // First time login - preload default positions
        const defaults = DEFAULT_POSITIONS['main-user'] || []
        setPositions(defaults)
        localStorage.setItem(key, JSON.stringify(defaults))
        setHasLoadedDefaults(true)
      }
    } catch (e) {
      console.error('Failed to load portfolio:', e)
      setPositions([])
    }
  }, [user])

  const savePositions = (newPositions) => {
    setPositions(newPositions)
    if (user) {
      try {
        const key = getStorageKey()
        localStorage.setItem(key, JSON.stringify(newPositions))
      } catch (e) {
        console.error('Failed to save portfolio:', e)
      }
    }
  }

  const addPosition = (ticker, shares, costBasis, purchaseDate = new Date().toISOString().split('T')[0]) => {
    const newPosition = {
      ticker: ticker.toUpperCase(),
      shares: parseFloat(shares),
      costBasis: parseFloat(costBasis),
      purchaseDate,
      id: `${ticker}-${Date.now()}`
    }
    savePositions([...positions, newPosition])
  }

  const removePosition = (positionId) => {
    savePositions(positions.filter(p => p.id !== positionId))
  }

  const updatePosition = (positionId, updates) => {
    savePositions(positions.map(p => p.id === positionId ? { ...p, ...updates } : p))
  }

  const clearAll = () => {
    if (confirm('Are you sure you want to clear all positions?')) {
      savePositions([])
    }
  }

  const exportPortfolio = () => {
    const data = {
      exportDate: new Date().toISOString(),
      user: user?.name || 'Guest',
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

  const importPortfolio = (file) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result)
        if (data.positions && Array.isArray(data.positions)) {
          savePositions(data.positions)
        }
      } catch (error) {
        alert('Failed to import portfolio: Invalid file format')
      }
    }
    reader.readAsText(file)
  }

  return {
    positions,
    addPosition,
    removePosition,
    updatePosition,
    clearAll,
    exportPortfolio,
    importPortfolio
  }
}
