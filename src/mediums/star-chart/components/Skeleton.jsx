/** No transitions in this medium — a faint unresolved graticule cell. */
export default function Skeleton() {
  return (
    <div data-sc-plate="true" role="status" aria-live="polite" style={{ opacity: 0.5 }}>
      <p style={{ color: 'var(--ink-faint)', fontSize: '11px' }}>exposing…</p>
    </div>
  )
}
