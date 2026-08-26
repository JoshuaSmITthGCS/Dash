/** No glow — loading is not breach. A dim, unlit tube row instead of a spinner. */
export default function Skeleton() {
  return (
    <div data-neon-panel="true" role="status" aria-live="polite" style={{ opacity: 0.5 }}>
      <div style={{ display: 'flex', gap: '2px' }} aria-hidden="true">
        {Array.from({ length: 6 }, (_, i) => <span key={i} style={{ width: '10px', height: '4px', background: 'var(--rule-hairline)', borderRadius: '2px' }} />)}
      </div>
      <span style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>WARMING UP</span>
    </div>
  )
}
