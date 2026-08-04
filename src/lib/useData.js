import { useCallback, useEffect, useRef, useState } from 'react'
import { datasetFor, migrate } from './schemaMigrations'

// Local cache of the last successfully fetched payload for each data file, so a page
// reload while iterating on new metrics (or running the app with no network at all for
// pack testing) doesn't require a fresh round trip to re-see the last refresh. Best
// effort only: private browsing and quota limits (a handful of the larger ETF snapshots
// won't fit) both fail silently and just fall back to a network fetch.
const CACHE_PREFIX = 'dash:last-refresh:'

function cacheKey(file) {
  return `${CACHE_PREFIX}${file}`
}

function readCachedPayload(file) {
  try {
    const raw = localStorage.getItem(cacheKey(file))
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function writeCachedPayload(file, data) {
  try {
    localStorage.setItem(cacheKey(file), JSON.stringify({ data, cachedAt: Date.now() }))
  } catch {
    // Quota exceeded or storage unavailable - caching is a nice-to-have, not load-bearing.
  }
}

// Drops one cached file, or every file this hook has cached, so a genuinely fresh pull
// can be forced without clearing all of localStorage (which would also drop the
// watchlist and portfolio settings other features keep there).
export function clearCachedData(file) {
  try {
    if (file) {
      localStorage.removeItem(cacheKey(file))
      return
    }
    Object.keys(localStorage)
      .filter((key) => key.startsWith(CACHE_PREFIX))
      .forEach((key) => localStorage.removeItem(key))
  } catch {
    // ignore
  }
}

// Loads a JSON file the pipeline committed into /public/data.
// Static fetch -> no backend. Returns { data, loading, error, fromCache, cachedAt, reload }.
//
// Payloads are migrated to the version this build expects on the way in, so a freshly
// deployed site keeps working against the last committed snapshot until the next pipeline
// run replaces it.
export function useData(file) {
  const hadCache = useRef(false)
  const [state, setState] = useState(() => {
    const cached = readCachedPayload(file)
    hadCache.current = Boolean(cached)
    return cached
      ? { data: cached.data, loading: false, error: null, fromCache: true, cachedAt: cached.cachedAt }
      : { data: null, loading: true, error: null, fromCache: false, cachedAt: null }
  })
  const mounted = useRef(false)
  const requestId = useRef(0)

  const load = useCallback(async ({ initial = false } = {}) => {
    const activeRequest = ++requestId.current
    // A cached copy is already on screen, so an initial mount revalidates quietly in the
    // background rather than showing a spinner over data the user can already see.
    if (initial && mounted.current && !hadCache.current) {
      setState((current) => ({ ...current, loading: true, error: null }))
    }
    try {
      const separator = file.includes('?') ? '&' : '?'
      const response = await fetch(
        `${import.meta.env.BASE_URL}data/${file}${separator}v=${Date.now()}`,
        { cache: 'no-store' }
      )
      if (!response.ok) throw new Error(`${file}: ${response.status}`)
      const raw = await response.json()
      const dataset = datasetFor(file)
      const data = dataset ? migrate(dataset, raw) : raw
      const cachedAt = Date.now()
      writeCachedPayload(file, data)
      if (mounted.current && activeRequest === requestId.current) setState({ data, loading: false, error: null, fromCache: false, cachedAt })
      return data
    } catch (error) {
      if (mounted.current && activeRequest === requestId.current) {
        setState((current) => ({ ...current, loading: false, error }))
      }
      throw error
    }
  }, [file])

  useEffect(() => {
    mounted.current = true
    const cached = readCachedPayload(file)
    hadCache.current = Boolean(cached)
    setState(cached
      ? { data: cached.data, loading: false, error: null, fromCache: true, cachedAt: cached.cachedAt }
      : { data: null, loading: true, error: null, fromCache: false, cachedAt: null })
    load({ initial: true }).catch(() => {})
    return () => { requestId.current += 1; mounted.current = false }
  }, [load])

  return { ...state, reload: load }
}

export const fmtPct = (v) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

export const fmtCap = (v) => {
  if (!v) return '—'
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`
  return `$${v}`
}

export const tierClass = (label = '') =>
  label.toLowerCase().replace(/\s+/g, '')

export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'

export function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`
}
