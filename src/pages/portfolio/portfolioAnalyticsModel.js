// Every statistic the Data overview renders, derived in one place.
//
// All of it runs against the same selected scope and the same daily benchmark. Metrics with
// a legitimately monthly cadence (batting average, factor loadings) declare their own
// observation count and dates rather than borrowing the daily ones.

import {
  alignSeries,
  concentrationLiquidityScore,
  diversificationScore,
  performanceMetrics,
  periodReturns,
  portfolioRiskDecomposition,
  portfolioScore,
  resilienceIndex,
  riskFreeAnnualRate,
  selectPeriod,
  sliceSeriesFrom,
  underwaterProfile,
} from '../../lib/portfolioAnalytics.js'
import { portfolioAcceleration } from '../../lib/portfolioAcceleration.js'
import { battingAverage, captureRatios } from '../../lib/portfolioBenchmarkComparison.js'
import { shortTermView } from '../../lib/portfolioShortTermView.js'
import { factorRegression } from '../../lib/factorAnalytics.js'
import {
  benchmarkFit,
  executionStatistics,
  exposureStatistics,
  performanceStatistics,
  regimeConditionalPerformance,
  robustnessStatistics,
  TRADING_DAYS,
} from '../../lib/portfolioStatistics.js'
import { buildPortfolioMetricModel } from '../../lib/portfolioMetricModel.js'
import { compareEvidencePeriods } from '../../lib/metricAssessment.js'
import { LIVE_TRACKING_START } from '../../lib/liveTrackingAvailability.js'
import prospectiveValidation from '../../../pipeline/validation/harness_freeze.json'
import { sliceSeriesBefore } from './portfolioModels.js'

const BACKTEST_BLOCKER = 'A registered algorithm backtest return series is not published; signal diagnostics are available in the Algorithm view, but portfolio returns are not inferred from them.'

const DEFLATION_TRIALS = prospectiveValidation.trial_count_for_deflated_statistics?.dsr_trial_count_used

