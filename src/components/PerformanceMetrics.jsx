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

/**
 * The two numbers worth keeping visible while the panel is closed. Sharpe is the headline
 * risk-adjusted read and drawdown is the one that describes what holding it felt like;
 * collapsing the section should cost the reader neither.
 */
export function collapsedSummary(metrics) {
  if (!metrics?.available) return metrics?.reason || 'Unavailable'
  return `Sharpe ${ratio(metrics.sharpe)} · Max drawdown ${percent(metrics.maxDrawdown)}`
}

/** A short-horizon move only earns a colour once it clears its own noise floor. Inside the
 * floor it tones neutral at zero; with no reading at all it stays null so the tile reads as
 * unavailable rather than as a flat week. */
function shortTermTone(window) {
  if (!window?.available) return null
  return window.beyondNoise ? window.excessPct : 0
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
 * Three panels of six rather than one long strip, split by the question each answers: what
 * this portfolio did to you, how it did against the index over quarters and years, and what
 * it has done in the last few days and weeks. Information ratio sits in the second because
 * it is a benchmark measure, not a standalone risk one; active share sits in the third
 * because it needs no history at all. Six tiles each also lands every grid exactly on its
 * column count at all three breakpoints.
 *
 * The first panel is collapsed by default. These are the slowest-moving numbers here - a
 * Sharpe ratio does not change meaningfully between visits, and at this sample length it
 * cannot - so they keep their two headline readings in the summary line and give the
 * vertical space back to the panels that answer days and weeks.
 */
export default function PerformanceMetrics({
  metrics, benchmarkLabel = 'benchmark', riskFree,
  acceleration = null, capture = null, batting = null, underwater = null,
  shortTerm = null, risk = null, defaultOpen = false,
}) {
  const captureNote = (side) => (capture?.available
    ? `${capture.observations[side]} ${side} periods · index ${side === 'up' ? '+' : ''}${capture[`${side}BenchmarkPct`].toFixed(1)}%`
    : capture?.reason || 'Needs history on both sides of the market')
  const windowOf = (days) => shortTerm?.windows?.find((row) => row.days === days) || null
  const week = windowOf(7)
  const month = windowOf(30)
  return (
    <>
      <details className="performance-metrics" open={defaultOpen}>
        <summary aria-label="Standard risk and performance measures">
          <div><span className="eyebrow">Standard measures</span><h2 id="standard-performance-title">Risk and performance</h2></div>
          <div className="performance-metrics-preview"><b>{collapsedSummary(metrics)}</b><small>{metrics?.available ? `${metrics.observations} daily returns` : ''}</small></div>
        </summary>
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
      </details>

      <section className="performance-metrics" aria-labelledby="benchmark-comparison-title">
        <header><div><span className="eyebrow">Comparison</span><h2 id="benchmark-comparison-title">Versus the {benchmarkLabel}</h2></div><small>{batting?.available ? `${batting.months} months, ${batting.firstMonth} to ${batting.lastMonth}` : batting?.reason}</small></header>
        <div>
          {/* Level, then change: information ratio says how far ahead, acceleration says
              whether the gap is still widening. See src/lib/portfolioAcceleration.js. */}
          {/* Tracking error is the information ratio's own denominator, so it belongs in
              this tile rather than in one of its own. The Diversification page reports the
              same quantity built from holdings covariance instead of the value series. */}
          <Metric name="informationRatio" label="Information ratio" value={metrics?.informationRatio} format={ratio}
            note={risk?.trackingErrorPct != null
              ? `Excess return per unit of tracking risk · ${risk.trackingErrorPct.toFixed(1)}% tracking error`
              : 'Excess return per unit of tracking risk'} />
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

      {/* Everything above is gated behind quarters or years of history, correctly so for
          what it claims. This panel answers days and weeks, and answers them for an account
          too new for any of it. The price of a short window is noise, so each reading is
          published beside the noise floor that says whether it is a result or a wobble. */}
      <section className="performance-metrics" aria-labelledby="short-term-view-title">
        <header>
          <div><span className="eyebrow">Fast reads</span><h2 id="short-term-view-title">Short-term view</h2></div>
          <small>{shortTerm?.available ? shortTerm.methodology : shortTerm?.reason}</small>
        </header>
        <div>
          <Metric
            name="shortTermExcessPct"
            label="Past week vs index"
            value={week?.available ? week.excessPct : null}
            toneValue={shortTermTone(week)}
            format={signedPercent}
            note={week?.available
              ? `You ${signedPercent(week.portfolioPct)} · index ${signedPercent(week.benchmarkPct)}`
              : week?.reason || 'Not enough history yet'}
          />
          <Metric
            name="shortTermExcessPct"
            label="Past month vs index"
            value={month?.available ? month.excessPct : null}
            toneValue={shortTermTone(month)}
            format={signedPercent}
            note={month?.available
              ? `You ${signedPercent(month.portfolioPct)} · index ${signedPercent(month.benchmarkPct)}`
              : month?.reason || 'Not enough history yet'}
          />
          {/* The tile that keeps the two beside it honest. */}
          <Metric
            name="noiseFloor"
            label="Noise floor (month)"
            value={month?.available ? month.noiseFloorPct : null}
            format={(value) => `±${Math.abs(value).toFixed(1)}%`}
            note={month?.available ? shortTermVerdict(month) : 'Needs a tracking-noise estimate'}
          />
          <Metric
            name="streak"
            label="Current streak"
            value={shortTerm?.available ? shortTerm.streak.observations : null}
            format={(value) => `${Math.round(value)}`}
            note={shortTerm?.available
              ? `Periods ${shortTerm.streak.direction} of the index, spanning ${shortTerm.streak.days}d`
              : 'Needs two overlapping observations'}
          />
          <Metric
            name="recentTrackingRisk"
            label="Recent tracking risk"
            value={shortTerm?.available ? shortTerm.recentTrackingRiskPct : null}
            format={percent}
            note={shortTerm?.baselineTrackingRiskPct != null
              ? `Last 30 days annualized · ${shortTerm.baselineTrackingRiskPct.toFixed(1)}% baseline`
              : 'How far this portfolio moves independently of the index'}
          />
          {/* Needs no history at all - it is a fact about today's weights - which is why it
              belongs in the panel for readings that work immediately. */}
          <Metric
            name="activeShare"
            label="Active share"
            value={risk?.activeSharePct ?? null}
            format={percent}
            note={risk?.activeSharePct != null
              ? 'Share of the book that differs from the index right now'
              : 'Needs benchmark constituent coverage'}
          />
        </div>
      </section>
    </>
  )
}
import modelSettings from '../../pipeline/config/settings.json'
import { accelerationLabel } from '../lib/portfolioAcceleration.js'
import { shortTermVerdict } from '../lib/portfolioShortTermView.js'
