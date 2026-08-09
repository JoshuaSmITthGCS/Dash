import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import { STRATEGY_SCREENS } from '../lib/strategyScreenConfigs.js'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import WatchlistToggleButton from '../components/WatchlistToggleButton.jsx'
import MobileVirtualList from '../components/MobileVirtualList.jsx'
import BacktestSummary from '../components/BacktestSummary.jsx'

const number = (value, digits = 1) => value == null ? '–' : Number(value).toFixed(digits)
const money = (value) => value == null ? '–' : `$${Number(value).toFixed(2)}`
const dollars = (value) => value == null ? '–' : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
const dateLabel = (value) => {
  if (!value) return '–'
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function formatMetric(value, format) {
  if (value == null) return '–'
  switch (format) {
    case 'pct': return `${(value * 100).toFixed(1)}%`
    case 'money': return money(value)
    case 'ratio': return `${Number(value).toFixed(2)}×`
    case 'signed': return `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}`
    default: return String(value)
  }
}

function legsSummary(legs) {
  return (legs || []).map((leg) => `${leg.action === 'buy' ? 'Buy' : 'Sell'} ${leg.option_type} ${money(leg.strike)}`).join(' · ')
}

function reasonsFor(row) {
  const m = row.metrics || {}
  const reasons = []
  if (m.annualized_yield != null) reasons.push(`Annualized premium yield of ${formatMetric(m.annualized_yield, 'pct')} at current pricing.`)
  if (m.probability_otm != null) reasons.push(`~${formatMetric(m.probability_otm, 'pct')} modeled probability this expires worthless — you'd keep the full premium.`)
  if (m.probability_in_range != null) reasons.push(`~${formatMetric(m.probability_in_range, 'pct')} modeled probability price stays inside the range through expiration.`)
  if (m.probability_of_profit != null) reasons.push(`~${formatMetric(m.probability_of_profit, 'pct')} modeled probability of a profitable move by expiration.`)
  if (m.risk_reward != null) reasons.push(`Risk/reward of ${formatMetric(m.risk_reward, 'ratio')} — potential profit relative to what's at risk.`)
  if (m.cost_pct != null) reasons.push(`Costs ${formatMetric(m.cost_pct, 'pct')} of the position to put on.`)
  if (m.net_cost_pct != null) reasons.push(`Net ${m.net_cost_pct >= 0 ? 'cost' : 'credit'} of ${formatMetric(Math.abs(m.net_cost_pct), 'pct')} of the position.`)
  const openInterests = (row.legs || []).map((leg) => leg.open_interest).filter((value) => value != null)
  if (openInterests.length) reasons.push(`Legs carry real open interest (as low as ${Math.min(...openInterests)} contracts) — liquid enough to expect a fill near mid.`)
  if (row.trend_20d != null) reasons.push(`Underlying ${row.trend_20d >= 0 ? 'up' : 'down'} ${formatMetric(Math.abs(row.trend_20d), 'pct')} over 20 days.`)
  return reasons
}

function StrategyCard({ row, config, onOpen }) {
  const confidencePct = row.confidence != null ? Math.round(row.confidence * 100) : null
  const metrics = config.metricsConfig(row)
  return <article className="research-mobile-card" key={`${row.ticker}-${row.strategy || ''}-${row.rank}`}>
    <div className="research-card-head">
      <span className="rank-badge">#{row.rank}</span>
      <div><h2>{row.ticker}</h2><p>{row.sector || row.peer_group || 'Unclassified'}</p></div>
      <span className="mobile-score">{number(row.score, 2)}<small>score</small></span>
    </div>

    <div className="option-action-line">
      <span className="chip">{config.strategyLabel(row)}</span>
      <strong>{legsSummary(row.legs)} · exp {dateLabel(row.expiration)} ({row.days_to_expiration}d)</strong>
    </div>

    <div className="research-card-badges">
      <span className="chip">Capital/margin: {dollars(row.capital_required)}</span>
    </div>

    <div className="bar-row">
      <span className="bar-lab">Confidence</span>
      <span className="bar-track"><span className="bar-fill" style={{ width: `${confidencePct ?? 0}%` }} /></span>
      <span className="bar-val">{confidencePct != null ? `${confidencePct}%` : '–'}</span>
    </div>

    <ul className="method-list option-reasons">
      {reasonsFor(row).map((reason, index) => <li key={index}>{reason}</li>)}
    </ul>

    <div className="research-card-badges">
      <WatchlistToggleButton stock={row} size={18} />
    </div>

    <dl className="research-card-metrics">
      <div><dt>Underlying</dt><dd>{money(row.price)}</dd></div>
      {metrics.map(([key, label, format]) => <div key={key}><dt>{label}</dt><dd>{formatMetric((row.metrics || {})[key], format)}</dd></div>)}
    </dl>
    <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
  </article>
}

export default function StrategyScreen({ id }) {
  const config = STRATEGY_SCREENS[id]
  const { data, loading, error } = useData(config.file)
  const { data: advisor } = useData('advisor.json')
  const [strategyFilter, setStrategyFilter] = useState('all')
  const [sector, setSector] = useState('all')
  const [selectedStock, setSelectedStock] = useState(null)

  const advisorByTicker = useMemo(() => {
    const rows = [...(advisor?.research || []), ...(advisor?.portfolio_coverage || [])]
    return new Map(rows.map((row) => [row.ticker, row]))
  }, [advisor])

  const sourceRows = (data?.results || []).filter((row) => row.eligibility)
  const strategies = useMemo(() => [...new Set(sourceRows.map((row) => row.strategy).filter(Boolean))], [sourceRows])
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => strategyFilter === 'all' || row.strategy === strategyFilter)
    .filter((row) => sector === 'all' || row.sector === sector)

  const openResearch = (row) => setSelectedStock(advisorByTicker.get(row.ticker) || { ticker: row.ticker })

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">{config.eyebrow}</span>
        <h1 className="page-title">{config.title}</h1>
        <p className="page-sub">{config.description}</p>
      </div>
      <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
    </div>

    <div className="card prospective-notice" role="note"><strong>Not a trade instruction.</strong> {config.riskNote}</div>

    {config.backtestFile && (config.backtestStrategyKeys
      ? config.backtestStrategyKeys.map(([key, label]) => (
        <BacktestSummary key={key} file={config.backtestFile} strategyKey={key} title={label} />
      ))
      : <BacktestSummary file={config.backtestFile} showBaseline={config.backtestShowBaseline} />)}

    <div className="research-toolbar">
      {strategies.length > 1 && <label><span className="sr-only">Strategy</span><select value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}>
        <option value="all">All strategies</option>
        {strategies.map((value) => <option key={value} value={value}>{value === 'iron_condor' ? 'Iron condor' : 'Straddle'}</option>)}
      </select></label>}
      {sectors.length > 0 && <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
        <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
      </select></label>}
    </div>

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div> : <>
      {data?.status === 'unavailable' ? (
        <Empty note={data.reason_code === 'YFINANCE_UNAVAILABLE'
          ? 'Options-chain data is unavailable in this snapshot.'
          : 'No ticker currently clears this screen. Check back after the next data refresh.'} />
      ) : !rows.length ? (
        <Empty note="No candidate matches the current filters." />
      ) : <>
        <MobileVirtualList className="research-mobile-list" items={rows} getKey={(row) => `${row.ticker}-${row.strategy || ''}-${row.rank}`} estimateSize={360}
          renderItem={(row) => <StrategyCard row={row} config={config} onOpen={openResearch} />} />

        <div className="research-table card">
          <table>
            <thead><tr>
              <th scope="col">Rank</th><th scope="col">Ticker</th><th scope="col">Sector</th>
              {strategies.length > 1 && <th scope="col">Strategy</th>}
              <th scope="col">Legs</th><th scope="col">Expiration</th><th scope="col" className="num">DTE</th>
              <th scope="col" className="num">Capital</th><th scope="col" className="num">Score</th>
              <th scope="col"><span className="sr-only">Open</span></th>
            </tr></thead>
            <tbody>{rows.map((row) => <tr key={`${row.ticker}-${row.strategy || ''}-${row.rank}`}>
              <td className="rank">#{row.rank}</td>
              <td><b>{row.ticker}</b></td>
              <td>{row.sector || '–'}</td>
              {strategies.length > 1 && <td>{config.strategyLabel(row)}</td>}
              <td>{legsSummary(row.legs)}</td>
              <td>{dateLabel(row.expiration)}</td>
              <td className="num mono">{row.days_to_expiration}</td>
              <td className="num mono">{dollars(row.capital_required)}</td>
              <td className="mono num score-cell">{number(row.score, 2)}</td>
              <td><button className="icon-button" onClick={() => openResearch(row)} aria-label={`Open ${row.ticker} research`}><Icon name="chevron" /></button></td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
      <p className="disclaimer">
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        Rankings are hypotheses for prospective validation, not claims of outperformance. Prices, implied volatility,
        and open interest are snapshots from the last pipeline run and move throughout the trading day.
      </p>
    </>}
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={advisor?.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
