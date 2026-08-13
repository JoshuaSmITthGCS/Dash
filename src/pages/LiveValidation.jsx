import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import SignalMetricsPanel from '../components/SignalMetricsPanel.jsx'
import { ScreenNavigation } from './ResearchScreen'

const title = (value = '') => String(value).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const pct = (value) => value == null ? '–' : `${Math.round(Number(value) * 100)}%`
const score = (value) => value == null ? '–' : Math.round(Number(value))

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

const icValue = (value) => value == null ? 'Not available' : Number(value).toFixed(3)

function BucketChart({ summary }) {
  const buckets = summary?.bucket_returns?.['5']?.buckets || []
  const present = buckets.filter((bucket) => bucket.mean_forward_return != null)
  if (!present.length) return <div className="ic-empty-chart">Quintile returns appear after the first complete forward period.</div>
  const scale = Math.max(...present.map((bucket) => Math.abs(bucket.mean_forward_return)), 0.001)
  return <div className="ic-buckets" aria-label="Quintile mean forward returns">
    {present.map((bucket) => <div key={bucket.bucket}>
      <span style={{ height: `${Math.max(6, Math.abs(bucket.mean_forward_return) / scale * 64)}px` }} />
      <b>Q{bucket.bucket}</b>
      <small>{(bucket.mean_forward_return * 100).toFixed(1)}%</small>
    </div>)}
  </div>
}

function VariantValidation({ name, horizons = {} }) {
  const oneMonth = horizons['1M'] || {}
  return <article className="card ic-variant-card">
    <header><div><span className="eyebrow">Score variant</span><h3>{title(name)}</h3></div>
      <Status value={oneMonth.status} /></header>
    <div className="ic-horizon-grid">
      {Object.entries(horizons).map(([horizon, summary]) => <section key={horizon}>
        <b>{horizon}</b>
        <strong>{summary.periods_accumulated || 0}</strong>
        <small>of {summary.minimum_periods || 24} periods</small>
        <dl>
          <div><dt>Mean IC</dt><dd>{icValue(summary.mean_rank_ic)}</dd></div>
          <div><dt>95% CI</dt><dd>{summary.confidence_interval_95?.[0] == null ? 'Not available' : `${icValue(summary.confidence_interval_95[0])} to ${icValue(summary.confidence_interval_95[1])}`}</dd></div>
          <div><dt>ICIR</dt><dd>{summary.status === 'eligible' ? icValue(summary.icir) : summary.status_message}</dd></div>
        </dl>
      </section>)}
    </div>
    <div className="ic-chart-head"><b>1M quintiles</b><span>{oneMonth.bucket_returns?.['5']?.monotonic ? 'Monotonic' : oneMonth.periods_accumulated ? 'Not monotonic' : 'Accumulating'}</span></div>
    <BucketChart summary={oneMonth} />
  </article>
}

function ICValidation({ data, error }) {
  if (error) return <section className="card etf-state" role="alert"><strong>IC validation unavailable</strong><span>Run the prospective validation harness. {error.message}</span></section>
  const variants = data?.variants || {}
  return <section className="ic-validation-section">
    <header className="section-heading"><div><span className="eyebrow">Prospective evidence</span><h2>Champion versus challenger</h2>
      <p>Point-in-time scores accumulate before returns are known. ICIR stays hidden until 24 monthly periods exist.</p></div>
      <span className="chip">{data?.snapshot_refreshes || 0} snapshots</span></header>
    <div className="ic-variant-grid">
      {Object.entries(variants).map(([name, horizons]) => <VariantValidation key={name} name={name} horizons={horizons} />)}
    </div>
    <p className="ic-integrity-note">Historical reconstruction is excluded because current-as-reported fundamentals would introduce look-ahead contamination.</p>
  </section>
}

export default function LiveValidation() {
  const { data, loading, error } = useData('validation/live_v2_validation.json')
  const { data: icData, loading: icLoading, error: icError } = useData('validation/ic_validation.json')
  const { data: signalMetrics, loading: signalLoading, error: signalError } = useData('validation/signal_metrics.json')
  if (loading || icLoading || signalLoading) return <><ScreenNavigation /><Loading /></>
  return <><ScreenNavigation />
    <div className="page-head"><div><span className="eyebrow">Controlled staging refresh</span><h1 className="page-title">Live v2 validation</h1>
      <p className="page-sub">Provider lineage, applicability, confidence gates, and independent decision layers. This view never replaces production output.</p></div></div>
    <SignalMetricsPanel report={signalMetrics} error={signalError} />
    <ICValidation data={icData} error={icError} />
    {error ? <div className="card etf-state" role="alert"><strong>Validation artifact unavailable</strong><span>Run pipeline/live_v2_validation.py. {error.message}</span></div>
      : <><div className="shadow-evidence"><span><b>{data?.summary?.passed || 0}</b> passed</span><span><b>{data?.summary?.failed || 0}</b> failed</span><span>Cutoff {data?.data_cutoff || '–'}</span></div>
        <div className="validation-grid">{(data?.results || []).map((row) => <TickerValidation key={row.ticker} row={row} />)}</div></>}
  </>
}
