/** A blank hand-drawn box with a "?" and the reason beneath — DESIGN.md §9 empty/loading/error. */
export default function EmptyState({ reason }) {
  return (
    <div data-chalk-box="true" role="alert" style={{ minHeight: '80px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
      <div style={{ fontSize: '22px', color: 'var(--ink-faint)' }}>?</div>
      <div style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>{reason}</div>
    </div>
  )
}
