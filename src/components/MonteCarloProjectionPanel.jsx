import { useState } from 'react'

const HORIZON_ORDER = ['30', '90', '180', '365']
const HORIZON_LABEL = { 30: '30 days', 90: '90 days', 180: '180 days', 365: '365 days' }
const PERCENTILE_ORDER = ['p5', 'p25', 'p50', 'p75', 'p95']
const PERCENTILE_LABEL = { p5: '5th', p25: '25th', p50: 'Median', p75: '75th', p95: '95th' }

const signedPct = (value, digits = 1) => value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
const probability = (value) => value == null ? '–' : `${Math.round(value * 100)}%`

/** Period return implied by a terminal-value multiple, e.g. 1.05 -> +5.0%. */
function periodReturnPct(multiple) {
  return multiple == null ? null : (multiple - 1) * 100
}

function HorizonPicker({ horizons, selected, onSelect }) {
  return (
    <div className="mc-horizon-picker" role="tablist" aria-label="Projection horizon">
      {HORIZON_ORDER.filter((days) => horizons[days]).map((days) => (
        <button
          key={days}
          type="button"
          role="tab"
          aria-selected={selected === days}
          className={selected === days ? 'active' : ''}
          onClick={() => onSelect(days)}
        >
          {HORIZON_LABEL[days]}
        </button>
      ))}
    </div>
  )
}

function PercentileTable({ summary }) {
  const terminal = summary.terminal_multiple_percentiles || {}
  const annualized = summary.annualized_return_percentiles_pct || {}
  return (
    <div className="mc-percentile-table" role="table" aria-label="Outcome distribution by percentile">
      <div className="mc-percentile-row mc-percentile-head" role="row">
        <span role="columnheader">Percentile</span>
        <span role="columnheader">Return over {summary.trading_days} trading days</span>
        <span role="columnheader">Annualized equivalent</span>
      </div>
      {PERCENTILE_ORDER.map((key) => (
        <div className={`mc-percentile-row${key === 'p50' ? ' median' : ''}`} role="row" key={key}>
          <span role="cell">{PERCENTILE_LABEL[key]}</span>
          <span role="cell" className="mc-mono">{signedPct(periodReturnPct(terminal[key]))}</span>
          <span role="cell" className="mc-mono">{signedPct(annualized[key])}</span>
        </div>
      ))}
    </div>
  )
}

function HorizonSummary({ summary, currentMaxDrawdownPct }) {
  const meanPeriodReturn = periodReturnPct(summary.mean_terminal_multiple)
  return (
    <div className="mc-horizon-summary">
      <div className="mc-headline">
        <div>
          <span className="eyebrow">Monte Carlo average</span>
          <strong className="mc-headline-value">{signedPct(meanPeriodReturn)}</strong>
          <small>over {summary.trading_days} simulated trading days ({summary.mean_annualized_return_pct >= 0 ? '+' : ''}{summary.mean_annualized_return_pct.toFixed(1)}%/yr annualized)</small>
        </div>
        <div>
          <span className="eyebrow">Confidence band width (annualized)</span>
          <strong className="mc-headline-value mc-band">{summary.confidence_band_width_pct.toFixed(0)}pp</strong>
          <small>5th-to-95th percentile spread. Wider is less certain, not less likely to be right.</small>
        </div>
        <div>
          <span className="eyebrow">P(drawdown beyond current worst)</span>
          <strong className="mc-headline-value">{probability(summary.probability_drawdown_exceeds_current_max)}</strong>
          <small>chance a simulated path falls further than the {signedPct(currentMaxDrawdownPct, 1)} already lived through</small>
        </div>
      </div>
      <PercentileTable summary={summary} />
    </div>
  )
}

function LiveComparison({ comparison, selected }) {
  if (!comparison) return null
  const row = comparison.shift_by_horizon?.[selected]
  if (!row) return null
  return (
    <div className={`mc-live-comparison${comparison.material_shift ? ' material' : ''}`}>
      <strong>{comparison.material_shift ? 'Material shift once live data is long enough to project from' : 'Live sample cross-check'}</strong>
      <p>
        The production shadow sample has reached {comparison.observations} observations - long enough to project from on its own.
        Backtest-based mean: {signedPct(row.backtest_mean_annualized_return_pct)}/yr. Live-based mean: {signedPct(row.live_mean_annualized_return_pct)}/yr
        {' '}({Math.round(row.relative_shift * 100)}% relative difference{comparison.material_shift ? `, above the ${Math.round(comparison.material_shift_threshold * 100)}% flag threshold` : ''}).
      </p>
    </div>
  )
}

/**
 * Monte Carlo forward projection: a prediction, not a read-out of the past.
 *
 * Deliberately separate from SignalMetricsPanel, which grades what already happened. This
 * panel is the one place on the metrics page that looks forward, and it says so on every
 * screen: the disclosure banner is not a footnote, and the headline number never appears
 * without the percentile band that gives it context.
 */
export default function MonteCarloProjectionPanel({ report, error }) {
  const horizons = report?.horizons || {}
  const defaultHorizon = HORIZON_ORDER.find((days) => horizons[days]) || '90'
  const [selected, setSelected] = useState(defaultHorizon)

  if (error || !report) {
    return (
      <section className="card etf-state mc-projection-empty" role={error ? 'alert' : undefined}>
        <strong>Monte Carlo projection unavailable</strong>
        <span>Run <code>python pipeline/monte_carlo_projection.py</code> to publish the artifact.{error ? ` ${error.message}` : ''}</span>
      </section>
    )
  }

  if (report.status === 'insufficient_data') {
    return (
      <section className="card etf-state mc-projection-empty" role="status">
        <strong>Not enough history to project forward yet</strong>
        <span>{report.status_message}</span>
      </section>
    )
  }

  const summary = horizons[selected]
  const input = report.input || {}

  return (
    <section className="mc-projection" aria-labelledby="mc-projection-title">
      <header className="section-heading">
        <div>
          <span className="eyebrow">Future simulations</span>
          <h2 id="mc-projection-title">Where could this go from here?</h2>
          <p>
            {input.paths?.toLocaleString()} simulated paths per horizon, block-bootstrapped from{' '}
            {input.source === 'backtest_daily_returns' ? 'the backtest daily return history' : 'the live production return sample'}{' '}
            ({input.observations} observations, {input.block_size_days}-day blocks
            {input.method === 'block_bootstrap_current_sample' ? ' - still a thin sample, read this as directional' : ''}).
          </p>
        </div>
      </header>

      <div className="mc-disclosure" role="note">
        {report.disclosure}
      </div>

      <HorizonPicker horizons={horizons} selected={selected} onSelect={setSelected} />
      {summary && (
        <HorizonSummary summary={summary} currentMaxDrawdownPct={input.current_max_drawdown_pct} />
      )}
      <LiveComparison comparison={report.live_comparison} selected={selected} />
    </section>
  )
}
