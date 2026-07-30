import { useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, MetricPills, Move, Loading, Empty } from '../components/Bits.jsx'
import { ActionPill } from '../components/ActionGuidance.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import { getRecommendation } from '../lib/recommendation'

const SORTS = {
  score: ['Research score', (a, b) => b.score - a.score],
  valuation: ['Cheapest for its sector', (a, b) => (b.sector_valuation_percentile ?? -1) - (a.sector_valuation_percentile ?? -1)],
  quality: ['Return on invested capital', (a, b) => (b.return_on_invested_capital ?? -1) - (a.return_on_invested_capital ?? -1)],
  accounting: ['Accounting quality', (a, b) => (b.fundamental_categories?.accounting_quality ?? -1) - (a.fundamental_categories?.accounting_quality ?? -1)],
  benchmark: ['Beating the S&P', (a, b) => (b.hypothetical?.excess_return_pct ?? -999) - (a.hypothetical?.excess_return_pct ?? -999)],
}

export default function Picks() {
  const { data, loading } = useData('advisor.json')
  const [sector, setSector] = useState('all')
  const [sort, setSort] = useState('score')
  const [selectedStock, setSelectedStock] = useState(null)

  if (loading) return <Loading />
  if (!data?.research) return <Empty />

  const sectors = [...new Set(data.research.map(x => x.sector).filter(Boolean))].sort()
  const rows = data.research
    .filter(x => sector === 'all' || x.sector === sector)
    .slice()
    .sort(SORTS[sort][1])

  return <>
    <div className="page-head"><div>
      <h1 className="page-title">Top {data.research.length} <span className="accent">deep dive</span></h1>
      <p className="page-sub">Compare the evidence behind every ranked company. Sector-aware multiples stop a bank, a grocer, and a software company from being judged by one arbitrary P/E cutoff, and a sector percentile separates “cheap for tech” from “cheap outright”.</p>
    </div></div>

    <div className="filters">
      <label className="sr-only" htmlFor="sector">Filter by sector</label>
      <select id="sector" value={sector} onChange={e => setSector(e.target.value)}>
        <option value="all">All sectors</option>
        {sectors.map(s => <option key={s}>{s}</option>)}
      </select>
      <label className="sr-only" htmlFor="sort">Sort by</label>
      <select id="sort" value={sort} onChange={e => setSort(e.target.value)}>
        {Object.entries(SORTS).map(([key, [label]]) => <option key={key} value={key}>{label}</option>)}
      </select>
    </div>

    <div className="grid">{rows.map(row => {
      const rank = data.research.findIndex(item => item.ticker === row.ticker) + 1
      return <article className="card card-pad research-card" key={row.ticker}>
        <div className="sig-top">
          <div className="company-line">
            <span className="rank">#{rank}</span>
            <div>
              <div className="sig-tick">{row.ticker}</div>
              <div className="sig-name">{row.name} · {row.industry || row.sector || '—'}</div>
            </div>
          </div>
          <div className="score-lockup">
            <Move pct={row.pct_30d} />
            <ActionPill recommendation={getRecommendation(row)} />
            <Tier label={row.stance} />
            <span className="sig-score">{row.score}</span>
          </div>
        </div>

        <div className="component-scores">
          {Object.entries(row.fundamental_categories || row.components).map(([key, value]) => (
            <div key={key}>
              <span>{key.replace(/_/g, ' ')}</span>
              <b>{value == null ? '—' : Math.round(value)}</b>
              <i><em style={{ width: `${value || 0}%` }} /></i>
            </div>
          ))}
        </div>

        <MetricPills {...row} fundamental_coverage={row.fundamental_detail?.coverage} />

        <div className="insider-line">
          {row.sector_valuation_percentile != null &&
            <b>cheaper than {row.sector_valuation_percentile.toFixed(0)}% of its sector</b>}
          {row.hypothetical &&
            <b style={{ color: row.hypothetical.dollars_ahead >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
              {row.hypothetical.dollars_ahead >= 0 ? '+' : '−'}${Math.abs(row.hypothetical.dollars_ahead).toFixed(0)} vs S&P on ${row.hypothetical.basis}
            </b>}
          {row.insider_activity?.records_reviewed > 0 &&
            <b>{row.insider_activity.recent_acquisitions} insider buys / {row.insider_activity.recent_disposals} sells</b>}
          <button className="chip button-chip" onClick={() => setSelectedStock(row)}>Full breakdown</button>
        </div>

        <details>
          <summary>Evidence and risks</summary>
          <div className="evidence-grid">
            <div><b>Evidence for</b><ul>{row.strengths.map(x => <li key={x}>{x}</li>)}</ul></div>
            <div><b>Risks / gaps</b><ul>{row.risks.map(x => <li key={x}>{x}</li>)}</ul></div>
          </div>
        </details>
      </article>
    })}</div>

    <div className="disclaimer">These are the top {data.research.length} from a configured {data.universe_count || data.universe?.length}-company universe. They do not imply expected return, suitability, or portfolio allocation.</div>
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
