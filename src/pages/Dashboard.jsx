import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { usePreferences, formatPreferenceMoney } from '../lib/PreferencesContext.jsx'
import { signedPct } from '../lib/formatters.js'
import {
  BENCHMARKS, compareBenchmarkSeries, concentrationLiquidityScore, currentHoldingsSeries, diversificationScore,
  enrichPortfolio, intradayPortfolioHigh, latestMarketDayReturn, performanceMetrics, portfolioReturnSummary, portfolioScore,
  resilienceIndex, riskFreeAnnualRate, selectPeriod, trackedAllTimeEarnings, trailingCashFlowPace,
} from '../lib/portfolioAnalytics.js'
import { beatMarketStreak, portfolioMood, valueStreak } from '../lib/traderInsights.js'
import { Loading, Empty, Move, RefreshProgress, Tier } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'
import { getRecommendation } from '../lib/recommendation.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes.js'
import { afterHoursPortfolioReturn } from '../lib/afterHoursQuotes.js'
import { rankGrowingEtfs, rankMomentum, rankReversal, rankValueTurnarounds } from '../lib/researchScreens.js'
import {
  actualRecordedValueSeries,
  PORTFOLIO_HISTORY_LABELS,
  selectPortfolioHistorySeries,
} from '../lib/portfolioPerformance.js'
import PortfolioReturnSummary from '../components/PortfolioReturnSummary.jsx'
import PerformanceMetrics from '../components/PerformanceMetrics.jsx'
import ProjectionPanel from '../components/ProjectionPanel.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import { projectionConfig, selectProjectionReturnSource } from '../lib/projectionEngine.js'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'
import { usePullToRefresh } from '../lib/usePullToRefresh.js'
import PullToRefreshIndicator from '../components/PullToRefreshIndicator.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh.js'

const WATCH_KEY = 'valuesignal.watchlist'
const PERIODS = ['1D', '1W', '1M', '3M', '6M', '1Y', 'All']
const BENCHMARK_STYLES = [
  { color: 'var(--series-benchmark)', dashPattern: '7 5' },
  { color: 'var(--series-benchmark-2)', dashPattern: '3 4' },
  { color: 'var(--series-benchmark-3)', dashPattern: '10 4 2 4' },
]

function Metric({ label, value, note, tone = '' }) {
  return <article className="report-metric"><span>{label}</span><strong className={tone}>{value}</strong><small>{note}</small></article>
}

function ScoreCard({ label, result, note }) {
  return <article className="report-score-card"><div className="score-orbit" style={{ '--score': result?.score || 0 }}><strong>{result?.available ? result.score : '—'}</strong><span>/100</span></div><div><h3>{label}</h3><p>{result?.available ? note : result?.reason || 'Not enough portfolio data yet.'}</p>{result?.provisional && <span className="provisional-badge">Provisional</span>}</div></article>
}

function DirectionPill({ value, children }) {
  const direction = value == null ? 'neutral' : value >= 0 ? 'positive' : 'negative'
  return <span className={`value-pill ${direction}`}>
    {value != null && <span className="value-pill-arrow" aria-hidden="true">{value >= 0 ? '▲' : '▼'}</span>}
    <span>{children}</span>
  </span>
}

function DashboardWidget({ id, widgets, children }) {
  const widget = widgets.find((item) => item.id === id)
  if (!widget?.visible) return null
  return <div className={`dashboard-widget dashboard-widget-${id}`} style={{ order: widget.order }}>{children}</div>
}

function FocusedScreenCard({ title, kicker, note, rows, metric, loading, to }) {
  return <article className="report-screen-card">
    <header><div><span>{kicker}</span><h3>{title}</h3></div><small>{note}</small></header>
    <div className="report-screen-list">
      {loading ? <div className="report-inline-loading" role="status">Loading this screen on the Report…</div>
        : rows.length ? rows.map((row, index) => {
          const detail = metric(row)
          return <div key={row.ticker}><span className="screen-rank">#{index + 1}</span><span className="screen-company"><b>{row.ticker}</b><small>{row.name}</small></span><span className="report-screen-metric"><small>{detail.label}</small><Move pct={detail.value} /></span></div>
        })
          : <div className="report-inline-loading">No name clears this screen in the latest report.</div>}
    </div>
    <Link className="report-screen-link" to={to}>Open full screen <Icon name="arrow" size={16} /></Link>
  </article>
}

