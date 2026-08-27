/** A not-yet-specified dimension — a dashed leader line ending in "?" rather than a number (DESIGN.md §6). */
export default function EmptyState({ reason }) {
  return (
    <div data-bp-sheet="true" role="alert" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <span aria-hidden="true" style={{ flex: 1, borderBottom: '1px dashed var(--ink-faint)' }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '18px', color: 'var(--ink-faint)' }}>?</span>
      </div>
      <p style={{ fontSize: '10px', color: 'var(--ink-faint)' }}>{reason}</p>
    </div>
  )
}
