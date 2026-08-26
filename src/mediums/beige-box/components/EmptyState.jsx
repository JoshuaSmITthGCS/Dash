/** A greyed-out disabled control, the reason surfaced beneath — the status-bar text lives here too, since this is the one place a screen composes a standalone empty region (DESIGN.md §10 empty/loading/error). */
export default function EmptyState({ reason }) {
  return (
    <div data-beige-bevel="true" data-beige-disabled="true" role="alert" style={{ padding: '10px 12px', minHeight: '48px' }}>
      <span style={{ fontSize: '13px' }}>Unavailable</span>
      <div style={{ fontSize: '11px' }}>{reason}</div>
    </div>
  )
}