function MarketPulsePreview({ data, loading }) {
  const macro = data?.market?.macro || {}
  const regime = macro.regime
  const items = [
    ['10Y Treasury', macro.treasury_10y, '%'],
    ['Fed funds', macro.federal_funds_rate, '%'],
    ['Inflation', macro.inflation, '%'],
  ]
  return <section className="report-section report-market-pulse" aria-labelledby="report-market-pulse-title">
    <header className="section-heading"><div><span className="eyebrow">Market pulse</span><h2 id="report-market-pulse-title">The current backdrop</h2></div><Link to="/market">News and context →</Link></header>
    {loading && !data ? <div className="report-inline-loading" role="status">Loading Market Pulse here on the Report…</div> : <div className="report-market-grid">
      <article><span>FRED regime</span><strong>{regime?.score ?? '—'}{regime?.score != null && <small>/100</small>}</strong><p>{regime?.label || 'Regime data pending'}</p></article>
      {items.map(([label, point, suffix]) => <article key={label}><span>{label}</span><strong>{point?.value ?? '—'}{point?.value != null ? suffix : ''}</strong><p>{point?.date ? `Through ${point.date}` : 'Period unavailable'}</p></article>)}
    </div>}
  </section>
}

function Customizer({ widgets, onChange, onDone }) {
  const move = (index, direction) => {
    const target = index + direction
    if (target < 0 || target >= widgets.length) return
    const next = [...widgets]; [next[index], next[target]] = [next[target], next[index]]
    onChange(next.map((widget, order) => ({ ...widget, order })))
  }
  return <aside className="customizer-panel"><div className="customizer-head"><div><span className="eyebrow">Settings</span><h2>Customize report</h2></div><button className="icon-button" onClick={onDone} aria-label="Close customization"><Icon name="close" /></button></div><p>Choose supporting modules and their reading order. Core financial-report metrics always remain visible.</p><div className="customizer-list">{widgets.map((widget, index) => <div className="customizer-row" key={widget.id}><Icon name="grip" /><div><strong>{widget.label}</strong><small>{widget.locked ? 'Required' : `Position ${index + 1}`}</small></div><label className="switch compact-switch"><span className="sr-only">Show {widget.label}</span><input type="checkbox" checked={widget.visible} disabled={widget.locked} onChange={(event) => onChange(widgets.map((item) => item.id === widget.id ? { ...item, visible: event.target.checked } : item))} /><span /></label><div className="reorder-buttons"><button onClick={() => move(index, -1)} disabled={!index}><Icon name="up" /></button><button onClick={() => move(index, 1)} disabled={index === widgets.length - 1}><Icon name="down" /></button></div></div>)}</div><button className="primary-button" onClick={onDone}>Save report</button></aside>
}

function ReportProjection({ input, source, money, currentAge, retirementAge, contribution }) {
  const state = useProjectionSimulation(input)
  return <div><ProjectionPanel
    state={state}
    source={source}
    money={money}
    startAge={currentAge}
    retirementAge={retirementAge}
    title="Long-range outcome distribution"
    assumptionNote={`${money(contribution)} of annual funding is added in monthly installments.`}
  /><Link className="primary-button planning-home-link" to="/planning">Open Planning</Link></div>
}

