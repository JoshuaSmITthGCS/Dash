import { useEffect, useRef, useState } from 'react'
import { useAuth } from './FirebaseAuthContext'
import { msUntilNextBoundary } from './nightlyRefresh'

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

  // Refresh immediately whenever the portfolio is opened or the user signs in – reloading
  // the tab or logging back in shouldn't show stale cached prices until 9pm rolls around –
  // and then once a day at 9pm local time – after Nasdaq/NYSE after-hours trading has wound
  // down – for as long as the tab stays open. See src/lib/nightlyRefresh.js for why 9pm.
  // requestRefresh is read through a ref so the recursive setTimeout chain always calls the
  // current closure, not whatever it closed over the one time the effect ran.
  const requestRefreshRef = useRef(requestRefresh)
  useEffect(() => { requestRefreshRef.current = requestRefresh })

  const tickerKey = [...new Set(symbols.map((symbol) => String(symbol || '').trim().toUpperCase()).filter(Boolean))]
    .sort().join(',')

  useEffect(() => {
    if (!currentUser || !tickerKey) return undefined
    let timer
    const scheduleNext = () => {
      timer = setTimeout(() => {
        requestRefreshRef.current()
        scheduleNext()
      }, msUntilNextBoundary())
    }
    requestRefreshRef.current()
    scheduleNext()
    return () => clearTimeout(timer)
  }, [currentUser, tickerKey])

  return { ...state, requestRefresh }
}
