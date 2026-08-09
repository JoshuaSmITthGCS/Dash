/**
 * A layer with no effective score is rendered as unavailable, with the reason, and never as
 * a number. It previously rendered a fabricated 50 alongside "0% coverage" -- a score
 * presented as evidence that was identical for every company in the universe. See
 * research/audit/CURRENT_MODEL_AUDIT.md section 3.
 */
function UnavailableLayer({ title, description, reason }) {
  return (
    <section className="analysis-layer-card analysis-layer-unavailable">
      <div className="analysis-layer-heading">
        <div>
          <span className="kpi-label">{title}</span>
          <strong className="mono">—</strong>
        </div>
        <span className="chip">not measured</span>
      </div>
      <p>{description}</p>
      <small className="analysis-warning">
        {reason || 'This layer has no resolved inputs, so no score is published for it.'}
      </small>
    </section>
  )
}

function ScoreLayer({ title, layer, description }) {
  if (!layer) return null
  if (layer.effective_score == null) {
    return <UnavailableLayer title={title} description={description} reason={layer.unavailable_reason} />
  }
  const raw = layer.raw_score
  return (
    <section className="analysis-layer-card">
      <div className="analysis-layer-heading">
        <div>
          <span className="kpi-label">{title}</span>
          <strong className="mono">{Math.round(layer.effective_score)}</strong>
        </div>
        <span className="chip">{String(layer.classification).replace(/_/g, ' ')}</span>
      </div>
      <p>{description}</p>
      <dl className="analysis-quality-grid">
        <div><dt>Raw</dt><dd>{raw == null ? 'Unavailable' : Math.round(raw)}</dd></div>
        {/* Both numbers below are completeness measures. Neither is a statistical property
            of the signal, so neither is labelled "confidence" -- that word was doing work it
            had not earned. A real confidence metric, tested against realised prediction
            error, is Phase 8 work and does not exist yet. */}
        <div><dt>Data coverage</dt><dd>{Math.round(layer.coverage * 100)}%</dd></div>
        <div><dt>Evidence weight resolved</dt>
          <dd title="Share of this layer's intended evidence that actually resolved, discounted for provenance, staleness and provider disagreement. Not a probability of a price move.">
            {Math.round(layer.evidence_weight_resolved * 100)}%</dd></div>
      </dl>
      {layer.evidence_weight_resolved < 0.4 && (
        <small className="analysis-warning">Insufficient evidence: this layer cannot issue prescriptive company guidance.</small>
      )}
    </section>
  )
}

export default function AnalysisLayers({ analysis }) {
  if (!analysis) return null
  return (
    <div className="analysis-layers" aria-label="Independent research decision layers">
      <ScoreLayer
        title="Business thesis"
        layer={analysis.structural}
        description="Structural quality and valuation. Position stops do not change this result."
      />
      <ScoreLayer
        title="Earnings timeliness"
        layer={analysis.timeliness}
        description="Forward estimates, revisions, surprises, and guidance–separate from trailing growth."
      />
    </div>
  )
}
