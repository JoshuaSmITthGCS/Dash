export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-ticker-row="true" data-testid="provenance-strip" style={{ flexWrap: 'wrap' }}>
      <span>{ready ?? '–'} RDY</span>
      <span style={{ color: breached ? 'var(--state-breach)' : 'inherit' }}>{breached ?? '–'} BRCH</span>
      <span>{liveDays ?? '–'}D</span>
      <span>MDL {modelVersion || '–'}</span>
      {promotionText && <span style={{ flexBasis: '100%', fontSize: '11px', color: 'var(--ink-faint)' }}>{promotionText}</span>}
    </div>
  )
}