export default function Dashboard() {
  const { data, loading, reload: reloadReport } = useData('report.json')
  // Start the larger Market Pulse payload on the landing report so /market is warm when it
  // is opened, while keeping it out of the report's blocking loading condition below.
  const { data: advisorData, loading: advisorLoading, reload: reloadAdvisor } = useData('advisor.json')
  const { data: etfData, loading: etfLoading, reload: reloadEtfs } = useData('etfs.json')
  const { currentUser } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const tracking = usePortfolioTracking()
  // Quietly refreshes at 9pm local time (see src/lib/nightlyRefresh.js) so after-hours has
  // real Yahoo data by the time anyone looks at the report, not just when someone happens to
  // hit refresh on the Portfolio page.
  const portfolioQuotes = usePortfolioQuotes(positions.map((position) => position.ticker))
  const { preferences, setWidgets, updatePreferences } = usePreferences()
  const { data: benchmarkReport, loading: benchmarkLoading, reload: reloadBenchmarks } = useData(positions.length ? 'benchmark-report.json' : null)
  const [period, setPeriod] = useState(preferences.defaultChartPeriod)
  const [chartMode, setChartMode] = useState(null)
  const [draftWidgets, setDraftWidgets] = useState(preferences.widgets)
  const [pullRefreshing, setPullRefreshing] = useState(false)
  const customize = new window.URLSearchParams(window.location.search).get('customize') === '1'
  const watchlist = useMemo(() => { try { return JSON.parse(localStorage.getItem(WATCH_KEY)) || [] } catch { return [] } }, [])

  const reloadHomeData = useCallback(async () => {
    const [latestReport] = await Promise.all([reloadReport(), reloadAdvisor(), reloadEtfs(), reloadBenchmarks()])
    return latestReport
  }, [reloadAdvisor, reloadBenchmarks, reloadEtfs, reloadReport])
  const universeRefresh = useAdvisorRefresh(
    data?.generated_at,
    reloadHomeData,
    [...positions.map((position) => position.ticker), ...watchlist],
  )

  const refreshReport = useCallback(async () => {
    setPullRefreshing(true)
    try {
      await reloadHomeData()
      await portfolioQuotes.requestRefresh()
    } finally { setPullRefreshing(false) }
  }, [portfolioQuotes, reloadHomeData])
  const pullToRefresh = usePullToRefresh({ onRefresh: refreshReport, refreshing: pullRefreshing })

  if (loading || (currentUser && (portfolioLoading || (positions.length > 0 && benchmarkLoading)))) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const prices = buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows)
  const portfolio = enrichPortfolio(positions, prices)
  const holdingsSeries = currentHoldingsSeries(positions, prices, data.benchmark_history?.dates || [])
  const recordedSeries = actualRecordedValueSeries(tracking.snapshots, tracking.activities)
  const chartSelection = selectPortfolioHistorySeries(holdingsSeries, recordedSeries, chartMode)
  const effectiveChartMode = chartSelection.mode
  const selected = selectPeriod(chartSelection.series, period)
  const selectedBenchmarkSymbols = preferences.defaultBenchmarks || [preferences.defaultBenchmark]
  const selectedBenchmarkSeries = selectedBenchmarkSymbols.map((symbol) => {
    const history = benchmarkReport?.histories?.[symbol]
    const definition = BENCHMARKS.find((item) => item.symbol === symbol)
    return history ? { symbol, label: definition?.label || symbol, dates: history.dates, closes: history.closes } : null
  }).filter(Boolean)
  const comparison = effectiveChartMode === 'backtest' ? compareBenchmarkSeries(selected, selectedBenchmarkSeries) : null
  const chartedPortfolio = comparison?.portfolio || selected
  const today = latestMarketDayReturn(holdingsSeries)
  const afterHours = afterHoursPortfolioReturn(positions, portfolioQuotes.quotes)
  const diversification = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })
  const scorePortfolioPeriod = selectPeriod(holdingsSeries, '1Y') || selectPeriod(holdingsSeries, 'All')
  const scoreComparison = compareBenchmarkSeries(scorePortfolioPeriod, selectedBenchmarkSeries.slice(0, 1))
  const resilience = resilienceIndex(scoreComparison?.portfolio.values || scorePortfolioPeriod?.values || [], diversification)
  const riskFree = riskFreeAnnualRate(advisorData)
  const performance = performanceMetrics(scoreComparison?.portfolio, scoreComparison?.benchmarks[0], riskFree.annualPct)
  const concentrationLiquidity = concentrationLiquidityScore(portfolio.positions)
  const overall = portfolioScore({ diversification, resilience, performance, benchmarkEfficiency: null, concentrationLiquidity, dataCompleteness: Math.round(portfolio.coveragePct || 0) })
  const leader = rows[0]
  const watchRows = watchlist.map((ticker) => rows.find((row) => row.ticker === ticker)).filter(Boolean).slice(0, 4)
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  const tone = (value) => value == null ? '' : value >= 0 ? 'positive' : 'negative'
  const forecast = preferences.forecast
  const latestTrackingDate = tracking.snapshots.at(-1)?.marketDate
  const intraday = intradayPortfolioHigh(tracking.snapshots.filter((snapshot) => snapshot.marketDate === latestTrackingDate))
  const allTimeEarnings = trackedAllTimeEarnings(portfolio, tracking.activities, tracking.trackingState)
  const actionable = portfolio.positions.map((row) => ({ ...row, recommendation: row.priceInfo ? getRecommendation(row.priceInfo) : null })).filter((row) => row.recommendation && row.recommendation.action !== 'HOLD')
  const sectorAllocation = Object.entries(portfolio.positions.reduce((totals, position) => {
    const sector = position.priceInfo?.sector || 'Unclassified'
    totals[sector] = (totals[sector] || 0) + Number(position.currentValue || 0)
    return totals
  }, {})).map(([sector, value]) => ({ sector, value, pct: portfolio.totalValue ? value / portfolio.totalValue * 100 : 0 }))
    .sort((left, right) => right.value - left.value)

  const uninvestedCash = tracking.trackingState?.cashTrackingEnabled ? Number(tracking.trackingState.cashBalance || 0) : 0
  const trackedAccountValue = portfolio.totalValue + uninvestedCash
  const cashHistoryComplete = tracking.trackingState?.cashFlowHistoryComplete
  const returnSummary = portfolioReturnSummary(tracking.snapshots, tracking.activities, cashHistoryComplete)
  const planningReportDate = today?.date || null
  const contributionPace = trailingCashFlowPace(tracking.activities, planningReportDate, cashHistoryComplete)
  const projectedAnnualContribution = contributionPace.available ? contributionPace.netContributions : forecast.recurringAnnual
  const primaryBenchmarkHistory = benchmarkReport?.histories?.[preferences.defaultBenchmark]
    ? { dates: benchmarkReport.histories[preferences.defaultBenchmark].dates, closes: benchmarkReport.histories[preferences.defaultBenchmark].closes, symbol: preferences.defaultBenchmark }
    : null
  const projectionSource = selectProjectionReturnSource(holdingsSeries, primaryBenchmarkHistory, preferences.defaultBenchmark)
  const projectionInput = projectionSource.available ? {
    monthlyReturns: projectionSource.returns,
    currentBalance: trackedAccountValue,
    monthlyContribution: projectedAnnualContribution / projectionConfig.months_per_year,
    accumulationMonths: Math.max(1, (forecast.retirementAge - forecast.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: 0,
    inflationPct: projectionConfig.default_inflation_pct,
  } : null
  const beatStreak = primaryBenchmarkHistory ? beatMarketStreak(tracking.snapshots, primaryBenchmarkHistory) : { available: false }
  const greenStreak = valueStreak(tracking.snapshots)
  const mood = portfolioMood({ returnPct: returnSummary.strategy.returnPct, diversificationScore: diversification.score, streak: beatStreak.available ? beatStreak : greenStreak })
  const screenRows = [...new Map([...rows, ...(data.screen_universe || [])].map((row) => [row.ticker, row])).values()]
  const focusedScreens = [
    { title: 'Value near 52-week lows', kicker: 'Value turnarounds', note: 'Quality plus a positive latest week', rows: rankValueTurnarounds(screenRows, 3), metric: (row) => ({ label: 'Above low', value: row.screen.aboveLow }), to: '/screens/quality-value' },
    { title: 'Recent momentum', kicker: 'Momentum', note: 'Positive week and month', rows: rankMomentum(screenRows, 3), metric: (row) => ({ label: '20 days', value: row.screen.monthReturn }), to: '/screens/momentum' },
    { title: 'Short-term reversals', kicker: 'Reversal', note: '20-day pullback turning up', rows: rankReversal(screenRows, 3), metric: (row) => ({ label: 'This week', value: row.screen.weekReturn }), to: '/screens/matrix' },
    { title: 'Top ETFs', kicker: 'Fund screens', note: 'Performance, risk, cost and liquidity', rows: rankGrowingEtfs(etfData?.etfs || [], 3), metric: (row) => ({ label: '1 year', value: row.returns?.['1y'] }), loading: etfLoading, to: '/research' },
  ]

  const toggleBenchmark = (symbol) => {
    const next = selectedBenchmarkSymbols.includes(symbol)
      ? selectedBenchmarkSymbols.filter((item) => item !== symbol)
      : [...selectedBenchmarkSymbols, symbol].slice(0, 3)
    if (!next.length) return
    updatePreferences({ defaultBenchmarks: next, defaultBenchmark: next[0] })
  }

  const saveCustomization = () => { setWidgets(draftWidgets); window.history.replaceState({}, '', '/'); window.location.reload() }

  return <div className="financial-report-page">
    <PullToRefreshIndicator pullDistance={pullToRefresh.pullDistance} armed={pullToRefresh.armed} refreshing={pullRefreshing} />
    {customize && <Customizer widgets={draftWidgets} onChange={setDraftWidgets} onDone={saveCustomization} />}
    <header className="page-head report-head">
      <div><span className="eyebrow">Latest close · {String(data.generated_at).slice(0, 10)}</span><h1 className="page-title">Financial Report</h1><p className="page-sub">Your portfolio, explained with traceable daily-close data.</p></div>
      <div className="report-head-actions">
        {currentUser && <button type="button" className="secondary-button home-universe-refresh" onClick={universeRefresh.requestFullRefresh} disabled={universeRefresh.refreshing}
          title="Rebuild research for the complete covered universe">
          <Icon name="sync" size={17} className={universeRefresh.refreshing ? 'refresh-spin' : ''} />
          {universeRefresh.refreshing ? 'Refreshing full universe…' : 'Refresh full universe'}
        </button>}
        <button className="icon-button desktop-only" onClick={() => updatePreferences({ privacyMode: !preferences.privacyMode })} aria-label={preferences.privacyMode ? 'Show balances' : 'Hide balances'}><Icon name={preferences.privacyMode ? 'eye-off' : 'eye'} /></button>
      </div>
    </header>
    {(universeRefresh.refreshing || universeRefresh.message) && <div className="home-refresh-feedback">
      <RefreshProgress active={universeRefresh.refreshing} elapsedLabel={universeRefresh.elapsedLabel}
        percent={universeRefresh.progress} stage={universeRefresh.stage} />
      {universeRefresh.message && <div className={`sync-message refresh-message ${universeRefresh.status}`} role="status" aria-live="polite">{universeRefresh.message}</div>}
    </div>}

    {!currentUser || !positions.length ? <section className="report-empty-state"><span className="eyebrow">Portfolio report</span><h2>{currentUser ? 'Add holdings to unlock your report' : 'Sign in to see your financial report'}</h2><p>Research remains available now. Portfolio analytics appear only after holdings and per-share cost basis are available.</p><Link className="primary-button" to={currentUser ? '/portfolio' : '/research'}>{currentUser ? 'Add holdings' : 'Explore research'}</Link></section> : <>
      <div className="dashboard-widget-stack">
      <DashboardWidget id="portfolio-summary" widgets={preferences.widgets}>
      <section className="report-hero-grid">
        <article className="report-hero">
          <span>Current portfolio value</span>
          <strong>{money(portfolio.totalValue)}</strong>
          <div className="report-hero-pills">
            <DirectionPill value={today?.dollarReturn}>{today ? `${money(Math.abs(today.dollarReturn))} · ${signedPct(today.returnPct, 2)} today` : 'Today — unavailable'}</DirectionPill>
            <DirectionPill value={afterHours.available ? afterHours.dollarReturn : null}>{afterHours.available
              ? `${money(Math.abs(afterHours.dollarReturn))}${afterHours.returnPct != null ? ` · ${signedPct(afterHours.returnPct, 2)}` : ''} after-hours`
              : 'After-hours — refreshes at 9pm'}</DirectionPill>
          </div>
          <button type="button" className="secondary-button compact after-hours-refresh" onClick={portfolioQuotes.requestRefresh} disabled={portfolioQuotes.refreshing}
            aria-label="Refresh after-hours quotes from Yahoo for portfolio holdings"
            title="Ask Yahoo only for the symbols currently held in this portfolio">
            <Icon name="sync" size={16} className={portfolioQuotes.refreshing ? 'refresh-spin' : ''} />
            {portfolioQuotes.refreshing ? 'Checking Yahoo…' : 'Refresh after-hours'}
          </button>
          {(portfolioQuotes.message || portfolioQuotes.error) && <span className={`after-hours-message ${portfolioQuotes.error ? 'negative' : 'positive'}`} role="status" aria-live="polite">{portfolioQuotes.error || portfolioQuotes.message}</span>}
          <small>{portfolio.positions.length} holdings · {Math.round(portfolio.coveragePct)}% price coverage</small>
        </article>
        <Metric label="Today’s return" value={today ? `${today.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(today.dollarReturn))}` : '—'} note={`${signedPct(today?.returnPct)} close-to-close through ${today?.date || 'unavailable'}`} tone={tone(today?.dollarReturn)} />
        <Metric label="Total unrealized return" value={portfolio.gain == null ? '—' : `${portfolio.gain >= 0 ? '+' : '−'}${money(Math.abs(portfolio.gain))}`} note={`${signedPct(portfolio.gainPct)} versus entered per-share cost basis`} tone={tone(portfolio.gain)} />
        <Metric label="Invested cost basis" value={money(portfolio.totalCost)} note="Shares × entered per-share cost; not net contributed capital" />
      </section>

      <PortfolioReturnSummary summary={returnSummary} />

      <section className="card insights-recap dashboard-pulse" aria-labelledby="dashboard-pulse-title">
        <div className="insights-mood">
          <span className="insights-mood-emoji" aria-hidden="true">{mood.emoji}</span>
          <div>
            <h2 id="dashboard-pulse-title">{mood.label}</h2>
            <p>{mood.blurb}{mood.note ? ` ${mood.note}` : ''}</p>
          </div>
          <Link className="secondary-button compact" to="/portfolio/insights">Trader insights →</Link>
        </div>
        <div className="insights-recap-stats">
          <div><span>Today</span><b className={tone(today?.dollarReturn)}>{today ? `${signedPct(today.returnPct, 2)} · ${money(Math.abs(today.dollarReturn))}` : '—'}</b></div>
          <div><span>Strategy return</span><b className={tone(returnSummary.strategy.returnPct)}>{returnSummary.strategy.available ? signedPct(returnSummary.strategy.returnPct, 1) : 'Unavailable'}</b></div>
          {beatStreak.available && beatStreak.days >= 1 && <div><span>{beatStreak.beating ? `Beating ${preferences.defaultBenchmark}` : `Trailing ${preferences.defaultBenchmark}`}</span><b>{beatStreak.days} day{beatStreak.days === 1 ? '' : 's'} running</b></div>}
        </div>
      </section>
      </DashboardWidget>

      <DashboardWidget id="performance-chart" widgets={preferences.widgets}>
      <section className="report-chart-card">
        <header className="section-heading"><div><span className="eyebrow">Performance</span><h2>{PORTFOLIO_HISTORY_LABELS[effectiveChartMode]}</h2></div><div className="chart-controls"><div className="period-control" aria-label="Portfolio series"><button className={effectiveChartMode === 'backtest' ? 'active' : ''} aria-pressed={effectiveChartMode === 'backtest'} onClick={() => setChartMode('backtest')}>Backtested basket</button><button className={effectiveChartMode === 'actual' ? 'active' : ''} aria-pressed={effectiveChartMode === 'actual'} disabled={!recordedSeries} onClick={() => setChartMode('actual')}>Recorded value</button></div><div className="period-control" aria-label="Performance period">{PERIODS.map((item) => <button key={item} className={period === item ? 'active' : ''} aria-pressed={period === item} onClick={() => { setPeriod(item); updatePreferences({ defaultChartPeriod: item }) }}>{item}</button>)}</div></div></header>
        <ResponsiveControlPanel label={`Benchmarks: ${selectedBenchmarkSymbols.join(', ')}`} title="Choose benchmarks"><fieldset className="benchmark-picker" aria-label="Comparison benchmarks"><legend>Compare with up to three ETF proxies</legend><div>{BENCHMARKS.map((item) => { const checked = selectedBenchmarkSymbols.includes(item.symbol); return <label key={item.symbol} className={checked ? 'selected' : ''}><input type="checkbox" checked={checked} disabled={!checked && selectedBenchmarkSymbols.length >= 3} onChange={() => toggleBenchmark(item.symbol)} /><span>{item.symbol}</span></label> })}</div></fieldset></ResponsiveControlPanel>
        {chartedPortfolio ? <GrowthChart dates={comparison?.dates || chartedPortfolio.dates} series={[{ label: PORTFOLIO_HISTORY_LABELS[effectiveChartMode], values: chartedPortfolio.values, color: 'var(--series-stock)', emphasis: true }, ...(comparison?.benchmarks || []).map((item, index) => ({ label: `${item.symbol} proxy`, values: item.values, ...BENCHMARK_STYLES[index] }))]} valueFormatter={money} caption={`${chartSelection.note} ${effectiveChartMode === 'actual' ? recordedSeries.methodology : `${comparison?.methodology || selected.methodology} This applies today's share quantities to past closes and is not reconstructed account history.`}`} /> : <div className="unavailable-panel"><strong>{period} history unavailable</strong><p>This series does not contain two usable observations for the selected period.</p></div>}
        {comparison?.benchmarks?.length > 0 && <div className="benchmark-result-strip" aria-label="Benchmark return comparison">{comparison.benchmarks.map((item) => <div key={item.symbol}><span>{item.symbol}<small>{item.label}</small></span><strong>{signedPct(item.returnPct)}</strong><em className={tone(item.differenceVsPortfolio)}>{item.differenceVsPortfolio >= 0 ? '+' : '−'}{money(Math.abs(item.differenceVsPortfolio))} vs portfolio</em></div>)}</div>}
        <div className="report-chart-summary"><Metric label={effectiveChartMode === 'actual' ? 'Recorded value change' : 'Backtested basket change'} value={chartedPortfolio ? `${chartedPortfolio.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(chartedPortfolio.dollarReturn))}` : 'Unavailable'} note={chartedPortfolio ? `${signedPct(chartedPortfolio.returnPct)} · ${chartedPortfolio.startDate} to ${chartedPortfolio.endDate}` : 'Unavailable'} tone={tone(chartedPortfolio?.dollarReturn)} /><Metric label="Charted portfolio high" value={chartedPortfolio ? money(chartedPortfolio.high) : 'Unavailable'} note="Highest value in the selected chart series" /><Metric label="Observed intraday high" value={intraday ? money(intraday.value) : 'Tracking'} note={intraday ? `${intraday.observations} stored observation${intraday.observations === 1 ? '' : 's'} on ${latestTrackingDate}` : 'Stored after signed-in portfolio price refreshes'} /><Metric label="All-time earnings" value={allTimeEarnings.available ? money(allTimeEarnings.value) : 'Tracking'} note={allTimeEarnings.reason} tone={tone(allTimeEarnings.value)} /></div>
      </section>
      </DashboardWidget>

      <DashboardWidget id="metric-grid" widgets={preferences.widgets}>
      <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Portfolio scores</span><h2>Decision-quality snapshot</h2></div><Link to="/portfolio/diversification">View diversification →</Link></header><div className="report-score-grid"><ScoreCard label="Portfolio score" result={overall} note={`${overall.reason} ${overall.available ? `${overall.strongest} is strongest. ${overall.weakest} has the most room to improve.` : ''}`} /><ScoreCard label="Diversification" result={diversification} note={`${diversification.warnings.length ? diversification.warnings[0] : 'No major concentration warning in covered holdings.'}`} /><ScoreCard label="Resilience" result={resilience} note={resilience.available ? `${Math.abs(resilience.maxDrawdown).toFixed(1)}% maximum drawdown and ${resilience.volatility.toFixed(1)}% annualized volatility.` : ''} /></div>{overall.available && <details className="score-method"><summary>How the portfolio score is built</summary><div>{Object.entries(overall.components).map(([label, value]) => <span key={label}><b>{label.replace(/([A-Z])/g, ' $1')}</b><em>{value == null ? 'Unavailable' : `${Math.round(value)}/100`}</em></span>)}</div><p>The portfolio score remains provisional whenever a component is missing. Standard performance statistics are reported separately and are not converted into a grade.</p></details>}</section>

      <PerformanceMetrics metrics={performance} benchmarkLabel={preferences.defaultBenchmark} riskFree={riskFree} />
      </DashboardWidget>

      <DashboardWidget id="allocation" widgets={preferences.widgets}>
        <section className="report-section sector-allocation-widget"><header className="section-heading"><div><span className="eyebrow">Allocation</span><h2>Sector allocation</h2></div><Link to="/portfolio/diversification">Full analysis →</Link></header><div>{sectorAllocation.map((item) => <article key={item.sector}><div><strong>{item.sector}</strong><span>{item.pct.toFixed(1)}%</span></div><i aria-hidden="true"><span style={{ width: `${item.pct}%` }} /></i><small>{money(item.value)}</small></article>)}</div></section>
      </DashboardWidget>

      <DashboardWidget id="top-signal" widgets={preferences.widgets}>
        <article className="signal-preview"><header><div><span className="eyebrow">Top signal</span><h2>Research leader</h2></div><Tier label={leader.stance} /></header><div className="signal-company"><CompanyLogo company={leader} size={48} /><div><strong>{leader.ticker}</strong><span>{leader.name}</span></div><b>{leader.score}/100</b></div><p>{leader.strengths?.[0] || 'Highest-scoring published company in the latest evidence run.'}</p><Link to="/research">Open research →</Link></article>
      </DashboardWidget>

      <DashboardWidget id="action-needed" widgets={preferences.widgets}>
        <article className="action-preview"><header><div><span className="eyebrow">Actions</span><h2>Holdings to review</h2></div><Link to="/portfolio">Open portfolio</Link></header><strong>{actionable.length}</strong><p>{actionable.length ? `${actionable.slice(0, 4).map((row) => row.ticker).join(', ')} have evidence-based guidance beyond Hold.` : 'No covered holding has multi-factor guidance beyond Hold.'}</p><small>Research prompts only. Review the underlying evidence before acting.</small></article>
      </DashboardWidget>

      <DashboardWidget id="watchlist-preview" widgets={preferences.widgets}>
        <article className="watchlist-preview"><header><div><span className="eyebrow">Watchlist</span><h2>Names you follow</h2></div><Link to="/watchlist">View all</Link></header>{watchRows.length ? watchRows.map((row) => <div className="watch-preview-row" key={row.ticker}><CompanyLogo company={row} size={32} /><div><strong>{row.ticker}</strong><span>{row.name}</span></div><b>{row.score}</b></div>) : <p>No published watchlist matches yet.</p>}</article>
      </DashboardWidget>
      </div>

      <section className="report-two-column">
        <ReportProjection input={projectionInput} source={projectionSource} money={money} currentAge={forecast.currentAge} retirementAge={forecast.retirementAge} contribution={projectedAnnualContribution} />
        <article className="opportunity-card"><span className="eyebrow">Opportunity cost</span><h2>Potential earnings by benchmark</h2>{comparison ? <><div className="opportunity-baseline"><span>Shared starting value</span><strong>{money(comparison.startingValue)}</strong><small>{comparison.startDate} to {comparison.endDate}</small></div><div className="opportunity-list"><div className="portfolio-opportunity-row"><span>Current holdings<small>Charted potential earnings</small></span><strong>{chartedPortfolio.dollarReturn >= 0 ? '+' : '−'}{money(Math.abs(chartedPortfolio.dollarReturn))}</strong></div>{comparison.benchmarks.map((item) => <div key={item.symbol}><span>{item.symbol} proxy<small>{item.label} potential earnings</small></span><strong>{item.potentialEarnings >= 0 ? '+' : '−'}{money(Math.abs(item.potentialEarnings))}</strong><em className={tone(item.differenceVsPortfolio)}>{item.differenceVsPortfolio >= 0 ? `Portfolio ahead ${money(item.differenceVsPortfolio)}` : `Benchmark ahead ${money(Math.abs(item.differenceVsPortfolio))}`}</em></div>)}</div><small>{comparison.methodology}</small></> : <p>Comparable history is unavailable for this selection.</p>}</article>
      </section>
    </>}

    <MarketPulsePreview data={advisorData} loading={advisorLoading} />

    <section className="report-focused-screens" aria-labelledby="focused-screens-title">
      <header className="section-heading"><div><span className="eyebrow">Focused breakdown</span><h2 id="focused-screens-title">Value, momentum, reversals, and ETFs</h2></div><Link to="/research">All research →</Link></header>
      <div className="report-screen-grid">{focusedScreens.map((screen) => <FocusedScreenCard key={screen.kicker} {...screen} />)}</div>
      <p className="screen-disclaimer">Research screens, not trade instructions. Confirm current prices, liquidity, news, and your own risk limits before acting.</p>
    </section>

    <footer className="report-methodology-note">Balances use the latest stored closes. Historical portfolio lines apply current quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes, fees, or dividends. General research only.</footer>
  </div>
}
