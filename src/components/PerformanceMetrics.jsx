import { useEffect, useMemo, useState } from 'react'
import modelSettings from '../../pipeline/config/settings.json'
import MetricCard from './MetricCard.jsx'
import SignalMetricsPanel from './SignalMetricsPanel.jsx'
import { buildPortfolioMetricModel } from '../lib/portfolioMetricModel.js'
import { combinedEvidence, sectionAssessment } from '../lib/metricAssessment.js'

const VIEWS = [
  { id: 'overview', label: 'Overview' },
  { id: 'all', label: 'All Metrics' },
  { id: 'algorithm', label: 'Algorithm' },
  { id: 'historical', label: 'Historical' },
]

const FILTERS = ['All', 'Return', 'Risk', 'Benchmark', 'Algorithm', 'Statistical', 'Execution', 'Cost']

const STATUS_ICON = { positive: '▲', neutral: '●', negative: '▼', insufficient: '?' }

function sessionValue(key, fallback) {
  try { return globalThis.sessionStorage?.getItem(key) || fallback } catch { return fallback }
}

function storeSession(key, value) {
  try { globalThis.sessionStorage?.setItem(key, value) } catch { /* storage can be unavailable in private contexts */ }
}

function PersistentDetails({ storageId, className, defaultOpen = false, children }) {
  const key = `valuesignal.analytics.expanded.${storageId}`
  const [open, setOpen] = useState(() => sessionValue(key, defaultOpen ? 'open' : 'closed') === 'open')
  return <details className={className} open={open} onToggle={(event) => {
    const next = event.currentTarget.open
    setOpen(next)
    storeSession(key, next ? 'open' : 'closed')
  }}>{children}</details>
}

export function performanceMetricTone(key, value) {
  if (value == null || !Number.isFinite(value)) return 'unavailable'
  const thresholds = modelSettings.portfolio_analytics.performance_metric_tones[key]
  if (!thresholds) return 'neutral'
  if (value >= thresholds.good_min) return 'positive'
  if (value <= thresholds.bad_max) return 'negative'
  return 'neutral'
}

export function collapsedSummary(metrics) {
  if (!metrics?.available) return metrics?.reason || 'Unavailable'
  const sharpe = Number.isFinite(metrics.sharpe) ? metrics.sharpe.toFixed(2) : 'Unavailable'
  const drawdown = Number.isFinite(metrics.maxDrawdown) ? `${metrics.maxDrawdown.toFixed(1)}%` : 'Unavailable'
  return `Sharpe ${sharpe} · Max drawdown ${drawdown}`
}

function EvidenceCounts({ counts }) {
  return (
    <div className="analytics-counts" aria-label={`${counts.positive} positive, ${counts.neutral} neutral, ${counts.negative} negative, ${counts.insufficient} insufficient`}>
      {['positive', 'neutral', 'negative', 'insufficient'].map((status) => (
        <span key={status} className={`count-${status}`}><i aria-hidden="true">{STATUS_ICON[status]}</i>{counts[status]} <small>{status}</small></span>
      ))}
    </div>
  )
}

function EvidenceBar({ summary }) {
  const assessed = summary.counts.positive + summary.counts.neutral + summary.counts.negative
  const width = (status) => assessed ? summary.counts[status] / assessed * 100 : 0
  return (
    <div className="evidence-bar" aria-label="Assessed evidence balance">
      <i className="positive" style={{ width: `${width('positive')}%` }} />
      <i className="neutral" style={{ width: `${width('neutral')}%` }} />
      <i className="negative" style={{ width: `${width('negative')}%` }} />
    </div>
  )
}

function Driver({ label, metric }) {
  return <span><b>{label}</b>{metric ? metric.name.toLowerCase() : 'None measured'}</span>
}

