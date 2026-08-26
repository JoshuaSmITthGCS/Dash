/**
 * The attribution strip as a readout — Cockpit's must-include device, and this rebuild's
 * theme-independent first-viewport seed (see ROUTE-INVENTORY.md §3). Renders live counts only;
 * never hardcodes "17 of 24" / "9 of 64" / "17 days" — see DATA-INVENTORY.md's standing warning.
 */
export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div data-cockpit-bezel="true" data-testid="provenance-strip">
      <div style={{ display: 'flex', gap: '16px', fontSize: '12px', letterSpacing: '0.04em', fontVariantNumeric: 'tabular-nums' }}>
        <span>{ready ?? '–'} READY</span>
        <span style={{ color: breached ? 'var(--state-breach)' : 'inherit' }}>{breached ?? '–'} BREACHED</span>
        <span>{liveDays ?? '–'}D LIVE</span>
        <span>MODEL {modelVersion || '–'}</span>
      </div>
      {promotionText && <p style={{ fontSize: '11px', color: 'var(--ink-faint)', marginTop: '6px' }}>{promotionText}</p>}
    </div>
  )
}
