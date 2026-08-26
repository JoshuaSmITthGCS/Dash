/** A printed no-report line — same row grammar as every other row, not a different widget. */
export default function EmptyState({ reason }) {
  return (
    <div data-ticker-row="true" role="alert">
      <span>NO REPORT</span>
      <span style={{ color: 'var(--ink-faint)' }}>{reason}</span>
    </div>
  )
}
