function ScoreLayer({ title, layer, description }) {
  if (!layer) return null
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
        <div><dt>Coverage</dt><dd>{Math.round(layer.coverage * 100)}%</dd></div>
        <div><dt>Confidence</dt><dd>{Math.round(layer.confidence * 100)}%</dd></div>
      </dl>
      {layer.confidence < 0.4 && (
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
