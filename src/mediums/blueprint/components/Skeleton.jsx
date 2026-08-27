/** No transitions in this medium — a faint construction-weight placeholder line. */
export default function Skeleton() {
  return (
    <div data-bp-sheet="true" role="status" aria-live="polite" style={{ opacity: 0.5 }}>
      <span aria-hidden="true" style={{ display: 'block', borderBottom: '1px dashed var(--grid-construction)', width: '60%' }} />
      <p style={{ fontSize: '10px', color: 'var(--ink-faint)' }}>DRAFTING…</p>
    </div>
  )
}
