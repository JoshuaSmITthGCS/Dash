function ratio(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : value.toFixed(2)
}

function percent(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : `${value.toFixed(1)}%`
}

export function performanceMetricTone(key, value) {
  if (value == null || !Number.isFinite(value)) return 'unavailable'
  const thresholds = modelSettings.portfolio_analytics.performance_metric_tones[key]
  if (!thresholds) return 'neutral'
  if (value >= thresholds.good_min) return 'positive'
  if (value <= thresholds.bad_max) return 'negative'
  return 'neutral'
}

function Metric({ name, label, value, format, note }) {
  const tone = performanceMetricTone(name, value)
  const glyph = tone === 'positive' ? '▲' : tone === 'negative' ? '▼' : tone === 'neutral' ? '●' : ''
  return <article className={`metric-tone-${tone}`}><span>{label}</span><strong>{glyph && <i aria-hidden="true">{glyph}</i>}{format(value)}</strong><small>{note}</small></article>
}

function sigma(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}σ`
}

export default function PerformanceMetrics({ metrics, benchmarkLabel = 'benchmark', riskFree, acceleration = null }) {
  return (
    <section className="performance-metrics" aria-labelledby="standard-performance-title">
      <header><div><span className="eyebrow">Standard measures</span><h2 id="standard-performance-title">Risk and performance</h2></div><small>{metrics?.available ? `${metrics.observations} daily returns` : metrics?.reason}</small></header>
      <div>
        {/* Every other tile here reports a level. This one reports the change in it: whether
            the gap against the benchmark is still widening. See src/lib/portfolioAcceleration.js. */}
        <Metric
          name="acceleration"
          label={`Acceleration vs ${benchmarkLabel}`}
          value={acceleration?.available ? acceleration.acceleration : null}
          format={sigma}
          note={acceleration?.available
            ? `${accelerationLabel(acceleration)} · ${acceleration.recentExcessPct >= 0 ? '+' : '−'}${Math.abs(acceleration.recentExcessPct).toFixed(1)}% this quarter vs ${acceleration.priorExcessPct >= 0 ? '+' : '−'}${Math.abs(acceleration.priorExcessPct).toFixed(1)}% last, beta-adjusted`
            : acceleration?.reason || 'Needs two quarters against the benchmark'}
        />
        <Metric name="informationRatio" label="Information ratio" value={metrics?.informationRatio} format={ratio} note={`Versus ${benchmarkLabel}`} />
        <Metric name="sharpe" label="Sharpe ratio" value={metrics?.sharpe} format={ratio} note={`${riskFree?.fallback ? 'Configured fallback' : riskFree?.series} ${riskFree?.annualPct?.toFixed(2) ?? '0.00'}%`} />
        <Metric name="sortino" label="Sortino ratio" value={metrics?.sortino} format={ratio} note="Downside risk only" />
        <Metric name="calmar" label="Calmar ratio" value={metrics?.calmar} format={ratio} note="Return per drawdown" />
        <Metric name="maxDrawdown" label="Maximum drawdown" value={metrics?.maxDrawdown} format={percent} note="Worst peak decline" />
        <Metric name="currentDrawdown" label="Current drawdown" value={metrics?.currentDrawdown} format={percent} note="From high-water mark" />
      </div>
    </section>
  )
}
import modelSettings from '../../pipeline/config/settings.json'
import { accelerationLabel } from '../lib/portfolioAcceleration.js'
