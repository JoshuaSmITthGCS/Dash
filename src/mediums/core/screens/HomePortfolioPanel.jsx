import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AuthProvider as FirebaseAuthProvider, useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { useFirebaseFinances } from '../../../lib/useFirebaseFinances.js'
import { useWatchlist } from '../../../lib/useWatchlist.js'
import { useData } from '../../../lib/useData.js'
import {
  enrichPortfolio, currentHoldingsSeries, selectPeriod, latestMarketDayReturn,
  BENCHMARKS, compareBenchmarkSeries, performanceMetrics, riskFreeAnnualRate, annualizeReturnPct,
} from '../../../lib/portfolioAnalytics.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { liveTodayPortfolioReturn } from '../../../lib/afterHoursQuotes.js'
import { dailyMoveForPosition } from '../../../lib/marketPresentation.js'
import { signedPct } from '../../../lib/formatters.js'
import { getRecommendation } from '../../../lib/recommendation.js'
import { buildPortfolioMetricModel } from '../../../lib/portfolioMetricModel.js'
import { combinedEvidence, sectionAssessment } from '../../../lib/metricAssessment.js'
import { useProjectionSimulation } from '../../../lib/useProjectionSimulation.js'
import { fidelityProjectionBaseline } from '../../../lib/referenceCashFlows.js'
import {
  projectionConfig, selectProjectionReturnSource, applyAllocationAssumption, normalizeAnnualReturnTarget,
} from '../../../lib/projectionEngine.js'
import { usePreferences } from '../../../lib/PreferencesContext.jsx'
import { useMedium } from '../MediumContext.jsx'
import { useRenderer } from '../useRenderer.js'
import { canonicalArtifactState, confidenceOf } from '../states.js'
import { cap } from '../capability.js'
import { HOME_IDS } from './capabilityIds.js'
import { fanChartCall, projectionArtifactState } from '../fanChart.js'

const PERIODS = ['1H', '1D', '1W', '1M', '3M', '1Y']
const PERIOD_LABELS = { '1H': 'Last hour', '1D': 'Today', '1W': 'Week', '1M': 'Month', '3M': '3 months', '1Y': 'Year' }

/**
 * The portfolio-value hero and growth-chart items from Home's first viewport (Container items
 * 1-2) — split out of HomeScreen.jsx and lazy-loaded from there (Phase 4, NOTES.md) because this
 * is the only Firebase-dependent part of Home: useAuth() and useFirebasePortfolio() both
 * statically import FirebaseAuthContext.jsx, which eagerly initializes the whole Firebase SDK
 * (~610 kB) at module-load time. Keeping that import out of HomeScreen.jsx's own static graph is
 * what lets Home's cold /v2 load stay under budget.spec.mjs's 500 kB ceiling. Item 3 (the
 * provenance strip) needs no Firebase data and stays in HomeScreen.jsx directly.
 *
 * /v2's own root (MediumApp.jsx) never mounts <FirebaseAuthProvider> — that's the whole point of
 * the deferral — so this chunk provides its own, wrapping the part of the tree that actually
 * calls useAuth()/useFirebasePortfolio(). Costs nothing extra: AuthProvider is the other named
 * export of the same FirebaseAuthContext.jsx module useFirebasePortfolio.js already pulls in.
 * usePreferences() is cheap to add alongside it — PreferencesContext.jsx has no Firebase import
 * of its own, and both mediums roots already mount <PreferencesProvider> above App.jsx/
 * MediumApp.jsx in main.jsx, so it costs nothing extra here either.
 */
export default function HomePortfolioPanel({ report }) {
  return <FirebaseAuthProvider><HomePortfolioContent report={report} /></FirebaseAuthProvider>
}

