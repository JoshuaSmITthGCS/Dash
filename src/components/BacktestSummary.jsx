import { useState } from 'react'
import { useData } from '../lib/useData'
import Sparkline from './Sparkline.jsx'
import Icon from './Icons.jsx'

const pct = (value, digits = 1) => value == null ? '–' : `${(value * 100).toFixed(digits)}%`
const number = (value, digits = 2) => value == null ? '–' : Number(value).toFixed(digits)
const money = (value) => value == null ? '–' : `$${Number(value).toFixed(2)}`

function StatsBlock({ stats, title }) {
  if (!stats) return null
  return <div className="backtest-stats-block">
    {title && <h4 className="backtest-subtitle">{title}</h4>}
    <div className="metrics" aria-label={`${title || 'Backtest'} statistics`}>
      <div className={`metric ${stats.annualized_return >= 0 ? 'good' : 'rich'}`}><b>{pct(stats.annualized_return)}</b><span>Annualized return</span></div>
      <div className="metric"><b>{number(stats.sharpe_ratio)}</b><span>Sharpe ratio</span></div>
      <div className="metric"><b>{pct(stats.deflated_sharpe_ratio, 0)}</b><span>Deflated Sharpe (vs. {stats.deflated_sharpe_trials ?? '–'} trials)</span></div>
      <div className="metric"><b>{pct(stats.max_drawdown)}</b><span>Max drawdown</span></div>
      <div className="metric"><b>{pct(stats.win_rate)}</b><span>Win rate</span></div>
      <div className="metric"><b>{money(stats.average_pnl_per_trade)}</b><span>Avg P/L per trade</span></div>
      <div className="metric"><b>{stats.num_trades}</b><span>Trades</span></div>
    </div>
    <Sparkline values={stats.equity_curve} label={`${title || 'Strategy'} simulated equity curve`} height={54} className="backtest-spark" />
  </div>
}

/** One collapsible "example performance" panel for a strategy screen.
 * strategyKey: picks a sub-object out of data.backtest for screens covering more than one
 * strategy (e.g. advanced-strategies' "iron_condor"/"straddle") - omit for single-strategy screens.
 * showBaseline: also renders data.baseline alongside data.backtest (protective-put's unhedged comparison).
 */
export default function BacktestSummary({ file, strategyKey, title, showBaseline }) {
  const [expanded, setExpanded] = useState(false)
  const { data, loading, error } = useData(file)

  if (loading || error || !data || data.status !== 'success') return null
  const stats = strategyKey ? data.backtest?.[strategyKey] : data.backtest
  if (!stats) return null

  return <div className="card backtest-summary">
    <button className="expand-button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {expanded ? `Hide simulated backtest${title ? ` — ${title}` : ''}` : `Show example performance${title ? ` — ${title}` : ''} (simulated)`}
      <Icon name="chevron" size={17} className={expanded ? 'rotated' : ''} />
    </button>
    {expanded && <div className="research-expanded backtest-detail">
      <p className="backtest-methodology">{data.methodology}</p>
      <StatsBlock stats={stats} title={showBaseline ? 'Hedged' : null} />
      {showBaseline && data.baseline && <StatsBlock stats={data.baseline} title="Unhedged baseline" />}
      <p className="backtest-footnote">Simulated over {data.universe_tickers} tickers · model {data.model_version}</p>
      <p className="backtest-footnote">Deflated Sharpe is the probability the true Sharpe ratio beats what
        random chance across this many strategy-design choices would produce on its own — a raw Sharpe ratio
        alone doesn't correct for that. It approximates a quantity (variance across independently-run trials)
        this pipeline doesn't have the data to measure directly, so read it as a directional multiple-testing
        haircut, not an exact probability.</p>
    </div>}
  </div>
}
