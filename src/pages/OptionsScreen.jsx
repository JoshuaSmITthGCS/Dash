import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, Tier } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import WatchlistToggleButton from '../components/WatchlistToggleButton.jsx'
import MobileVirtualList from '../components/MobileVirtualList.jsx'

const number = (value, digits = 1) => value == null ? '–' : Number(value).toFixed(digits)
const pct = (value, digits = 1) => value == null ? '–' : `${(value * 100).toFixed(digits)}%`
const money = (value) => value == null ? '–' : `$${Number(value).toFixed(2)}`
const dateLabel = (value) => {
  if (!value) return '–'
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function OptionIdeaCard({ row, onOpen }) {
  return <article className="research-mobile-card" key={row.ticker}>
    <div className="research-card-head">
      <span className="rank-badge">#{row.rank}</span>
      <div><h2>{row.ticker}</h2><p>{row.sector || row.peer_group || 'Unclassified'}</p></div>
      <span className="mobile-score">{number(row.score, 2)}<small>score</small></span>
    </div>
    <div className="research-card-badges">
      <span className={`chip screen-chip screen-chip-${row.option_type}`}>{row.option_type === 'put' ? 'Put' : 'Call'}</span>
      <span className="chip">{row.days_to_expiration}d to exp · {dateLabel(row.expiration)}</span>
      <WatchlistToggleButton stock={row} size={18} />
    </div>
    <dl className="research-card-metrics">
      <div><dt>Strike</dt><dd>{money(row.strike)}</dd></div>
      <div><dt>Underlying</dt><dd>{money(row.price)}</dd></div>
      <div><dt>Moneyness</dt><dd><Move pct={row.moneyness} /></dd></div>
      <div><dt>Mid price</dt><dd>{money(row.mid)}</dd></div>
      <div><dt>Spread</dt><dd>{pct(row.spread_pct)}</dd></div>
      <div><dt>Open interest</dt><dd>{row.open_interest ?? '–'}</dd></div>
      <div><dt>Implied vol.</dt><dd>{pct(row.implied_volatility)}</dd></div>
      <div><dt>IV / RV (20d)</dt><dd>{number(row.implied_realized_vol_ratio, 2)}×</dd></div>
      <div><dt>20d trend</dt><dd><Move pct={row.trend_20d} /></dd></div>
    </dl>
    <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
  </article>
}

export default function OptionsScreen() {
  const { data, loading, error } = useData('screens/options.json')
  const { data: advisor } = useData('advisor.json')
  const [optionType, setOptionType] = useState('all')
  const [sector, setSector] = useState('all')
  const [selectedStock, setSelectedStock] = useState(null)

  const advisorByTicker = useMemo(() => {
    const rows = [...(advisor?.research || []), ...(advisor?.portfolio_coverage || [])]
    return new Map(rows.map((row) => [row.ticker, row]))
  }, [advisor])

  const sourceRows = (data?.results || []).filter((row) => row.eligibility)
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => optionType === 'all' || row.option_type === optionType)
    .filter((row) => sector === 'all' || row.sector === sector)

  const openResearch = (row) => setSelectedStock(advisorByTicker.get(row.ticker) || { ticker: row.ticker })

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">Multi-day horizon · your universe</span>
        <h1 className="page-title">Best <span className="accent">multi-day options</span></h1>
        <p className="page-sub">
          Near-the-money call and put candidates expiring {data?.window?.min_days_to_expiration ?? 2}–
          {data?.window?.max_days_to_expiration ?? 45} days out, ranked by implied-vs-realized volatility value,
          contract liquidity, and recent trend strength. Direction (call vs. put) follows the 20-day price
          trend, not a prediction of what happens next.
        </p>
      </div>
      <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
    </div>

    <div className="card prospective-notice" role="note">
      <strong>Research screen, not a trade instruction.</strong> Options carry leverage, time decay, and can expire
      worthless. Confirm live bid/ask, open interest, and your own risk limits in your broker before acting on
      anything here — nothing in this app places orders or connects to a brokerage account.
    </div>

    <div className="research-toolbar">
      <label><span className="sr-only">Direction</span><select value={optionType} onChange={(event) => setOptionType(event.target.value)}>
        <option value="all">Calls &amp; puts</option>
        <option value="call">Calls only</option>
        <option value="put">Puts only</option>
      </select></label>
      {sectors.length > 0 && <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
        <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
      </select></label>}
    </div>

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div> : <>
      {data?.status === 'unavailable' ? (
        <Empty note={data.reason_code === 'YFINANCE_UNAVAILABLE'
          ? 'Options-chain data is unavailable in this snapshot.'
          : 'No ticker currently clears the multi-day options screen. Check back after the next data refresh.'} />
      ) : !rows.length ? (
        <Empty note="No candidate matches the current filters." />
      ) : <>
        <MobileVirtualList className="research-mobile-list" items={rows} getKey={(row) => row.ticker} estimateSize={330}
          renderItem={(row) => <OptionIdeaCard row={row} onOpen={openResearch} />} />

        <div className="research-table card">
          <table>
            <thead><tr>
              <th scope="col">Rank</th><th scope="col">Ticker</th><th scope="col">Sector</th>
              <th scope="col">Side</th><th scope="col" className="num">Strike</th><th scope="col">Expiration</th>
              <th scope="col" className="num">DTE</th><th scope="col" className="num">IV</th>
              <th scope="col" className="num">IV / RV</th><th scope="col" className="num">Spread</th>
              <th scope="col" className="num">Open int.</th><th scope="col" className="num">Score</th>
              <th scope="col"><span className="sr-only">Open</span></th>
            </tr></thead>
            <tbody>{rows.map((row) => <tr key={row.ticker}>
              <td className="rank">#{row.rank}</td>
              <td><b>{row.ticker}</b></td>
              <td>{row.sector || '–'}</td>
              <td><Tier label={row.option_type === 'put' ? 'Put' : 'Call'} /></td>
              <td className="num mono">{money(row.strike)}</td>
              <td>{dateLabel(row.expiration)}</td>
              <td className="num mono">{row.days_to_expiration}</td>
              <td className="num mono">{pct(row.implied_volatility)}</td>
              <td className="num mono">{number(row.implied_realized_vol_ratio, 2)}×</td>
              <td className="num mono">{pct(row.spread_pct)}</td>
              <td className="num mono">{row.open_interest ?? '–'}</td>
              <td className="mono num score-cell">{number(row.score, 2)}</td>
              <td><button className="icon-button" onClick={() => openResearch(row)} aria-label={`Open ${row.ticker} research`}><Icon name="chevron" /></button></td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
      <p className="disclaimer">
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        Rankings are hypotheses for prospective validation, not claims of outperformance. Implied volatility, spreads,
        and open interest are snapshots from the last pipeline run and move throughout the trading day.
      </p>
    </>}
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={advisor?.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