function AnalyticsSection({ id, eyebrow, title, metrics, summary, sampleNote, defaultCore = 3 }) {
  const ordered = metrics.slice().sort((left, right) => right.priority - left.priority)
  const core = ordered.slice(0, defaultCore)
  const detail = ordered.slice(defaultCore)
  return (
    <section className="performance-metrics analytics-section" aria-labelledby={`${id}-title`}>
      <header>
        <div><span className="eyebrow">{eyebrow}</span><h2 id={`${id}-title`}>{title}</h2></div>
        <span className={`section-read read-${summary.read.toLowerCase()}`}>{summary.read}</span>
      </header>
      <EvidenceCounts counts={summary.counts} />
      <EvidenceBar summary={summary} />
      <p className="analytics-takeaway">{summary.narrative}</p>
      {sampleNote && <small className="analytics-sample">{sampleNote}</small>}
      <div className="analytics-drivers">
        <Driver label="Helping" metric={summary.helping} />
        <Driver label="Hurting" metric={summary.hurting} />
        <Driver label="Watch" metric={summary.watch} />
      </div>
      <div className="metric-card-grid">
        {core.map((row) => <MetricCard key={row.id} metric={row} />)}
      </div>
      {detail.length > 0 && (
        <PersistentDetails className="analytics-detail" storageId={`${id}-detail`}>
          <summary><span>Show {detail.length} more measure{detail.length === 1 ? '' : 's'}</span><small>{metrics.length} total</small></summary>
          <div className="metric-card-grid compact-grid">{detail.map((row) => <MetricCard key={row.id} metric={row} mode="compact" />)}</div>
        </PersistentDetails>
      )}
    </section>
  )
}

function OverallEvidence({ sections }) {
  const overall = combinedEvidence(sections)
  return (
    <section className="analytics-overall" aria-labelledby="analytics-overall-title">
      <div>
        <span className="eyebrow">Performance evidence</span>
        <h2 id="analytics-overall-title">Overall evidence: {overall.read}</h2>
        <p>{overall.narrative}</p>
      </div>
      <EvidenceCounts counts={overall.counts} />
      <div className="analytics-section-rollup">
        {sections.map((section) => <span key={section.id}><b>{section.label}</b>{section.summary.counts.positive} positive · {section.summary.counts.neutral} neutral · {section.summary.counts.negative} negative</span>)}
      </div>
    </section>
  )
}

function RollingSharpeChart({ statistics }) {
  const series = statistics?.rolling60 || []
  if (!series.length) return <div className="analytics-empty"><strong>Rolling Sharpe is insufficient</strong><p>Requires at least 60 contiguous daily returns in this scope.</p></div>
  const values = series.map((row) => row.value).filter(Number.isFinite)
  const minimum = Math.min(...values, -1)
  const maximum = Math.max(...values, 1)
  const points = series.map((row, index) => {
    const x = series.length === 1 ? 50 : index / (series.length - 1) * 100
    const y = 100 - (row.value - minimum) / (maximum - minimum) * 100
    return `${x},${y}`
  }).join(' ')
  const zeroY = 100 - (0 - minimum) / (maximum - minimum) * 100
  return (
    <section className="rolling-sharpe" aria-labelledby="rolling-sharpe-title">
      <header><div><span className="eyebrow">Stability</span><h2 id="rolling-sharpe-title">Rolling 60-day Sharpe</h2></div><small>{series.length} rolling windows</small></header>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Rolling 60-day Sharpe chart">
        <defs>
          <linearGradient id="rolling-sharpe-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--brand-primary)" stopOpacity=".18" />
            <stop offset="1" stopColor="var(--brand-primary)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" x2="100" y1={zeroY} y2={zeroY} />
        <polygon className="rolling-sharpe-fill" points={`${points} ${series.length === 1 ? '50' : '100'},100 0,100`} fill="url(#rolling-sharpe-grad)" />
        <polyline points={points} />
      </svg>
    </section>
  )
}

function EvidenceMatrix({ sections }) {
  return (
    <section className="evidence-matrix" aria-labelledby="evidence-matrix-title">
      <header><span className="eyebrow">Cross-section check</span><h2 id="evidence-matrix-title">Evidence matrix</h2></header>
      <div className="evidence-matrix-grid" role="table" aria-label="Evidence counts by section">
        <div role="row" className="matrix-head"><span role="columnheader">Section</span><span role="columnheader">Positive</span><span role="columnheader">Neutral</span><span role="columnheader">Negative</span><span role="columnheader">Insufficient</span></div>
        {sections.map((section) => <div role="row" key={section.id}><b role="rowheader">{section.label}</b><span>{section.summary.counts.positive}</span><span>{section.summary.counts.neutral}</span><span>{section.summary.counts.negative}</span><span>{section.summary.counts.insufficient}</span></div>)}
      </div>
    </section>
  )
}

