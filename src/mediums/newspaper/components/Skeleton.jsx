/** No transitions in this medium — a static wire-service placeholder line. */
export default function Skeleton() {
  return (
    <p role="status" aria-live="polite" data-column-rule="true" style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ink-faint)' }}>
      DEVELOPING —
    </p>
  )
}
