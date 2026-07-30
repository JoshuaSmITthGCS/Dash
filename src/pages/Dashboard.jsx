import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData'
import { Tier, Move, Loading, Empty } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import { getRecommendation } from '../lib/recommendation'
import { humanDate } from '../lib/formatters'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'

const WATCH_KEY = 'valuesignal.watchlist'

function historyValues(row) {
  return row?.history?.closes || row?.history?.growth || []
}

function recentReturn(values, points = 5) {
  const clean = values.filter(Number.isFinite).slice(-points)
  if (clean.length < 2 || !clean[0]) return null
  return (clean.at(-1) / clean[0] - 1) * 100
}

function Freshness({ date }) {
  const parsed = Date.parse(date)
  const stale = !Number.isFinite(parsed) || Date.now() - parsed > 1000 * 60 * 60 * 24 * 45
  return <span className={`freshness ${stale ? 'stale' : 'fresh'}`}>
    <span aria-hidden="true" />{stale ? 'Stale' : 'Current'}
  </span>
}

function MacroCard({ label, point, suffix = '', detail }) {
  return (
    <article className="macro-card">
      <div className="macro-top"><span>{label}</span><Freshness date={point?.date} /></div>
      <strong>{point?.value ?? '—'}{point?.value != null ? suffix : ''}</strong>
      <small>{detail || (point?.date ? `Period: ${point.date}` : 'Period unavailable')}</small>
    </article>
  )
}

function CandidateCard({ row, rank, onOpen }) {
  const recommendation = getRecommendation(row)
  return (
    <button className="candidate-card" onClick={() => onOpen(row)}
      aria-label={`Open research for ${row.name}`}>
      <div className="candidate-top">
        <span className="rank-badge">#{rank}</span>
        <Tier label={row.stance} />
      </div>
      <div>
        <strong className="candidate-ticker">{row.ticker}</strong>
        <span className="candidate-name">{row.name}</span>
      </div>
      <Sparkline values={historyValues(row)} label={`${row.ticker} trend`} height={54} />
      <div className="candidate-metrics">
        <div><span>Score</span><b>{row.score}</b></div>
        <div><span>20-day return</span><Move pct={row.technical_detail?.return_20d} /></div>
      </div>
      <div className="candidate-action">{recommendation?.label || 'Research'}<Icon name="chevron" size={17} /></div>
    </button>
  )
}

function TrendCard({ row, direction, onOpen }) {
  const trendReturn = row.trendReturn
  const relative = row.trendRelative
  return (
    <button className="trend-card" onClick={() => onOpen(row)}
      aria-label={`Open ${row.name}; ${direction} trend, ${trendReturn?.toFixed(1)} percent over one month`}>
      <div className="trend-card-head">
        <div><strong>{row.ticker}</strong><span>{row.name}</span></div>
        <span className={`trend-direction ${direction === 'Strengthening' ? 'positive' : 'negative'}`}>
          {direction}
        </span>
      </div>
      <Sparkline values={historyValues(row).slice(-5)} label={`${row.ticker} one-month price trend`} height={78} />
      <div className="trend-card-stats">
        <div><span>1-month</span><Move pct={trendReturn} /></div>
        <div><span>Vs SPY</span><Move pct={relative} /></div>
      </div>
    </button>
  )
}

