import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import SignalMetricsPanel from '../components/SignalMetricsPanel.jsx'
import ResearchEvidence from '../components/ResearchEvidence'
import { ScreenNavigation } from './ResearchScreen'
import InfoTag from '../components/InfoTag.jsx'
import AutoOverviewLine from '../components/AutoOverviewLine.jsx'
import PairedBarChart from '../components/PairedBarChart.jsx'
import DataTable from '../components/DataTable.jsx'

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

function ICValidation({ data, error }) {
  if (error) return <section className="card etf-state" role="alert"><strong>IC validation unavailable</strong><span>Run the prospective validation harness. {error.message}</span></section>
  const variants = data?.variants || {}
  const allHorizons = [...new Set([
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
  return <section className="ic-validation-section">
    <header className="section-heading"><div><span className="eyebrow">Prospective evidence</span><h2>Champion versus challenger</h2>
      <p>Point-in-time scores accumulate before returns are known. ICIR stays hidden until 24 monthly periods exist.</p></div>
      <span className="chip">{data?.snapshot_refreshes || 0} snapshots</span></header>
    <PairedBarChart
      groups={allHorizons.map((horizon) => ({
        label: horizon,
        values: [variants.champion?.[horizon]?.mean_rank_ic, variants.challenger?.[horizon]?.mean_rank_ic],
      }))}
      seriesLabels={['Champion', 'Challenger']}
      yFormatter={icValue}
      caption="Mean rank IC, champion versus challenger, by horizon"
    />
    <div className="ic-variant-grid">
      {Object.entries(variants).map(([name, horizons]) => <VariantValidation key={name} name={name} horizons={horizons} />)}
    </div>
    <p className="ic-integrity-note">Historical reconstruction is excluded because current-as-reported fundamentals would introduce look-ahead contamination.</p>
  </section>
}

function EtfValidationCard({ row }) {
  const metrics = row.one_year?.metrics || {}
  const checks = Object.entries(row.checks || {})
  const percent = (value, digits = 1) => value == null ? '–' : `${Number(value).toFixed(digits)}%`
  return <article className="card validation-card">
    <header className="validation-card-head">
      <div><span className="eyebrow">{title(row.case)}</span><h2>{row.ticker}</h2></div>
      <Status value={row.status} />
    </header>
    {row.status !== 'pass' && row.reason_code ? <div role="alert"><b>{row.reason_code}</b><p>{row.message}</p></div> : <>
      <div className="shadow-layers">
        <div className="shadow-layer"><span>Benchmark</span><strong>{row.benchmark?.ticker || '–'}</strong><small>{row.benchmark?.quality_label || 'Unlabeled'} · {pct(row.benchmark?.confidence)} confidence</small></div>
        <div className="shadow-layer"><span>Fund return (1Y)</span><strong>{percent(metrics.fund_return)}</strong><small>Benchmark {percent(metrics.benchmark_return)}</small></div>
        <div className="shadow-layer"><span>Excess return</span><strong>{percent(metrics.excess_return, 2)}</strong><small>Beta {metrics.beta != null ? Number(metrics.beta).toFixed(2) : '–'} · Corr {metrics.correlation != null ? Number(metrics.correlation).toFixed(3) : '–'}</small></div>
        <div className="shadow-layer"><span>Capture</span><strong>{percent(metrics.up_capture, 0)} up</strong><small>{percent(metrics.down_capture, 0)} down</small></div>
      </div>
      <dl className="analysis-quality-grid">
        {checks.map(([key, passed]) => <div key={key}><dt>{title(key)}</dt><dd className={passed ? 'validation-pass' : 'validation-fail'}>{passed ? 'Pass' : 'Fail'}</dd></div>)}
      </dl>
    </>}
  </article>
}

function EtfValidation({ data, error }) {
  if (error) return <section className="card etf-state" role="alert"><strong>ETF validation unavailable</strong><span>Run pipeline/live_etf_validation.py. {error.message}</span></section>
  return <section className="ic-validation-section">
    <header className="section-heading"><div><span className="eyebrow">Cross-asset spot check</span><h2>ETF watchlist benchmark validation</h2>
      <p>Checks benchmark-proxy honesty, adjusted-total-return basis, and capture-ratio sample gating for a representative slice of the ETF watchlist spanning equity, bond, commodity, leveraged, and currency-hedged funds.</p></div></header>
    <div className="shadow-evidence"><span><b>{data?.summary?.passed || 0}</b> passed</span><span><b>{data?.summary?.failed || 0}</b> failed</span></div>
    <div className="validation-grid">{(data?.results || []).map((row) => <EtfValidationCard key={row.ticker} row={row} />)}</div>
  </section>
}

// Renders any pipeline/validation/composite_attribution.py report: does each weighted metric
// predict on its own (own rank IC, ignoring the blend), and does the composite actually need
// it (delta IC - the composite's rank IC minus its rank IC with that metric's weight removed
// and the rest reweighted; negative means the composite predicts *better* without it). Shared
// by every composite screen below rather than duplicated per screen, since
// composite_attribution.build_attribution_report publishes the same shape for all of them.
const ATTRIBUTION_COLUMNS = [
  { key: 'name', label: 'Metric', rowHeader: true, cell: (row) => title(row.id) },
  { key: 'weight', label: 'Weight', numeric: true, cell: (row) => row.weight == null ? '–' : `${Math.round(row.weight * 100)}%` },
  { key: 'own_rank_ic', label: 'Own rank IC', numeric: true, cell: (row) => icValue(row.own_rank_ic) },
  { key: 'delta_ic', label: 'Delta IC', numeric: true, cell: (row) => icValue(row.delta_ic) },
  {
    key: 'verdict', label: 'Verdict', sortable: false,
    cell: (row) => row.delta_ic == null ? '–'
      : row.hurts_composite
        ? <span className="validation-fail">Hurts composite</span>
        : <span className="validation-pass">Earns its weight</span>,
  },
]

function AttributionTable({ attribution }) {
  const rows = Object.entries(attribution?.metrics || {}).map(([id, metric]) => ({ id, ...metric }))
  if (!rows.length) return null
  return <div className="attribution-block">
    <div className="ic-chart-head"><b>Per-metric attribution
      <InfoTag label="Per-metric attribution">
        <strong>Does each weighted input earn its place?</strong>
        <p>Own rank IC is the metric's own predictive power, standalone - ignoring the blend
          entirely. Delta IC is the full composite's rank IC minus its rank IC with that
          metric's weight removed and the rest reweighted over what remains; negative means
          the composite predicts better once that metric is gone.</p>
      </InfoTag>
    </b><span>{attribution.status === 'eligible' ? `${attribution.eligible_periods} periods` : 'Accumulating'}</span></div>
    <DataTable columns={ATTRIBUTION_COLUMNS} rows={rows} getKey={(row) => row.id} defaultSort={{ key: 'weight', dir: 'desc' }} className="attribution-table" />
  </div>
}

function RankIcMetricCard({ id, metric, eyebrow = 'Component' }) {
  return <article className="card ic-variant-card">
    <header><div><span className="eyebrow">{eyebrow}</span><h3>{title(id)}</h3></div>
      <Status value={metric.status} /></header>
    <dl className="analysis-quality-grid">
      <div><dt>Periods</dt><dd>{metric.eligible_periods || 0} of {metric.minimum_icir_periods || 24}</dd></div>
      <div><dt>Mean rank IC</dt><dd>{icValue(metric.mean_rank_ic)}</dd></div>
      <div><dt>ICIR</dt><dd>{metric.status === 'eligible' ? icValue(metric.icir) : 'Not available'}</dd></div>
      <div><dt>Hit rate</dt><dd>{pct(metric.hit_rate)}</dd></div>
    </dl>
    {metric.attribution && <AttributionTable attribution={metric.attribution} />}
  </article>
}

// Shared by the theme, swing, and growth sections below: all three read a
// `{ snapshot_dates_recorded, metrics: { id: { status, eligible_periods, ... } } }`
// artifact shaped identically to theme_metrics.json (see pipeline/validation/theme_ic.py) -
// swing_ic.py and growth_ic.py were built to match that shape rather than invent their own,
// so one renderer covers all three instead of three near-identical ones. `attribution` is an
// optional top-level composite_attribution report (swing has one; theme does not, since it
// has no sub-metric weights of its own to attribute).
function RankIcValidationSection({ data, error, eyebrow, title: heading, description, script, cardEyebrow, attribution }) {
  if (error) return <section className="card etf-state" role="alert"><strong>{heading} unavailable</strong><span>Run {script}. {error.message}</span></section>
  const metrics = data?.metrics || {}
  const minimumPeriods = Object.values(metrics)[0]?.minimum_icir_periods || 24
  return <section className="ic-validation-section">
    <header className="section-heading"><div><span className="eyebrow">{eyebrow}</span><h2>{heading}</h2>
      <p>{description} ICIR stays hidden until {minimumPeriods} monthly periods exist.</p></div>
      <span className="chip">{data?.snapshot_dates_recorded || 0} snapshots</span></header>
    <div className="ic-variant-grid">{Object.entries(metrics).map(([id, metric]) => <RankIcMetricCard key={id} id={id} metric={metric} eyebrow={cardEyebrow} />)}</div>
    {attribution && <AttributionTable attribution={attribution} />}
  </section>
}

// Pre-breakout and Momentum publish one composite (not several named ones like theme/growth),
// paired with its own composite_attribution report - a `{ composite: {...}, attribution: {...} }`
// shape distinct enough from RankIcValidationSection's `metrics` dict to warrant its own
// renderer rather than forcing a single-entry metrics dict through that one.
function CompositeAttributionValidation({ data, error, eyebrow, title: heading, description, script, snapshotLabel }) {
  if (error) return <section className="card etf-state" role="alert"><strong>{heading} unavailable</strong><span>Run {script}. {error.message}</span></section>
  const composite = data?.composite || {}
  return <section className="ic-validation-section">
    <header className="section-heading"><div><span className="eyebrow">{eyebrow}</span><h2>{heading}</h2>
      <p>{description} ICIR stays hidden until {composite.minimum_icir_periods || 24} monthly periods exist.</p></div>
      <span className="chip">{snapshotLabel}</span></header>
    <div className="ic-variant-grid">
      <RankIcMetricCard id="composite_score" metric={composite} eyebrow="Rank IC" />
    </div>
    <AttributionTable attribution={data?.attribution} />
  </section>
}

const OPTIONS_GRADED_METRIC = 'short_term_trades_score'

function OptionsIcValidation({ data, error }) {
  if (error) return <section className="card etf-state" role="alert"><strong>Options screen validation unavailable</strong><span>Run pipeline/validation/options_ic.py. {error.message}</span></section>
  const metric = data?.metrics?.[OPTIONS_GRADED_METRIC]
  return <section className="ic-validation-section">
    <header className="section-heading"><div><span className="eyebrow">Prospective evidence</span><h2>Options screen validation</h2>
      <p>Rank IC of the Short-term-trades screen's selection score against each recommended position's realized payoff (premium collected, assignment or expiration outcome), graded once that position's own 1-to-14-day expiration has actually passed - not a simulated chain. ICIR stays hidden until {metric?.minimum_icir_periods || 24} monthly periods exist.</p></div>
      <span className="chip">{data?.positions_resolved || 0} of {data?.positions_recorded || 0} positions resolved</span></header>
    {metric && <div className="ic-variant-grid"><RankIcMetricCard id={OPTIONS_GRADED_METRIC} metric={metric} eyebrow="Options screen" /></div>}
  </section>
}

export default function LiveValidation() {
  const { data, loading, error } = useData('validation/live_v2_validation.json')
  const { data: icData, loading: icLoading, error: icError } = useData('validation/ic_validation.json')
  const { data: evidence, error: evidenceError } = useData('validation/research_evidence.json')
  const { data: signalMetrics, loading: signalLoading, error: signalError } = useData('validation/signal_metrics.json')
  const { data: etfData, error: etfError } = useData('validation/live_etf_validation.json')
  const { data: themeData, error: themeError } = useData('validation/theme_metrics.json')
  const { data: swingData, error: swingError } = useData('validation/swing_metrics.json')
  const { data: growthData, error: growthError } = useData('validation/growth_metrics.json')
  const { data: optionsIcData, error: optionsIcError } = useData('validation/options_metrics.json')
  const { data: preBreakoutData, error: preBreakoutError } = useData('validation/pre_breakout_metrics.json')
  const { data: momentumData, error: momentumError } = useData('validation/momentum_metrics.json')
  if (loading || icLoading || signalLoading) return <><ScreenNavigation /><Loading /></>
  const overview = rankIcOverview(signalMetrics, signalError)
  return <><ScreenNavigation />
    <div className="page-head"><div><span className="eyebrow">Controlled staging refresh</span><h1 className="page-title">Live v2 validation</h1>
      <p className="page-sub">Provider lineage, applicability, confidence gates, and independent decision layers. This view never replaces production output.</p></div></div>
    <AutoOverviewLine tone={overview.tone}>{overview.text}</AutoOverviewLine>
    <SignalMetricsPanel report={signalMetrics} error={signalError} />
    <ResearchEvidence data={evidence} error={evidenceError} />
    <ICValidation data={icData} error={icError} />
    <EtfValidation data={etfData} error={etfError} />
    <RankIcValidationSection data={themeData} error={themeError} eyebrow="Prospective evidence" cardEyebrow="Theme component"
      title="Thematic screen validation" script="pipeline/validation/theme_ic.py"
      description="Rank IC for the theme exposure, connectivity, and structural-rank components behind the thematic and factor screens." />
    <RankIcValidationSection data={swingData} error={swingError} eyebrow="Prospective evidence" cardEyebrow="Swing screen"
      title="Swing screen validation" script="pipeline/validation/swing_ic.py" attribution={swingData?.attribution}
      description="Rank IC of the swing screen's composite_z signal against a forward return at a 14-day horizon (the mid 'M' tier), read from shadow_store/swing's own daily basket rather than a separate recorder. Below, every one of its 5 legs' own predictive power and marginal impact on the composite." />
    <RankIcValidationSection data={growthData} error={growthError} eyebrow="Prospective evidence" cardEyebrow="Growth screen"
      title="Fast growth screen validation" script="pipeline/validation/growth_ic.py"
      description="Rank IC of the breakout-in-progress and emerging-growth screens' selection scores against forward return (1-month and 3-month horizons respectively), plus every weighted component's own predictive power and marginal impact on its composite - the first live measurement either screen has ever had." />
    <CompositeAttributionValidation data={preBreakoutData} error={preBreakoutError} eyebrow="Prospective evidence"
      title="Pre-breakout screen validation" script="pipeline/validation/pre_breakout_ic.py"
      snapshotLabel={`${preBreakoutData?.snapshot_dates_recorded || 0} snapshots`}
      description="Rank IC of the pre-breakout composite against a 3-month forward return, plus every one of its 11 standardized subfactors' own predictive power and marginal impact on the composite - across the 3 named legs (fundamental inflection, momentum/relative strength, flow sentiment)." />
    <CompositeAttributionValidation data={momentumData} error={momentumError} eyebrow="Prospective evidence"
      title="Momentum screen validation" script="pipeline/validation/momentum_ic.py"
      snapshotLabel={`${momentumData?.snapshot_dates_recorded || 0} snapshots`}
      description="Rank IC of the momentum composite against a 1-month forward return, plus every one of its 5 factors' own predictive power and marginal impact on the composite." />
    <OptionsIcValidation data={optionsIcData} error={optionsIcError} />
    {error ? <div className="card etf-state" role="alert"><strong>Validation artifact unavailable</strong><span>Run pipeline/live_v2_validation.py. {error.message}</span></div>
      : <><div className="shadow-evidence"><span><b>{data?.summary?.passed || 0}</b> passed</span><span><b>{data?.summary?.failed || 0}</b> failed</span><span>Cutoff {data?.data_cutoff || '–'}</span></div>
        <div className="validation-grid">{(data?.results || []).map((row) => <TickerValidation key={row.ticker} row={row} />)}</div></>}
  </>
}
