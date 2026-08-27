import DataTable from './DataTable.jsx'

/**
 * The evidence behind the Research Score, surfaced where a reader can act on it.
 *
 * A confident-looking "84" in the product with every caveat buried in pipeline JSON is an
 * asymmetry, not a design. This renders the committed research artifacts: how the strategy
 * compares to tradeable benchmarks, what factors explain its returns, what it costs to run,
 * and -- most importantly -- that no score bucket has enough closed forward windows to carry
 * an empirical meaning yet.
 *
 * Every panel reports "not generated" rather than defaulting, because "we did not measure
 * this" and "this measured zero" must not look the same.
 */

const pct = (value, digits = 1) =>
  value == null ? '–' : `${(Number(value) * 100).toFixed(digits)}%`
const signedPct = (value, digits = 1) =>
  value == null ? '–' : `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(digits)}%`
const num = (value, digits = 2) =>
  value == null ? '–' : Number(value).toFixed(digits)
const title = (value = '') =>
  String(value).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

function NotGenerated({ panel, name }) {
  return <div className="evidence-empty" role="note">
    <strong>{name} not generated</strong>
    <span>{panel?.reason || 'This report has not been built in this checkout.'}</span>
  </div>
}

/** The single most important thing on the page: what the score does and does not claim. */
export function ScoreInterpretation({ headline }) {
  if (!headline) return null
  const calibrated = headline.validation_status === 'calibrated'
  return <section className="card evidence-headline">
    <header className="section-heading">
      <div><span className="eyebrow">How to read a score</span>
        <h2>Research Score is a rank, not a probability</h2></div>
      <span className={`chip validation-${calibrated ? 'pass' : 'accumulating'}`}>
        {calibrated ? 'Calibrated' : 'Historical calibration: insufficient data'}
      </span>
    </header>
    <p className="evidence-note">{headline.score_is_not_a_probability}</p>
    <dl className="analysis-quality-grid">
      <div><dt>Forecast target</dt>
        <dd>{headline.forecast_target?.primary_horizon_sessions
          ? `${headline.forecast_target.primary_horizon_sessions}-session sector-residual return`
          : 'Not configured'}</dd></div>
      <div><dt>Point-in-time periods</dt>
        <dd>{headline.ic_periods_accumulated ?? 0} of {headline.ic_periods_required ?? 24}</dd></div>
      <div><dt>Calibration</dt>
        <dd>{calibrated ? 'Available' : 'Insufficient data'}</dd></div>
    </dl>
  </section>
}

export function BenchmarkPanel({ panel }) {
  if (!panel || panel.status !== 'measured') {
    return <NotGenerated panel={panel} name="Benchmark comparison" />
  }
  const strategy = panel.strategy || {}
  const rows = [
    {
      key: '__self__', name: 'ValueSignal', cagr: strategy.cagr, volatility: strategy.volatility,
      sharpe: strategy.sharpe, max_drawdown: strategy.max_drawdown,
      beta: null, annualized_alpha_pct: null, newey_west_t_statistic: null, significant: false, isSelf: true,
    },
    ...panel.rows.map((row) => ({ key: row.name, ...row })),
  ]
  const columns = [
    { key: 'name', label: 'Benchmark', sortable: false, rowHeader: true, cell: (row) => <span title={row.description}>{row.name}</span> },
    { key: 'cagr', label: 'CAGR', sortable: false, cell: (row) => pct(row.cagr, 2) },
    { key: 'volatility', label: 'Vol', sortable: false, cell: (row) => pct(row.volatility, 2) },
    { key: 'sharpe', label: 'Sharpe', sortable: false, cell: (row) => num(row.sharpe, 3) },
    { key: 'max_drawdown', label: 'Max DD', sortable: false, cell: (row) => pct(row.max_drawdown, 2) },
    { key: 'beta', label: 'Beta', sortable: false, cell: (row) => (row.isSelf ? '–' : num(row.beta)) },
    {
      key: 'annualized_alpha_pct', label: 'Alpha', sortable: false,
      cell: (row) => (row.isSelf ? '–' : row.annualized_alpha_pct == null ? '–' : `${row.annualized_alpha_pct > 0 ? '+' : ''}${num(row.annualized_alpha_pct)}%`),
    },
    {
      key: 'newey_west_t_statistic', label: 'NW t', sortable: false,
      cell: (row) => (row.isSelf ? '–' : <span className={row.significant ? 'evidence-significant' : undefined}>{num(row.newey_west_t_statistic)}</span>),
    },
  ]
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">Could an ETF have done this?</span>
        <h2>Benchmark comparison</h2>
        <p>Each leg is buy-and-hold from the strategy&apos;s own start date with one entry cost,
          then a Newey-West regression of the strategy on that benchmark.</p></div>
      <span className="chip">{panel.summary?.beaten_on_cagr_count} beaten on CAGR</span>
    </header>
    <div className="evidence-table-scroll" tabIndex={0}>
      <DataTable
        className="evidence-table"
        rows={rows}
        getKey={(row) => row.key}
        columns={columns}
        rowClassName={(row) => (row.isSelf ? 'evidence-row-self' : undefined)}
      />
    </div>
    <p className="evidence-note evidence-disclosure">
      {panel.summary?.honesty_disclosure || panel.summary?.verdict}
    </p>
  </section>
}

