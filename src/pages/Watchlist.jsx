import { useEffect, useState } from 'react'
import { useData } from '../lib/useData'
import { Move, Loading, RefreshProgress } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import { watchlistGuidance } from '../lib/watchlistGuidance'

const KEY = 'valuesignal.watchlist'
const SETTINGS_KEY = 'valuesignal.watchlistSizing'

export default function Watchlist() {
  const { data, loading, reload } = useData('advisor.json')
  const [list, setList] = useState([])
  const [input, setInput] = useState('')
  const [sizing, setSizing] = useState({ budget: '', maxPositionPct: '5' })
  const refresh = useAdvisorRefresh(data?.generated_at, reload, list)
  useEffect(() => {
    try { setList(JSON.parse(localStorage.getItem(KEY)) || ['AAPL', 'MSFT']) }
    catch { setList(['AAPL', 'MSFT']) }
    try {
      const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY))
      if (saved) setSizing(saved)
    } catch {
      // Invalid local sizing settings fall back to a blank budget and 5% cap.
    }
  }, [])
  const save = (next) => { setList(next); localStorage.setItem(KEY, JSON.stringify(next)) }
  const saveSizing = (next) => {
    setSizing(next)
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next))
  }
  const add = () => {
    const value = input.trim().toUpperCase()
    if (value && !list.includes(value)) save([...list, value])
    setInput('')
  }
  if (loading) return <Loading />
  const byTicker = Object.fromEntries([
    ...(data?.research || []),
    ...(data?.portfolio_coverage || []),
  ].map((row) => [row.ticker, row]))
  const budget = Number(sizing.budget)
  const maxPositionPct = Number(sizing.maxPositionPct)

  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Saved research</span>
        <h1 className="page-title">My <span className="accent">watchlist</span></h1>
        <p className="page-sub">Track Yahoo-covered companies you want to revisit. Saved privately in this browser.</p></div>
        <div className="page-actions">
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing || !list.length}>
            <Icon name="sync" size={17} className={refresh.refreshing ? 'refresh-spin' : ''} />
            {refresh.refreshing ? 'Refreshing…' : 'Refresh watchlist'}
          </button>
          <div className="result-count"><strong>{list.length}</strong><span>saved</span></div>
        </div>
      </div>
      <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel} />
      {refresh.message && (
        <div className={`sync-message refresh-message ${refresh.status}`} role="status" aria-live="polite">
          {refresh.message}
        </div>
      )}
      <div className="watchlist-add">
        <label><span>Ticker symbol</span><input autoCapitalize="characters" placeholder="AAPL" value={input}
          onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && add()} /></label>
        <button className="primary-button compact" onClick={add}><Icon name="plus" size={18} /> Add ticker</button>
      </div>
      <div className="watchlist-sizing card">
        <div>
          <span className="eyebrow">Illustrative sizing cap</span>
          <strong>Set the most this screen may allocate</strong>
          <small>Stored only in this browser. “Don’t buy yet” always allocates $0.</small>
        </div>
        <label>
          <span>Investable budget</span>
          <input type="number" min="0" step="100" inputMode="decimal" placeholder="10000"
            value={sizing.budget} onChange={(event) => saveSizing({ ...sizing, budget: event.target.value })} />
        </label>
        <label>
          <span>Maximum per stock</span>
          <input type="number" min="0.1" max="100" step="0.5" inputMode="decimal"
            value={sizing.maxPositionPct} onChange={(event) => saveSizing({ ...sizing, maxPositionPct: event.target.value })} />
        </label>
      </div>
      <div className="watchlist-grid">
        {list.map((ticker) => {
          const row = byTicker[ticker]
          const guidance = watchlistGuidance(row, budget, maxPositionPct)
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
                    <div><span>20-day move</span><Move pct={row.technical_detail?.return_20d} /></div>
                    <div><span>Score</span><b>{row.score}</b></div>
                  </div>
                  <div className={`watchlist-verdict ${guidance.buySetup ? 'buy' : 'wait'}`}>
                    <strong>{guidance.verdict}</strong>
                    <span>Bull/bear thesis {guidance.thesisScore == null ? '—' : `${guidance.thesisScore.toFixed(1)} / 10`}</span>
                  </div>
                  <div className="watchlist-plan">
                    <div>
                      <span>Yahoo consensus target</span>
                      <b>{guidance.target ? `$${guidance.target.toFixed(2)}` : 'Unavailable'}</b>
                      <small>{guidance.targetUpside == null
                        ? 'Yahoo did not publish a usable target'
                        : `${guidance.targetUpside >= 0 ? '+' : ''}${guidance.targetUpside.toFixed(1)}% · ${guidance.analystCount || '—'} analysts`}</small>
                    </div>
                    <div>
                      <span>Illustrative maximum</span>
                      <b>{guidance.allocation > 0 ? `$${guidance.allocation.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '$0'}</b>
                      <small>{guidance.shares > 0 ? `Up to ${guidance.shares} shares` : sizing.budget ? 'No entry while setup is negative' : 'Enter a budget above'}</small>
                    </div>
                  </div>
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
