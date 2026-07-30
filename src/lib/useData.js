import { useCallback, useEffect, useRef, useState } from 'react'

// Loads a JSON file the pipeline committed into /public/data.
// Static fetch -> no backend. Returns { data, loading, error, reload }.
export function useData(file) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const mounted = useRef(false)

  const load = useCallback(async ({ initial = false } = {}) => {
    if (initial && mounted.current) {
      setState((current) => ({ ...current, loading: true, error: null }))
    }
    try {
      const separator = file.includes('?') ? '&' : '?'
      const response = await fetch(
        `${import.meta.env.BASE_URL}data/${file}${separator}v=${Date.now()}`,
        { cache: 'no-store' }
      )
      if (!response.ok) throw new Error(`${file}: ${response.status}`)
      const data = await response.json()
      if (mounted.current) setState({ data, loading: false, error: null })
      return data
    } catch (error) {
      if (mounted.current) {
        setState((current) => ({ data: current.data, loading: false, error }))
      }
      throw error
    }
  }, [file])

  useEffect(() => {
    mounted.current = true
    load({ initial: true }).catch(() => {})
    return () => { mounted.current = false }
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
