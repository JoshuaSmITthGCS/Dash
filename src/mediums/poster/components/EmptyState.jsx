/** An unprinted area (blank paper) with the reason set in masthead type — absence as literally unprinted. */
export default function EmptyState({ reason }) {
  return (
    <div role="alert" style={{ border: '2px dashed var(--rule-hairline)', padding: '12px 14px', background: 'transparent' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--ink-faint)' }}>UNPRINTED</div>
      <div style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>{reason}</div>
    </div>
  )
}
