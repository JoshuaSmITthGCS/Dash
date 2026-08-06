import { writeFile } from 'node:fs/promises'
import {
  benchmarkCenteredSparseHistory,
  extendSparsePortfolioHistory,
  projectionConfig,
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
const startedAt = performance.now()
const newResult = simulateProjection({ ...common, monthlyReturns: corrected.returns })
const runtimeMs = performance.now() - startedAt
const oldSpread = oldResult.terminalPercentiles.p90 - oldResult.terminalPercentiles.p10
const newSpread = newResult.terminalPercentiles.p90 - newResult.terminalPercentiles.p10

const report = {
  generated_at: new Date().toISOString(),
  comparison: '30-year terminal balance p90 minus p10',
  scenario: common,
  path_count: newResult.pathCount,
  performance: {
    runtime_ms: Number(runtimeMs.toFixed(3)),
    interaction_budget_ms: projectionConfig.interaction_budget_ms,
    passed: runtimeMs < projectionConfig.interaction_budget_ms,
  },
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
}
await writeFile(new URL('../pipeline/reports/projection_spread_comparison.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`)
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`)
if (!report.materially_wider || !report.performance.passed) process.exitCode = 1