export function FactorPanel({ panel }) {
  if (!panel || panel.status !== 'measured') {
    return <NotGenerated panel={panel} name="Factor exposures" />
  }
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">What explains the returns</span>
        <h2>Factor exposures</h2>
        <p>Six-factor regression with Newey-West standard errors over {panel.months} months.
          R² {num(panel.r_squared)}.</p></div>
    </header>
    <ul className="evidence-loadings">
      {panel.loadings.map((loading) => <li key={loading.factor}>
        <span>{title(loading.factor)}</span>
        <b>{num(loading.estimate, 3)}</b>
        <small className={loading.significant ? 'evidence-significant' : undefined}>
          t {num(loading.newey_west_t_statistic)}
          {loading.significant ? ' · significant' : ''}
        </small>
      </li>)}
    </ul>
  </section>
}

export function DiagnosticsPanel({ panel }) {
  if (!panel || panel.status !== 'measured') {
    return <NotGenerated panel={panel} name="Strategy diagnostics" />
  }
  const expectancy = panel.expectancy || {}
  const turnoverAdjusted = panel.turnover_adjusted_return || {}
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">Trade shape</span><h2>Strategy diagnostics</h2>
        <p>{panel.unit_of_account?.trade
          ? `One observation is ${panel.unit_of_account.trade}.`
          : null} {panel.sample?.first} to {panel.sample?.last}.</p></div>
    </header>
    <dl className="analysis-quality-grid">
      <div><dt>Win rate</dt><dd>{pct(expectancy.win_rate)}</dd></div>
      <div><dt>Average win</dt><dd>{signedPct(expectancy.average_win, 2)}</dd></div>
      <div><dt>Average loss</dt><dd>−{pct(expectancy.average_loss, 2)}</dd></div>
      <div><dt>Payoff ratio</dt><dd>{num(expectancy.payoff_ratio, 3)}</dd></div>
      <div><dt>Expectancy / month</dt><dd>{signedPct(expectancy.expectancy_per_period, 2)}</dd></div>
      <div><dt>Profit factor</dt><dd>{num(panel.profit_factor?.profit_factor, 3)}</dd></div>
      <div><dt>Longest losing streak</dt><dd>{panel.streaks?.longest_losing_streak ?? '–'} months</dd></div>
      <div><dt>Monthly turnover</dt><dd>{pct(panel.turnover?.mean_monthly_turnover)}</dd></div>
      <div><dt>Cost share of gross</dt>
        <dd>{pct(turnoverAdjusted.share_of_gross_return_consumed_by_costs)}</dd></div>
    </dl>
    {panel.regime_attribution ? <details className="evidence-details">
      <summary>Performance by regime</summary>
      <p className="evidence-note">{panel.regime_definitions?.preregistration}</p>
      {Object.entries(panel.regime_attribution).map(([family, buckets]) => <div key={family}>
        <b>{title(family)}</b>
        <ul className="evidence-regimes">
          {Object.entries(buckets).map(([label, block]) => <li key={label}>
            <span>{title(label)}</span>
            <b>{signedPct(block.strategy_annualized)}</b>
            <small>vs {signedPct(block.benchmark_annualized)} · n={block.months}</small>
          </li>)}
        </ul>
      </div>)}
    </details> : null}
  </section>
}

