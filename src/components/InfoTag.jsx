// Compact "what does this measure" affordance for a sort option, chart, or table column.
// Built on <details>/<summary> deliberately: it opens on tap on mobile and on click on
// desktop with zero extra JS and no hover-only CSS, which a touch screen could never reach.
export default function InfoTag({ label, children, align = 'left' }) {
  return (
    <details className={`info-tag info-tag-${align}`}>
      <summary aria-label={label ? `About: ${label}` : 'About this'}>
        <span aria-hidden="true">i</span>
      </summary>
      <div className="info-tag-panel" role="note">{children}</div>
    </details>
  )
}
