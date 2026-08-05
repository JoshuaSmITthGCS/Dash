import {
  benchmarkCenteredSparseHistory,
  extendSparsePortfolioHistory,
  simulateProjection,
} from '../src/lib/projectionEngine.js'

function monthlySeries(months, monthlyReturn = 0.01) {
  const dates = []
  const values = []
  let value = 100
  for (let index = 0; index < months; index += 1) {
    dates.push(new Date(Date.UTC(2020, index + 1, 0)).toISOString().slice(0, 10))
    values.push(value)
    value *= 1 + monthlyReturn
  }
  return { dates, values }
}

const portfolio = monthlySeries(20)
const benchmark = monthlySeries(120)
benchmark.values = benchmark.values.map((_, index) => (
  100 * (1.006 ** index) * (1 + Math.sin(index * 0.8) * 0.08)
))

const legacy = extendSparsePortfolioHistory(portfolio)
const corrected = benchmarkCenteredSparseHistory(portfolio, benchmark)
const common = { currentBalance: 100000, accumulationMonths: 360, seed: 42 }
const oldResult = simulateProjection({ ...common, monthlyReturns: legacy.returns })
const newResult = simulateProjection({ ...common, monthlyReturns: corrected.returns })
const oldSpread = oldResult.terminalPercentiles.p90 - oldResult.terminalPercentiles.p10
const newSpread = newResult.terminalPercentiles.p90 - newResult.terminalPercentiles.p10

process.stdout.write(`${JSON.stringify({
  generated_at: new Date().toISOString(),
  comparison: '30-year terminal balance p90 minus p10',
  scenario: common,
  path_count: newResult.pathCount,
  old_repeating_pattern: {
    source_months: legacy.months,
    terminal_percentiles: oldResult.terminalPercentiles,
    spread: oldSpread,
  },
  benchmark_centered: {
    source_months: corrected.months,
    terminal_percentiles: newResult.terminalPercentiles,
    spread: newSpread,
  },
  spread_ratio: oldSpread > 0 ? newSpread / oldSpread : null,
  spread_ratio_note: oldSpread > 0 ? null : 'The repeating-pattern method collapsed the p10 to p90 spread to zero in this sparse-history case.',
  materially_wider: newSpread > oldSpread,
}, null, 2)}\n`)
