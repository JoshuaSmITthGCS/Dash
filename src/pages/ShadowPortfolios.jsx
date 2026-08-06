import { ScreenNavigation } from './ResearchScreen'
import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import ResultCards from '../components/ResultCards.jsx'

const metric = (value, suffix = '', row, minimum = 1) => {
  if (value != null) return `${Number(value).toFixed(2)}${suffix}`
  if (!row?.snapshots) return 'Not started'
  if (!row?.observations) return 'First return pending'
  return `${row.observations}/${minimum} returns`
}

const windowLabel = (row) => row.window_start && row.window_end
  ? `${row.window_start} → ${row.window_end}`
  : 'No matched window yet'

export default function ShadowPortfolios() {
  const { data, loading, error } = useData('screens/shadow-portfolios.json')
  if (loading) return <><ScreenNavigation /><Loading /></>
  const strategies = data?.strategies || []
  const live = strategies.filter((row) => row.observations > 0)
  const snapshots = strategies.reduce((total, row) => total + (row.snapshots || 0), 0)
  const dates = strategies.flatMap((row) => [row.window_start, row.window_end]).filter(Boolean).sort()
  const annualizedMinimum = Math.max(...strategies.map((row) => row.annualized_metrics_minimum_observations || 0), 20)
  return <><ScreenNavigation /><div className="page-head"><div><span className="eyebrow">Prospective validation</span>
    <h1 className="page-title">Shadow portfolio performance</h1><p className="page-sub">Immutable, net-of-cost observations. No strategy is promoted from implementation alone.</p></div></div>
    {error ? <div className="card etf-state" role="alert"><strong>Shadow results unavailable</strong><span>{error.message}</span></div> : <>
      <section className="shadow-validation-summary" aria-label="Shadow validation collection status">
        <article><span>Reporting now</span><strong>{live.length}</strong><small>strategies with matched returns</small></article>
        <article><span>Immutable snapshots</span><strong>{snapshots}</strong><small>first observation of each market date</small></article>
        <article><span>Matched window</span><strong>{dates.length ? `${dates[0].slice(5)} → ${dates.at(-1).slice(5)}` : 'Starting'}</strong><small>strict next-snapshot valuation</small></article>
        <article><span>Implementation cost</span><strong>{live[0]?.cost_bps ?? 20} bps</strong><small>spread plus slippage</small></article>
      </section>
      <ResultCards rows={strategies} getKey={(row) => row.strategy}
        title={(row) => row.strategy} subtitle={(row) => row.evidence_status || 'Insufficient observations'}
        fields={[
          { label: 'Net return', value: (row) => metric(row.net_return, '%', row) },
          { label: 'CAGR', value: (row) => metric(row.cagr, '%', row, annualizedMinimum) },
          { label: 'Sharpe', value: (row) => metric(row.sharpe, '', row, annualizedMinimum) },
          { label: 'Sortino', value: (row) => metric(row.sortino, '', row, annualizedMinimum) },
          { label: 'Max drawdown', value: (row) => metric(row.max_drawdown, '%', row) },
          { label: 'Turnover', value: (row) => metric(row.turnover, '%', row) },
          { label: 'Observations', value: (row) => `${row.observations || 0} returns · ${row.snapshots || 0} snapshots` },
          { label: 'Window', value: windowLabel },
        ]} />
      <div className="research-table card shadow-performance-table"><table><thead><tr><th>Strategy</th><th className="num">Net return</th><th className="num">CAGR</th><th className="num">Sharpe</th><th className="num">Sortino</th><th className="num">Max drawdown</th><th className="num">Turnover</th><th className="num">Observations</th><th>Evidence status</th></tr></thead>
        <tbody>{strategies.map((row) => <tr key={row.strategy}><td><b>{row.strategy}</b><small className="shadow-window">{windowLabel(row)}</small></td><td className="num">{metric(row.net_return, '%', row)}</td><td className="num">{metric(row.cagr, '%', row, annualizedMinimum)}</td><td className="num">{metric(row.sharpe, '', row, annualizedMinimum)}</td><td className="num">{metric(row.sortino, '', row, annualizedMinimum)}</td><td className="num">{metric(row.max_drawdown, '%', row)}</td><td className="num">{metric(row.turnover, '%', row)}</td><td className="num">{row.observations || 0}<small className="shadow-window">{row.snapshots || 0} snapshots</small></td><td><span className={`shadow-evidence-status ${row.observations ? 'live' : ''}`}>{row.evidence_status || 'Insufficient observations'}</span></td></tr>)}</tbody></table></div>
      </>}
    <p className="disclaimer">Signal comparisons use identical weighting and declared costs. Annualized statistics remain gated until {annualizedMinimum} matched returns exist; promotion remains gated until 36 monthly observations. Full-strategy comparisons are labeled separately.</p>
  </>
}
