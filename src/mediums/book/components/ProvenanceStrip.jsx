export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-book-table="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
        <span>{ready ?? '–'} established</span>
        <span style={{ color: breached ? 'var(--ink-editorial)' : 'inherit' }}>{breached ?? '–'} breached</span>
        <span>{liveDays ?? '–'}d live</span>
        <span>ed. {modelVersion || '–'}</span>
      </div>
      {promotionText && <p style={{ fontSize: '12px', color: 'var(--ink-faint)', fontStyle: 'italic' }}>{promotionText}</p>}
    </div>
  )
}
