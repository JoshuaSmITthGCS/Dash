// View 03 — Data overview. Why the portfolio moved, then every standard measure with the
// evidence behind it, evaluated over the selected analytics scope.

import PortfolioMoveExplanation from '../../components/PortfolioMoveExplanation.jsx'
import PerformanceMetrics from '../../components/PerformanceMetrics.jsx'
import ExportMetricsMenu from '../../components/ExportMetricsMenu.jsx'
import ScenarioSensitivityPanel from '../../components/ScenarioSensitivityPanel.jsx'
import AutoOverviewLine from '../../components/AutoOverviewLine.jsx'
import HoldingsDataQuality from './HoldingsDataQuality.jsx'
import FundCostOverview from './FundCostOverview.jsx'
import TimeToValidMetric from './TimeToValidMetric.jsx'
import { explainPortfolioMove } from '../../lib/portfolioAttribution.js'
import { buildDataOverviewBrief } from '../../lib/portfolioPlainBrief.js'
import { ANALYTICS_SCOPES } from './format.js'

export default function DataOverview({
  holdings,
  benchmarkQuote,
  analytics,
  benchmarks,
  signalMetrics,
  monteCarlo,
  monteCarloError,
  attributionPeriod,
  onAttributionPeriodChange,
  analyticsScope,
  onAnalyticsScopeChange,
}) {
  const moveExplanation = explainPortfolioMove(holdings.portfolioPositions, holdings.benchmarkHistory, {
    benchmarkQuote,
    period: attributionPeriod,
  })
  const brief = buildDataOverviewBrief({
    performance: analytics.performance,
    batting: analytics.batting,
    metricModel: analytics.metricModel,
    benchmarkLabel: benchmarks.selectedBenchmarkLabel,
  })

  return (
    <section className="portfolio-dashboard-section portfolio-data-overview-section" aria-labelledby="portfolio-data-overview-title">
      <header className="portfolio-section-heading">
        <div><span className="portfolio-section-number">03</span><div><span className="eyebrow">Evidence</span><h2 id="portfolio-data-overview-title">Data overview</h2></div></div>
        <ExportMetricsMenu
          holdings={holdings}
          analytics={analytics}
          benchmarks={benchmarks}
          signalMetrics={signalMetrics}
          monteCarlo={monteCarlo}
          scope={analyticsScope}
        />
      </header>
      <PortfolioMoveExplanation
        attribution={moveExplanation}
        benchmarkLabel="S&P 500"
        period={attributionPeriod}
        onPeriodChange={onAttributionPeriodChange}
      />
      <ScenarioSensitivityPanel holdings={holdings} signalMetrics={signalMetrics} />
      <AutoOverviewLine tone={brief.tone}>{brief.text}</AutoOverviewLine>
      <HoldingsDataQuality portfolioPositions={holdings.portfolioPositions} />
      <FundCostOverview fundCost={holdings.fundCost} />
      <TimeToValidMetric timeToValidMetric={analytics.timeToValidMetric} />
      <PerformanceMetrics
        metrics={analytics.performance}
        benchmarkLabel={benchmarks.selectedBenchmarkLabel}
        riskFree={analytics.riskFree}
        acceleration={analytics.acceleration}
        capture={analytics.capture}
        batting={analytics.batting}
        underwater={analytics.underwater}
        shortTerm={analytics.shortTerm}
        risk={analytics.risk}
        model={analytics.metricModel}
        statistics={analytics.statistics}
        factor={analytics.factor}
        benchmark={analytics.benchmark}
        constructedBenchmark={analytics.constructedBenchmark}
        exposure={analytics.exposure}
        execution={analytics.execution}
        robustness={analytics.robustness}
        signalMetrics={signalMetrics}
        monteCarlo={monteCarlo}
        monteCarloError={monteCarloError}
        prospective={analytics.prospective}
        baselineComparison={analytics.baselineComparison}
        scopes={ANALYTICS_SCOPES}
        scope={analyticsScope}
        onScopeChange={onAnalyticsScopeChange}
      />
    </section>
  )
}
