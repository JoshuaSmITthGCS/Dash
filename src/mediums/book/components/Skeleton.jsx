/** Page turns are instant — no animated placeholder, a plain bracketed note. */
export default function Skeleton() {
  return (
    <p role="status" aria-live="polite" data-book-table="true" style={{ color: 'var(--ink-faint)' }}>[setting…]</p>
  )
}