export function CostPanel({ panel }) {
  if (!panel || panel.status !== 'measured') {
    return <NotGenerated panel={panel} name="Cost sensitivity" />
  }
  const flat = panel.realized_flat_10bps || {}
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">What turnover costs</span><h2>Cost sensitivity</h2>
        <p>The published backtest charges a flat 10bps one-way. These re-price its own
          recorded turnover at each rate the cost model can produce.</p></div>
    </header>
    <dl className="analysis-quality-grid">
      <div><dt>Mean monthly turnover</dt><dd>{pct(panel.turnover?.mean_turnover)}</dd></div>
      <div><dt>Rebalances</dt><dd>{panel.turnover?.rebalances ?? '–'}</dd></div>
      <div><dt>Published CAGR at 10bps</dt><dd>{pct(flat.cagr, 2)}</dd></div>
    </dl>
    <div className="evidence-table-scroll" tabIndex={0}>
      <DataTable
        className="evidence-table"
        rows={panel.scenarios || []}
        getKey={(row) => row.scenario}
        columns={[
          { key: 'scenario', label: 'Scenario', sortable: false, rowHeader: true, cell: (row) => title(row.scenario) },
          { key: 'cost_bps', label: 'One-way', sortable: false, cell: (row) => `${num(row.cost_bps, 2)} bps` },
          { key: 'total_cost', label: 'Total cost', sortable: false, cell: (row) => (row.total_cost == null ? '–' : `$${Math.round(row.total_cost).toLocaleString()}`) },
          {
            key: 'drag_vs_realized_flat', label: 'vs flat 10bps', sortable: false,
            cell: (row) => (row.drag_vs_realized_flat == null ? '–' : `${row.drag_vs_realized_flat > 0 ? '+' : ''}$${Math.round(row.drag_vs_realized_flat).toLocaleString()}`),
          },
        ]}
      />
    </div>
    <p className="evidence-note">{panel.never_present_gross_as_net}</p>
  </section>
}

export function CalibrationPanel({ panel }) {
  if (!panel) return <NotGenerated panel={panel} name="Score calibration" />
  const measured = panel.status === 'measured'
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">What a score has historically meant</span>
        <h2>Score calibration</h2></div>
      <span className={`chip validation-${measured ? 'pass' : 'accumulating'}`}>
        {measured ? 'Measured' : 'Insufficient data'}
      </span>
    </header>
    {measured
      ? <div className="evidence-table-scroll" tabIndex={0}>
        <DataTable
          className="evidence-table"
          rows={panel.fixed_score_bands.filter((band) => band.status === 'measured')}
          getKey={(row) => row.bucket}
          columns={[
            { key: 'bucket', label: 'Score band', sortable: false, rowHeader: true, cell: (row) => row.bucket },
            { key: 'observations', label: 'n', sortable: false, cell: (row) => row.observations },
            { key: 'median_residual_return', label: 'Median residual', sortable: false, cell: (row) => signedPct(row.median_residual_return) },
            { key: 'beat_sector_rate', label: 'Beat sector', sortable: false, cell: (row) => pct(row.beat_sector_rate) },
          ]}
        />
      </div>
      : <p className="evidence-note">
        No score bucket has enough closed forward windows to report an outcome distribution.
        Nothing is shown rather than an estimate, because an invented calibration would turn an
        admitted unknown into a false claim. {panel.what_would_populate_this}
      </p>}
  </section>
}

export function ExperimentPanel({ panel }) {
  if (!panel || panel.status !== 'measured') {
    return <NotGenerated panel={panel} name="Experiment registry" />
  }
  const summary = panel.summary || {}
  return <section className="card evidence-panel">
    <header className="section-heading">
      <div><span className="eyebrow">What has been tried</span><h2>Experiment registry</h2>
        <p>{summary.experiments} experiments, {summary.total_variants_tested} variants.
          Failures are recorded, not omitted.</p></div>
      <span className="chip">{(summary.promoted_to_champion || []).length} promoted</span>
    </header>
    <ul className="evidence-experiments">
      {panel.experiments.map((item) => <li key={item.id}>
        <div><b>{item.id}</b>
          <span className={`chip validation-${item.result === 'supported' ? 'pass' : 'accumulating'}`}>
            {title(item.result)}</span></div>
        <p>{item.hypothesis}</p>
        <small>{title(item.decision)} · {item.reason}</small>
      </li>)}
    </ul>
  </section>
}

export default function ResearchEvidence({ data, error }) {
  if (error) {
    return <section className="card etf-state" role="alert">
      <strong>Research evidence unavailable</strong>
      <span>Run pipeline/build_research_evidence.py. {error.message}</span>
    </section>
  }
  if (!data) return null
  return <div className="evidence-stack">
    <ScoreInterpretation headline={data.headline} />
    <CalibrationPanel panel={data.calibration} />
    <BenchmarkPanel panel={data.benchmarks} />
    <FactorPanel panel={data.factor_exposures} />
    <DiagnosticsPanel panel={data.strategy_diagnostics} />
    <CostPanel panel={data.costs} />
    <ExperimentPanel panel={data.experiments} />
    <p className="ic-integrity-note">
      Model {data.model_version || 'unknown'} · commit {(data.code_commit_hash || '').slice(0, 8)}
    </p>
  </div>
}
