/** Cockpit's own loading state — a dimmed bezel with an in-progress sweep arc, never a generic spinner. */
export default function Skeleton() {
  return (
    <div data-cockpit-bezel="true" role="status" aria-live="polite" style={{ opacity: 0.6 }}>
      <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
        <circle cx="14" cy="14" r="11" fill="none" stroke="var(--rule-hairline)" strokeWidth="2" />
        <path d="M14 3 A11 11 0 0 1 25 14" fill="none" stroke="var(--state-established)" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span style={{ fontSize: '11px', color: 'var(--ink-faint)', marginLeft: '8px' }}>ACQUIRING</span>
    </div>
  )
}
