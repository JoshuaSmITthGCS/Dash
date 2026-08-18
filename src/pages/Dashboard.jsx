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
  annualizeReturnPct, BENCHMARKS, compareBenchmarkSeries, concentrationLiquidityScore, currentHoldingsSeries, diversificationScore,
  enrichPortfolio, latestMarketDayReturn, performanceMetrics, portfolioScore,
  resilienceIndex, riskFreeAnnualRate, selectPeriod, sliceSeriesFrom,
} from '../lib/portfolioAnalytics.js'
import { Loading, Empty, Move, RefreshProgress, Tier } from '../components/Bits.jsx'
import GrowthChart from '../components/GrowthChart.jsx'
import DotPlot from '../components/DotPlot.jsx'
import InfoTag from '../components/InfoTag.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'
import { getRecommendation } from '../lib/recommendation.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes.js'
import { liveTodayPortfolioReturn } from '../lib/afterHoursQuotes.js'
import { rankBreakoutInProgress, rankBuyingTheDip, rankGrowingEtfs, rankMomentum, rankReversal, rankValueTurnarounds } from '../lib/researchScreens.js'
import BuyingTheDipChart from '../components/BuyingTheDipChart.jsx'
import {
  currentHoldingsPerformanceSeriesForPeriod,
} from '../lib/portfolioPerformance.js'
import { PerformanceEvidenceSummary } from '../components/PerformanceMetrics.jsx'
import LiveTrackingCountdown from '../components/LiveTrackingCountdown.jsx'
import ProjectionPanel from '../components/ProjectionPanel.jsx'
import { applyAllocationAssumption, formatAnnualReturnTarget, normalizeAnnualReturnTarget, projectionConfig, selectProjectionReturnSource } from '../lib/projectionEngine.js'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'
import { usePullToRefresh } from '../lib/usePullToRefresh.js'
import PullToRefreshIndicator from '../components/PullToRefreshIndicator.jsx'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh.js'
import { fidelityProjectionBaseline } from '../lib/referenceCashFlows.js'
import modelSettings from '../../pipeline/config/settings.json'
import { LIVE_TRACKING_START } from '../lib/liveTrackingAvailability.js'
import AllocationDonut from '../components/AllocationDonut.jsx'
import ScoreGauge from '../components/ScoreGauge.jsx'
import MarketHeatmap from '../components/MarketHeatmap.jsx'
import Sparkline from '../components/Sparkline.jsx'
import { dailyMoveForPosition, marketType, rankDailySectors, rankDailyStocks } from '../lib/marketPresentation.js'

const PERIODS = ['1H', '1D', '1W', '1M', '3M', '1Y']
const PERIOD_LABELS = { '1H': 'Last hour', '1D': 'Today', '1W': 'Week', '1M': 'Month', '3M': '3 months', '1Y': 'Year' }
const interfaceConfig = modelSettings.interface

function ScoreCard({ label, result, note }) {
  return <article className="report-score-card"><ScoreGauge score={result?.score || 0} available={result?.available} label={label} provisional={result?.provisional} reason={result?.reason} /><div><h3>{label}</h3><p>{result?.available ? note : result?.reason || 'Not enough portfolio data yet.'}</p></div></article>
}

// The single market read on this page. It absorbed the old `MarketSentimentStrip`,
// which restated macro regime and top mover 6,000px further down; the only fields
// unique to that strip were the research leader (here) and the universe size (now
// in the page-head eyebrow, where dataset metadata belongs).
function HomeMarketSummary({ rows, macro, researchLeader }) {
  const ranked = rankDailyStocks(rows)
  const sectors = rankDailySectors(rows)
  const session = marketType(rows)
  const leader = ranked[0]
  return <section className="home-market-summary" aria-label="Market summary">
    <div className={`home-market-type ${session.tone}`}><span aria-hidden="true" /><div><small>Today’s market</small><strong>{session.label}</strong></div></div>
    <div><small>Market breadth</small><strong>{session.breadthPct == null ? 'Pending' : `${session.breadthPct.toFixed(0)}% advancing`}</strong></div>
    <div><small>Hottest sector</small><strong title={sectors[0]?.sector || undefined}>{sectors[0]?.sector || 'Pending'}{sectors[0] && ` · ${signedPct(sectors[0].averagePct)}`}</strong></div>
    <div><small>Biggest mover</small><strong>{leader ? `${leader.ticker} · ${signedPct(leader.dailyMove.pct)}` : 'Pending'}</strong></div>
    <div><small>Research leader</small><strong>{researchLeader ? `${researchLeader.ticker} · ${researchLeader.score}` : 'Pending'}</strong></div>
    <div><small>Macro backdrop</small><strong>{macro?.regime?.label || 'Pending'}</strong></div>
    <Link to="/markets">Open Markets <Icon name="arrow" size={15} /></Link>
  </section>
}

