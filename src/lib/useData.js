import { useEffect, useState } from 'react'

// Loads a JSON file the pipeline committed into /public/data.
// Static fetch -> no backend. Returns { data, loading, error }.
export function useData(file) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  useEffect(() => {
    let alive = true
    fetch(`${import.meta.env.BASE_URL}data/${file}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${file}: ${r.status}`)
        return r.json()
      })
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((error) => alive && setState({ data: null, loading: false, error }))
    return () => { alive = false }
  }, [file])
  return state
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
