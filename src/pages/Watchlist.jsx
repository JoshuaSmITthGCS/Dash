import { useEffect, useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, Move, MetricPills, Loading } from '../components/Bits.jsx'

const KEY = 'polititrade.watchlist'

export default function Watchlist() {
  const { data, loading } = useData('signals.json')
  const [list, setList] = useState([])
  const [input, setInput] = useState('')

  useEffect(() => {
    try { setList(JSON.parse(localStorage.getItem(KEY)) || ['NVDA', 'RTX']) }
    catch { setList(['NVDA', 'RTX']) }
  }, [])

  const save = (next) => { setList(next); localStorage.setItem(KEY, JSON.stringify(next)) }
  const add = () => {
    const t = input.trim().toUpperCase()
    if (t && !list.includes(t)) save([...list, t])
    setInput('')
  }
  const remove = (t) => save(list.filter((x) => x !== t))

  if (loading) return <Loading />
  const byTicker = Object.fromEntries((data?.signals || []).map((s) => [s.ticker, s]))

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">My <span className="accent">watchlist</span></h1>
          <p className="page-sub">Saved locally in your browser. Cross-referenced against the live signal set so you see when Congress is moving on something you're tracking.</p>
        </div>
      </div>

      <div className="filters">
        <input placeholder="add ticker…" value={input}
          onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()} />
        <button className="tab active" onClick={add}>+ add</button>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '1fr' }}>
        {list.map((t) => {
          const s = byTicker[t]
          return (
            <div className="card sig" key={t}>
              <div className="sig-top">
                <div className="sig-tick">{t}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  {s ? <><Move pct={s.pct_30d} /><Tier label={s.label} /><span className="sig-score">{s.political_score}</span></>
                     : <span className="chip">no active signal</span>}
                  <button className="chip" onClick={() => remove(t)} style={{ cursor: 'pointer' }}>remove</button>
                </div>
              </div>
              {s && <MetricPills {...s} isEtf={s.is_etf} />}
            </div>
          )
        })}
        {list.length === 0 && <div className="card card-pad" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>Empty — add a ticker above.</div>}
      </div>
    </>
  )
}