function HomePortfolioPanel({
  positions,
  chart,
  chartLabel,
  period,
  onPeriodChange,
  money,
  totalValue,
  totalProfit,
  today,
  fetchedAt,
}) {
  const [holdingsSort, setHoldingsSort] = useState('day')
  const resolutionNote = chart?.frequency === 'five-minute'
    ? `Every five-minute interval is shown for ${period === '1H' ? 'the last hour' : period === '1W' ? 'the trailing week' : 'the latest trading day'}.`
    : chart?.frequency === 'hourly-close'
      ? 'Hourly closes keep the current-holdings monthly path responsive.'
      : chart?.frequency === 'daily-close'
        ? 'Daily closes show the current-holdings three-month path.'
      : chart?.frequency === 'weekly-close'
          ? 'Weekly closes show the current-holdings yearly path.'
          : period === '1D'
            ? 'Five-minute cloud history is still accumulating; the latest historical fallback is shown.'
            : 'Historical values use saved closes until enough cloud snapshots accumulate.'
  const ranked = positions.map((position) => ({ ...position, move: dailyMoveForPosition(position) }))
    .sort((left, right) => holdingsSort === 'allocation'
      ? (right.allocationPct ?? -Infinity) - (left.allocationPct ?? -Infinity)
      : (right.move.pct ?? -Infinity) - (left.move.pct ?? -Infinity))
    .slice(0, 5)

  return <section className="home-primary-grid" aria-label="Portfolio performance and leading holdings">
    <article className="home-performance-card">
      <header className="home-performance-head">
        <label><span>Portfolio performance</span><select value={period} onChange={(event) => onPeriodChange(event.target.value)}>{PERIODS.map((item) => <option key={item} value={item}>{PERIOD_LABELS[item]}</option>)}</select></label>
        <div className="home-performance-kpis">
          <span><small>Invested value</small><strong>{money(totalValue)}</strong></span>
          <span><small>Today · regular session</small><strong className={today?.dollarReturn >= 0 ? 'positive' : 'negative'}>{today ? `${today.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(today.dollarReturn))} · ${signedPct(today.returnPct, 2)}` : 'Unavailable'}</strong></span>
          <span><small>Total profit · {PERIOD_LABELS[period]}</small><strong className={totalProfit >= 0 ? 'positive' : 'negative'}>{totalProfit == null ? 'Unavailable' : `${totalProfit >= 0 ? '+' : '−'}${money(Math.abs(totalProfit))}`}</strong></span>
        </div>
      </header>
      {chart ? <GrowthChart className="home-primary-chart" height={360} width={920} dates={chart.dates} series={[{ label: chartLabel, values: chart.values, color: 'var(--series-stock)', emphasis: true }]} valueFormatter={money} caption={chart.methodology} lineStyle="line" /> : <div className="unavailable-panel"><strong>{period} history is still building</strong><p>Two saved portfolio observations are needed to draw this range.</p></div>}
      <footer><span><i aria-hidden="true" />{chartLabel}</span><small>{resolutionNote}{fetchedAt ? ` Last quote ${new Date(fetchedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}.` : ''}</small></footer>
    </article>

    <aside className="home-top-holdings">
      <header><div><span className="eyebrow">Your portfolio</span><h2>Top 5 holdings</h2></div><label><span className="sr-only">Rank holdings by</span><select value={holdingsSort} onChange={(event) => setHoldingsSort(event.target.value)}><option value="day">Today’s performance</option><option value="allocation">Biggest allocation</option></select></label></header>
      <div>{ranked.map((position, index) => <article key={position.id || position.ticker} className={position.move.pct == null ? 'neutral' : position.move.pct >= 0 ? 'positive' : 'negative'}>
        <span className="holding-rank">{index + 1}</span><CompanyLogo company={position.priceInfo || position} size={36} /><span className="top-holding-name"><strong>{position.ticker}</strong><small>{position.allocationPct == null ? 'Allocation pending' : `${position.allocationPct.toFixed(1)}% allocation`}</small></span><span className="top-holding-move"><strong>{signedPct(position.move.pct, 2)}</strong><small>{position.move.positionDelta == null ? 'Day delta pending' : `${position.move.positionDelta >= 0 ? '+' : '−'}${money(Math.abs(position.move.positionDelta))}`}</small></span>
      </article>)}</div>
      <Link to="/portfolio">View all holdings <Icon name="arrow" size={15} /></Link>
    </aside>
  </section>
}

