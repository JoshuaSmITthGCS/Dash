import { useState } from 'react'
import { useData } from '../lib/useData'
import { Loading, Empty, RatingBadge } from '../components/Bits.jsx'
import { nextNewsSort, NEWS_SORT_OPTIONS, sortNews } from '../lib/newsSort.js'
import { buildRatingContext, researchRating } from '../lib/researchRating.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'

// Research and screen_universe never share a ticker (research is the published subset,
// screen_universe the broader unpublished pool) - see FastGrowthScreen.jsx/ThemeExposureScreen.jsx
// for the same combine-by-ticker pattern used to look a news item's row up either way.
function buildUniverseByTicker(research, screenUniverse) {
  return new Map([...research, ...screenUniverse].map((row) => [row.ticker, row]))
}

// Same $/share x shares math as Portfolio.jsx's allocationPct, just without that page's live
// quote refresh - good enough for a "how big is this in my book" sort on a news list.
function buildAllocationByTicker(positions, priceData) {
  const valueByTicker = new Map()
  for (const position of positions) {
    const ticker = String(position.ticker || '').trim().toUpperCase()
    const price = priceData[ticker]?.price
    if (!Number.isFinite(price) || !Number.isFinite(position.shares)) continue
    valueByTicker.set(ticker, (valueByTicker.get(ticker) || 0) + position.shares * price)
  }
  const totalValue = [...valueByTicker.values()].reduce((sum, value) => sum + value, 0)
  const allocationByTicker = new Map()
  if (totalValue > 0) {
    for (const [ticker, value] of valueByTicker) allocationByTicker.set(ticker, (value / totalValue) * 100)
  }
  return allocationByTicker
}

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

// The subset of news_intelligence.py's event taxonomy that names a discrete, idiosyncratic
// catalyst rather than routine coverage (earnings/guidance/product/analyst chatter) - the
// "why did this specific thing happen" bucket: litigation, a regulatory action, a deal, a
// government-contract-or-stake event, a congressional disclosure naming the ticker, or a
// macro/policy shock (tariffs, rate decisions). Kept in sync by hand with
// pipeline/config/settings.json's news_intelligence.event_type_markers - there is no schema
// linking the two, so a new marker added there needs a decision here too.
const IDIOSYNCRATIC_EVENT_TYPES = ['litigation', 'regulatory', 'm_and_a', 'government_contract', 'political_disclosure', 'macro_exposure']

const EVENT_TYPE_LABELS = {
  litigation: 'Litigation',
  regulatory: 'Regulatory action',
  m_and_a: 'M&A',
  government_contract: 'Government contract/stake',
  political_disclosure: 'Political disclosure',
  macro_exposure: 'Macro/policy',
}

function isIdiosyncratic(item) {
  return (item.event_types || []).some((type) => IDIOSYNCRATIC_EVENT_TYPES.includes(type)) || Boolean(item.affiliation)
}

function EventTypeChips({ item }) {
  const types = (item.event_types || []).filter((type) => IDIOSYNCRATIC_EVENT_TYPES.includes(type))
  if (!types.length && !item.affiliation) return null
  return <div className="news-catalyst-tags">
    {types.map((type) => <span key={type} className="chip catalyst-tag">{EVENT_TYPE_LABELS[type] || type}</span>)}
    {item.affiliation && (
      <span className="chip catalyst-tag catalyst-tag-affiliation" title={item.affiliation.individuals?.map((person) =>
        `${person.name} — ${person.role}${person.note ? `: ${person.note}` : ''}`).join('\n')}>
        {item.affiliation.label}
      </span>
    )}
  </div>
}

