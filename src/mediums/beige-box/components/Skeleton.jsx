/** No transitions in this medium — a static bevelled placeholder, not an animated shimmer. */
export default function Skeleton() {
  return (
    <div data-beige-bevel="true" role="status" aria-live="polite" style={{ opacity: 0.6, minHeight: '40px', padding: '8px 10px' }}>
      <span style={{ fontSize: '11px' }}>Loading…</span>
    </div>
  )
}
