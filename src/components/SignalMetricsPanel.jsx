import { useState } from 'react'
import {
  defaultOpenGroups,
  isRead,
  liveSampleNote,
  metricTone,
  metricValueText,
  sampleProgress,
  sharedStatusMessage,
  splitBySampleRequirement,
  statusLabel,
} from '../lib/signalMetrics'

// A reading longer than this stops being a number and becomes a line of text; sitting it in
// the narrow right-hand column would squeeze the label rather than show it.
const INLINE_VALUE_LIMIT = 24

const METRIC_TOOLTIPS = {
  rank_ic: 'Rank IC is the Spearman correlation between model ranks and later returns at the named horizon. Positive values mean higher-ranked securities subsequently performed better.',
  icir: 'ICIR divides the mean rank IC by its variability and scales it for the observation cadence. Higher values indicate a more consistent cross-sectional ranking signal.',
  mfe: 'Maximum favorable excursion is the largest mark-to-market gain reached while a position was open. It describes opportunity captured or left unrealized; it is not the final trade return.',
  mae: 'Maximum adverse excursion is the largest mark-to-market loss reached while a position was open. Smaller adverse excursions generally indicate cleaner entries or tighter risk control.',
}

function metricTooltip(metric) {
  const id = String(metric.id || '').toLowerCase()
  return Object.entries(METRIC_TOOLTIPS).find(([key]) => id.includes(key))?.[1] || null
}

// A bullet chart, one per metric that publishes a real numeric threshold on the same
// scale as its value (see signal_metrics.py's kill_threshold_value/comparison — never
// derived from the prose kill_threshold, never fabricated for a metric that lacks one).
// aria-hidden because it repeats information the card already states in text: the value,
// the kill_threshold sentence, and the breached tone are all read independently of this bar.
function MetricBullet({ metric }) {
  if (metric.kill_threshold_value == null || !metric.comparison || typeof metric.value !== 'number') return null
  const { value, kill_threshold_value: threshold } = metric
  const low = Math.min(0, value, threshold)
  const high = Math.max(value, threshold, low + 0.0001) * 1.15
  const span = high - low || 1
  const pct = (point) => Math.max(0, Math.min(100, ((point - low) / span) * 100))
  return (
    <div className="signal-metric-bullet" aria-hidden="true">
      <span className="signal-metric-bullet-track">
        <i className="signal-metric-bullet-threshold" style={{ left: `${pct(threshold)}%` }} />
        <i className={`signal-metric-bullet-value${metric.breached ? ' breached' : ''}`} style={{ left: `${pct(value)}%` }} />
      </span>
    </div>
  )
}

function Metric({ metric, hideState = false }) {
  const tone = metricTone(metric)
  const progress = sampleProgress(metric)
  const text = metricValueText(metric)
  const wide = text.length > INLINE_VALUE_LIMIT
  const state = metric.status_message || progress
  const tooltip = metricTooltip(metric)
  return (
    <article className={`signal-metric tone-${tone}${wide ? ' wide-value' : ''}`}>
      <header>
        <div>
          <strong>{metric.label}</strong>
          {metric.reads && <small>{metric.reads}</small>}
        </div>
        <div className="signal-metric-value">
          {!wide && <b>{text}</b>}
          <span className={`chip signal-status-${tone}`}>{statusLabel(metric.status)}</span>
        </div>
      </header>
      {wide && <p className="signal-metric-wide">{text}</p>}
      <MetricBullet metric={metric} />
      {state && !hideState && <p className="signal-metric-state">{state}</p>}
      {metric.backtest_reference != null && (
        <p className="signal-metric-reference">
          Backtest reference {typeof metric.backtest_reference === 'number'
            ? metric.backtest_reference.toFixed(3)
            : metric.backtest_reference}. Not a live reading.
        </p>
      )}
      <footer>
        {metric.kill_threshold && (
          <span className={metric.breached ? 'signal-kill breached' : 'signal-kill'}>
            {metric.breached ? 'Breached: ' : 'Kill: '}{metric.kill_threshold}
          </span>
        )}
        {metric.cadence && <span className="signal-cadence">{metric.cadence}</span>}
        {tooltip && (
          <details className="metric-tooltip">
            <summary aria-label={`About ${metric.label}`}>What it measures</summary>
            <p>{tooltip}</p>
          </details>
        )}
      </footer>
    </article>
  )
}

