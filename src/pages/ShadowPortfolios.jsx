import { ScreenNavigation } from './ResearchScreen'
import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'

const metric = (value, suffix = '') => value == null ? '—' : `${Number(value).toFixed(2)}${suffix}`
export default function ShadowPortfolios() {
  const { data, loading, error } = useData('screens/shadow-portfolios.json')
  if (loading) return <><ScreenNavigation /><Loading /></>
  return <><ScreenNavigation /><div className="page-head"><div><span className="eyebrow">Prospective validation</span>
    <h1 className="page-title">Shadow portfolio performance</h1><p className="page-sub">Immutable, net-of-cost observations. No strategy is promoted from implementation alone.</p></div></div>
    {error ? <div className="card etf-state" role="alert"><strong>Shadow results unavailable</strong><span>{error.message}</span></div> :
      <div className="research-table card"><table><thead><tr><th>Strategy</th><th className="num">Net return</th><th className="num">CAGR</th><th className="num">Sharpe</th><th className="num">Sortino</th><th className="num">Max drawdown</th><th className="num">Turnover</th><th>Evidence status</th></tr></thead>
        <tbody>{(data?.strategies || []).map((row) => <tr key={row.strategy}><td><b>{row.strategy}</b></td><td className="num">{metric(row.net_return, '%')}</td><td className="num">{metric(row.cagr, '%')}</td><td className="num">{metric(row.sharpe)}</td><td className="num">{metric(row.sortino)}</td><td className="num">{metric(row.max_drawdown, '%')}</td><td className="num">{metric(row.turnover, '%')}</td><td>{row.evidence_status || 'Insufficient observations'}</td></tr>)}</tbody></table></div>}
    <p className="disclaimer">Signal comparisons must use identical rebalance dates, stock count, weighting, filters, constraints, costs, and execution lag. Full-strategy comparisons are labeled separately.</p>
  </>
}
