import { useEffect, useState } from 'react'
import { useData } from '../lib/useData'
import { Tier, Move, Loading } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'

const KEY = 'valuesignal.watchlist'

export default function Watchlist() {
  const { data, loading } = useData('advisor.json')
  const [list, setList] = useState([])
  const [input, setInput] = useState('')
  useEffect(() => {
    try { setList(JSON.parse(localStorage.getItem(KEY)) || ['AAPL', 'MSFT']) }
    catch { setList(['AAPL', 'MSFT']) }
  }, [])
  const save = (next) => { setList(next); localStorage.setItem(KEY, JSON.stringify(next)) }
  const add = () => {
    const value = input.trim().toUpperCase()
    if (value && !list.includes(value)) save([...list, value])
    setInput('')
  }
  if (loading) return <Loading />
  const byTicker = Object.fromEntries((data?.research || []).map((row) => [row.ticker, row]))

  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Saved research</span>
        <h1 className="page-title">My <span className="accent">watchlist</span></h1>
        <p className="page-sub">Track the companies you want to revisit. Saved privately in this browser.</p></div>
        <div className="result-count"><strong>{list.length}</strong><span>saved</span></div>
      </div>
      <div className="watchlist-add">
        <label><span>Ticker symbol</span><input autoCapitalize="characters" placeholder="AAPL" value={input}
          onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && add()} /></label>
        <button className="primary-button compact" onClick={add}><Icon name="plus" size={18} /> Add ticker</button>
      </div>
      <div className="watchlist-grid">
        {list.map((ticker) => {
          const row = byTicker[ticker]
          return (
            <article className="watchlist-card" key={ticker}>
              <div className="watchlist-card-head">
                <div><strong>{ticker}</strong><span>{row?.name || 'Not in published research'}</span></div>
                <button className="icon-button danger" onClick={() => save(list.filter((item) => item !== ticker))}
                  aria-label={`Remove ${ticker} from watchlist`}><Icon name="close" /></button>
              </div>
              {row ? (
                <>
                  <Sparkline values={row.history?.closes || row.history?.growth || []} label={`${ticker} trend`} height={92} />
                  <div className="watchlist-stats">
                    <div><span>Price</span><b>{row.price ? `$${row.price.toFixed(2)}` : 'Unavailable'}</b></div>
                    <div><span>30-day move</span><Move pct={row.pct_30d} /></div>
                    <div><span>Score</span><b>{row.score}</b></div>
                  </div>
                  <Tier label={row.stance} />
                </>
              ) : <div className="inline-empty">This ticker is saved, but no current quote or research record was published. It will populate after a successful pipeline refresh that covers it.</div>}
            </article>
          )
        })}
      </div>
      {!list.length && <div className="empty-state"><Icon name="watchlist" size={30} /><h2>Your watchlist is empty</h2><p>Add a ticker above to start a focused research list.</p></div>}
    </>
  )
}
