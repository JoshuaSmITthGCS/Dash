import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { MARKETS_IDS } from './capabilityIds.js'
import { dailyMove, priceSeriesFromSnapshot, rankDailySectors, rankDailyStocks } from '../../../lib/marketPresentation.js'
import { NEWS_SORT_OPTIONS, nextNewsSort, sortNews } from '../../../lib/newsSort.js'

export const MARKETS_VIEWS = Object.freeze(['indexes', 'news'])

const INDEXES = [
  { ticker: 'SPY', label: 'S&P 500' },
  { ticker: 'QQQ', label: 'Nasdaq 100' },
  { ticker: 'DIA', label: 'Dow Jones' },
  { ticker: 'IWM', label: 'Russell 2000' },
]
const RANGE_KEYS = ['1D', '1W', '1M', '3M', '1Y']
const RANGE_DAYS = { '1D': 2, '1W': 6, '1M': 22, '3M': 66, '1Y': 253 }
const INTRADAY_STORAGE_KEY = 'valuesignal.marketIntraday.v1'
const INTRADAY_POLL_MS = 5 * 60 * 1000

const money = (value) => (value == null ? '–' : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
const signedPct = (value) => (value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`)

function sliceRange(series, range) {
  const points = RANGE_DAYS[range] || RANGE_DAYS['1M']
  return { dates: series.dates.slice(-points), values: series.values.slice(-points) }
}

function readIntraday() {
  try {
    const value = JSON.parse(localStorage.getItem(INTRADAY_STORAGE_KEY) || '{}')
    return value && typeof value === 'object' ? value : {}
  } catch {
    return {}
  }
}

function writeIntraday(value) {
  try {
    localStorage.setItem(INTRADAY_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // In-memory history still works when storage is unavailable.
  }
}

function combineCoveredRows(report) {
  const byTicker = new Map()
  for (const row of [...(report?.research || []), ...(report?.portfolio_coverage || [])]) {
    if (row?.ticker) byTicker.set(row.ticker, row)
  }
  return [...byTicker.values()]
}

// Renders through the active medium's Control when it implements one (per the wiring contract's
// `manifest.components?.X || fallback` rule) — a plain, correctly-typed native element otherwise,
// since Control's own fallback can't be a bare string tag (it takes `as`/`capId`/`pressed`, which
// a plain 'select'/'input'/'button' string doesn't understand).
function SelectField({ Control, capId, value, onChange, ariaLabel, options }) {
  const optionEls = options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)
  return Control
    ? <Control as="select" capId={capId} value={value} onChange={onChange} aria-label={ariaLabel}>{optionEls}</Control>
    : <select data-capability-id={capId} value={value} onChange={onChange} aria-label={ariaLabel}>{optionEls}</select>
}

function SearchField({ Control, capId, value, onChange, ariaLabel, placeholder }) {
  return Control
    ? <Control as="input" capId={capId} type="search" value={value} onChange={onChange} aria-label={ariaLabel} placeholder={placeholder} />
    : <input data-capability-id={capId} type="search" value={value} onChange={onChange} aria-label={ariaLabel} placeholder={placeholder} />
}

function ButtonField({ Control, onClick, ariaLabel, children }) {
  return Control
    ? <Control onClick={onClick} aria-label={ariaLabel}>{children}</Control>
    : <button type="button" onClick={onClick} aria-label={ariaLabel}>{children}</button>
}

/**
 * Absorbs Markets and News behind `?view=indexes|news` (see ROUTE-INVENTORY.md §2), which also
 * resolves the old `/market` (singular) vs `/markets` (plural) confusion by naming both as
 * views of one destination. Wires CAPABILITY-LEDGER.md §3 in full except two rows noted at their
 * render site: `chart.markets.growth-chart` (the full per-medium chart-renderer contract is out
 * of scope for this pass) and `link.markets.market-redirect` (a router-level `/market` redirect —
 * this file has no route table to add it to).
 */
export default function MarketsScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const Control = manifest.components?.Control || null
  const [searchParams, setSearchParams] = useSearchParams()
  const view = MARKETS_VIEWS.includes(searchParams.get('view')) ? searchParams.get('view') : 'indexes'

  // URL-addressability rule: every selector reads from the URL param first (no localStorage
  // fallback for these three — none existed before the rebuild, so there is nothing to fall
  // back to), and writes back on change. Defaults are omitted from the URL to keep it clean.
  const updateParams = (updates) => {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === undefined || value === '') next.delete(key)
      else next.set(key, value)
    }
    setSearchParams(next, { replace: true })
  }

  const { data: report, loading: reportLoading } = useData('report.json')

  if (reportLoading) {
    return <div {...cap('state.markets.loading')} role="status" aria-live="polite">Loading…</div>
  }
  if (!report?.market) {
    return <div {...cap(MARKETS_IDS.unavailable)} role="alert">Market data is unavailable in the latest refresh.</div>
  }

  return (
    <div data-screen="markets" data-view={view}>
      <Container {...cap(MARKETS_IDS.sessionBadge)}>
        <span data-testid="market-type">{report.market?.macro?.regime?.label || 'regime unavailable'}</span>
      </Container>
      {view === 'indexes'
        ? <IndexesView report={report} Container={Container} Control={Control} searchParams={searchParams} updateParams={updateParams} />
        : <NewsView Container={Container} Control={Control} searchParams={searchParams} updateParams={updateParams} />}
    </div>
  )
}

function IndexesView({ report, Container, Control, searchParams, updateParams }) {
  const spyQ = useData('etf/SPY.json')
  const qqqQ = useData('etf/QQQ.json')
  const diaQ = useData('etf/DIA.json')
  const iwmQ = useData('etf/IWM.json')
  const snapshots = { SPY: spyQ.data, QQQ: qqqQ.data, DIA: diaQ.data, IWM: iwmQ.data }

  const range = RANGE_KEYS.includes(searchParams.get('range')) ? searchParams.get('range') : '1D'
  const [query, setQuery] = useState(searchParams.get('q') || '')
  const [intraday, setIntraday] = useState(readIntraday)

  const coveredRows = useMemo(() => combineCoveredRows(report), [report])
  const rankedStocks = useMemo(() => rankDailyStocks(coveredRows), [coveredRows])
  const sectors = useMemo(() => rankDailySectors(coveredRows), [coveredRows])

  // No live quote overlay here (unlike the legacy page's `usePortfolioQuotes`): that hook
  // requires `useAuth`/FirebaseAuthContext, whose ~610kB SDK init HomeScreen/PortfolioScreen
  // deliberately keep out of their eager-loaded paths by splitting the Firebase-dependent part
  // into its own lazily-loaded panel file. MarketsScreen is statically imported by
  // MediumShell.jsx, and this pass is scoped to this one file with no sibling to split into, so
  // index moves are computed from the committed close-to-close snapshot instead — real data,
  // just without the live-quote overlay.
  const indexes = useMemo(() => (
    INDEXES
      .map((index) => {
        const series = priceSeriesFromSnapshot(snapshots[index.ticker])
        return { ...index, series, move: dailyMove({ history: { closes: series.values } }) }
      })
      .filter((index) => index.move.available)
      .sort((left, right) => right.move.pct - left.move.pct)
  ), [spyQ.data, qqqQ.data, diaQ.data, iwmQ.data])

  const selected = indexes.find((index) => index.ticker === 'SPY') || indexes[0]
  const recordedToday = selected ? intraday[selected.ticker] || [] : []
  const chart = selected
    ? (range === '1D' && recordedToday.length > 1
        ? { dates: recordedToday.map((point) => point.at), values: recordedToday.map((point) => point.price) }
        : sliceRange(selected.series, range))
    : null

  const normalizedQuery = query.trim().toUpperCase()
  const result = normalizedQuery
    ? coveredRows.find((row) => row.ticker === normalizedQuery)
      || coveredRows.find((row) => String(row.name || '').toUpperCase().includes(normalizedQuery))
    : null
  const resultMove = result ? dailyMove(result) : null

  const top = rankedStocks[0]
  const worst = rankedStocks.at(-1)

  // Re-fetch the committed ETF snapshots every five minutes while this view stays mounted, so
  // `link.markets.intraday-accumulation`'s rolling per-day log keeps polling for a new published
  // close on the same cadence the legacy live-quote feed used — see the comment on `indexes`
  // above for why this reads the committed snapshot rather than a live quote.
  useEffect(() => {
    const id = setInterval(() => {
      spyQ.reload().catch(() => {})
      qqqQ.reload().catch(() => {})
      diaQ.reload().catch(() => {})
      iwmQ.reload().catch(() => {})
    }, INTRADAY_POLL_MS)
    return () => clearInterval(id)
  }, [spyQ.reload, qqqQ.reload, diaQ.reload, iwmQ.reload])

  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10)
    const now = new Date().toISOString()
    setIntraday((current) => {
      let changed = false
      const next = { ...current }
      for (const index of indexes) {
        const price = index.series.values.at(-1)
        if (!Number.isFinite(price)) continue
        const sameDay = (next[index.ticker] || []).filter((point) => String(point.at).slice(0, 10) === today)
        const last = sameDay.at(-1)
        if (last && last.price === price) {
          next[index.ticker] = sameDay
          continue
        }
        next[index.ticker] = [...sameDay, { at: now, price }].slice(-120)
        changed = true
      }
      if (!changed) return current
      writeIntraday(next)
      return next
    })
    // Keyed on the fetched payloads themselves, not the derived `indexes` array identity
    // (which is a new array every render regardless of whether the underlying data changed).
  }, [spyQ.data, qqqQ.data, diaQ.data, iwmQ.data])

  const onRangeChange = (event) => updateParams({ range: event.target.value === '1D' ? null : event.target.value })
  const onQueryChange = (event) => {
    const value = event.target.value
    setQuery(value)
    updateParams({ q: value || null })
  }

  return (
    <>
      <Container {...cap('control.markets.time-range')}>
        <SelectField
          Control={Control} capId="control.markets.time-range" value={range} onChange={onRangeChange}
          ariaLabel="Time range" options={RANGE_KEYS.map((item) => ({ value: item, label: item === '1D' ? 'Today' : item }))}
        />
      </Container>

      <Container {...cap('figure.markets.stat-cards')} aria-label="Market leaders and laggards">
        <article data-testid="stat-index-leader"><span>Index ETF leader</span><strong>{indexes[0]?.ticker || 'Unavailable'}</strong><em>{signedPct(indexes[0]?.move.pct)}</em></article>
        <article data-testid="stat-hot-sector"><span>Hottest sector</span><strong>{sectors[0]?.sector || 'Unavailable'}</strong><em>{signedPct(sectors[0]?.averagePct)}</em></article>
        <article data-testid="stat-cold-sector"><span>Weakest sector</span><strong>{sectors.at(-1)?.sector || 'Unavailable'}</strong><em>{signedPct(sectors.at(-1)?.averagePct)}</em></article>
        <article data-testid="stat-top-stock"><span>Top stock</span><strong>{top?.ticker || 'Unavailable'}</strong><em>{signedPct(top?.dailyMove.pct)}</em></article>
        <article data-testid="stat-worst-stock"><span>Worst stock</span><strong>{worst?.ticker || 'Unavailable'}</strong><em>{signedPct(worst?.dailyMove.pct)}</em></article>
      </Container>

      <Container {...cap('link.markets.intraday-accumulation')} data-testid="intraday-marker">
        <p {...cap('disclosure.markets.live-observation-count')} data-testid="observation-count">
          {recordedToday.length > 1
            ? `${recordedToday.length} live observations recorded today at five-minute intervals.`
            : 'The 1D fallback is the latest close-to-close move; five-minute live observations build while this tab is open.'}
        </p>
        {chart?.dates.length > 1
          ? <p {...cap('disclosure.markets.chart-caption')} data-testid="chart-caption">{`${selected.ticker} adjusted closes through ${chart.dates.at(-1)}.`}</p>
          : <div {...cap('state.markets.two-observations-needed')} role="status" data-testid="two-observations-needed">Two market observations are required to draw this range.</div>}
      </Container>

      <Container {...cap('figure.markets.index-strip')} aria-label="Major index ETF performance">
        {indexes.map((index) => (
          <article key={index.ticker} data-testid={`index-${index.ticker}`}>
            <span>{index.ticker}<small>{index.label}</small></span>
            <strong>{money(index.move.price)}</strong>
            <em>{signedPct(index.move.pct)}</em>
          </article>
        ))}
      </Container>

      <Container {...cap('control.markets.direct-lookup')}>
        <SearchField
          Control={Control} capId="control.markets.direct-lookup" value={query} onChange={onQueryChange}
          ariaLabel="Stock ticker or company" placeholder="Try AAPL or Apple"
        />
      </Container>

      {normalizedQuery && (result
        ? (
          <Container {...cap('figure.markets.lookup-result')} data-testid="lookup-result">
            <strong>{result.ticker}</strong><span>{result.name}</span>
            <b data-testid="lookup-price">{money(resultMove?.price ?? result.price)}</b>
            <b data-testid="lookup-today">{signedPct(resultMove?.pct)}</b>
            <b data-testid="lookup-20d">{signedPct(result.technical_detail?.return_20d)}</b>
          </Container>
        )
        : <p {...cap('state.markets.no-lookup-match')} role="status" data-testid="no-lookup-match">{`No covered ticker matched “${query}”.`}</p>)}
    </>
  )
}

function NewsView({ Container, Control, searchParams, updateParams }) {
  const { data: advisor, loading } = useData('advisor.json')
  const sortKey = NEWS_SORT_OPTIONS.some((option) => option.key === searchParams.get('sort')) ? searchParams.get('sort') : 'date'
  const direction = searchParams.get('dir') === 'asc' ? 'asc' : 'desc'

  if (loading) {
    return <div {...cap('state.markets.news-loading')} role="status" aria-live="polite">Loading…</div>
  }
  if (!advisor) {
    return <div {...cap('state.markets.news-empty')} role="status" data-testid="news-empty">No news data is available in the latest refresh.</div>
  }

  const usMarket = advisor.market?.status?.find((row) => row.region === 'United States' && row.market_type === 'Equity')
  const publishedTickers = new Set((advisor.research || []).map((row) => row.ticker))
  const news = sortNews(advisor.news || [], sortKey, direction)
  const publishedNews = news.filter((item) => publishedTickers.has(item.ticker))
  const discoveryNews = news.filter((item) => !publishedTickers.has(item.ticker))

  const onSortKey = (event) => {
    const next = nextNewsSort({ key: sortKey, direction }, event.target.value)
    updateParams({ sort: next.key === 'date' ? null : next.key, dir: next.direction === 'desc' ? null : next.direction })
  }
  const onToggleDirection = () => {
    const nextDirection = direction === 'asc' ? 'desc' : 'asc'
    updateParams({ dir: nextDirection === 'desc' ? null : nextDirection })
  }

  return (
    <>
      <Container {...cap('figure.markets.status-callout')} data-testid="status-callout">
        {usMarket
          ? `U.S. equities: ${usMarket.current_status} · ${usMarket.primary_exchanges} · regular session ${usMarket.local_open}–${usMarket.local_close} local exchange time`
          : 'U.S. equity market status unavailable.'}
      </Container>

      <p {...cap('disclosure.markets.news-supporting-evidence')} data-testid="news-supporting-evidence">
        Company news and sentiment are supporting evidence–not a substitute for earnings, cash flow, or balance-sheet quality.
      </p>

      {news.length > 0 && (
        <Container {...cap('control.markets.news-sort')} aria-label="News sorting controls">
          <SelectField
            Control={Control} capId="control.markets.news-sort" value={sortKey} onChange={onSortKey}
            ariaLabel="Sort news" options={NEWS_SORT_OPTIONS.map((option) => ({ value: option.key, label: option.label }))}
          />
          <ButtonField Control={Control} onClick={onToggleDirection} ariaLabel="Reverse news sort order">
            {direction === 'asc' ? 'Ascending ↑' : 'Descending ↓'}
          </ButtonField>
        </Container>
      )}

      <h2>News for published research</h2>
      <Container {...cap('figure.markets.published-research-news')} data-testid="published-news">
        {publishedNews.map((item, index) => (
          <a key={`${item.url}-${index}`} href={item.url} target="_blank" rel="noreferrer" data-testid="news-card">
            <span>{item.ticker}</span>
            <strong>{item.title}</strong>
            <p>{item.summary}</p>
          </a>
        ))}
      </Container>
      {!publishedNews.length && (
        <div {...cap('state.markets.no-recent-articles')} role="status" data-testid="no-recent-articles">
          No recent articles matched the published research companies.
        </div>
      )}

      {discoveryNews.length > 0 && (
        <>
          <h2>More companies to research</h2>
          <p {...cap('disclosure.markets.news-not-buy-signal')} data-testid="news-not-buy-signal">
            Stronger broader-universe candidates with recent sourced coverage. News can surface an idea, but it is not a buy signal by itself.
          </p>
          <Container {...cap('figure.markets.discovery-news')} data-testid="discovery-news">
            {discoveryNews.map((item, index) => (
              <a key={`${item.url}-${index}`} href={item.url} target="_blank" rel="noreferrer" data-testid="discovery-news-card">
                <span>{item.ticker}</span>
                <strong>{item.title}</strong>
                <p>{item.summary}</p>
              </a>
            ))}
          </Container>
        </>
      )}

      {!news.length && (
        <div {...cap('state.markets.no-company-news')} role="status" data-testid="no-company-news">
          No company news returned in this refresh.
        </div>
      )}
    </>
  )
}
