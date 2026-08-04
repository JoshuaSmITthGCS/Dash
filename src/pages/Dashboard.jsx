import { cloneElement, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { portfolioGrowthSeries } from '../lib/portfolioPerformance.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { getRecommendation } from '../lib/recommendation.js'
import { humanDate, signedPct } from '../lib/formatters.js'
import { Loading, Empty, Move, Tier } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import Icon from '../components/Icons.jsx'

const WATCH_KEY = 'valuesignal.watchlist'

function historyValues(row) {
  return row?.history?.closes || row?.history?.growth || []
}

function recentReturn(values, points = 5) {
  const clean = values.filter(Number.isFinite).slice(-points)
  if (clean.length < 2 || !clean[0]) return null
  return (clean.at(-1) / clean[0] - 1) * 100
}

function Metric({ label, value, note, tone }) {
  return <div className="overview-metric"><span>{label}</span><strong className={tone || ''}>{value}</strong><small>{note}</small></div>
}

function WidgetFrame({ widget, editMode, children }) {
  return <section className={`dashboard-widget widget-${widget.size}${editMode ? ' editing' : ''}`} data-widget={widget.id}>
    {editMode && <div className="widget-edit-banner"><Icon name="grip" size={18} /><span>{widget.label}</span><small>{widget.size}</small></div>}
    {children}
  </section>
}

function DashboardCustomizer({ widgets, onChange, onCancel, onDone }) {
  const update = (id, patch) => onChange(widgets.map((widget) => widget.id === id ? { ...widget, ...patch } : widget))
  const move = (index, direction) => {
    const target = index + direction
    if (target < 0 || target >= widgets.length) return
    const next = [...widgets]
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next.map((widget, order) => ({ ...widget, order })))
  }

  return <aside className="customizer-panel" aria-labelledby="customizer-heading">
    <div className="customizer-head"><div><span className="eyebrow">Edit mode</span><h2 id="customizer-heading">Customize dashboard</h2></div><button className="icon-button" onClick={onCancel} aria-label="Cancel customization"><Icon name="close" /></button></div>
    <p>Choose what appears, then use the arrow controls to set reading order. Mobile widgets remain full width.</p>
    <div className="customizer-list">
      {widgets.map((widget, index) => <div className="customizer-row" key={widget.id}>
        <span className="drag-handle" aria-hidden="true"><Icon name="grip" /></span>
        <div><strong>{widget.label}</strong><small>{widget.locked ? 'Required summary' : `Position ${index + 1}`}</small></div>
        <label className="switch compact-switch"><span className="sr-only">Show {widget.label}</span><input type="checkbox" checked={widget.visible} disabled={widget.locked} onChange={(event) => update(widget.id, { visible: event.target.checked })} /><span aria-hidden="true" /></label>
        <select aria-label={`${widget.label} size`} value={widget.size} onChange={(event) => update(widget.id, { size: event.target.value })}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option><option value="full">Full</option></select>
        <div className="reorder-buttons"><button onClick={() => move(index, -1)} disabled={index === 0} aria-label={`Move ${widget.label} up`}><Icon name="up" size={17} /></button><button onClick={() => move(index, 1)} disabled={index === widgets.length - 1} aria-label={`Move ${widget.label} down`}><Icon name="down" size={17} /></button></div>
      </div>)}
    </div>
    <div className="customizer-actions"><button className="secondary-button" onClick={onCancel}>Cancel</button><button className="primary-button" onClick={onDone}>Done</button></div>
  </aside>
}

