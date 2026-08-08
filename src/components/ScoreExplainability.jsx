import { useState } from 'react'
import modelSettings from '../../pipeline/config/settings.json'
import InfoTag from './InfoTag.jsx'

const config = modelSettings.explainability

const signedPoints = (value) => `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}`

function rawValue(metric) {
  if (metric.raw_value == null) return 'unavailable'
  if (metric.format === 'percent') return `${(metric.raw_value * 100).toFixed(1)}%`
  if (metric.format === 'multiple') return `${Number(metric.raw_value).toFixed(1)}x`
  return Number(metric.raw_value).toFixed(2)
}

function ordinal(value) {
  const rounded = Math.round(value)
  const remainder = rounded % 100
  if (remainder >= 11 && remainder <= 13) return `${rounded}th`
  return `${rounded}${{ 1: 'st', 2: 'nd', 3: 'rd' }[rounded % 10] || 'th'}`
}

export function FactorBars({ bars = {} }) {
  if (!Object.keys(bars).length) return null
  return <section className="factor-bar-summary" aria-label="Research factor summary">
    {Object.entries(bars).map(([key, value]) => <div key={key}>
      <span>{key}</span>
      <i aria-hidden="true"><em style={{ width: `${value ?? 0}%` }} /></i>
      <strong>{value == null ? 'N/A' : Math.round(value)}</strong>
    </div>)}
  </section>
}

function Waterfall({ attribution }) {
  if (!attribution) return <p>Attribution is unavailable in this snapshot.</p>
  const lines = [
    ...attribution.evidence,
    { key: 'confidence', label: 'confidence shrinkage', points: attribution.confidence_shrinkage_points },
    ...attribution.modifiers,
  ]
  const visible = lines.filter((line) => line.key !== 'score_rounding' || Math.abs(line.points) >= 0.01)
  const largest = [...visible].sort((left, right) => Math.abs(right.points) - Math.abs(left.points)).slice(0, 3)
  const scale = Math.max(...visible.map((line) => Math.abs(line.points)), 1)
  return <div className="score-waterfall">
    <div className="attribution-callouts">{largest.map((line) => <span className={line.points >= 0 ? 'positive' : 'negative'} key={line.key}><small>{line.label}</small><strong>{signedPoints(line.points)} pts</strong></span>)}</div>
    <div className="waterfall-total"><span>Start from neutral</span><strong>{attribution.base.toFixed(1)}</strong></div>
    {visible.map((line) => <div className="waterfall-row" key={line.key}>
      <span>{line.label}</span>
      <i aria-hidden="true"><em className={line.points >= 0 ? 'positive' : 'negative'} style={{ width: `${Math.abs(line.points) / scale * 50}%` }} /></i>
      <strong className={line.points >= 0 ? 'positive' : 'negative'}>{signedPoints(line.points)}</strong>
    </div>)}
    <div className="waterfall-total"><span>Final score</span><strong>{attribution.final_score.toFixed(1)}</strong></div>
  </div>
}

function MetricExplanation({ metric, sector }) {
  const peer = metric.sector_percentile == null
    ? 'peer percentile is accumulating'
    : `${ordinal(metric.sector_percentile)} percentile in ${metric.normalization_scope === 'sector' ? sector : 'the full universe'}`
  let peerMeaning = ''
  if (metric.sector_percentile != null && metric.direction === 'lower_is_better') {
    peerMeaning = metric.sector_percentile >= 50 ? ', so expensive relative to peers' : ', so cheap relative to peers'
  }
  const own = !metric.own_history_status
    ? 'own-history comparison does not apply'
    : metric.own_history_percentile == null
      ? `${metric.own_history_observations || 0} own-history observations accumulated`
      : `${ordinal(metric.own_history_percentile)} percentile versus its own ${metric.own_history_years}-year history`
  return <li>
    <strong>{metric.label}</strong> {rawValue(metric)}, {peer}{peerMeaning}, {own}, worth <b className={metric.final_point_contribution >= 0 ? 'positive' : 'negative'}>{signedPoints(metric.final_point_contribution)} points</b>.
  </li>
}

