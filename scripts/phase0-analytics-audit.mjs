import fs from 'node:fs'
import { REFERENCE_PORTFOLIO } from '../src/lib/referencePortfolio.js'
import { buildPortfolioPriceData } from '../src/lib/portfolioPosition.js'
import {
  alignSeries,
  currentHoldingsSeries,
  performanceMetrics,
  riskFreeAnnualRate,
  selectPeriod,
  underwaterProfile,
} from '../src/lib/portfolioAnalytics.js'
import { battingAverage, captureRatios } from '../src/lib/portfolioBenchmarkComparison.js'
import { shortTermView } from '../src/lib/portfolioShortTermView.js'
import { benchmarkFit, dailyCadence, performanceStatistics } from '../src/lib/portfolioStatistics.js'

const payload = JSON.parse(fs.readFileSync('public/data/report.json'))
const priceData = buildPortfolioPriceData(
  payload.screen_universe || [],
  payload.portfolio_coverage || [],
  payload.research || [],
)
// Reconstruct the pre-fix input explicitly. The current calculation correctly prefers
// analytics_history, so an audit that simply called it would stop reproducing the defect it
// exists to document after the repair landed.
const legacyPriceData = Object.fromEntries(Object.entries(priceData).map(([ticker, row]) => [ticker, { ...row, analytics_history: undefined }]))
const benchmark = {
  dates: payload.benchmark_history?.dates || [],
  values: payload.benchmark_history?.closes || [],
}
const full = currentHoldingsSeries(REFERENCE_PORTFOLIO, legacyPriceData, benchmark.dates)
const selected = selectPeriod(full, '1Y') || selectPeriod(full, 'All')
const selectedBenchmark = selectPeriod(benchmark, selected?.period || 'All')
const aligned = alignSeries(selected, selectedBenchmark, selected?.period)

function sample(series) {
  const dates = series?.dates || []
  const gaps = dates.slice(1).map((date, index) => (
    (Date.parse(date) - Date.parse(dates[index])) / 86_400_000
  ))
  return {
    observations: dates.length,
    returns: Math.max(0, dates.length - 1),
    first: dates[0] || null,
    last: dates.at(-1) || null,
    calendarDays: dates.length > 1
      ? (Date.parse(dates.at(-1)) - Date.parse(dates[0])) / 86_400_000
      : 0,
    oneDayIntervals: gaps.filter((gap) => gap === 1).length,
    weekendIntervals: gaps.filter((gap) => gap === 3 || gap === 4).length,
    intervalsOverFourDays: gaps.filter((gap) => gap > 4).length,
    maximumGapDays: gaps.length ? Math.max(...gaps) : null,
    meanGapDays: gaps.length ? gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length : null,
  }
}

const missingHistory = REFERENCE_PORTFOLIO
  .filter((position) => !priceData[position.ticker]?.history?.dates?.length)
  .map((position) => position.ticker)
const dailyBenchmark = {
  dates: payload.benchmark_analytics_history?.dates || [],
  values: payload.benchmark_analytics_history?.closes || [],
  frequency: payload.benchmark_analytics_history?.frequency,
}
const repairedFull = currentHoldingsSeries(REFERENCE_PORTFOLIO, priceData, dailyBenchmark.dates)
const repairedAligned = alignSeries(selectPeriod(repairedFull, 'All'), selectPeriod(dailyBenchmark, 'All'), 'All')
const repairedStatistics = performanceStatistics(repairedAligned?.left, riskFreeAnnualRate(payload).annualPct, { trialCount: 50 })
const benchmarkCandidates = [
  ['SPY', 'S&P 500'],
  ['RSP', 'Equal-weight S&P 500'],
  ['IWM', 'Russell 2000'],
  ['IJR', 'S&P SmallCap 600'],
].map(([symbol, label]) => {
  const snapshot = JSON.parse(fs.readFileSync(`public/data/etf/${symbol}.json`))
  const rows = snapshot.price_series?.fund?.slice(-504) || []
  return { symbol, label, dates: rows.map((row) => row.date), closes: rows.map((row) => row.adjusted_close) }
})

console.log(JSON.stringify({
  generatedAt: payload.generated_at,
  referenceTickers: REFERENCE_PORTFOLIO.map((position) => position.ticker),
  missingHistory,
  benchmark: sample(benchmark),
  fullPortfolio: sample(full),
  oneYearPortfolio: sample(selected),
  alignedOneYear: sample(aligned?.left),
  standardMeasures: performanceMetrics(aligned?.left, aligned?.right, riskFreeAnnualRate(payload).annualPct),
  comparison: {
    batting: battingAverage(full, benchmark),
    capture: captureRatios(full, benchmark),
  },
  underwater: underwaterProfile(full),
  fastReads: shortTermView(full, benchmark),
  repairedDailyContract: {
    portfolio: sample(repairedAligned?.left),
    benchmark: sample(repairedAligned?.right),
    cadence: dailyCadence(repairedAligned?.left),
    statistics: repairedStatistics.available ? {
      observations: repairedStatistics.observations,
      naiveSharpe: repairedStatistics.naiveSharpe,
      loAdjustedSharpe: repairedStatistics.loAdjustedSharpe,
      sharpeTStatistic: repairedStatistics.sharpeTStatistic,
      psr: repairedStatistics.psr,
      minTrackRecord: repairedStatistics.minTrackRecord,
      dsr: repairedStatistics.dsr,
      autocorrelation1: repairedStatistics.autocorrelation1,
      ljungBox: repairedStatistics.ljungBox,
    } : repairedStatistics,
    benchmarkFit: benchmarkFit(repairedFull, benchmarkCandidates),
  },
}, null, 2))
