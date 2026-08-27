/**
 * Prop-driven, unlike the existing `ModelVersionFooter`/`DataStatus` (which fetch their own
 * `report.json`/`status.json`) — every other medium's `ProvenanceStrip` takes the same
 * `{ready, breached, liveDays, modelVersion, promotionText}` shape from its screen, so Classic's
 * follows suit rather than double-fetching. Reuses the existing `.model-version-footer` class
 * for visual continuity (DESIGN.md §12 existing token set).
 */
export default function ProvenanceStrip({ ready, breached, liveDays, modelVersion, promotionText }) {
  return (
    <div className="card card-pad" data-testid="provenance-strip">
      <div className="data-status-main">
        <span>{ready ?? '–'} ready</span>
        <span className={breached ? 'tone-breached' : undefined}>{breached ?? '–'} breached</span>
        <span>{liveDays ?? '–'}d live</span>
      </div>
      <footer className="model-version-footer">Model {modelVersion || 'unknown'}</footer>
      {promotionText && <p className="signal-metric-state">{promotionText}</p>}
    </div>
  )
}
