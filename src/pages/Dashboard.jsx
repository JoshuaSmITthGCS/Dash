import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData'
import { Tier, Move, Loading, Empty, RefreshProgress } from '../components/Bits.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import { getRecommendation } from '../lib/recommendation'
import { humanDate } from '../lib/formatters'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import {
  activeThemes, rankGrowingEtfs, rankMomentum, rankThemeExposure, rankValueTurnarounds,
} from '../lib/researchScreens'

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
  const trendValues = historyValues(row).filter(Number.isFinite).slice(-5)
  const trendReturn = recentReturn(trendValues)
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
      <Sparkline values={trendValues} label={`${row.ticker} one-month trend`} height={54} />
      <div className="candidate-metrics">
        <div><span>Score</span><b>{row.score}</b></div>
        <div><span>1-month return</span><Move pct={trendReturn} /></div>
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

function ScreenRow({ row, rank, type, onOpen }) {
  const isValue = type === 'value'
  return (
    <button onClick={() => onOpen(row)} aria-label={`Open ${row.name} research`}>
      <span className="screen-rank">#{rank}</span>
      <span className="screen-company"><b>{row.ticker}</b><small>{row.name}</small></span>
      <span><small>{isValue ? 'Above 52w low' : 'This week'}</small><Move pct={isValue ? row.screen.aboveLow : row.screen.weekReturn} /></span>
      <span><small>{isValue ? 'This week' : '20 days'}</small><Move pct={isValue ? row.screen.weekReturn : row.screen.monthReturn} /></span>
      <Icon name="chevron" size={17} />
    </button>
  )
}

// ETFs carry a different shape than the stock screens (a blended score plus multi-window
// returns vs the S&P 500 and the Dow), so they get their own row instead of overloading
// ScreenRow's two-metric layout.
const PEER_GROUP_LABELS = {
  equity_broad: 'broad equity', equity_income: 'dividend', equity_sector: 'sector',
  equity_thematic: 'thematic', equity_international: 'international',
  fixed_income: 'bonds', commodity: 'commodity', crypto: 'crypto',
  _pooled: 'mixed asset classes',
}

function EtfScreenRow({ row, rank, onOpen }) {
  const oneYearReturn = row.returns?.['1y']
  const vsSp500 = row.vs_benchmarks?.sp500_1y
  // Rank only means something inside a peer group; comparing a bond fund's score to an
  // equity fund's is an artifact of the batch, so the label says which group it is.
  const group = PEER_GROUP_LABELS[row.ranked_against] || row.ranked_against
  const peerNote = row.peer_rank && !row.cross_asset_class_rank
    ? `#${row.peer_rank} of ${row.peer_group_size} ${group}`
    : row.cross_asset_class_rank
      ? 'ranked across asset classes'
      : row.name
  return (
    <button onClick={() => onOpen(row)} aria-label={`Open ${row.name} research`}>
      <span className="screen-rank">#{rank}</span>
      <span className="screen-company"><b>{row.ticker}</b><small>{peerNote}</small></span>
      <span><small>1-year return</small><Move pct={oneYearReturn} /></span>
      <span><small>Vs S&amp;P 500</small><Move pct={vsSp500} /></span>
      <Icon name="chevron" size={17} />
    </button>
  )
}

// Theme rows carry a different shape again: an exposure score, the guardrail verdict, and
// an opportunity score that combines exposure with business quality and valuation discipline.
// Excluded names stay on the board — high exposure at a euphoric price is worth seeing — but
// they are visibly marked so nobody reads them as the screen's recommendation.
function ThemeRow({ row, rank, onOpen, research }) {
  const full = research.find((item) => item.ticker === row.ticker)
  return (
    <button
      onClick={() => onOpen(full || row)}
      aria-label={`Open ${row.name || row.ticker} research`}
      className={row.eligible ? undefined : 'screen-row-flagged'}
    >
      <span className="screen-rank">#{rank}</span>
      <span className="screen-company">
        <b>{row.ticker}</b>
        <small>{row.eligible ? row.name : `${row.name} · valuation already stretched`}</small>
      </span>
      <span><small>Exposure</small><b>{Math.round(row.theme_exposure_score)}</b></span>
      <span>
        <small>Quality</small>
        <b>{Number.isFinite(row.fundamental_score) ? Math.round(row.fundamental_score) : '—'}</b>
      </span>
      <Icon name="chevron" size={17} />
    </button>
  )
}

