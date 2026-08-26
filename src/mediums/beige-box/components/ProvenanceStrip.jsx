export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-beige-window="true" data-testid="provenance-strip">
      <div data-beige-titlebar="true"><span>System Properties</span></div>
      <div data-beige-body="true">
        <div style={{ display: 'flex', gap: '16px', fontSize: '12px', fontVariantNumeric: 'tabular-nums' }}>
          <span>{ready ?? '–'} ready</span>
          <span style={{ color: breached ? 'var(--state-breach)' : 'inherit' }}>{breached ?? '–'} breached</span>
          <span>{liveDays ?? '–'}d live</span>
          <span>build {modelVersion || '–'}</span>
        </div>
        {promotionText && <p style={{ fontSize: '11px', color: 'var(--ink-faint)', marginTop: '6px' }}>{promotionText}</p>}
      </div>
    </div>
  )
}