function Group({ group, open, onToggle }) {
  const read = group.metrics.filter(isRead).length
  const breached = group.metrics.filter((metric) => metric.breached).length
  const shared = sharedStatusMessage(group.metrics)
  return (
    <details className="signal-group" open={open} onToggle={(event) => onToggle(group.id, event.currentTarget.open)}>
      <summary>
        <div>
          <span className="eyebrow">{group.letter}</span>
          <strong>{group.title}</strong>
          <small>{group.summary}</small>
        </div>
        <div className="signal-group-count">
          <b>{read}/{group.metrics.length}</b>
          {breached > 0 && <span className="chip signal-status-breached">{breached} breached</span>}
        </div>
      </summary>
      {shared && <p className="signal-group-note">{shared}</p>}
      <div className="signal-metric-grid">
        {group.metrics.map((metric) => (
          <Metric key={metric.id} metric={metric} hideState={Boolean(shared)} />
        ))}
      </div>
    </details>
  )
}

function Bucket({ bucket }) {
  const [open, setOpen] = useState(() => defaultOpenGroups(bucket))
  const toggle = (id, isOpen) => setOpen((current) => {
    const next = new Set(current)
    if (isOpen) next.add(id)
    else next.delete(id)
    return next
  })
  return (
    <section className="signal-bucket" aria-labelledby={`signal-bucket-${bucket.id}`}>
      <header className="section-heading">
        <div>
          <span className="eyebrow">{bucket.requiresLiveSample ? 'Waiting on data' : 'Available today'}</span>
          <h3 id={`signal-bucket-${bucket.id}`}>{bucket.title}</h3>
          <p>{bucket.subtitle}</p>
        </div>
        <div className="signal-bucket-count">
          <b>{bucket.read}/{bucket.total}</b>
          <small>reading</small>
        </div>
      </header>
      {bucket.groups.map((group) => (
        <Group key={group.id} group={group} open={open.has(group.id)} onToggle={toggle} />
      ))}
    </section>
  )
}

/**
 * Signal quality, split by what a live sample gates and what it does not.
 *
 * The reframe this panel exists to make: returns need years before they say anything, and
 * the account is eighteen days old. Rank IC, leg contribution and the overfitting statistics
 * are computable today on backtest data and are what actually say whether there is an edge
 * to start a clock on.
 */
export default function SignalMetricsPanel({ report, error }) {
  if (error || !report) {
    return (
      <section className="card etf-state signal-evidence-empty" role={error ? 'alert' : undefined}>
        <strong>Signal metrics unavailable</strong>
        <span>Run <code>python pipeline/signal_metrics.py</code> to publish the artifact.{error ? ` ${error.message}` : ''}</span>
      </section>
    )
  }
  const buckets = splitBySampleRequirement(report)
  const summary = report.summary || {}
  return (
    <section className="signal-evidence" aria-labelledby="signal-evidence-title">
      <header className="section-heading">
        <div>
          <span className="eyebrow">Model evidence</span>
          <h2 id="signal-evidence-title">Is there an edge to measure?</h2>
          <p>
            Returns need years before they say anything. IC gives a usable read on signal
            quality in weeks, on data that already exists. {liveSampleNote(report)}
          </p>
        </div>
        <div className="signal-evidence-summary">
          <span><b>{summary.sample_free_ready ?? 0}/{summary.sample_free_total ?? 0}</b><small>readable now</small></span>
          <span><b>{summary.needs_sample_total ?? 0}</b><small>awaiting sample</small></span>
          <span className={summary.breached ? 'breached' : ''}><b>{summary.breached ?? 0}</b><small>thresholds breached</small></span>
        </div>
      </header>
      {buckets.map((bucket) => <Bucket key={bucket.id} bucket={bucket} />)}
      <details className="signal-cadence-table">
        <summary>Review cadence</summary>
        <dl>
          {(report.cadence || []).map((row) => (
            <div key={row.frequency}><dt>{row.frequency}</dt><dd>{row.items}</dd></div>
          ))}
        </dl>
      </details>
    </section>
  )
}
