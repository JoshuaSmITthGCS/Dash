import { useMemo, useState } from 'react'
import { ScreenNavigation } from './ResearchScreen'
import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import ResultCards from '../components/ResultCards.jsx'

const percent = (value, digits = 2) => value == null ? '—' : `${Number(value).toFixed(digits)}%`
const rate = (value) => value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`
const number = (value, digits = 2) => value == null ? '—' : Number(value).toFixed(digits)
const count = (value) => value == null ? '—' : Number(value).toLocaleString()

const windowLabel = (row) => row.window_start && row.window_end
  ? `${row.window_start} → ${row.window_end}`
  : 'No measured window'

// Order matters: the groups a reader is most likely to be choosing between come first, and
// the ranking diagnostics last, because they are the ones most easily misread as returns.
const GROUP_ORDER = ['held_portfolio', 'contribution_flows', 'option_trades', 'rank_quality']

const GROUP_TITLES = {
  held_portfolio: 'Held portfolios',
  contribution_flows: 'Portfolios with ongoing contributions',
  option_trades: 'Option strategies',
  rank_quality: 'Ranking quality (not a portfolio return)',
}

// A success rate only means something next to its definition, and the three definitions in
// this payload are not interchangeable - a 33% option win rate and a 33% monthly-period win
// rate describe completely different situations. The basis is therefore rendered as a column
// on every row rather than explained once in a footnote the reader has already scrolled past.
const BASIS_LABELS = {
  rebalance_periods_positive: 'periods positive',
  trades_profitable: 'trades profitable',
  periods_with_positive_ic: 'periods ranked correctly',
  not_measurable_with_contribution_flows: 'not measurable',
}

const statusLabel = (row) => {
  if (row.status === 'measured') return null
  if (row.status === 'unavailable') return 'Not yet run'
  return 'Insufficient history'
}

function SuccessCell({ row }) {
  if (row.success_rate == null) {
    return <span className="backtest-success none">{row.periods_in_cash
      ? `Held cash in ${row.periods_in_cash} of ${row.periods_in_cash + (row.periods_measured || 0)} periods`
      : '—'}</span>
  }
  return <span className="backtest-success"><b>{rate(row.success_rate)}</b>
    <small>{BASIS_LABELS[row.success_rate_basis] || row.success_rate_basis}</small></span>
}

function MethodTable({ rows, group }) {
  const portfolioLike = group === 'held_portfolio' || group === 'contribution_flows'
  return <div className="research-table card backtest-compare-table"><table>
    <thead><tr>
      <th>Method</th>
      <th className="num">Success rate</th>
      {portfolioLike && <th className="num">Beat SPY</th>}
      <th className="num">Total return</th>
      {portfolioLike && <th className="num">vs SPY</th>}
      <th className="num">{group === 'rank_quality' ? 'Mean IC' : 'CAGR'}</th>
      <th className="num">Sharpe</th>
      <th className="num">Max drawdown</th>
      <th className="num">Observations</th>
      <th>Window</th>
    </tr></thead>
    <tbody>{rows.map((row) => <tr key={row.id}>
      <td><b>{row.label}</b>
        {statusLabel(row) && <small className="backtest-status-flag">{statusLabel(row)}</small>}
        <small className="backtest-features">{(row.features || []).join(' · ')}</small></td>
      <td className="num"><SuccessCell row={row} /></td>
      {portfolioLike && <td className="num">{rate(row.beat_benchmark_rate)}</td>}
      <td className="num">{percent(row.total_return_pct)}</td>
      {portfolioLike && <td className="num">{row.excess_return_pct == null ? '—'
        : <span className={row.excess_return_pct >= 0 ? 'pos' : 'neg'}>{percent(row.excess_return_pct)}</span>}</td>}
      <td className="num">{group === 'rank_quality' ? number(row.mean_ic, 4) : percent(row.cagr_pct)}</td>
      <td className="num">{number(row.sharpe ?? row.deflated_sharpe, 3)}</td>
      <td className="num">{percent(row.max_drawdown_pct)}</td>
      <td className="num">{count(row.periods_measured)}</td>
      <td><small className="shadow-window">{windowLabel(row)}</small></td>
    </tr>)}</tbody>
  </table></div>
}

export default function BacktestComparison() {
  const { data, loading, error } = useData('screens/backtest-comparison.json')
  const [showCaveats, setShowCaveats] = useState(false)
  const methods = useMemo(() => data?.methods || [], [data])

  const groups = useMemo(() => {
    const bucketed = new Map()
    methods.forEach((row) => {
      const key = row.comparable_group || 'other'
      if (!bucketed.has(key)) bucketed.set(key, [])
      bucketed.get(key).push(row)
    })
    // Inside a group the rows are genuinely rankable, so they are sorted by success rate.
    // Across groups they are not, which is why sorting happens here and never on the flat list.
    //
    // Anything not fully measured sorts to the bottom whatever its rate: the political and
    // institutional strategy currently scores a 100% success rate off a single non-cash
    // period, which put it at the top of the table ahead of a five-year result. A rate
    // computed from one observation is not a better rate, and position on a ranked table
    // reads as a claim no matter what the status chip next to it says.
    bucketed.forEach((rows) => rows.sort((a, b) => {
      const ranked = (row) => row.status === 'measured' && row.success_rate != null
      if (ranked(a) !== ranked(b)) return ranked(a) ? -1 : 1
      if (!ranked(a)) return (a.label || '').localeCompare(b.label || '')
      return b.success_rate - a.success_rate
    }))
    return GROUP_ORDER.filter((key) => bucketed.has(key)).map((key) => [key, bucketed.get(key)])
  }, [methods])

  if (loading) return <><ScreenNavigation /><Loading /></>

  const measured = methods.filter((row) => row.status === 'measured')
  const rollup = data?.feature_rollup || []
  const caveats = methods.filter((row) => (row.caveats || []).length)

  return <><ScreenNavigation />
    <div className="page-head"><div><span className="eyebrow">Retrospective evidence</span>
      <h1 className="page-title">Backtest comparison</h1>
      <p className="page-sub">Every method this app can trade, measured against the others on
        the same terms — and labelled where those terms stop being the same.</p></div>
      <div className="result-count"><strong>{measured.length}</strong><span>measured</span></div></div>

    {error ? <div className="card etf-state" role="alert"><strong>Backtest comparison unavailable</strong>
      <span>{error.message}</span></div> : <>

      <section className="shadow-validation-summary" aria-label="Backtest coverage">
        <article><span>Methods measured</span><strong>{measured.length}</strong>
          <small>of {data?.methods_total ?? 0} backtests wired up</small></article>
        <article><span>Comparable groups</span><strong>{groups.length}</strong>
          <small>success rates rank only within a group</small></article>
        <article><span>Features tracked</span><strong>{new Set(rollup.map((row) => row.feature)).size}</strong>
          <small>declared inputs across all methods</small></article>
        <article><span>Generated</span><strong>{(data?.generated_at || '').slice(0, 10) || '—'}</strong>
          <small>from result files on disk</small></article>
      </section>

      <p className="disclaimer" role="note">{data?.interpretation}</p>

      {groups.map(([group, rows]) => <section key={group} className="backtest-compare-group">
        <h2 className="section-title">{GROUP_TITLES[group] || group}</h2>
        <p className="backtest-group-note">{data?.comparable_groups?.[group]}</p>
        <ResultCards rows={rows} getKey={(row) => row.id}
          title={(row) => row.label}
          subtitle={(row) => statusLabel(row) || (row.features || []).join(' · ')}
          fields={[
            { label: 'Success rate', value: (row) => row.success_rate == null ? '—'
              : `${rate(row.success_rate)} (${BASIS_LABELS[row.success_rate_basis] || row.success_rate_basis})` },
            { label: 'Beat SPY', value: (row) => rate(row.beat_benchmark_rate), hideEmpty: true },
            { label: 'Total return', value: (row) => percent(row.total_return_pct) },
            { label: 'vs SPY', value: (row) => percent(row.excess_return_pct), hideEmpty: true },
            { label: 'CAGR', value: (row) => percent(row.cagr_pct), hideEmpty: true },
            { label: 'Sharpe', value: (row) => number(row.sharpe ?? row.deflated_sharpe, 3) },
            { label: 'Max drawdown', value: (row) => percent(row.max_drawdown_pct) },
            { label: 'Observations', value: (row) => count(row.periods_measured) },
            { label: 'Window', value: windowLabel },
          ]} />
        <MethodTable rows={rows} group={group} />
      </section>)}

      <section className="backtest-compare-group">
        <h2 className="section-title">Success rate by feature</h2>
        <p className="backtest-group-note">Which inputs the higher-scoring methods happen to
          read. This is co-occurrence across methods, not attribution: methods share inputs and
          cover different windows, so use it to decide what to investigate, never as evidence
          that a feature caused a result.</p>
        <div className="research-table card backtest-compare-table"><table>
          <thead><tr><th>Feature</th><th className="num">Mean success rate</th>
            <th className="num">Range</th><th className="num">Methods</th>
            <th>Measured as</th><th>Methods reading it</th></tr></thead>
          <tbody>{rollup.map((row) => <tr key={`${row.feature}-${row.success_rate_basis}`}>
            <td><b>{row.feature}</b></td>
            <td className="num">{rate(row.mean_success_rate)}</td>
            <td className="num">{rate(row.minimum_success_rate)} – {rate(row.maximum_success_rate)}</td>
            <td className="num">{row.methods}</td>
            <td><span className="shadow-evidence-status">{BASIS_LABELS[row.success_rate_basis] || row.success_rate_basis}</span></td>
            <td><small className="backtest-features">{(row.method_labels || []).join(' · ')}</small></td>
          </tr>)}</tbody>
        </table></div>
        {!rollup.length && <p className="backtest-group-note">No method has published a success
          rate yet, so there is nothing to roll up.</p>}
      </section>

      {caveats.length > 0 && <section className="backtest-compare-group">
        <button className="expand-button" aria-expanded={showCaveats}
          onClick={() => setShowCaveats((value) => !value)}>
          {showCaveats ? 'Hide' : 'Show'} what each backtest cannot measure ({caveats.length} methods)
        </button>
        {showCaveats && <div className="card backtest-caveat-list">{caveats.map((row) => <div key={row.id}>
          <strong>{row.label}</strong>
          {row.status_detail && <p className="backtest-status-detail">{row.status_detail}</p>}
          <ul>{row.caveats.map((note) => <li key={note}>{note}</li>)}</ul>
          <small className="shadow-window">Source: {row.source}</small>
        </div>)}</div>}
      </section>}
    </>}

    <p className="disclaimer">Every figure here is retrospective and simulated. A backtest is
      evidence about the past under its own stated assumptions, not a forecast, and the
      strategies with the shortest windows are the ones most easily misread — check the
      observation count and the window before comparing anything. Prospective, forward-only
      results are on the shadow portfolios screen, and those are the ones that govern whether
      a strategy is ever promoted.</p>
  </>
}