function ThemePanel({ theme, onOpen, rows }) {
  const ranked = rankThemeExposure(theme)
  const leading = (theme.signals || []).filter((signal) => signal.leading).length
  return (
    <article className="stock-screen-panel">
      <header>
        <div>
          <span>Top {ranked.length} of {theme.count}</span>
          <h3>{theme.display_name}</h3>
        </div>
        <small>
          {theme.eligible_count} clear the valuation guardrail · {leading} leading signals
        </small>
      </header>
      <div className="stock-screen-list">
        {ranked.map((row, index) => (
          <ThemeRow key={row.ticker} row={row} rank={index + 1} onOpen={onOpen} research={rows} />
        ))}
        {!ranked.length && (
          <div className="inline-empty">No company currently has measurable exposure to this theme.</div>
        )}
      </div>
    </article>
  )
}

export default function Dashboard() {
  const { data, loading, reload } = useData('advisor.json')
  const { data: etfData } = useData('etfs.json')
  const { currentUser } = useAuth()
  const [selectedStock, setSelectedStock] = useState(null)

  const watchlist = useMemo(() => {
    try { return JSON.parse(localStorage.getItem(WATCH_KEY)) || ['AAPL', 'MSFT'] }
    catch { return ['AAPL', 'MSFT'] }
  }, [])
  const refresh = useAdvisorRefresh(data?.generated_at, reload, watchlist)

  if (loading) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset yet — run python pipeline/fetch_advisor.py." />

  const rows = data.research
  const leader = rows[0]
  const leaderTrendValues = historyValues(leader).filter(Number.isFinite).slice(-5)
  const leaderTrendReturn = recentReturn(leaderTrendValues)
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
  // The screens rank on price behavior, not the fundamentals-led composite score used to
  // decide which names get published, so scan the full scored universe, not just the leaderboard.
  const screenRows = [...rows, ...(data.screen_universe || [])]
  const valueTurnarounds = rankValueTurnarounds(screenRows)
  const momentumLeaders = rankMomentum(screenRows)
  // ETFs are ranked against each other in a separate dataset (public/data/etfs.json),
  // not folded into the stock screen universe — a diversified fund doesn't clear the same
  // fundamentals/momentum bars a single stock does, so a blended score decides its rank.
  const etfUniverse = etfData?.etfs || []
  const growingEtfs = rankGrowingEtfs(etfUniverse)
  // Theme exposure is a separate screen, deliberately not folded into the research score.
  const themeScreens = activeThemes(data.theme_screen)
  const sp500Benchmark = etfUniverse.find((row) => row.ticker === etfData?.benchmarks?.sp500)
  const dowBenchmark = etfUniverse.find((row) => row.ticker === etfData?.benchmarks?.dow)

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
                className={refresh.refreshing && refresh.activeMode === 'data' ? 'refresh-spin' : ''} />
              {refresh.refreshing && refresh.activeMode === 'data' ? 'Refreshing…' : 'Refresh data'}
            </button>
          )}
          {currentUser && (
            <button className="secondary-button compact refresh-button" onClick={refresh.requestReanalyze}
              disabled={refresh.refreshing}
              title="Re-score the last published data without fetching anything new — takes a couple of minutes">
              <Icon name="research" size={17}
                className={refresh.refreshing && refresh.activeMode === 'rescore' ? 'refresh-spin' : ''} />
              {refresh.refreshing && refresh.activeMode === 'rescore' ? 'Reanalyzing…' : 'Reanalyze'}
            </button>
          )}
          <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
            percent={refresh.progress} stage={refresh.stage} />
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
            <div><span>1-month return</span><Move pct={leaderTrendReturn} /></div>
            <div><span>Research rating</span><b>{leader.stance}</b></div>
          </div>
          <button className="primary-button" onClick={() => setSelectedStock(leader)}>
            View research <Icon name="arrow" size={18} />
          </button>
        </div>
        <div className="hero-chart">
          <div className="chart-caption"><span>One-month trend</span><span>Five weekly observations</span></div>
          <Sparkline values={leaderTrendValues} label={`${leader.name} one-month price trend`} height={230} />
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

      <div className="section-heading">
        <div><span className="eyebrow">Focused screens</span><h2>Value turnarounds, momentum, and top ETFs</h2></div>
        <Link to="/research">Compare research <Icon name="arrow" size={17} /></Link>
      </div>
      <section className="stock-screen-grid" aria-label="Focused stock and ETF research screens">
        <article className="stock-screen-panel">
          <header>
            <div><span>Top 5</span><h3>Value near 52-week lows</h3></div>
            <small>Strong fundamentals · positive latest week</small>
          </header>
          <div className="stock-screen-list">
            {valueTurnarounds.map((row, index) => (
              <ScreenRow key={row.ticker} row={row} rank={index + 1} type="value" onOpen={setSelectedStock} />
            ))}
            {!valueTurnarounds.length && <div className="inline-empty">No published stock currently clears every value-turnaround requirement.</div>}
          </div>
        </article>
        <article className="stock-screen-panel">
          <header>
            <div><span>Top 5</span><h3>Recent momentum</h3></div>
            <small>Positive week and month · relative strength ranked</small>
          </header>
          <div className="stock-screen-list">
            {momentumLeaders.map((row, index) => (
              <ScreenRow key={row.ticker} row={row} rank={index + 1} type="momentum" onOpen={setSelectedStock} />
            ))}
            {!momentumLeaders.length && <div className="inline-empty">No published stock currently clears every momentum requirement.</div>}
          </div>
        </article>
        <article className="stock-screen-panel">
          <header>
            <div><span>Top 5 of {etfUniverse.length || 40}</span><h3>Top ETFs</h3></div>
            <small>Performance, risk, cost, liquidity &amp; issuer quality</small>
          </header>
          {(sp500Benchmark || dowBenchmark) && (
            <div className="etf-benchmark-strip">
              {sp500Benchmark && <span>S&amp;P 500 (1Y) <Move pct={sp500Benchmark.returns?.['1y']} /></span>}
              {dowBenchmark && <span>Dow (1Y) <Move pct={dowBenchmark.returns?.['1y']} /></span>}
            </div>
          )}
          <div className="stock-screen-list">
            {growingEtfs.map((row, index) => (
              <EtfScreenRow key={row.ticker} row={row} rank={index + 1} onOpen={setSelectedStock} />
            ))}
            {!growingEtfs.length && <div className="inline-empty">ETF ranking data isn't available yet.</div>}
          </div>
        </article>
      </section>
      <p className="screen-disclaimer">
        Research screens, not trade instructions. Prices can gap before the open; confirm the current quote,
        liquidity, news, and your order limits before acting.
      </p>

      {themeScreens.length > 0 && (
        <>
          <div className="section-heading">
            <div>
              <span className="eyebrow">Structural trends</span>
              <h2>Theme exposure</h2>
            </div>
            <Link to="/methodology">How exposure is measured <Icon name="arrow" size={17} /></Link>
          </div>
          <section className="stock-screen-grid" aria-label="Structural trend exposure screens">
            {themeScreens.map((theme) => (
              <ThemePanel key={theme.id} theme={theme} onOpen={setSelectedStock} rows={rows} />
            ))}
          </section>
          <p className="screen-disclaimer">
            Exposure is measured from filings and supply-chain evidence, never from price. Share-price
            momentum contributes nothing to these scores by design, and companies already priced in the
            top valuation decile of their sector are flagged rather than promoted — buying structural
            themes after they are priced in is the documented way thematic funds lose money.
          </p>
        </>
      )}

      {trendRows.length >= 4 && (
        <>
          <div className="section-heading">
            <div><span className="eyebrow">Price momentum</span><h2>Market trends</h2></div>
            <Link to="/market">Open market pulse <Icon name="arrow" size={17} /></Link>
          </div>
          <section className="trend-grid" aria-label="Strongest and weakest one-month market trends">
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
