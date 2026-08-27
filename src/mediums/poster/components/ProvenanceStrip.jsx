export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-poster-panel="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', fontVariantNumeric: 'tabular-nums' }}>
        <span>{ready ?? '–'} READY</span>
        <span style={{ color: breached ? 'var(--ink-spot-1)' : 'inherit' }}>{breached ?? '–'} BREACHED</span>
        <span>{liveDays ?? '–'}D LIVE</span>
        <span>MODEL {modelVersion || '–'}</span>
      </div>
      {promotionText && <p style={{ fontSize: '11px', color: 'var(--ink-faint)', marginTop: '6px' }}>{promotionText}</p>}
    </div>
  )
}