function AllMetrics({ model }) {
  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const visible = useMemo(() => model.groups.map((group) => ({
    ...group,
    metrics: group.metrics.filter((row) => (filter === 'All' || row.category === filter) && `${row.name} ${row.id}`.toLowerCase().includes(query.trim().toLowerCase())),
  })).filter((group) => group.metrics.length), [filter, model.groups, query])
  return (
    <section className="all-metrics" aria-labelledby="all-metrics-title">
      <header><div><span className="eyebrow">Full tear-sheet</span><h2 id="all-metrics-title">All metrics</h2></div><small>{visible.reduce((sum, group) => sum + group.metrics.length, 0)} visible</small></header>
      <div className="metric-search"><label><span>Search metrics</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Sharpe, drawdown, alpha…" /></label></div>
      <div className="metric-filters" aria-label="Filter metrics">{FILTERS.map((item) => <button type="button" key={item} className={filter === item ? 'active' : ''} onClick={() => setFilter(item)}>{item}</button>)}</div>
      {visible.length ? visible.map((group) => (
        <PersistentDetails key={group.name} className="metric-group" storageId={`all-${group.name}`} defaultOpen>
          <summary><strong>{group.name}</strong><span>{group.metrics.length}</span></summary>
          <div className="metric-card-grid compact-grid">{group.metrics.map((row) => <MetricCard key={row.id} metric={row} mode="compact" />)}</div>
        </PersistentDetails>
      )) : <div className="analytics-empty"><strong>No matching metrics</strong><p>Try a broader filter or search term.</p></div>}
    </section>
  )
}

function ProspectiveClock({ prospective }) {
  if (!prospective) return null
  const criteria = prospective.promotion_criteria_champion_or_challenger || {}
  const trials = prospective.trial_count_for_deflated_statistics?.dsr_trial_count_used
  return (
    <section className="prospective-clock" aria-labelledby="prospective-clock-title">
      <header><div><span className="eyebrow">Pre-registered validation</span><h2 id="prospective-clock-title">Prospective clock</h2></div><span className="section-read read-inconclusive">0 / {criteria.minimum_periods || 24} periods</span></header>
      <p>Starts {prospective.harness_start_date}. Thresholds were frozen {prospective.frozen_at}; UI changes do not reset the clock.</p>
      <dl><div><dt>Mean rank IC</dt><dd>{criteria.mean_spearman_ic}</dd></div><div><dt>ICIR</dt><dd>{criteria.icir}</dd></div><div><dt>Deflated Sharpe</dt><dd>{criteria.deflated_sharpe}</dd></div><div><dt>PBO</dt><dd>{criteria.pbo}</dd></div><div><dt>Trials registry</dt><dd>N={trials ?? 'not recorded'}</dd></div></dl>
    </section>
  )
}

function BaselineComparison({ comparison }) {
  if (!comparison) return null
  const row = (label, counts) => <span><b>{label}</b>{counts.positive} positive · {counts.neutral} neutral · {counts.negative} negative</span>
  return (
    <section className="baseline-comparison" aria-labelledby="baseline-comparison-title">
      <header><div><span className="eyebrow">Compatible evidence only</span><h2 id="baseline-comparison-title">Baseline comparison</h2></div></header>
      <div>{row('Before algorithm', comparison.before)}{row('Since algorithm', comparison.since)}<span><b>Evidence shift</b>{comparison.positiveShift >= 0 ? '+' : ''}{comparison.positiveShift} positive · {comparison.negativeShift >= 0 ? '+' : ''}{comparison.negativeShift} negative</span></div>
      <p>{comparison.label} {comparison.compared} compatible sufficient metrics compared; {comparison.omitted} omitted for insufficient samples or incompatible definitions. This is observational, not a causal claim.</p>
    </section>
  )
}

