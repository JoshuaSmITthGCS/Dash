import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { useWatchlist } from '../lib/useWatchlist.js'
import { useFirebaseFinances } from '../lib/useFirebaseFinances.js'
import { buildPortfolioPriceData, mergePortfolioQuotes, mergePositionSnapshots } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  BENCHMARKS, compareBenchmarkSeries, concentrationLiquidityScore, currentHoldingsSeries, diversificationScore,
  enrichPortfolio, latestMarketDayReturn, performanceMetrics, portfolioScore,
  resilienceIndex, riskFreeAnnualRate, selectPeriod, sliceSeriesFrom,
} from '../lib/portfolioAnalytics.js'
import { Loading, Empty, Move } from '../components/Bits.jsx'
import DotPlot from '../components/DotPlot.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'
import { getRecommendation } from '../lib/recommendation.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes.js'
import { liveTodayPortfolioReturn } from '../lib/afterHoursQuotes.js'
import { rankBreakoutInProgress, rankBuyingTheDip, rankGrowingEtfs, rankMomentum, rankReversal, rankValueTurnarounds } from '../lib/researchScreens.js'
import BuyingTheDipChart from '../components/BuyingTheDipChart.jsx'
import { currentHoldingsPerformanceSeriesForPeriod } from '../lib/portfolioPerformance.js'
import { PerformanceEvidenceSummary } from '../components/PerformanceMetrics.jsx'
import LiveTrackingCountdown from '../components/LiveTrackingCountdown.jsx'
import ProjectionPanel from '../components/ProjectionPanel.jsx'
import { applyAllocationAssumption, normalizeAnnualReturnTarget, projectionConfig, selectProjectionReturnSource } from '../lib/projectionEngine.js'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'
import { fidelityProjectionBaseline } from '../lib/referenceCashFlows.js'
import modelSettings from '../../pipeline/config/settings.json'
import { LIVE_TRACKING_START } from '../lib/liveTrackingAvailability.js'
import AllocationDonut from '../components/AllocationDonut.jsx'
import ScoreGauge from '../components/ScoreGauge.jsx'
import MarketHeatmap from '../components/MarketHeatmap.jsx'
import Sparkline from '../components/Sparkline.jsx'
import { dailyMoveForPosition, marketType, rankDailySectors, rankDailyStocks } from '../lib/marketPresentation.js'
import {
  CircularRadar,
  LiveClock,
  TechPanel,
  DataStrip,
  MetricGrid,
  StatusMatrix,
  SectorDonut,
} from '../lib/hudUltra.jsx'

const PERIODS = ['1H', '1D', '1W', '1M', '3M', '1Y']
const PERIOD_LABELS = { '1H': 'Last hour', '1D': 'Today', '1W': 'Week', '1M': 'Month', '3M': '3 months', '1Y': 'Year' }
const interfaceConfig = modelSettings.interface

function HudScoreCard({ label, result, note }) {
  return <article className="report-score-card hud-card">
    <ScoreGauge score={result?.score || 0} available={result?.available} label={label} provisional={result?.provisional} reason={result?.reason} />
    <div>
      <h3>{label}</h3>
      <p>{result?.available ? note : result?.reason || 'Not enough portfolio data yet.'}</p>
    </div>
  </article>
}

function HudMarketSummary({ rows, macro, researchLeader }) {
  const ranked = rankDailyStocks(rows)
  const sectors = rankDailySectors(rows)
  const session = marketType(rows)
  const leader = ranked[0]
  return <section className="home-market-summary hud-panel" aria-label="Market summary">
    <div className={`home-market-type ${session.tone}`}><span aria-hidden="true" /><div><small>Today's market</small><strong>{session.label}</strong></div></div>
    <div><small>Market breadth</small><strong>{session.breadthPct == null ? 'Pending' : `${session.breadthPct.toFixed(0)}% advancing`}</strong></div>
    <div><small>Hottest sector</small><strong title={sectors[0]?.sector || undefined}>{sectors[0]?.sector || 'Pending'}{sectors[0] && ` · ${signedPct(sectors[0].averagePct)}`}</strong></div>
    <div><small>Biggest mover</small><strong>{leader ? `${leader.ticker} · ${signedPct(leader.dailyMove.pct)}` : 'Pending'}</strong></div>
    <div><small>Research leader</small><strong>{researchLeader ? `${researchLeader.ticker} · ${researchLeader.score}` : 'Pending'}</strong></div>
    <div><small>Macro backdrop</small><strong>{macro?.regime?.label || 'Pending'}</strong></div>
    <Link to="/markets">Open Markets <Icon name="arrow" size={15} /></Link>
  </section>
}

