/**
 * The title block — model version, config hash, as-of, and revision state, drafting convention
 * (bottom-right corner in layout, DESIGN.md §6). The revision state explicitly reads
 * "REV — UNPROMOTED" rather than implying a false "Rev. A, final" — the medium's own named risk
 * control against over-precision.
 */
export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-bp-titleblock="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '14px' }}>
        <span>{ready ?? '–'} EST.</span>
        <span style={{ color: breached ? 'var(--state-breach)' : 'inherit' }}>{breached ?? '–'} O.O.T.</span>
        <span>{liveDays ?? '–'}D LIVE</span>
      </div>
      <div>REV — {promotionText ? 'UNPROMOTED' : '—'}</div>
      <div style={{ color: 'var(--ink-faint)' }}>{modelVersion || '–'}</div>
      {promotionText && <p style={{ fontSize: '9px', color: 'var(--ink-faint)' }}>{promotionText}</p>}
    </div>
  )
}
