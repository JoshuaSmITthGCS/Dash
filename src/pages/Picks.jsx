import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, MetricPills, Move, Loading, Empty } from '../components/Bits.jsx'
import { ActionPill } from '../components/ActionGuidance.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import { getRecommendation } from '../lib/recommendation'

const SORTS = {
  score: ['Research score', (a, b) => b.score - a.score],
  return: ['20-day return', (a, b) => (b.technical_detail?.return_20d ?? -999) - (a.technical_detail?.return_20d ?? -999)],
  valuation: ['Sector valuation', (a, b) => (b.sector_valuation_percentile ?? -1) - (a.sector_valuation_percentile ?? -1)],
  quality: ['Fundamentals', (a, b) => (b.components?.fundamentals ?? -1) - (a.components?.fundamentals ?? -1)],
  confidence: ['Data confidence', (a, b) => (b.confidence ?? -1) - (a.confidence ?? -1)],
}

function ResearchCard({ row, rank, onOpen }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <article className="research-mobile-card">
      <div className="research-card-head">
        <span className="rank-badge">#{rank}</span>
        <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
        <span className="mobile-score">{row.score}</span>
      </div>
      <div className="research-card-badges"><Tier label={row.stance} /><ActionPill recommendation={getRecommendation(row)} /></div>
      <dl className="research-card-metrics">
        <div><dt>Fundamentals</dt><dd>{row.components?.fundamentals == null ? '—' : Math.round(row.components.fundamentals)}</dd></div>
        <div><dt>20-day return</dt><dd><Move pct={row.technical_detail?.return_20d} /></dd></div>
        <div><dt>Data confidence</dt><dd>{Math.round((row.confidence || 0) * 100)}%</dd></div>
      </dl>
      <button className="expand-button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        {expanded ? 'Hide secondary metrics' : 'Show secondary metrics'}
        <Icon name="chevron" size={17} className={expanded ? 'rotated' : ''} />
      </button>
      {expanded && (
        <div className="research-expanded">
          <MetricPills {...row} fundamental_coverage={row.fundamental_detail?.coverage} />
          <div className="evidence-grid">
            <div><b>Strengths</b><ul>{row.strengths?.map((item) => <li key={item}>{item}</li>)}</ul></div>
            <div><b>Risks & gaps</b><ul>{row.risks?.map((item) => <li key={item}>{item}</li>)}</ul></div>
          </div>
          <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
        </div>
      )}
    </article>
  )
}

export default function Picks() {
  const { data, loading } = useData('advisor.json')
  const [sector, setSector] = useState('all')
  const [sort, setSort] = useState('score')
  const [query, setQuery] = useState('')
  const [selectedStock, setSelectedStock] = useState(null)

  const research = data?.research || []
  const sectors = useMemo(() => [...new Set(research.map((row) => row.sector).filter(Boolean))].sort(), [research])

  if (loading) return <Loading />
  if (!data?.research) return <Empty />

  const normalized = query.trim().toLowerCase()
  const rows = research
    .filter((row) => sector === 'all' || row.sector === sector)
    .filter((row) => !normalized || row.ticker.toLowerCase().includes(normalized) || row.name.toLowerCase().includes(normalized))
    .slice().sort(SORTS[sort][1])

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
      </div>

      <div className="research-mobile-list">
        {rows.map((row) => <ResearchCard key={row.ticker} row={row}
          rank={research.findIndex((item) => item.ticker === row.ticker) + 1} onOpen={setSelectedStock} />)}
      </div>

      <div className="research-table card">
        <table>
          <thead><tr>
            <th scope="col">Rank</th><th scope="col">Company</th><th scope="col">Research rating</th><th scope="col">Signal</th>
            <th scope="col" className="num">Score</th><th scope="col" className="num">Fundamentals</th>
            <th scope="col" className="num">20-day return</th><th scope="col" className="num">Confidence</th><th scope="col"><span className="sr-only">Open</span></th>
          </tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.ticker}>
              <td className="rank">#{research.findIndex((item) => item.ticker === row.ticker) + 1}</td>
              <td><div className="table-company"><b>{row.ticker}</b><span>{row.name}</span><small>{row.sector || 'Unclassified'}</small></div></td>
              <td><Tier label={row.stance} /></td><td><ActionPill recommendation={getRecommendation(row)} /></td>
              <td className="mono num score-cell">{row.score}</td>
              <td className="mono num">{row.components?.fundamentals == null ? '—' : Math.round(row.components.fundamentals)}</td>
              <td className="num"><Move pct={row.technical_detail?.return_20d} /></td>
              <td className="mono num">{Math.round((row.confidence || 0) * 100)}%</td>
              <td><button className="icon-button" onClick={() => setSelectedStock(row)} aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button></td>
            </tr>
          ))}</tbody>
        </table>
      </div>

      {!rows.length && <Empty note="No companies match those filters." />}
      <div className="disclaimer">Published {research.length} highest-ranked companies from a configured {data.universe_count || data.universe?.length}-company universe. Rankings do not imply suitability or portfolio allocation.</div>
      {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
    </>
  )
}
