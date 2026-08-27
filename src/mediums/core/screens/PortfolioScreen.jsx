import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { AuthProvider as FirebaseAuthProvider, useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { usePortfolioTracking } from '../../../lib/usePortfolioTracking.js'
import { useFirebaseFinances } from '../../../lib/useFirebaseFinances.js'
import { usePreferences, formatPreferenceMoney } from '../../../lib/PreferencesContext.jsx'
import {
  enrichPortfolio, currentHoldingsSeries, benchmarkHistoryFromSnapshot, selectPeriod, alignSeries,
  compareBenchmarkSeries, performanceMetrics, underwaterProfile, diversificationScore,
  portfolioRiskDecomposition, concentrationLiquidityScore, resilienceIndex, portfolioScore,
  riskFreeAnnualRate, portfolioReturnSummary, portfolioReconciliationBridge, weightedExpenseRatio,
  sectorLookThrough, latestMarketDayReturn, annualizeReturnPct, sliceSeriesFrom,
} from '../../../lib/portfolioAnalytics.js'
import { portfolioAcceleration } from '../../../lib/portfolioAcceleration.js'
import { captureRatios, battingAverage } from '../../../lib/portfolioBenchmarkComparison.js'
import { shortTermView } from '../../../lib/portfolioShortTermView.js'
import { factorRegression } from '../../../lib/factorAnalytics.js'
import { timeToValidMetric } from '../../../lib/portfolioStatistics.js'
import { portfolioVsBenchmark } from '../../../lib/portfolioPerformance.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { splitBySampleRequirement, defaultOpenGroups, sharedStatusMessage } from '../../../lib/signalMetrics.js'
import {
  alignManyForChart, benchmarkShadowPortfolio, holdingsVsBenchmark, portfolioMood,
  purchaseTimingSignal, snapshotDailySeries, tradeStats,
} from '../../../lib/traderInsights.js'
import { summarizeBudget, splitAmount } from '../../../lib/financeSplit.js'
import { ACCOUNT_TYPES, getAnnualLimit, accountTypeLabel } from '../../../lib/retirementLimits.js'
import {
  annualReturnTargetRange, applyAllocationAssumption, formatAnnualReturnTarget, normalizeAnnualReturnTarget,
  projectionConfig, selectProjectionReturnSource, sequenceRiskPaths,
} from '../../../lib/projectionEngine.js'
import { useProjectionSimulation } from '../../../lib/useProjectionSimulation.js'
import { fidelityProjectionBaseline } from '../../../lib/referenceCashFlows.js'
import { coastFireStatus } from '../../../lib/coastFire.js'
import { derivePortfolioRiskProfile } from '../../../lib/monteCarloRiskProfile.js'
import { usePortfolioMonteCarloCalibration } from '../../../lib/usePortfolioMonteCarloCalibration.js'
import { buildExportSnapshot, snapshotFilename, snapshotToJson } from '../../../lib/exportSnapshot.js'
import { LIVE_TRACKING_START } from '../../../lib/liveTrackingAvailability.js'
import prospectiveValidation from '../../../../pipeline/validation/harness_freeze.json'
import { useMedium } from '../MediumContext.jsx'
import { useRenderer } from '../useRenderer.js'
import { canonicalArtifactState, confidenceOf } from '../states.js'
import { fanChartCall, projectionArtifactState } from '../fanChart.js'
import { cap } from '../capability.js'
import WallLabel from '../WallLabel.jsx'
import { PORTFOLIO_IDS } from './capabilityIds.js'
import { useStockDetail } from '../useStockDetail.js'
import StockDetailSheet from './StockDetailSheet.jsx'
import { getRecommendation, actionHeadline, actionStyle, positionImpact } from '../../../lib/recommendation.js'

const MARKET_DESTINATIONS = [
  { symbol: 'SPY', label: 'S&P 500' },
  { symbol: 'QQQ', label: 'Nasdaq-100' },
  { symbol: 'DIA', label: 'Dow Jones' },
  { symbol: 'IWM', label: 'Russell 2000' },
]

function latestMove(history) {
  const values = history?.closes || []
  if (values.length < 2 || !values.at(-2)) return null
  return (values.at(-1) / values.at(-2) - 1) * 100
}

/** Finances/Planning-scoped money formatting -- no privacy masking, matches `src/pages/Finances.jsx`/`Planning.jsx`. */
function financeMoney(value, digits = 0) {
  return value == null || !Number.isFinite(Number(value)) ? '–' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })}`
}

/** Sums held-position value against live research prices, falling back to cost basis when a price isn't available. */
function currentPortfolioValue(positions, report) {
  const priceData = Object.fromEntries(
    [...(report?.research || []), ...(report?.portfolio_coverage || [])]
      .filter((row) => row.ticker && row.price != null)
      .map((row) => [String(row.ticker).trim().toUpperCase(), row])
  )
  return positions.reduce((sum, pos) => {
    const ticker = String(pos.ticker || '').trim().toUpperCase()
    const currentPrice = priceData[ticker]?.price ?? pos.snapshotPrice ?? pos.costBasis ?? 0
    return sum + (pos.shares || 0) * currentPrice
  }, 0)
}

function defaultGoalDate() {
  const date = new Date()
  date.setUTCFullYear(date.getUTCFullYear() + projectionConfig.goal_default_years)
  return date.toISOString().slice(0, 10)
}

function successBand(probability) {
  return projectionConfig.success_bands.find((band) => probability >= band.minimum) || projectionConfig.success_bands.at(-1)
}

export const PORTFOLIO_VIEWS = Object.freeze(['summary', 'performance', 'data', 'diversification', 'insights', 'finances', 'planning'])

// --- formatting helpers -----------------------------------------------------------------
const finite = (value) => value != null && value !== '' && Number.isFinite(Number(value))
const ratio = (value) => finite(value) ? Number(value).toFixed(2) : null
const pct = (value, digits = 1) => finite(value) ? `${Number(value).toFixed(digits)}%` : null
const signedPct = (value, digits = 1) => finite(value) ? `${Number(value) >= 0 ? '+' : '−'}${Math.abs(Number(value)).toFixed(digits)}%` : null
const money = (value) => finite(value) ? `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}` : null
const duration = (days) => {
  if (!finite(days)) return null
  if (Number(days) < 60) return `${Math.round(Number(days))}d`
  const months = Number(days) / 30.44
  return months < 18 ? `${months.toFixed(1)}mo` : `${(Number(days) / 365.25).toFixed(1)}y`
}

/**
 * Builds a `WallLabel`-shaped metric row from a live computed value. `capabilityId` is always
 * passed explicitly to `<WallLabel>` for these (rather than relying on its id-derivation), since
 * the underlying lib functions use their own internal id conventions that don't match the
 * ledger's dash-separated ids one-for-one.
 */
function metricRow(label, { display, value = null, reads = null, cadence = null, source = null, observations = null, requiredObservations = null, unavailableReason = null } = {}) {
  const ready = display != null
  const status = ready ? 'ready' : observations != null && requiredObservations ? 'accumulating' : 'unavailable'
  return {
    label,
    display: display ?? null,
    value,
    reads,
    cadence,
    source,
    breached: false,
    status,
    observations,
    required_observations: requiredObservations,
    status_message: ready ? null : unavailableReason || 'Not enough history to compute this yet.',
  }
}

function Metric({ capId, label, ...options }) {
  return <WallLabel metric={metricRow(label, options)} capabilityId={capId} />
}

// --- analytics assembly ------------------------------------------------------------------
/**
 * Assembles the live analytics every `?view=data`/`?view=diversification`/`?view=summary`
 * metric row reads from, replicating (at reduced scope) the same lib call chain
 * `src/pages/portfolio/portfolioAnalyticsModel.js` uses -- that file itself cannot be imported
 * here (ESLint bans `src/pages/*` outside Classic), so the assembly is re-done directly against
 * `src/lib/*`, which is unrestricted.
 */
function useAnalytics({ report, positions, priceData, etfData, factorData, spySnapshot }) {
  return useMemo(() => {
    try {
      const enriched = enrichPortfolio(positions, priceData)
      const holdingsSeriesFull = currentHoldingsSeries(enriched.positions, priceData)
      const spyHistory = benchmarkHistoryFromSnapshot(spySnapshot)
      const spySeries = spyHistory ? { dates: spyHistory.dates, values: spyHistory.closes, symbol: 'SPY', label: 'S&P 500' } : null

      const scorePeriod = selectPeriod(holdingsSeriesFull, 'All')
      const benchmarkPeriod = selectPeriod(spySeries, 'All')
      const comparable = alignSeries(scorePeriod, benchmarkPeriod, 'All')
      const riskFree = riskFreeAnnualRate(report)

      const performance = performanceMetrics(comparable?.left, comparable?.right, riskFree.annualPct)
      const acceleration = portfolioAcceleration(holdingsSeriesFull, spySeries)
      const capture = captureRatios(holdingsSeriesFull, spySeries)
      const batting = battingAverage(holdingsSeriesFull, spySeries)
      const underwater = underwaterProfile(holdingsSeriesFull)
      const shortTerm = shortTermView(holdingsSeriesFull, spySeries)
      const risk = portfolioRiskDecomposition(enriched.positions, {
        benchmarkHistory: spySeries ? { dates: spySeries.dates, closes: spySeries.values } : null,
        etfs: etfData?.etfs || [],
      })
      const diversification = diversificationScore(enriched.positions, { etfs: etfData?.etfs || [] })
      const factor = factorRegression(comparable?.left || scorePeriod, factorData)
      const resilience = resilienceIndex(comparable?.left?.values || scorePeriod?.values || [], diversification)
      const concentration = concentrationLiquidityScore(enriched.positions)
      const dataCompleteness = positions.length
        ? Math.round(enriched.positions.filter((row) => row.currentValue != null).length / positions.length * 100)
        : 0
      const legacyScore = portfolioScore({ diversification, resilience, performance, benchmarkEfficiency: null, concentrationLiquidity: concentration, dataCompleteness })
      const versusIndex = portfolioVsBenchmark(enriched.positions, report?.benchmark_history)
      const twrComparison = spySeries ? compareBenchmarkSeries(scorePeriod, [spySeries]) : null
      const timeToValid = timeToValidMetric(performance?.observations, comparable?.left?.dates?.at(-1) || scorePeriod?.dates?.at(-1) || null)
      const fundCost = weightedExpenseRatio(enriched.positions, etfData?.etfs || [])
      const lookThrough = sectorLookThrough(enriched.positions, etfData?.etfs || [])

      return {
        available: true, enriched, holdingsSeriesFull, spySeries, riskFree, performance, acceleration, capture,
        batting, underwater, shortTerm, risk, diversification, factor, resilience, concentration, legacyScore,
        versusIndex, twrComparison, timeToValid, fundCost, lookThrough,
      }
    } catch (error) {
      return { available: false, error: error.message }
    }
  }, [report, positions, priceData, etfData, factorData, spySnapshot])
}

/** Groups positions by their published industry classification, preserving labels (unlike
 * `diversificationScore`'s internal `industries`, which only keeps sorted values). */
function industryAllocation(positions = []) {
  const priced = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0)
  const total = priced.reduce((sum, row) => sum + Number(row.currentValue), 0)
  if (!total) return []
  const byIndustry = new Map()
  priced.forEach((row) => {
    const key = row.priceInfo?.industry || 'Unclassified'
    byIndustry.set(key, (byIndustry.get(key) || 0) + Number(row.currentValue))
  })
  return [...byIndustry.entries()].map(([label, value]) => ({ label, pct: value / total * 100 })).sort((left, right) => right.pct - left.pct)
}

export default function PortfolioScreen() {
  return <FirebaseAuthProvider><PortfolioScreenContent /></FirebaseAuthProvider>
}

function PortfolioScreenContent() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams, setSearchParams] = useSearchParams()
  const view = PORTFOLIO_VIEWS.includes(searchParams.get('view')) ? searchParams.get('view') : 'summary'

  const { data: report, loading: reportLoading } = useData('report.json')
  const { data: etfData } = useData('etfs.json')
  const { data: factorData } = useData('factors/french.json')
  const { data: spySnapshot } = useData('etf/SPY.json')
  const { data: signalMetrics } = useData(view === 'data' ? 'validation/signal_metrics.json' : null)
  const needsBenchmarkReport = view === 'data' || view === 'insights' || view === 'finances' || view === 'planning'
  const { data: benchmarkReport, loading: benchmarkReportLoading } = useData(needsBenchmarkReport ? 'benchmark-report.json' : null)
  const { preferences } = usePreferences()
  const { data: alternateBenchmarkSnapshot } = useData(
    view === 'insights' && preferences.defaultBenchmark !== 'SPY' ? `etf/${preferences.defaultBenchmark}.json` : null,
  )
  const { currentUser } = useAuth()
  const { positions, loading: portfolioLoading, exportPortfolio, syncState } = useFirebasePortfolio()
  const tracking = usePortfolioTracking()
  const finances = useFirebaseFinances()
  const { openStockDetail } = useStockDetail()

  const priceData = useMemo(() => {
    if (!report) return {}
    const published = buildPortfolioPriceData(report.screen_universe || [], report.portfolio_coverage || [], report.research || [])
    return mergePositionSnapshots(published, positions, report.generated_at)
  }, [report, positions])

  const portfolio = useMemo(() => enrichPortfolio(positions, priceData), [positions, priceData])
  const analytics = useAnalytics({ report, positions, priceData, etfData, factorData, spySnapshot })

  const returnSummary = useMemo(
    () => portfolioReturnSummary(tracking.snapshots, tracking.activities, Boolean(tracking.trackingState?.ledgerComplete)),
    [tracking.snapshots, tracking.activities, tracking.trackingState],
  )
  const bridge = useMemo(() => portfolioReconciliationBridge(tracking.snapshots, tracking.activities), [tracking.snapshots, tracking.activities])

  if (reportLoading || portfolioLoading) {
    return <div {...cap(PORTFOLIO_IDS.loading)} role="status" aria-live="polite">Loading…</div>
  }

  const setView = (nextView) => {
    const next = new URLSearchParams(searchParams)
    next.set('view', nextView)
    setSearchParams(next)
  }

  return (
    <div data-screen="portfolio" data-view={view}>
      <StockDetailSheet />
      <nav {...cap('nav.portfolio.sub-tabs')} aria-label="Portfolio views">
        {PORTFOLIO_VIEWS.map((item) => (
          <button type="button" key={item} aria-current={view === item ? 'page' : undefined} onClick={() => setView(item)}>{item}</button>
        ))}
      </nav>
      <div {...cap('disclosure.portfolio.firebase-sync-pill')}>
        {syncState?.connected ? 'Firebase live sync on' : syncState?.error ? `Firebase live sync unavailable: ${syncState.error}` : 'Firebase live sync unavailable'}
      </div>
      <p {...cap('disclosure.portfolio.hold-not-shown')}>Hold positions are not shown here.</p>

      {view === 'summary' && (
        <SummaryView Container={Container} portfolio={portfolio} positions={positions} analytics={analytics} returnSummary={returnSummary}
          openStockDetail={openStockDetail} preferences={preferences} />
      )}
      {view === 'performance' && (
        <PerformanceView Container={Container} analytics={analytics} returnSummary={returnSummary} bridge={bridge} tracking={tracking} searchParams={searchParams} setSearchParams={setSearchParams} />
      )}
      {view === 'data' && (
        <DataView Container={Container} analytics={analytics} positions={positions} signalMetrics={signalMetrics} benchmarks={benchmarkReport} searchParams={searchParams} setSearchParams={setSearchParams} exportPortfolio={exportPortfolio} />
      )}
      {view === 'diversification' && (
        <DiversificationView Container={Container} analytics={analytics} positions={positions} />
      )}
      {view === 'insights' && (
        <InsightsView
          Container={Container} benchmarkReport={benchmarkReport} benchmarkReportLoading={benchmarkReportLoading}
          alternateBenchmarkSnapshot={alternateBenchmarkSnapshot} positions={positions} portfolio={portfolio} analytics={analytics}
          tracking={tracking} preferences={preferences} currentUser={currentUser}
        />
      )}
      {view === 'finances' && (
        <FinancesView
          Container={Container} report={report} benchmarkReport={benchmarkReport} benchmarkReportLoading={benchmarkReportLoading}
          positions={positions} analytics={analytics} preferences={preferences} finances={finances}
          searchParams={searchParams} setSearchParams={setSearchParams}
        />
      )}
      {view === 'planning' && (
        <PlanningView
          Container={Container} report={report} benchmarkReport={benchmarkReport} benchmarkReportLoading={benchmarkReportLoading}
          positions={positions} analytics={analytics} preferences={preferences} finances={finances} tracking={tracking}
        />
      )}
    </div>
  )
}

