import { useEffect, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'

const storageKey = (userId) => `valuesignal.portfolioQuotes.${userId}`

function readCachedQuotes(userId) {
  if (!userId) return { quotes: {}, fetchedAt: null }
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey(userId)) || '{}')
    return {
      quotes: parsed.quotes && typeof parsed.quotes === 'object' ? parsed.quotes : {},
      fetchedAt: parsed.fetchedAt || null,
    }
  } catch {
    return { quotes: {}, fetchedAt: null }
  }
}

export function usePortfolioQuotes(symbols) {
  const { currentUser } = useAuth()
  const [state, setState] = useState(() => ({
    ...readCachedQuotes(currentUser?.uid),
    refreshing: false,
    message: '',
    error: '',
  }))

  useEffect(() => {
    setState({
      ...readCachedQuotes(currentUser?.uid),
      refreshing: false,
      message: '',
      error: '',
    })
  }, [currentUser?.uid])

  const requestRefresh = async () => {
    if (!currentUser || state.refreshing) return
    const requested = [...new Set(symbols
      .map((symbol) => String(symbol || '').trim().toUpperCase())
      .filter(Boolean))]
    if (!requested.length) {
      setState((current) => ({ ...current, error: 'Add a position before refreshing prices.' }))
      return
    }

    setState((current) => ({ ...current, refreshing: true, message: '', error: '' }))
    try {
      const idToken = await currentUser.getIdToken()
      const response = await fetch('/.netlify/functions/portfolio-prices', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${idToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ symbols: requested }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.error || 'Portfolio prices could not be refreshed.')

      const next = {
        quotes: payload.quotes || {},
        fetchedAt: payload.fetchedAt,
        refreshing: false,
        message: payload.failed?.length
          ? `Updated ${payload.updated} of ${payload.requested} positions. ${payload.failed.map((item) => item.symbol).join(', ')} could not be refreshed.`
          : `Updated ${payload.updated} portfolio price${payload.updated === 1 ? '' : 's'}.`,
        error: '',
      }
      setState(next)
      try {
        localStorage.setItem(storageKey(currentUser.uid), JSON.stringify({
          quotes: next.quotes,
          fetchedAt: next.fetchedAt,
        }))
      } catch {
        // The in-memory quotes still work when browser storage is unavailable.
      }
    } catch (error) {
      setState((current) => ({
        ...current,
        refreshing: false,
        message: '',
        error: error.message,
      }))
    }
  }

  return { ...state, requestRefresh }
}