export default function Dashboard() {
  const { data, loading, reload } = useData('advisor.json')
  const { currentUser } = useAuth()
  const [selectedStock, setSelectedStock] = useState(null)
  const refresh = useAdvisorRefresh(data?.generated_at, reload)

  const watchlist = useMemo(() => {
    try { return JSON.parse(localStorage.getItem(WATCH_KEY)) || ['AAPL', 'MSFT'] }
    catch { return ['AAPL', 'MSFT'] }
  }, [])

  if (loading) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset yet — run python pipeline/fetch_advisor.py." />

  const rows = data.research
  const leader = rows[0]
  const macro = data.market?.macro || {}
  const regime = macro.regime
  const universeSize = data.universe_count || data.universe?.length || 0
  const sectorCounts = rows.reduce((counts, row) => ({
    ...counts, [row.sector || 'Unclassified']: (counts[row.sector || 'Unclassified'] || 0) + 1,
  }), {})
  const topSector = Object.entries(sectorCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'Unavailable'
  const averageConfidence = rows.reduce((sum, row) => sum + (row.confidence || 0), 0) / rows.length
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 3)
  const benchmarkTrend = recentReturn(data.benchmark_history?.closes || [])
  const trendRows = rows
    .map((row) => {
      const trendReturn = recentReturn(historyValues(row))
      return {
        ...row,
        trendReturn,
        trendRelative: trendReturn == null || benchmarkTrend == null ? null : trendReturn - benchmarkTrend,
      }
    })
    .filter((row) => Number.isFinite(row.trendReturn))
    .sort((left, right) => right.trendReturn - left.trendReturn)
  const strengthening = trendRows.slice(0, 2)
  const cooling = trendRows.slice(-2).reverse()

  return (
    <>
      <header className="dashboard-intro">
        <div>
          <span className="eyebrow">Research overview</span>
          <h1>Good morning.<br /><span>Here’s the signal.</span></h1>
        </div>
        <div className="refresh-control">
          <div className="stamp">Refreshed {humanDate(data.generated_at)}</div>
          {currentUser && (
            <button className="secondary-button compact refresh-button" onClick={refresh.requestRefresh}
              disabled={refresh.refreshing}>
              <Icon name="sync" size={17}
                className={refresh.refreshing ? 'refresh-spin' : ''} />
              {refresh.refreshing ? 'Refreshing…' : 'Refresh data'}
            </button>
          )}
          {refresh.message && (
            <span className={`refresh-message ${refresh.status}`} role="status" aria-live="polite">
              {refresh.message}
            </span>
          )}
        </div>
      </header>

      <section className="hero-research" aria-labelledby="top-pick-heading">
        <div className="hero-copy">
          <div className="hero-labels">
            <span className="rank-badge large">Rank #1</span>
            <Tier label={leader.stance} />
          </div>
          <div className="hero-company">
            <span className="hero-ticker">{leader.ticker}</span>
            <div><h2 id="top-pick-heading">{leader.name}</h2><p>{leader.sector || 'Sector unavailable'}</p></div>
          </div>
          <div className="hero-score-row">
            <div><span>Overall research score</span><strong>{leader.score}</strong><small>/ 100</small></div>
            <div className="confidence-ring" style={{ '--confidence': `${Math.round(leader.confidence * 100)}%` }}>
              <strong>{Math.round(leader.confidence * 100)}%</strong><span>data confidence</span>
            </div>
          </div>
          <div className="hero-stat-row">
            <div><span>20-day return</span><Move pct={leader.technical_detail?.return_20d} /></div>
            <div><span>Research rating</span><b>{leader.stance}</b></div>
          </div>
          <button className="primary-button" onClick={() => setSelectedStock(leader)}>
            View research <Icon name="arrow" size={18} />
          </button>
        </div>
        <div className="hero-chart">
          <div className="chart-caption"><span>Market trend</span><span>Available history only</span></div>
          <Sparkline values={historyValues(leader)} label={`${leader.name} price trend`} height={230} />
        </div>
      </section>

      <div className="section-heading">
        <div><span className="eyebrow">Ranked next</span><h2>Top candidates</h2></div>
        <Link to="/research">See all <Icon name="arrow" size={17} /></Link>
      </div>
      <section className="candidate-carousel" aria-label="Top research candidates">
        {rows.slice(1, 5).map((row, index) => (
          <CandidateCard key={row.ticker} row={row} rank={index + 2} onOpen={setSelectedStock} />
        ))}
      </section>

      {trendRows.length >= 4 && (
        <>
          <div className="section-heading">
            <div><span className="eyebrow">Price momentum</span><h2>Market trends</h2></div>
            <Link to="/market">Open market pulse <Icon name="arrow" size={17} /></Link>
          </div>
          <section className="trend-grid" aria-label="Strongest and weakest 20-day market trends">
            {strengthening.map((row) => (
              <TrendCard key={row.ticker} row={row} direction="Strengthening" onOpen={setSelectedStock} />
            ))}
            {cooling.map((row) => (
              <TrendCard key={row.ticker} row={row} direction="Cooling" onOpen={setSelectedStock} />
            ))}
          </section>
        </>
      )}

      <section className="summary-grid" aria-label="Research summary">
        <article><span>Universe analyzed</span><strong>{universeSize}</strong><small>configured companies</small></article>
        <article><span>Published research</span><strong>{rows.length}</strong><small>highest evidence scores</small></article>
        <article><span>Leading sector</span><strong className="summary-word">{topSector}</strong><small>within published results</small></article>
        <article><span>Average confidence</span><strong>{Math.round(averageConfidence * 100)}%</strong><small>coverage, not return odds</small></article>
      </section>

      <div className="dashboard-columns">
        <section>
          <div className="section-heading compact"><div><span className="eyebrow">Economic context</span><h2>Macro backdrop</h2></div></div>
          <div className="macro-grid">
            <MacroCard label="10Y Treasury" point={macro.treasury_10y} suffix="%" />
            <MacroCard label="Fed funds rate" point={macro.federal_funds_rate} suffix="%" />
            <MacroCard label="Inflation" point={macro.inflation} suffix="%" />
            <MacroCard label="FRED regime" point={{ value: regime?.score, date: regime?.freshness_date }}
              suffix="/100" detail={regime ? `${regime.label} · ${Math.round(regime.coverage * 100)}% coverage` : undefined} />
          </div>
          {regime && <p className="fred-notice">
            {regime.notice} Data attribution: {regime.attribution}. By using this application,
            users agree to the <a href={regime.terms_url} target="_blank" rel="noreferrer">FRED API Terms of Use</a>.
          </p>}
        </section>
        <section>
          <div className="section-heading compact">
            <div><span className="eyebrow">Saved names</span><h2>Watchlist</h2></div>
            <Link to="/watchlist">See all</Link>
          </div>
          <div className="watch-preview">
            {watchRows.map((row) => (
              <button key={row.ticker} onClick={() => setSelectedStock(row)}>
                <div><b>{row.ticker}</b><span>{row.name}</span></div>
                <Sparkline values={historyValues(row)} height={40} label={`${row.ticker} trend`} />
                <div><strong>{row.price ? `$${row.price.toFixed(2)}` : 'Price unavailable'}</strong><Move pct={row.pct_30d} /></div>
              </button>
            ))}
            {!watchRows.length && <div className="inline-empty">No saved ticker is in the current published research set.</div>}
          </div>
        </section>
      </div>

      <Link to="/research" className="rankings-cta">
        <div><span>Complete research list</span><strong>View all {rows.length} rankings</strong></div>
        <Icon name="arrow" size={24} />
      </Link>

      <p className="method-link">Ranked using fundamentals, valuation, market behavior, and recent news. <Link to="/methodology">Read the methodology.</Link></p>
      <div className="disclaimer">{data.disclaimer}</div>
      {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
    </>
  )
}