// --- Summary view --------------------------------------------------------------------------
/**
 * Positions whose current guidance is TRIM or SELL -- the "needs your attention" subset, not
 * every held position (HOLD/WATCH are the default state and stay on the holdings grid only).
 * `row.priceInfo` is the full published research/coverage/screen_universe row `enrichPortfolio`
 * already resolved per ticker (see `buildPortfolioPriceData`), which is exactly the shape
 * `getRecommendation()` expects -- no separate `report.json` lookup needed here.
 */
function suggestedActionPositions(portfolioPositions) {
  return portfolioPositions
    .map((row) => ({ row, recommendation: row.priceInfo ? getRecommendation(row.priceInfo) : null }))
    .filter(({ recommendation }) => recommendation && ['TRIM', 'SELL'].includes(recommendation.action))
}

function SummaryView({ Container, portfolio, positions, analytics, returnSummary, openStockDetail, preferences }) {
  const [suggestedActionsOpen, setSuggestedActionsOpen] = useState(preferences?.suggestedActionsDefault === 'expanded')
  const suggestedActions = useMemo(() => suggestedActionPositions(portfolio.positions), [portfolio.positions])

  return (
    <>
      <Container {...cap(PORTFOLIO_IDS.kpiRow)}>
        {positions.length ? (
          <>
            <strong data-testid="invested-value">{portfolio.totalValue != null ? `$${portfolio.totalValue.toFixed(2)}` : '–'}</strong>
            <span data-testid="gain">{portfolio.gain != null ? `${portfolio.gain >= 0 ? '+' : ''}$${portfolio.gain.toFixed(2)}` : '–'}</span>
          </>
        ) : (
          <span {...cap('state.portfolio.no-positions')}>No positions yet. Add a position to start tracking.</span>
        )}
      </Container>

      {positions.length > 0 && analytics.available && (
        <>
          <Container aria-label="Summary metrics">
            <Metric capId="metric.report.strategy-return-twr" label="Strategy return (time-weighted)"
              display={analytics.twrComparison ? signedPct(analytics.twrComparison.portfolio.returnPct, 2) : null}
              value={analytics.twrComparison?.portfolio.returnPct}
              reads="Current holdings, repriced against their own historical closes -- immune to deposit and withdrawal timing by construction."
              cadence="daily" source="portfolioAnalytics.js" observations={analytics.twrComparison?.dates?.length}
              unavailableReason="Two shared market dates are needed to compare current holdings with the benchmark." />
            <Metric capId="metric.report.money-weighted-xirr" label="Your return (money-weighted)"
              display={returnSummary?.moneyWeighted?.available ? signedPct(returnSummary.moneyWeighted.rate, 2) : null}
              value={returnSummary?.moneyWeighted?.rate}
              reads="Annualized XIRR from recorded account values and settled external deposits/withdrawals -- reflects the actual size and timing of your cash flows."
              cadence="per recorded snapshot" source="portfolioAnalytics.js"
              unavailableReason={returnSummary?.moneyWeighted?.reason || 'Confirm the complete deposit and withdrawal history, then record at least two dated account values.'} />
            <Metric capId="metric.report.portfolio-score" label="Portfolio Score"
              display={analytics.legacyScore?.available ? `${Math.round(analytics.legacyScore.score)} / 100` : null}
              value={analytics.legacyScore?.score}
              reads="Weighted composite of diversification, resilience, risk-adjusted performance, concentration/liquidity, and data completeness."
              cadence="per refresh" source="portfolioAnalytics.js"
              unavailableReason={analytics.legacyScore?.reason} />
            <Metric capId="metric.report.versus-sp500-return" label="Vs S&P 500"
              display={analytics.versusIndex ? signedPct(analytics.versusIndex.excessReturnPct, 2) : null}
              value={analytics.versusIndex?.excessReturnPct}
              reads="Position-by-position: what the same invested dollars would be worth today had they gone into the S&P 500 on each purchase date instead."
              cadence="per refresh" source="portfolioPerformance.js"
              unavailableReason="No positions have both a comparable purchase date and published benchmark history yet." />
          </Container>

          <Container {...cap('figure.portfolio.holdings-grid')}>
            <ul data-testid="holdings-grid">
              {portfolio.positions.map((row) => (
                <li key={row.id || row.ticker}>
                  <button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button>
                  <span>{money(row.currentValue) || '–'}</span>
                  <span>{row.gainPct != null ? signedPct(row.gainPct, 1) : '–'}</span>
                </li>
              ))}
            </ul>
          </Container>

          <details id="sell-signals" {...cap('control.portfolio.suggested-actions-toggle')}
            open={suggestedActionsOpen} onToggle={(event) => setSuggestedActionsOpen(event.currentTarget.open)}>
            <summary>Suggested actions ({suggestedActions.length})</summary>
            <ul data-testid="suggested-actions-list" {...cap('figure.portfolio.suggested-actions-list')}>
              {suggestedActions.length ? suggestedActions.map(({ row, recommendation }) => {
                const style = actionStyle(recommendation.action)
                const impact = positionImpact(recommendation, { shares: row.shares, price: row.currentPrice })
                return (
                  <li key={row.id || row.ticker}>
                    <span style={{ color: style.color }}>{style.icon} {actionHeadline(recommendation)}</span>
                    <strong>{row.ticker}</strong>
                    <span>{recommendation.summary}</span>
                    {impact && (
                      <small>{impact.shares.toFixed(2)} of {row.shares} shares ≈ {money(impact.proceeds)}</small>
                    )}
                    <button type="button" onClick={() => openStockDetail(row.ticker)}>Why</button>
                  </li>
                )
              }) : <li>No sell/trim actions need review right now.</li>}
            </ul>
          </details>

          <Container {...cap('column.portfolio.benchmark-table')}>
            {analytics.versusIndex ? (
              <table>
                <thead><tr><th scope="col">Metric</th><th scope="col">Your holdings</th><th scope="col">S&P 500</th></tr></thead>
                <tbody>
                  <tr><th scope="row">Return</th><td>{signedPct(analytics.versusIndex.holdingsReturnPct, 2)}</td><td>{signedPct(analytics.versusIndex.benchmarkReturnPct, 2)}</td></tr>
                  <tr><th scope="row">TOTAL</th><td>{money(analytics.versusIndex.holdingsValue)}</td><td>{money(analytics.versusIndex.benchmarkValue)}</td></tr>
                </tbody>
              </table>
            ) : <p>Benchmark comparison is unavailable — no positions have a comparable purchase date yet.</p>}
          </Container>

          <p {...cap('disclosure.portfolio.summary-chart-caption')}>Current quantities applied to historical prices; only invested holdings are included.</p>
          {analytics.versusIndex && (
            <p {...cap('disclosure.portfolio.fair-comparison-callout')}>The only fair comparison: the same dollars, on the same dates, in the S&P 500 instead.</p>
          )}
          <p {...cap('disclosure.portfolio.comparison-footnote')}>Positions before the benchmark window shows "–".</p>
        </>
      )}
    </>
  )
}

// --- Performance view ----------------------------------------------------------------------
const PERFORMANCE_PERIODS = ['1W', '1M', '3M', '1Y', 'All']

function PerformanceView({ Container, analytics, returnSummary, bridge, tracking, searchParams, setSearchParams }) {
  const period = PERFORMANCE_PERIODS.includes(searchParams.get('compareOver')) ? searchParams.get('compareOver') : '1M'
  const setPeriod = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('compareOver', next)
    setSearchParams(params)
  }

  if (!analytics.available) {
    return <div {...cap('state.portfolio.performance-building')}>Comparison history is still building.</div>
  }

  const comparison = analytics.twrComparison

  return (
    <>
      <label {...cap('control.portfolio.performance-compare-over')}>
        <span>Compare over</span>
        <select value={period} onChange={(event) => setPeriod(event.target.value)}>
          {PERFORMANCE_PERIODS.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>

      {comparison ? (
        <Container {...cap('figure.portfolio.twr-kpis')}>
          <span><small>Time-weighted return</small><strong>{signedPct(comparison.portfolio.returnPct, 2)}</strong></span>
          <span><small>{comparison.benchmarks[0].label}</small><strong>{signedPct(comparison.benchmarks[0].returnPct, 2)}</strong></span>
          <span><small>Difference</small><strong>{signedPct(comparison.portfolio.returnPct - comparison.benchmarks[0].returnPct, 2)}</strong></span>
        </Container>
      ) : (
        <div {...cap('state.portfolio.performance-building')}>Comparison history is still building — two shared market dates are needed.</div>
      )}
      <p {...cap('disclosure.portfolio.twr-immune-to-flows')}>Time-weighted return reprices the exact share count, immune to cash-flow timing.</p>

      <Container {...cap('figure.portfolio.xirr-kpi')}>
        {returnSummary?.moneyWeighted?.available ? (
          <span><small>Money-weighted return (XIRR)</small><strong>{signedPct(returnSummary.moneyWeighted.rate, 2)}</strong></span>
        ) : (
          <p {...cap('disclosure.portfolio.xirr-accumulating')}>Money-weighted return (XIRR) is accumulating: {returnSummary?.moneyWeighted?.reason}</p>
        )}
      </Container>

      <Container {...cap('figure.portfolio.reconciliation-bridge')}>
        {bridge?.available ? (
          <ul>
            {[
              ['Beginning NAV', bridge.beginningNav], ['+ Deposits', bridge.deposits], ['− Withdrawals', -bridge.withdrawals],
              ['+ Dividends', bridge.dividends], ['− Fees', -bridge.fees], ['+ Realized gains', bridge.realizedGains],
              ['+ Unrealized gain change', bridge.unrealizedGainChange],
            ].map(([label, value]) => <li key={label}><span>{label}</span><span>{money(value)}</span></li>)}
            <li><span>= Reconstructed ending NAV</span><span>{money(bridge.reconstructedEndingNav)}</span></li>
            <li><span>Recorded ending NAV</span><span>{money(bridge.endingNav)}</span></li>
          </ul>
        ) : (
          <p {...cap('disclosure.portfolio.bridge-accumulating')}>Reconciliation bridge is accumulating: {bridge?.reason}</p>
        )}
        <p {...cap('disclosure.portfolio.bridge-not-tracked')}>FX (not tracked) · Taxes (not tracked) · Trading costs (not tracked)</p>
      </Container>

      <label {...cap('control.portfolio.ledger-complete-checkbox')}>
        <input type="checkbox" checked={Boolean(tracking.trackingState?.ledgerComplete)} onChange={(event) => tracking.setLedgerComplete(event.target.checked)} />
        <span>This ledger has every deposit/withdrawal since tracking started</span>
      </label>
      <CashFlowForm capId="control.portfolio.cash-flow-ledger" tracking={tracking} />
    </>
  )
}

function CashFlowForm({ capId, tracking }) {
  const submit = async (event) => {
    event.preventDefault()
    const form = event.currentTarget
    const amount = parseFloat(form.amount.value)
    if (!Number.isFinite(amount) || amount <= 0 || !form.effectiveDate.value) return
    await tracking.recordActivity?.({ type: form.type.value, amount, effectiveDate: form.effectiveDate.value })
    form.reset()
  }
  return (
    <form {...cap(capId)} onSubmit={submit}>
      <label><span>Type</span>
        <select name="type" defaultValue="deposit">
          <option value="deposit">Deposit</option>
          <option value="withdrawal">Withdrawal</option>
          <option value="dividend">Dividend received</option>
          <option value="fee">Fee charged</option>
        </select>
      </label>
      <label><span>Amount</span><input name="amount" type="number" step="0.01" min="0" /></label>
      <label><span>Date</span><input name="effectiveDate" type="date" defaultValue={new Date().toISOString().slice(0, 10)} /></label>
      <button type="submit">Record</button>
    </form>
  )
}

// --- Data view -------------------------------------------------------------------------------
const ANALYTICS_VIEWS = ['overview', 'all', 'algorithm', 'historical']
const ANALYTICS_SCOPES = ['all_history', 'since_algorithm', 'live_algorithm', 'backtest']

