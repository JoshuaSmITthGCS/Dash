function ratio(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : value.toFixed(2)
}

function percent(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : `${value.toFixed(1)}%`
}

function sigma(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}σ`
}

function signedPercent(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}%`
}

function days(value) {
  if (value == null || !Number.isFinite(value)) return 'Unavailable'
  if (value < 60) return `${Math.round(value)}d`
  const months = value / 30.44
  return months < 18 ? `${months.toFixed(1)}mo` : `${(value / 365.25).toFixed(1)}y`
}

export function performanceMetricTone(key, value) {
  if (value == null || !Number.isFinite(value)) return 'unavailable'
  const thresholds = modelSettings.portfolio_analytics.performance_metric_tones[key]
  if (!thresholds) return 'neutral'
  if (value >= thresholds.good_min) return 'positive'
  if (value <= thresholds.bad_max) return 'negative'
  return 'neutral'
}

/** `toneValue` lets a lower-is-better metric colour itself correctly without inverting what
 * it displays - the day counts below are better when small, and every tone bound in config
 * is read as higher-is-better. */
function Metric({ name, label, value, format, note, toneValue }) {
  const tone = performanceMetricTone(name, toneValue ?? value)
  const glyph = tone === 'positive' ? '▲' : tone === 'negative' ? '▼' : tone === 'neutral' ? '●' : ''
  return <article className={`metric-tone-${tone}`}><span>{label}</span><strong>{glyph && <i aria-hidden="true">{glyph}</i>}{format(value)}</strong><small>{note}</small></article>
}

/**
 * Two panels of six rather than one long strip, and the split is the point: the first answers
 * "what did this portfolio do to me", the second answers "how did it do against the index".
 * Information ratio sits in the second because it is a benchmark measure, not a standalone
 * risk one. Six tiles each also lands both grids exactly on their column count at every
 * breakpoint.
 */
export default function PerformanceMetrics({
  metrics, benchmarkLabel = 'benchmark', riskFree,
  acceleration = null, capture = null, batting = null, underwater = null,
}) {
  const captureNote = (side) => (capture?.available
    ? `${capture.observations[side]} ${side} periods · index ${side === 'up' ? '+' : ''}${capture[`${side}BenchmarkPct`].toFixed(1)}%`
    : capture?.reason || 'Needs history on both sides of the market')
  return (
    <>
      <section className="performance-metrics" aria-labelledby="standard-performance-title">
        <header><div><span className="eyebrow">Standard measures</span><h2 id="standard-performance-title">Risk and performance</h2></div><small>{metrics?.available ? `${metrics.observations} daily returns` : metrics?.reason}</small></header>
        <div>
          <Metric name="sharpe" label="Sharpe ratio" value={metrics?.sharpe} format={ratio} note={`${riskFree?.fallback ? 'Configured fallback' : riskFree?.series} ${riskFree?.annualPct?.toFixed(2) ?? '0.00'}%`} />
          <Metric name="sortino" label="Sortino ratio" value={metrics?.sortino} format={ratio} note="Downside risk only" />
          <Metric name="calmar" label="Calmar ratio" value={metrics?.calmar} format={ratio} note="Return per drawdown" />
          <Metric name="maxDrawdown" label="Maximum drawdown" value={metrics?.maxDrawdown} format={percent} note="Worst peak decline" />
          <Metric name="currentDrawdown" label="Current drawdown" value={metrics?.currentDrawdown} format={percent} note="From high-water mark" />
          {/* Depth is two tiles to the left. This is how long it lasted - the part that is
              underestimated in advance and felt most at the time. */}
          <Metric
            name="longestUnderwaterDays"
            label="Longest underwater"
            value={underwater?.available ? underwater.longestUnderwaterDays : null}
            toneValue={underwater?.available ? -underwater.longestUnderwaterDays : null}
            format={days}
            note={underwater?.available
              ? (underwater.stillUnderwater
                ? `Below its high since ${underwater.highWaterDate}`
                : `Recovered · at a high as of ${underwater.highWaterDate}`)
              : underwater?.reason || 'Needs dated portfolio values'}
          />
        </div>
      </section>

      <section className="performance-metrics" aria-labelledby="benchmark-comparison-title">
        <header><div><span className="eyebrow">Comparison</span><h2 id="benchmark-comparison-title">Versus the {benchmarkLabel}</h2></div><small>{batting?.available ? `${batting.months} months, ${batting.firstMonth} to ${batting.lastMonth}` : batting?.reason}</small></header>
        <div>
          {/* Level, then change: information ratio says how far ahead, acceleration says
              whether the gap is still widening. See src/lib/portfolioAcceleration.js. */}
          <Metric name="informationRatio" label="Information ratio" value={metrics?.informationRatio} format={ratio} note={`Excess return per unit of tracking risk`} />
          <Metric
            name="acceleration"
            label="Acceleration"
            value={acceleration?.available ? acceleration.acceleration : null}
            format={sigma}
            note={acceleration?.available
              ? `${accelerationLabel(acceleration)} · ${signedPercent(acceleration.recentExcessPct)} this quarter vs ${signedPercent(acceleration.priorExcessPct)} last, beta-adjusted`
              : acceleration?.reason || 'Needs two quarters against the benchmark'}
          />
          {/* Neither capture number is good or bad alone - a low up capture is the price of
              a low down capture. The spread beside them is what settles it. */}
          <Metric name="upCapture" label="Up capture" value={capture?.available ? capture.upCapturePct : null} format={percent} note={captureNote('up')} />
          <Metric name="downCapture" label="Down capture" value={capture?.available ? capture.downCapturePct : null} format={percent} note={captureNote('down')} />
          <Metric
            name="captureSpread"
            label="Capture spread"
            value={capture?.available ? capture.captureSpread : null}
            format={signedPercent}
            note={capture?.available
              ? (capture.captureSpread >= 0
                ? 'Keeping more of the upside than the downside'
                : 'Taking more of the downside than the upside')
              : capture?.reason || 'Needs history on both sides of the market'}
          />
          <Metric
            name="battingAveragePct"
            label="Batting average"
            value={batting?.available ? batting.battingAveragePct : null}
            format={percent}
            note={batting?.available
              ? `Beat the index in ${batting.wins} of ${batting.months} months${batting.winLossRatio ? ` · wins ${batting.winLossRatio.toFixed(1)}× the size of losses` : ''}`
              : batting?.reason || 'Needs six months of overlapping history'}
          />
        </div>
      </section>
    </>
  )
}
import modelSettings from '../../pipeline/config/settings.json'
import { accelerationLabel } from '../lib/portfolioAcceleration.js'
