import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, MetricPills, Move, Loading, Empty } from '../components/Bits.jsx'
import { ActionPill } from '../components/ActionGuidance.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import { getRecommendation } from '../lib/recommendation'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Sparkline from '../components/Sparkline.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'

const SORTS = {
  score: ['Research score', (a, b) => (b.score ?? -1) - (a.score ?? -1)],
  return: ['20-day return', (a, b) => (b.technical_detail?.return_20d ?? -999) - (a.technical_detail?.return_20d ?? -999)],
  valuation: ['Sector valuation', (a, b) => (b.sector_valuation_percentile ?? -1) - (a.sector_valuation_percentile ?? -1)],
  quality: ['Fundamentals', (a, b) => (b.components?.fundamentals ?? -1) - (a.components?.fundamentals ?? -1)],
  confidence: ['Data confidence', (a, b) => (b.confidence ?? -1) - (a.confidence ?? -1)],
}

const etfStance = (score) => score >= 80 ? 'Attractive' : score >= 70 ? 'Promising' : score >= 55 ? 'Neutral' : 'Caution'

function normalizeEtf(row) {
  const score = row.scores?.overall ?? row.quality_score ?? null
  return {
    ...row,
    is_etf: true,
    asset_type: 'etf',
    score,
    stance: etfStance(score),
    components: {
      fundamentals: row.scores?.quality,
      market_behavior: row.scores?.performance,
      news_sentiment: null,
    },
    fundamental_categories: row.scores,
    technical_detail: {
      return_20d: row.returns?.['1m'],
      return_252d: row.returns?.['1y'],
      max_drawdown_252d: row.max_drawdown,
      beta: row.beta,
    },
    strengths: [
      row.expense_ratio != null ? `${row.expense_ratio.toFixed(2)}% expense ratio` : null,
      row.peer_rank ? `#${row.peer_rank} of ${row.peer_group_size} in its peer group` : null,
    ].filter(Boolean),
    risks: [
      row.max_drawdown != null ? `${Math.abs(row.max_drawdown).toFixed(1)}% maximum drawdown in the measured window` : null,
      row.tracking_error_pct != null ? `${row.tracking_error_pct.toFixed(2)}% tracking error` : null,
    ].filter(Boolean),
    researchType: 'ETF',
  }
}

function ResearchCard({ row, rank, onOpen, held, buying, buyStatus, onBuy }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <article className="research-mobile-card">
      <div className="research-card-head">
        <span className="rank-badge">#{rank}</span>
        <CompanyLogo company={row} size={42} />
        <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
        <span className="mobile-score">{row.score}</span>
      </div>
      <div className="research-card-badges">
        <Tier label={row.stance} />
        {row.is_etf ? <span className="chip asset-chip">ETF</span> : <ActionPill recommendation={getRecommendation(row)} />}
        <span className={`holding-chip ${held ? 'held' : ''}`}>{held ? 'Bought' : 'Not bought'}</span>
      </div>
      <dl className="research-card-metrics">
        <div><dt>Fundamentals</dt><dd>{row.components?.fundamentals == null ? '—' : Math.round(row.components.fundamentals)}</dd></div>
        <div><dt>20-day return</dt><dd><Move pct={row.technical_detail?.return_20d} /></dd></div>
        <div><dt>Data confidence</dt><dd>{Math.round((row.confidence || 0) * 100)}%</dd></div>
      </dl>
      <Sparkline values={(row.history?.closes || []).slice(-22)} label={`${row.ticker} one-month daily close trend`} height={54} className="research-card-spark" />
      <button className="expand-button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        {expanded ? 'Hide secondary metrics' : 'Show secondary metrics'}
        <Icon name="chevron" size={17} className={expanded ? 'rotated' : ''} />
      </button>
      {expanded && (
        <div className="research-expanded">
          <MetricPills {...row} isEtf={row.is_etf} fundamental_coverage={row.fundamental_detail?.coverage} />
          <div className="evidence-grid">
            <div><b>Strengths</b><ul>{row.strengths?.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div><b>Risks & gaps</b><ul>{row.risks?.map((item) => <li key={item}>{item}</li>)}</ul></div>
          </div>
          <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
        </div>
      )}
      <div className="research-trade-row">
        <span>{held ? 'Already tracked in your portfolio' : row.price ? `Today · $100 at $${Number(row.price).toFixed(2)} = ${(100 / Number(row.price)).toFixed(4)} shares` : 'Current price unavailable'}</span>
        <button className={held ? 'secondary-button compact' : 'primary-button compact'} disabled={held || buying || !row.price} onClick={() => onBuy(row)}>
          {held ? 'Bought' : buying ? 'Adding…' : 'Buy $100'}
        </button>
      </div>
      {buyStatus && <p className={`research-trade-status ${buyStatus.error ? 'error' : ''}`} role="status">{buyStatus.message}</p>}
    </article>
  )
}