function DataView({ Container, analytics, positions, signalMetrics, benchmarks, searchParams, setSearchParams, exportPortfolio }) {
  const analyticsView = ANALYTICS_VIEWS.includes(searchParams.get('analytics')) ? searchParams.get('analytics') : 'overview'
  const scope = ANALYTICS_SCOPES.includes(searchParams.get('scope')) ? searchParams.get('scope') : 'all_history'
  const setParam = (key, value) => {
    const params = new URLSearchParams(searchParams)
    params.set(key, value)
    setSearchParams(params)
  }
  const [exportStatus, setExportStatus] = useState(null)

  const buildSnapshot = () => buildExportSnapshot({
    holdings: { portfolioPositions: positions, actionable: [] },
    analytics,
    benchmarks,
    signalMetrics,
    monteCarlo: null,
    scope,
  })

  const handleCopyMetrics = async () => {
    try {
      await navigator.clipboard.writeText(snapshotToJson(buildSnapshot()))
      setExportStatus('Copied to clipboard')
    } catch {
      setExportStatus('Copy failed')
    }
    setTimeout(() => setExportStatus(null), 2500)
  }

  const handleDownloadSnapshot = () => {
    try {
      const blob = new Blob([snapshotToJson(buildSnapshot())], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = snapshotFilename(scope)
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setExportStatus('Download started')
    } catch {
      setExportStatus('Download failed')
    }
    setTimeout(() => setExportStatus(null), 2500)
  }

  const buckets = signalMetrics ? splitBySampleRequirement(signalMetrics) : []
  const criteria = prospectiveValidation.promotion_criteria_champion_or_challenger || {}

  if (!analytics.available) {
    return <div {...cap('state.portfolio.performance-building')}>Analytics are still building.</div>
  }

  const qualityIssues = positions.length - analytics.enriched.positions.filter((row) => row.currentValue != null).length

  return (
    <>
      <nav {...cap('nav.portfolio.analytics-view-tabs')} aria-label="Analytics views">
        {ANALYTICS_VIEWS.map((item) => (
          <button type="button" key={item} aria-current={analyticsView === item ? 'page' : undefined} onClick={() => setParam('analytics', item)}>{item}</button>
        ))}
      </nav>
      <label {...cap('control.portfolio.analytics-scope')}>
        <span>Scope</span>
        <select value={scope} onChange={(event) => setParam('scope', event.target.value)}>
          <option value="all_history">All history</option>
          <option value="since_algorithm">Since activation</option>
          <option value="live_algorithm">Live only</option>
          <option value="backtest">Backtest period</option>
        </select>
      </label>
      <p {...cap('disclosure.portfolio.scope-rationale')}>Scope narrows which daily returns feed every measure below; it does not change the chart on the Performance view.</p>

      <div>
        <button type="button" {...cap('export.data-overview.copy-metrics')} onClick={handleCopyMetrics}>Copy all metrics to clipboard</button>
        <button type="button" {...cap('export.data-overview.download-json')} onClick={handleDownloadSnapshot}>Download all metrics (JSON)</button>
        <button type="button" {...cap('export.portfolio.export-portfolio-json')} onClick={exportPortfolio}>Export portfolio</button>
        {exportStatus && <p role="status" {...cap('state.export.data-overview-status')}>{exportStatus}</p>}
      </div>

      <p {...cap('figure.portfolio.move-explanation')}>
        {analytics.twrComparison ? `Your holdings moved ${signedPct(analytics.twrComparison.portfolio.returnPct, 2)} over the selected period.` : 'Not enough history yet to explain the recent move.'}
      </p>
      <p {...cap('figure.portfolio.auto-overview-line')}>
        {analytics.performance?.available
          ? `Sharpe ${ratio(analytics.performance.sharpe)} · max drawdown ${pct(analytics.performance.maxDrawdown)} over ${analytics.performance.observations} daily returns.`
          : analytics.performance?.reason || 'Insufficient daily history to summarize.'}
      </p>

      <Container {...cap('figure.portfolio.holdings-data-quality')}>
        {qualityIssues > 0
          ? <p {...cap('state.portfolio.holdings-quality-count')}>{qualityIssues} of {positions.length} need attention</p>
          : <p>All {positions.length} holdings have a current price.</p>}
      </Container>

      <Container {...cap('figure.portfolio.fund-cost-overview')}>
        {analytics.fundCost ? <p>Weighted average expense ratio: {pct(analytics.fundCost.expenseRatioPct, 3)} across {analytics.fundCost.fundCount} funds.</p> : <p>No fund holdings with a published expense ratio.</p>}
      </Container>

      <Container {...cap('figure.portfolio.time-to-valid-metric')}>
        {analytics.timeToValid?.available && !analytics.timeToValid.met
          ? <p>{analytics.timeToValid.observations} of {analytics.timeToValid.floor} observations collected.</p>
          : analytics.timeToValid?.met ? <p>{analytics.timeToValid.observations} of {analytics.timeToValid.floor} observations collected — floor met.</p> : <p>{analytics.timeToValid?.reason}</p>}
      </Container>

      <p {...cap('disclosure.portfolio.sample-note')}>
        {analytics.performance?.available ? `${analytics.performance.observations} daily returns` : 'Sample size unavailable'}
      </p>

      <Container {...cap('figure.portfolio.performance-metrics-overview')} aria-label="Risk and performance">
        <Metric capId="metric.report.annualized-return" label="Annualized return" display={signedPct(analytics.performance?.annualizedReturn)} value={analytics.performance?.annualizedReturn} reads="Compound growth projected to 252 trading days over the displayed sample." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />
        <Metric capId="metric.report.sharpe-naive" label="Sharpe ratio" display={ratio(analytics.performance?.sharpe)} value={analytics.performance?.sharpe} reads="Return above the risk-free rate per unit of total volatility." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />
        <Metric capId="metric.report.sortino-naive" label="Sortino ratio" display={ratio(analytics.performance?.sortino)} value={analytics.performance?.sortino} reads="Return above the risk-free rate per unit of downside deviation." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />
        <Metric capId="metric.report.calmar" label="Calmar ratio" display={ratio(analytics.performance?.calmar)} value={analytics.performance?.calmar} reads="Annualized return divided by the magnitude of maximum drawdown." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />
        <Metric capId="metric.report.maximum-drawdown" label="Maximum drawdown" display={pct(analytics.performance?.maxDrawdown)} value={analytics.performance?.maxDrawdown} reads="Worst peak-to-trough decline in the selected sample." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />
        <Metric capId="metric.report.current-drawdown" label="Current drawdown" display={pct(analytics.performance?.currentDrawdown)} value={analytics.performance?.currentDrawdown} reads="Current distance below the sample high-water mark." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />
        <Metric capId="metric.report.information-ratio-spy" label="Information ratio" display={ratio(analytics.performance?.informationRatio)} value={analytics.performance?.informationRatio} reads="Annualized active return per unit of tracking error against the S&P 500." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.performance?.reason} />

        <Metric capId="metric.report.longest-underwater" label="Longest underwater" display={duration(analytics.underwater?.longestUnderwaterDays)} value={analytics.underwater?.longestUnderwaterDays} reads="Longest wall-clock span below a prior high-water mark." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.underwater?.reason} />
        <Metric capId="metric.report.current-underwater" label="Current underwater duration" display={duration(analytics.underwater?.currentUnderwaterDays)} value={analytics.underwater?.currentUnderwaterDays} reads="Wall-clock time since the current high-water mark, or zero when at a high." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.underwater?.reason} />
        <Metric capId="metric.report.deepest-drawdown" label="Deepest drawdown" display={pct(analytics.underwater?.deepestDrawdownPct)} value={analytics.underwater?.deepestDrawdownPct} reads="Deepest peak-to-trough decline, retained as the canonical duplicate of maximum drawdown." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.underwater?.reason} />
        <Metric capId="metric.report.recovery-deepest" label="Recovery time for deepest drawdown" display={duration(analytics.underwater?.recoveryDaysForDeepest)} value={analytics.underwater?.recoveryDaysForDeepest} reads="Wall-clock time from the high preceding the deepest drawdown until recovery." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.underwater?.available ? 'The deepest drawdown has not recovered yet.' : analytics.underwater?.reason} />

        <Metric capId="metric.report.acceleration" label="Acceleration" display={analytics.acceleration?.available ? `${analytics.acceleration.acceleration >= 0 ? '+' : '−'}${Math.abs(analytics.acceleration.acceleration).toFixed(2)}σ` : null} value={analytics.acceleration?.acceleration} reads="Change between recent and prior beta-adjusted excess-return windows." cadence="quarterly legs" source="portfolioAcceleration.js" unavailableReason={analytics.acceleration?.reason} />
        <Metric capId="metric.report.acceleration-pct" label="Acceleration percentage-point change" display={signedPct(analytics.acceleration?.accelerationPct)} value={analytics.acceleration?.accelerationPct} reads="Recent beta-adjusted excess return less the prior comparable window, in percentage points." cadence="quarterly legs" source="portfolioAcceleration.js" unavailableReason={analytics.acceleration?.reason} />
        <Metric capId="metric.report.acceleration-beta" label="Acceleration fitted beta" display={ratio(analytics.acceleration?.beta)} value={analytics.acceleration?.beta} reads="Beta fitted on the two acceleration legs used to adjust benchmark return." cadence="quarterly legs" source="portfolioAcceleration.js" unavailableReason={analytics.acceleration?.reason} />

        <Metric capId="metric.report.up-capture-spy" label="Up capture" display={pct(analytics.capture?.upCapturePct)} value={analytics.capture?.upCapturePct} reads="Fraction of the S&P 500's gains kept, over the periods it rose." cadence="daily" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.capture?.reason} />
        <Metric capId="metric.report.down-capture-spy" label="Down capture" display={pct(analytics.capture?.downCapturePct)} value={analytics.capture?.downCapturePct} reads="Fraction of the S&P 500's losses taken, over the periods it fell." cadence="daily" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.capture?.reason} />
        <Metric capId="metric.report.capture-spread-spy" label="Capture spread" display={signedPct(analytics.capture?.captureSpread)} value={analytics.capture?.captureSpread} reads="Up capture minus down capture -- how much more upside is kept than downside taken." cadence="daily" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.capture?.reason} />

        <Metric capId="metric.report.batting-average-spy" label="Batting average" display={pct(analytics.batting?.battingAveragePct)} value={analytics.batting?.battingAveragePct} reads="Share of calendar months in which the portfolio beat the S&P 500." cadence="monthly" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.batting?.reason} />
        <Metric capId="metric.report.batting-wins-losses" label="Winning / losing months" display={analytics.batting?.available ? `${analytics.batting.wins} of ${analytics.batting.months}` : null} value={analytics.batting?.wins} reads="Count of calendar months beating the benchmark, out of months measured." cadence="monthly" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.batting?.reason} />
        <Metric capId="metric.report.relative-payoff" label="Win/loss size ratio" display={analytics.batting?.winLossRatio != null ? `${ratio(analytics.batting.winLossRatio)}×` : null} value={analytics.batting?.winLossRatio} reads="Average benchmark-relative winning month divided by the magnitude of an average losing month." cadence="monthly" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.batting?.reason} />
        <Metric capId="metric.report.average-relative-win" label="Average winning-month excess" display={signedPct(analytics.batting?.averageWinPct)} value={analytics.batting?.averageWinPct} reads="Average benchmark-relative return in winning calendar months." cadence="monthly" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.batting?.reason} />
        <Metric capId="metric.report.average-relative-loss" label="Average losing-month excess" display={signedPct(analytics.batting?.averageLossPct)} value={analytics.batting?.averageLossPct} reads="Average benchmark-relative return in losing calendar months." cadence="monthly" source="portfolioBenchmarkComparison.js" unavailableReason={analytics.batting?.reason} />

        <Metric capId="metric.report.week-excess" label="Past week vs index" display={signedPct(windowFor(analytics.shortTerm, 7)?.excessPct)} value={windowFor(analytics.shortTerm, 7)?.excessPct} reads="Portfolio return less benchmark return over the past 7 calendar days." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 7)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.month-excess" label="Past month vs index" display={signedPct(windowFor(analytics.shortTerm, 30)?.excessPct)} value={windowFor(analytics.shortTerm, 30)?.excessPct} reads="Portfolio return less benchmark return over the past 30 calendar days." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 30)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.week-portfolio-return" label="Week portfolio return" display={signedPct(windowFor(analytics.shortTerm, 7)?.portfolioPct)} value={windowFor(analytics.shortTerm, 7)?.portfolioPct} reads="Portfolio's own return over the past 7 calendar days." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 7)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.week-benchmark-return" label="Week index return" display={signedPct(windowFor(analytics.shortTerm, 7)?.benchmarkPct)} value={windowFor(analytics.shortTerm, 7)?.benchmarkPct} reads="S&P 500 return over the past 7 calendar days." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 7)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.month-portfolio-return" label="Month portfolio return" display={signedPct(windowFor(analytics.shortTerm, 30)?.portfolioPct)} value={windowFor(analytics.shortTerm, 30)?.portfolioPct} reads="Portfolio's own return over the past 30 calendar days." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 30)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.month-benchmark-return" label="Month index return" display={signedPct(windowFor(analytics.shortTerm, 30)?.benchmarkPct)} value={windowFor(analytics.shortTerm, 30)?.benchmarkPct} reads="S&P 500 return over the past 30 calendar days." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 30)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.noise-floor-week" label="Noise floor (week)" display={windowFor(analytics.shortTerm, 7)?.noiseFloorPct != null ? `±${pct(Math.abs(windowFor(analytics.shortTerm, 7).noiseFloorPct))}` : null} value={windowFor(analytics.shortTerm, 7)?.noiseFloorPct} reads="One standard error of ordinary benchmark-relative movement over a week." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 7)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.noise-floor-month" label="Noise floor (month)" display={windowFor(analytics.shortTerm, 30)?.noiseFloorPct != null ? `±${pct(Math.abs(windowFor(analytics.shortTerm, 30).noiseFloorPct))}` : null} value={windowFor(analytics.shortTerm, 30)?.noiseFloorPct} reads="One standard error of ordinary benchmark-relative movement over a month." cadence="daily" source="portfolioShortTermView.js" unavailableReason={windowFor(analytics.shortTerm, 30)?.reason || analytics.shortTerm?.reason} />
        <Metric capId="metric.report.excess-streak" label="Current streak" display={analytics.shortTerm?.available ? `${analytics.shortTerm.streak.observations} ${analytics.shortTerm.streak.direction}` : null} value={analytics.shortTerm?.streak?.observations} reads="Consecutive overlapping observations on the same side of the benchmark." cadence="daily" source="portfolioShortTermView.js" unavailableReason={analytics.shortTerm?.reason} />
        <Metric capId="metric.report.recent-tracking-risk" label="Recent tracking risk" display={pct(analytics.shortTerm?.recentTrackingRiskPct)} value={analytics.shortTerm?.recentTrackingRiskPct} reads="Annualized volatility of benchmark-relative movement over the recent window." cadence="daily" source="portfolioShortTermView.js" unavailableReason={analytics.shortTerm?.reason} />
        <Metric capId="metric.report.baseline-tracking-risk" label="Baseline tracking risk" display={pct(analytics.shortTerm?.baselineTrackingRiskPct)} value={analytics.shortTerm?.baselineTrackingRiskPct} reads="Annualized volatility of benchmark-relative movement over the longer baseline window." cadence="daily" source="portfolioShortTermView.js" unavailableReason={analytics.shortTerm?.reason} />
        <Metric capId="metric.report.short-term-beta" label="Fast-read fitted beta" display={ratio(analytics.shortTerm?.beta)} value={analytics.shortTerm?.beta} reads="Beta fitted over the short-term view baseline and used for beta-adjusted excess returns." cadence="daily" source="portfolioShortTermView.js" unavailableReason={analytics.shortTerm?.reason} />

        <Metric capId="metric.report.portfolio-volatility" label="Portfolio volatility" display={pct(analytics.risk?.portfolioVolatilityPct)} value={analytics.risk?.portfolioVolatilityPct} reads="Annualized covariance-based volatility of current portfolio weights." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.risk?.reason} />
        <Metric capId="metric.report.tracking-error-selected" label="Tracking error (selected benchmark)" display={pct(analytics.risk?.trackingErrorPct)} value={analytics.risk?.trackingErrorPct} reads="Volatility of portfolio returns relative to the S&P 500." cadence="daily" source="portfolioAnalytics.js" unavailableReason={analytics.risk?.available ? 'Overlapping selected-benchmark returns are required.' : analytics.risk?.reason} />
        <Metric capId="metric.report.active-share" label="Active share" display={pct(analytics.risk?.activeSharePct)} value={analytics.risk?.activeSharePct} reads="Share of current portfolio weights that differs from benchmark constituent weights." cadence="point-in-time" source="portfolioAnalytics.js" unavailableReason="Benchmark constituent weights are required." />
        <Metric capId="metric.report.marginal-risk-contribution" label="Marginal contribution to risk" display={pct(analytics.risk?.contributions?.[0]?.marginalContributionToRiskPct)} value={analytics.risk?.contributions?.[0]?.marginalContributionToRiskPct} reads={`Marginal portfolio volatility change associated with ${analytics.risk?.contributions?.[0]?.ticker || 'the largest'} holding's weight.`} cadence="point-in-time" source="portfolioAnalytics.js" unavailableReason={analytics.risk?.reason} />
        <Metric capId="metric.report.standalone-volatility" label="Standalone holding volatility" display={pct(analytics.risk?.contributions?.[0]?.standaloneVolatilityPct)} value={analytics.risk?.contributions?.[0]?.standaloneVolatilityPct} reads={`Annualized volatility of ${analytics.risk?.contributions?.[0]?.ticker || 'the largest holding'} before portfolio correlations.`} cadence="point-in-time" source="portfolioAnalytics.js" unavailableReason={analytics.risk?.reason} />
      </Container>

      {analyticsView === 'algorithm' && (
        <>
          <Container {...cap('figure.portfolio.prospective-clock')}>
            <span>0 / {criteria.minimum_periods || 24} periods</span>
            <p>Starts {prospectiveValidation.harness_start_date}. Thresholds were frozen {prospectiveValidation.frozen_at}; UI changes do not reset the clock.</p>
          </Container>
          <Container {...cap('chart.portfolio.signal-metrics-embed')}>
            {signalMetrics ? (
              <>
                <span data-testid="portfolio-metrics-summary">{signalMetrics.summary?.ready} ready · {signalMetrics.summary?.breached} breached of {signalMetrics.summary?.total}</span>
                {buckets.map((bucket) => {
                  const openGroups = defaultOpenGroups(bucket)
                  return (
                    <section key={bucket.id} data-metrics-bucket={bucket.id}>
                      <h4>{bucket.title}</h4>
                      {bucket.groups.map((group) => {
                        const groupMessage = sharedStatusMessage(group.metrics)
                        return (
                          <details key={group.id} open={openGroups.has(group.id)}>
                            <summary>{group.letter ? `${group.letter} — ` : ''}{group.title || group.id} ({group.metrics.length})</summary>
                            {groupMessage && <p>{groupMessage}</p>}
                            {group.metrics.map((metric) => <WallLabel key={metric.id} metric={metric} />)}
                          </details>
                        )
                      })}
                    </section>
                  )
                })}
              </>
            ) : <p>Signal metrics unavailable — run pipeline/signal_metrics.py.</p>}
          </Container>
        </>
      )}

      {/* Deferred: chart.portfolio.monte-carlo-panel-embed, chart.portfolio.scenario-sensitivity,
          chart.portfolio.rolling-sharpe-historical (each needs a real per-medium chart renderer
          via manifest.loadRenderer(), not implemented in this pass), figure.portfolio.all-metrics-tearsheet
          and figure.portfolio.baseline-comparison (need the full cross-period evidence-comparison model). */}
    </>
  )
}

