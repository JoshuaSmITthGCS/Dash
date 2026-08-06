import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData'
import { Loading, Move, RefreshProgress } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import { inverseVolatilityAllocations, watchlistGuidance } from '../lib/watchlistGuidance'
import { suggestPriceTargets } from '../lib/watchlistPriceTargets.js'
import { useWatchlist } from '../lib/useWatchlist.js'
import { useAlerts } from '../lib/useAlerts.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import SetupQualityBreakdown from '../components/SetupQualityBreakdown.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'

const SETTINGS_KEY = 'valuesignal.watchlistSizing'

function PriceTargetEditor({ item, suggested, onSave, onCreateAlert, alertBusy }) {
  const [dip, setDip] = useState(item.dipPrice ?? '')
  const [goodBuy, setGoodBuy] = useState(item.goodBuyPrice ?? '')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setDip(item.dipPrice ?? '')
    setGoodBuy(item.goodBuyPrice ?? '')
  }, [item.dipPrice, item.goodBuyPrice])

  const save = async () => {
    await onSave({
      dipPrice: dip === '' ? null : Number(dip),
      goodBuyPrice: goodBuy === '' ? null : Number(goodBuy),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 1800)
  }

  const useSuggested = () => {
    setDip(suggested.dipBuy?.price ?? '')
    setGoodBuy(suggested.goodBuy?.price ?? '')
  }

  return (
    <div className="watchlist-targets">
      <div className="watchlist-target-fields">
        <label>
          <span>Dip buy price</span>
          <input type="number" min="0" step="0.01" inputMode="decimal" placeholder="e.g. 142.50"
            value={dip} onChange={(event) => setDip(event.target.value)} />
        </label>
        <label>
          <span>Good buy price</span>
          <input type="number" min="0" step="0.01" inputMode="decimal" placeholder="e.g. 150.00"
            value={goodBuy} onChange={(event) => setGoodBuy(event.target.value)} />
        </label>
      </div>
      {(suggested.dipBuy?.price != null || suggested.goodBuy?.price != null) && (
        <div className="watchlist-target-suggestion">
          <button type="button" className="secondary-button compact" onClick={useSuggested}>
            Use suggested: {suggested.dipBuy?.price != null ? `dip $${suggested.dipBuy.price.toFixed(2)}` : ''}
            {suggested.dipBuy?.price != null && suggested.goodBuy?.price != null ? ' · ' : ''}
            {suggested.goodBuy?.price != null ? `good buy $${suggested.goodBuy.price.toFixed(2)}` : ''}
          </button>
          <details className="watchlist-target-derivation">
            <summary>How were these suggested?</summary>
            {suggested.dipBuy?.derivation && <p>{suggested.dipBuy.derivation}</p>}
            {suggested.goodBuy?.derivation && <p>{suggested.goodBuy.derivation}</p>}
          </details>
        </div>
      )}
      <div className="watchlist-target-actions">
        <button type="button" className="primary-button compact" onClick={save}>{saved ? 'Saved' : 'Save targets'}</button>
        {dip !== '' && (
          <button type="button" className="secondary-button compact" disabled={alertBusy}
            onClick={() => onCreateAlert(Number(dip))}>
            {alertBusy ? 'Creating…' : 'Alert me at dip price'}
          </button>
        )}
      </div>
    </div>
  )
}