export default function PerformanceMetrics({
  metrics, benchmarkLabel = 'benchmark',
  acceleration = null, capture = null, batting = null, underwater = null,
  shortTerm = null, risk = null,
  model: suppliedModel = null, statistics = null, factor = null, benchmark = null,
  exposure = null, execution = null, robustness = null, signalMetrics = null,
  prospective = null, scopes = [], scope = null, onScopeChange = null,
  baselineComparison = null,
}) {
  const model = suppliedModel || buildPortfolioMetricModel({ performance: metrics, statistics, acceleration, capture, batting, underwater, shortTerm, risk, factor, benchmark, exposure, execution, robustness })
  const [view, setView] = useState(() => sessionValue('valuesignal.analytics.view', 'overview'))
  const selectView = (next) => {
    setView(next)
    storeSession('valuesignal.analytics.view', next)
    if (next === 'algorithm' && scope === 'all_history' && scopes.some((item) => item.id === 'since_algorithm')) onScopeChange?.('since_algorithm')
  }
  useEffect(() => {
    if (view === 'algorithm' && scope === 'all_history' && scopes.some((item) => item.id === 'since_algorithm')) {
      onScopeChange?.('since_algorithm')
    }
  }, [onScopeChange, scope, scopes, view])
  const sections = [
    { id: 'standard', label: 'Risk & performance', metrics: model.standard, summary: sectionAssessment('standard', model.standard) },
    { id: 'comparison', label: 'Benchmark comparison', metrics: model.comparison, summary: sectionAssessment('comparison', model.comparison) },
    { id: 'fast', label: 'Short-term', metrics: model.fast, summary: sectionAssessment('fast', model.fast) },
  ]
  const sample = statistics?.available ? `${statistics.observations} daily returns · ${statistics.startDate} to ${statistics.endDate} · ${statistics.cadence.coveragePct.toFixed(1)}% weekday coverage` : statistics?.reason || metrics?.reason
  return (
    <div className="analytics-workspace">
      <nav className="analytics-toolbar" aria-label="Analytics views and scope">
        <div className="analytics-view-selector">{VIEWS.map((item) => <button type="button" key={item.id} aria-current={view === item.id ? 'page' : undefined} onClick={() => selectView(item.id)}>{item.label}</button>)}</div>
        {scopes.length > 0 && <label className="analytics-scope"><span>Scope</span><select value={scope || scopes[0].id} onChange={(event) => onScopeChange?.(event.target.value)}>{scopes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>}
      </nav>
      {view === 'overview' && <>
        <OverallEvidence sections={sections} />
        <AnalyticsSection id="standard-performance" eyebrow="Standard measures" title="Risk and performance" metrics={model.standard} summary={sections[0].summary} sampleNote={sample} />
        <AnalyticsSection id="benchmark-comparison" eyebrow="Comparison" title={`Versus the ${benchmarkLabel}`} metrics={model.comparison} summary={sections[1].summary} sampleNote={sample} />
        <AnalyticsSection id="short-term-view" eyebrow="Fast reads" title="Short-term view" metrics={model.fast} summary={sections[2].summary} sampleNote={shortTerm?.methodology || shortTerm?.reason} />
        <EvidenceMatrix sections={sections} />
      </>}
      {view === 'all' && <AllMetrics model={model} />}
      {view === 'algorithm' && <>
        <ProspectiveClock prospective={prospective} />
        <BaselineComparison comparison={baselineComparison} />
        <section className="algorithm-period" aria-labelledby="algorithm-period-title"><header><div><span className="eyebrow">Algorithm period</span><h2 id="algorithm-period-title">Scoped evidence</h2></div></header><EvidenceCounts counts={combinedEvidence(sections).counts} /><p>{statistics?.available ? `${statistics.observations} trading returns · Evidence: ${statistics.observations >= 250 ? 'developing' : 'promising but immature'}.` : `? Insufficient — ${statistics?.reason || 'daily live algorithm observations are required'}`}</p></section>
        <SignalMetricsPanel report={signalMetrics} />
      </>}
      {view === 'historical' && <>
        <RollingSharpeChart statistics={statistics} />
        <AnalyticsSection id="historical-risk" eyebrow="Historical" title="Risk and performance" metrics={model.standard} summary={sections[0].summary} sampleNote={sample} />
        <AnalyticsSection id="historical-comparison" eyebrow="Historical" title={`Versus the ${benchmarkLabel}`} metrics={model.comparison} summary={sections[1].summary} sampleNote={sample} />
      </>}
    </div>
  )
}