function windowFor(shortTerm, days) {
  return shortTerm?.windows?.find((row) => row.days === days) || null
}

// --- Diversification view --------------------------------------------------------------------
function DiversificationView({ Container, analytics, positions }) {
  if (!positions.length) {
    return <div {...cap('state.diversification.no-holdings')}>Add portfolio holdings before calculating diversification.</div>
  }
  if (!analytics.available || !analytics.diversification?.available) {
    return <div {...cap('state.diversification.loading')} role="status">Loading…</div>
  }

  const div = analytics.diversification
  const risk = analytics.risk
  const factorModels = analytics.factor?.models || []
  const full = factorModels.at(-1)
  const industries = industryAllocation(analytics.enriched.positions)
  const correlation = div.correlation

  return (
    <>
      <Container {...cap('figure.diversification.score-dial')}>
        <span>You hold {div.rawHoldingCount} positions / {ratio(div.effectiveBets)} effective bets</span>
      </Container>
      <Container {...cap('figure.diversification.effective-bet-summary')}>
        <span>Raw holdings {div.rawHoldingCount} · Effective bets {ratio(div.effectiveBets)} · Effective holdings {ratio(div.effectiveHoldings)} (1/HHI)</span>
      </Container>
      {div.provisional && <p {...cap('disclosure.diversification.provisional-label')}>Provisional score</p>}
      <p {...cap('disclosure.diversification.coverage-note')}>Coverage: {pct(div.coveragePct)} of entered positions have a current price. This score is descriptive, not a recommendation.</p>

      <Container {...cap('chart.diversification.score-components')}>
        <label>Holding breadth<progress max="100" value={div.components.holdingHhi ?? 0} /></label>
        <label>Sector breadth<progress max="100" value={div.components.sectorHhi ?? 0} /></label>
        <label>Industry breadth<progress max="100" value={div.components.industryHhi ?? 0} /></label>
      </Container>

      <Container {...cap('chart.diversification.sector-allocation')}>
        <ul>{div.sectorExposures?.slice(0, 8).map((row) => <li key={row.label}><span>{row.label}</span><span>{pct(row.pct)}</span></li>)}</ul>
        {div.lookThrough?.unavailableEtfs?.length > 0 && (
          <p {...cap('disclosure.diversification.unresolved-etf-lookthrough')}>${div.lookThrough.unresolvedDollars.toFixed(0)} is unresolved ETF exposure because published look-through data is unavailable.</p>
        )}
      </Container>

      <Container {...cap('figure.diversification.industry-concentration')}>
        <ul>{industries.slice(0, 8).map((row) => <li key={row.label}><span>{row.label}</span><span>{pct(row.pct)}</span></li>)}</ul>
      </Container>

      <Container {...cap('chart.diversification.holdings-by-allocation')}>
        <ul>{div.weights?.slice(0, 10).map((row) => <li key={row.ticker}><span>{row.ticker}</span><span style={{ width: `${row.pct}%` }} /><span>{pct(row.pct)}</span></li>)}</ul>
      </Container>

      {risk?.available ? (
        <Container {...cap('figure.diversification.risk-decomposition')}>
          <table>
            <thead><tr><th scope="col">Holding</th><th scope="col">Weight</th><th scope="col">Share of risk</th></tr></thead>
            <tbody>
              {risk.contributions.map((row) => <tr key={row.ticker}><th scope="row">{row.ticker}</th><td>{pct(row.weightPct)}</td><td>{pct(row.percentContributionToRisk)}</td></tr>)}
            </tbody>
          </table>
          <p>Expected shortfall 95%: {pct(risk.expectedShortfall95Pct)} · Tracking error: {pct(risk.trackingErrorPct) || '–'} · Active share: {pct(risk.activeSharePct) || '–'}</p>
          {risk.activeSharePct == null && <p {...cap('disclosure.diversification.active-share-coverage')}>Active share is shown only with sufficient benchmark constituent coverage.</p>}
        </Container>
      ) : <p {...cap('state.diversification.risk-reason')}>{risk?.reason}</p>}

      {full?.available ? (
        <Container {...cap('chart.diversification.factor-loadings')}>
          <table>
            <thead><tr><th scope="col">Factor</th><th scope="col">Loading</th><th scope="col">Std. error</th></tr></thead>
            <tbody>
              {Object.entries(full.loadings).map(([key, value]) => (
                <tr key={key}><th scope="row">{key.replace('_', ' ')}</th><td>{ratio(value)}</td><td>{ratio(full.standardErrors[key])}</td></tr>
              ))}
            </tbody>
          </table>
          <p>Alpha {signedPct(full.alphaAnnualPct)} · t-stat {ratio(full.alphaTStatistic)} · R² {pct(full.rSquared * 100)}</p>
          {Math.abs(full.alphaTStatistic || 0) < 2 && <p {...cap('disclosure.diversification.multiple-testing-hurdle')}>The registered multiple-testing evidence hurdle is a positive t-statistic above 3.</p>}
        </Container>
      ) : <p {...cap('state.diversification.factor-history-accumulating')}>Factor history is accumulating — {analytics.factor?.reason}</p>}

      <Container aria-label="Diversification metrics">
        <Metric capId="metric.report.diversification-score" label="Diversification score" display={String(div.score)} value={div.score} reads="Weighted composite of holding, sector, and industry breadth plus effective bets and diversification ratio." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.raw-holding-count" label="Raw holdings" display={String(div.rawHoldingCount)} value={div.rawHoldingCount} reads="Count of currently priced holdings." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.hhi" label="Herfindahl concentration" display={div.hhi != null ? div.hhi.toFixed(3) : null} value={div.hhi} reads="Sum of squared position weights; lower is more diversified." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.effective-holdings" label="Effective holdings" display={ratio(div.effectiveHoldings)} value={div.effectiveHoldings} reads="Reciprocal of the Herfindahl index (1/HHI)." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.effective-bets" label="Effective bets" display={ratio(div.effectiveBets)} value={div.effectiveBets} reads="Eigenvalue-concentration measure of independent return-driving bets across holdings." cadence="per refresh" source="portfolioAnalytics.js" unavailableReason={!correlation?.available ? correlation?.reason : null} />
        <Metric capId="metric.report.diversification-ratio" label="Diversification ratio" display={ratio(div.diversificationRatio)} value={div.diversificationRatio} reads="Weighted average standalone volatility divided by realized portfolio volatility." cadence="per refresh" source="portfolioAnalytics.js" unavailableReason={!correlation?.available ? correlation?.reason : null} />
        <Metric capId="metric.report.holding-breadth-score" label="Holding HHI score component" display={ratio(div.components.holdingHhi)} value={div.components.holdingHhi} reads="Score component from position-level Herfindahl concentration." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.sector-breadth-score" label="Sector HHI score component" display={ratio(div.components.sectorHhi)} value={div.components.sectorHhi} reads="Score component from look-through sector Herfindahl concentration." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.industry-breadth-score" label="Industry HHI score component" display={ratio(div.components.industryHhi)} value={div.components.industryHhi} reads="Score component from industry Herfindahl concentration." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.pairwise-correlation" label="Pairwise correlation matrix" display={correlation?.available ? `${correlation.tickers.length} holdings · ${correlation.observations} common days` : null} value={correlation?.observations} reads="Correlation matrix of daily returns across covered holdings, used for effective bets and portfolio volatility." cadence="daily" source="portfolioAnalytics.js" unavailableReason={correlation?.reason} />
        <Metric capId="metric.report.sector-allocation" label="Look-through sector allocation" display={div.sectorExposures?.[0] ? `${div.sectorExposures[0].label} ${pct(div.sectorExposures[0].pct)}` : null} value={div.sectorExposures?.[0]?.pct} reads="Largest look-through sector exposure, resolving ETF holdings to their underlying sector weights." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.industry-allocation" label="Industry concentration" display={industries[0] ? `${industries[0].label} ${pct(industries[0].pct)}` : null} value={industries[0]?.pct} reads="Largest single-industry concentration among priced holdings." cadence="per refresh" source="portfolioAnalytics.js (industry classification)" />
        <Metric capId="metric.report.position-weight" label="Holdings by allocation" display={div.weights?.[0] ? `${div.weights[0].ticker} ${pct(div.weights[0].pct)}` : null} value={div.weights?.[0]?.pct} reads="Largest single-position weight as a share of priced portfolio value." cadence="per refresh" source="portfolioAnalytics.js" />
        <Metric capId="metric.report.expected-shortfall-95" label="Expected shortfall 95%" display={pct(risk?.expectedShortfall95Pct)} value={risk?.expectedShortfall95Pct} reads="Average historical daily loss beyond the 95th-percentile tail." cadence="daily" source="portfolioAnalytics.js" unavailableReason={risk?.reason} />
        <Metric capId="metric.report.risk-contribution" label="Share of total risk" display={risk?.contributions?.[0] ? `${risk.contributions[0].ticker} ${pct(risk.contributions[0].percentContributionToRisk)}` : null} value={risk?.contributions?.[0]?.percentContributionToRisk} reads="Euler component contribution as a share of total portfolio volatility, largest holding shown." cadence="daily" source="portfolioAnalytics.js" unavailableReason={risk?.reason} />
        <Metric capId="metric.report.factor-alpha" label="Annualized factor alpha" display={full?.available ? signedPct(full.alphaAnnualPct) : null} value={full?.alphaAnnualPct} reads="Intercept after removing Fama-French 5 + momentum factor returns." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.factor-alpha-t" label="Factor alpha t-statistic" display={full?.available ? ratio(full.alphaTStatistic) : null} value={full?.alphaTStatistic} reads="Newey-West HAC t-statistic on the factor-model alpha; the registered evidence hurdle is above 3." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.factor-r-squared" label="Factor R²" display={full?.available ? pct(full.rSquared * 100) : null} value={full?.rSquared} reads="Share of monthly return variance explained by the factor model." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.market-loading" label="Market factor loading" display={full?.available ? ratio(full.loadings.market_excess) : null} value={full?.loadings?.market_excess} reads="Sensitivity to the market-excess factor." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.size-loading" label="Size factor loading" display={full?.available ? ratio(full.loadings.size) : null} value={full?.loadings?.size} reads="Sensitivity to the size (SMB) factor." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.value-loading" label="Value factor loading" display={full?.available ? ratio(full.loadings.value) : null} value={full?.loadings?.value} reads="Sensitivity to the value (HML) factor." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.profitability-loading" label="Profitability factor loading" display={full?.available ? ratio(full.loadings.profitability) : null} value={full?.loadings?.profitability} reads="Sensitivity to the profitability (RMW) factor." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.investment-loading" label="Investment factor loading" display={full?.available ? ratio(full.loadings.investment) : null} value={full?.loadings?.investment} reads="Sensitivity to the investment (CMA) factor." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.momentum-loading" label="Momentum factor loading" display={full?.available ? ratio(full.loadings.momentum) : null} value={full?.loadings?.momentum} reads="Sensitivity to the momentum (UMD) factor." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
        <Metric capId="metric.report.factor-loading-se" label="Factor loading standard errors" display={full?.available ? Object.entries(full.standardErrors).map(([key, value]) => `${key.replace('_', ' ')} ${ratio(value)}`).join(' · ') : null} value={null} reads="Newey-West HAC standard error for each factor loading above." cadence="monthly" source="factorAnalytics.js" unavailableReason={analytics.factor?.reason} />
      </Container>

      {!div.warnings?.length && <p {...cap('state.diversification.no-concentration-warnings')}>No concentration warnings in covered holdings.</p>}
      <p {...cap('disclosure.diversification.lookthrough-provisional')}>Missing look-through stays visible as unavailable and makes the result provisional.</p>

      {/* Deferred: chart.diversification.correlation-heatmap (NxN visual matrix), chart.diversification.theme-exposure-grid
          (needs the theme registry keyed by ticker), detail.diversification.info-tags, state.diversification.theme-exposure-unavailable. */}
    </>
  )
}

