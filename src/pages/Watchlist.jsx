import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData'
import { Loading, RefreshProgress } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import { inverseVolatilityAllocations, watchlistGuidance } from '../lib/watchlistGuidance'
import CompanyLogo from '../components/CompanyLogo.jsx'
import SetupQualityBreakdown from '../components/SetupQualityBreakdown.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'

const KEY = 'valuesignal.watchlist'
const SETTINGS_KEY = 'valuesignal.watchlistSizing'

export default function Watchlist() {
  const { data, loading, reload } = useData('advisor.json')
  const { preferences } = usePreferences()
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
  const watchRows = list.map((ticker) => byTicker[ticker]).filter(Boolean)
  const volatilityAllocations = inverseVolatilityAllocations(watchRows, budget, maxPositionPct)
  const sizingModeLabel = preferences.watchlistSizingMode === 'inverse-volatility'
    ? 'Equal risk by volatility'
    : 'Capped maximum'

  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Saved research</span>
        <h1 className="page-title">My <span className="accent">watchlist</span></h1>
        <p className="page-sub">Track Yahoo-covered companies you want to revisit. Saved privately in this browser.</p></div>
        <div className="page-actions">
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing || !list.length}>
            <Icon name="sync" size={17} className={refresh.refreshing && refresh.activeMode === 'data' ? 'refresh-spin' : ''} />
            {refresh.refreshing && refresh.activeMode === 'data' ? 'Refreshing…' : 'Refresh watchlist'}
          </button>
          <button className="secondary-button" onClick={refresh.requestReanalyze} disabled={refresh.refreshing}
            title="Re-score the last published data without fetching anything new — takes a couple of minutes">
            <Icon name="research" size={17} className={refresh.refreshing && refresh.activeMode === 'rescore' ? 'refresh-spin' : ''} />
            {refresh.refreshing && refresh.activeMode === 'rescore' ? 'Reanalyzing…' : 'Reanalyze'}
          </button>
          <div className="result-count"><strong>{list.length}</strong><span>saved</span></div>
        </div>
      </div>
      <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
        percent={refresh.progress} stage={refresh.stage} />
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
          <span className="eyebrow">Illustrative position sizing</span>
          <strong>Set the most this screen may allocate</strong>
          <small>{sizingModeLabel}. Only a low-confidence block or published Sell forces $0. Change the method in <Link to="/settings">Settings</Link>.</small>
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
          const guidance = watchlistGuidance(row, budget, maxPositionPct, {
            sizingMode: preferences.watchlistSizingMode,
            volatilityAllocation: volatilityAllocations[ticker],
          })
          return (
            <article className="watchlist-card" key={ticker}>
              <div className="watchlist-card-head">
                <CompanyLogo company={row || { ticker }} size={42} /><div><strong>{ticker}</strong><span>{row?.name || 'Not in published research'}</span></div>
                <button className="icon-button danger" onClick={() => save(list.filter((item) => item !== ticker))}
                  aria-label={`Remove ${ticker} from watchlist`}><Icon name="close" /></button>
              </div>
              {row ? (
                <>
                  <Sparkline values={row.history?.closes || row.history?.growth || []} label={`${ticker} trend`} height={92} />
                  <div className="watchlist-stats">
                    <div><span>Price</span><b>{row.price ? `$${row.price.toFixed(2)}` : 'Unavailable'}</b></div>
                    <div><span>Setup quality</span><b>{guidance.setupScore.toFixed(0)}</b></div>
                    <div><span>Score</span><b>{row.score}</b></div>
                  </div>
                  <SetupQualityBreakdown guidance={guidance} compact />
                  <div className="watchlist-plan">
                    <div>
                      <span>Yahoo consensus target</span>
                      <b>{guidance.target ? `$${guidance.target.toFixed(2)}` : 'Unavailable'}</b>
                      <small>{guidance.targetUpside == null
                        ? 'Yahoo did not publish a usable target'
                        : `${guidance.targetUpside >= 0 ? '+' : ''}${guidance.targetUpside.toFixed(1)}% · ${guidance.analystCount || '—'} analysts`}</small>
                    </div>
                    <div>
                      <span>{guidance.sizingMode === 'inverse-volatility' ? 'Equal-risk maximum' : 'Capped maximum'}</span>
                      <b>{guidance.allocation > 0 ? `$${guidance.allocation.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '$0'}</b>
                      <small>{guidance.shares > 0
                        ? guidance.sizingFallback
                          ? `Up to ${guidance.shares} shares with capped fallback`
                          : `Up to ${guidance.shares} shares${guidance.annualizedVolatility == null ? '' : ` at ${guidance.annualizedVolatility.toFixed(0)}% volatility`}`
                        : guidance.hardBlocked ? 'Sizing blocked by published evidence' : 'Enter a budget above'}</small>
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
