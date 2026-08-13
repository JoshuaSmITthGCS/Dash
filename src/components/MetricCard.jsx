const STATUS = {
  positive: { icon: '▲', label: 'Positive' },
  neutral: { icon: '●', label: 'Neutral' },
  negative: { icon: '▼', label: 'Negative' },
  insufficient: { icon: '?', label: 'Insufficient' },
}

function sampleLabel(metric) {
  if (metric.frequency === 'point') return 'Point-in-time'
  if (metric.observations == null) return null
  const cadence = metric.frequency === 'monthly' ? 'monthly observations' : 'daily returns'
  return `${metric.observations} ${cadence}`
}

/** One config-driven metric renderer used in full and compact modes. */
export default function MetricCard({ metric, mode = 'full' }) {
  const status = STATUS[metric.assessment] || STATUS.insufficient
  const sample = sampleLabel(metric)
  return (
    <article
      className={`metric-tone-${metric.assessment === 'insufficient' ? 'unavailable' : metric.assessment}`}
      data-metric-card={mode}
      data-metric-id={metric.id}
    >
      <header>
        <span>{metric.name}</span>
        <span className="metric-status" aria-label={status.label}><i aria-hidden="true">{status.icon}</i>{mode === 'full' && status.label}</span>
      </header>
      <strong>{metric.assessment === 'insufficient' ? '? Insufficient' : metric.formattedValue}</strong>
      {metric.assessment === 'insufficient'
        ? <small>{metric.insufficientReason || metric.reason}</small>
        : <small>{[metric.supportingValue, sample].filter(Boolean).join(' · ')}</small>}
      {mode === 'full' && (
        <footer>
          {metric.confidence !== 'none' && <span className="metric-confidence">{metric.confidence} confidence</span>}
          {metric.trend && metric.trend !== 'unknown' && <span className={`metric-trend trend-${metric.trend}`}>{metric.trend === 'improving' ? '↑' : metric.trend === 'deteriorating' ? '↓' : '→'} {metric.trendDetail || metric.trend}</span>}
          {metric.tooltip?.measures && (
            <details className="metric-tooltip">
              <summary aria-label={`About ${metric.name}`}>What it measures</summary>
              <p>{metric.tooltip.measures}{metric.tooltip.better ? ` ${metric.tooltip.better}` : ''}</p>
            </details>
          )}
        </footer>
      )}
    </article>
  )
}

