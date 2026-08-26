/** No animated wipe — DESIGN.md §9 transitions: none. A faint hand-drawn box, unfinished. */
export default function Skeleton() {
  return (
    <div data-chalk-box="true" role="status" aria-live="polite" style={{ opacity: 0.35, minHeight: '48px' }}>
      <span style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>chalking…</span>
    </div>
  )
}