export function buildAnalyticsModel({
  data,
  positions,
  portfolioPositions,
  etfData,
  factorData,
  signalMetrics,
  analyticsScope,
  benchmarks,
  holdingsSeriesFull,
  rebalances,
}) {
  const { analyticsBenchmarkSeries, selectedBenchmarkSymbol, candidateInputs } = benchmarks
  const sinceAlgorithmSeries = sliceSeriesFrom(holdingsSeriesFull, LIVE_TRACKING_START)
  const scoreHoldingsSeries = analyticsScope === 'since_algorithm'
    ? sinceAlgorithmSeries
    : analyticsScope === 'live_algorithm'
      ? sinceAlgorithmSeries
      : analyticsScope === 'backtest'
        ? null
        : holdingsSeriesFull
  const scorePortfolioPeriod = selectPeriod(scoreHoldingsSeries, 'All')
  const scoreBenchmarkPeriod = selectPeriod(analyticsBenchmarkSeries, 'All')
  const scoreComparable = alignSeries(scorePortfolioPeriod, scoreBenchmarkPeriod, scorePortfolioPeriod?.period)
  const riskFree = riskFreeAnnualRate(data)

  const performance = analyticsScope === 'backtest'
    ? { available: false, score: null, observations: 0, reason: BACKTEST_BLOCKER }
    : performanceMetrics(scoreComparable?.left, scoreComparable?.right, riskFree.annualPct)
  const acceleration = portfolioAcceleration(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const capture = captureRatios(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const batting = battingAverage(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const underwater = underwaterProfile(scoreHoldingsSeries)
  const shortTerm = shortTermView(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const risk = portfolioRiskDecomposition(portfolioPositions, {
    benchmarkHistory: analyticsBenchmarkSeries ? { dates: analyticsBenchmarkSeries.dates, closes: analyticsBenchmarkSeries.values } : null,
    benchmarkWeights: (etfData?.etfs || []).find((row) => row.ticker === selectedBenchmarkSymbol)?.top_holdings,
    etfs: etfData?.etfs || [],
  })
  const diversification = diversificationScore(portfolioPositions, { etfs: etfData?.etfs || [] })
  const resilience = resilienceIndex(scoreComparable?.left?.values || scorePortfolioPeriod?.values || [], diversification)
  const concentration = concentrationLiquidityScore(portfolioPositions)
  const legacyPortfolioScore = portfolioScore({
    diversification,
    resilience,
    performance,
    benchmarkEfficiency: null,
    concentrationLiquidity: concentration,
    dataCompleteness: positions.length ? Math.round(portfolioPositions.filter((position) => position.currentValue != null).length / positions.length * 100) : 0,
  })
  const statistics = analyticsScope === 'backtest'
    ? { available: false, observations: 0, reason: BACKTEST_BLOCKER }
    : performanceStatistics(scoreComparable?.left || scorePortfolioPeriod, riskFree.annualPct, { trialCount: DEFLATION_TRIALS })
  const factor = factorRegression(scoreComparable?.left || scorePortfolioPeriod, factorData)
  const benchmark = benchmarkFit(scoreHoldingsSeries, candidateInputs)

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
  const benchmarkComparisons = {
    spy: comparisonFor(candidateInputs.find((row) => row.symbol === 'SPY')),
    best: comparisonFor(candidateInputs.find((row) => row.symbol === benchmark.bestFit?.symbol)),
  }
  const exposure = exposureStatistics(portfolioPositions)
  const riskFreeDaily = (1 + Number(riskFree.annualPct) / 100) ** (1 / TRADING_DAYS) - 1
  const execution = executionStatistics({
    returns: periodReturns(scoreComparable?.left?.values || []),
    rebalances: rebalances || [],
    riskFreePerPeriod: riskFreeDaily,
  })
  const publishedPbo = signalMetrics?.metrics?.find((row) => row.id === 'pbo')
  const robustness = robustnessStatistics({
    pbo: ['ready', 'provisional'].includes(publishedPbo?.status) ? publishedPbo.value : null,
  })
  const regime = regimeConditionalPerformance(scoreHoldingsSeries, analyticsBenchmarkSeries)
  const metricModel = buildPortfolioMetricModel({
    performance,
    statistics,
    acceleration,
    capture,
    batting,
    underwater,
    shortTerm,
    risk,
    factor,
    benchmark,
    benchmarkComparisons,
    exposure,
    execution,
    robustness,
    regime,
    legacyPortfolioScore,
  })

  // The same evidence, computed over the window before live tracking started and over the
  // window since, so the Data overview can show whether the algorithm actually moved them.
  const comparableEvidenceFor = (series) => {
    const portfolioPeriod = selectPeriod(series, 'All')
    const benchmarkPeriod = selectPeriod(analyticsBenchmarkSeries, 'All')
    const comparable = alignSeries(portfolioPeriod, benchmarkPeriod, 'All')
    const periodPerformance = performanceMetrics(comparable?.left, comparable?.right, riskFree.annualPct)
    const periodStatistics = performanceStatistics(comparable?.left || portfolioPeriod, riskFree.annualPct, { trialCount: DEFLATION_TRIALS })
    const model = buildPortfolioMetricModel({
      performance: periodPerformance,
      statistics: periodStatistics,
      acceleration: portfolioAcceleration(series, analyticsBenchmarkSeries),
      capture: captureRatios(series, analyticsBenchmarkSeries),
      batting: battingAverage(series, analyticsBenchmarkSeries),
      underwater: underwaterProfile(series),
      shortTerm: shortTermView(series, analyticsBenchmarkSeries),
    })
    return [...model.standard, ...model.comparison, ...model.fast]
  }

  return {
    riskFree,
    performance,
    acceleration,
    capture,
    batting,
    underwater,
    shortTerm,
    risk,
    statistics,
    factor,
    benchmark,
    exposure,
    execution,
    robustness,
    metricModel,
    prospective: prospectiveValidation,
    baselineComparison: compareEvidencePeriods(
      comparableEvidenceFor(sliceSeriesBefore(holdingsSeriesFull, LIVE_TRACKING_START)),
      comparableEvidenceFor(sinceAlgorithmSeries),
    ),
  }
}
