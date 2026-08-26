/** A dead tube with its reason — never glowed (glow means breach only, not absence). */
export default function EmptyState({ reason }) {
  return (
    <div data-neon-panel="true" role="alert" style={{ opacity: 0.5 }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-faint)' }}>DEAD TUBE</div>
      <div style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>{reason}</div>
    </div>
  )
}
