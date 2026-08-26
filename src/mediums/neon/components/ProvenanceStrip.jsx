/** The evidence strip, rendered as a title-card-style marquee line. Never glowed — glow means breach only. */
export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-neon-panel="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', fontVariantNumeric: 'tabular-nums', color: 'var(--brand-cyan)' }}>
        <span>{ready ?? '–'} READY</span>
        <span style={{ color: breached ? 'var(--brand-magenta)' : 'inherit' }}>{breached ?? '–'} BREACHED</span>
        <span>{liveDays ?? '–'}D LIVE</span>
        <span>MODEL {modelVersion || '–'}</span>
      </div>
      {promotionText && <p style={{ fontSize: '11px', color: 'var(--ink-faint)', marginTop: '6px' }}>{promotionText}</p>}
    </div>
  )
}