function NewsCard({ item, index }) {
  return <a className="card card-pad news-card" href={item.url} target="_blank" rel="noreferrer"
    key={`${item.url}-${index}`}>
    <div>
      <span className="chip">{item.ticker}</span>{' '}
      <span className="chip">{item.source || 'Unknown source'}</span>{' '}
      <span className="chip">{item.content_type === 'filing' ? 'Source filing' : 'News commentary'}</span>{' '}
      {item.research_score != null && <span className="chip">Score {item.research_score}</span>}{' '}
      <RatingBadge value={item.rating} title="Rating: -5 (worst) to +5 (best) vs. its research pool" />{' '}
      {item.headline_direction != null && (
        <RatingBadge
          value={Math.round(item.headline_direction * 10) / 10}
          title="Headline sentiment: -1 (negative) to +1 (positive)"
        />
      )}{' '}
      {item.allocationPct != null && <span className="chip">{item.allocationPct.toFixed(1)}% of portfolio</span>}
    </div>
    <strong>{item.title}</strong>
    <p>{item.summary}</p>
    <EventTypeChips item={item} />
    {item.research_rank != null && <small className="news-context">
      {item.published_research
        ? `Published research rank #${item.research_rank}`
        : `Broader-universe research rank #${item.research_rank}`}
    </small>}
  </a>
}

export default function PolicyRadar() {
  const { data, loading } = useData('advisor.json')
  const { positions } = useFirebasePortfolio()
  const [newsSort, setNewsSort] = useState({ key: 'date', direction: 'desc' })
  if (loading) return <Loading />
  if (!data) return <Empty />
  const usMarket = data.market?.status?.find(row => row.region === 'United States' && row.market_type === 'Equity')
  const research = data.research || []
  const screenUniverse = data.screen_universe || []
  const publishedTickers = new Set(research.map((row) => row.ticker))

  const ratingContext = buildRatingContext([...research, ...screenUniverse])
  const universeByTicker = buildUniverseByTicker(research, screenUniverse)
  const priceData = buildPortfolioPriceData(screenUniverse, data.portfolio_coverage || [], research)
  const allocationByTicker = buildAllocationByTicker(positions, priceData)
  const enrichedNews = (data.news || []).map((item) => {
    const ticker = String(item.ticker || '').trim().toUpperCase()
    return {
      ...item,
      rating: researchRating(universeByTicker.get(item.ticker), ratingContext),
      allocationPct: allocationByTicker.get(ticker) ?? null,
    }
  })

  const news = sortNews(enrichedNews, newsSort.key, newsSort.direction)
  const publishedNews = news.filter((item) => publishedTickers.has(item.ticker))
  const discoveryNews = news.filter((item) => !publishedTickers.has(item.ticker))
  const idiosyncraticNews = news.filter(isIdiosyncratic)
  const setSortKey = (key) => setNewsSort(nextNewsSort(newsSort, key))
  const toggleSortDirection = () => setNewsSort({ ...newsSort, direction: newsSort.direction === 'asc' ? 'desc' : 'asc' })
  return <>
    <div className="page-head"><div><h1 className="page-title">Market <span className="accent">pulse</span></h1><p className="page-sub">Company news and sentiment are supporting evidence–not a substitute for earnings, cash flow, or balance-sheet quality.</p></div></div>
    {usMarket && <div className="callout"><strong>U.S. equities: {usMarket.current_status}</strong> · {usMarket.primary_exchanges} · regular session {usMarket.local_open}–{usMarket.local_close} local exchange time</div>}
    {news.length > 0 && <NewsSortToolbar sort={newsSort} onSortKey={setSortKey} onToggleDirection={toggleSortDirection} />}

    {idiosyncraticNews.length > 0 && <>
      <div className="sec-label">Idiosyncratic catalysts</div>
      <p className="body-copy news-discovery-note">
        A single discrete event rather than routine coverage - litigation, a regulatory action, a deal,
        a government contract or equity stake, a congressional disclosure, or a tariff/macro-policy
        shock - plus any disclosed ownership or leadership affiliation on file for that ticker. These
        are the movers that don't fit a repeatable screen; each is a one-off to look into on its own,
        not a scored signal.
      </p>
      <div className="grid">{idiosyncraticNews.map((item, index) => <NewsCard item={item} index={index} key={`idio-${item.url}-${index}`} />)}</div>
    </>}

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
