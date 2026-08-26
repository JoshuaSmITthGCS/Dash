export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-sc-legend="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '14px' }}>
        <span>{ready ?? '–'} established</span>
        <span style={{ color: breached ? 'var(--state-breach)' : 'inherit' }}>{breached ?? '–'} cross-haired</span>
        <span>epoch +{liveDays ?? '–'}d</span>
      </div>
      <p style={{ color: 'var(--ink-faint)', margin: '4px 0 0' }}>plate {modelVersion || '–'}</p>
      {promotionText && <p style={{ color: 'var(--ink-faint)', fontStyle: 'italic', margin: '2px 0 0' }}>{promotionText}</p>}
    </div>
  )
}
