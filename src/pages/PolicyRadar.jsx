import { useState } from 'react'
import { useData } from '../lib/useData'
import { Loading, Empty } from '../components/Bits.jsx'
import { nextNewsSort, NEWS_SORT_OPTIONS, sortNews } from '../lib/newsSort.js'

function NewsSortToolbar({ sort, onSortKey, onToggleDirection }) {
  return (
    <div className="news-sort-toolbar" aria-label="News sorting controls">
      <label>
        <span>Sort news</span>
        <select value={sort.key} onChange={(event) => onSortKey(event.target.value)}>
          {NEWS_SORT_OPTIONS.map((option) => (
            <option key={option.key} value={option.key}>{option.label}</option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button news-sort-direction"
        onClick={onToggleDirection}
        aria-label="Reverse news sort order"
      >
        {sort.direction === 'asc' ? 'Ascending ↑' : 'Descending ↓'}
      </button>
    </div>
  )
}

function NewsCard({ item, index }) {
  return <a className="card card-pad news-card" href={item.url} target="_blank" rel="noreferrer"
    key={`${item.url}-${index}`}>
    <div>
      <span className="chip">{item.ticker}</span>{' '}
      <span className="chip">{item.source || 'Unknown source'}</span>{' '}
      <span className="chip">{item.content_type === 'filing' ? 'Source filing' : 'News commentary'}</span>{' '}
      {item.research_score != null && <span className="chip">Score {item.research_score}</span>}
    </div>
    <strong>{item.title}</strong>
    <p>{item.summary}</p>
    {item.research_rank && <small className="news-context">
      {item.published_research
        ? `Published research rank #${item.research_rank}`
        : `Broader-universe research rank #${item.research_rank}`}
    </small>}
  </a>
}

export default function PolicyRadar() {
  const { data, loading } = useData('advisor.json')
  const [newsSort, setNewsSort] = useState({ key: 'date', direction: 'desc' })
  if (loading) return <Loading />
  if (!data) return <Empty />
  const usMarket = data.market?.status?.find(row => row.region === 'United States' && row.market_type === 'Equity')
  const publishedTickers = new Set((data.research || []).map((row) => row.ticker))
  const news = sortNews(data.news || [], newsSort.key, newsSort.direction)
  const publishedNews = news.filter((item) => publishedTickers.has(item.ticker))
  const discoveryNews = news.filter((item) => !publishedTickers.has(item.ticker))
  const setSortKey = (key) => setNewsSort(nextNewsSort(newsSort, key))
  const toggleSortDirection = () => setNewsSort({ ...newsSort, direction: newsSort.direction === 'asc' ? 'desc' : 'asc' })
  return <>
    <div className="page-head"><div><h1 className="page-title">Market <span className="accent">pulse</span></h1><p className="page-sub">Company news and sentiment are supporting evidence–not a substitute for earnings, cash flow, or balance-sheet quality.</p></div></div>
    {usMarket && <div className="callout"><strong>U.S. equities: {usMarket.current_status}</strong> · {usMarket.primary_exchanges} · regular session {usMarket.local_open}–{usMarket.local_close} local exchange time</div>}
    {news.length > 0 && <NewsSortToolbar sort={newsSort} onSortKey={setSortKey} onToggleDirection={toggleSortDirection} />}
    <div className="sec-label">News for published research</div>
    <div className="grid">{publishedNews.map((item, index) => <NewsCard item={item} index={index} key={`${item.url}-${index}`} />)}</div>
    {!publishedNews.length && <div className="inline-empty">No recent articles matched the published research companies.</div>}

    {discoveryNews.length > 0 && <>
      <div className="sec-label">More companies to research</div>
      <p className="body-copy news-discovery-note">
        Stronger broader-universe candidates with recent sourced coverage. News can surface an idea,
        but it is not a buy signal by itself.
      </p>
      <div className="grid">{discoveryNews.map((item, index) => <NewsCard item={item} index={index} key={`${item.url}-${index}`} />)}</div>
    </>}
    {!news.length && <Empty note="No company news returned in this refresh." />}
  </>
}