function HomePortfolioContent({ report }) {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const ControlComponent = manifest.components?.Control
  const Skeleton = manifest.components?.Skeleton

  const renderer = useRenderer()
  const { currentUser, authError, retryAuth } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { items: watchlistItems } = useWatchlist()
  const { preferences, updatePreferences } = usePreferences()
  const finances = useFirebaseFinances()
  // benchmark-report.json backs both the opportunity-cost figure and the performance-evidence
  // summary below — same file, same shape Dashboard.jsx reads for its own `comparison`/
  // `scoreComparison`. Only fetched once a holder actually has positions to compare.
  const { data: benchmarkReport } = useData(positions.length ? 'benchmark-report.json' : null)

  const [period, setPeriod] = useState(preferences.defaultChartPeriod && PERIODS.includes(preferences.defaultChartPeriod) ? preferences.defaultChartPeriod : '1M')
  const [holdingsSort, setHoldingsSort] = useState('day')

  const priceData = useMemo(() => {
    if (!report) return {}
    const published = buildPortfolioPriceData(report.screen_universe || [], report.portfolio_coverage || [], report.research || [])
    return mergePositionSnapshots(published, positions, report.generated_at)
  }, [report, positions])

  const portfolio = useMemo(() => enrichPortfolio(positions, priceData), [positions, priceData])
  const holdingsSeries = useMemo(
    () => currentHoldingsSeries(positions, priceData, report?.benchmark_history?.dates || []),
    [positions, priceData, report],
  )
  const chart = useMemo(() => selectPeriod(holdingsSeries, period), [holdingsSeries, period])
  const liveToday = useMemo(() => liveTodayPortfolioReturn(positions, priceData), [positions, priceData])
  const marketDayToday = useMemo(() => latestMarketDayReturn(holdingsSeries), [holdingsSeries])
  const today = liveToday.available ? liveToday : marketDayToday

  const rankedHoldings = useMemo(() => portfolio.positions
    .map((position) => ({ ...position, move: dailyMoveForPosition(position) }))
    .sort((left, right) => holdingsSort === 'allocation'
      ? (right.allocationPct ?? -Infinity) - (left.allocationPct ?? -Infinity)
      : (right.move.pct ?? -Infinity) - (left.move.pct ?? -Infinity))
    .slice(0, 5), [portfolio.positions, holdingsSort])

  const privacyMode = Boolean(preferences.privacyMode)
  const money = (value) => value == null ? '–' : privacyMode ? '••••' : `$${value.toFixed(2)}`

  const changePeriod = (next) => { setPeriod(next); updatePreferences({ defaultChartPeriod: next }) }

  // chart.home.growth-chart's state/confidence — mirrors MarketsScreen's `IndexesView`: no
  // per-metric row exists for a holdings-value series, so state comes from whether report.json
  // itself built (`canonicalArtifactState`), never hand-derived, and confidence stays the
  // neutral default (no explicit confidence field, no |t| flag applies to a value chart).
  const growthChartState = canonicalArtifactState(report ? { status: 'success' } : null)
  const growthChartConfidence = confidenceOf({})

  // chart.home.allocation — sector allocation by current market value, same source Dashboard.jsx
  // uses for AllocationDonut/`.allocation-bars` (portfolioAnalytics.js via enrichPortfolio's
  // priceInfo.sector). Composition-safe replacement for the retired donut (DESIGN.md, ledger note).
  const sectorAllocation = useMemo(() => Object.entries(portfolio.positions.reduce((totals, position) => {
    const sector = position.priceInfo?.sector || 'Unclassified'
    totals[sector] = (totals[sector] || 0) + Number(position.currentValue || 0)
    return totals
  }, {})).map(([sector, value]) => ({ sector, value, pct: portfolio.totalValue ? value / portfolio.totalValue * 100 : 0 }))
    .sort((left, right) => right.value - left.value), [portfolio.positions, portfolio.totalValue])
  const allocationState = canonicalArtifactState(sectorAllocation.length ? { status: 'success' } : null)
  const allocationConfidence = confidenceOf({})

  // figure.home.action-needed — holdings with evidence-based guidance beyond Hold, same
  // getRecommendation() Dashboard.jsx's `actionable` reads off each position's merged priceInfo.
  const actionable = useMemo(() => portfolio.positions
    .map((row) => ({ ...row, recommendation: row.priceInfo ? getRecommendation(row.priceInfo) : null }))
    .filter((row) => row.recommendation?.action === 'SELL' || row.recommendation?.action === 'TRIM'),
  [portfolio.positions])

  // figure.home.watchlist-preview — followed tickers matched against the published research
  // rows, same lookup Dashboard.jsx's `watchRows` performs against `data.research`.
  const watchRows = useMemo(() => watchlistItems
    .map((item) => (report?.research || []).find((row) => row.ticker === item.ticker))
    .filter(Boolean)
    .slice(0, 4), [watchlistItems, report])

  // Selected benchmark proxies (up to 3, preference-driven) — one shared read backing both the
  // opportunity-cost figure and the performance-evidence summary, same as Dashboard.jsx's
  // `selectedBenchmarkSeries`.
  const selectedBenchmarkSeries = useMemo(() => (preferences.defaultBenchmarks || [preferences.defaultBenchmark])
    .map((symbol) => {
      const history = benchmarkReport?.histories?.[symbol]
      const definition = BENCHMARKS.find((item) => item.symbol === symbol)
      return history ? { symbol, label: definition?.label || symbol, dates: history.dates, closes: history.closes } : null
    }).filter(Boolean), [benchmarkReport, preferences.defaultBenchmarks, preferences.defaultBenchmark])

  // figure.home.opportunity-cost — potential earnings had the same starting value been put in
  // each benchmark proxy instead, over the currently charted period. Identical computation to
  // Dashboard.jsx's `comparison` (compareBenchmarkSeries against the selected chart period).
  const opportunityComparison = useMemo(() => compareBenchmarkSeries(chart, selectedBenchmarkSeries), [chart, selectedBenchmarkSeries])

  // figure.home.performance-evidence-summary — standard risk/return measures against the
  // primary benchmark over up to a year of live holdings, fed through the same
  // buildPortfolioMetricModel()/combinedEvidence() apparatus PerformanceEvidenceSummary
  // (src/components/PerformanceMetrics.jsx, read-only reference) uses — reimplemented against
  // lib/* directly since importing from src/components is ESLint-forbidden outside Classic.
  const scorePeriod = useMemo(() => selectPeriod(holdingsSeries, '1Y') || selectPeriod(holdingsSeries, 'All'), [holdingsSeries])
  const scoreComparison = useMemo(() => compareBenchmarkSeries(scorePeriod, selectedBenchmarkSeries.slice(0, 1)), [scorePeriod, selectedBenchmarkSeries])
  const riskFree = useMemo(() => riskFreeAnnualRate(report), [report])
  const performance = useMemo(
    () => performanceMetrics(scoreComparison?.portfolio || scorePeriod, scoreComparison?.benchmarks?.[0], riskFree.annualPct),
    [scoreComparison, scorePeriod, riskFree],
  )
  const evidenceOverall = useMemo(() => {
    const model = buildPortfolioMetricModel({ performance })
    return combinedEvidence([
      { id: 'standard', metrics: model.standard, summary: sectionAssessment('standard', model.standard) },
      { id: 'comparison', metrics: model.comparison, summary: sectionAssessment('comparison', model.comparison) },
      { id: 'fast', metrics: model.fast, summary: sectionAssessment('fast', model.fast) },
    ])
  }, [performance])

  // chart.home.projection-panel — long-range Monte Carlo outcome fan, same derived-input chain
  // as Dashboard.jsx's ReportProjection (selectProjectionReturnSource → applyAllocationAssumption
  // → normalizeAnnualReturnTarget), reusing benchmarkReport/holdingsSeries/portfolio already
  // fetched/computed above rather than re-deriving them a second time.
  const primaryBenchmarkHistory = benchmarkReport?.histories?.[preferences.defaultBenchmark]
    ? { dates: benchmarkReport.histories[preferences.defaultBenchmark].dates, closes: benchmarkReport.histories[preferences.defaultBenchmark].closes, symbol: preferences.defaultBenchmark }
    : null
  const projectionSource = useMemo(
    () => selectProjectionReturnSource(holdingsSeries, primaryBenchmarkHistory, preferences.defaultBenchmark, fidelityProjectionBaseline(positions)),
    [holdingsSeries, primaryBenchmarkHistory, preferences.defaultBenchmark, positions],
  )
  const liveStrategyAnnualReturnPct = useMemo(() => {
    const period = selectPeriod(holdingsSeries, 'All')
    return period ? annualizeReturnPct(period.returnPct, period.startDate, period.endDate) : null
  }, [holdingsSeries])
  const annualReturnTargetPct = normalizeAnnualReturnTarget(
    liveStrategyAnnualReturnPct ?? finances.settings.planningAnnualReturnTargetPct, projectionSource,
  )
  const planningReturns = projectionSource.available
    ? applyAllocationAssumption(projectionSource.returns, finances.settings.allocationAggressiveness || projectionConfig.allocation_default, annualReturnTargetPct / 100)
    : []
  const projectionInput = !finances.loading && projectionSource.available ? {
    monthlyReturns: planningReturns,
    currentBalance: finances.settings.currentSavings || portfolio.totalValue,
    monthlyContribution: finances.settings.monthlyContribution,
    monthlyWithdrawal: finances.settings.monthlyWithdrawal,
    accumulationMonths: Math.max(1, (finances.settings.retireAge - finances.settings.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: Math.max(0, (finances.settings.retirementEndAge - finances.settings.retireAge) * projectionConfig.months_per_year),
    inflationPct: finances.settings.inflationPct,
  } : null
  const projection = useProjectionSimulation(projectionInput)

  if (currentUser && portfolioLoading) {
    return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
  }

  return (
    <>
      {/* First-viewport item 1: portfolio value + today's delta + as-of line */}
      <Container primary {...cap(HOME_IDS.portfolioHero)}>
        {ControlComponent ? (
          <ControlComponent
            as="button" type="button" capId="control.home.privacy-eye"
            pressed={privacyMode}
            aria-label={privacyMode ? 'Show balances' : 'Hide balances'}
            onClick={() => updatePreferences({ privacyMode: !privacyMode })}
          >
            {privacyMode ? 'Show balances' : 'Hide balances'}
          </ControlComponent>
        ) : (
          <button
            type="button" {...cap('control.home.privacy-eye')}
            aria-pressed={privacyMode}
            aria-label={privacyMode ? 'Show balances' : 'Hide balances'}
            onClick={() => updatePreferences({ privacyMode: !privacyMode })}
          >
            {privacyMode ? 'Show balances' : 'Hide balances'}
          </button>
        )}

        {!currentUser ? (
          <div {...cap('state.home.cloud-offline')}>
            <strong>Cloud portfolio is offline</strong>
            <p>{authError || 'Firebase is connecting to your solo workspace.'}</p>
            <button type="button" onClick={retryAuth}>Reconnect Firebase</button>
          </div>
        ) : !positions.length ? (
          <div {...cap('state.home.no-holdings')}>
            <strong>Add holdings to unlock your report</strong>
            <p>Portfolio analytics appear after holdings and per-share cost basis are available.</p>
          </div>
        ) : (
          <>
            <strong data-testid="portfolio-value">{money(portfolio.totalValue)}</strong>
            <span data-testid="portfolio-today">
              {today?.dollarReturn != null
                ? `${today.dollarReturn >= 0 ? '+' : ''}${money(Math.abs(today.dollarReturn))} (${signedPct(today.returnPct, 2)}) today`
                : 'Today’s move is still building.'}
            </span>

            <div data-testid="top-5-holdings">
              <label>
                <span>Rank holdings by</span>
                <select
                  {...cap('control.home.top5-rank-mode')}
                  value={holdingsSort}
                  onChange={(event) => setHoldingsSort(event.target.value)}
                >
                  <option value="day">Today’s performance</option>
                  <option value="allocation">Biggest allocation</option>
                </select>
              </label>
              <ol>
                {rankedHoldings.map((position, index) => (
                  <li key={position.id || position.ticker}>
                    <span>{index + 1}</span>
                    <b>{position.ticker}</b>
                    <small>{position.allocationPct == null ? 'Allocation pending' : `${position.allocationPct.toFixed(1)}% allocation`}</small>
                    <span>{signedPct(position.move.pct, 2)}</span>
                  </li>
                ))}
              </ol>
            </div>
          </>
        )}

        <span {...cap(HOME_IDS.asOfEyebrow)} data-testid="as-of">
          Latest close · {report?.generated_at ? new Date(report.generated_at).toLocaleDateString() : '–'} · {report?.research?.length ?? 0} names covered
        </span>
      </Container>

      {/* First-viewport item 2: growth chart of current holdings */}
      <Container {...cap(HOME_IDS.growthChart)}>
        <label>
          <span>Portfolio performance</span>
          <select {...cap('control.home.chart-period')} value={period} onChange={(event) => changePeriod(event.target.value)}>
            {PERIODS.map((item) => <option key={item} value={item}>{PERIOD_LABELS[item]}</option>)}
          </select>
        </label>
        {chart ? (
          <div data-testid="growth-chart" data-points={chart.values.length}>
            {renderer && renderer.line({
              metricId: 'home-growth-chart',
              series: chart.dates.map((date, index) => ({ x: date, y: chart.values[index] })),
              domain: { min: chart.low, max: chart.high },
              unit: 'USD',
              thresholds: [],
              annotations: [],
              state: growthChartState,
              confidence: growthChartConfidence,
              ariaLabel: `Current holdings value history, ${period} range`,
              width: 920,
              height: 360,
            })}
            <span className="sr-only">Current holdings, {chart.period}: {chart.returnPct != null ? signedPct(chart.returnPct) : '–'}</span>
          </div>
        ) : (
          <span data-testid="growth-chart-empty" {...cap('state.home.chart-unavailable')}>
            {PERIOD_LABELS[period] || period} history is still building — two saved portfolio observations are needed.
          </span>
        )}
      </Container>

      {/* chart.home.allocation — composition-safe replacement for the retired AllocationDonut */}
      <Container {...cap('chart.home.allocation')} aria-label="Sector allocation">
        {sectorAllocation.length ? (
          <div data-testid="allocation-chart">
            {renderer && renderer.composition({
              metricId: 'home-allocation',
              values: sectorAllocation.map((item) => ({ value: item.pct, label: item.sector })),
              domain: { min: 0, max: 100 },
              unit: '%',
              thresholds: [],
              annotations: [],
              state: allocationState,
              confidence: allocationConfidence,
              ariaLabel: `Sector allocation of ${money(portfolio.totalValue)} covered portfolio value`,
              width: 480,
              height: 32,
            })}
            <ul data-testid="allocation-bars">
              {sectorAllocation.map((item) => (
                <li key={item.sector}><b>{item.sector}</b><span>{item.pct.toFixed(1)}%</span><small>{money(item.value)}</small></li>
              ))}
            </ul>
          </div>
        ) : (
          <span data-testid="allocation-empty">No priced holdings to allocate yet.</span>
        )}
      </Container>

      {/* figure.home.performance-evidence-summary — the read and its counts; full analytics live
          on Portfolio → Data overview, not duplicated here. */}
      <Container {...cap('figure.home.performance-evidence-summary')} aria-labelledby="evidence-summary-title">
        <span className="eyebrow">Performance evidence</span>
        <h3 id="evidence-summary-title" data-testid="evidence-summary-overall">Overall evidence: {evidenceOverall.read}</h3>
        <p data-testid="evidence-summary-headline">
          {performance.available
            ? `Sharpe ${Number.isFinite(performance.sharpe) ? performance.sharpe.toFixed(2) : 'Unavailable'} · Max drawdown ${Number.isFinite(performance.maxDrawdown) ? `${performance.maxDrawdown.toFixed(1)}%` : 'Unavailable'}`
            : performance.reason || 'Unavailable'}
        </p>
        <div data-testid="evidence-summary-counts" aria-label={`${evidenceOverall.counts.positive} positive, ${evidenceOverall.counts.neutral} neutral, ${evidenceOverall.counts.negative} negative, ${evidenceOverall.counts.insufficient} insufficient`}>
          {['positive', 'neutral', 'negative', 'insufficient'].map((status) => (
            <span key={status} data-status={status}>{evidenceOverall.counts[status]} {status}</span>
          ))}
        </div>
        <p data-testid="evidence-summary-narrative">{evidenceOverall.narrative}</p>
      </Container>

      {/* figure.home.action-needed */}
      <Container {...cap('figure.home.action-needed')} aria-label="Holdings to review">
        <strong data-testid="action-needed-count">{actionable.length}</strong>
        <p data-testid="action-needed-note">
          {actionable.length
            ? `${actionable.slice(0, 4).map((row) => row.ticker).join(', ')} have evidence-based guidance beyond Hold.`
            : 'No covered holding has multi-factor guidance beyond Hold.'}
        </p>
        <small>Research prompts only. Review the underlying evidence before acting.</small>
      </Container>

      {/* figure.home.watchlist-preview */}
      <Container {...cap('figure.home.watchlist-preview')} aria-label="Names you follow">
        {watchRows.length ? (
          <ol data-testid="watchlist-preview-rows">
            {watchRows.map((row) => (
              <li key={row.ticker}><b>{row.ticker}</b><span>{row.name}</span><em>{row.score}</em>{row.dayChange != null && <span>{signedPct(row.dayChange, 2)}</span>}</li>
            ))}
          </ol>
        ) : (
          <p data-testid="watchlist-preview-empty">No published watchlist matches yet.</p>
        )}
      </Container>

      {/* figure.home.opportunity-cost */}
      <Container {...cap('figure.home.opportunity-cost')} aria-label="Potential earnings by benchmark">
        {opportunityComparison ? (
          <div data-testid="opportunity-cost">
            <div><span>Shared starting value</span><strong>{money(opportunityComparison.startingValue)}</strong><small>{opportunityComparison.startDate} to {opportunityComparison.endDate}</small></div>
            <div><span>Current holdings</span><strong>{opportunityComparison.portfolio.dollarReturn >= 0 ? '+' : '−'}{money(Math.abs(opportunityComparison.portfolio.dollarReturn))}</strong></div>
            {opportunityComparison.benchmarks.map((item) => (
              <div key={item.symbol}>
                <span>{item.symbol} proxy · {item.label}</span>
                <strong>{item.potentialEarnings >= 0 ? '+' : '−'}{money(Math.abs(item.potentialEarnings))}</strong>
                <em>{item.differenceVsPortfolio >= 0 ? `Portfolio ahead ${money(item.differenceVsPortfolio)}` : `Benchmark ahead ${money(Math.abs(item.differenceVsPortfolio))}`}</em>
              </div>
            ))}
            <small>{opportunityComparison.methodology}</small>
          </div>
        ) : (
          <p data-testid="opportunity-cost-empty">Comparable history is unavailable for this selection.</p>
        )}
      </Container>

      {/* chart.home.projection-panel — long-range Monte Carlo outcome fan + Open Planning link */}
      <Container {...cap('chart.home.projection-panel')} aria-label="Long-range outcome distribution">
        {projectionSource.available ? (
          <>
            {renderer && fanChartCall(renderer, projection.result, {
              metricId: 'home-projection-panel',
              ariaLabel: 'Long-range outcome distribution, 10th to 90th percentile',
              state: projectionArtifactState(projection.loading, projection.result, projection.error),
              confidence: confidenceOf({}),
            })}
            <Link to="/v2/portfolio?view=planning">Open Planning</Link>
          </>
        ) : <p>{projectionSource.reason}</p>}
      </Container>

      <p {...cap('disclosure.home.methodology-footer')}>
        Balances use the latest stored closes. Historical portfolio lines apply current
        quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes,
        fees, or dividends. General research only.
      </p>
    </>
  )
}
