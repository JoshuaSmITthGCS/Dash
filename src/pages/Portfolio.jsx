import { useEffect, useRef, useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useAuth } from '../lib/FirebaseAuthContext'
import { Loading, RefreshProgress } from '../components/Bits'
import { ActionPill } from '../components/ActionGuidance'
import GrowthChart from '../components/GrowthChart'
import Sparkline from '../components/Sparkline'
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
} from '../lib/portfolioPerformance'
import Icon from '../components/Icons'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh'
import {
  nextPortfolioSort,
  PORTFOLIO_SORT_OPTIONS,
  sortPortfolioPositions,
} from '../lib/portfolioSort'
import { buildPortfolioPriceData, mergePortfolioQuotes } from '../lib/portfolioPosition'
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
  concentrationLiquidityScore,
  contributionAdjustedPerformance,
  currentHoldingsSeries,
  diversificationScore,
  performanceMetrics,
  portfolioReturnSummary,
  portfolioScore,
  resilienceIndex,
  riskFreeAnnualRate,
  selectPeriod,
} from '../lib/portfolioAnalytics.js'
import { FIDELITY_CASH_FLOWS, FIDELITY_REFERENCE_SNAPSHOT, summarizeCashFlows } from '../lib/referenceCashFlows.js'
import PortfolioReturnSummary from '../components/PortfolioReturnSummary.jsx'
import PerformanceMetrics from '../components/PerformanceMetrics.jsx'
import { MobileSheet, ResponsiveControlPanel } from '../components/MobileSheet.jsx'

const money = (value, digits = 0) =>
  value == null ? '–' : `$${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`

