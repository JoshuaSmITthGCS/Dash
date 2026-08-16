import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useAuth } from '../lib/FirebaseAuthContext'
import { Loading, RefreshProgress, RatingBadge } from '../components/Bits'
import { ActionPill } from '../components/ActionGuidance'
import GrowthChart from '../components/GrowthChart'
import Sparkline from '../components/Sparkline'
import InfoTag from '../components/InfoTag.jsx'
import StockDetailModal from '../components/StockDetailModal'
import { getRecommendation } from '../lib/recommendation'
import { stopLossLevels, withStopLoss } from '../lib/positionRisk'
import { assessPortfolioExposure } from '../lib/portfolioExposure'
import {
  benchmarkAlternative,
  fixedBasisAlternative,
  portfolioFixedBasisVsBenchmark,
  portfolioGrowthSeries,
  portfolioVsBenchmark,
  currentHoldingsPerformanceSeriesForPeriod,
} from '../lib/portfolioPerformance'
import Icon from '../components/Icons'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import {
  nextPortfolioSort,
  PORTFOLIO_SORT_OPTIONS,
  sortPortfolioPositions,
} from '../lib/portfolioSort'
import { buildPortfolioPriceData, mergePortfolioQuotes, mergePositionSnapshots } from '../lib/portfolioPosition'
import { buildRatingContext, researchRating } from '../lib/researchRating.js'
import { explainPortfolioMove } from '../lib/portfolioAttribution.js'
import PortfolioMoveExplanation from '../components/PortfolioMoveExplanation.jsx'
import { usePortfolioQuotes } from '../lib/usePortfolioQuotes'
import { usePullToRefresh } from '../lib/usePullToRefresh'
import PullToRefreshIndicator from '../components/PullToRefreshIndicator.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import AnimatedNumber from '../components/AnimatedNumber.jsx'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import {
  alignSeries,
  benchmarkHistoryFromSnapshot,
  BENCHMARKS,
  compareBenchmarkSeries,
  concentrationLiquidityScore,
  currentHoldingsSeries,
  diversificationScore,
  latestMarketDayReturn,
  performanceMetrics,
  portfolioRiskDecomposition,
  portfolioScore,
  resilienceIndex,
  riskFreeAnnualRate,
  sectorLookThrough,
  selectPeriod,
  sliceSeriesFrom,
  underwaterProfile,
} from '../lib/portfolioAnalytics.js'
import { portfolioAcceleration } from '../lib/portfolioAcceleration.js'
import { battingAverage, captureRatios } from '../lib/portfolioBenchmarkComparison.js'
import { shortTermView } from '../lib/portfolioShortTermView.js'
import PerformanceMetrics from '../components/PerformanceMetrics.jsx'
import { MobileSheet, ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import { LIVE_TRACKING_START } from '../lib/liveTrackingAvailability.js'
import { factorRegression } from '../lib/factorAnalytics.js'
import {
  benchmarkFit,
  executionStatistics,
  exposureStatistics,
  performanceStatistics,
  regimeConditionalPerformance,
  robustnessStatistics,
} from '../lib/portfolioStatistics.js'
import { buildPortfolioMetricModel } from '../lib/portfolioMetricModel.js'
import { compareEvidencePeriods } from '../lib/metricAssessment.js'
import prospectiveValidation from '../../pipeline/validation/harness_freeze.json'
import StockTickerTape from '../components/StockTickerTape.jsx'
import { dailyMoveForPosition } from '../lib/marketPresentation.js'
import AllocationDonut from '../components/AllocationDonut.jsx'
import { buildPeerIndex } from '../lib/rankingModels.js'
import { styleOf } from '../lib/portfolioStyleTilt.js'
import { liveTodayPortfolioReturn } from '../lib/afterHoursQuotes.js'
import { REFERENCE_PORTFOLIO_VERSION } from '../lib/referencePortfolio.js'
import modelSettings from '../../pipeline/config/settings.json'

const ANALYTICS_SCOPES = [
  { id: 'all_history', label: 'All portfolio history' },
  { id: 'since_algorithm', label: 'Since algorithm activation' },
  { id: 'live_algorithm', label: 'Live algorithm only' },
  { id: 'backtest', label: 'Backtest period' },
]

const SUMMARY_PERIODS = ['1H', '1D', '1W', '1M', '3M', '1Y']
const PERFORMANCE_PERIODS = ['1W', '1M', '3M', '1Y', 'All']
const PERIOD_NAMES = { '1H': 'Last hour', '1D': 'Today', '1W': 'Week', '1M': 'Month', '3M': '3 months', '1Y': 'Year', All: 'All time' }
export const PORTFOLIO_NAV = [
  { to: '/portfolio', label: 'Summary', end: true },
  { to: '/portfolio/performance', label: 'Performance' },
  { to: '/portfolio/data-overview', label: 'Data overview' },
]

const PORTFOLIO_PAGE_COPY = {
  summary: {
    title: <>My <span className="accent">portfolio</span></>,
    description: 'Your holdings, suggested actions, and current allocation.',
  },
  performance: {
    title: <>Portfolio <span className="accent">performance</span></>,
    description: 'Your time-weighted return and a fair comparison with the selected benchmark.',
  },
  data: {
    title: <>Portfolio <span className="accent">data overview</span></>,
    description: 'Why your portfolio moved and the evidence behind its standard measures.',
  },
}

export function PortfolioNavigation() {
  return (
    <nav className="screen-nav portfolio-section-nav" aria-label="Portfolio sections">
      {PORTFOLIO_NAV.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end}
          className={({ isActive }) => isActive ? 'active' : ''}>{item.label}</NavLink>
      ))}
    </nav>
  )
}

function sessionSetting(key, fallback) {
  try { return globalThis.sessionStorage?.getItem(key) || fallback } catch { return fallback }
}

function asValueSeries(history, limit = null) {
  if (!history?.dates?.length) return null
  const start = limit ? Math.max(0, history.dates.length - limit) : 0
  return {
    dates: history.dates.slice(start),
    values: (history.values || history.closes || []).slice(start),
    frequency: history.frequency || 'daily',
    source: history.source || history.symbol || null,
    symbol: history.symbol || null,
    label: history.label || null,
    methodology: history.methodology,
  }
}

function sliceSeriesBefore(series, cutoffDate) {
  if (!series?.dates?.length) return null
  const end = series.dates.findIndex((date) => date >= cutoffDate)
  if (end < 2) return null
  return { ...series, dates: series.dates.slice(0, end), values: series.values.slice(0, end), coverage: series.coverage?.slice(0, end) }
}

const money = (value, digits = 0) =>
  value == null ? '–' : `$${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`

