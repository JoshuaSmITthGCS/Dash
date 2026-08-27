/**
 * The "DO NOT ERASE" corner — model version, config hash, as-of, plus the four-state summary.
 * Uses the `[data-chalk-do-not-erase]` dashed-box treatment declared in tokens.css.
 */
export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-chalk-box="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', fontVariantNumeric: 'tabular-nums' }}>
        <span>{ready ?? '–'} ready</span>
        <span style={{ color: breached ? 'var(--chalk-alert)' : 'inherit' }}>{breached ?? '–'} breached</span>
        <span>{liveDays ?? '–'}d live</span>
      </div>
      <div data-chalk-do-not-erase="true" style={{ marginTop: '8px' }}>
        DO NOT ERASE — model {modelVersion || '–'}
      </div>
      {promotionText && <p style={{ fontSize: '11px', color: 'var(--ink-faint)', marginTop: '6px' }}>{promotionText}</p>}
    </div>
  )
}
