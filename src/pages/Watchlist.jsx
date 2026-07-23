import { useEffect, useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, MetricPills, Loading } from '../components/Bits.jsx'

const KEY = 'valuesignal.watchlist'
export default function Watchlist() {
  const { data, loading } = useData('advisor.json')
  const [list, setList] = useState([])
  const [input, setInput] = useState('')
  useEffect(() => { try { setList(JSON.parse(localStorage.getItem(KEY)) || ['AAPL', 'MSFT']) } catch { setList(['AAPL', 'MSFT']) } }, [])
  const save = next => { setList(next); localStorage.setItem(KEY, JSON.stringify(next)) }
  const add = () => { const value = input.trim().toUpperCase(); if (value && !list.includes(value)) save([...list, value]); setInput('') }
  if (loading) return <Loading />
  const byTicker = Object.fromEntries((data?.research || []).map(x => [x.ticker, x]))
  return <><div className="page-head"><div><h1 className="page-title">My <span className="accent">watchlist</span></h1><p className="page-sub">Stored only in this browser. Add symbols to track which ones are covered by the current research universe.</p></div></div>
    <div className="filters"><input aria-label="Ticker" placeholder="add ticker…" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} /><button className="tab active" onClick={add}>+ add</button></div>
    <div className="grid">{list.map(ticker => { const row = byTicker[ticker]; return <div className="card sig" key={ticker}><div className="sig-top"><div className="sig-tick">{ticker}</div><div className="score-lockup">{row ? <><Tier label={row.stance} /><span className="sig-score">{row.score}</span></> : <span className="chip">not in current universe</span>}<button className="chip button-chip" onClick={() => save(list.filter(x => x !== ticker))}>remove</button></div></div>{row && <MetricPills {...row} fundamental_coverage={row.fundamental_detail?.coverage} />}</div>})}</div>
  </>
}
