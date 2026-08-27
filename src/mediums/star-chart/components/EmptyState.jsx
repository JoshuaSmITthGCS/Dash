/** A catalogued position with nothing plotted — the coordinate exists in the index but no mark appears, reason in the legend (DESIGN.md §7). */
export default function EmptyState({ reason }) {
  return (
    <div data-sc-plate="true" role="alert">
      <svg width="60" height="40" viewBox="0 0 60 40" aria-hidden="true">
        <line x1="30" x2="30" y1="0" y2="40" stroke="var(--graticule)" strokeWidth="0.5" />
        <line x1="0" x2="60" y1="20" y2="20" stroke="var(--graticule)" strokeWidth="0.5" />
      </svg>
      <p data-sc-legend="true" style={{ color: 'var(--ink-faint)' }}>catalogued, unplotted — {reason}</p>
    </div>
  )
}
