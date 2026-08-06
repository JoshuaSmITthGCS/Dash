import { useEffect, useMemo, useState } from 'react'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { Loading, Move, Tier } from '../components/Bits.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import Icon from '../components/Icons.jsx'

const RECENT_KEY = 'valuesignal.recent-searches'
const WATCH_KEY = 'valuesignal.watchlist'

function readList(key) { try { const value = JSON.parse(localStorage.getItem(key)); return Array.isArray(value) ? value : [] } catch { return [] } }
function latestMove(row) {
  const values = row?.history?.closes || []
  if (values.length < 2 || !values.at(-2)) return null
  return (values.at(-1) / values.at(-2) - 1) * 100
}

export default function Search() {
  const { data, loading } = useData('advisor.json')
  const { positions } = useFirebasePortfolio()
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [selected, setSelected] = useState(null)
  const [recent, setRecent] = useState(() => readList(RECENT_KEY))
  const watchlist = useMemo(() => readList(WATCH_KEY).map((item) => typeof item === 'string' ? item : item.ticker), [])

  useEffect(() => { const timer = window.setTimeout(() => setDebounced(query.trim()), 180); return () => window.clearTimeout(timer) }, [query])
  const catalog = useMemo(() => {
    if (!data) return []
    const detailed = [...(data.portfolio_coverage || []), ...(data.screen_universe || []), ...(data.research || [])]
    const byTicker = new Map()
    detailed.forEach((row) => { if (row?.ticker) byTicker.set(row.ticker, { ...byTicker.get(row.ticker), ...row }) })
    ;(data.universe || []).forEach((ticker) => { if (!byTicker.has(ticker)) byTicker.set(ticker, { ticker, name: ticker }) })
    const portfolioTickers = new Set(positions.map((row) => String(row.ticker).toUpperCase()))
    return [...byTicker.values()].map((row) => ({ ...row, inPortfolio: portfolioTickers.has(row.ticker), inWatchlist: watchlist.includes(row.ticker), published: (data.research || []).some((item) => item.ticker === row.ticker) }))
  }, [data, positions, watchlist])

  if (loading) return <Loading />
  const normalized = debounced.toLowerCase()
  const results = normalized ? catalog.filter((row) => row.ticker.toLowerCase().includes(normalized) || String(row.name || '').toLowerCase().includes(normalized)).sort((a, b) => Number(b.inPortfolio) - Number(a.inPortfolio) || Number(b.published) - Number(a.published) || (b.score || 0) - (a.score || 0)).slice(0, 60) : []
  const saveRecent = (row) => {
    const next = [row.ticker, ...recent.filter((ticker) => ticker !== row.ticker)].slice(0, 8)
    setRecent(next); try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* optional */ }
    if (row.published || row.history) setSelected(row)
  }
  const groups = [
    ['In your portfolio', results.filter((row) => row.inPortfolio)],
    ['Published research', results.filter((row) => !row.inPortfolio && row.published)],
    ['Watchlist', results.filter((row) => !row.inPortfolio && !row.published && row.inWatchlist)],
    ['Covered universe', results.filter((row) => !row.inPortfolio && !row.published && !row.inWatchlist)],
  ].filter(([, items]) => items.length)

  return <div className="global-search-page">
    <header className="page-head compact-page-head"><div><span className="eyebrow">Global discovery</span><h1 className="page-title">Search</h1><p className="page-sub">Find a company across your portfolio, published research, watchlist, and the covered universe.</p></div></header>
    <label className="global-search-input"><Icon name="search" size={22} /><span className="sr-only">Search companies</span><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ticker or company name" autoComplete="off" />{query && <button className="icon-button" onClick={() => setQuery('')} aria-label="Clear search"><Icon name="close" /></button>}</label>
    {!debounced && <section className="recent-searches"><h2>Recent searches</h2>{recent.length ? <div>{recent.map((ticker) => <button key={ticker} onClick={() => setQuery(ticker)}>{ticker}</button>)}<button className="muted-button" onClick={() => { setRecent([]); localStorage.removeItem(RECENT_KEY) }}>Clear</button></div> : <p>Your recent company searches will appear here.</p>}</section>}
    {debounced && <div className="search-result-summary"><strong>{results.length}</strong> {results.length === 1 ? 'match' : 'matches'} for “{debounced}”</div>}
    {groups.map(([label, items]) => <section className="search-result-group" key={label}><h2>{label}</h2><div>{items.map((row) => <button className="company-search-result" key={row.ticker} onClick={() => saveRecent(row)}><CompanyLogo company={row} size={42} /><span className="search-company-copy"><strong>{row.ticker}</strong><span>{row.name}</span><small>{row.sector || (row.published ? 'Published research' : 'Coverage universe')}</small></span><span className="search-market-data"><b>{row.price == null ? '–' : `$${Number(row.price).toFixed(2)}`}</b><Move pct={latestMove(row)} /></span>{row.score != null && <span className="search-score"><b>{Math.round(row.score)}</b><small>score</small></span>}{row.stance && <Tier label={row.stance} />}<Icon name="chevron" /></button>)}</div></section>)}
    {debounced && !results.length && <div className="report-empty-state"><h2>No matching company</h2><p>Try a ticker or a broader company name. Search covers the currently loaded ValueSignal universe.</p></div>}
    {selected && <StockDetailModal stock={selected} benchmarkHistory={data.benchmark_history} onClose={() => setSelected(null)} />}
  </div>
}