export default function Picks() {
  const { data, loading } = useData('advisor.json')
  const { data: etfData, loading: etfLoading } = useData('etfs.json')
  const { positions, loading: portfolioLoading, addPosition } = useFirebasePortfolio()
  const [sector, setSector] = useState('all')
  const [sort, setSort] = useState('score')
  const [query, setQuery] = useState('')
  const [assetType, setAssetType] = useState('all')
  const [ownership, setOwnership] = useState('all')
  const [selectedStock, setSelectedStock] = useState(null)
  const [buyingTicker, setBuyingTicker] = useState('')
  const [buyStatuses, setBuyStatuses] = useState({})
  const [tradeNotice, setTradeNotice] = useState(null)

  const stockResearch = data?.research || []
  const research = useMemo(() => [
    ...stockResearch.map((row) => ({ ...row, researchType: 'Stock' })),
    ...(etfData?.etfs || []).map(normalizeEtf),
  ], [stockResearch, etfData])
  const heldTickers = useMemo(() => new Set(positions.map((position) => String(position.ticker || '').toUpperCase())), [positions])
  const sectors = useMemo(() => [...new Set(research.map((row) => row.sector).filter(Boolean))].sort(), [research])

  if (loading || etfLoading || portfolioLoading) return <Loading />
  if (!data?.research) return <Empty />

  const normalized = query.trim().toLowerCase()
  const rows = research
    .filter((row) => sector === 'all' || row.sector === sector)
    .filter((row) => assetType === 'all' || (assetType === 'etf') === Boolean(row.is_etf))
    .filter((row) => ownership === 'all' || (ownership === 'bought') === heldTickers.has(row.ticker))
    .filter((row) => !normalized || row.ticker.toLowerCase().includes(normalized) || String(row.name || '').toLowerCase().includes(normalized))
    .slice().sort(SORTS[sort][1])

  const handleQuickBuy = async (row) => {
    const price = Number(row.price)
    if (!Number.isFinite(price) || price <= 0 || heldTickers.has(row.ticker)) return
    const shares = Number((100 / price).toFixed(6))
    const localToday = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)
    setBuyingTicker(row.ticker)
    setBuyStatuses((current) => ({ ...current, [row.ticker]: null }))
    const result = await addPosition(row.ticker, shares, price, localToday, 'share')
    setBuyingTicker('')
    const notice = result?.success
      ? { message: `${shares.toFixed(4)} ${row.ticker} shares added at $${price.toFixed(2)} for $100 on ${localToday}.` }
      : { error: true, message: result?.error ? `Could not add ${row.ticker}: ${result.error}` : 'Sign in to add this trade to your portfolio.' }
    setBuyStatuses((current) => ({ ...current, [row.ticker]: notice }))
    setTradeNotice(notice)
  }

  return (
    <>
      <div className="page-head">
        <div><span className="eyebrow">Evidence library</span><h1 className="page-title">Company <span className="accent">research</span></h1>
          <p className="page-sub">Compare the ranked evidence behind every published company. Confidence measures data completeness, not expected performance.</p></div>
        <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
      </div>

      <div className="research-toolbar">
        <label className="search-field">
          <Icon name="research" size={18} /><span className="sr-only">Search companies</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ticker or company" />
        </label>
        <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
          <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
        </select></label>
        <label><span className="sr-only">Sort research</span><select value={sort} onChange={(event) => setSort(event.target.value)}>
          {Object.entries(SORTS).map(([key, [label]]) => <option key={key} value={key}>Sort: {label}</option>)}
        </select></label>
        <label><span className="sr-only">Filter by asset type</span><select value={assetType} onChange={(event) => setAssetType(event.target.value)}>
          <option value="all">Stocks &amp; ETFs</option><option value="stock">Stocks</option><option value="etf">ETFs</option>
        </select></label>
        <label><span className="sr-only">Filter by ownership</span><select value={ownership} onChange={(event) => setOwnership(event.target.value)}>
          <option value="all">Bought &amp; not bought</option><option value="bought">Bought</option><option value="not-bought">Not bought</option>
        </select></label>
      </div>
      {tradeNotice && <div className={`research-trade-notice ${tradeNotice.error ? 'error' : ''}`} role="status" aria-live="polite">{tradeNotice.message}</div>}

      <div className="research-mobile-list">
        {rows.map((row) => <ResearchCard key={row.ticker} row={row}
          rank={rows.findIndex((item) => item.ticker === row.ticker) + 1} onOpen={setSelectedStock}
          held={heldTickers.has(row.ticker)} buying={buyingTicker === row.ticker}
          buyStatus={buyStatuses[row.ticker]} onBuy={handleQuickBuy} />)}
      </div>

      <div className="research-table card">
        <table>
          <thead><tr>
            <th scope="col">Rank</th><th scope="col">Company</th><th scope="col">Type</th><th scope="col">Research rating</th><th scope="col">Signal</th>
            <th scope="col" className="num">Score</th><th scope="col" className="num">Fundamentals</th>
            <th scope="col" className="num">20-day return</th><th scope="col" className="num">Confidence</th><th scope="col">Portfolio</th><th scope="col"><span className="sr-only">Open</span></th>
          </tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.ticker}>
              <td className="rank">#{rows.findIndex((item) => item.ticker === row.ticker) + 1}</td>
              <td><div className="table-company company-with-logo"><CompanyLogo company={row} size={34} /><div><b>{row.ticker}</b><span>{row.name}</span><small>{row.sector || 'Unclassified'}</small></div></div></td>
              <td><span className="chip asset-chip">{row.is_etf ? 'ETF' : 'Stock'}</span></td>
              <td><Tier label={row.stance} /></td><td>{row.is_etf ? '—' : <ActionPill recommendation={getRecommendation(row)} />}</td>
              <td className="mono num score-cell">{row.score}</td>
              <td className="mono num">{row.components?.fundamentals == null ? '—' : Math.round(row.components.fundamentals)}</td>
              <td className="num"><Move pct={row.technical_detail?.return_20d} /></td>
              <td className="mono num">{Math.round((row.confidence || 0) * 100)}%</td>
              <td>{heldTickers.has(row.ticker)
                ? <span className="holding-chip held">Bought</span>
                : <button className="primary-button compact research-table-buy" disabled={buyingTicker === row.ticker || !row.price} onClick={() => handleQuickBuy(row)}>{buyingTicker === row.ticker ? 'Adding…' : 'Buy $100'}</button>}</td>
              <td><button className="icon-button" onClick={() => setSelectedStock(row)} aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      {!rows.length && <Empty note="No companies match those filters." />}
      <div className="disclaimer">Research includes {stockResearch.length} ranked companies and {etfData?.etfs?.length || 0} ETFs. “Buy $100” records a fractional-share portfolio entry at the displayed current price and today’s date; it does not place a brokerage order. Rankings do not imply suitability or portfolio allocation.</div>
      {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
    </>
  )
}