function ScoreHistory({ history }) {
  if (!history || history.status !== 'available') return <div className="unavailable-panel"><strong>Score history is accumulating</strong><p>{history?.stored_months || 0} of {history?.required_months || 6} stored months. A chart appears after enough distinct monthly snapshots exist.</p></div>
  const points = history.points.filter((point) => Number.isFinite(point.champion_score))
  if (points.length < 2) return null
  const width = config.history_chart_width
  const height = config.history_chart_height
  const plotted = points.map((point, index) => ({
    ...point,
    x: points.length === 1 ? 0 : index / (points.length - 1) * width,
    y: height - point.champion_score / config.score_scale_maximum * height,
  }))
  const changes = plotted.filter((point, index) => index > 0 && point.champion_stance !== plotted[index - 1].champion_stance)
  const driver = history.largest_category_driver
  return <div className="score-history">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Research score history">
      <polyline points={plotted.map((point) => `${point.x},${point.y}`).join(' ')} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      {changes.map((point) => <circle key={point.refresh_id} cx={point.x} cy={point.y} r="3" />)}
    </svg>
    <p>Score moved from {points[0].champion_score.toFixed(0)} to {points.at(-1).champion_score.toFixed(0)}{driver ? `, driven mainly by ${driver.category.replace(/_/g, ' ')}` : ''}.</p>
  </div>
}

export default function ScoreExplainability({ stock }) {
  const explainability = stock.explainability
  const [variant, setVariant] = useState(explainability?.active_variant || 'champion')
  if (!explainability) return null
  const attribution = explainability.attribution?.[variant]
  const metrics = explainability.metrics?.[variant] || []
  return <div className="score-explainability">
    <section>
      <header className="section-heading"><div><span className="eyebrow">Exact reconciliation</span><h3>Why the score is {attribution?.final_score?.toFixed(1) ?? 'unavailable'}
        <InfoTag label="Score waterfall">
          <strong>Reading the waterfall</strong>
          <p>Starts from a neutral baseline and adds/subtracts each evidence line and modifier
            (confidence shrinkage, insider activity, sector valuation, etc.) exactly as the pipeline
            computed it - this is an exact reconciliation, not an approximation. The callouts above
            highlight the three largest-magnitude drivers, positive or negative.</p>
        </InfoTag>
      </h3></div><div className="period-control" aria-label="Score model variant">{['champion', 'challenger'].map((key) => explainability.attribution?.[key] && <button className={variant === key ? 'active' : ''} key={key} onClick={() => setVariant(key)}>{key}</button>)}</div></header>
      <Waterfall attribution={attribution} />
    </section>
    <section><span className="eyebrow">Metric-level evidence</span><h3>What each input contributed</h3><ul className="metric-explanation-list">{metrics.map((metric) => <MetricExplanation key={metric.metric} metric={metric} sector={stock.sector || 'its sector'} />)}</ul></section>
    <section><span className="eyebrow">Stored history</span><h3>Research score over time
      <InfoTag label="Research score over time">
        <strong>Research score over time</strong>
        <p>The stored research score at each refresh, not a backtest or a price chart. Dots mark a
          change in stance (e.g. Promising to Attractive). Needs several distinct monthly snapshots
          before a trend line appears - see the note below when it has not yet accumulated enough.</p>
      </InfoTag>
    </h3><ScoreHistory history={explainability.score_history} /></section>
    {explainability.anomalies?.length > 0 && <section><span className="eyebrow">Divergence flags</span><h3>Patterns worth reviewing</h3><ul className="anomaly-list">{explainability.anomalies.map((flag) => <li className={`severity-${flag.severity}`} key={flag.id}>{flag.message}</li>)}</ul></section>}
  </div>
}