function DashboardWidget({ id, widgets, children }) {
  const widget = widgets.find((item) => item.id === id)
  if (!widget?.visible) return null
  // The reading order is published as a custom property rather than as `order`
  // directly, so a media query can reorder widgets for mobile with an ordinary
  // rule. Setting `order` inline meant the mobile override needed !important.
  return (
    <div className={`dashboard-widget dashboard-widget-${id}`} style={{ '--widget-order': widget.order }}>
      {children}
    </div>
  )
}

// Congress + institutional 13F, merged and pre-filtered to notable rows by
// build_inside_information_screen.py - unlike the other cards on this grid, there is no
// percentage metric to show (a CLUSTER_ACCUMULATION flag isn't a return), so this renders
// which flag(s) fired instead of a Move pct.
function InsideInformationCard({ rows, loading, style }) {
  const flagSummary = (row) => [
    row.institutional_flag === 'CLUSTER_ACCUMULATION' && 'Managers accumulating',
    row.institutional_flag === 'CLUSTER_DISTRIBUTION' && 'Managers distributing',
    row.congress_flags?.length ? 'Congressional cluster' : null,
  ].filter(Boolean).join(' · ') || 'Notable disclosed activity'
  return <article className="report-screen-card" style={style}>
    <header><div><span>Inside information</span><h3>Congress + institutional 13F</h3></div><small>Rare or flagged activity only</small></header>
    <div className="report-screen-list">
      {loading ? <div className="report-inline-loading" role="status">Loading this screen on the Report…</div>
        : rows.length ? rows.map((row, index) => (
          <div key={row.ticker}><CompanyLogo company={row} size={28} /><span className="screen-rank">#{index + 1}</span><span className="screen-company"><b>{row.ticker}</b><small>{flagSummary(row)}</small></span></div>
        ))
          : <div className="report-inline-loading">No notable disclosed activity right now.</div>}
    </div>
    <Link className="report-screen-link" to="/screens/inside-information">Open full screen <Icon name="arrow" size={16} /></Link>
  </article>
}

function FocusedScreenCard({ title, kicker, note, rows, metric, loading, to, style }) {
  return <article className="report-screen-card" style={style}>
    <header><div><span>{kicker}</span><h3>{title}</h3></div><small>{note}</small></header>
    <div className="report-screen-list">
      {loading ? <div className="report-inline-loading" role="status">Loading this screen on the Report…</div>
        : rows.length ? rows.map((row, index) => {
          const detail = metric(row)
          return <div key={row.ticker}><CompanyLogo company={row} size={28} /><span className="screen-rank">#{index + 1}</span><span className="screen-company"><b>{row.ticker}</b><small>{row.name}</small></span><span className="report-screen-metric"><small>{detail.label}</small><Move pct={detail.value} /></span></div>
        })
          : <div className="report-inline-loading">No name clears this screen in the latest report.</div>}
    </div>
    <Link className="report-screen-link" to={to}>Open full screen <Icon name="arrow" size={16} /></Link>
  </article>
}

const MACRO_FACTOR_LABELS = [['rates', 'Rates'], ['inflation', 'Inflation'], ['labor', 'Labor']]

