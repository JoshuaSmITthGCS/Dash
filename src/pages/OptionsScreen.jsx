import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, Tier } from '../components/Bits.jsx'
import { OptionsNavigation, ScreenNavigation } from './ResearchScreen.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import WatchlistToggleButton from '../components/WatchlistToggleButton.jsx'
import DataTable from '../components/DataTable.jsx'
import BacktestSummary from '../components/BacktestSummary.jsx'
import CrossStrategyComparison from '../components/CrossStrategyComparison.jsx'

const number = (value, digits = 1) => value == null ? '–' : Number(value).toFixed(digits)
const pct = (value, digits = 1) => value == null ? '–' : `${(value * 100).toFixed(digits)}%`
const money = (value) => value == null ? '–' : `$${Number(value).toFixed(2)}`
const signed = (value) => value == null ? '–' : `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}`
const dateLabel = (value) => {
  if (!value) return '–'
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function reasonsFor(row) {
  const reasons = []
  if (row.implied_realized_vol_ratio != null) {
    reasons.push(row.implied_realized_vol_ratio <= 1.15
      ? `Priced close to, or below, realized volatility (${number(row.implied_realized_vol_ratio, 2)}× RV) — you're not paying a big premium for the expected move.`
      : `Priced at ${number(row.implied_realized_vol_ratio, 2)}× the stock's realized volatility — a real premium for expected movement, factored into the score.`)
  }
  if (row.open_interest != null && row.spread_pct != null) {
    reasons.push(`${row.open_interest} contracts of open interest and a ${pct(row.spread_pct)} bid/ask spread — liquid enough to fill near mid.`)
  }
  if (row.trend_20d != null) {
    reasons.push(`Underlying ${row.trend_20d >= 0 ? 'up' : 'down'} ${pct(Math.abs(row.trend_20d))} over 20 days — why this is a ${row.option_type === 'put' ? 'put' : 'call'} idea, not a prediction of what happens next.`)
  }
  return reasons
}

function OptionIdeaCard({ row, onOpen }) {
  const confidencePct = row.confidence != null ? Math.round(row.confidence * 100) : null
  return <article className="research-mobile-card" key={row.ticker}>
    <div className="research-card-head">
      <span className="rank-badge">#{row.rank}</span>
      <div><h2>{row.ticker}</h2><p>{row.sector || row.peer_group || 'Unclassified'}</p></div>
      <span className="mobile-score">{number(row.score, 2)}<small>score</small></span>
    </div>

    <div className="option-action-line">
      <span className={`chip screen-chip screen-chip-${row.option_type}`}>{row.option_type === 'put' ? 'Put' : 'Call'}</span>
      <strong>Buy to open · {money(row.strike)} {row.option_type} · exp {dateLabel(row.expiration)} ({row.days_to_expiration}d)</strong>
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
      <div><dt>Moneyness</dt><dd><Move pct={row.moneyness} /></dd></div>
      <div><dt>Mid price</dt><dd>{money(row.mid)}</dd></div>
      <div><dt>Spread</dt><dd>{pct(row.spread_pct)}</dd></div>
      <div><dt>Open interest</dt><dd>{row.open_interest ?? '–'}</dd></div>
      <div><dt>Implied vol.</dt><dd>{pct(row.implied_volatility)}</dd></div>
      <div><dt>IV / RV (20d)</dt><dd>{number(row.implied_realized_vol_ratio, 2)}×</dd></div>
      <div><dt>20d trend</dt><dd><Move pct={row.trend_20d} /></dd></div>
      <div><dt>News sentiment tilt</dt><dd>{signed(row.news_sentiment)}</dd></div>
      <div><dt>Research confidence tilt</dt><dd>{signed(row.research_confidence)}</dd></div>
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

  // The published screen has occasionally carried the exact same contract at two adjacent
  // ranks (same ticker/side/strike/expiration, identical score) — a pipeline dedup gap, not
  // a display choice. Never show a reader the same idea twice; keep whichever copy is
  // ranked first (results already arrive rank-ordered).
  const seenContracts = new Set()
  const sourceRows = (data?.results || [])
    .filter((row) => row.eligibility)
    .filter((row) => {
      const key = `${row.ticker}-${row.option_type}-${row.strike}-${row.expiration}`
      if (seenContracts.has(key)) return false
      seenContracts.add(key)
      return true
    })
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => optionType === 'all' || row.option_type === optionType)
    .filter((row) => sector === 'all' || row.sector === sector)

  const openResearch = (row) => setSelectedStock(advisorByTicker.get(row.ticker) || { ticker: row.ticker })

  return <>
    <ScreenNavigation />
    <OptionsNavigation />
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

    <BacktestSummary file="screens/options-backtest.json" />
    <CrossStrategyComparison />

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
      ) : (
        <DataTable
          rows={rows}
          getKey={(row) => `${row.ticker}-${row.option_type}-${row.strike}-${row.expiration}`}
          columns={[
            { key: 'rank', label: 'Rank', cell: (row) => <span className="rank">#{row.rank}</span> },
            { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker}</b> },
            { key: 'sector', label: 'Sector', cell: (row) => row.sector || '\u2013' },
            { key: 'option_type', label: 'Side', cell: (row) => <Tier label={row.option_type === 'put' ? 'Put' : 'Call'} /> },
            { key: 'strike', label: 'Strike', numeric: true, cell: (row) => <span className="mono">{money(row.strike)}</span> },
            { key: 'expiration', label: 'Expiration', cell: (row) => dateLabel(row.expiration) },
            { key: 'days_to_expiration', label: 'DTE', numeric: true, cell: (row) => <span className="mono">{row.days_to_expiration}</span> },
            { key: 'implied_volatility', label: 'IV', numeric: true, cell: (row) => <span className="mono">{pct(row.implied_volatility)}</span> },
            { key: 'implied_realized_vol_ratio', label: 'IV / RV', numeric: true,
              cell: (row) => <span className="mono">{number(row.implied_realized_vol_ratio, 2)}\u00d7</span> },
            { key: 'spread_pct', label: 'Spread', numeric: true, cell: (row) => <span className="mono">{pct(row.spread_pct)}</span> },
            { key: 'open_interest', label: 'Open int.', numeric: true, cell: (row) => <span className="mono">{row.open_interest ?? '\u2013'}</span> },
            { key: 'score', label: 'Score', numeric: true, cell: (row) => <span className="mono score-cell">{number(row.score, 2)}</span> },
            { key: 'open', label: <span className="sr-only">Open</span>, sortable: false,
              cell: (row) => <button className="icon-button" onClick={() => openResearch(row)}
                aria-label={`Open ${row.ticker} research`}><Icon name="chevron" /></button> },
          ]}
          mobile={{ estimateSize: 330, renderItem: (row) => <OptionIdeaCard row={row} onOpen={openResearch} /> }}
        />
      )}
      <p className="disclaimer">
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        Rankings are hypotheses for prospective validation, not claims of outperformance. Implied volatility, spreads,
        and open interest are snapshots from the last pipeline run and move throughout the trading day.
      </p>
    </>}
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={advisor?.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