function HudPortfolioPanel({
  positions,
  period,
  onPeriodChange,
  money,
  totalValue,
  totalProfit,
  today,
  topStocks,
}) {
  const [holdingsSort, setHoldingsSort] = useState('day')

  const ranked = positions.map((position) => ({ ...position, move: dailyMoveForPosition(position) }))
    .sort((left, right) => holdingsSort === 'allocation'
      ? (right.allocationPct ?? -Infinity) - (left.allocationPct ?? -Infinity)
      : (right.move.pct ?? -Infinity) - (left.move.pct ?? -Infinity))
    .slice(0, 5)

  return <section className="home-primary-grid hud-grid" aria-label="Portfolio performance and leading holdings">
    <article className="home-performance-card hud-card">
      <header className="home-performance-head">
        <label><span>Portfolio radar</span><select value={period} onChange={(event) => onPeriodChange(event.target.value)}>{PERIODS.map((item) => <option key={item} value={item}>{PERIOD_LABELS[item]}</option>)}</select></label>
        <div className="home-performance-kpis">
          <span><small>Invested value</small><strong>{money(totalValue)}</strong></span>
          <span><small>Today · regular session</small><strong className={today?.dollarReturn >= 0 ? 'positive' : 'negative'}>{today ? `${today.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(today.dollarReturn))} · ${signedPct(today.returnPct, 2)}` : 'Unavailable'}</strong></span>
          <span><small>Total profit · {PERIOD_LABELS[period]}</small><strong className={totalProfit >= 0 ? 'positive' : 'negative'}>{totalProfit == null ? 'Unavailable' : `${totalProfit >= 0 ? '+' : '−'}${money(Math.abs(totalProfit))}`}</strong></span>
        </div>
      </header>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '360px' }}>
        <CircularRadar stocks={topStocks} onStockClick={(stock) => window.location.href = `/research?ticker=${stock.ticker}`} />
      </div>
      <footer><span><i aria-hidden="true" />Top holdings radar</span><small>Circular position display · Click any stock to view details</small></footer>
    </article>

    <aside className="home-top-holdings hud-card">
      <header><div><span className="eyebrow">Your portfolio</span><h2>Top 5 holdings</h2></div><label><span className="sr-only">Rank holdings by</span><select value={holdingsSort} onChange={(event) => setHoldingsSort(event.target.value)}><option value="day">Today's performance</option><option value="allocation">Biggest allocation</option></select></label></header>
      <div>{ranked.map((position, index) => <article key={position.id || position.ticker} className={position.move.pct == null ? 'neutral' : position.move.pct >= 0 ? 'positive' : 'negative'}>
        <span className="holding-rank">{index + 1}</span><CompanyLogo company={position.priceInfo || position} size={36} /><span className="top-holding-name"><strong>{position.ticker}</strong><small>{position.allocationPct == null ? 'Allocation pending' : `${position.allocationPct.toFixed(1)}% allocation`}</small></span><span className="top-holding-move"><strong>{signedPct(position.move.pct, 2)}</strong><small>{position.move.positionDelta == null ? 'Day delta pending' : `${position.move.positionDelta >= 0 ? '+' : '−'}${money(Math.abs(position.move.positionDelta))}`}</small></span>
      </article>)}</div>
      <Link to="/portfolio">View all holdings <Icon name="arrow" size={15} /></Link>
    </aside>
  </section>
}

function HudScreenCard({ title, kicker, note, rows, metric, loading, to }) {
  return <article className="report-screen-card hud-card">
    <header><div><span>{kicker}</span><h3>{title}</h3></div><small>{note}</small></header>
    <div className="report-screen-list">
      {loading ? <div className="report-inline-loading" role="status">Loading this screen…</div>
        : rows.length ? rows.map((row, index) => {
          const detail = metric(row)
          return <div key={row.ticker}><CompanyLogo company={row} size={28} /><span className="screen-rank">#{index + 1}</span><span className="screen-company"><b>{row.ticker}</b><small>{row.name}</small></span><span className="report-screen-metric"><small>{detail.label}</small><Move pct={detail.value} /></span></div>
        })
          : <div className="report-inline-loading">No name clears this screen.</div>}
    </div>
    <Link className="report-screen-link" to={to}>Open full screen <Icon name="arrow" size={16} /></Link>
  </article>
}

