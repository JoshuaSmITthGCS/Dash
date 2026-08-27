/** An unlit channel bezel with its reason printed in the readout font — no spinner, no icon-only. */
export default function EmptyState({ reason }) {
  return (
    <div data-cockpit-bezel="true" role="alert" style={{ opacity: 0.5 }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-faint)' }}>
        CHANNEL UNLIT
      </div>
      <div style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>{reason}</div>
    </div>
  )
}