export default function Watchlist() {
  const { data, loading, reload } = useData('advisor.json')
  const { preferences } = usePreferences()
  const { currentUser } = useAuth()
  const watchlist = useWatchlist()
  const { createRule } = useAlerts()
  const [input, setInput] = useState('')
  const [sizing, setSizing] = useState({ budget: '', maxPositionPct: '5' })
  const [alertBusyTicker, setAlertBusyTicker] = useState('')
  const [alertNotice, setAlertNotice] = useState(null)
  const tickers = watchlist.items.map((item) => item.ticker)
  const refresh = useAdvisorRefresh(data?.generated_at, reload, tickers)

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY))
      if (saved) setSizing(saved)
    } catch {
      // Invalid local sizing settings fall back to a blank budget and 5% cap.
    }
  }, [])
  const saveSizing = (next) => {
    setSizing(next)
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next))
  }
  const add = async () => {
    const value = input.trim().toUpperCase()
    if (value && !watchlist.isWatched(value)) await watchlist.addTicker(value)
    setInput('')
  }

  if (loading || watchlist.loading) return <Loading />
  if (!currentUser) {
    return (
      <div className="page-head"><div><span className="eyebrow">Saved research</span>
        <h1 className="page-title">My <span className="accent">watchlist</span></h1>
        <p className="page-sub">Sign in to save a watchlist that syncs across your devices.</p></div></div>
    )
  }

  const byTicker = Object.fromEntries([
    ...(data?.research || []),
    ...(data?.portfolio_coverage || []),
  ].map((row) => [row.ticker, row]))
  const budget = Number(sizing.budget)
  const maxPositionPct = Number(sizing.maxPositionPct)
  const watchRows = tickers.map((ticker) => byTicker[ticker]).filter(Boolean)
  const volatilityAllocations = inverseVolatilityAllocations(watchRows, budget, maxPositionPct)
  const sizingModeLabel = preferences.watchlistSizingMode === 'inverse-volatility'
    ? 'Equal risk by volatility'
    : 'Capped maximum'

  const handleCreateDipAlert = async (item, dipPrice) => {
    setAlertBusyTicker(item.ticker)
    const result = await createRule({ type: 'price_cross', ticker: item.ticker, direction: 'below', threshold: dipPrice })
    setAlertBusyTicker('')
    setAlertNotice(result.success
      ? { error: false, message: `Alert created: ${item.ticker} price below $${dipPrice.toFixed(2)}.` }
      : { error: true, message: result.error || 'Could not create the alert.' })
    setTimeout(() => setAlertNotice(null), 4000)
  }

  return (
    <>
      <div className="page-head"><div><span className="eyebrow">Saved research</span>
        <h1 className="page-title">My <span className="accent">watchlist</span></h1>
        <p className="page-sub">Track companies you want to revisit, with a dip price and a good-buy price for each. Synced to your account.</p></div>
        <div className="page-actions">
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing || !tickers.length}>
            <Icon name="sync" size={17} className={refresh.refreshing && refresh.activeMode === 'data' ? 'refresh-spin' : ''} />
            {refresh.refreshing && refresh.activeMode === 'data' ? 'Refreshing…' : 'Refresh watchlist'}
          </button>
          <button className="secondary-button" onClick={refresh.requestReanalyze} disabled={refresh.refreshing}
            title="Re-score the last published data without fetching anything new – takes a couple of minutes">
            <Icon name="research" size={17} className={refresh.refreshing && refresh.activeMode === 'rescore' ? 'refresh-spin' : ''} />
            {refresh.refreshing && refresh.activeMode === 'rescore' ? 'Reanalyzing…' : 'Reanalyze'}
          </button>
          <div className="result-count"><strong>{tickers.length}</strong><span>saved</span></div>
        </div>
      </div>
      <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
        percent={refresh.progress} stage={refresh.stage} />
      {refresh.message && (
        <div className={`sync-message refresh-message ${refresh.status}`} role="status" aria-live="polite">
          {refresh.message}
        </div>
      )}
      {alertNotice && <div className={`research-trade-notice ${alertNotice.error ? 'error' : ''}`} role="status" aria-live="polite">{alertNotice.message}</div>}
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
        {watchlist.items.map((item) => {
          const ticker = item.ticker
          const row = byTicker[ticker]
          const guidance = watchlistGuidance(row, budget, maxPositionPct, {
            sizingMode: preferences.watchlistSizingMode,
            volatilityAllocation: volatilityAllocations[ticker],
          })
          const suggested = row ? suggestPriceTargets(row) : { dipBuy: null, goodBuy: null }
          return (
            <article className="watchlist-card" key={ticker}>
              <div className="watchlist-card-head">
                <CompanyLogo company={row || { ticker }} size={42} /><div><strong>{ticker}</strong><span>{row?.name || 'Not in published research'}</span></div>
                {row && <Move pct={row.technical_detail?.return_20d} capsule />}
                <button className="icon-button danger" onClick={() => watchlist.removeTicker(ticker)}
                  aria-label={`Remove ${ticker} from watchlist`}><Icon name="close" /></button>
              </div>
              {row ? (
                <>
                  <Sparkline values={row.history?.closes || row.history?.growth || []} label={`${ticker} trend`} height={92} />
                  <small className="as-of-line">As of {row.history?.dates?.at(-1) || row.data_as_of || 'the latest published close'}</small>
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
                        : `${guidance.targetUpside >= 0 ? '+' : ''}${guidance.targetUpside.toFixed(1)}% · ${guidance.analystCount || '–'} analysts`}</small>
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
                  <PriceTargetEditor item={item} suggested={suggested}
                    onSave={(updates) => watchlist.updateTargets(ticker, updates)}
                    onCreateAlert={(dipPrice) => handleCreateDipAlert(item, dipPrice)}
                    alertBusy={alertBusyTicker === ticker} />
                </>
              ) : <div className="inline-empty">This ticker is saved, but no current quote or research record was published. It will populate after a successful pipeline refresh that covers it.</div>}
            </article>
          )
        })}
      </div>
      {!tickers.length && <div className="empty-state"><Icon name="watchlist" size={30} /><h2>Your watchlist is empty</h2><p>Add a ticker above to start a focused research list.</p></div>}
    </>
  )
}
