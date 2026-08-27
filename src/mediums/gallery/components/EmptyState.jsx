/** An empty frame with a placard giving the reason — the museum "under conservation" device. */
export default function EmptyState({ reason }) {
  return (
    <div data-gallery-frame="true" role="alert" style={{ minHeight: '80px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', color: 'var(--ink-faint)' }}>Not currently on view</div>
      <div data-gallery-plaque="true">{reason}</div>
    </div>
  )
}