// --- Insights view -------------------------------------------------------------------------
/**
 * `chart.insights.vs-indexes-chart` is inherently multi-series (account vs. up to four
 * indexes), but the shared chart-renderer contract's `line` type takes one `series`/`values`
 * per call (see `useRenderer.js`'s doc comment and Classic's adapter, which renders exactly one
 * line per call). Rather than inventing an unsupported multi-line prop shape, this renders one
 * `renderer.line()` call per line (small multiples: the account, then each index) inside a
 * single labeled container -- honest against the contract, at the cost of one shared-axis chart.
 */
function InsightsView({ Container, benchmarkReport, benchmarkReportLoading, alternateBenchmarkSnapshot, positions, portfolio, analytics, tracking, preferences, currentUser }) {
  const renderer = useRenderer()
  const [shareStatus, setShareStatus] = useState('')

  if (benchmarkReportLoading || !currentUser) {
    return <div {...cap('state.insights.loading')} role="status" aria-live="polite">Loading…</div>
  }
  if (!positions.length) {
    return <div {...cap('state.insights.no-holdings')} role="status">Add portfolio holdings to see how you're doing versus the market and as a trader.</div>
  }

  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  const diversification = analytics.diversification
  const holdingsSeriesFull = analytics.holdingsSeriesFull

  const marketHistories = MARKET_DESTINATIONS.map((destination) => {
    const history = benchmarkReport?.histories?.[destination.symbol]
    return history ? { ...destination, dates: history.dates, closes: history.closes } : null
  }).filter(Boolean)

  const benchmarkLabel = preferences.defaultBenchmark
  const benchmarkHistory = benchmarkLabel === 'SPY'
    ? (analytics.spySeries ? { dates: analytics.spySeries.dates, closes: analytics.spySeries.values } : null)
    : benchmarkHistoryFromSnapshot(alternateBenchmarkSnapshot)
  const holdingsRanked = benchmarkHistory ? holdingsVsBenchmark(portfolio.positions, benchmarkHistory) : []

  const trades = tradeStats(tracking.activities)
  const timingSignals = portfolio.positions
    .map((position) => ({ position, timing: purchaseTimingSignal(position, position.priceInfo?.history) }))
    .filter((row) => row.timing.available)

  const holdingsPeriod = selectPeriod(holdingsSeriesFull, '1Y') || selectPeriod(holdingsSeriesFull, 'All')
  const actualDaily = snapshotDailySeries(tracking.snapshots)
  // The first plotted date must exist in the account and every benchmark -- seeding each
  // hypothetical index with the account value on that exact date guarantees the caption's
  // "same dollars" claim is literally true before later deposits/withdrawals are replayed.
  const comparisonStartIndex = actualDaily.dates.findIndex((date) => marketHistories.every((history) => history.dates.includes(date)))
  const comparisonAccount = comparisonStartIndex >= 0 ? {
    dates: actualDaily.dates.slice(comparisonStartIndex),
    values: actualDaily.values.slice(comparisonStartIndex),
  } : null
  const comparisonStartDate = comparisonAccount?.dates[0]
  const comparisonStartingValue = comparisonAccount?.values[0]
  const marketShadows = comparisonStartDate ? marketHistories.map((history) => ({
    ...history,
    ...benchmarkShadowPortfolio(tracking.activities, history, { startDate: comparisonStartDate, startingValue: comparisonStartingValue }),
  })).filter((shadow) => shadow.available) : []
  const chartComparison = marketShadows.length === marketHistories.length && marketShadows.length > 0
    ? alignManyForChart(comparisonAccount, marketShadows)
    : null

  const mood = portfolioMood({ returnPct: holdingsPeriod?.returnPct, diversificationScore: diversification?.score, streak: { available: false } })
  const todayMove = latestMarketDayReturn(holdingsSeriesFull)
  const topMover = portfolio.positions
    .map((position) => ({ ...position, dailyMovePct: latestMove(position.priceInfo?.history) }))
    .filter((position) => position.dailyMovePct != null)
    .sort((a, b) => Math.abs(b.dailyMovePct) - Math.abs(a.dailyMovePct))[0]

  const shareRecap = async () => {
    const lines = [
      `${mood.emoji} ${mood.label} – my portfolio today`,
      todayMove ? `Today: ${signedPct(todayMove.returnPct, 2)} (${money(Math.abs(todayMove.dollarReturn))})` : null,
      holdingsPeriod ? `Current-holdings return: ${signedPct(holdingsPeriod.returnPct, 1)}` : null,
      topMover ? `Biggest mover: ${topMover.ticker} ${signedPct(topMover.dailyMovePct, 1)}` : null,
    ].filter(Boolean)
    const text = lines.join('\n')
    try {
      if (navigator.share) { await navigator.share({ text, title: 'My portfolio today' }); return }
      await navigator.clipboard.writeText(text)
      setShareStatus('Copied to clipboard.')
      setTimeout(() => setShareStatus(''), 3000)
    } catch {
      // Share was cancelled or clipboard access was denied -- nothing to recover from here.
    }
  }

  const chartState = canonicalArtifactState({ status: 'success' })
  const chartConfidence = confidenceOf({})

  return (
    <>
      <Container {...cap('figure.insights.mood-hero')} aria-label="Today's recap">
        <span aria-hidden="true">{mood.emoji}</span>
        <h2>{mood.label}</h2>
        <p>{mood.blurb}{mood.note ? ` ${mood.note}` : ''}</p>
        <button type="button" {...cap('export.insights.share-today')} onClick={shareRecap}>Share today</button>
        <dl>
          <div><dt>Today</dt><dd>{todayMove ? `${signedPct(todayMove.returnPct, 2)} · ${money(Math.abs(todayMove.dollarReturn))}` : '–'}</dd></div>
          <div><dt>Current-holdings return</dt><dd>{holdingsPeriod ? signedPct(holdingsPeriod.returnPct, 1) : 'Unavailable'}</dd></div>
          <div><dt>Invested value</dt><dd>{money(portfolio.totalValue)}</dd></div>
          {topMover && <div><dt>Today's biggest mover</dt><dd>{topMover.ticker} {signedPct(topMover.dailyMovePct, 1)}</dd></div>}
        </dl>
        {shareStatus && <p role="status" aria-live="polite">{shareStatus}</p>}
      </Container>

      <p {...cap('disclosure.insights.index-comparison-methodology')}>
        Starts every index with your account's exact recorded value on the first shared date, then applies each later settled
        deposit or withdrawal using its actual amount and effective date. Pending transfers are excluded.
      </p>

      {chartComparison ? (
        <Container {...cap('chart.insights.vs-indexes-chart')} aria-label="You vs. the major indexes">
          <div>
            <span>Your recorded account</span>
            {renderer && renderer.line({
              metricId: 'insights-vs-indexes-account',
              series: chartComparison.dates.map((date, index) => ({ x: date, y: chartComparison.primaryValues[index] })),
              domain: { min: Math.min(...chartComparison.primaryValues), max: Math.max(...chartComparison.primaryValues) },
              unit: 'USD', thresholds: [], annotations: [], state: chartState, confidence: chartConfidence,
              ariaLabel: 'Your recorded account value over time', width: 720, height: 200,
            })}
          </div>
          {marketShadows.map((shadow, index) => {
            const values = chartComparison.comparisonValues[index]
            return (
              <div key={shadow.symbol}>
                <span>{shadow.label} ({shadow.symbol})</span>
                {renderer && renderer.line({
                  metricId: `insights-vs-indexes-${shadow.symbol}`,
                  series: chartComparison.dates.map((date, dateIndex) => ({ x: date, y: values[dateIndex] })),
                  domain: { min: Math.min(...values), max: Math.max(...values) },
                  unit: 'USD', thresholds: [], annotations: [], state: chartState, confidence: chartConfidence,
                  ariaLabel: `${shadow.label} shadow portfolio -- same dollars, same dates, invested in ${shadow.symbol} instead`,
                  width: 720, height: 120,
                })}
              </div>
            )
          })}
          <p {...cap('disclosure.insights.chart-caption')}>
            {`Every line starts at ${money(chartComparison.primaryValues[0])} on ${chartComparison.dates[0]}. On the latest shared recording date, your account is ${money(chartComparison.primaryValues.at(-1))}; applying the same settled deposit and withdrawal amounts on the same dates would leave ${marketShadows.map((shadow, index) => `${money(chartComparison.comparisonValues[index].at(-1))} in ${shadow.symbol}`).join(' · ')}. Pending transfers are excluded.`}
          </p>
        </Container>
      ) : (
        <div {...cap('state.insights.not-enough-history')} role="status">Not enough history yet — cash-flow-aware comparison needs two shared market dates</div>
      )}

      {holdingsRanked.length > 0 && (
        <Container {...cap('figure.insights.holdings-vs-benchmark')} aria-label={`Holdings vs. ${benchmarkLabel}`}>
          <ul>
            {holdingsRanked.map((row) => (
              <li key={row.ticker}>
                <strong>{row.ticker}</strong>
                <span>{signedPct(row.stockReturnPct, 1)} vs {signedPct(row.benchmarkReturnPct, 1)} {benchmarkLabel}</span>
                <b>{signedPct(row.deltaPct, 1)}</b>
              </li>
            ))}
          </ul>
        </Container>
      )}

      <Container {...cap('figure.insights.as-a-trader')} aria-label="As a trader">
        {trades.available ? (
          <dl>
            <div><dt>Win rate</dt><dd>{trades.winRate.toFixed(0)}% ({trades.winCount}W / {trades.lossCount}L of {trades.count} closed)</dd></div>
            <div><dt>Average win</dt><dd>{trades.avgWin != null ? money(trades.avgWin) : '–'}</dd></div>
            <div><dt>Average loss</dt><dd>{trades.avgLoss != null ? money(Math.abs(trades.avgLoss)) : '–'}</dd></div>
            <div><dt>Best trade</dt><dd>{money(trades.best.amount)} ({trades.best.note || 'No note'})</dd></div>
            <div><dt>Worst trade</dt><dd>{money(trades.worst.amount)} ({trades.worst.note || 'No note'})</dd></div>
          </dl>
        ) : <p {...cap('state.insights.no-realized-sales')}>Record position sales on the Portfolio page to build realized win-rate and trade statistics.</p>}
      </Container>

      <Container {...cap('figure.insights.purchase-timing')} aria-label="Purchase timing">
        {timingSignals.length ? (
          <ul>
            {timingSignals.map(({ position, timing }) => (
              <li key={position.id || position.ticker}><strong>{position.ticker}</strong> <span>{timing.label}</span> <b>{signedPct(timing.deltaPct, 1)}</b></li>
            ))}
          </ul>
        ) : <p {...cap('state.insights.entry-timing-insufficient')}>Not enough price history around your purchase dates yet to judge entry timing.</p>}
      </Container>
    </>
  )
}

// --- Finances view --------------------------------------------------------------------------
const FINANCES_TABS = ['budget', 'pools', 'retirement']

function FinancesView({ Container, report, benchmarkReport, benchmarkReportLoading, positions, analytics, preferences, finances, searchParams, setSearchParams }) {
  const renderer = useRenderer()
  const tab = FINANCES_TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : 'budget'
  const setTab = (next) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params)
  }

  const [budgetForm, setBudgetForm] = useState({ name: '', amount: '', type: 'expense' })
  const [poolForm, setPoolForm] = useState({ name: '', percent: '' })
  const [depositAmount, setDepositAmount] = useState('')
  const [accountForm, setAccountForm] = useState({ name: '', type: ACCOUNT_TYPES[0].key })
  const [selectedAccountId, setSelectedAccountId] = useState(null)
  const [returnTargetDraft, setReturnTargetDraft] = useState(null)
  const [returnTargetCommitted, setReturnTargetCommitted] = useState(null)

  const minimumRetirementAge = Math.max(
    projectionConfig.lever_ranges.retirement_age.minimum,
    finances.settings.currentAge + projectionConfig.minimum_years_until_retirement,
  )
  const maximumRetirementAge = Math.max(projectionConfig.lever_ranges.retirement_age.maximum, minimumRetirementAge)
  const retirementAge = Math.min(maximumRetirementAge, Math.max(minimumRetirementAge, finances.settings.retireAge))

  const portfolioValue = useMemo(() => currentPortfolioValue(positions, report), [positions, report])
  const budgetSummary = useMemo(() => summarizeBudget(finances.budgetItems), [finances.budgetItems])
  const totalPoolBalance = finances.pools.reduce((sum, pool) => sum + (pool.balance || 0), 0)
  const accounts = finances.accounts || []
  const totalAnnualFromAccounts = accounts.reduce((sum, account) => sum + (account.annualContribution || 0), 0)
  const monthlyFromAccounts = totalAnnualFromAccounts / 12

  const projectionSource = useMemo(() => {
    const benchmarkSymbol = preferences.defaultBenchmark
    const benchmark = benchmarkReport?.histories?.[benchmarkSymbol]
    return selectProjectionReturnSource(analytics.holdingsSeriesFull, benchmark, benchmarkSymbol, fidelityProjectionBaseline(positions))
  }, [analytics.holdingsSeriesFull, benchmarkReport, positions, preferences.defaultBenchmark])
  const returnTargetRange = useMemo(() => annualReturnTargetRange(projectionSource), [projectionSource])
  const savedAnnualReturnTargetPct = normalizeAnnualReturnTarget(finances.settings.planningAnnualReturnTargetPct, projectionSource)
  const annualReturnTargetPct = returnTargetCommitted ?? savedAnnualReturnTargetPct
  const displayedAnnualReturnTargetPct = returnTargetDraft ?? annualReturnTargetPct

  useEffect(() => {
    setReturnTargetDraft(savedAnnualReturnTargetPct)
    setReturnTargetCommitted(savedAnnualReturnTargetPct)
  }, [savedAnnualReturnTargetPct])

  const projectionInput = useMemo(() => projectionSource.available ? {
    monthlyReturns: applyAllocationAssumption(
      projectionSource.returns,
      finances.settings.allocationAggressiveness || projectionConfig.allocation_default,
      annualReturnTargetPct / 100,
    ),
    currentBalance: finances.settings.currentSavings,
    monthlyContribution: finances.settings.monthlyContribution,
    monthlyWithdrawal: finances.settings.monthlyWithdrawal,
    inflationPct: finances.settings.inflationPct,
    accumulationMonths: Math.max(projectionConfig.months_per_year, (retirementAge - finances.settings.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: Math.max(0, (finances.settings.retirementEndAge - retirementAge) * projectionConfig.months_per_year),
  } : null, [annualReturnTargetPct, finances.settings, projectionSource, retirementAge])
  const projection = useProjectionSimulation(projectionInput)
  const depositPreview = splitAmount(parseFloat(depositAmount) || 0, finances.pools)
  const projectedMedian = projection.result?.retirementPercentiles?.p50
  const successProbability = projection.result?.successProbability

  if (benchmarkReportLoading || finances.loading) {
    return <div {...cap('state.finances.loading')} role="status" aria-live="polite">Loading…</div>
  }

  const handleAddBudgetItem = (event) => {
    event.preventDefault()
    if (!budgetForm.name || !budgetForm.amount) return
    finances.addBudgetItem(budgetForm)
    setBudgetForm({ name: '', amount: '', type: budgetForm.type })
  }
  const handleAddPool = (event) => {
    event.preventDefault()
    if (!poolForm.name || !poolForm.percent) return
    finances.addPool(poolForm)
    setPoolForm({ name: '', percent: '' })
  }
  const handleDeposit = (event) => {
    event.preventDefault()
    const amount = parseFloat(depositAmount)
    if (!amount || !finances.pools.length) return
    finances.depositToPools(splitAmount(amount, finances.pools).map(({ id, share }) => ({ id, share })))
    setDepositAmount('')
  }
  const handleAddAccount = (event) => {
    event.preventDefault()
    if (!accountForm.name || !accountForm.type) return
    finances.addAccount(accountForm)
    setAccountForm({ name: '', type: accountForm.type })
  }
  const commitReturnTarget = () => {
    const next = normalizeAnnualReturnTarget(displayedAnnualReturnTargetPct, projectionSource)
    if (next === annualReturnTargetPct) return
    setReturnTargetCommitted(next)
    finances.updateSettings({ planningAnnualReturnTargetPct: next })
  }

  const projectionState = projectionArtifactState(projection.loading, projection.result, projection.error)
  const projectionConfidence = confidenceOf({})
  const incomeItems = finances.budgetItems.filter((item) => item.type === 'income')
  const expenseItems = finances.budgetItems.filter((item) => item.type === 'expense')
  const accountsWithLimits = accounts.filter((account) => getAnnualLimit(account.type, finances.settings.currentAge))

  return (
    <>
      <Container {...cap('figure.finances.kpi-row')} aria-label="Finances overview">
        <div>
          <span>Monthly Leftover</span>
          <strong>{financeMoney(budgetSummary.leftover)}</strong>
          <small>{financeMoney(budgetSummary.income)} income − {financeMoney(budgetSummary.expenses)} expenses</small>
        </div>
        <div>
          <span>Saved in Pools</span>
          <strong>{financeMoney(totalPoolBalance, 2)}</strong>
          <small>{finances.pools.length} pool{finances.pools.length === 1 ? '' : 's'}</small>
        </div>
        <div>
          <span>Median at Retirement</span>
          <strong>{projection.loading ? <span {...cap('state.finances.simulating')}>Simulating…</span> : financeMoney(projectedMedian)}</strong>
          <small {...cap('disclosure.finances.bootstrap-paths-note')}>From {projectionConfig.paths.toLocaleString()} historical return paths</small>
        </div>
      </Container>

      <nav {...cap('nav.finances.tabs')} aria-label="Finances views">
        {FINANCES_TABS.map((item) => (
          <button type="button" key={item} aria-current={tab === item ? 'page' : undefined} onClick={() => setTab(item)}>
            {item === 'budget' ? 'Budget' : item === 'pools' ? 'Auto-Split Pools' : 'Retirement'}
          </button>
        ))}
      </nav>

      {tab === 'budget' && (
        <Container aria-label="Budget">
          <form {...cap('control.finances.budget-add-form')} onSubmit={handleAddBudgetItem}>
            <label><span>Name</span><input type="text" placeholder="Paycheck" value={budgetForm.name} required onChange={(e) => setBudgetForm({ ...budgetForm, name: e.target.value })} /></label>
            <label><span>Monthly amount</span><input type="number" step="0.01" placeholder="500" value={budgetForm.amount} required onChange={(e) => setBudgetForm({ ...budgetForm, amount: e.target.value })} /></label>
            <label><span>Type</span>
              <select value={budgetForm.type} onChange={(e) => setBudgetForm({ ...budgetForm, type: e.target.value })}>
                <option value="income">Income</option>
                <option value="expense">Expense</option>
              </select>
            </label>
            <button type="submit">Add</button>
          </form>

          <div aria-label="Income">
            {incomeItems.length === 0 && <p {...cap('state.finances.no-income-items')}>No income items yet.</p>}
            {incomeItems.map((item) => (
              <div key={item.id}><span>{item.name}</span><span>{financeMoney(item.amount)}</span><button type="button" onClick={() => finances.removeBudgetItem(item.id)}>Remove</button></div>
            ))}
          </div>
          <div aria-label="Expenses">
            {expenseItems.length === 0 && <p {...cap('state.finances.no-expense-items')}>No expense items yet.</p>}
            {expenseItems.map((item) => (
              <div key={item.id}><span>{item.name}</span><span>{financeMoney(item.amount)}</span><button type="button" onClick={() => finances.removeBudgetItem(item.id)}>Remove</button></div>
            ))}
          </div>

          <p>
            <strong>{financeMoney(budgetSummary.leftover)}</strong> left over each month.{' '}
            <button type="button" {...cap('action.finances.use-as-retirement-contribution')} onClick={() => finances.updateSettings({ monthlyContribution: Math.max(0, Math.round(budgetSummary.leftover)) })}>
              Use as retirement contribution
            </button>
          </p>
        </Container>
      )}

      {tab === 'pools' && (
        <>
          <Container aria-label="Add a pool">
            <form {...cap('control.finances.pool-add-form')} onSubmit={handleAddPool}>
              <label><span>Name</span><input type="text" placeholder="Emergency fund" value={poolForm.name} required onChange={(e) => setPoolForm({ ...poolForm, name: e.target.value })} /></label>
              <label><span>Percent</span><input type="number" step="1" min="0" max="100" placeholder="30" value={poolForm.percent} required onChange={(e) => setPoolForm({ ...poolForm, percent: e.target.value })} /></label>
              <button type="submit">Add pool</button>
            </form>
          </Container>

          {finances.pools.length === 0 ? (
            <p {...cap('state.finances.no-pools')}>Add at least one pool to start splitting deposits.</p>
          ) : (
            <Container {...cap('chart.finances.pool-bars')} aria-label="Pool allocation">
              {renderer && renderer.bar({
                metricId: 'finances-pool-allocation',
                values: finances.pools.map((pool) => Number(pool.percent) || 0),
                unit: '%',
                thresholds: [],
                annotations: [],
                state: canonicalArtifactState({ status: 'success' }),
                confidence: confidenceOf({}),
                ariaLabel: 'Pool allocation, percent of each deposit',
                width: 320, height: 120,
              })}
              {finances.pools.map((pool) => (
                <div key={pool.id}>
                  <span>{pool.name}</span><span>{pool.percent}%</span>
                  <span>{financeMoney(pool.balance, 2)} saved</span>
                  <button type="button" onClick={() => finances.removePool(pool.id)}>Remove</button>
                </div>
              ))}
            </Container>
          )}

          <Container aria-label="Log a deposit">
            <form {...cap('control.finances.deposit-split-preview')} onSubmit={handleDeposit}>
              <label><span>Amount to split</span>
                <input type="number" step="0.01" placeholder={budgetSummary.leftover > 0 ? budgetSummary.leftover.toFixed(0) : '0'} value={depositAmount} onChange={(e) => setDepositAmount(e.target.value)} />
              </label>
              <button type="submit" disabled={!finances.pools.length}>Add to pools</button>
            </form>
            {depositPreview.some((pool) => pool.share > 0) && (
              <div>{depositPreview.map((pool) => <span key={pool.id}>{pool.name}: {financeMoney(pool.share, 2)}</span>)}</div>
            )}
          </Container>
        </>
      )}

      {tab === 'retirement' && (
        <>
          <Container {...cap('control.finances.retirement-assumptions')} aria-label="Assumptions">
            <label><span>Current age</span><input type="number" value={finances.settings.currentAge} onChange={(e) => finances.updateSettings({ currentAge: parseInt(e.target.value, 10) || 0 })} /></label>
            <label><span>Retirement age</span><input type="number" min={minimumRetirementAge} max={maximumRetirementAge} value={retirementAge} onChange={(e) => finances.updateSettings({ retireAge: parseInt(e.target.value, 10) || 0 })} /></label>
            <label><span>Inflation %</span><input type="number" step="0.1" value={finances.settings.inflationPct} onChange={(e) => finances.updateSettings({ inflationPct: parseFloat(e.target.value) || 0 })} /></label>
            <label><span>Current savings</span><input type="number" step="1" value={finances.settings.currentSavings} onChange={(e) => finances.updateSettings({ currentSavings: parseFloat(e.target.value) || 0 })} /></label>
            <label><span>Monthly contribution</span><input type="number" step="1" value={finances.settings.monthlyContribution} onChange={(e) => finances.updateSettings({ monthlyContribution: parseFloat(e.target.value) || 0 })} /></label>
            <label><span>Plan through age</span><input type="number" min={finances.settings.retireAge} max="120" value={finances.settings.retirementEndAge} onChange={(e) => finances.updateSettings({ retirementEndAge: parseInt(e.target.value, 10) || projectionConfig.default_retirement_end_age })} /></label>
            <label><span>Monthly retirement spending</span><input type="number" min="0" step="100" value={finances.settings.monthlyWithdrawal} onChange={(e) => finances.updateSettings({ monthlyWithdrawal: parseFloat(e.target.value) || 0 })} /></label>
            <label {...cap('control.finances.return-target-slider')}>
              <span>Annual return target</span><strong>{formatAnnualReturnTarget(displayedAnnualReturnTargetPct)}</strong>
              <input type="range" min={returnTargetRange.minimumPct} max={returnTargetRange.maximumPct} step={returnTargetRange.stepPct} value={displayedAnnualReturnTargetPct}
                onChange={(event) => setReturnTargetDraft(Number(event.target.value))} onPointerUp={commitReturnTarget} onKeyUp={commitReturnTarget} />
              <small {...cap('disclosure.finances.return-target-evidence-range')}>
                Sets the dotted median for retirement. {returnTargetRange.evidence ? `${returnTargetRange.evidence.lowerPct.toFixed(2)}% year to date to ${returnTargetRange.evidence.upperPct.toFixed(2)}% trailing one year.` : 'Historical returns set the uncertainty around your target.'}
              </small>
            </label>
            <button type="button" {...cap('action.finances.sync-savings-from-portfolio')} onClick={() => finances.updateSettings({ currentSavings: Math.round(portfolioValue) })}>
              Sync current savings from portfolio ({financeMoney(portfolioValue)})
            </button>
          </Container>

          <Container aria-label="Retirement and investing accounts">
            <p {...cap('disclosure.finances.irs-limit-note')}>
              Track contribution room against the 2026 IRS limits for each account. Roth IRA room can phase out at higher incomes. This assumes you're eligible.
            </p>
            {accounts.length > 0 && (
              <nav {...cap('nav.finances.account-tabs')} aria-label="Retirement accounts">
                {accounts.map((account) => (
                  <button type="button" key={account.id} aria-current={(selectedAccountId || accounts[0]?.id) === account.id ? 'page' : undefined}
                    onClick={() => { setSelectedAccountId(account.id); document.getElementById(`finance-account-${account.id}`)?.scrollIntoView({ block: 'nearest' }) }}>
                    {account.name} ({accountTypeLabel(account.type)})
                  </button>
                ))}
              </nav>
            )}
            <form {...cap('control.finances.account-add-form')} onSubmit={handleAddAccount}>
              <label><span>Name</span><input type="text" placeholder="Fidelity 401(k)" value={accountForm.name} required onChange={(e) => setAccountForm({ ...accountForm, name: e.target.value })} /></label>
              <label><span>Type</span>
                <select value={accountForm.type} onChange={(e) => setAccountForm({ ...accountForm, type: e.target.value })}>
                  {ACCOUNT_TYPES.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
              <button type="submit">Add account</button>
            </form>

            {accounts.length === 0 ? (
              <p {...cap('state.finances.no-accounts')}>Add a 401(k), IRA, HSA, or taxable account to track contributions toward the annual max.</p>
            ) : (
              accounts.map((account) => {
                const limit = getAnnualLimit(account.type, finances.settings.currentAge)
                const contributed = account.annualContribution || 0
                const usedPct = limit ? Math.min(100, (contributed / limit) * 100) : 0
                return (
                  <div key={account.id} id={`finance-account-${account.id}`}>
                    <span>{account.name} · {accountTypeLabel(account.type)}</span>
                    <button type="button" onClick={() => finances.removeAccount(account.id)}>Remove</button>
                    {limit ? (
                      <p>{financeMoney(contributed)} of {financeMoney(limit)} maxed ({usedPct.toFixed(0)}%) · {financeMoney(Math.max(0, limit - contributed))} room left</p>
                    ) : (
                      <p>{financeMoney(contributed)} contributed this year · No IRS cap</p>
                    )}
                    <label><span>Annual contribution</span>
                      <input type="number" step="1" min="0" value={contributed} onChange={(e) => finances.updateAccountContribution(account.id, parseFloat(e.target.value) || 0)} />
                    </label>
                  </div>
                )
              })
            )}

            {accountsWithLimits.length > 0 && (
              <Container {...cap('chart.finances.contribution-room-bars')} aria-label="Contribution room used, percent of IRS limit">
                {renderer && renderer.bar({
                  metricId: 'finances-contribution-room',
                  values: accountsWithLimits.map((account) => Math.min(150, ((account.annualContribution || 0) / getAnnualLimit(account.type, finances.settings.currentAge)) * 100)),
                  unit: '%',
                  domain: { min: 0, max: 150 },
                  thresholds: [{ value: 100, label: 'IRS limit', kind: 'target' }],
                  annotations: [],
                  state: canonicalArtifactState({ status: 'success' }),
                  confidence: confidenceOf({}),
                  ariaLabel: 'Contribution room used, percent of each account\'s IRS limit',
                  width: 320, height: 120,
                })}
              </Container>
            )}

            {accounts.length > 0 && (
              <p>
                <strong>{financeMoney(monthlyFromAccounts, 2)}/mo</strong> equivalent across all accounts ({financeMoney(totalAnnualFromAccounts)}/yr).{' '}
                <button type="button" {...cap('action.finances.use-as-retirement-contribution')} onClick={() => finances.updateSettings({ monthlyContribution: Math.round(monthlyFromAccounts) })}>
                  Use as retirement contribution
                </button>
              </p>
            )}
          </Container>

          <Container {...cap('figure.finances.retirement-kpi-row')} aria-label="Retirement outcome KPIs">
            <div><span>Median at Retirement</span><strong>{projection.loading ? <span {...cap('state.finances.simulating')}>Simulating…</span> : financeMoney(projectedMedian)}</strong></div>
            <div><span>Median in Today's Dollars</span><strong>{financeMoney(projection.result?.retirementPercentilesReal?.p50)}</strong></div>
            <div>
              <span>Savings Last Through Age {finances.settings.retirementEndAge}</span>
              <strong>{successProbability == null ? '–' : `${(successProbability * 100).toFixed(0)}%`}</strong>
              <small>Given {financeMoney(finances.settings.monthlyWithdrawal)} monthly spending</small>
            </div>
          </Container>

          {!projectionSource.available ? (
            <p>{projectionSource.reason || 'Historical monthly returns are not available for this model.'}</p>
          ) : (
            <Container {...cap('chart.finances.projection-panel')} aria-label="Retirement outcome range">
              {fanChartCall(renderer, projection.result, {
                metricId: 'finances-retirement-projection',
                ariaLabel: 'Retirement outcome range, 10th to 90th percentile',
                state: projectionState, confidence: projectionConfidence,
              })}
              <p {...cap('disclosure.finances.dotted-median-note')}>
                The dotted median targets {formatAnnualReturnTarget(annualReturnTargetPct)} annually. Historical monthly returns determine the range around it.
              </p>
              {projection.result?.terminalPercentiles && (
                <dl>
                  {[['p10', '10th'], ['p25', '25th'], ['p50', 'Median'], ['p75', '75th'], ['p90', '90th']].map(([key, label]) => (
                    <div key={key}><dt>{label}</dt><dd>{financeMoney(projection.result.terminalPercentiles[key])}</dd></div>
                  ))}
                </dl>
              )}
            </Container>
          )}
        </>
      )}
    </>
  )
}

// --- Planning view --------------------------------------------------------------------------
function PlanningView({ Container, report, benchmarkReport, benchmarkReportLoading, positions, analytics, preferences, finances, tracking }) {
  const renderer = useRenderer()
  const [draft, setDraft] = useState(null)
  const [committed, setCommitted] = useState(null)
  const [useLiveStrategyReturn, setUseLiveStrategyReturn] = useState(true)
  const [changedLever, setChangedLever] = useState(null)
  const [leverDeltas, setLeverDeltas] = useState({})
  const priorProbability = useRef(null)
  const [goalForm, setGoalForm] = useState({ name: '', targetAmount: projectionConfig.goal_default_amount, targetDate: defaultGoalDate(), poolId: '' })
  const [selectedGoalId, setSelectedGoalId] = useState(null)

  const minimumRetirementAge = Math.max(
    projectionConfig.lever_ranges.retirement_age.minimum,
    finances.settings.currentAge + projectionConfig.minimum_years_until_retirement,
  )
  const maximumRetirementAge = Math.max(projectionConfig.lever_ranges.retirement_age.maximum, minimumRetirementAge)

  const benchmarkSymbol = preferences.defaultBenchmark
  // Reuses the same holdings series the rest of the screen already computed (`analytics`,
  // from `useAnalytics` above) rather than rebuilding it -- one fewer independent read of
  // `priceData`, and it keeps this view's baseline return in step with the Overview panel's.
  const portfolioSeries = analytics.holdingsSeriesFull
  const sinceAlgorithmSeries = useMemo(() => sliceSeriesFrom(portfolioSeries, LIVE_TRACKING_START), [portfolioSeries])
  const riskProfile = useMemo(() => derivePortfolioRiskProfile(sinceAlgorithmSeries, report), [sinceAlgorithmSeries, report])
  const lastActivityAt = useMemo(() => tracking.activities.map((row) => row.recordedAt).filter(Boolean).sort().at(-1) || null, [tracking.activities])
  const calibration = usePortfolioMonteCarloCalibration(riskProfile, lastActivityAt)
  const source = useMemo(() => selectProjectionReturnSource(
    portfolioSeries, benchmarkReport?.histories?.[benchmarkSymbol], benchmarkSymbol, fidelityProjectionBaseline(positions), calibration.riskProfile,
  ), [benchmarkReport, portfolioSeries, positions, benchmarkSymbol, calibration.riskProfile])
  const returnTargetRange = useMemo(() => annualReturnTargetRange(source), [source])

  const currentHoldingsPeriod = selectPeriod(portfolioSeries, 'All')
  const wholeHistoryAnnualReturnPct = currentHoldingsPeriod
    ? annualizeReturnPct(currentHoldingsPeriod.returnPct, currentHoldingsPeriod.startDate, currentHoldingsPeriod.endDate)
    : null
  const liveStrategyAnnualReturnPct = calibration.riskProfile?.available ? calibration.riskProfile.annualReturn * 100 : wholeHistoryAnnualReturnPct
  const liveStrategyReturnWindow = calibration.riskProfile?.available
    ? { startDate: calibration.riskProfile.startDate, endDate: calibration.riskProfile.endDate }
    : currentHoldingsPeriod
  const liveTargetActive = useLiveStrategyReturn && liveStrategyAnnualReturnPct != null
  const effectiveAnnualReturnTargetPct = liveTargetActive
    ? normalizeAnnualReturnTarget(liveStrategyAnnualReturnPct, source)
    : committed?.annualReturnTargetPct

  useEffect(() => {
    if (finances.loading) return
    const next = {
      annualReturnTargetPct: normalizeAnnualReturnTarget(finances.settings.planningAnnualReturnTargetPct, source),
      monthlyContribution: finances.settings.monthlyContribution,
      retirementAge: Math.min(maximumRetirementAge, Math.max(minimumRetirementAge, finances.settings.retireAge)),
      annualWithdrawal: finances.settings.monthlyWithdrawal * projectionConfig.months_per_year,
      allocation: finances.settings.allocationAggressiveness || projectionConfig.allocation_default,
    }
    setDraft(next)
    setCommitted(next)
  }, [finances.loading, maximumRetirementAge, minimumRetirementAge, returnTargetRange.minimumPct, returnTargetRange.maximumPct])

  const adjustedReturns = useMemo(() => source.available && committed
    ? applyAllocationAssumption(source.returns, committed.allocation, effectiveAnnualReturnTargetPct / 100)
    : [], [committed, effectiveAnnualReturnTargetPct, source])
  const input = useMemo(() => source.available && committed ? {
    monthlyReturns: adjustedReturns,
    currentBalance: finances.settings.currentSavings,
    monthlyContribution: committed.monthlyContribution,
    monthlyWithdrawal: committed.annualWithdrawal / projectionConfig.months_per_year,
    inflationPct: finances.settings.inflationPct,
    accumulationMonths: Math.max(1, (committed.retirementAge - finances.settings.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: Math.max(0, (finances.settings.retirementEndAge - committed.retirementAge) * projectionConfig.months_per_year),
  } : null, [adjustedReturns, committed, finances.settings, source.available])
  const projection = useProjectionSimulation(input)
  const contributionAlternative = useProjectionSimulation(input ? { ...input, monthlyContribution: input.monthlyContribution + projectionConfig.contribution_lever_step } : null)
  const probability = projection.result?.successProbability

  const coastFire = useMemo(() => committed ? coastFireStatus({
    currentSavings: finances.settings.currentSavings,
    currentAge: finances.settings.currentAge,
    retirementAge: committed.retirementAge,
    annualReturnPct: effectiveAnnualReturnTargetPct,
    annualWithdrawal: committed.annualWithdrawal,
  }) : { available: false }, [committed, finances.settings.currentSavings, finances.settings.currentAge, effectiveAnnualReturnTargetPct])

  useEffect(() => {
    if (probability == null) return
    if (changedLever && priorProbability.current != null) {
      setLeverDeltas((current) => ({ ...current, [changedLever]: probability - priorProbability.current }))
      setChangedLever(null)
    }
    priorProbability.current = probability
  }, [changedLever, probability])

  const commitLever = (key) => {
    if (!draft || !committed || draft[key] === committed[key]) return
    priorProbability.current = probability
    setChangedLever(key)
    setCommitted({ ...committed, [key]: draft[key] })
    const settingsUpdate = key === 'monthlyContribution' ? { monthlyContribution: draft[key] }
      : key === 'retirementAge' ? { retireAge: draft[key] }
        : key === 'annualWithdrawal' ? { monthlyWithdrawal: draft[key] / projectionConfig.months_per_year }
          : key === 'annualReturnTargetPct' ? { planningAnnualReturnTargetPct: draft[key] }
            : { allocationAggressiveness: draft[key] }
    finances.updateSettings(settingsUpdate)
  }
  const delta = (key) => leverDeltas[key] == null
    ? <span {...cap('state.planning.move-lever-to-compare')}>Move this lever to compare outcomes</span>
    : <span>{`${leverDeltas[key] >= 0 ? '+' : '−'}${Math.abs(leverDeltas[key] * 100).toFixed(0)} percentage points from its prior setting`}</span>

  const selectedGoal = finances.goals.find((goal) => goal.id === selectedGoalId) || finances.goals[0]
  const selectedPool = finances.pools.find((pool) => pool.id === selectedGoal?.poolId)
  const goalMonths = selectedGoal?.targetDate
    ? Math.max(1, Math.round((Date.parse(selectedGoal.targetDate) - Date.now()) / (projectionConfig.milliseconds_per_day * projectionConfig.days_per_year / projectionConfig.months_per_year)))
    : null
  const goalInput = selectedGoal && goalMonths && source.available ? {
    monthlyReturns: adjustedReturns,
    currentBalance: selectedPool?.balance || 0,
    monthlyContribution: (committed?.monthlyContribution || 0) * ((selectedPool?.percent || 0) / 100),
    accumulationMonths: goalMonths,
    withdrawalMonths: 0,
    inflationPct: finances.settings.inflationPct,
    targetAmount: selectedGoal.targetAmount,
  } : null
  const goalProjection = useProjectionSimulation(goalInput)

  if (benchmarkReportLoading || finances.loading || !draft || !committed) {
    return <div {...cap('state.planning.loading')} role="status" aria-live="polite">Loading…</div>
  }

  const success = probability == null ? null : probability * 100
  const verdict = successBand(probability || 0)
  const alternativeSuccess = contributionAlternative.result?.successProbability
  const addGoal = (event) => {
    event.preventDefault()
    finances.addGoal(goalForm)
    setGoalForm({ ...goalForm, name: '' })
  }

  const gaugeState = projectionArtifactState(projection.loading, projection.result, projection.error)
  const gaugeConfidence = confidenceOf({})
  const calibrationValues = calibration.riskProfile?.available ? [
    { label: 'Sharpe', value: calibration.riskProfile.sharpe },
    { label: 'Sortino', value: calibration.riskProfile.sortino },
    { label: 'Lo-adjusted Sortino', value: calibration.riskProfile.loAdjusted ? calibration.riskProfile.loAdjustedSortino : 0 },
    { label: 'Calmar', value: calibration.riskProfile.calmar },
  ] : []
  const sequencePaths = sequenceRiskPaths()
  const sequenceState = canonicalArtifactState({ status: 'success' })
  const sequenceConfidence = confidenceOf({})

  return (
    <>
      <section aria-label="Plan verdict">
        <Container {...cap('chart.planning.success-probability-gauge')} aria-label="Probability of success">
          {renderer && renderer.dial({
            metricId: 'planning-success-probability',
            values: [success ?? 0],
            domain: { min: 0, max: 100 },
            unit: '%',
            thresholds: projectionConfig.success_bands.map((band) => ({ value: band.minimum * 100, label: band.label, kind: 'band' })),
            annotations: [],
            state: gaugeState,
            confidence: gaugeConfidence,
            ariaLabel: success == null ? 'Success probability unavailable' : `Success probability ${success.toFixed(0)} percent`,
            width: 220, height: 220,
          })}
          <strong>{projection.loading && success == null ? <span {...cap('state.planning.projection-running')}>…</span> : success == null ? 'N/A' : `${success.toFixed(0)}%`}</strong>
          <span>probability of success</span>
        </Container>
        <div>
          <span className={`planning-band-${verdict.label.toLowerCase().replaceAll(' ', '-')}`}>{verdict.label}</span>
          <h2>{verdict.label === 'On track' ? 'Your current plan clears the survival threshold.' : verdict.label === 'Needs attention' ? 'Your plan works in some paths, but the margin is thin.' : 'Your current assumptions exhaust savings in too many paths.'}</h2>
          <p {...cap('figure.planning.contribution-lever-comparison')}>
            {alternativeSuccess == null || success == null ? 'Testing the most effective contribution lever.' : `Raising monthly contributions by ${financeMoney(projectionConfig.contribution_lever_step)} moves this from ${success.toFixed(0)}% to ${(alternativeSuccess * 100).toFixed(0)}%.`}
          </p>
          <small {...cap('disclosure.planning.historical-paths-count')}>{(projection.result?.pathCount || projectionConfig.paths).toLocaleString()} historical paths through age {finances.settings.retirementEndAge}</small>
        </div>
      </section>

      <section {...cap('figure.planning.dotted-median-target-panel')} aria-labelledby="planning-baseline-title">
        <span>Dotted median target</span><h2 id="planning-baseline-title">{formatAnnualReturnTarget(effectiveAnnualReturnTargetPct)} annual</h2>
        <p {...cap('disclosure.planning.assumption-not-forecast')}>
          {liveTargetActive
            ? `Your current-holdings return, annualized from ${liveStrategyReturnWindow?.startDate} to ${liveStrategyReturnWindow?.endDate}${calibration.riskProfile?.available ? ' -- the same window and calculation behind your Sharpe, Sortino, and Calmar ratios' : ''}. Cash transfers are not part of this series. This is a planning assumption, not a forecast.`
            : returnTargetRange.evidence ? `Your ${returnTargetRange.evidence.lowerPct.toFixed(2)}% year-to-date return and ${returnTargetRange.evidence.upperPct.toFixed(2)}% trailing one-year return set the evidence range. Move the slider to choose the annual target. This is a planning assumption, not a forecast.` : 'Move the slider to choose the annual target. Historical monthly volatility and return ordering determine the shaded estimates around it. This is a planning assumption, not a forecast.'}
        </p>
        <label {...cap('control.planning.track-current-holdings')}>
          <input type="checkbox" checked={useLiveStrategyReturn} disabled={liveStrategyAnnualReturnPct == null} onChange={(e) => setUseLiveStrategyReturn(e.target.checked)} />
          Track my current-holdings return
          {liveStrategyAnnualReturnPct == null && <span {...cap('state.planning.two-dated-values-needed')}> -- unavailable until there are at least two dated market values</span>}
        </label>
      </section>

      <section aria-labelledby="planning-calibration-title">
        <span>Monte Carlo calibration</span><h2 id="planning-calibration-title">{calibration.riskProfile?.available ? 'Calibrated to your risk-adjusted return ratios' : 'Waiting on enough daily history'}</h2>
        {calibration.riskProfile?.available ? (
          <Container {...cap('chart.planning.monte-carlo-calibration')} aria-label="Calibration ratios">
            {renderer && renderer.profile({
              metricId: 'planning-monte-carlo-calibration',
              values: calibrationValues,
              annotations: [],
              state: canonicalArtifactState({ status: 'success' }),
              confidence: confidenceOf({}),
              ariaLabel: 'Sharpe, Sortino, Lo-adjusted Sortino, and Calmar ratios driving the simulation',
              width: 320, height: 220,
            })}
            {!calibration.riskProfile.loAdjusted && <p {...cap('disclosure.planning.lo-sortino-insufficient')}>Lo-adjusted Sortino — Insufficient</p>}
            <p {...cap('disclosure.planning.distribution-solved-algebraically')}>
              The simulated distribution's mean and volatility are solved algebraically from these ratios, not resampled from your literal daily path.
            </p>
            <p {...cap('disclosure.planning.last-calibrated')}>
              {calibration.calibratedAt ? `Last calibrated ${calibration.calibratedAt.slice(0, 10)} from ${calibration.riskProfile.observations} daily returns through ${calibration.riskProfile.endDate}.` : 'Calibrating now.'}{' '}
              {calibration.stale ? `A new calibration is due${calibration.staleReason ? ` (${calibration.staleReason})` : ''} and will run automatically the next time you open this page.` : `Holds steady until your next ${calibration.refreshLabel} or a new deposit, so day-to-day price moves don't reshuffle the plan.`}
            </p>
            <button type="button" {...cap('action.planning.recalibrate')} onClick={calibration.recalibrate} disabled={calibration.loading}>Recalibrate now</button>
          </Container>
        ) : (
          <p {...cap('state.planning.waiting-on-history')}>{riskProfile.reason || 'At least 20 daily portfolio observations are required before the simulation can calibrate to your own Sharpe, Sortino, and Calmar ratios. Until then, the model falls back to benchmark-derived history.'}</p>
        )}
      </section>

      <section {...cap('figure.planning.coast-fire-panel')} aria-labelledby="planning-coast-fire-title">
        <span>Coast FIRE</span><h2 id="planning-coast-fire-title">Can you stop contributing today?</h2>
        <label {...cap('control.planning.track-coast-fire')}>
          <input type="checkbox" checked={Boolean(finances.settings.coastFireEnabled)} onChange={(event) => finances.updateSettings({ coastFireEnabled: event.target.checked })} />
          Track Coast FIRE status
        </label>
        {finances.settings.coastFireEnabled && (coastFire.available ? (
          <>
            <span>{coastFire.isCoasting ? 'Coasting' : 'Not coasting'}</span>
            <dl>
              <div><dt>Target at retirement</dt><dd>{financeMoney(coastFire.targetAmount)}</dd></div>
              <div><dt>Needed today to coast</dt><dd>{financeMoney(coastFire.requiredTodayAmount)}</dd></div>
              <div><dt>Current savings, grown to age {committed.retirementAge}</dt><dd>{financeMoney(coastFire.projectedBalance)}</dd></div>
            </dl>
            <p {...cap('disclosure.planning.assumption-not-forecast')}>
              {coastFire.isCoasting
                ? `Your current ${financeMoney(finances.settings.currentSavings)} balance, compounding at ${formatAnnualReturnTarget(effectiveAnnualReturnTargetPct)} with no further contributions, clears ${financeMoney(coastFire.targetAmount)} by age ${committed.retirementAge}. You could stop contributing today and still coast to this plan's retirement target.`
                : `At ${formatAnnualReturnTarget(effectiveAnnualReturnTargetPct)} with no further contributions, your current ${financeMoney(finances.settings.currentSavings)} balance reaches ${financeMoney(coastFire.projectedBalance)} by age ${committed.retirementAge} -- short of the ${financeMoney(coastFire.targetAmount)} target. Coasting from here needs ${financeMoney(coastFire.requiredTodayAmount)} saved today, ${financeMoney(Math.max(0, coastFire.requiredTodayAmount - finances.settings.currentSavings))} more than you have now.`}
              {' '}This is a planning assumption, not a forecast.
            </p>
          </>
        ) : <p {...cap('state.planning.set-retirement-age-first')}>Set a retirement age and an annual retirement withdrawal above to see this.</p>)}
      </section>

      <section {...cap('figure.planning.lever-deltas')} aria-label="Live levers">
        <span>Live levers</span><h2>Change the plan, then release to resimulate</h2>
        <label {...cap('control.planning.return-target-lever')}>
          <span>Annual return target <strong>{formatAnnualReturnTarget(liveTargetActive ? effectiveAnnualReturnTargetPct : draft.annualReturnTargetPct)}</strong></span>
          <input type="range" disabled={liveTargetActive} min={returnTargetRange.minimumPct} max={returnTargetRange.maximumPct} step={returnTargetRange.stepPct}
            value={liveTargetActive ? effectiveAnnualReturnTargetPct : draft.annualReturnTargetPct}
            onChange={(event) => setDraft({ ...draft, annualReturnTargetPct: Number(event.target.value) })}
            onPointerUp={() => commitLever('annualReturnTargetPct')} onKeyUp={() => commitLever('annualReturnTargetPct')} />
          <small>{liveTargetActive ? 'Following your current-holdings return -- turn off tracking above to set a custom target.' : <>Dotted median target. {returnTargetRange.evidence ? `${returnTargetRange.evidence.lowerPct.toFixed(2)}% year to date to ${returnTargetRange.evidence.upperPct.toFixed(2)}% trailing one year. ` : ''}{delta('annualReturnTargetPct')}</>}</small>
        </label>
        <label {...cap('control.planning.contribution-lever')}>
          <span>Monthly contribution <strong>{financeMoney(draft.monthlyContribution)}</strong></span>
          <input type="range" min={projectionConfig.lever_ranges.monthly_contribution.minimum} max={projectionConfig.lever_ranges.monthly_contribution.maximum} step={projectionConfig.lever_ranges.monthly_contribution.step}
            value={draft.monthlyContribution} onChange={(event) => setDraft({ ...draft, monthlyContribution: Number(event.target.value) })}
            onPointerUp={() => commitLever('monthlyContribution')} onKeyUp={() => commitLever('monthlyContribution')} />
          <small>{delta('monthlyContribution')}</small>
        </label>
        <label {...cap('control.planning.retirement-age-lever')}>
          <span>Target retirement age <strong>{draft.retirementAge}</strong></span>
          <input type="range" min={minimumRetirementAge} max={maximumRetirementAge} step={projectionConfig.lever_ranges.retirement_age.step}
            value={draft.retirementAge} onChange={(event) => setDraft({ ...draft, retirementAge: Number(event.target.value) })}
            onPointerUp={() => commitLever('retirementAge')} onKeyUp={() => commitLever('retirementAge')} />
          <small>Available from age {minimumRetirementAge}. {delta('retirementAge')}</small>
        </label>
        <label {...cap('control.planning.withdrawal-lever')}>
          <span>Annual retirement withdrawal <strong>{financeMoney(draft.annualWithdrawal)}</strong></span>
          <input type="range" min={projectionConfig.lever_ranges.annual_withdrawal.minimum} max={projectionConfig.lever_ranges.annual_withdrawal.maximum} step={projectionConfig.lever_ranges.annual_withdrawal.step}
            value={draft.annualWithdrawal} onChange={(event) => setDraft({ ...draft, annualWithdrawal: Number(event.target.value) })}
            onPointerUp={() => commitLever('annualWithdrawal')} onKeyUp={() => commitLever('annualWithdrawal')} />
          <small>In today's dollars. {delta('annualWithdrawal')}</small>
        </label>
        <label {...cap('control.planning.aggressiveness-select')}>
          <span>Allocation aggressiveness <strong>{projectionConfig.allocation_assumptions[draft.allocation].label}</strong></span>
          <select value={draft.allocation} onChange={(event) => {
            const allocation = event.target.value
            setDraft({ ...draft, allocation })
            setCommitted({ ...committed, allocation })
            priorProbability.current = probability
            setChangedLever('allocation')
            finances.updateSettings({ allocationAggressiveness: allocation })
          }}>
            {Object.entries(projectionConfig.allocation_assumptions).map(([key, assumption]) => <option value={key} key={key}>{assumption.label}: {assumption.annual_volatility_pct}% volatility around your target</option>)}
          </select>
          <small>{delta('allocation')}</small>
        </label>
        {projection.result?.runtimeMs != null && <p {...cap('state.planning.updated-in-ms')}>Updated in {projection.result.runtimeMs.toFixed(0)} ms</p>}
      </section>

      {source.available ? (
        <Container {...cap('chart.planning.projection-fan-chart')} aria-label="Long-range outcome distribution">
          {fanChartCall(renderer, projection.result, {
            metricId: 'planning-projection-fan',
            ariaLabel: 'Long-range outcome distribution, 10th to 90th percentile',
            state: gaugeState,
            confidence: gaugeConfidence,
          })}
          <p {...cap('disclosure.planning.assumption-not-forecast')}>
            {`The chart runs from now through age ${finances.settings.retirementEndAge}. The dotted median targets ${formatAnnualReturnTarget(effectiveAnnualReturnTargetPct)} annually${liveTargetActive ? ', your current-holdings return with transfers excluded' : ''} and the shaded bands are estimates around it.`}
          </p>
        </Container>
      ) : <p>{source.reason}</p>}

      <Container {...cap('chart.planning.sequence-risk-panel')} aria-label="Sequence risk">
        <h2>Same average, different ending</h2>
        <div>
          <span>Gains first</span>
          {renderer && renderer.line({
            metricId: 'planning-sequence-favorable',
            series: sequencePaths.favorable.map((value, index) => ({ x: index, y: value })),
            domain: { min: 0, max: Math.max(...sequencePaths.favorable, ...sequencePaths.unfavorable) },
            unit: 'USD', thresholds: [], annotations: [], state: sequenceState, confidence: sequenceConfidence,
            ariaLabel: `Gains-first sequence, ending at ${financeMoney(sequencePaths.favorable.at(-1))}`, width: 320, height: 140,
          })}
          <strong>{financeMoney(sequencePaths.favorable.at(-1))}</strong>
        </div>
        <div>
          <span>Losses first</span>
          {renderer && renderer.line({
            metricId: 'planning-sequence-unfavorable',
            series: sequencePaths.unfavorable.map((value, index) => ({ x: index, y: value })),
            domain: { min: 0, max: Math.max(...sequencePaths.favorable, ...sequencePaths.unfavorable) },
            unit: 'USD', thresholds: [], annotations: [], state: sequenceState, confidence: sequenceConfidence,
            ariaLabel: `Losses-first sequence, ending at ${financeMoney(sequencePaths.unfavorable.at(-1))}`, width: 320, height: 140,
          })}
          <strong>{financeMoney(sequencePaths.unfavorable.at(-1))}</strong>
        </div>
        <p>Both paths use the same returns and the same average. Withdrawals after early losses leave less capital available for the later recovery.</p>
      </Container>

      <section {...cap('figure.planning.goals-section')} aria-label="Goals">
        <span>Goals</span><h2>Retirement is one goal among several</h2>
        <form {...cap('control.planning.goal-form')} onSubmit={addGoal}>
          <label><span>Goal name</span><input required placeholder="Home down payment" value={goalForm.name} onChange={(event) => setGoalForm({ ...goalForm, name: event.target.value })} /></label>
          <label><span>Target amount</span><input required type="number" min="1" value={goalForm.targetAmount} onChange={(event) => setGoalForm({ ...goalForm, targetAmount: event.target.value })} /></label>
          <label><span>Target date</span><input required type="date" value={goalForm.targetDate} onChange={(event) => setGoalForm({ ...goalForm, targetDate: event.target.value })} /></label>
          <label><span>Funding pool</span>
            <select value={goalForm.poolId} onChange={(event) => setGoalForm({ ...goalForm, poolId: event.target.value })}>
              <option value="">No linked pool</option>
              {finances.pools.map((pool) => <option value={pool.id} key={pool.id}>{pool.name}</option>)}
            </select>
          </label>
          <button type="submit">Add goal</button>
        </form>
        {finances.goals.length ? (
          <div>
            {finances.goals.map((goal) => (
              <button type="button" key={goal.id} aria-current={selectedGoal?.id === goal.id ? 'true' : undefined} onClick={() => setSelectedGoalId(goal.id)}>
                <span>{goal.name}<small>{goal.targetDate}</small></span><strong>{financeMoney(goal.targetAmount)}</strong>
              </button>
            ))}
          </div>
        ) : <p>Add a named goal and connect it to one of your Finances pools.</p>}
        {selectedGoal && (
          <div>
            <span>Probability of reaching {selectedGoal.name}</span>
            <strong>{goalProjection.loading || goalProjection.result?.goalProbability == null ? <span {...cap('state.planning.goal-calculating')}>Calculating</span> : `${(goalProjection.result.goalProbability * 100).toFixed(0)}%`}</strong>
            <small>Uses {finances.pools.find((pool) => pool.id === selectedGoal.poolId)?.name || 'an unlinked starting balance'} through {selectedGoal.targetDate}</small>
          </div>
        )}
      </section>
    </>
  )
}
