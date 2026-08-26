import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { AuthProvider as FirebaseAuthProvider } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { usePortfolioTracking } from '../../../lib/usePortfolioTracking.js'
import {
  enrichPortfolio, currentHoldingsSeries, benchmarkHistoryFromSnapshot, selectPeriod, alignSeries,
  compareBenchmarkSeries, performanceMetrics, underwaterProfile, diversificationScore,
  portfolioRiskDecomposition, concentrationLiquidityScore, resilienceIndex, portfolioScore,
  riskFreeAnnualRate, portfolioReturnSummary, portfolioReconciliationBridge, weightedExpenseRatio,
  sectorLookThrough,
} from '../../../lib/portfolioAnalytics.js'
import { portfolioAcceleration } from '../../../lib/portfolioAcceleration.js'
import { captureRatios, battingAverage } from '../../../lib/portfolioBenchmarkComparison.js'
import { shortTermView } from '../../../lib/portfolioShortTermView.js'
import { factorRegression } from '../../../lib/factorAnalytics.js'
import { timeToValidMetric } from '../../../lib/portfolioStatistics.js'
import { portfolioVsBenchmark } from '../../../lib/portfolioPerformance.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { splitBySampleRequirement, defaultOpenGroups, sharedStatusMessage } from '../../../lib/signalMetrics.js'
import prospectiveValidation from '../../../../pipeline/validation/harness_freeze.json'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import WallLabel from '../WallLabel.jsx'
import { PORTFOLIO_IDS } from './capabilityIds.js'

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
  const { positions, loading: portfolioLoading, exportPortfolio, syncState } = useFirebasePortfolio()
  const tracking = usePortfolioTracking()

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
        <SummaryView Container={Container} portfolio={portfolio} positions={positions} analytics={analytics} returnSummary={returnSummary} />
      )}
      {view === 'performance' && (
        <PerformanceView Container={Container} analytics={analytics} returnSummary={returnSummary} bridge={bridge} tracking={tracking} searchParams={searchParams} setSearchParams={setSearchParams} />
      )}
      {view === 'data' && (
        <DataView Container={Container} analytics={analytics} positions={positions} signalMetrics={signalMetrics} searchParams={searchParams} setSearchParams={setSearchParams} exportPortfolio={exportPortfolio} />
      )}
      {view === 'diversification' && (
        <DiversificationView Container={Container} analytics={analytics} positions={positions} />
      )}
      {view === 'insights' && (
        <div {...cap(positions.length ? 'state.insights.no-holdings' : 'state.insights.loading')} role="status">
          {positions.length ? 'Insights for this view have not been ported to the new shell yet.' : "Add portfolio holdings to see how you're doing…"}
        </div>
      )}
      {view === 'finances' && (
        <div {...cap('state.finances.loading')} role="status">Finances has not been ported to the new shell yet.</div>
      )}
      {view === 'planning' && (
        <div>
          <p {...cap('disclosure.planning.assumption-not-forecast')}>This is a planning assumption, not a forecast.</p>
          <div {...cap('state.planning.loading')} role="status">Planning has not been ported to the new shell yet.</div>
        </div>
      )}
    </div>
  )
}

// --- Summary view --------------------------------------------------------------------------
function SummaryView({ Container, portfolio, positions, analytics, returnSummary }) {
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
                  <span>{row.ticker}</span>
                  <span>{money(row.currentValue) || '–'}</span>
                  <span>{row.gainPct != null ? signedPct(row.gainPct, 1) : '–'}</span>
                </li>
              ))}
            </ul>
          </Container>

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

function DataView({ Container, analytics, positions, signalMetrics, searchParams, setSearchParams, exportPortfolio }) {
  const analyticsView = ANALYTICS_VIEWS.includes(searchParams.get('analytics')) ? searchParams.get('analytics') : 'overview'
  const scope = ANALYTICS_SCOPES.includes(searchParams.get('scope')) ? searchParams.get('scope') : 'all_history'
  const setParam = (key, value) => {
    const params = new URLSearchParams(searchParams)
    params.set(key, value)
    setSearchParams(params)
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

      <div {...cap('export.portfolio.data-overview-menu')}>
        <button type="button" onClick={() => navigator.clipboard?.writeText?.(JSON.stringify({ performance: analytics.performance, risk: analytics.risk }, null, 2))}>Copy all</button>
        <button type="button" onClick={exportPortfolio}>Download JSON</button>
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
