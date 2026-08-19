import { useState } from 'react'
import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import SignalMetricsPanel from '../components/SignalMetricsPanel.jsx'
import ResearchEvidence from '../components/ResearchEvidence'
import { ScreenNavigation } from './ResearchScreen'
import InfoTag from '../components/InfoTag.jsx'
import AutoOverviewLine from '../components/AutoOverviewLine.jsx'
import PairedBarChart from '../components/PairedBarChart.jsx'

const HORIZON_ORDER = ['1M', '3M', '6M', '12M']

const title = (value = '') => String(value).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const pct = (value) => value == null ? '–' : `${Math.round(Number(value) * 100)}%`
const score = (value) => value == null ? '–' : Math.round(Number(value))

function rankIcOverview(report, error) {
  if (error) return {
    tone: 'caution',
    text: 'The ranking overview is unavailable because the signal-metrics report could not be read.',
  }

  const rankMetrics = (report?.metrics || [])
    .filter((metric) => metric.id?.startsWith('rank_ic_') && metric.status === 'ready'
      && metric.value != null && Number.isFinite(Number(metric.value)))
    .sort((left, right) => Number(right.value) - Number(left.value))
  const breached = Number(report?.summary?.breached) || 0
  const liveDays = Number(report?.live_sample?.days) || 0
  const warning = breached
    ? `Across the full test suite, ${breached} threshold${breached === 1 ? ' is' : 's are'} breached.`
    : 'No published thresholds are breached.'
  const sample = liveDays
    ? ` Live-only evidence spans ${liveDays} day${liveDays === 1 ? '' : 's'}.`
    : ''

  if (!rankMetrics.length) return {
    tone: 'caution',
    text: `No ready Rank IC horizons can be ranked yet. ${warning}${sample}`,
  }

  const leader = rankMetrics[0]
  const horizon = leader.label?.match(/\(([^)]+)\)/)?.[1]
    || leader.id.replace('rank_ic_', '')
  const clears = rankMetrics.filter((metric) => metric.breached === false).length
  const horizonLabel = `${rankMetrics.length} tested horizon${rankMetrics.length === 1 ? '' : 's'}`
  return {
    tone: breached ? 'caution' : 'positive',
    text: `${horizon} is the strongest ${horizonLabel === '1 tested horizon' ? 'ready horizon' : 'tested horizon'} at Rank IC ${leader.display || Number(leader.value).toFixed(3)}; ${clears} of ${horizonLabel} clear${clears === 1 ? 's' : ''} the published floor. ${warning}${sample}`,
  }
}

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
        <div className="shadow-layer"><span>Structural</span><strong>{score(structural.effective_score)}</strong><small>{pct(structural.evidence_weight_resolved)} of evidence weight resolved · {pct(structural.coverage)} data coverage</small></div>
        <div className="shadow-layer"><span>Timeliness</span><strong>{score(timeliness.effective_score)}</strong><small>{timeliness.effective_score == null ? 'not measured' : `${pct(timeliness.evidence_weight_resolved)} of evidence weight resolved`} · {title(timeliness.classification)}</small></div>
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
    <div className="ic-chart-head"><b>1M quintiles
      <InfoTag label="1M quintiles">
        <strong>1-month quintile returns</strong>
        <p>Splits scored companies into five equal-size groups (quintiles) by this variant's score,
          then shows each group's mean forward 1-month return. A useful model shows a monotonic
          staircase - Q5 (highest score) beating Q1 (lowest) - not a flat or reversed pattern.</p>
      </InfoTag>
    </b><span>{oneMonth.bucket_returns?.['5']?.monotonic ? 'Monotonic' : oneMonth.periods_accumulated ? 'Not monotonic' : 'Accumulating'}</span></div>
    <BucketChart summary={oneMonth} />
  </article>
}

function sortedHorizons(variants) {
  return [...new Set([
    ...Object.keys(variants.champion || {}),
    ...Object.keys(variants.challenger || {}),
  ])].sort((left, right) => {
    const leftIndex = HORIZON_ORDER.indexOf(left)
    const rightIndex = HORIZON_ORDER.indexOf(right)
    if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right)
    if (leftIndex === -1) return 1
    if (rightIndex === -1) return -1
    return leftIndex - rightIndex
  })
}

// One coverage_regime's worth of the Model Evidence panel: the bar chart plus every
// per-variant card. Reused standalone for Pre/Post and side by side for Compare.
function RegimeReport({ report, label, refreshCount }) {
  const variants = report?.variants || {}
  const allHorizons = sortedHorizons(variants)
  return <div className="ic-regime-report">
    {label && <div className="ic-regime-report-head"><b>{label}</b><span className="chip">{refreshCount || 0} snapshots</span></div>}
    <PairedBarChart
      groups={allHorizons.map((horizon) => ({
        label: horizon,
        values: [variants.champion?.[horizon]?.mean_rank_ic, variants.challenger?.[horizon]?.mean_rank_ic],
      }))}
      seriesLabels={['Champion', 'Challenger']}
      yFormatter={icValue}
      caption={`Mean rank IC, champion versus challenger, by horizon${label ? ` (${label})` : ''}`}
    />
    <div className="ic-variant-grid">
      {Object.entries(variants).map(([name, horizons]) => <VariantValidation key={name} name={name} horizons={horizons} />)}
    </div>
  </div>
}

