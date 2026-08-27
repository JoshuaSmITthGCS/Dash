export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-column-rule="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
        <span>{ready ?? '–'} established</span>
        <span style={{ color: breached ? 'var(--accent-standfirst)' : 'inherit' }}>{breached ?? '–'} breached</span>
        <span>{liveDays ?? '–'} days live</span>
      </div>
      <p style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>Model {modelVersion || '–'}. Corrections run here.</p>
      {promotionText && <p style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{promotionText}</p>}
    </div>
  )
}