const signedPct = (value, digits = 1) =>
  value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`

const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

// The backtested-basket series that risk/performance stats are computed from applies today's
// holdings to every historical date it has prices for -- including dates before live tracking
// in this account actually began. The switch below lets those stats be evaluated only since
// that date instead, so ratios reflect the strategy actually being run, not a hypothetical
// basket replayed further back than the account existed.
// Cost basis is stored per share everywhere downstream (totalCost = shares * costBasis), but
// that's easy to enter wrong: a $200 total investment typed into a bare "Cost Basis" field
// reads as $200/share, inflating cost basis by the share count. Letting the form accept
// either unit and normalizing here keeps the stored value's meaning consistent.
function perShareCost(rawValue, shares, mode) {
  const amount = parseFloat(rawValue)
  if (!Number.isFinite(amount) || !Number.isFinite(shares) || shares <= 0) return NaN
  return mode === 'total' ? amount / shares : amount
}

function Move({ value, digits = 1 }) {
  return <span className="mono" style={{ color: moveColor(value) }}>{signedPct(value, digits)}</span>
}

function recentReturn(values, points = 5) {
  const clean = (values || []).filter(Number.isFinite).slice(-points)
  if (clean.length < 2 || !clean[0]) return null
  return (clean.at(-1) / clean[0] - 1) * 100
}

/** Where the binding stop sits and how far away it is – visible before it's hit, not just after. */
function StopLossNote({ stopLoss }) {
  if (!stopLoss || stopLoss.bindingPrice == null) return null
  const close = stopLoss.distancePct != null && stopLoss.distancePct <= 5
  const past = stopLoss.distancePct != null && stopLoss.distancePct < 0
  return (
    <span className="mono stop-loss-note" style={{ color: past ? 'var(--neg)' : close ? 'var(--warn)' : 'var(--text-faint)', fontSize: 12 }}>
      Stop ${stopLoss.bindingPrice.toFixed(2)}
      {stopLoss.distancePct != null && (
        past ? ` · ${Math.abs(stopLoss.distancePct).toFixed(1)}% past it` : ` · ${stopLoss.distancePct.toFixed(1)}% away`
      )}
    </span>
  )
}

function PortfolioSortToolbar({ sort, selectedLabel, onSortKey, onToggleDirection }) {
  const controls = (
    <div className="portfolio-sort-toolbar" aria-label="Portfolio sorting controls">
      <label>
        <span>Sort holdings</span>
        <select value={sort.key} onChange={(event) => onSortKey(event.target.value)}>
          {PORTFOLIO_SORT_OPTIONS.map((option) => (
            <option key={option.key} value={option.key}>{option.label}</option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button portfolio-sort-direction"
        onClick={onToggleDirection}
        aria-label={`Reverse ${selectedLabel || 'portfolio'} sort order`}
      >
        {sort.direction === 'asc' ? 'Ascending ↑' : 'Descending ↓'}
      </button>
    </div>
  )
  return <ResponsiveControlPanel label={`Sort: ${selectedLabel || 'holdings'}`} title="Sort holdings">{controls}</ResponsiveControlPanel>
}

export default function Portfolio({ view = 'summary' }) {
  const { currentUser } = useAuth()
  const { data, loading: dataLoading, reload } = useData('report.json')
  const { data: etfData } = useData('etfs.json')
  const { data: factorData } = useData('factors/french.json')
  const { data: signalMetrics } = useData('validation/signal_metrics.json')
  const { data: spySnapshot } = useData('etf/SPY.json')
  const { data: rspSnapshot } = useData('etf/RSP.json')
  const { data: iwmSnapshot } = useData('etf/IWM.json')
  const { data: ijrSnapshot } = useData('etf/IJR.json')
  const {
    positions: storedPositions,
    loading: portfolioLoading,
    addPosition,
    removePosition,
    updatePosition,
    exportPortfolio,
    syncReferencePortfolio,
    syncState,
  } = useFirebasePortfolio()
  const previewPortfolio = import.meta.env.DEV
    && new window.URLSearchParams(window.location.search).get('portfolioPreview') === '1'
  const positions = previewPortfolio ? modelSettings.interface.mobile_preview_positions : storedPositions
  const tracking = usePortfolioTracking()
  const { preferences, updatePreferences } = usePreferences()
  const { data: selectedBenchmarkSnapshot } = useData(`etf/${preferences.defaultBenchmark || 'SPY'}.json`)

  const [showAddForm, setShowAddForm] = useState(false)
  const [formData, setFormData] = useState({ ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: new Date().toISOString().split('T')[0] })
  const [viewMode, setViewMode] = useState('holdings')
  const [selectedStock, setSelectedStock] = useState(null)
  const [syncMessage, setSyncMessage] = useState('')
  const [portfolioSort, setPortfolioSort] = useState(preferences.holdingSort)
  const [removingId, setRemovingId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ shares: '', costBasis: '', costMode: 'share', purchaseDate: '' })
  const [editSaving, setEditSaving] = useState(false)
  const [sellingId, setSellingId] = useState(null)
  const [sellForm, setSellForm] = useState({ shares: '', price: '', saleDate: new Date().toISOString().split('T')[0] })
  const [sellSaving, setSellSaving] = useState(false)
  const [analyticsScope, setAnalyticsScope] = useState(() => sessionSetting('valuesignal.analytics.scope', 'all_history'))
  const [summaryPeriod, setSummaryPeriod] = useState('1D')
  const [performancePeriod, setPerformancePeriod] = useState('1M')
  const [attributionPeriod, setAttributionPeriod] = useState('1D')
  const [essentialOnly, setEssentialOnly] = useState(true)
  const [suggestedActionsOpen, setSuggestedActionsOpen] = useState(preferences.suggestedActionsDefault === 'expanded')
  const referencePortfolioSyncStarted = useRef(false)
  const refresh = useAdvisorRefresh(
    data?.generated_at,
    reload,
    positions.map((position) => position.ticker),
  )
  // SPY rides along with the portfolio's own quote requests so the move-explanation
  // widget's market leg can use a live intraday benchmark return too, not just the
  // holdings - same refresh cadence, same Netlify function, one extra symbol.
  const portfolioQuotes = usePortfolioQuotes([...positions.map((position) => position.ticker), 'SPY'])
  const pullToRefresh = usePullToRefresh({
    onRefresh: portfolioQuotes.requestRefresh,
    enabled: positions.length > 0,
    refreshing: portfolioQuotes.refreshing,
  })

  const research = data?.research || []
  const portfolioCoverage = data?.portfolio_coverage || []
  const screenUniverse = data?.screen_universe || []
  const benchmarkHistory = data?.benchmark_history
  const benchmarkAnalyticsHistory = data?.benchmark_analytics_history
  // Lightweight screen rows are a useful quote fallback for a holding that has been
  // fetched but has not reached full published coverage yet (EXPE is one such case).
  // Full coverage is listed last so it always wins when both versions exist.
  const publishedPriceData = mergePositionSnapshots(
    buildPortfolioPriceData(screenUniverse, portfolioCoverage, research),
    positions,
    data?.generated_at,
  )
  const quoteRefreshIsNewest = portfolioQuotes.fetchedAt
    && new Date(portfolioQuotes.fetchedAt) >= new Date(data?.generated_at || 0)
  const priceData = mergePortfolioQuotes(
    publishedPriceData,
    quoteRefreshIsNewest ? portfolioQuotes.quotes : {},
  )
  const pricesUpdatedAt = quoteRefreshIsNewest ? portfolioQuotes.fetchedAt : data?.generated_at

  const portfolioStats = positions.reduce((acc, pos) => {
    const ticker = String(pos.ticker || '').trim().toUpperCase()
    const current = priceData[ticker]
    const currentPrice = current?.price ?? pos.snapshotPrice ?? null
    const totalCost = pos.shares * pos.costBasis
    const currentValue = current?.positionSnapshot && pos.snapshotValue != null
      ? Number(pos.snapshotValue)
      : current?.price != null
      ? pos.shares * current.price
      : pos.snapshotValue ?? (currentPrice == null ? null : pos.shares * currentPrice)
    const gain = currentValue == null ? null : currentValue - totalCost
    const trendValues = current?.history?.closes?.filter(Number.isFinite).slice(-22) || []
    const gainPct = gain == null || !totalCost ? null : (gain / totalCost) * 100
    const riskPosition = { gainPct, currentPrice, costBasis: pos.costBasis, purchaseDate: pos.purchaseDate, priceInfo: current }
    const recommendation = current
      ? withStopLoss(getRecommendation(current), riskPosition)
      : null
    const enriched = {
      ...pos,
      ticker,
      currentPrice,
      totalCost,
      currentValue,
      gain,
      gainPct,
      trendValues,
      trendPct: recentReturn(trendValues),
      quoteSource: current?.portfolioQuote
        ? 'Portfolio price refresh'
        : current?.price ? 'Research refresh' : pos.snapshotPrice ? pos.snapshotSource : null,
      priceInfo: current,
      recommendation,
      stopLoss: current ? stopLossLevels(riskPosition) : null,
      versusBenchmark: benchmarkAlternative({ ...pos, currentValue }, benchmarkHistory),
    }
    return {
      totalCost: acc.totalCost + totalCost,
      totalValue: acc.totalValue + (currentValue || 0),
      totalGain: acc.totalGain + (gain || 0),
      positions: [...acc.positions, enriched],
    }
  }, { totalCost: 0, totalValue: 0, totalGain: 0, positions: [] })

  // Same percentile-based -5..+5 read used on the Research page (src/lib/researchRating.js),
  // built from the published research pool so a holding rates against the same peers there.
  const ratingContext = buildRatingContext(research)
  const portfolioPositions = portfolioStats.positions.map((position) => ({
    ...position,
    allocationPct: portfolioStats.totalValue > 0 && position.currentValue != null ? position.currentValue / portfolioStats.totalValue * 100 : null,
    rating: researchRating(position.priceInfo, ratingContext),
    dayMove: dailyMoveForPosition(position),
  }))
  const pricedAccountValue = portfolioStats.totalValue
  const etfTickers = new Set((etfData?.etfs || []).map((row) => String(row.ticker || '').toUpperCase()))
  const stylePeerIndex = buildPeerIndex(research.filter((row) => !row.is_etf))
  const assetTotals = portfolioPositions.reduce((totals, position) => {
    if (!(position.currentValue > 0)) return totals
    const bucket = etfTickers.has(position.ticker)
      ? 'ETFs'
      : styleOf(stylePeerIndex, position.priceInfo) === 'short_term'
        ? 'Short-term stocks'
        : 'Long-term stocks'
    totals[bucket] = (totals[bucket] || 0) + position.currentValue
    return totals
  }, {})
  const assetAllocation = ['Long-term stocks', 'Short-term stocks', 'ETFs']
    .filter((label) => assetTotals[label] > 0)
    .map((label) => ({
      label,
      value: assetTotals[label],
      pct: pricedAccountValue > 0 ? assetTotals[label] / pricedAccountValue * 100 : 0,
    }))
  const sectorAllocation = sectorLookThrough(portfolioPositions, etfData?.etfs || []).exposures
    .map((row) => ({ sector: row.label, pct: row.pct }))
  // Tagged the same way mergePortfolioQuotes tags a holding's live quote, since this is the
  // raw Netlify-function payload rather than something already run through that merge.
  const benchmarkQuote = quoteRefreshIsNewest && portfolioQuotes.quotes?.SPY
    ? { ...portfolioQuotes.quotes.SPY, portfolioQuote: true }
    : null
  const moveExplanation = explainPortfolioMove(portfolioPositions, benchmarkHistory, {
    benchmarkQuote,
    period: attributionPeriod,
  })
  const reportBenchmarkSeries = asValueSeries(benchmarkAnalyticsHistory, 504)
  const candidateInputs = [
    { symbol: 'SPY', label: 'S&P 500', snapshot: spySnapshot },
    { symbol: 'RSP', label: 'Equal-weight S&P 500', snapshot: rspSnapshot },
    { symbol: 'IWM', label: 'Russell 2000', snapshot: iwmSnapshot },
    { symbol: 'IJR', label: 'S&P SmallCap 600', snapshot: ijrSnapshot },
  ].map(({ symbol, label, snapshot }) => {
    const series = asValueSeries(benchmarkHistoryFromSnapshot(snapshot), 504)
    return series ? { ...series, symbol, label } : null
  }).filter(Boolean)
  const selectedPublished = asValueSeries(benchmarkHistoryFromSnapshot(selectedBenchmarkSnapshot), 504)
  const selectedBenchmarkSymbol = selectedPublished?.symbol || reportBenchmarkSeries?.symbol || 'SPY'
  const selectedBenchmarkLabel = BENCHMARKS.find((row) => row.symbol === selectedBenchmarkSymbol)?.label
    || candidateInputs.find((row) => row.symbol === selectedBenchmarkSymbol)?.label
    || selectedBenchmarkSymbol
  const analyticsBenchmarkSeries = selectedPublished || reportBenchmarkSeries
  const scoreHoldingsSeriesFull = currentHoldingsSeries(positions, priceData, analyticsBenchmarkSeries?.dates || [])
  const sinceAlgorithmSeries = sliceSeriesFrom(scoreHoldingsSeriesFull, LIVE_TRACKING_START)
  const summaryRecordedSeries = currentHoldingsPerformanceSeriesForPeriod(
    tracking.snapshots,
    positions,
    priceData,
    summaryPeriod,
  )
  const summaryFallbackSeries = summaryPeriod === '1H' ? null : selectPeriod(scoreHoldingsSeriesFull, summaryPeriod)
  const summaryChart = summaryRecordedSeries || summaryFallbackSeries
  const summaryProfit = summaryChart?.dollarReturn
    ?? (summaryChart?.values?.length > 1 ? summaryChart.values.at(-1) - summaryChart.values[0] : null)
  const summaryReturnPct = summaryChart?.returnPct
    ?? (summaryChart?.values?.length > 1 && summaryChart.values[0]
      ? (summaryChart.values.at(-1) / summaryChart.values[0] - 1) * 100
      : null)
  const comparisonSource = scoreHoldingsSeriesFull
  const visiblePerformancePeriod = selectPeriod(comparisonSource, performancePeriod)
  const visiblePerformanceComparison = compareBenchmarkSeries(
    visiblePerformancePeriod,
    analyticsBenchmarkSeries ? [{
      symbol: selectedBenchmarkSymbol,
      label: selectedBenchmarkLabel,
      dates: analyticsBenchmarkSeries.dates,
      values: analyticsBenchmarkSeries.values,
    }] : [],
  )
  const performanceIndex = visiblePerformanceComparison ? {
    dates: visiblePerformanceComparison.dates,
    portfolio: visiblePerformanceComparison.portfolio.values.map((value) => 100 * value / visiblePerformanceComparison.portfolio.values[0]),
    benchmark: visiblePerformanceComparison.benchmarks[0].values.map((value) => 100 * value / visiblePerformanceComparison.benchmarks[0].values[0]),
  } : null
  const scoreHoldingsSeries = analyticsScope === 'since_algorithm'
    ? sinceAlgorithmSeries
    : analyticsScope === 'live_algorithm'
      ? sinceAlgorithmSeries
      : analyticsScope === 'backtest'
        ? null
        : scoreHoldingsSeriesFull
  const scorePortfolioPeriod = selectPeriod(scoreHoldingsSeries, 'All')
  const scoreBenchmarkPeriod = selectPeriod(analyticsBenchmarkSeries, 'All')
  const scoreComparable = alignSeries(scorePortfolioPeriod, scoreBenchmarkPeriod, scorePortfolioPeriod?.period)
  const riskFree = riskFreeAnnualRate(data)
  const backtestBlocker = 'A registered algorithm backtest return series is not published; signal diagnostics are available in the Algorithm view, but portfolio returns are not inferred from them.'
  const scorePerformance = analyticsScope === 'backtest'
    ? { available: false, score: null, observations: 0, reason: backtestBlocker }
    : performanceMetrics(scoreComparable?.left, scoreComparable?.right, riskFree.annualPct)
  // Every metric below receives the same selected scope and daily benchmark. Metrics with a
  // legitimate monthly cadence (batting average/factors) declare their own count and dates.
  const scoreAcceleration = portfolioAcceleration(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const scoreCapture = captureRatios(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const scoreBatting = battingAverage(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const scoreUnderwater = underwaterProfile(scoreHoldingsSeries)
  const scoreShortTerm = shortTermView(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const scoreRisk = portfolioRiskDecomposition(portfolioPositions, {
    benchmarkHistory: analyticsBenchmarkSeries ? { dates: analyticsBenchmarkSeries.dates, closes: analyticsBenchmarkSeries.values } : null,
    benchmarkWeights: (etfData?.etfs || []).find((row) => row.ticker === selectedBenchmarkSymbol)?.top_holdings,
    etfs: etfData?.etfs || [],
  })
  const scoreDiversification = diversificationScore(portfolioPositions, { etfs: etfData?.etfs || [] })
  const scoreResilience = resilienceIndex(scoreComparable?.left?.values || scorePortfolioPeriod?.values || [], scoreDiversification)
  const scoreConcentration = concentrationLiquidityScore(portfolioPositions)
  const legacyPortfolioScore = portfolioScore({
    diversification: scoreDiversification,
    resilience: scoreResilience,
    performance: scorePerformance,
    benchmarkEfficiency: null,
    concentrationLiquidity: scoreConcentration,
    dataCompleteness: positions.length ? Math.round(portfolioPositions.filter((position) => position.currentValue != null).length / positions.length * 100) : 0,
  })
  const scoreStatistics = analyticsScope === 'backtest'
    ? { available: false, observations: 0, reason: backtestBlocker }
    : performanceStatistics(scoreComparable?.left || scorePortfolioPeriod, riskFree.annualPct, { trialCount: prospectiveValidation.trial_count_for_deflated_statistics?.dsr_trial_count_used })
  const scoreFactor = factorRegression(scoreComparable?.left || scorePortfolioPeriod, factorData)
  const scoreBenchmarkFit = benchmarkFit(scoreHoldingsSeries, candidateInputs)
  const comparisonFor = (candidate) => {
    if (!candidate || !scoreHoldingsSeries) return null
    const portfolioPeriod = selectPeriod(scoreHoldingsSeries, 'All')
    const benchmarkPeriod = selectPeriod(candidate, 'All')
    const comparable = alignSeries(portfolioPeriod, benchmarkPeriod, 'All')
    return {
      symbol: candidate.symbol,
      label: candidate.label,
      performance: performanceMetrics(comparable?.left, comparable?.right, riskFree.annualPct),
      capture: captureRatios(scoreHoldingsSeries, candidate),
      batting: battingAverage(scoreHoldingsSeries, candidate),
    }
  }
  const scoreBenchmarkComparisons = {
    spy: comparisonFor(candidateInputs.find((row) => row.symbol === 'SPY')),
    best: comparisonFor(candidateInputs.find((row) => row.symbol === scoreBenchmarkFit.bestFit?.symbol)),
  }
  const scoreExposure = exposureStatistics(portfolioPositions)
  const scoreExecution = executionStatistics()
  const publishedPbo = signalMetrics?.metrics?.find((row) => row.id === 'pbo')
  const scoreRobustness = robustnessStatistics({
    pbo: ['ready', 'provisional'].includes(publishedPbo?.status) ? publishedPbo.value : null,
  })
  const scoreRegimes = regimeConditionalPerformance(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const scoreMetricModel = buildPortfolioMetricModel({
    performance: scorePerformance,
    statistics: scoreStatistics,
    acceleration: scoreAcceleration,
    capture: scoreCapture,
    batting: scoreBatting,
    underwater: scoreUnderwater,
    shortTerm: scoreShortTerm,
    risk: scoreRisk,
    factor: scoreFactor,
    benchmark: scoreBenchmarkFit,
    benchmarkComparisons: scoreBenchmarkComparisons,
    exposure: scoreExposure,
    execution: scoreExecution,
    robustness: scoreRobustness,
    regime: scoreRegimes,
    legacyPortfolioScore,
  })
  const comparableEvidenceFor = (series) => {
    const portfolioPeriod = selectPeriod(series, 'All')
    const benchmarkPeriod = selectPeriod(analyticsBenchmarkSeries, 'All')
    const comparable = alignSeries(portfolioPeriod, benchmarkPeriod, 'All')
    const performance = performanceMetrics(comparable?.left, comparable?.right, riskFree.annualPct)
    const statistics = performanceStatistics(comparable?.left || portfolioPeriod, riskFree.annualPct, { trialCount: prospectiveValidation.trial_count_for_deflated_statistics?.dsr_trial_count_used })
    const model = buildPortfolioMetricModel({
      performance,
      statistics,
      acceleration: portfolioAcceleration(series, analyticsBenchmarkSeries),
      capture: captureRatios(series, analyticsBenchmarkSeries),
      batting: battingAverage(series, analyticsBenchmarkSeries),
      underwater: underwaterProfile(series),
      shortTerm: shortTermView(series, analyticsBenchmarkSeries),
    })
    return [...model.standard, ...model.comparison, ...model.fast]
  }
  const algorithmBaseline = compareEvidencePeriods(
    comparableEvidenceFor(sliceSeriesBefore(scoreHoldingsSeriesFull, LIVE_TRACKING_START)),
    comparableEvidenceFor(sinceAlgorithmSeries),
  )
  const versusIndex = portfolioVsBenchmark(portfolioPositions, benchmarkHistory)
  const basis = data?.hypothetical_basis || 500
  const fixedBasisTotal = portfolioFixedBasisVsBenchmark(portfolioStats.positions, priceData, benchmarkHistory, basis)
  const growth = portfolioGrowthSeries(portfolioStats.positions, priceData, benchmarkHistory)
  const actionable = portfolioPositions.filter((pos) => pos.recommendation?.action === 'SELL')
  const exposure = assessPortfolioExposure(portfolioPositions)
  const sortedPositions = sortPortfolioPositions(
    portfolioPositions,
    portfolioSort.key,
    portfolioSort.direction,
  )
  const commitSort = (next) => { setPortfolioSort(next); updatePreferences({ holdingSort: next }) }
  const setSortKey = (key) => commitSort(nextPortfolioSort(portfolioSort, key))
  const toggleSortDirection = () => commitSort({ ...portfolioSort, direction: portfolioSort.direction === 'asc' ? 'desc' : 'asc' })
  const selectedSort = PORTFOLIO_SORT_OPTIONS.find((option) => option.key === portfolioSort.key)
  // Rendered once, outside both the mobile card list and the desktop table, so triggering a
  // sale from either (only one is visible at a given viewport width) still shows the sheet.
  const sellingPosition = sortedPositions.find((pos) => (pos.id || pos.ticker) === sellingId)

  const currentSessionMove = liveTodayPortfolioReturn(positions, priceData)
  const latestDailyMove = latestMarketDayReturn(scoreHoldingsSeriesFull)
  const todayMove = currentSessionMove.available
    ? currentSessionMove
    : latestDailyMove

  // Apply the user's authoritative Fidelity position export once on the signed-in account.
  // The version marker prevents later manual portfolio edits from being overwritten.
  useEffect(() => {
    const referenceReady = tracking.trackingState?.referencePortfolioVersion === REFERENCE_PORTFOLIO_VERSION
    if (previewPortfolio || !syncState.connected || referenceReady || referencePortfolioSyncStarted.current) return
    referencePortfolioSyncStarted.current = true
    syncReferencePortfolio().then((result) => {
      if (result?.success) setSyncMessage(`Fidelity snapshot applied: ${result.added} added · ${result.updated} updated · ${result.removed} removed.`)
      else {
        referencePortfolioSyncStarted.current = false
        setSyncMessage(`Could not apply Fidelity positions: ${result?.error || 'Unknown error'}`)
      }
    })
  }, [previewPortfolio, syncReferencePortfolio, syncState.connected, tracking.trackingState?.referencePortfolioVersion])

  if (dataLoading || portfolioLoading) return <Loading />

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!formData.ticker || !formData.shares || !formData.costBasis) {
      alert('Please fill in all required fields')
      return
    }
    const shares = parseFloat(formData.shares)
    const costBasis = perShareCost(formData.costBasis, shares, formData.costMode)
    if (!Number.isFinite(costBasis) || costBasis <= 0) {
      alert('Enter a valid share count and cost')
      return
    }
    const result = await addPosition(formData.ticker, shares, costBasis, formData.purchaseDate, formData.costMode)
    if (result?.success === false) {
      setSyncMessage(`Could not sync position: ${result.error}`)
      return
    }
    setSyncMessage(`${formData.ticker} saved to your cloud portfolio.`)
    setFormData({ ticker: '', shares: '', costBasis: '', costMode: 'share', purchaseDate: new Date().toISOString().split('T')[0] })
    setShowAddForm(false)
  }

  const handleReferenceSync = async () => {
    setSyncMessage('Syncing…')
    const result = await syncReferencePortfolio()
    setSyncMessage(result.success
      ? `${result.added} added · ${result.updated} updated · ${result.removed} removed from the Aug 14 Fidelity baseline`
      : `Sync failed: ${result.error}`)
  }

  const handlePurchaseDateChange = async (positionId, purchaseDate) => {
    const result = await updatePosition(positionId, { purchaseDate })
    setSyncMessage(result?.success ? 'Purchase date saved' : `Could not save date: ${result?.error || 'Unknown error'}`)
  }

  const handleRemove = async (positionId) => {
    if (removingId) return
    setRemovingId(positionId)
    const result = await removePosition(positionId)
    setRemovingId(null)
    if (result?.success === false) {
      setSyncMessage(`Could not remove position: ${result.error || 'Unknown error'}`)
    } else setSyncMessage('Position removed from the cloud portfolio on every connected device.')
  }

  const startSell = (pos) => {
    setSellingId(pos.id)
    setSellForm({ shares: String(pos.shares ?? ''), price: pos.currentPrice != null ? String(pos.currentPrice) : '', saleDate: new Date().toISOString().split('T')[0] })
  }

  const cancelSell = () => {
    setSellingId(null)
    setSellForm({ shares: '', price: '', saleDate: new Date().toISOString().split('T')[0] })
  }

  // Selling adjusts (or removes) the position and records only the realized result. Proceeds
  // are not tracked as a cash balance; charts continue to reprice the remaining holdings only.
  const saveSell = async (pos) => {
    const sharesSold = parseFloat(sellForm.shares)
    const price = parseFloat(sellForm.price)
    if (!Number.isFinite(sharesSold) || sharesSold <= 0 || sharesSold > pos.shares || !Number.isFinite(price) || price <= 0 || !sellForm.saleDate) {
      setSyncMessage('Enter a valid share count (up to what you hold), sale price, and date')
      return
    }
    setSellSaving(true)
    const proceeds = sharesSold * price
    const realizedGain = proceeds - sharesSold * pos.costBasis
    const remainingShares = pos.shares - sharesSold
    const positionResult = remainingShares > 0.0000001
      ? await updatePosition(pos.id, { shares: remainingShares })
      : await removePosition(pos.id)
    if (positionResult?.success === false) {
      setSellSaving(false)
      setSyncMessage(`Could not save sale: ${positionResult.error || 'Unknown error'}`)
      return
    }
    await tracking.recordActivity({ type: 'realized_gain', amount: realizedGain, effectiveDate: sellForm.saleDate, note: `${pos.ticker} sale` })
    setSellSaving(false)
    cancelSell()
    setSyncMessage(`Sold ${sharesSold} ${pos.ticker} share${sharesSold === 1 ? '' : 's'} at $${price.toFixed(2)} · ${realizedGain >= 0 ? '+' : '−'}$${Math.abs(realizedGain).toFixed(2)} realized.`)
  }

  const startEdit = (pos) => {
    const costMode = pos.costBasisInputMode === 'total' ? 'total' : 'share'
    setEditingId(pos.id)
    setEditForm({
      shares: String(pos.shares ?? ''),
      costBasis: String(costMode === 'total' ? pos.shares * pos.costBasis : pos.costBasis ?? ''),
      costMode,
      purchaseDate: pos.purchaseDate || '',
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setEditForm({ shares: '', costBasis: '', costMode: 'share', purchaseDate: '' })
  }

  const saveEdit = async (positionId) => {
    const shares = parseFloat(editForm.shares)
    const costBasis = perShareCost(editForm.costBasis, shares, editForm.costMode)
    if (!Number.isFinite(shares) || shares <= 0 || !Number.isFinite(costBasis) || costBasis <= 0) {
      setSyncMessage('Shares and cost basis must be positive numbers')
      return
    }
    setEditSaving(true)
    const result = await updatePosition(positionId, {
      shares,
      costBasis,
      costBasisUnit: 'per_share',
      costBasisInputMode: editForm.costMode,
      purchaseDate: editForm.purchaseDate,
    })
    setEditSaving(false)
    if (result?.success === false) {
      setSyncMessage(`Could not save changes: ${result.error || 'Unknown error'}`)
      return
    }
    setSyncMessage('Position updated')
    cancelEdit()
  }

  const pageCopy = PORTFOLIO_PAGE_COPY[view] || PORTFOLIO_PAGE_COPY.summary

  return (
    <>
      <PullToRefreshIndicator pullDistance={pullToRefresh.pullDistance} armed={pullToRefresh.armed} refreshing={portfolioQuotes.refreshing} />
      <StockTickerTape positions={portfolioPositions} />
      <div className="page-head">
        <div>
          <span className="eyebrow">Your money</span>
          <h1 className="page-title">{pageCopy.title}</h1>
          <p className="page-sub">{pageCopy.description}</p>
        </div>
        <div className={`cloud-sync-state ${syncState.connected ? 'connected' : 'disconnected'}`} role="status">
          <span aria-hidden="true" />
          <div><strong>{syncState.connected ? 'Firebase live sync on' : 'Firebase sync unavailable'}</strong><small>{syncState.connected ? `${currentUser?.email || 'Solo workspace'} · devices update automatically${syncState.lastSyncedAt ? ` · ${new Date(syncState.lastSyncedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : ''}` : syncState.error || 'Connecting your solo cloud workspace'}</small></div>
        </div>
      </div>
      {view === 'summary' && actionable.length > 0 && <a className="portfolio-sell-alert" href="#sell-signals"><Icon name="bell" size={17} /><span><strong>{actionable.length} sell signal{actionable.length === 1 ? '' : 's'} need review</strong><small>{actionable.map((position) => position.ticker).join(', ')} · Hold positions are not shown here.</small></span><Icon name="chevron" size={16} /></a>}
      {syncMessage && <div className="sync-message" role="status">{syncMessage}</div>}
      {(portfolioQuotes.message || portfolioQuotes.error) && (
        <div className={`sync-message refresh-message ${portfolioQuotes.error ? 'error' : 'success'}`} role="status" aria-live="polite">
          {portfolioQuotes.error || portfolioQuotes.message}
        </div>
      )}
      <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
        percent={refresh.progress} stage={refresh.stage} />
      {refresh.message && (
        <div className={`sync-message refresh-message ${refresh.status}`} role="status" aria-live="polite">
          {refresh.message}
        </div>
      )}

      <div className="portfolio-sticky-tools">
        <PortfolioNavigation />
        <div className="portfolio-sticky-actions">
          <button className="primary-button compact portfolio-sticky-refresh" onClick={portfolioQuotes.requestRefresh} disabled={portfolioQuotes.refreshing || positions.length === 0}>
            <Icon name="sync" size={16} className={portfolioQuotes.refreshing ? 'refresh-spin' : ''} />
            <span>{portfolioQuotes.refreshing ? 'Updating…' : 'Refresh prices'}</span>
          </button>
          <details className="portfolio-data-menu">
            <summary><span>Data actions</span><Icon name="chevron" size={15} aria-hidden="true" /></summary>
            <div className="portfolio-data-popover">
              <div className="portfolio-data-status">
                <span className="eyebrow">Portfolio prices</span>
                <time dateTime={pricesUpdatedAt || undefined}>{pricesUpdatedAt ? `Updated ${new Date(pricesUpdatedAt).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'Not updated yet'}</time>
              </div>
              <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}><Icon name="sync" size={17} className={refresh.refreshing && refresh.activeMode === 'data' ? 'refresh-spin' : ''} />{refresh.refreshing && refresh.activeMode === 'data' ? 'Refreshing all data…' : 'Refresh all research'}</button>
              <button className="secondary-button" onClick={refresh.requestReanalyze} disabled={refresh.refreshing}><Icon name="research" size={17} className={refresh.refreshing && refresh.activeMode === 'rescore' ? 'refresh-spin' : ''} />{refresh.refreshing && refresh.activeMode === 'rescore' ? 'Reanalyzing…' : 'Reanalyze portfolio'}</button>
              <button className="secondary-button" onClick={handleReferenceSync}>Reapply Aug 14 Fidelity snapshot</button>
              <button className="secondary-button" onClick={exportPortfolio}><Icon name="download" size={17} />Export portfolio</button>
            </div>
          </details>
        </div>
      </div>

      {view === 'summary' && <section className="portfolio-page-section" aria-labelledby="portfolio-summary-title">
      <div className="portfolio-dashboard-section portfolio-summary-section">
        <header className="portfolio-section-heading">
          <div><span className="portfolio-section-number">01</span><div><span className="eyebrow">Overview</span><h2 id="portfolio-summary-title">Summary</h2></div></div>
          <label><span>Time range</span><select value={summaryPeriod} onChange={(event) => setSummaryPeriod(event.target.value)}>{SUMMARY_PERIODS.map((period) => <option key={period} value={period}>{PERIOD_NAMES[period]}</option>)}</select></label>
        </header>
        <div className="portfolio-summary-kpis">
          <span><small>Invested value{portfolioQuotes.refreshing && <Icon name="sync" size={12} className="refresh-spin hero-value-spinner" aria-hidden="true" />}</small><strong>{portfolioStats.totalValue == null ? '–' : <AnimatedNumber value={portfolioStats.totalValue} format={(value) => money(value, 2)} />}</strong></span>
          <span><small>Today · regular session</small><strong className={todayMove?.dollarReturn >= 0 ? 'positive' : 'negative'}>{todayMove?.dollarReturn == null ? 'Unavailable' : `${todayMove.dollarReturn >= 0 ? '+' : '−'}${money(Math.abs(todayMove.dollarReturn), 2)} · ${signedPct(todayMove.returnPct, 2)}`}</strong></span>
          <span><small>Total profit · {PERIOD_NAMES[summaryPeriod]}</small><strong className={summaryProfit >= 0 ? 'positive' : 'negative'}>{summaryProfit == null ? 'Unavailable' : `${summaryProfit >= 0 ? '+' : '−'}${money(Math.abs(summaryProfit), 2)} · ${signedPct(summaryReturnPct, 2)}`}</strong></span>
        </div>
        {summaryChart ? <GrowthChart
          className="portfolio-summary-chart"
          height={390}
          width={1080}
          dates={summaryChart.dates}
          series={[{ label: 'Current holdings', values: summaryChart.values, color: 'var(--series-stock)', emphasis: true }]}
          valueFormatter={(value) => money(value, 2)}
          caption={summaryChart.methodology || 'Current quantities applied to historical prices; only invested holdings are included.'}
          lineStyle="line"
        /> : <div className="unavailable-panel"><strong>{PERIOD_NAMES[summaryPeriod]} history is still building</strong><p>Two five-minute account observations are needed to draw this range.</p></div>}
      </div>

      <section className="portfolio-holdings-section" aria-labelledby="portfolio-holdings-title">
        <header className="portfolio-subsection-heading">
          <div><span className="eyebrow">Your positions</span><h3 id="portfolio-holdings-title">All holdings</h3></div>
          <div className="portfolio-holdings-heading-actions">
            <span>{positions.length} holding{positions.length === 1 ? '' : 's'}</span>
            <label className="portfolio-essential-control">
              <span><strong>Essential only</strong><small>{essentialOnly ? 'Extra details hidden' : 'All details shown'}</small></span>
              <span className="switch">
                <input type="checkbox" checked={essentialOnly} onChange={(event) => setEssentialOnly(event.target.checked)} />
                <span aria-hidden="true" />
              </span>
            </label>
          </div>
        </header>

      <div className="filters" style={{ marginBottom: 20 }}>
        <button className={`tab ${viewMode === 'holdings' ? 'active' : ''}`} onClick={() => setViewMode('holdings')}>
          My Holdings
        </button>
        <button className={`tab ${viewMode === 'benchmark' ? 'active' : ''}`} onClick={() => setViewMode('benchmark')}>
          Vs S&P 500
        </button>
        <button className={`tab ${viewMode === 'hypothetical' ? 'active' : ''}`} onClick={() => setViewMode('hypothetical')}>
          ${basis} Calculator
        </button>
        <button className="tab active" onClick={() => setShowAddForm(!showAddForm)} style={{ marginLeft: 'auto' }}>
          + Add Position
        </button>
      </div>

      {showAddForm && (
        <div className="card" style={{ marginBottom: 20, padding: 20 }}>
          <h3 style={{ marginBottom: 16 }}>Add New Position</h3>
          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr) auto', gap: 12, alignItems: 'end' }}>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Ticker</label>
              <input type="text" placeholder="AAPL" value={formData.ticker} required
                onChange={(e) => setFormData({ ...formData, ticker: e.target.value.toUpperCase() })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Shares</label>
              <input type="number" step="0.001" placeholder="10" value={formData.shares} required
                onChange={(e) => setFormData({ ...formData, shares: e.target.value })} />
            </div>
            <div>
              <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 6, marginBottom: 4, fontSize: 13 }}>
                <span>Cost basis</span>
                <select value={formData.costMode} onChange={(e) => setFormData({ ...formData, costMode: e.target.value })}
                  style={{ minHeight: 'auto', height: 20, padding: '0 2px', border: 0, background: 'transparent', color: 'var(--text-faint)', fontSize: 10 }}>
                  <option value="share">$/share</option>
                  <option value="total">Total $</option>
                </select>
              </label>
              <input type="number" step="0.01" placeholder={formData.costMode === 'total' ? '200.00' : '150.00'}
                value={formData.costBasis} required
                onChange={(e) => setFormData({ ...formData, costBasis: e.target.value })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Purchase Date</label>
              <input type="date" value={formData.purchaseDate} required
                onChange={(e) => setFormData({ ...formData, purchaseDate: e.target.value })} />
            </div>
            <div><button type="submit" className="tab active">Add</button></div>
          </form>
        </div>
      )}

      {viewMode === 'holdings' && (
        <>
        <PortfolioSortToolbar
          sort={portfolioSort}
          selectedLabel={selectedSort?.label}
          onSortKey={setSortKey}
          onToggleDirection={toggleSortDirection}
        />
        <div className={`portfolio-mobile-list portfolio-stock-grid ${essentialOnly ? 'essential' : 'expanded'}`}>
          {sortedPositions.map((pos) => (
            <article className={`portfolio-stock-tile ${pos.dayMove?.pct == null ? 'tone-flat' : pos.dayMove.pct >= 0 ? 'tone-up' : 'tone-down'}`} key={pos.id || pos.ticker}>
              <button type="button" className="portfolio-stock-primary" onClick={() => pos.priceInfo && setSelectedStock(pos)} disabled={!pos.priceInfo}
                aria-label={`${pos.ticker}, ${signedPct(pos.dayMove?.pct, 2)} today, ${pos.currentPrice == null ? 'price unavailable' : `${money(pos.currentPrice, 2)} per share`}${pos.priceInfo ? '. Open research' : ''}`}>
                <span className="portfolio-stock-identity">
                  <CompanyLogo company={pos.priceInfo || pos} size={26} />
                  <span><strong>{pos.ticker}</strong><small title={pos.priceInfo?.name || 'Coverage pending'}>{pos.priceInfo?.name || 'Coverage pending'}</small></span>
                </span>
                <span className="portfolio-stock-move">
                  <strong><span aria-hidden="true">{pos.dayMove?.pct == null ? '•' : pos.dayMove.pct >= 0 ? '▲' : '▼'}</span>{signedPct(pos.dayMove?.pct, 2)}</strong>
                  <small>{pos.currentPrice == null ? 'Price pending' : money(pos.currentPrice, 2)}</small>
                </span>
              </button>

              {!essentialOnly && <div className="portfolio-stock-details">
                <div className="portfolio-stock-allocation">{pos.allocationPct == null ? 'Allocation unavailable' : `${pos.allocationPct.toFixed(1)}% of portfolio`}</div>
                <div className="holding-value">
                  <div><span>Current price</span><strong>{pos.currentPrice == null ? 'Unavailable' : money(pos.currentPrice, 2)}</strong></div>
                  <div><span>Position value</span><strong>{pos.currentValue == null ? 'Unavailable' : money(pos.currentValue)}</strong></div>
                </div>
                <div className="holding-block-status"><ActionPill recommendation={pos.recommendation} /><RatingBadge value={pos.rating} title="-5 (worst) to +5 (best) vs. its research pool" /><span>{signedPct(pos.gainPct)} total return</span></div>
                <small className="as-of-line">As of {pos.priceInfo?.history?.dates?.at(-1) || pos.priceInfo?.data_as_of || 'the latest available close'}</small>
                {editingId === pos.id ? (
                  <MobileSheet open title={`Edit ${pos.ticker}`} onClose={cancelEdit} className="holding-edit-sheet"><div className="holding-edit-form">
                    <label><span>Shares</span>
                      <input className="inline-edit-input" type="number" step="0.001" min="0" value={editForm.shares}
                        onChange={(e) => setEditForm({ ...editForm, shares: e.target.value })} />
                    </label>
                    <label>
                      <span style={{ display: 'flex', justifyContent: 'space-between' }}>
                        Cost basis
                        <select value={editForm.costMode} onChange={(e) => setEditForm({ ...editForm, costMode: e.target.value })}
                          style={{ minHeight: 'auto', height: 18, padding: '0 2px', border: 0, background: 'transparent', color: 'var(--text-faint)', fontSize: 9, textTransform: 'none', letterSpacing: 0 }}>
                          <option value="share">$/share</option>
                          <option value="total">Total $</option>
                        </select>
                      </span>
                      <input className="inline-edit-input" type="number" step="0.01" min="0" value={editForm.costBasis}
                        onChange={(e) => setEditForm({ ...editForm, costBasis: e.target.value })} />
                    </label>
                    <label><span>Purchase date</span>
                      <input className="inline-edit-input" type="date" value={editForm.purchaseDate}
                        onChange={(e) => setEditForm({ ...editForm, purchaseDate: e.target.value })} />
                    </label>
                  </div><div className="holding-edit-sheet-actions"><button className="secondary-button" onClick={cancelEdit} disabled={editSaving}>Cancel</button><button className="primary-button" onClick={() => saveEdit(pos.id)} disabled={editSaving}>{editSaving ? 'Saving…' : 'Save changes'}</button></div></MobileSheet>
                ) : (
                  <div className="holding-meta">
                    <span>{pos.shares} shares</span><span>Avg. cost/share {money(pos.costBasis, 2)}</span>
                    <span>{pos.quoteSource || 'Live quote unavailable'}</span>
                    <StopLossNote stopLoss={pos.stopLoss} />
                  </div>
                )}
                {editingId !== pos.id && sellingId !== pos.id && pos.trendValues.length > 1 && (
                  <div className="holding-trend">
                    <div><span>1-month trend
                      <InfoTag label="1-month trend">
                        <strong>1-month trend</strong>
                        <p>Trailing 30-day price movement for this holding - direction and shape only,
                          not a substitute for the full research score.</p>
                      </InfoTag>
                    </span><Move value={pos.trendPct} /></div>
                    <Sparkline values={pos.trendValues} label={`${pos.ticker} one-month price trend`} height={48} />
                  </div>
                )}
                <div className="holding-actions">
                  {editingId !== pos.id && sellingId !== pos.id && (
                    <>
                      {pos.priceInfo && <button className="secondary-button" onClick={() => setSelectedStock(pos)}>Research</button>}
                      <button className="text-button" onClick={() => startEdit(pos)}>Edit</button>
                      <button className="text-button" onClick={() => startSell(pos)}>Sell</button>
                      <button className="text-button danger" onClick={() => handleRemove(pos.id)} disabled={removingId === pos.id}>
                        {removingId === pos.id ? 'Removing…' : 'Remove'}
                      </button>
                    </>
                  )}
                </div>
              </div>}
            </article>
          ))}
          {sortedPositions.length === 0 && <div className="portfolio-holdings-empty">No positions yet. Add a position to start tracking.</div>}
        </div>
        {sellingPosition && (
          <MobileSheet open title={`Sell ${sellingPosition.ticker}`} onClose={cancelSell} className="holding-edit-sheet">
            <div className="holding-edit-form">
              <label><span>Shares to sell (of {sellingPosition.shares})</span>
                <input className="inline-edit-input" type="number" step="0.001" min="0" max={sellingPosition.shares} value={sellForm.shares}
                  onChange={(e) => setSellForm({ ...sellForm, shares: e.target.value })} />
              </label>
              <label><span>Sale price/share</span>
                <input className="inline-edit-input" type="number" step="0.01" min="0" value={sellForm.price}
                  onChange={(e) => setSellForm({ ...sellForm, price: e.target.value })} />
              </label>
              <label><span>Sale date</span>
                <input className="inline-edit-input" type="date" value={sellForm.saleDate}
                  onChange={(e) => setSellForm({ ...sellForm, saleDate: e.target.value })} />
              </label>
            </div>
            <div className="holding-edit-sheet-actions">
              <button className="secondary-button" onClick={cancelSell} disabled={sellSaving}>Cancel</button>
              <button className="primary-button" onClick={() => saveSell(sellingPosition)} disabled={sellSaving}>{sellSaving ? 'Selling…' : 'Confirm sale'}</button>
            </div>
          </MobileSheet>
        )}
        </>
      )}

      {viewMode === 'benchmark' && (
        <>
        <PortfolioSortToolbar
          sort={portfolioSort}
          selectedLabel={selectedSort?.label}
          onSortKey={setSortKey}
          onToggleDirection={toggleSortDirection}
        />
        <div className="card card-pad table-wrap">
          <div className="callout" style={{ margin: '0 0 16px' }}>
            <strong>The only fair comparison:</strong> what each position is worth now against
            what the identical dollars, invested on the identical day, would be worth in the S&P 500.
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th className="num">Purchased</th><th className="num">Invested</th>
                <th className="num">Now</th><th className="num">Return</th>
                <th className="num">S&P instead</th><th className="num">S&P return</th>
                <th className="num">Dollars ahead</th>
              </tr>
            </thead>
            <tbody>
              {sortedPositions.map((pos) => (
                <tr key={pos.id || pos.ticker}>
                  <td className="mono">{pos.ticker}</td>
                  <td className="mono num">
                    <input
                      className="portfolio-date-input"
                      type="date"
                      value={pos.purchaseDate || ''}
                      aria-label={`${pos.ticker} purchase date`}
                      onChange={(event) => handlePurchaseDateChange(pos.id, event.target.value)}
                    />
                  </td>
                  <td className="mono num">{money(pos.totalCost)}</td>
                  <td className="mono num">{money(pos.currentValue)}</td>
                  <td className="num"><Move value={pos.gainPct} /></td>
                  <td className="mono num">{pos.versusBenchmark ? money(pos.versusBenchmark.value) : '–'}</td>
                  <td className="num">
                    {pos.versusBenchmark ? <Move value={pos.versusBenchmark.gainPct} /> : <span className="mono">–</span>}
                  </td>
                  <td className="mono num" style={{ color: moveColor(pos.versusBenchmark ? pos.currentValue - pos.versusBenchmark.value : null) }}>
                    {pos.versusBenchmark
                      ? `${pos.currentValue - pos.versusBenchmark.value >= 0 ? '+' : '−'}${money(Math.abs(pos.currentValue - pos.versusBenchmark.value))}`
                      : '–'}
                  </td>
                </tr>
              ))}
              {versusIndex && (
                <tr style={{ fontWeight: 600 }}>
                  <td className="mono">TOTAL</td>
                  <td className="num">–</td>
                  <td className="mono num">{money(versusIndex.invested)}</td>
                  <td className="mono num">{money(versusIndex.holdingsValue)}</td>
                  <td className="num"><Move value={versusIndex.holdingsReturnPct} /></td>
                  <td className="mono num">{money(versusIndex.benchmarkValue)}</td>
                  <td className="num"><Move value={versusIndex.benchmarkReturnPct} /></td>
                  <td className="mono num" style={{ color: moveColor(versusIndex.dollarsAhead) }}>
                    {versusIndex.dollarsAhead >= 0 ? '+' : '−'}{money(Math.abs(versusIndex.dollarsAhead))}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 12 }}>
            Add or correct a purchase date above to calculate the same-day comparison. Positions
            bought before the published benchmark window show “–” rather than being compared
            against the wrong entry price.
          </p>
        </div>
        </>
      )}

      {viewMode === 'hypothetical' && (
        <>
        <PortfolioSortToolbar
          sort={portfolioSort}
          selectedLabel={selectedSort?.label}
          onSortKey={setSortKey}
          onToggleDirection={toggleSortDirection}
        />
        <div className="card card-pad table-wrap">
          <div className="callout" style={{ margin: '0 0 16px' }}>
            <strong>${basis} calculator:</strong> what ${basis} would be worth today if it went into
            each position on the day you actually bought it, against the same ${basis} in the
            S&amp;P 500 from that same day. Not what you actually invested – same fair, same-day
            comparison as "Vs S&amp;P 500", just a flat ${basis} everywhere.
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th className="num">Purchased</th><th className="num">${basis} invested</th>
                <th className="num">Now</th><th className="num">Return</th>
                <th className="num">S&P instead</th><th className="num">S&P return</th>
                <th className="num">Dollars ahead</th>
              </tr>
            </thead>
            <tbody>
              {sortedPositions.map((pos) => {
                const calc = fixedBasisAlternative(pos, pos.priceInfo?.history, benchmarkHistory, basis)
                return (
                  <tr key={pos.id || pos.ticker}>
                    <td className="mono">{pos.ticker}</td>
                    <td className="mono num">
                      <input
                        className="portfolio-date-input"
                        type="date"
                        value={pos.purchaseDate || ''}
                        aria-label={`${pos.ticker} purchase date`}
                        onChange={(event) => handlePurchaseDateChange(pos.id, event.target.value)}
                      />
                    </td>
                    <td className="mono num">{money(basis)}</td>
                    <td className="mono num">{calc ? money(calc.stockValue) : '–'}</td>
                    <td className="num">
                      {calc ? <Move value={calc.stockReturnPct} /> : <span className="mono">–</span>}
                    </td>
                    <td className="mono num">{calc ? money(calc.benchmarkValue) : '–'}</td>
                    <td className="num">
                      {calc ? <Move value={calc.benchmarkReturnPct} /> : <span className="mono">–</span>}
                    </td>
                    <td className="mono num" style={{ color: moveColor(calc?.dollarsAhead) }}>
                      {calc
                        ? `${calc.dollarsAhead >= 0 ? '+' : '−'}${money(Math.abs(calc.dollarsAhead))}`
                        : '–'}
                    </td>
                  </tr>
                )
              })}
              {fixedBasisTotal && (
                <tr style={{ fontWeight: 600 }}>
                  <td className="mono">TOTAL</td>
                  <td className="num">–</td>
                  <td className="mono num">{money(fixedBasisTotal.invested)}</td>
                  <td className="mono num">{money(fixedBasisTotal.stockValue)}</td>
                  <td className="num"><Move value={fixedBasisTotal.stockReturnPct} /></td>
                  <td className="mono num">{money(fixedBasisTotal.benchmarkValue)}</td>
                  <td className="num"><Move value={fixedBasisTotal.benchmarkReturnPct} /></td>
                  <td className="mono num" style={{ color: moveColor(fixedBasisTotal.dollarsAhead) }}>
                    {fixedBasisTotal.dollarsAhead >= 0 ? '+' : '−'}{money(Math.abs(fixedBasisTotal.dollarsAhead))}
                  </td>
                </tr>
              )}
              {portfolioStats.positions.length === 0 && (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>
                    No positions yet. Click "+ Add Position" to start tracking.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <p style={{ color: 'var(--text-faint)', fontSize: 12, marginTop: 12 }}>
            Add or correct a purchase date above to calculate the same-day comparison. Positions
            bought before the published benchmark window show “–” rather than being compared
            against the wrong entry price.
          </p>
        </div>
        </>
      )}
      </section>

      <details id="sell-signals" className="card card-pad suggested-actions" open={suggestedActionsOpen} onToggle={(event) => setSuggestedActionsOpen(event.currentTarget.open)}>
          <summary><span><span className="sec-label">Suggested actions</span><strong>{actionable.length} holding{actionable.length === 1 ? '' : 's'} to review</strong></span><Icon name="chevron" /></summary>
          <div className="portfolio-suggested-list">
            {actionable.length ? actionable.map((pos) => (
              <div className="portfolio-suggested-row" key={pos.id || pos.ticker}>
                <ActionPill recommendation={pos.recommendation} />
                <b className="mono">{pos.ticker}</b>
                <span>{pos.recommendation.summary}</span>
                {pos.recommendation.suggestedTrimPct > 0 && (
                  <small className="mono">
                    {((pos.shares * pos.recommendation.suggestedTrimPct) / 100).toFixed(2)} of {pos.shares} shares
                    {' '}≈ {money((pos.currentValue * pos.recommendation.suggestedTrimPct) / 100)}
                  </small>
                )}
                <button className="chip button-chip" onClick={() => setSelectedStock(pos)}>Why</button>
              </div>
            )) : <p className="portfolio-suggested-empty">No sell actions need review. Your current hold guidance remains visible on each position.</p>}
          </div>
        </details>

      {exposure.warnings.length > 0 && (
        <div className="card card-pad portfolio-concentration-card">
          <div className="sec-label">Concentration risk</div>
          <div className="portfolio-concentration-list">
            {exposure.warnings.map((warning) => (
              <div key={`${warning.type}-${warning.label}`}>
                <span className="mono">{warning.pct.toFixed(1)}%</span>
                <span>{warning.message}</span>
              </div>
            ))}
          </div>
          <p>
            Illustrative guidelines only ({exposure.maxPositionPct}% per position, {exposure.maxSectorPct}% per
            sector) – not a rule to force a sale, but a prompt to size new buys and rebalancing with the
            concentration you already carry in mind.
          </p>
        </div>
      )}

      <section className="portfolio-dashboard-section portfolio-allocation-section" aria-labelledby="portfolio-allocation-title">
        <header className="portfolio-subsection-heading">
          <div><span className="eyebrow">Portfolio mix</span><h3 id="portfolio-allocation-title">Allocation</h3></div>
          <span>Assets and sectors</span>
        </header>
        <div className="portfolio-allocation-grid">
          <article className="portfolio-allocation-card">
            <header><div><span className="eyebrow">By role</span><h3>Asset allocation</h3></div><small>Current market value</small></header>
            <div className="portfolio-asset-bars">{assetAllocation.map((item) => <div key={item.label}>
              <div><span>{item.label}</span><strong>{item.pct.toFixed(1)}%</strong></div>
              <i aria-hidden="true"><span style={{ width: `${item.pct}%` }} /></i>
              <small>{money(item.value, 2)}</small>
            </div>)}</div>
            <p>Stocks with an active, evidence-backed catalyst are short-term; other stocks are long-term. ETFs remain separate.</p>
          </article>
          <article className="portfolio-allocation-card portfolio-sector-card">
            <header><div><span className="eyebrow">By exposure</span><h3>Sector allocation</h3></div><small>ETF look-through where available</small></header>
            {sectorAllocation.length ? <AllocationDonut sectors={sectorAllocation} totalLabel={money(portfolioStats.totalValue)} /> : <div className="unavailable-panel"><strong>Sector data unavailable</strong><p>Priced holdings with sector coverage will appear here.</p></div>}
          </article>
        </div>
      </section>
      </section>}

      {view === 'performance' && <section className="portfolio-dashboard-section portfolio-performance-section" aria-labelledby="portfolio-performance-title">
        <header className="portfolio-section-heading">
          <div><span className="portfolio-section-number">02</span><div><span className="eyebrow">Benchmark</span><h2 id="portfolio-performance-title">Performance</h2></div></div>
          <label><span>Compare over</span><select value={performancePeriod} onChange={(event) => setPerformancePeriod(event.target.value)}>{PERFORMANCE_PERIODS.map((period) => <option key={period} value={period}>{PERIOD_NAMES[period]}</option>)}</select></label>
        </header>
        {performanceIndex ? <div className="portfolio-benchmark-chart">
          <div className="portfolio-benchmark-kpis">
            <span><small>Time-weighted return</small><strong className={visiblePerformanceComparison.portfolio.returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(visiblePerformanceComparison.portfolio.returnPct, 2)}</strong></span>
            <span><small>{selectedBenchmarkLabel}</small><strong className={visiblePerformanceComparison.benchmarks[0].returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(visiblePerformanceComparison.benchmarks[0].returnPct, 2)}</strong></span>
            <span><small>Difference</small><strong className={visiblePerformanceComparison.portfolio.returnPct - visiblePerformanceComparison.benchmarks[0].returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(visiblePerformanceComparison.portfolio.returnPct - visiblePerformanceComparison.benchmarks[0].returnPct, 2)}</strong></span>
          </div>
          <GrowthChart
            height={330}
            width={1080}
            dates={performanceIndex.dates}
            series={[
              { label: 'Portfolio TWR', values: performanceIndex.portfolio, color: 'var(--series-stock)', emphasis: true },
              { label: selectedBenchmarkLabel, values: performanceIndex.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
            ]}
            valueFormatter={(value) => signedPct(value - 100, 1)}
            caption={`Both lines start at 0% on the same market date. Your line reprices today's exact shares at matched historical closes, so cash transfers cannot affect it; ${selectedBenchmarkLabel} uses the same dates.`}
            lineStyle="line"
          />
        </div> : <div className="unavailable-panel"><strong>Comparison history is still building</strong><p>Two shared market dates are needed to compare your current holdings with {selectedBenchmarkLabel}.</p></div>}

        {growth && (
          <details className="card portfolio-comparison">
            <summary>
              <div>
                <span className="eyebrow">Opportunity cost</span>
                <strong>What if I chose the S&amp;P 500–or did not invest?</strong>
                <small>Same cost-basis dollars on your recorded purchase dates</small>
              </div>
              <div className="comparison-summary-side">
                {versusIndex && <span className="comparison-edge" style={{ color: moveColor(versusIndex.excessReturnPct) }}>{signedPct(versusIndex.excessReturnPct)} vs S&amp;P</span>}
                <span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span>
              </div>
            </summary>
            <div className="portfolio-comparison-chart">
              <GrowthChart
                dates={growth.dates}
                series={[
                  { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
                  { label: 'S&P 500, same cost basis', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
                  { label: 'Cost basis held flat', values: growth.cash, color: 'var(--series-cash)', dashPattern: '2 5' },
                ]}
                title="One-to-one performance from your investment dates"
                caption={`Each holding starts with its exact cost-basis dollars on its recorded purchase date, then follows that stock’s price return. The S&P receives the identical starting dollars on the identical date; the flat line leaves that cost basis unchanged. Covers ${growth.trackedTickers.length} dated position${growth.trackedTickers.length === 1 ? '' : 's'} from ${growth.firstInvestmentDate}${growth.untrackedCount ? `. ${growth.untrackedCount} missing a usable date or published history` : ''}.`}
                zoomable
              />
            </div>
          </details>
        )}
      </section>}

      {view === 'data' && <section className="portfolio-dashboard-section portfolio-data-overview-section" aria-labelledby="portfolio-data-overview-title">
        <header className="portfolio-section-heading">
          <div><span className="portfolio-section-number">03</span><div><span className="eyebrow">Evidence</span><h2 id="portfolio-data-overview-title">Data overview</h2></div></div>
        </header>
        <PortfolioMoveExplanation
          attribution={moveExplanation}
          benchmarkLabel="S&P 500"
          period={attributionPeriod}
          onPeriodChange={setAttributionPeriod}
        />
        <PerformanceMetrics metrics={scorePerformance} benchmarkLabel={selectedBenchmarkLabel} riskFree={riskFree}
          acceleration={scoreAcceleration} capture={scoreCapture} batting={scoreBatting} underwater={scoreUnderwater}
          shortTerm={scoreShortTerm} risk={scoreRisk} model={scoreMetricModel} statistics={scoreStatistics}
          factor={scoreFactor} benchmark={scoreBenchmarkFit} exposure={scoreExposure} execution={scoreExecution}
          robustness={scoreRobustness} signalMetrics={signalMetrics} prospective={prospectiveValidation}
          baselineComparison={algorithmBaseline}
          scopes={ANALYTICS_SCOPES} scope={analyticsScope} onScopeChange={(next) => {
            setAnalyticsScope(next)
            try { globalThis.sessionStorage?.setItem('valuesignal.analytics.scope', next) } catch { /* optional session persistence */ }
          }} />
      </section>}

      {selectedStock && (
        <StockDetailModal
          stock={selectedStock.priceInfo || selectedStock}
          recommendationOverride={selectedStock.recommendation}
          stopLoss={selectedStock.stopLoss}
          position={selectedStock.shares
            ? { shares: selectedStock.shares, price: selectedStock.currentPrice, purchaseDate: selectedStock.purchaseDate }
            : null}
          benchmarkHistory={benchmarkHistory}
          onClose={() => setSelectedStock(null)}
        />
      )}
    </>
  )
}