const MACRO_FACTOR_LABELS = [['rates', 'Rates'], ['inflation', 'Inflation'], ['labor', 'Labor']]

function HudMarketPulse({ data, loading }) {
  const macro = data?.market?.macro || {}
  const regime = macro.regime
  const items = [
    ['10Y Treasury', macro.treasury_10y, '%'],
    ['Fed funds', macro.federal_funds_rate, '%'],
    ['Inflation', macro.inflation, '%'],
  ]
  const factorRows = MACRO_FACTOR_LABELS
    .map(([key, label]) => {
      const factor = regime?.factors?.[key]
      return factor?.score == null ? null : { id: key, label: `${label} · ${factor.label}`, value: factor.score }
    })
    .filter(Boolean)

  return <section className="report-section report-market-pulse hud-section" aria-labelledby="report-market-pulse-title">
    <header className="section-heading"><div><span className="eyebrow">Market pulse</span><h2 id="report-market-pulse-title">The current backdrop</h2></div><Link to="/market">News and context →</Link></header>
    {loading && !data ? <div className="report-inline-loading" role="status">Loading Market Pulse…</div> : <>
      <div className="report-market-grid">
        <article className={regime?.score == null ? 'is-unavailable' : undefined}><span>FRED regime</span><strong>{regime?.score ?? '–'}{regime?.score != null && <small>/100</small>}</strong><p>{regime?.label || 'Regime data pending'}</p></article>
        {items.map(([label, point, suffix]) => <article key={label} className={point?.value == null ? 'is-unavailable' : undefined}><span>{label}</span><strong>{point?.value ?? '–'}{point?.value != null ? suffix : ''}</strong><p>{point?.date ? `Through ${point.date}` : 'Not published in this run'}</p></article>)}
      </div>
      {factorRows.length > 1 && (
        <DotPlot
          rows={factorRows}
          xLabel="Factor score (0-100, higher is more supportive)"
          xFormatter={(value) => value.toFixed(1)}
          domain={{ min: 0, max: 100 }}
          caption="What the FRED regime score is composed of: rates, inflation, and labor factor scores"
        />
      )}
    </>}
  </section>
}

