import { useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, MetricPills, Move, Loading, Empty } from '../components/Bits.jsx'

export default function Picks() {
  const { data, loading } = useData('advisor.json')
  const [sector, setSector] = useState('all')
  if (loading) return <Loading />
  if (!data?.research) return <Empty />
  const sectors = [...new Set(data.research.map(x => x.sector).filter(Boolean))].sort()
  const rows = data.research.filter(x => sector === 'all' || x.sector === sector)
  return <>
    <div className="page-head"><div><h1 className="page-title">Top 20 <span className="accent">deep dive</span></h1><p className="page-sub">Compare the evidence behind every ranked company. Sector-aware multiples prevent a bank, grocer, and software company from being judged by one arbitrary P/E cutoff.</p></div></div>
    <div className="filters"><label className="sr-only" htmlFor="sector">Filter by sector</label><select id="sector" value={sector} onChange={e => setSector(e.target.value)}><option value="all">All sectors</option>{sectors.map(s => <option key={s}>{s}</option>)}</select></div>
    <div className="grid">{rows.map(row => { const rank = data.research.findIndex(item => item.ticker === row.ticker) + 1; return <article className="card card-pad research-card" key={row.ticker}>
      <div className="sig-top"><div className="company-line"><span className="rank">#{rank}</span><div><div className="sig-tick">{row.ticker}</div><div className="sig-name">{row.name} · {row.industry || row.sector || '—'}</div></div></div><div className="score-lockup"><Move pct={row.pct_30d} /><Tier label={row.stance} /><span className="sig-score">{row.score}</span></div></div>
      <div className="component-scores">{Object.entries(row.components).map(([key, value]) => <div key={key}><span>{key.replace(/_/g, ' ')}</span><b>{value == null ? '—' : Math.round(value)}</b><i><em style={{ width: `${value || 0}%` }} /></i></div>)}</div>
      <MetricPills {...row} fundamental_coverage={row.fundamental_detail?.coverage} />
      {row.insider_activity && <div className="insider-line"><span>Corporate-insider context</span><b>{row.insider_activity.recent_acquisitions} acquisitions</b><b>{row.insider_activity.recent_disposals} disposals</b><small>{row.insider_activity.records_reviewed} records reviewed · context only, not scored</small></div>}
      <details><summary>Evidence and risks</summary><div className="evidence-grid"><div><b>Evidence for</b><ul>{row.strengths.map(x => <li key={x}>{x}</li>)}</ul></div><div><b>Risks / gaps</b><ul>{row.risks.map(x => <li key={x}>{x}</li>)}</ul></div></div></details>
    </article>})}</div>
    <div className="disclaimer">These are the top 20 from a configured {data.universe_count || data.universe?.length}-company universe. They do not imply expected return, suitability, or portfolio allocation.</div>
  </>
}
