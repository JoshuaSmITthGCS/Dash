import { useCallback, useEffect, useRef, useState } from 'react'
import { datasetFor, migrate } from './schemaMigrations'

// Local cache of the last successfully fetched payload for each data file, so a page
// reload while iterating on new metrics (or running the app with no network at all for
// pack testing) doesn't require a fresh round trip to re-see the last refresh. Best
// effort only: private browsing and quota limits (a handful of the larger ETF snapshots
// won't fit) both fail silently and just fall back to a network fetch.
const CACHE_PREFIX = 'dash:last-refresh:'
const PERSISTENT_CACHE = 'dash-data-cache-v1'
const memoryPayloads = new Map()
const inFlightRequests = new Map()

function cacheKey(file) {
  return `${CACHE_PREFIX}${file}`
}

function cacheRequestKey(file) {
  return `/__cached-data/${encodeURIComponent(file)}`
}

function readCachedPayload(file) {
  if (!file) return null
  if (memoryPayloads.has(file)) return memoryPayloads.get(file)
  try {
    const raw = localStorage.getItem(cacheKey(file))
    const cached = raw ? JSON.parse(raw) : null
    if (cached) memoryPayloads.set(file, cached)
    return cached
  } catch {
    return null
  }
}

// The multi-megabyte research payloads (report/advisor) blow past the localStorage quota,
// so they persist in the Cache API instead, which budgets in the hundreds of MB. Reads are
// async, so this layer backs the synchronous localStorage path rather than replacing it.
async function readPersistentPayload(file) {
  if (!file || typeof caches === 'undefined') return null
  try {
    const cache = await caches.open(PERSISTENT_CACHE)
    const response = await cache.match(cacheRequestKey(file))
    if (!response) return null
    const payload = await response.json()
    memoryPayloads.set(file, payload)
    return payload
  } catch {
    return null
  }
}

async function writePersistentPayload(file, serialized) {
  if (typeof caches === 'undefined') return
  try {
    const cache = await caches.open(PERSISTENT_CACHE)
    await cache.put(cacheRequestKey(file), new Response(serialized, {
      headers: { 'Content-Type': 'application/json' },
    }))
  } catch {
    // Quota exceeded or storage unavailable - caching is a nice-to-have, not load-bearing.
  }
}

function writeCachedPayload(file, data) {
  const payload = { data, cachedAt: Date.now() }
  memoryPayloads.set(file, payload)
  let serialized
  try {
    serialized = JSON.stringify(payload)
  } catch {
    return
  }
  try {
    localStorage.setItem(cacheKey(file), serialized)
  } catch {
    writePersistentPayload(file, serialized)
  }
}

// Drops one cached file, or every file this hook has cached, so a genuinely fresh pull
// can be forced without clearing all of localStorage (which would also drop the
// watchlist and portfolio settings other features keep there).
export function clearCachedData(file) {
  try {
    if (file) {
      localStorage.removeItem(cacheKey(file))
      memoryPayloads.delete(file)
      inFlightRequests.delete(file)
      if (typeof caches !== 'undefined') {
        caches.open(PERSISTENT_CACHE).then((cache) => cache.delete(cacheRequestKey(file))).catch(() => {})
      }
      return
    }
    Object.keys(localStorage)
      .filter((key) => key.startsWith(CACHE_PREFIX))
      .forEach((key) => localStorage.removeItem(key))
    memoryPayloads.clear()
    inFlightRequests.clear()
    if (typeof caches !== 'undefined') caches.delete(PERSISTENT_CACHE).catch(() => {})
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
      : { data: null, loading: Boolean(file), error: null, fromCache: false, cachedAt: null }
  })
  const mounted = useRef(false)
  const requestId = useRef(0)

  const load = useCallback(async ({ initial = false } = {}) => {
    const activeRequest = ++requestId.current
    if (!file) {
      if (mounted.current) setState({ data: null, loading: false, error: null, fromCache: false, cachedAt: null })
      return null
    }
    // A cached copy is already on screen, so an initial mount revalidates quietly in the
    // background rather than showing a spinner over data the user can already see.
    if (initial && mounted.current && !hadCache.current) {
      setState((current) => ({ ...current, loading: true, error: null }))
    }
    try {
      let request = inFlightRequests.get(file)
      if (!request) {
        request = (async () => {
          // 'no-cache' revalidates against the server's ETag on every request, so a fresh
          // pipeline commit always comes through - but an unchanged file answers 304 and is
          // served from the browser's disk cache instead of re-downloading tens of MB.
          const response = await fetch(`${import.meta.env.BASE_URL}data/${file}`, { cache: 'no-cache' })
          if (!response.ok) throw new Error(`${file}: ${response.status}`)
          const raw = await response.json()
          const dataset = datasetFor(file)
          const data = dataset ? migrate(dataset, raw) : raw
          writeCachedPayload(file, data)
          return data
        })().finally(() => inFlightRequests.delete(file))
        inFlightRequests.set(file, request)
      }
      const data = await request
      const cachedAt = memoryPayloads.get(file)?.cachedAt || Date.now()
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
      : { data: null, loading: Boolean(file), error: null, fromCache: false, cachedAt: null })
    let active = true
    if (!cached && file) {
      // The big payloads live in the async Cache API layer. Paint from that copy the moment
      // it reads back - unless the network revalidation has already delivered fresh data.
      readPersistentPayload(file).then((payload) => {
        if (!active || !payload || !mounted.current) return
        hadCache.current = true
        setState((current) => (current.data
          ? current
          : { ...current, data: payload.data, loading: false, fromCache: true, cachedAt: payload.cachedAt }))
      }).catch(() => {})
    }
    load({ initial: true }).catch(() => {})
    return () => { active = false; requestId.current += 1; mounted.current = false }
  }, [load])

  return { ...state, reload: load }
}

export const fmtPct = (v) =>
  v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

export const fmtCap = (v) => {
  if (!v) return '–'
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`
  return `$${v}`
}

export const tierClass = (label = '') =>
  label.toLowerCase().replace(/\s+/g, '')

export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '–'

export function formatElapsed(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`
}