export default function CommandCenter() {
  const { data, loading } = useData('report.json')
  const { data: etfData, loading: etfLoading } = useData('etfs.json')
  const { currentUser, authError, retryAuth } = useAuth()
  const { positions: storedPositions, loading: portfolioLoading } = useFirebasePortfolio()
  const previewPortfolio = import.meta.env.DEV
    && new window.URLSearchParams(window.location.search).get('portfolioPreview') === '1'
  const positions = previewPortfolio ? interfaceConfig.mobile_preview_positions : storedPositions
  const hasPortfolioAccess = currentUser || previewPortfolio
  const finances = useFirebaseFinances()
  const tracking = usePortfolioTracking()
  const portfolioQuotes = usePortfolioQuotes(positions.map((position) => position.ticker))
  const { preferences, updatePreferences } = usePreferences()
  const { data: benchmarkReport, loading: benchmarkLoading } = useData(positions.length ? 'benchmark-report.json' : null)
  const [period, setPeriod] = useState('1D')
  const [sinceLiveTrackingOnly, setSinceLiveTrackingOnly] = useState(false)
  const { items: watchlistItems } = useWatchlist()
  const watchlist = useMemo(() => watchlistItems.map((item) => item.ticker), [watchlistItems])

  if (loading || (hasPortfolioAccess && !previewPortfolio && (portfolioLoading || finances.loading || (positions.length > 0 && benchmarkLoading)))) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const publishedPrices = mergePositionSnapshots(
    buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows),
    positions,
    data.generated_at,
  )
  const quoteRefreshIsNewest = portfolioQuotes.fetchedAt
    && new Date(portfolioQuotes.fetchedAt) >= new Date(data?.generated_at || 0)
  const prices = mergePortfolioQuotes(publishedPrices, quoteRefreshIsNewest ? portfolioQuotes.quotes : {})
  const portfolio = enrichPortfolio(positions, prices)
  const holdingsSeries = currentHoldingsSeries(positions, prices, data.benchmark_history?.dates || [])
  const selected = period === '1H' ? null : selectPeriod(holdingsSeries, period)
  const selectedBenchmarkSymbols = preferences.defaultBenchmarks || [preferences.defaultBenchmark]
  const selectedBenchmarkSeries = selectedBenchmarkSymbols.map((symbol) => {
    const history = benchmarkReport?.histories?.[symbol]
    const definition = BENCHMARKS.find((item) => item.symbol === symbol)
    return history ? { symbol, label: definition?.label || symbol, dates: history.dates, closes: history.closes } : null
  }).filter(Boolean)
  const comparison = compareBenchmarkSeries(selected, selectedBenchmarkSeries)
  const chartedPortfolio = comparison?.portfolio || selected
  const recordedZoomSeries = currentHoldingsPerformanceSeriesForPeriod(tracking.snapshots, positions, prices, period)
  const homeChart = recordedZoomSeries || chartedPortfolio
  const homePeriodProfit = homeChart?.dollarReturn
    ?? (homeChart?.values?.length > 1 ? homeChart.values.at(-1) - homeChart.values[0] : null)
  const today = latestMarketDayReturn(holdingsSeries)
  const liveToday = liveTodayPortfolioReturn(positions, prices)
  const heroToday = liveToday.available
    ? liveToday
    : today ? { dollarReturn: today.dollarReturn, returnPct: today.returnPct } : null
  const diversification = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })
  const liveHoldingsSeries = sliceSeriesFrom(holdingsSeries, LIVE_TRACKING_START)
  const scoreHoldingsSeries = sinceLiveTrackingOnly ? liveHoldingsSeries : holdingsSeries
  const scorePortfolioPeriod = selectPeriod(scoreHoldingsSeries, '1Y') || selectPeriod(scoreHoldingsSeries, 'All')
  const scoreComparison = compareBenchmarkSeries(scorePortfolioPeriod, selectedBenchmarkSeries.slice(0, 1))
  const resilience = resilienceIndex(scoreComparison?.portfolio.values || scorePortfolioPeriod?.values || [], diversification)
  const riskFree = riskFreeAnnualRate(data)
  const performance = performanceMetrics(scoreComparison?.portfolio, scoreComparison?.benchmarks[0], riskFree.annualPct)
  const concentrationLiquidity = concentrationLiquidityScore(portfolio.positions)
  const overall = portfolioScore({ diversification, resilience, performance, benchmarkEfficiency: null, concentrationLiquidity, dataCompleteness: Math.round(portfolio.coveragePct || 0) })
  const leader = rows[0]
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 4)
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  const tone = (value) => value == null ? '' : value >= 0 ? 'positive' : 'negative'
  const actionable = portfolio.positions.map((row) => ({ ...row, recommendation: row.priceInfo ? getRecommendation(row.priceInfo) : null })).filter((row) => row.recommendation?.action === 'SELL')
  const sectorAllocation = Object.entries(portfolio.positions.reduce((totals, position) => {
    const sector = position.priceInfo?.sector || 'Unclassified'
    totals[sector] = (totals[sector] || 0) + Number(position.currentValue || 0)
    return totals
  }, {})).map(([sector, value]) => ({ sector, value, pct: portfolio.totalValue ? value / portfolio.totalValue * 100 : 0 }))
    .sort((left, right) => right.value - left.value)

  const screenRows = [...new Map([...rows, ...(data.screen_universe || [])].map((row) => [row.ticker, row])).values()]
  const dipRows = rankBuyingTheDip(screenRows, 8)
  const focusedScreens = [
    { title: 'Fast growth breakouts', kicker: 'Fast growth', note: 'Sharp acceleration this week', rows: rankBreakoutInProgress(screenRows, 3), metric: (row) => ({ label: '5 days', value: row.screen.weekReturn }), to: '/screens/fast-growth' },
    { title: 'Value near 52-week lows', kicker: 'Value turnarounds', note: 'Quality plus a positive latest week', rows: rankValueTurnarounds(screenRows, 3), metric: (row) => ({ label: 'Above low', value: row.screen.aboveLow }), to: '/screens/quality-value' },
    { title: 'Recent momentum', kicker: 'Momentum', note: 'Positive week and month', rows: rankMomentum(screenRows, 3), metric: (row) => ({ label: '20 days', value: row.screen.monthReturn }), to: '/screens/momentum' },
    { title: 'Short-term reversals', kicker: 'Reversal', note: '20-day pullback turning up', rows: rankReversal(screenRows, 3), metric: (row) => ({ label: 'This week', value: row.screen.weekReturn }), to: '/screens/matrix' },
    { title: 'Top ETFs', kicker: 'Fund screens', note: 'Performance, risk, cost and liquidity', rows: rankGrowingEtfs(etfData?.etfs || [], 3), metric: (row) => ({ label: '1 year', value: row.returns?.['1y'] }), loading: etfLoading, to: '/research' },
  ]

  // Top stocks for radar
  const topStocks = rows.slice(0, 16).map(row => ({
    ticker: row.ticker,
    name: row.name,
    score: row.score,
    sector: row.sector,
  }))

  // Market session
  const ranked = rankDailyStocks(rows)
  const sectors = rankDailySectors(rows)
  const session = marketType(rows)
  const topMover = ranked[0]

  // Macro data
  const macro = data?.market?.macro || {}
  const regime = macro.regime

  return <div className="command-center">
    {/* Background effects */}
    <div className="particle-field" aria-hidden="true">
      {[...Array(50)].map((_, i) => (
        <div
          key={i}
          className="particle"
          style={{
            left: `${Math.random() * 100}%`,
            top: `${Math.random() * 100}%`,
            animationDelay: `${Math.random() * 5}s`,
            animationDuration: `${3 + Math.random() * 4}s`,
          }}
        />
      ))}
    </div>

    <div className="command-grid">
      {/* Header */}
      <header className="command-header">
        <div className="command-title">
          <span className="command-logo">COMMAND</span>
          <span className="command-subtitle">Tactical Research Interface · <LiveClock /></span>
        </div>
        <div className="command-status">
          <div className="command-stat">
            <span className="command-stat-label">Universe</span>
            <span className="command-stat-value">{rows.length}</span>
          </div>
          <div className="command-stat">
            <span className="command-stat-label">Portfolio</span>
            <span className="command-stat-value">{positions.length}</span>
          </div>
          <div className="command-stat">
            <span className="command-stat-label">Status</span>
            <span className="command-stat-value">LIVE</span>
          </div>
        </div>
      </header>

      {/* Left side panels */}
      <div className="side-panel side-panel-left">
        {/* System status */}
        <TechPanel title="System status" active={true}>
          <StatusMatrix items={[
            { value: 'OK', label: 'Alpha Vantage' },
            { value: 'OK', label: 'Marketaux' },
            { value: 'OK', label: 'FRED' },
            { value: 'OK', label: 'Yahoo Data' },
            { value: 'OK', label: 'Yahoo News' },
            { value: 'OK', label: 'SEC Form 4' },
          ]} />
        </TechPanel>

        {/* Market summary */}
        <TechPanel title="Market pulse" active={true}>
          <DataStrip items={[
            { label: 'Session', value: session.label },
            { label: 'Breadth', value: session.breadthPct == null ? '—' : `${session.breadthPct.toFixed(0)}%` },
            { label: 'Hot sector', value: sectors[0]?.sector || '—' },
            { label: 'Top mover', value: topMover ? `${topMover.ticker} ${signedPct(topMover.dailyMove.pct)}` : '—' },
            { label: 'Macro', value: regime?.label || '—' },
          ]} />
        </TechPanel>

        {/* Portfolio overview */}
        {hasPortfolioAccess && positions.length > 0 && (
          <TechPanel title="Portfolio overview" active={true}>
            <DataStrip items={[
              { label: 'Total value', value: money(portfolio.totalValue) },
              { label: 'Today', value: heroToday ? `${heroToday.dollarReturn >= 0 ? '+' : ''}${money(Math.abs(heroToday.dollarReturn))}` : '—' },
              { label: 'Period', value: homePeriodProfit != null ? `${homePeriodProfit >= 0 ? '+' : ''}${money(Math.abs(homePeriodProfit))}` : '—' },
              { label: 'Holdings', value: String(positions.length) },
            ]} />
          </TechPanel>
        )}

        {/* Portfolio scores */}
        {hasPortfolioAccess && positions.length > 0 && (
          <TechPanel title="Portfolio scores" active={true}>
            <MetricGrid items={[
              { label: 'Overall', value: overall.score != null ? `${Math.round(overall.score)}/100` : '—' },
              { label: 'Diversification', value: diversification.score != null ? `${Math.round(diversification.score)}/100` : '—' },
              { label: 'Resilience', value: resilience.score != null ? `${Math.round(resilience.score)}/100` : '—' },
              { label: 'Coverage', value: portfolio.coveragePct != null ? `${Math.round(portfolio.coveragePct)}%` : '—' },
            ]} />
          </TechPanel>
        )}
      </div>

      {/* Central radar */}
      <CircularRadar
        stocks={topStocks}
        onStockClick={(stock) => window.location.href = `/research?ticker=${stock.ticker}`}
      />

      {/* Right side panels */}
      <div className="side-panel side-panel-right">
        {/* Research leader */}
        <TechPanel title="Research leader" active={true}>
          <div style={{ padding: 'var(--sp-2)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <CompanyLogo company={leader} size={40} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{leader.ticker}</div>
                <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-secondary)' }}>{leader.name}</div>
              </div>
              <div style={{ fontSize: 'var(--fs-2xl)', fontWeight: 700, color: 'var(--brand-primary)' }}>{leader.score}</div>
            </div>
            {leader.sparkline && <Sparkline values={leader.sparkline} height={40} />}
          </div>
        </TechPanel>

        {/* Top holdings */}
        {hasPortfolioAccess && positions.length > 0 && (
          <TechPanel title="Top holdings" active={true}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
              {portfolio.positions.slice(0, 5).map((position, index) => {
                const move = dailyMoveForPosition(position)
                return (
                  <div key={position.ticker} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--sp-2)',
                    padding: 'var(--sp-2)',
                    background: 'rgba(0, 0, 0, 0.3)',
                    borderRadius: 'var(--r-xs)',
                  }}>
                    <span style={{
                      fontSize: 'var(--fs-xs)',
                      color: 'var(--brand-primary)',
                      fontWeight: 700,
                      minWidth: '20px',
                    }}>{index + 1}</span>
                    <CompanyLogo company={position.priceInfo || position} size={28} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 'var(--fs-sm)' }}>{position.ticker}</div>
                      <div style={{ fontSize: 'var(--fs-2xs)', color: 'var(--text-secondary)' }}>
                        {position.allocationPct != null ? `${position.allocationPct.toFixed(1)}%` : '—'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{
                        fontSize: 'var(--fs-sm)',
                        fontWeight: 600,
                        color: move.pct == null ? 'var(--text-primary)' : move.pct >= 0 ? '#00ff88' : '#ff4466'
                      }}>
                        {move.pct != null ? signedPct(move.pct, 2) : '—'}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </TechPanel>
        )}

        {/* Sector allocation */}
        {hasPortfolioAccess && positions.length > 0 && sectorAllocation.length > 0 && (
          <TechPanel title="Sector allocation" active={true}>
            <div style={{ display: 'flex', justifyContent: 'center', padding: 'var(--sp-3)' }}>
              <SectorDonut sectors={sectorAllocation.slice(0, 5).map(s => ({ name: s.sector, count: Math.round(s.pct) }))} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
              {sectorAllocation.slice(0, 5).map((item) => (
                <div key={item.sector} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: 'var(--sp-1)',
                  fontSize: 'var(--fs-xs)',
                }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{item.sector}</span>
                  <span style={{ color: 'var(--brand-primary)', fontWeight: 700 }}>{item.pct.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </TechPanel>
        )}

        {/* Watchlist */}
        {watchRows.length > 0 && (
          <TechPanel title="Watchlist" active={true}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
              {watchRows.map((row) => (
                <div key={row.ticker} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--sp-2)',
                  padding: 'var(--sp-2)',
                  background: 'rgba(0, 0, 0, 0.3)',
                  borderRadius: 'var(--r-xs)',
                }}>
                  <CompanyLogo company={row} size={28} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: 'var(--fs-sm)' }}>{row.ticker}</div>
                  </div>
                  <div style={{ fontSize: 'var(--fs-lg)', fontWeight: 700, color: 'var(--brand-primary)' }}>{row.score}</div>
                  {row.dayChange != null && (
                    <div style={{
                      fontSize: 'var(--fs-sm)',
                      color: row.dayChange >= 0 ? '#00ff88' : '#ff4466'
                    }}>
                      {signedPct(row.dayChange)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </TechPanel>
        )}
      </div>

      {/* Footer */}
      <footer className="command-footer">
        <div className="command-footer-left">
          <span>Latest close: {String(data.generated_at).slice(0, 10)}</span>
          <span>Coverage: {rows.length} names</span>
        </div>
        <div className="command-footer-right">
          <span>Research-only • Not investment advice</span>
          <span>© 2024 ValueSignal</span>
        </div>
      </footer>
    </div>
  </div>
}