export default function Dashboard() {
  const { data, loading } = useData('advisor.json')
  const { currentUser } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { preferences, setWidgets, updatePreferences } = usePreferences()
  const [selectedStock, setSelectedStock] = useState(null)
  const [editMode, setEditMode] = useState(() => new window.URLSearchParams(window.location.search).get('customize') === '1')
  const [draftWidgets, setDraftWidgets] = useState(preferences.widgets)
  const [announcement, setAnnouncement] = useState('')

  const watchlist = useMemo(() => {
    try { return JSON.parse(localStorage.getItem(WATCH_KEY)) || ['AAPL', 'MSFT'] }
    catch { return ['AAPL', 'MSFT'] }
  }, [])

  if (loading || (currentUser && portfolioLoading)) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const leader = rows[0]
  const leaderHistory = historyValues(leader).filter(Number.isFinite)
  const leaderReturn = recentReturn(leaderHistory)
  const priceData = buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows)
  const portfolio = positions.reduce((result, position) => {
    const ticker = String(position.ticker || '').toUpperCase()
    const source = priceData[ticker]
    const price = source?.price ?? position.snapshotPrice ?? null
    const cost = Number(position.shares) * Number(position.costBasis)
    const value = price == null ? null : Number(position.shares) * price
    const gain = value == null ? null : value - cost
    const recommendation = source ? getRecommendation(source) : null
    return {
      cost: result.cost + (Number.isFinite(cost) ? cost : 0),
      value: result.value + (Number.isFinite(value) ? value : 0),
      gain: result.gain + (Number.isFinite(gain) ? gain : 0),
      priced: result.priced + (value == null ? 0 : 1),
      actionable: result.actionable + (recommendation && recommendation.action !== 'HOLD' ? 1 : 0),
      sectors: { ...result.sectors, [source?.sector || 'Unclassified']: (result.sectors[source?.sector || 'Unclassified'] || 0) + (value || 0) },
    }
  }, { cost: 0, value: 0, gain: 0, priced: 0, actionable: 0, sectors: {} })
  const gainPct = portfolio.cost > 0 ? (portfolio.gain / portfolio.cost) * 100 : null
  const growth = positions.length ? portfolioGrowthSeries(positions, priceData, data.benchmark_history) : null
  const sectorAllocation = Object.entries(portfolio.sectors).filter(([, value]) => value > 0).sort((a, b) => b[1] - a[1]).slice(0, 5)
  const averageConfidence = rows.reduce((sum, row) => sum + (row.confidence || 0), 0) / rows.length
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 4)
  const activeWidgets = (editMode ? draftWidgets : preferences.widgets).filter((widget) => editMode || widget.visible).sort((a, b) => a.order - b.order)
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)

  const renderWidget = (widget) => {
    switch (widget.id) {
      case 'portfolio-summary': return <WidgetFrame widget={widget} editMode={editMode}><article className="portfolio-overview-card">
        <header><div><span className="card-kicker">{currentUser ? 'Portfolio value' : 'Research overview'}</span><h2>{currentUser ? 'Your financial snapshot' : 'Today’s evidence set'}</h2></div><button className="icon-button" onClick={() => updatePreferences({ privacyMode: !preferences.privacyMode })} aria-pressed={preferences.privacyMode} aria-label={preferences.privacyMode ? 'Show balances' : 'Hide balances'}><Icon name={preferences.privacyMode ? 'eye-off' : 'eye'} /></button></header>
        <div className="primary-balance"><strong>{currentUser ? money(portfolio.value) : rows.length}</strong><span>{currentUser ? (positions.length ? 'Current priced value' : 'No positions yet') : 'published companies'}</span></div>
        <div className="balance-change" aria-label={currentUser ? `${portfolio.gain} dollars, ${gainPct} percent total unrealized return` : `Top research score ${leader.score} out of 100`}><b className={currentUser && portfolio.gain < 0 ? 'negative' : 'positive'}>{currentUser ? `${portfolio.gain >= 0 ? '+' : '−'}${money(Math.abs(portfolio.gain))}` : `${leader.score}/100 top score`}</b><span>{currentUser ? `${signedPct(gainPct)} total unrealized return` : `${Math.round(leader.confidence * 100)}% data confidence`}</span></div>
        <div className="summary-footer"><div><span>Cost basis</span><b>{currentUser ? (portfolio.cost ? money(portfolio.cost) : '—') : humanDate(data.generated_at)}</b></div><div><span>Positions</span><b>{currentUser ? positions.length : data.universe_count || rows.length}</b></div><div><span>Data coverage</span><b>{currentUser ? `${portfolio.priced}/${positions.length}` : `${Math.round(averageConfidence * 100)}%`}</b></div><div><span>Period</span><b>{currentUser ? 'Since purchase' : 'Latest run'}</b></div></div>
      </article></WidgetFrame>
      case 'performance-chart': return <WidgetFrame widget={widget} editMode={editMode}><article className="overview-card chart-card"><header className="card-header"><div><span className="card-kicker">Performance</span><h2>{growth ? 'Portfolio vs benchmark' : `${leader.ticker} recent trend`}</h2><p>{growth ? 'Same recorded contributions over available history' : 'Top-ranked company · real published observations'}</p></div><div className="chart-summary"><strong>{growth ? money(portfolio.value) : signedPct(leaderReturn)}</strong><span>{growth ? signedPct(gainPct) : 'one month'}</span></div></header><div className="period-selector" aria-label="Chart period">{['1W', '1M', '3M', '1Y'].map((period) => <button key={period} className={preferences.defaultChartPeriod === period ? 'active' : ''} onClick={() => updatePreferences({ defaultChartPeriod: period })}>{period}</button>)}</div><div className="overview-chart">{growth ? <GrowthChart dates={growth.dates} series={[{ label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true }, { label: 'S&P 500', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' }]} height={238} valueFormatter={preferences.privacyMode ? () => 'Balances hidden' : undefined} /> : <Sparkline values={leaderHistory.slice(-12)} label={`${leader.name} published price trend`} height={238} />}</div><p className="chart-accessible-summary">{growth ? 'Portfolio and S&P 500 use the same recorded contribution dates.' : `${leader.ticker} moved ${signedPct(leaderReturn)} across the latest available observations.`}</p></article></WidgetFrame>
      case 'metric-grid': return <WidgetFrame widget={widget} editMode={editMode}><div className="overview-metric-grid"><Metric label="Total return" value={currentUser ? signedPct(gainPct) : `${leader.score}/100`} note={currentUser ? 'Unrealized · since purchase' : 'Top research score'} tone={gainPct < 0 ? 'negative' : 'positive'} /><Metric label="Action needed" value={currentUser ? portfolio.actionable : rows.filter((row) => row.stance !== 'Neutral').length} note={currentUser ? 'Holdings outside Hold' : 'Non-neutral classifications'} /><Metric label="Research coverage" value={`${Math.round(averageConfidence * 100)}%`} note={`${rows.length} published companies`} /><Metric label="Latest update" value={humanDate(data.generated_at).split(',')[0]} note="Not live market data" /></div></WidgetFrame>
      case 'top-signal': return <WidgetFrame widget={widget} editMode={editMode}><article className="overview-card signal-widget"><header className="card-header"><div><span className="card-kicker">Rank #1 · Top signal</span><h2>Highest evidence score</h2></div><Link to="/research">View all</Link></header><button className="signal-company" onClick={() => !editMode && setSelectedStock(leader)} disabled={editMode}><span className="ticker-avatar">{leader.ticker.slice(0, 1)}</span><span><strong>{leader.ticker}</strong><small>{leader.name} · {leader.sector || 'Unclassified'}</small></span><Tier label={leader.stance} /><span className="signal-score"><b>{leader.score}</b><small>score</small></span><Icon name="chevron" /></button><div className="signal-metrics"><Metric label="Confidence" value={`${Math.round(leader.confidence * 100)}%`} note="Data coverage" /><Metric label="Recent return" value={signedPct(leaderReturn)} note="Latest month" tone={leaderReturn < 0 ? 'negative' : 'positive'} /></div></article></WidgetFrame>
      case 'action-needed': return <WidgetFrame widget={widget} editMode={editMode}><article className="overview-card guidance-widget"><header className="card-header"><div><span className="card-kicker">Research guidance</span><h2>{currentUser && portfolio.actionable ? `${portfolio.actionable} holding${portfolio.actionable === 1 ? '' : 's'} need review` : 'No urgent portfolio flags'}</h2></div><span className={`status-mark ${portfolio.actionable ? 'warning' : 'positive'}`}>{portfolio.actionable ? 'Review' : 'Clear'}</span></header><p>{currentUser ? 'Action labels are research classifications, not brokerage instructions. Confirm current prices, news, liquidity, and your own constraints.' : 'Sign in to compare your holdings with current research classifications and concentration guidance.'}</p><Link className="secondary-button compact" to={currentUser ? '/portfolio' : '/methodology'}>{currentUser ? 'Open portfolio' : 'Read methodology'}<Icon name="arrow" size={16} /></Link></article></WidgetFrame>
      case 'allocation': return <WidgetFrame widget={widget} editMode={editMode}><article className="overview-card allocation-widget"><header className="card-header"><div><span className="card-kicker">Allocation</span><h2>Sector distribution</h2></div><Link to="/portfolio">Details</Link></header>{sectorAllocation.length ? <div className="allocation-list">{sectorAllocation.map(([sector, value], index) => { const pct = portfolio.value ? value / portfolio.value * 100 : 0; return <div key={sector}><div><span><i className={`allocation-dot dot-${index}`} />{sector}</span><b>{pct.toFixed(1)}%</b></div><span className="allocation-track"><i style={{ width: `${pct}%` }} /></span><small>{money(value)}</small></div> })}</div> : <div className="widget-empty"><Icon name="portfolio" /><strong>No allocation data yet</strong><span>Add priced positions to see sector weights.</span></div>}</article></WidgetFrame>
      case 'watchlist-preview': return <WidgetFrame widget={widget} editMode={editMode}><article className="overview-card watch-widget"><header className="card-header"><div><span className="card-kicker">Saved names</span><h2>Watchlist preview</h2></div><Link to="/watchlist">Manage</Link></header><div className="compact-list">{watchRows.map((row) => <button key={row.ticker} onClick={() => !editMode && setSelectedStock(row)} disabled={editMode}><span className="ticker-avatar small">{row.ticker.slice(0, 1)}</span><span><strong>{row.ticker}</strong><small>{row.name}</small></span><Sparkline values={historyValues(row).slice(-5)} height={34} label={`${row.ticker} trend`} /><span><b>{row.price ? money(row.price) : `${row.score}/100`}</b><Move pct={recentReturn(historyValues(row))} /></span></button>)}{!watchRows.length && <div className="widget-empty">No saved ticker is in today’s published set.</div>}</div></article></WidgetFrame>
      case 'market-pulse': { const macro = data.market?.macro || {}; return <WidgetFrame widget={widget} editMode={editMode}><article className="overview-card market-widget"><header className="card-header"><div><span className="card-kicker">Market Pulse</span><h2>{macro.regime?.label || 'Macro backdrop'}</h2></div><Link to="/market">Explore</Link></header><div className="macro-metrics"><Metric label="10Y Treasury" value={macro.treasury_10y?.value != null ? `${macro.treasury_10y.value}%` : '—'} note={macro.treasury_10y?.date || 'Unavailable'} /><Metric label="Fed funds" value={macro.federal_funds_rate?.value != null ? `${macro.federal_funds_rate.value}%` : '—'} note={macro.federal_funds_rate?.date || 'Unavailable'} /><Metric label="Inflation" value={macro.inflation?.value != null ? `${macro.inflation.value}%` : '—'} note={macro.inflation?.date || 'Unavailable'} /></div><p>Economic context informs interpretation; it does not override company evidence.</p></article></WidgetFrame> }
      default: return null
    }
  }

  return <>
    <div className={`overview-layout${editMode ? ' customize-active' : ''}`}>
      <div className="overview-main">
        <header className="overview-heading"><div><span className="eyebrow">{humanDate(data.generated_at)} · Latest research run</span><h1>{currentUser ? 'Portfolio overview' : 'Research overview'}</h1><p>{currentUser ? 'Your holdings, performance, and current research guidance in one view.' : 'A compact view of current research signals and market context.'}</p></div><button className="secondary-button compact" onClick={() => { setDraftWidgets(preferences.widgets); setEditMode(true) }}><Icon name="settings" size={17} />Customize dashboard</button></header>
        <p className="sr-only" aria-live="polite">{announcement}</p>
        <div className="dashboard-widget-grid">{activeWidgets.map((widget) => cloneElement(renderWidget(widget), { key: widget.id }))}</div>
        <p className="overview-disclaimer">{data.disclaimer || 'General research only. Values may be delayed and do not constitute personalized financial advice.'}</p>
      </div>
      {editMode && <DashboardCustomizer widgets={draftWidgets} onChange={setDraftWidgets} onCancel={() => { setDraftWidgets(preferences.widgets); setEditMode(false); setAnnouncement('Dashboard changes canceled.') }} onDone={() => { setWidgets(draftWidgets); setEditMode(false); setAnnouncement('Dashboard layout saved.') }} />}
    </div>
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