// Phase 5's Pre | Post | Compare control (docs/QUESTIONS-FOR-OWNER.md question 1):
// pre- and post-enrichment-ladder periods are never blended into one IC number on the
// backend (pipeline/validation/ic_harness.py's coverage_regime guard), so every Model
// Evidence metric on this page is scoped to one regime at a time -- Compare is the two
// side by side, not a merge. Post/Compare stay hidden until the backend actually has
// ladder data and enough of it (default_regime_view / compare_available), so this
// control is inert today and activates itself the moment real post-ladder evidence exists.
function ICValidation({ data, error }) {
  const regimes = data?.coverage_regimes || {}
  const refreshCounts = data?.refresh_counts || {}
  const preReport = regimes.pre_enrichment_ladder || data
  const postReport = regimes.enrichment_ladder_v1
  const hasPost = Boolean(postReport)
  const compareAvailable = Boolean(data?.compare_available)
  const defaultView = data?.default_regime_view === 'enrichment_ladder_v1' ? 'post' : 'pre'
  const [requestedView, setRequestedView] = useState(null)
  const view = requestedView === 'post' && !hasPost ? 'pre'
    : requestedView === 'compare' && !compareAvailable ? defaultView
    : requestedView || defaultView

  if (error) return <section className="card etf-state" role="alert"><strong>IC validation unavailable</strong><span>Run the prospective validation harness. {error.message}</span></section>
  return <section className="ic-validation-section">
    <header className="section-heading">
      <div><span className="eyebrow">Prospective evidence</span><h2>Champion versus challenger</h2>
        <p>Point-in-time scores accumulate before returns are known. ICIR stays hidden until 24 monthly periods exist.</p></div>
      {(hasPost || compareAvailable)
        ? <div className="ic-regime-toggle" role="group" aria-label="Coverage regime"><div>
            <button type="button" className={view === 'pre' ? 'is-active' : ''} onClick={() => setRequestedView('pre')}>Pre</button>
            {hasPost && <button type="button" className={view === 'post' ? 'is-active' : ''} onClick={() => setRequestedView('post')}>Post</button>}
            {compareAvailable && <button type="button" className={view === 'compare' ? 'is-active' : ''} onClick={() => setRequestedView('compare')}>Compare</button>}
          </div></div>
        : <span className="chip">{refreshCounts.pre_enrichment_ladder ?? data?.snapshot_refreshes ?? 0} snapshots</span>}
    </header>
    {view === 'compare'
      ? <div className="ic-regime-compare">
          <RegimeReport report={preReport} label="Pre-ladder" refreshCount={refreshCounts.pre_enrichment_ladder} />
          <RegimeReport report={postReport} label="Post-ladder" refreshCount={refreshCounts.enrichment_ladder_v1} />
        </div>
      : <RegimeReport report={view === 'post' ? postReport : preReport} />}
    <p className="ic-integrity-note">Historical reconstruction is excluded because current-as-reported fundamentals would introduce look-ahead contamination.</p>
  </section>
}

export default function LiveValidation() {
  const { data, loading, error } = useData('validation/live_v2_validation.json')
  const { data: icData, loading: icLoading, error: icError } = useData('validation/ic_validation.json')
  const { data: evidence, error: evidenceError } = useData('validation/research_evidence.json')
  const { data: signalMetrics, loading: signalLoading, error: signalError } = useData('validation/signal_metrics.json')
  if (loading || icLoading || signalLoading) return <><ScreenNavigation /><Loading /></>
  const overview = rankIcOverview(signalMetrics, signalError)
  return <><ScreenNavigation />
    <div className="page-head"><div><span className="eyebrow">Controlled staging refresh</span><h1 className="page-title">Live v2 validation</h1>
      <p className="page-sub">Provider lineage, applicability, confidence gates, and independent decision layers. This view never replaces production output.</p></div></div>
    <AutoOverviewLine tone={overview.tone}>{overview.text}</AutoOverviewLine>
    <SignalMetricsPanel report={signalMetrics} error={signalError} />
    <ResearchEvidence data={evidence} error={evidenceError} />
    <ICValidation data={icData} error={icError} />
    {error ? <div className="card etf-state" role="alert"><strong>Validation artifact unavailable</strong><span>Run pipeline/live_v2_validation.py. {error.message}</span></div>
      : <><div className="shadow-evidence"><span><b>{data?.summary?.passed || 0}</b> passed</span><span><b>{data?.summary?.failed || 0}</b> failed</span><span>Cutoff {data?.data_cutoff || '–'}</span></div>
        <div className="validation-grid">{(data?.results || []).map((row) => <TickerValidation key={row.ticker} row={row} />)}</div></>}
  </>
}
