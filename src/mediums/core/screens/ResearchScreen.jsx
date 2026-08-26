import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { RESEARCH_IDS } from './capabilityIds.js'

/**
 * Absorbs Picks, Search, and Watchlist behind `?q=` and `?view=picks|watchlist` (see
 * ROUTE-INVENTORY.md §2). This is the URL-addressability rule made concrete: `?q=` is read here
 * on mount, fixing the dead param Alerts has always produced but Search never consumed.
 *
 * Scope note (NOTES.md): Phase 2a ships the search-and-list slice that proves the pattern and
 * the `?q=` fix; the full ranking-model sort, allocation planner, and watchlist lens/sizing
 * controls port over per-medium in Phase 2b, each against CAPABILITY-LEDGER.md §2's full row set.
 */
export default function ResearchScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams, setSearchParams] = useSearchParams()
  const view = searchParams.get('view') || 'picks'
  const [query, setQuery] = useState(searchParams.get('q') || '')

  const { data: report, loading } = useData('report.json')

  const results = useMemo(() => {
    const rows = report?.research || []
    if (!query.trim()) return rows
    const needle = query.trim().toUpperCase()
    return rows.filter((row) => row.ticker?.toUpperCase().includes(needle) || row.name?.toUpperCase().includes(needle))
  }, [report, query])

  const onSearchChange = (event) => {
    const value = event.target.value
    setQuery(value)
    const next = new URLSearchParams(searchParams)
    if (value) next.set('q', value); else next.delete('q')
    setSearchParams(next, { replace: true })
  }

  if (loading) return <div role="status" aria-live="polite">Loading…</div>

  return (
    <div data-screen="research" data-view={view}>
      <Container {...cap(RESEARCH_IDS.searchInput)}>
        <input
          type="search"
          value={query}
          onChange={onSearchChange}
          aria-label="Search research"
          placeholder="Search ticker or company"
        />
      </Container>
      <Container {...cap(RESEARCH_IDS.resultCount)}>
        <span data-testid="result-count">{results.length} result{results.length === 1 ? '' : 's'}</span>
      </Container>
      {results.length === 0 && (
        <div {...cap(RESEARCH_IDS.empty)} role="status">No companies match those filters.</div>
      )}
      <ul data-testid="research-results">
        {results.slice(0, 25).map((row) => (
          <li key={row.ticker}>{row.ticker} — {row.name} — {row.score != null ? row.score.toFixed(1) : '–'}</li>
        ))}
      </ul>
    </div>
  )
}