function MarketPulsePreview({ data, loading }) {
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
  // A series with no published value gets a muted tile rather than a full-size dash:
  // an empty reading should not carry the same visual weight as a real one.
  return <section className="report-section report-market-pulse" aria-labelledby="report-market-pulse-title">
    <header className="section-heading"><div><span className="eyebrow">Market pulse</span><h2 id="report-market-pulse-title">The current backdrop</h2></div><Link to="/market">News and context →</Link></header>
    {loading && !data ? <div className="report-inline-loading" role="status">Loading Market Pulse here on the Report…</div> : <>
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

function Customizer({ widgets, onChange, onDone }) {
  const move = (index, direction) => {
    const target = index + direction
    if (target < 0 || target >= widgets.length) return
    const next = [...widgets]; [next[index], next[target]] = [next[target], next[index]]
    onChange(next.map((widget, order) => ({ ...widget, order })))
  }
  return <aside className="customizer-panel"><div className="customizer-head"><div><span className="eyebrow">Settings</span><h2>Customize report</h2></div><button className="icon-button" onClick={onDone} aria-label="Close customization"><Icon name="close" /></button></div><p>Choose supporting modules and their reading order. Core financial-report metrics always remain visible.</p><div className="customizer-list">{widgets.map((widget, index) => <div className="customizer-row" key={widget.id}><Icon name="grip" /><div><strong>{widget.label}</strong><small>{widget.locked ? 'Required' : `Position ${index + 1}`}</small></div><label className="switch compact-switch"><span className="sr-only">Show {widget.label}</span><input type="checkbox" checked={widget.visible} disabled={widget.locked} onChange={(event) => onChange(widgets.map((item) => item.id === widget.id ? { ...item, visible: event.target.checked } : item))} /><span /></label><div className="reorder-buttons"><button onClick={() => move(index, -1)} disabled={!index}><Icon name="up" /></button><button onClick={() => move(index, 1)} disabled={index === widgets.length - 1}><Icon name="down" /></button></div></div>)}</div><button className="primary-button" onClick={onDone}>Save report</button></aside>
}

function ReportProjection({ input, source, money, annualReturnTargetPct, currentAge, retirementAge, contribution, liveStrategyReturn }) {
  const state = useProjectionSimulation(input)
  return <div><ProjectionPanel
    state={state}
    source={source}
    money={money}
    annualReturnTargetPct={annualReturnTargetPct}
    startAge={currentAge}
    retirementAge={retirementAge}
    title="Long-range outcome distribution"
    assumptionNote={`${money(contribution)} of annual funding is added in monthly installments. The dotted median targets ${formatAnnualReturnTarget(annualReturnTargetPct)} annually${liveStrategyReturn ? ' -- your current-holdings return, annualized with cash transfers excluded' : ''}.`}
  /><Link className="primary-button planning-home-link" to="/planning">Open Planning</Link></div>
}

export default function Dashboard() {
  const { data, loading, reload: reloadReport } = useData('report.json')
  const { data: etfData, loading: etfLoading, reload: reloadEtfs } = useData('etfs.json')
  const { data: insideInformation, loading: insideInformationLoading } = useData('screens/inside-information.json')
  const { currentUser, authError, retryAuth } = useAuth()
  const { positions: storedPositions, loading: portfolioLoading } = useFirebasePortfolio()
  const previewPortfolio = import.meta.env.DEV
    && new window.URLSearchParams(window.location.search).get('portfolioPreview') === '1'
  const positions = previewPortfolio ? interfaceConfig.mobile_preview_positions : storedPositions
  const hasPortfolioAccess = currentUser || previewPortfolio
  const finances = useFirebaseFinances()
  const tracking = usePortfolioTracking()
  // One fetch on arrival keeps the visible holding cards current; the production scheduler's
  // five-minute cloud snapshots (not a browser timer) are what carry the day the rest of the
  // time. See usePortfolioQuotes.js.
  const portfolioQuotes = usePortfolioQuotes(positions.map((position) => position.ticker))
  const { preferences, setWidgets, updatePreferences } = usePreferences()
  const { data: benchmarkReport, loading: benchmarkLoading, reload: reloadBenchmarks } = useData(positions.length ? 'benchmark-report.json' : null)
  const [period, setPeriod] = useState('1D')
  const [draftWidgets, setDraftWidgets] = useState(preferences.widgets)
  const [pullRefreshing, setPullRefreshing] = useState(false)
  const [sinceLiveTrackingOnly, setSinceLiveTrackingOnly] = useState(true)
  const customize = new window.URLSearchParams(window.location.search).get('customize') === '1'
  const { items: watchlistItems } = useWatchlist()
  const watchlist = useMemo(() => watchlistItems.map((item) => item.ticker), [watchlistItems])

  const reloadHomeData = useCallback(async () => {
    const [latestReport] = await Promise.all([reloadReport(), reloadEtfs(), reloadBenchmarks()])
    return latestReport
  }, [reloadBenchmarks, reloadEtfs, reloadReport])
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

  if (loading || (hasPortfolioAccess && !previewPortfolio && (portfolioLoading || finances.loading || (positions.length > 0 && benchmarkLoading)))) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset is available yet." />

  const rows = data.research
  const publishedPrices = mergePositionSnapshots(
    buildPortfolioPriceData(data.screen_universe || [], data.portfolio_coverage || [], rows),
    positions,
    data.generated_at,
  )
  // A quote refresh older than the latest published report is stale relative to it (e.g. a
  // fresh nightly pipeline run) and must not override those newer closes on the hero number.
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
  const homeChart = recordedZoomSeries
    ? recordedZoomSeries
    : chartedPortfolio
  const homeChartLabel = 'Current holdings'
  const homePeriodProfit = homeChart?.dollarReturn
    ?? (homeChart?.values?.length > 1 ? homeChart.values.at(-1) - homeChart.values[0] : null)
  const today = latestMarketDayReturn(holdingsSeries)
  // Prefer each holding's current/session price versus its own previous close. The Fidelity
  // import supplies the same baseline before the first live quote refresh arrives.
  const liveToday = liveTodayPortfolioReturn(positions, prices)
  const heroToday = liveToday.available
    ? liveToday
    : today ? { dollarReturn: today.dollarReturn, returnPct: today.returnPct } : null
  const diversification = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })
  // Standard-measures/score inputs only -- kept separate from holdingsSeries (used above for
  // the performance chart) so this toggle affects risk/ratio stats without changing the chart.
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

  const trackedAccountValue = portfolio.totalValue
  const primaryBenchmarkHistory = benchmarkReport?.histories?.[preferences.defaultBenchmark]
    ? { dates: benchmarkReport.histories[preferences.defaultBenchmark].dates, closes: benchmarkReport.histories[preferences.defaultBenchmark].closes, symbol: preferences.defaultBenchmark }
    : null
  const projectionSource = selectProjectionReturnSource(
    holdingsSeries,
    primaryBenchmarkHistory,
    preferences.defaultBenchmark,
    fidelityProjectionBaseline(positions),
  )
  // The automatic planning assumption comes from the current basket's price history. Because
  // quantities are held constant across the series, transfers cannot affect this return.
  const currentHoldingsPeriod = selectPeriod(holdingsSeries, 'All')
  const liveStrategyAnnualReturnPct = currentHoldingsPeriod
    ? annualizeReturnPct(currentHoldingsPeriod.returnPct, currentHoldingsPeriod.startDate, currentHoldingsPeriod.endDate)
    : null
  const annualReturnTargetPct = normalizeAnnualReturnTarget(
    liveStrategyAnnualReturnPct ?? finances.settings.planningAnnualReturnTargetPct,
    projectionSource,
  )
  const planningReturns = projectionSource.available
    ? applyAllocationAssumption(
      projectionSource.returns,
      finances.settings.allocationAggressiveness || projectionConfig.allocation_default,
      annualReturnTargetPct / 100,
    )
    : []
  const projectionInput = projectionSource.available ? {
    monthlyReturns: planningReturns,
    currentBalance: finances.settings.currentSavings || trackedAccountValue,
    monthlyContribution: finances.settings.monthlyContribution,
    monthlyWithdrawal: finances.settings.monthlyWithdrawal,
    accumulationMonths: Math.max(1, (finances.settings.retireAge - finances.settings.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: Math.max(0, (finances.settings.retirementEndAge - finances.settings.retireAge) * projectionConfig.months_per_year),
    inflationPct: finances.settings.inflationPct,
  } : null
  const screenRows = [...new Map([...rows, ...(data.screen_universe || [])].map((row) => [row.ticker, row])).values()]
  const dipRows = rankBuyingTheDip(screenRows, 8)
  const focusedScreens = [
    { title: 'Fast growth breakouts', kicker: 'Fast growth', note: 'Sharp acceleration this week', rows: rankBreakoutInProgress(screenRows, 3), metric: (row) => ({ label: '5 days', value: row.screen.weekReturn }), to: '/screens/fast-growth' },
    { title: 'Value near 52-week lows', kicker: 'Value turnarounds', note: 'Quality plus a positive latest week', rows: rankValueTurnarounds(screenRows, 3), metric: (row) => ({ label: 'Above low', value: row.screen.aboveLow }), to: '/screens/quality-value' },
    { title: 'Recent momentum', kicker: 'Momentum', note: 'Positive week and month', rows: rankMomentum(screenRows, 3), metric: (row) => ({ label: '20 days', value: row.screen.monthReturn }), to: '/screens/momentum' },
    { title: 'Short-term reversals', kicker: 'Reversal', note: '20-day pullback turning up', rows: rankReversal(screenRows, 3), metric: (row) => ({ label: 'This week', value: row.screen.weekReturn }), to: '/screens/matrix' },
    { title: 'Top ETFs', kicker: 'Fund screens', note: 'Performance, risk, cost and liquidity', rows: rankGrowingEtfs(etfData?.etfs || [], 3), metric: (row) => ({ label: '1 year', value: row.returns?.['1y'] }), loading: etfLoading, to: '/research' },
    // Plus InsideInformationCard below, appended outside this array (its rows carry flags,
    // not a Move pct, so it doesn't fit the {title, rows, metric} shape the rest share).
    // Six cards total keeps `.report-screen-grid` a uniform 2-up layout - no card spans
    // full width the way the old odd-count "Top ETFs" card briefly did.
  ]

  const saveCustomization = () => { setWidgets(draftWidgets); window.history.replaceState({}, '', '/'); window.location.reload() }

  return <div className="financial-report-page">
    <PullToRefreshIndicator pullDistance={pullToRefresh.pullDistance} armed={pullToRefresh.armed} refreshing={pullRefreshing} settling={pullToRefresh.settling} />
    {customize && <Customizer widgets={draftWidgets} onChange={setDraftWidgets} onDone={saveCustomization} />}
    <header className="page-head report-head">
      <div><span className="eyebrow">Latest close · {String(data.generated_at).slice(0, 10)} · {rows.length} names covered</span><h1 className="page-title">Portfolio Overview</h1><p className="page-sub">Traceable daily-close analytics</p></div>
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

    <HomeMarketSummary rows={[...rows, ...(data.portfolio_coverage || [])]} macro={data?.market?.macro} researchLeader={leader} />

    {!hasPortfolioAccess || !positions.length ? <section className="report-empty-state"><span className="eyebrow">Portfolio report</span><h2>{hasPortfolioAccess ? 'Add holdings to unlock your report' : 'Cloud portfolio is offline'}</h2><p>{hasPortfolioAccess ? 'Portfolio analytics appear after holdings and per-share cost basis are available.' : authError || 'Firebase is connecting to your solo workspace.'}</p>{hasPortfolioAccess ? <Link className="primary-button" to="/portfolio">Add holdings</Link> : <button type="button" className="primary-button" onClick={retryAuth}>Reconnect Firebase</button>}</section> : <>
      {actionable.length > 0 && <Link className="home-sell-notification" to="/portfolio"><Icon name="bell" size={17} /><span><strong>{actionable.length} sell signal{actionable.length === 1 ? '' : 's'} need review</strong><small>{actionable.map((row) => row.ticker).join(', ')} · Hold positions are intentionally excluded.</small></span><Icon name="chevron" size={16} /></Link>}
      <HomePortfolioPanel
        positions={portfolio.positions}
        chart={homeChart}
        chartLabel={homeChartLabel}
        period={period}
        onPeriodChange={(next) => { setPeriod(next); updatePreferences({ defaultChartPeriod: next }) }}
        money={money}
        totalValue={trackedAccountValue}
        totalProfit={homePeriodProfit}
        today={heroToday}
        fetchedAt={portfolioQuotes.fetchedAt}
      />
      <div className="dashboard-customize-bar"><a className="secondary-button compact" href="/?customize=1"><Icon name="grip" size={15} /> Reorder widgets</a></div>
      <div className="dashboard-widget-stack">
      <DashboardWidget id="metric-grid" widgets={preferences.widgets}>
      {/* The scope switch sits above everything it scopes — it drives the score gauges
          and the evidence summary alike, and used to sit between them. */}
      <div className="settings-row live-tracking-setting">
        <div><strong>Since live tracking started only</strong><span>Excludes the backtested history before {LIVE_TRACKING_START} from the scores and evidence below, instead of applying today's holdings to the full history.</span>{sinceLiveTrackingOnly && <LiveTrackingCountdown dates={liveHoldingsSeries?.dates} />}</div>
        <label className="switch"><input type="checkbox" checked={sinceLiveTrackingOnly} onChange={(e) => setSinceLiveTrackingOnly(e.target.checked)} /><span aria-hidden="true" /></label>
      </div>
      <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Portfolio scores</span><h2>Decision-quality snapshot</h2></div><Link to="/portfolio/diversification">View diversification →</Link></header><div className="report-score-grid"><ScoreCard label="Portfolio score" result={overall} note={`${overall.reason} ${overall.available ? `${overall.strongest} is strongest. ${overall.weakest} has the most room to improve.` : ''}`} /><ScoreCard label="Diversification" result={diversification} note={`${diversification.warnings.length ? diversification.warnings[0] : 'No major concentration warning in covered holdings.'}`} /><ScoreCard label="Resilience" result={resilience} note={resilience.available ? `${Math.abs(resilience.maxDrawdown).toFixed(1)}% maximum drawdown and ${resilience.volatility.toFixed(1)}% annualized volatility.` : ''} /></div>{overall.available && <details className="score-method"><summary>How the portfolio score is built</summary><div>{Object.entries(overall.components).map(([label, value]) => <span key={label}><b>{label.replace(/([A-Z])/g, ' $1')}</b><em>{value == null ? 'Unavailable' : `${Math.round(value)}/100`}</em></span>)}</div><p>The portfolio score remains provisional whenever a component is missing. Standard performance statistics are reported separately and are not converted into a grade.</p></details>}</section>

      {/* The full metric apparatus lives on Portfolio → Data overview. This is the read
          and its counts, linking through — not a second copy of that page. */}
      <PerformanceEvidenceSummary metrics={performance} />
      </DashboardWidget>

      <DashboardWidget id="allocation" widgets={preferences.widgets}>
        <section className="report-section sector-allocation-widget"><header className="section-heading"><div><span className="eyebrow">Allocation</span><h2>Sector allocation
          <InfoTag label="Sector allocation">
            <strong>Sector allocation</strong>
            <p>Share of your covered portfolio value in each GICS sector, by current market value.
              Concentrated in one or two sectors means the portfolio moves with that sector's fate -
              see Diversification for the full look-through breakdown including ETF holdings.</p>
          </InfoTag>
        </h2></div><Link to="/portfolio/diversification">Full analysis →</Link></header>
        <div className="allocation-split">
          <AllocationDonut sectors={sectorAllocation} totalLabel={money(portfolio.totalValue)} />
          <div className="allocation-bars">{sectorAllocation.map((item) => <article key={item.sector}><div><strong>{item.sector}</strong><span>{item.pct.toFixed(1)}%</span></div><i aria-hidden="true"><span style={{ width: `${item.pct}%` }} /></i><small>{money(item.value)}</small></article>)}</div>
        </div></section>
      </DashboardWidget>

      <DashboardWidget id="top-signal" widgets={preferences.widgets}>
        <article className="signal-preview"><header><div><span className="eyebrow">Top signal</span><h2>Research leader</h2></div><Tier label={leader.stance} /></header><div className="signal-company"><CompanyLogo company={leader} size={48} /><div><strong>{leader.ticker}</strong><span>{leader.name}</span></div><b>{leader.score}/100</b></div>{leader.sparkline && <Sparkline values={leader.sparkline} height={48} className="signal-sparkline" />}<p>{leader.strengths?.[0] || 'Highest-scoring published company in the latest evidence run.'}</p><Link to="/research">Open research →</Link></article>
      </DashboardWidget>

      <DashboardWidget id="action-needed" widgets={preferences.widgets}>
        <article className="action-preview"><header><div><span className="eyebrow">Actions</span><h2>Holdings to review</h2></div><Link to="/portfolio">Open portfolio</Link></header><strong>{actionable.length}</strong><p>{actionable.length ? `${actionable.slice(0, 4).map((row) => row.ticker).join(', ')} have evidence-based guidance beyond Hold.` : 'No covered holding has multi-factor guidance beyond Hold.'}</p><small>Research prompts only. Review the underlying evidence before acting.</small></article>
      </DashboardWidget>

      <DashboardWidget id="watchlist-preview" widgets={preferences.widgets}>
        <article className="watchlist-preview"><header><div><span className="eyebrow">Watchlist</span><h2>Names you follow</h2></div><Link to="/watchlist">View all</Link></header>{watchRows.length ? watchRows.map((row) => <div className="watch-preview-row" key={row.ticker}><CompanyLogo company={row} size={32} /><div><strong>{row.ticker}</strong><span>{row.name}</span></div>{row.sparkline && <Sparkline values={row.sparkline} height={28} className="watch-sparkline" />}<span className="watch-row-stats"><b>{row.score}</b>{row.dayChange != null && <Move pct={row.dayChange} />}</span></div>) : <p>No published watchlist matches yet.</p>}</article>
      </DashboardWidget>
      </div>

      <section className="report-two-column">
        <ReportProjection input={projectionInput} source={projectionSource} money={money} annualReturnTargetPct={annualReturnTargetPct} currentAge={finances.settings.currentAge} retirementAge={finances.settings.retireAge} contribution={finances.settings.monthlyContribution * projectionConfig.months_per_year} liveStrategyReturn={liveStrategyAnnualReturnPct != null} />
        <article className="opportunity-card"><span className="eyebrow">Opportunity cost</span><h2>Potential earnings by benchmark</h2>{comparison ? <><div className="opportunity-baseline"><span>Shared starting value</span><strong>{money(comparison.startingValue)}</strong><small>{comparison.startDate} to {comparison.endDate}</small></div><div className="opportunity-list"><div className="portfolio-opportunity-row"><span>Current holdings<small>Charted potential earnings</small></span><strong>{chartedPortfolio.dollarReturn >= 0 ? '+' : '−'}{money(Math.abs(chartedPortfolio.dollarReturn))}</strong></div>{comparison.benchmarks.map((item) => <div key={item.symbol}><span>{item.symbol} proxy<small>{item.label} potential earnings</small></span><strong>{item.potentialEarnings >= 0 ? '+' : '−'}{money(Math.abs(item.potentialEarnings))}</strong><em className={tone(item.differenceVsPortfolio)}>{item.differenceVsPortfolio >= 0 ? `Portfolio ahead ${money(item.differenceVsPortfolio)}` : `Benchmark ahead ${money(Math.abs(item.differenceVsPortfolio))}`}</em></div>)}</div><small>{comparison.methodology}</small></> : <p>Comparable history is unavailable for this selection.</p>}</article>
      </section>
    </>}

    <BuyingTheDipChart rows={dipRows} />

    <MarketPulsePreview data={data} loading={loading} />
    <MarketHeatmap positions={portfolio.positions} />

    <section className="report-focused-screens" aria-labelledby="focused-screens-title">
      <header className="section-heading"><div><span className="eyebrow">Focused breakdown</span><h2 id="focused-screens-title">Fast growth, value, momentum, reversals, and ETFs</h2></div><Link to="/research">All research →</Link></header>
      <div className="report-screen-grid">
        {focusedScreens.map((screen, index) => <FocusedScreenCard key={screen.kicker} {...screen} style={{ '--i': index }} />)}
        <InsideInformationCard rows={insideInformation?.results?.slice(0, 3) || []} loading={insideInformationLoading}
          style={{ '--i': focusedScreens.length }} />
      </div>
      <p className="screen-disclaimer">Research screens, not trade instructions. Confirm current prices, liquidity, news, and your own risk limits before acting.</p>
    </section>

    <footer className="report-methodology-note">Balances use the latest stored closes. Historical portfolio lines apply current quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes, fees, or dividends. General research only.</footer>
  </div>
}
