import { useEffect, useMemo, useState } from 'react'
import { useData } from '../lib/useData.js'
import { Empty, Loading } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import Icon from '../components/Icons.jsx'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes.js'
import {
  dailyMove,
  marketType,
  priceSeriesFromSnapshot,
  rankDailySectors,
  rankDailyStocks,
} from '../lib/marketPresentation.js'

const INDEXES = [
  { ticker: 'SPY', label: 'S&P 500' },
  { ticker: 'QQQ', label: 'Nasdaq 100' },
  { ticker: 'DIA', label: 'Dow Jones' },
  { ticker: 'IWM', label: 'Russell 2000' },
]
const RANGE_DAYS = { '1D': 2, '1W': 6, '1M': 22, '3M': 66, '1Y': 253 }
const INTRADAY_STORAGE_KEY = 'valuesignal.marketIntraday.v1'
const money = (value) => value == null ? '–' : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const signedPct = (value) => value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`

function sliceRange(series, range) {
  const points = RANGE_DAYS[range] || RANGE_DAYS['1M']
  return { dates: series.dates.slice(-points), values: series.values.slice(-points) }
}

function readIntraday() {
  try {
    const value = JSON.parse(localStorage.getItem(INTRADAY_STORAGE_KEY) || '{}')
    return value && typeof value === 'object' ? value : {}
  } catch { return {} }
}

function MarketStat({ label, title, value, tone = 'neutral', detail }) {
  return <article className={`market-stat-card ${tone}`}><span>{label}</span><h2>{title || 'Unavailable'}</h2><strong>{value}</strong><small>{detail}</small></article>
}

export default function Markets() {
  const { data: report, loading: reportLoading } = useData('report.json')
  const { data: spy, loading: spyLoading } = useData('etf/SPY.json')
  const { data: qqq } = useData('etf/QQQ.json')
  const { data: dia } = useData('etf/DIA.json')
  const { data: iwm } = useData('etf/IWM.json')
  const liveIndexes = usePortfolioQuotes(INDEXES.map((index) => index.ticker))
  const [range, setRange] = useState('1D')
  const [query, setQuery] = useState('')
  const [intraday, setIntraday] = useState(readIntraday)
  const snapshots = { SPY: spy, QQQ: qqq, DIA: dia, IWM: iwm }

  const coveredRows = useMemo(() => {
    const byTicker = new Map()
    for (const row of [...(report?.research || []), ...(report?.portfolio_coverage || [])]) {
      if (row?.ticker) byTicker.set(row.ticker, row)
    }
    return [...byTicker.values()]
  }, [report])
  const rankedStocks = useMemo(() => rankDailyStocks(coveredRows), [coveredRows])
  const sectors = useMemo(() => rankDailySectors(coveredRows), [coveredRows])
  const session = useMemo(() => marketType(coveredRows), [coveredRows])
  const indexes = INDEXES.map((index) => {
    const series = priceSeriesFromSnapshot(snapshots[index.ticker])
    const live = liveIndexes.quotes?.[index.ticker]
    const move = dailyMove({
      price: Number.isFinite(live?.price) ? live.price : undefined,
      previousClose: Number.isFinite(live?.previousClose) ? live.previousClose : undefined,
      history: { closes: series.values },
    })
    return { ...index, series, move }
  }).filter((index) => index.move.available).sort((left, right) => right.move.pct - left.move.pct)
  const selected = indexes.find((index) => index.ticker === 'SPY') || indexes[0]
  const recordedToday = selected ? intraday[selected.ticker] || [] : []
  const chart = selected
    ? range === '1D' && recordedToday.length > 1
      ? { dates: recordedToday.map((point) => point.at), values: recordedToday.map((point) => point.price) }
      : sliceRange(selected.series, range)
    : null
  const normalizedQuery = query.trim().toUpperCase()
  const result = normalizedQuery
    ? coveredRows.find((row) => row.ticker === normalizedQuery)
      || coveredRows.find((row) => String(row.name || '').toUpperCase().includes(normalizedQuery))
    : null
  const resultMove = result ? dailyMove(result) : null
  const top = rankedStocks[0]
  const worst = rankedStocks.at(-1)
  const status = report?.market?.status?.find((row) => row.region === 'United States' && row.market_type === 'Equity')

  useEffect(() => {
    if (!liveIndexes.fetchedAt) return
    const marketDate = String(liveIndexes.fetchedAt).slice(0, 10)
    setIntraday((current) => {
      const next = { ...current }
      for (const index of INDEXES) {
        const quote = liveIndexes.quotes?.[index.ticker]
        if (!Number.isFinite(quote?.price)) continue
        const sameDay = (next[index.ticker] || []).filter((point) => String(point.at).slice(0, 10) === marketDate)
        if (!sameDay.some((point) => point.at === liveIndexes.fetchedAt)) sameDay.push({ at: liveIndexes.fetchedAt, price: quote.price })
        next[index.ticker] = sameDay.slice(-120)
      }
      try { localStorage.setItem(INTRADAY_STORAGE_KEY, JSON.stringify(next)) } catch { /* in-memory history still works */ }
      return next
    })
  }, [liveIndexes.fetchedAt, liveIndexes.quotes])

  if (reportLoading || spyLoading) return <Loading />
  if (!report || !spy) return <Empty note="Market data is unavailable in the latest refresh." />

  return <div className="markets-page">
    <header className="markets-header">
      <div><span className="eyebrow">Markets</span><h1>Today in the market</h1><p>Latest available prices, breadth, leaders, and laggards—one place to understand the session.</p></div>
      <div className={`market-session-badge ${session.tone}`}><span aria-hidden="true" /><div><small>Today’s market type</small><strong>{session.label}</strong><em>{session.breadthPct == null ? 'Breadth unavailable' : `${session.breadthPct.toFixed(0)}% advancing`}</em></div></div>
    </header>

    {status && <div className="market-status-line"><Icon name="market" size={16} /><strong>U.S. equities: {status.current_status}</strong><span>{status.primary_exchanges} · {status.local_open}–{status.local_close}</span></div>}

    <section className="market-stats-grid" aria-label="Market leaders and laggards">
      <MarketStat label="Index ETF leader" title={indexes[0]?.ticker} value={signedPct(indexes[0]?.move.pct)} tone="positive" detail={indexes[0]?.label || 'Latest close'} />
      <MarketStat label="Hottest sector" title={sectors[0]?.sector} value={signedPct(sectors[0]?.averagePct)} tone="positive" detail={`${sectors[0]?.count || 0} covered stocks`} />
      <MarketStat label="Weakest sector" title={sectors.at(-1)?.sector} value={signedPct(sectors.at(-1)?.averagePct)} tone="negative" detail={`${sectors.at(-1)?.count || 0} covered stocks`} />
      <MarketStat label="Top stock" title={top?.ticker} value={signedPct(top?.dailyMove.pct)} tone="positive" detail={top?.name || 'Latest close'} />
      <MarketStat label="Worst stock" title={worst?.ticker} value={signedPct(worst?.dailyMove.pct)} tone="negative" detail={worst?.name || 'Latest close'} />
    </section>

    <section className="market-chart-card" aria-labelledby="market-chart-title">
      <header><div><span className="eyebrow">Market summary</span><h2 id="market-chart-title">{selected?.label || 'S&P 500'} performance</h2><p>{recordedToday.length > 1 ? `${recordedToday.length} live observations recorded today at five-minute intervals.` : 'The 1D fallback is the latest close-to-close move; five-minute live observations build while this tab is open.'}</p></div><label><span>Time range</span><select value={range} onChange={(event) => setRange(event.target.value)}>{Object.keys(RANGE_DAYS).map((item) => <option key={item} value={item}>{item === '1D' ? 'Today' : item}</option>)}</select></label></header>
      {chart?.dates.length > 1 ? <GrowthChart height={360} width={920} dates={chart.dates} series={[{ label: selected.label, values: chart.values, color: 'var(--series-stock)', emphasis: true }]} valueFormatter={money} caption={`${selected.ticker} adjusted closes through ${chart.dates.at(-1)}.`} /> : <Empty note="Two market observations are required to draw this range." />}
      <div className="index-strip" aria-label="Major index ETF performance">{indexes.map((index) => <article key={index.ticker}><span>{index.ticker}<small>{index.label}</small></span><strong>{money(index.move.price)}</strong><em className={index.move.pct >= 0 ? 'positive' : 'negative'}>{signedPct(index.move.pct)}</em></article>)}</div>
    </section>

    <section className="market-search-card" aria-labelledby="market-search-title">
      <div><span className="eyebrow">Direct lookup</span><h2 id="market-search-title">How did a stock perform today?</h2><p>Search the latest covered market snapshot by ticker or company name.</p></div>
      <label className="market-search-input"><span className="sr-only">Stock ticker or company</span><Icon name="search" size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try AAPL or Apple" /></label>
      {normalizedQuery && (result ? <article className={`market-search-result ${resultMove?.pct >= 0 ? 'positive' : 'negative'}`}><div><strong>{result.ticker}</strong><span>{result.name}</span></div><div><small>Current price</small><b>{money(resultMove?.price ?? result.price)}</b></div><div><small>Today</small><b>{signedPct(resultMove?.pct)}</b><em>{resultMove?.delta == null ? 'Daily change unavailable' : `${resultMove.delta >= 0 ? '+' : '−'}${money(Math.abs(resultMove.delta))} per share`}</em></div><div><small>20 trading days</small><b>{signedPct(result.technical_detail?.return_20d)}</b></div></article> : <p className="market-search-empty">No covered ticker matched “{query}”.</p>)}
    </section>
  </div>
}
