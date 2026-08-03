import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import { ScreenNavigation } from './ResearchScreen'

const title = (value = '') => String(value).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const pct = (value) => value == null ? '—' : `${Math.round(Number(value) * 100)}%`
const score = (value) => value == null ? '—' : Math.round(Number(value))

function Status({ value }) {
  return <span className={`chip validation-${value}`}>{title(value || 'unavailable')}</span>
}

function TickerValidation({ row }) {
  const structural = row.analysis?.structural || {}
  const timeliness = row.analysis?.timeliness || {}
  const applicability = row.analysis?.applicability || {}
  const failed = Object.entries(row.invariants || {}).filter(([, result]) => result.status !== 'pass')
  return <article className="card validation-card">
    <header className="validation-card-head">
      <div><span className="eyebrow">{row.classification?.profile_id || 'Provider unavailable'}</span>
        <h2>{row.ticker}</h2></div><Status value={row.status} />
    </header>
    {row.provider_status === 'error' ? <div role="alert"><b>{row.reason_code}</b><p>{row.message}</p></div> : <>
      <div className="shadow-layers">
        <div className="shadow-layer"><span>Structural</span><strong>{score(structural.effective_score)}</strong><small>{pct(structural.confidence)} confidence · {pct(structural.coverage)} coverage</small></div>
        <div className="shadow-layer"><span>Timeliness</span><strong>{score(timeliness.effective_score)}</strong><small>{pct(timeliness.confidence)} confidence · {title(timeliness.classification)}</small></div>
        <div className="shadow-layer"><span>Company evidence</span><strong>{row.company_action?.display_label || title(row.company_action?.label)}</strong><small>{(row.company_action?.reason_codes || []).map(title).join(' · ')}</small></div>
        <div className="shadow-layer"><span>Position rule</span><strong>{row.position_action?.display_label || title(row.position_action?.label)}</strong><small>{(row.position_action?.reason_codes || []).map(title).join(' · ') || 'No position supplied'}</small></div>
      </div>
      <dl className="analysis-quality-grid">
        <div><dt>Peer sample</dt><dd>{row.classification?.valid_peer_count || 0} / {row.classification?.total_peer_count || 0}</dd></div>
        <div><dt>Percentile</dt><dd>{title(row.classification?.percentile_status)}</dd></div>
        <div><dt>Profile confidence</dt><dd>{pct(applicability.profile_confidence)}</dd></div>
      </dl>
      <details><summary>Applicability and lineage</summary>
        <p><b>Applied:</b> {(applicability.applied_metrics || []).map(title).join(', ') || 'None with complete lineage'}</p>
        <p><b>Suppressed:</b> {(applicability.suppressed_metrics || []).map(title).join(', ') || 'None'}</p>
        <p><b>Unavailable replacements:</b> {(applicability.unavailable_replacement_metrics || []).map(title).join(', ') || 'None'}</p>
        <p><b>Critical gaps:</b> {(applicability.critical_data_gaps || []).map(title).join(', ') || 'None'}</p>
        <p><b>Provider conflicts:</b> {(structural.provider_conflicts || []).map(title).join(', ') || 'None'}</p>
      </details>
      {failed.length > 0 && <div className="analysis-warning" role="alert"><b>Failed invariants</b><ul>{failed.map(([key]) => <li key={key}>{title(key)}</li>)}</ul></div>}
    </>}
  </article>
}

export default function LiveValidation() {
  const { data, loading, error } = useData('validation/live_v2_validation.json')
  if (loading) return <><ScreenNavigation /><Loading /></>
  return <><ScreenNavigation />
    <div className="page-head"><div><span className="eyebrow">Controlled staging refresh</span><h1 className="page-title">Live v2 validation</h1>
      <p className="page-sub">Provider lineage, applicability, confidence gates, and independent decision layers. This view never replaces production output.</p></div></div>
    {error ? <div className="card etf-state" role="alert"><strong>Validation artifact unavailable</strong><span>Run pipeline/live_v2_validation.py. {error.message}</span></div>
      : <><div className="shadow-evidence"><span><b>{data?.summary?.passed || 0}</b> passed</span><span><b>{data?.summary?.failed || 0}</b> failed</span><span>Cutoff {data?.data_cutoff || '—'}</span></div>
        <div className="validation-grid">{(data?.results || []).map((row) => <TickerValidation key={row.ticker} row={row} />)}</div></>}
  </>
}
