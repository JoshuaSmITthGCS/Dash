import { useData, fmtDate } from '../lib/useData'

const SOURCE_LABELS = {
  advisor: 'Advisor engine',
}

export function freshness(generatedAt, now = Date.now()) {
  const timestamp = Date.parse(generatedAt)
  if (!Number.isFinite(timestamp)) return { stale: true, label: 'unknown age' }
  const hours = Math.max(0, Math.floor((now - timestamp) / 3_600_000))
  return { stale: hours >= 36, label: hours < 1 ? 'under 1h old' : `${hours}h old` }
}

export function DataStatus() {
  const { data: advisor } = useData('advisor.json')
  const { data: status } = useData('status.json')
  if (!advisor && !status) return null

  const mode = advisor?.data_mode || 'unknown'
  const age = freshness(advisor?.generated_at || status?.generated_at)
  const stages = Object.entries(status?.stages || {})
    .filter(([key]) => SOURCE_LABELS[key])
  const advisorStage = status?.stages?.advisor
  const unhealthy = advisorStage?.status === 'error' || advisorStage?.status === 'degraded' ||
    advisor?.source_status?.alpha_vantage?.status === 'degraded'
  const level = mode === 'demo' ? 'demo' : (age.stale || unhealthy ? 'warning' : 'live')

  return (
    <section className={`data-status ${level}`} aria-label="Pipeline data status" role="status">
      <div className="data-status-main">
        <strong>{mode === 'demo' ? 'Demo data' : level === 'live' ? 'Live data' : 'Data needs attention'}</strong>
        <span>{mode === 'demo'
          ? 'Generated fixtures are active. Do not use them for decisions.'
          : `Last researched ${fmtDate(advisor?.generated_at)} · ${age.label}`}</span>
      </div>
      {advisor?.source_status && <div className="source-health" aria-label="Provider health">
        {Object.entries(advisor.source_status).map(([key, source]) => <span className={`source-pill ${source.status}`} key={key}><span aria-hidden="true" className="source-dot" />{key.replace(/_/g, ' ')}</span>)}
      </div>}
      {stages.length > 0 && (
        <div className="source-health" aria-label="Source health">
          {stages.map(([key, stage]) => (
            <span className={`source-pill ${stage.status}`} key={key}
              title={stage.message || `${stage.source || SOURCE_LABELS[key]} checked ${fmtDate(stage.checked_at)}`}>
              <span aria-hidden="true" className="source-dot" />
              {SOURCE_LABELS[key]}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}
