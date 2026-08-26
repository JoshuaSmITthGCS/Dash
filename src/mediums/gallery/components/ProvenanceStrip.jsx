export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-gallery-frame="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
        <span>{ready ?? '–'} established</span>
        <span style={{ color: breached ? 'var(--state-breach)' : 'inherit' }}>{breached ?? '–'} under review</span>
        <span>{liveDays ?? '–'} days recorded</span>
      </div>
      <div data-gallery-plaque="true">model {modelVersion || '–'}</div>
      {promotionText && <p style={{ fontSize: '12px', color: 'var(--ink-faint)', marginTop: '6px' }}>{promotionText}</p>}
    </div>
  )
}