const signedPct = (value, digits = 1) =>
  value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`

const moveColor = (value) => (value == null ? undefined : value >= 0 ? 'var(--pos)' : 'var(--neg)')

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

function SortableHeader({ sortKey, sort, onSort, children, numeric = false }) {
  const active = sort.key === sortKey
  return (
    <th
      scope="col"
      className={numeric ? 'num' : undefined}
      aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <button
        className={`sort-header ${active ? 'active' : ''}`}
        onClick={() => onSort(sortKey)}
      >
        {children}
        <span className="sort-arrows" aria-hidden="true">
          <i className={`sort-arrow up ${active && sort.direction === 'asc' ? 'selected' : ''}`} />
          <i className={`sort-arrow down ${active && sort.direction === 'desc' ? 'selected' : ''}`} />
        </span>
      </button>
    </th>
  )
}

export default function Portfolio() {
  const { currentUser, logout } = useAuth()
  const { data, loading: dataLoading, reload } = useData('report.json')
  const { data: etfData } = useData('etfs.json')
  const {
    positions,
    loading: portfolioLoading,
    addPosition,
    removePosition,
    updatePosition,
    exportPortfolio,
    syncReferencePortfolio,
    syncState,
  } = useFirebasePortfolio()
  const tracking = usePortfolioTracking()
  const { preferences, updatePreferences } = usePreferences()

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
  const [activityForm, setActivityForm] = useState({ type: 'realized_gain', amount: '', effectiveDate: new Date().toISOString().split('T')[0], note: '' })
  const [activitySaving, setActivitySaving] = useState(false)
  const [cashForm, setCashForm] = useState({ type: 'deposit', amount: '', effectiveDate: new Date().toISOString().split('T')[0], note: '' })
  const [cashSaving, setCashSaving] = useState(false)
  const [cashBalanceForm, setCashBalanceForm] = useState('')
  const [fidelityPeriod, setFidelityPeriod] = useState('1Y')
  const recordedSnapshot = useRef(null)
  const referenceCashFlowSyncStarted = useRef(false)
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
  // Lightweight screen rows are a useful quote fallback for a holding that has been
  // fetched but has not reached full published coverage yet (EXPE is one such case).
  // Full coverage is listed last so it always wins when both versions exist.
  const publishedPriceData = buildPortfolioPriceData(screenUniverse, portfolioCoverage, research)
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
    const currentValue = currentPrice == null ? null : pos.shares * currentPrice
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

  const uninvestedCash = tracking.trackingState?.cashTrackingEnabled
    ? Number(tracking.trackingState.cashBalance || 0)
    : null
  const trackedAccountValue = portfolioStats.totalValue + (uninvestedCash || 0)
  const contributionPerformance = contributionAdjustedPerformance(
    trackedAccountValue,
    tracking.activities,
    tracking.trackingState?.cashFlowHistoryComplete,
  )
  const returnSummary = portfolioReturnSummary(
    tracking.snapshots,
    tracking.activities,
    tracking.trackingState?.cashFlowHistoryComplete,
  )
  const fidelityCashSummary = summarizeCashFlows()
  const fidelityReferencePerformance = contributionAdjustedPerformance(
    FIDELITY_REFERENCE_SNAPSHOT.totalAccountValue,
    FIDELITY_CASH_FLOWS,
    true,
  )
  const cashFlowRows = tracking.activities
    .filter((row) => ['deposit', 'withdrawal', 'sale_proceeds', 'stock_purchase'].includes(row.type))
    .sort((left, right) => String(right.effectiveDate || '').localeCompare(String(left.effectiveDate || '')))

  const totalGainPct = portfolioStats.totalCost > 0
    ? ((portfolioStats.totalValue - portfolioStats.totalCost) / portfolioStats.totalCost) * 100
    : 0

  const portfolioPositions = portfolioStats.positions.map((position) => ({ ...position, allocationPct: portfolioStats.totalValue > 0 && position.currentValue != null ? position.currentValue / portfolioStats.totalValue * 100 : null }))
  // Tagged the same way mergePortfolioQuotes tags a holding's live quote, since this is the
  // raw Netlify-function payload rather than something already run through that merge.
  const benchmarkQuote = quoteRefreshIsNewest && portfolioQuotes.quotes?.SPY
    ? { ...portfolioQuotes.quotes.SPY, portfolioQuote: true }
    : null
  const moveExplanation = explainPortfolioMove(portfolioPositions, benchmarkHistory, { benchmarkQuote })
  const scoreHoldingsSeries = currentHoldingsSeries(positions, priceData, benchmarkHistory?.dates || [])
  const scorePortfolioPeriod = selectPeriod(scoreHoldingsSeries, '1Y') || selectPeriod(scoreHoldingsSeries, 'All')
  const scoreBenchmarkPeriod = selectPeriod(benchmarkHistory?.dates ? { dates: benchmarkHistory.dates, values: benchmarkHistory.closes } : null, scorePortfolioPeriod?.period || 'All')
  const scoreComparable = alignSeries(scorePortfolioPeriod, scoreBenchmarkPeriod, scorePortfolioPeriod?.period)
  const scoreDiversification = diversificationScore(portfolioPositions, { etfs: etfData?.etfs || [] })
  const scoreResilience = resilienceIndex(scoreComparable?.left.values || scorePortfolioPeriod?.values || [], scoreDiversification)
  const riskFree = riskFreeAnnualRate(data)
  const scorePerformance = performanceMetrics(scoreComparable?.left, scoreComparable?.right, riskFree.annualPct)
  const scoreConcentration = concentrationLiquidityScore(portfolioPositions)
  const overallScore = portfolioScore({
    diversification: scoreDiversification,
    resilience: scoreResilience,
    performance: scorePerformance,
    benchmarkEfficiency: null,
    concentrationLiquidity: scoreConcentration,
    dataCompleteness: positions.length ? Math.round(portfolioPositions.filter((position) => position.currentValue != null).length / positions.length * 100) : 0,
  })
  const versusIndex = portfolioVsBenchmark(portfolioPositions, benchmarkHistory)
  const basis = data?.hypothetical_basis || 500
  const fixedBasisTotal = portfolioFixedBasisVsBenchmark(portfolioStats.positions, priceData, benchmarkHistory, basis)
  const growth = portfolioGrowthSeries(portfolioStats.positions, priceData, benchmarkHistory)
  const actionable = portfolioPositions.filter(
    (pos) => pos.recommendation && pos.recommendation.action !== 'HOLD')
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

  useEffect(() => {
    if (!quoteRefreshIsNewest || !portfolioQuotes.fetchedAt || !portfolioStats.totalValue || recordedSnapshot.current === portfolioQuotes.fetchedAt) return
    recordedSnapshot.current = portfolioQuotes.fetchedAt
    tracking.recordSnapshot({ value: trackedAccountValue, coveragePct: positions.length ? portfolioStats.positions.filter((position) => position.currentValue != null).length / positions.length * 100 : 0, source: 'portfolio_price_refresh', recordedAt: portfolioQuotes.fetchedAt })
  }, [portfolioQuotes.fetchedAt, quoteRefreshIsNewest, trackedAccountValue])

  // The supplied Fidelity cash history belongs with the supplied Fidelity holdings snapshot.
  // Import once, automatically, after that portfolio is connected; stable document IDs make it safe to retry.
  useEffect(() => {
    const hasReferencePortfolio = positions.some((position) => position.snapshotSource === 'User-provided brokerage snapshot')
    const referenceReady = tracking.trackingState?.fidelityHistoryImported && tracking.trackingState?.cashTrackingEnabled
    if (!syncState.connected || !hasReferencePortfolio || referenceReady || referenceCashFlowSyncStarted.current) return
    referenceCashFlowSyncStarted.current = true
    tracking.syncReferenceCashFlows().then((result) => {
      if (result?.success) setSyncMessage(`${result.count} Fidelity cash-flow records added to Joshua’s portfolio.`)
      else {
        referenceCashFlowSyncStarted.current = false
        setSyncMessage(`Could not add Fidelity cash history: ${result?.error || 'Unknown error'}`)
      }
    })
  }, [positions, syncState.connected, tracking.trackingState?.fidelityHistoryImported, tracking.trackingState?.cashTrackingEnabled])

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
      ? `${result.added} holding${result.added === 1 ? '' : 's'} added · ${result.updated} refreshed${result.removed ? ` · ${result.removed} retired reference holding removed` : ''}`
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
    } else setSyncMessage('Position removed from the cloud portfolio on every signed-in device.')
  }

  const handleActivity = async (event) => {
    event.preventDefault()
    setActivitySaving(true)
    const result = await tracking.recordActivity({ ...activityForm, amount: Number(activityForm.amount) })
    setActivitySaving(false)
    if (!result.success) { setSyncMessage(`Could not save earnings activity: ${result.error}`); return }
    setActivityForm((current) => ({ ...current, amount: '', note: '' }))
    setSyncMessage('Earnings activity saved to Firebase.')
  }

  const handleCashMovement = async (event) => {
    event.preventDefault()
    setCashSaving(true)
    const result = await tracking.recordActivity({ ...cashForm, amount: Number(cashForm.amount) })
    setCashSaving(false)
    if (!result.success) { setSyncMessage(`Could not update cash: ${result.error}`); return }
    const labels = { deposit: 'Deposit added', withdrawal: 'Withdrawal saved', sale_proceeds: 'Sale proceeds moved to cash', stock_purchase: 'Investment deducted from cash' }
    setCashForm((current) => ({ ...current, amount: '', note: '' }))
    setSyncMessage(`${labels[cashForm.type]}. Uninvested cash updated.`)
  }

  const handleCashReconciliation = async (event) => {
    event.preventDefault()
    setCashSaving(true)
    const result = await tracking.setCashBalance({ amount: Number(cashBalanceForm), effectiveDate: new Date().toISOString().split('T')[0], note: 'Manual uninvested cash reconciliation' })
    setCashSaving(false)
    if (!result.success) { setSyncMessage(`Could not set cash balance: ${result.error}`); return }
    setCashBalanceForm('')
    setSyncMessage('Uninvested cash balance reconciled.')
  }

  const toggleLedgerComplete = async () => {
    const next = !tracking.trackingState?.ledgerComplete
    if (next && !window.confirm('Confirm that all prior realized gains and losses, dividends, and fees have been entered. This enables the All-time earnings value.')) return
    const result = await tracking.setLedgerComplete(next)
    setSyncMessage(result.success ? (next ? 'All-time earnings history confirmed.' : 'Earnings history marked incomplete.') : `Could not update earnings history: ${result.error}`)
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

  return (
    <>
      <PullToRefreshIndicator pullDistance={pullToRefresh.pullDistance} armed={pullToRefresh.armed} refreshing={portfolioQuotes.refreshing} />
      <div className="page-head">
        <div>
          <span className="eyebrow">Your money</span>
          <h1 className="page-title">My <span className="accent">portfolio</span></h1>
          <p className="page-sub">
            Holdings, action guidance, and a fair same-dollar comparison with the S&amp;P 500.
          </p>
        </div>
        <div className={`cloud-sync-state ${syncState.connected ? 'connected' : 'disconnected'}`} role="status">
          <span aria-hidden="true" />
          <div><strong>{syncState.connected ? 'Firebase live sync on' : 'Firebase sync unavailable'}</strong><small>{syncState.connected ? `${currentUser?.email || 'Signed-in account'} · devices update automatically${syncState.lastSyncedAt ? ` · ${new Date(syncState.lastSyncedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : ''}` : syncState.error || 'Waiting for your signed-in account'}</small></div>
        </div>
      </div>
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

      <div className="portfolio-summary">
        <div className="portfolio-value-card">
          <div className="kpi-label"><span className="report-hero-label">Total Value{portfolioQuotes.refreshing && <Icon name="sync" size={12} className="refresh-spin hero-value-spinner" aria-hidden="true" />}</span></div>
          <div className="kpi-value">{trackedAccountValue == null ? '–' : <AnimatedNumber value={trackedAccountValue} format={(v) => money(v, 2)} />}</div>
          <div className="portfolio-delta" style={{ color: moveColor(returnSummary.strategy.available ? returnSummary.strategy.gain : portfolioStats.totalGain) }}>
            {returnSummary.strategy.available
              ? <>{returnSummary.strategy.gain >= 0 ? '+' : '−'}<AnimatedNumber value={Math.abs(returnSummary.strategy.gain)} format={(v) => money(v, 2)} /> · <AnimatedNumber value={returnSummary.strategy.returnPct} format={(v) => signedPct(v, 2)} /> strategy return</>
              : <>{portfolioStats.totalGain >= 0 ? '+' : '−'}<AnimatedNumber value={Math.abs(portfolioStats.totalGain)} format={money} /> · <AnimatedNumber value={totalGainPct} format={(v) => signedPct(v, 2)} /></>}
          </div>
          <div className="kpi-note">{returnSummary.strategy.available ? 'Modified Dietz with settled external flows' : `${positions.length} positions · ${money(portfolioStats.totalCost)} cost basis`}</div>
        </div>
        <div className="card kpi portfolio-score-kpi">
          <div className="kpi-label">Portfolio Score</div>
          <div className="kpi-value">{overallScore.available ? overallScore.score : '–'}<small>/100</small></div>
          <div className="kpi-note">{overallScore.available ? `${overallScore.provisional ? 'Provisional · ' : ''}${overallScore.reason}` : overallScore.reason}</div>
          <a href="/portfolio/diversification">See score details →</a>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Vs S&P 500</div>
          <div className="kpi-value" style={{ color: moveColor(versusIndex?.excessReturnPct) }}>
            {versusIndex
              ? signedPct(versusIndex.excessReturnPct)
              : '–'}
          </div>
          <div className="kpi-note">
            {versusIndex
              ? `${versusIndex.dollarsAhead >= 0 ? '+' : '−'}${money(Math.abs(versusIndex.dollarsAhead))} versus the index · ${versusIndex.comparable} compared position${versusIndex.comparable === 1 ? '' : 's'}`
              : 'Add a purchase date inside the charted window'}
          </div>
          <a href="/portfolio/insights">Trader insights →</a>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Uninvested cash</div>
          <div className="kpi-value">
            {uninvestedCash == null ? '–' : money(uninvestedCash, 2)}
          </div>
          <div className="kpi-note">
            {uninvestedCash == null ? 'Sync Fidelity or set a cash balance below' : 'Available for your next purchase'}
          </div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Action Needed</div>
          <div className="kpi-value" style={{ color: actionable.length ? 'var(--warn)' : 'var(--pos)' }}>
            {actionable.length}
          </div>
          <div className="kpi-note">
            {actionable.length
              ? actionable.map((pos) => pos.ticker).join(', ')
              : 'No multi-factor deterioration'}
          </div>
        </div>
      </div>

      <PortfolioReturnSummary summary={returnSummary} />

      <PortfolioMoveExplanation attribution={moveExplanation} benchmarkLabel="S&P 500" />

      <PerformanceMetrics metrics={scorePerformance} benchmarkLabel="S&P 500" riskFree={riskFree} />

      <section className="card cash-account" aria-labelledby="cash-account-title">
        <div className="cash-account-copy">
          <span className="eyebrow">Buying power</span>
          <h2 id="cash-account-title">Uninvested cash</h2>
          <strong>{uninvestedCash == null ? 'Not set' : money(uninvestedCash, 2)}</strong>
          <p>Deposits and sale proceeds add cash. Withdrawals and new stock purchases use it without changing lifetime contributions. After a trade, edit or add the holding’s shares so total account value stays accurate.</p>
        </div>
        <form className="cash-movement-form" onSubmit={handleCashMovement}>
          <label><span>Cash action</span><select value={cashForm.type} onChange={(event) => setCashForm({ ...cashForm, type: event.target.value })}><option value="deposit">Deposit cash</option><option value="sale_proceeds">Trim / sale proceeds</option><option value="stock_purchase">Buy / invest cash</option><option value="withdrawal">Withdraw cash</option></select></label>
          <label><span>Amount</span><input type="number" inputMode="decimal" min="0.01" step="0.01" required value={cashForm.amount} onChange={(event) => setCashForm({ ...cashForm, amount: event.target.value })} placeholder="0.00" /></label>
          <label><span>Date</span><input type="date" required value={cashForm.effectiveDate} onChange={(event) => setCashForm({ ...cashForm, effectiveDate: event.target.value })} /></label>
          <label><span>Ticker or note</span><input value={cashForm.note} onChange={(event) => setCashForm({ ...cashForm, note: event.target.value })} placeholder="Optional, e.g. trimmed OXY" /></label>
          <button className="primary-button compact" disabled={cashSaving}>{cashSaving ? 'Saving…' : 'Update cash'}</button>
        </form>
        <details className="cash-reconcile">
          <summary>Cash does not match your brokerage?</summary>
          <form onSubmit={handleCashReconciliation}>
            <label><span>Current uninvested cash</span><input type="number" inputMode="decimal" min="0" step="0.01" required value={cashBalanceForm} onChange={(event) => setCashBalanceForm(event.target.value)} placeholder="0.00" /></label>
            <button className="secondary-button compact" disabled={cashSaving}>Set balance</button>
          </form>
        </details>
      </section>

      <section className="card fidelity-performance" aria-labelledby="fidelity-performance-title">
        <div className="fidelity-performance-head">
          <div>
            <span className="eyebrow">Brokerage check · Aug 4, 2026 at 2:01 p.m. ET</span>
            <h2 id="fidelity-performance-title">Fidelity performance reference</h2>
            <p>Your screenshots reconcile deposits separately from market performance.</p>
          </div>
          <div className="period-control" aria-label="Fidelity reference return period">
            {Object.keys(FIDELITY_REFERENCE_SNAPSHOT.periodReturns).map((period) => (
              <button key={period} className={fidelityPeriod === period ? 'active' : ''} aria-pressed={fidelityPeriod === period} onClick={() => setFidelityPeriod(period)}>{period}</button>
            ))}
          </div>
        </div>
        <div className="fidelity-performance-grid">
          <div><span>Account value</span><strong>{money(FIDELITY_REFERENCE_SNAPSHOT.totalAccountValue, 2)}</strong><small>{money(FIDELITY_REFERENCE_SNAPSHOT.investments, 2)} invested · {money(FIDELITY_REFERENCE_SNAPSHOT.cash, 2)} cash</small></div>
          <div><span>Net contributed</span><strong>{money(fidelityCashSummary.netContributions)}</strong><small>{money(fidelityCashSummary.deposits)} settled deposits · {money(fidelityCashSummary.withdrawals)} withdrawn{fidelityCashSummary.pendingDeposits ? ` · ${money(fidelityCashSummary.pendingDeposits)} processing` : ''}</small></div>
          <div><span>Fidelity {fidelityPeriod} return</span><strong style={{ color: moveColor(FIDELITY_REFERENCE_SNAPSHOT.periodReturns[fidelityPeriod]) }}>{signedPct(FIDELITY_REFERENCE_SNAPSHOT.periodReturns[fidelityPeriod], 2)}</strong><small>Time-weighted pre-tax return from Fidelity</small></div>
        </div>
        <p className="fidelity-method-note">The Aug. 4 $100 transfer remains excluded while Fidelity labels it Processing. Fidelity’s period return is time-weighted, so it measures investment performance without a large late deposit diluting the percentage.</p>
        <details className="fidelity-method-note"><summary>Contribution-adjusted gain detail</summary><p>{fidelityReferencePerformance.value >= 0 ? '+' : '−'}{money(Math.abs(fidelityReferencePerformance.value), 2)} is the reference account value minus settled net deposits. Its simple percentage is {signedPct(fidelityReferencePerformance.returnPct, 2)} and is not the primary reported return.</p></details>
      </section>

      <details className="card portfolio-actions-menu">
        <summary><span><span className="eyebrow">Data actions</span><strong>Refresh and manage portfolio data</strong></span><span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span></summary>
        <div className="page-actions portfolio-toolbar">
          <div className="portfolio-primary-refresh">
            <button className="primary-button compact" onClick={portfolioQuotes.requestRefresh} disabled={portfolioQuotes.refreshing || positions.length === 0}><Icon name="sync" size={17} className={portfolioQuotes.refreshing ? 'refresh-spin' : ''} />{portfolioQuotes.refreshing ? 'Updating portfolio…' : 'Refresh portfolio prices'}</button>
            <time dateTime={pricesUpdatedAt || undefined}>{pricesUpdatedAt ? `Prices updated ${new Date(pricesUpdatedAt).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}` : 'Prices not updated yet'}</time>
          </div>
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}><Icon name="sync" size={17} className={refresh.refreshing && refresh.activeMode === 'data' ? 'refresh-spin' : ''} />{refresh.refreshing && refresh.activeMode === 'data' ? 'Refreshing all data…' : 'Refresh all research'}</button>
          <button className="secondary-button" onClick={refresh.requestReanalyze} disabled={refresh.refreshing}><Icon name="research" size={17} className={refresh.refreshing && refresh.activeMode === 'rescore' ? 'refresh-spin' : ''} />{refresh.refreshing && refresh.activeMode === 'rescore' ? 'Reanalyzing…' : 'Reanalyze'}</button>
          <button className="secondary-button" onClick={handleReferenceSync}>Sync holdings</button>
          <button className="icon-button" onClick={exportPortfolio} aria-label="Export portfolio"><Icon name="download" /></button>
          <button className="icon-button" onClick={logout} aria-label="Sign out"><Icon name="logout" /></button>
        </div>
      </details>

      <details className="card earnings-tracker">
        <summary><span><span className="eyebrow">Cash flows &amp; earnings</span><strong>Cloud portfolio ledger</strong><small>{tracking.trackingState?.trackingStartedAt ? `Storing activity since ${tracking.trackingState.trackingStartedAt.slice(0, 10)}` : 'Tracking starts with your next saved activity or price refresh'}</small></span><span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span></summary>
        <div className="earnings-tracker-body">
          <p>Deposits, withdrawals, trims, and purchases are managed in the uninvested-cash card above. Record realized gains, dividends, and fees here for the earnings report.</p>
          <form className="earnings-activity-form" onSubmit={handleActivity}>
            <label><span>Activity</span><select value={activityForm.type} onChange={(event) => setActivityForm({ ...activityForm, type: event.target.value })}><option value="realized_gain">Realized gain/loss</option><option value="dividend">Dividend</option><option value="fee">Fee</option></select></label>
            <label><span>Amount</span><input type="number" step="0.01" required value={activityForm.amount} onChange={(event) => setActivityForm({ ...activityForm, amount: event.target.value })} placeholder={activityForm.type === 'realized_gain' ? 'Negative for a loss' : '0.00'} /></label>
            <label><span>Date</span><input type="date" required value={activityForm.effectiveDate} onChange={(event) => setActivityForm({ ...activityForm, effectiveDate: event.target.value })} /></label>
            <label><span>Note</span><input value={activityForm.note} onChange={(event) => setActivityForm({ ...activityForm, note: event.target.value })} placeholder="Optional" /></label>
            <button className="primary-button compact" disabled={activitySaving}>{activitySaving ? 'Saving…' : 'Save activity'}</button>
          </form>
          {cashFlowRows.length > 0 && (
            <div className="cash-flow-history" aria-label="Deposit and withdrawal history">
              <div className="cash-flow-history-head"><strong>Cash activity</strong><span>{cashFlowRows.length} movements · {money(contributionPerformance.netContributions ?? fidelityCashSummary.netContributions)} lifetime net deposits</span></div>
              {cashFlowRows.map((row) => (
                <div className="cash-flow-row" key={row.id}>
                  <span><b>{{ deposit: 'Deposit', withdrawal: 'Withdrawal', sale_proceeds: 'Trim / sale proceeds', stock_purchase: 'Buy / invest cash' }[row.type]}</b><small>{row.effectiveDate}{row.note ? ` · ${row.note}` : ''}{row.status === 'processing' ? ' · Processing' : ''}</small></span>
                  <strong style={{ color: ['deposit', 'sale_proceeds'].includes(row.type) ? 'var(--pos)' : 'var(--text-primary)' }}>{['deposit', 'sale_proceeds'].includes(row.type) ? '+' : '−'}{money(Number(row.amount), 2)}</strong>
                </div>
              ))}
            </div>
          )}
          <div className="ledger-confirmation"><div><strong>{tracking.trackingState?.ledgerComplete ? 'History confirmed complete' : 'Prior history not yet confirmed'}</strong><span>{tracking.activities.length} stored ledger event{tracking.activities.length === 1 ? '' : 's'}. Position removals are not assumed to be sales.</span></div><button className="secondary-button compact" onClick={toggleLedgerComplete}>{tracking.trackingState?.ledgerComplete ? 'Mark incomplete' : 'Confirm history is complete'}</button></div>
          {tracking.error && <p className="form-error" role="alert">Firebase tracking error: {tracking.error}</p>}
        </div>
      </details>

      {actionable.length > 0 && (
        <details className="card card-pad suggested-actions" style={{ marginBottom: 20 }} defaultOpen={preferences.suggestedActionsDefault === 'expanded'}>
          <summary><span><span className="sec-label">Suggested actions</span><strong>{actionable.length} holding{actionable.length === 1 ? '' : 's'} to review</strong></span><Icon name="chevron" /></summary>
          <div style={{ display: 'grid', gap: 10 }}>
            {actionable.map((pos) => (
              <div key={pos.id || pos.ticker} style={{
                display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap',
                paddingBottom: 10, borderBottom: '1px solid var(--border)',
              }}>
                <ActionPill recommendation={pos.recommendation} />
                <b className="mono">{pos.ticker}</b>
                <span style={{ color: 'var(--text-dim)', fontSize: 13, flex: 1, minWidth: 200 }}>
                  {pos.recommendation.summary}
                </span>
                {pos.recommendation.suggestedTrimPct > 0 && (
                  <span className="mono" style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                    {((pos.shares * pos.recommendation.suggestedTrimPct) / 100).toFixed(2)} of {pos.shares} shares
                    {' '}≈ {money((pos.currentValue * pos.recommendation.suggestedTrimPct) / 100)}
                  </span>
                )}
                <button className="chip button-chip" onClick={() => setSelectedStock(pos)}>Why</button>
              </div>
            ))}
          </div>
        </details>
      )}

      {exposure.warnings.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 20, borderColor: 'var(--warn)' }}>
          <div className="sec-label">Concentration risk</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {exposure.warnings.map((warning) => (
              <div key={`${warning.type}-${warning.label}`} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <span className="mono" style={{ color: 'var(--warn)', fontWeight: 600 }}>{warning.pct.toFixed(1)}%</span>
                <span style={{ color: 'var(--text-dim)', fontSize: 13 }}>{warning.message}</span>
              </div>
            ))}
          </div>
          <p style={{ color: 'var(--text-faint)', fontSize: 11, marginTop: 10 }}>
            Illustrative guidelines only ({exposure.maxPositionPct}% per position, {exposure.maxSectorPct}% per
            sector) – not a rule to force a sale, but a prompt to size new buys and rebalancing with the
            concentration you already carry in mind.
          </p>
        </div>
      )}

      {growth && (
        <details className="card portfolio-comparison">
          <summary>
            <div>
              <span className="eyebrow">Opportunity cost</span>
              <strong>What if I chose the S&amp;P 500–or did not invest?</strong>
              <small>Same contributions, added on your recorded purchase dates</small>
            </div>
            <div className="comparison-summary-side">
              {versusIndex && (
                <span className="comparison-edge" style={{ color: moveColor(versusIndex.excessReturnPct) }}>
                  {signedPct(versusIndex.excessReturnPct)} vs S&amp;P
                </span>
              )}
              <span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span>
            </div>
          </summary>
          <div className="portfolio-comparison-chart">
            <GrowthChart
              dates={growth.dates}
              series={[
                { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
                { label: 'S&P 500, same deposits', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
                { label: 'Deposits held as cash', values: growth.cash, color: 'var(--series-cash)', dashPattern: '2 5' },
              ]}
              title="One-to-one performance from your investment dates"
              caption={`Each holding starts with its exact cost-basis dollars on its recorded purchase date, then follows that stock’s price return. The S&P receives the identical dollars on the identical date. Cash holds the same deposits. Jumps show new money entering, not investment gains. Covers ${growth.trackedTickers.length} dated position${growth.trackedTickers.length === 1 ? '' : 's'} from ${growth.firstInvestmentDate}${growth.untrackedCount ? `. ${growth.untrackedCount} missing a usable date or published history` : ''}.`}
              zoomable
            />
          </div>
        </details>
      )}

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
        <div className="portfolio-mobile-list">
          {sortedPositions.map((pos) => (
            <article className="holding-card" key={pos.id || pos.ticker}>
              <div className="holding-card-head">
                <CompanyLogo company={pos.priceInfo || pos} size={40} /><div><strong>{pos.ticker}</strong><span>{pos.priceInfo?.name || 'Coverage pending'}</span><small>{pos.allocationPct == null ? 'Allocation unavailable' : `${pos.allocationPct.toFixed(1)}% of portfolio`}</small></div>
                <ActionPill recommendation={pos.recommendation} />
              </div>
              <div className="holding-value">
                <div><span>Position value</span><strong>{pos.currentValue == null ? 'Unavailable' : money(pos.currentValue)}</strong></div>
                <Move value={pos.gainPct} capsule />
              </div>
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
              {editingId !== pos.id && pos.trendValues.length > 1 && (
                <div className="holding-trend">
                  <div><span>1-month trend</span><Move value={pos.trendPct} /></div>
                  <Sparkline values={pos.trendValues} label={`${pos.ticker} one-month price trend`} height={48} />
                </div>
              )}
              <div className="holding-actions">
                {editingId !== pos.id && (
                  <>
                    {pos.priceInfo && <button className="secondary-button" onClick={() => setSelectedStock(pos)}>Research</button>}
                    <button className="text-button" onClick={() => startEdit(pos)}>Edit</button>
                    <button className="text-button danger" onClick={() => handleRemove(pos.id)} disabled={removingId === pos.id}>
                      {removingId === pos.id ? 'Removing…' : 'Remove'}
                    </button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
        <div className="card card-pad table-wrap portfolio-table">
          <table>
            <thead>
              <tr>
                <SortableHeader sortKey="ticker" sort={portfolioSort} onSort={setSortKey}>Ticker</SortableHeader>
                <SortableHeader sortKey="company" sort={portfolioSort} onSort={setSortKey}>Company</SortableHeader>
                <SortableHeader sortKey="signal" sort={portfolioSort} onSort={setSortKey}>Signal</SortableHeader>
                <th scope="col">Stop-loss</th>
                <SortableHeader numeric sortKey="shares" sort={portfolioSort} onSort={setSortKey}>Shares</SortableHeader>
                <SortableHeader numeric sortKey="cost" sort={portfolioSort} onSort={setSortKey}>Avg. cost/share</SortableHeader>
                <SortableHeader numeric sortKey="price" sort={portfolioSort} onSort={setSortKey}>Price</SortableHeader>
                <SortableHeader numeric sortKey="value" sort={portfolioSort} onSort={setSortKey}>Value</SortableHeader>
                <SortableHeader numeric sortKey="allocation" sort={portfolioSort} onSort={setSortKey}>Allocation</SortableHeader>
                <SortableHeader numeric sortKey="gain" sort={portfolioSort} onSort={setSortKey}>Gain/Loss</SortableHeader>
                <SortableHeader numeric sortKey="return" sort={portfolioSort} onSort={setSortKey}>Return</SortableHeader>
                <SortableHeader numeric sortKey="score" sort={portfolioSort} onSort={setSortKey}>Score</SortableHeader>
                <SortableHeader numeric sortKey="trend" sort={portfolioSort} onSort={setSortKey}>1M trend</SortableHeader>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedPositions.map((pos) => (
                <tr key={pos.id || pos.ticker}>
                  <td className="mono">{pos.ticker}</td>
                  <td>{pos.priceInfo?.name || '–'}</td>
                  <td><ActionPill recommendation={pos.recommendation} /></td>
                  <td>{pos.stopLoss ? <StopLossNote stopLoss={pos.stopLoss} /> : <span className="mono">–</span>}</td>
                  <td className="mono num">
                    {editingId === pos.id
                      ? <input className="inline-edit-input table-edit-input" type="number" step="0.001" min="0" value={editForm.shares}
                          onChange={(e) => setEditForm({ ...editForm, shares: e.target.value })} />
                      : pos.shares}
                  </td>
                  <td className="mono num">
                    {editingId === pos.id
                      ? (
                        <div style={{ display: 'grid', gap: 2, justifyItems: 'end' }}>
                          <select value={editForm.costMode} onChange={(e) => setEditForm({ ...editForm, costMode: e.target.value })}
                            style={{ minHeight: 'auto', height: 16, padding: '0 2px', border: 0, background: 'transparent', color: 'var(--text-faint)', fontSize: 8, textTransform: 'none', letterSpacing: 0 }}>
                            <option value="share">$/share</option>
                            <option value="total">Total $</option>
                          </select>
                          <input className="inline-edit-input table-edit-input" type="number" step="0.01" min="0" value={editForm.costBasis}
                            onChange={(e) => setEditForm({ ...editForm, costBasis: e.target.value })} />
                        </div>
                      )
                      : `$${pos.costBasis.toFixed(2)}`}
                  </td>
                  <td className="mono num">{pos.currentPrice == null ? '–' : `$${pos.currentPrice.toFixed(2)}`}</td>
                  <td className="mono num">{pos.currentValue == null ? '–' : money(pos.currentValue)}</td>
                  <td className="mono num">{pos.allocationPct == null ? '–' : `${pos.allocationPct.toFixed(1)}%`}</td>
                  <td className="mono num" style={{ color: moveColor(pos.gain) }}>
                    {pos.gain == null ? '–' : `${pos.gain >= 0 ? '+' : '−'}${money(Math.abs(pos.gain))}`}
                  </td>
                  <td className="num"><Move value={pos.gainPct} /></td>
                  <td className="mono num score-cell">{pos.priceInfo?.score ?? '–'}</td>
                  <td className="num portfolio-trend-cell">
                    {pos.trendValues.length > 1 ? (
                      <>
                        <Sparkline values={pos.trendValues} label={`${pos.ticker} one-month price trend`} height={34} />
                        <Move value={pos.trendPct} />
                      </>
                    ) : <span className="mono">–</span>}
                  </td>
                  <td style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {editingId === pos.id ? (
                      <>
                        <button className="chip button-chip" onClick={() => saveEdit(pos.id)} disabled={editSaving}>
                          {editSaving ? 'Saving…' : 'Save'}
                        </button>
                        <button className="chip button-chip" onClick={cancelEdit} disabled={editSaving}>Cancel</button>
                      </>
                    ) : (
                      <>
                        {pos.priceInfo && (
                          <button className="chip button-chip" onClick={() => setSelectedStock(pos)}>Details</button>
                        )}
                        <button className="chip button-chip" onClick={() => startEdit(pos)}>Edit</button>
                        <button className="chip button-chip" onClick={() => handleRemove(pos.id)} disabled={removingId === pos.id}>
                          {removingId === pos.id ? 'Removing…' : 'Remove'}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {portfolioStats.positions.length === 0 && (
                <tr>
                  <td colSpan="13" style={{ textAlign: 'center', padding: 40, opacity: 0.5 }}>
                    No positions yet. Click "+ Add Position" to start tracking.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
