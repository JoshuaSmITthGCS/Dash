import modelSettings from '../../pipeline/config/settings.json'

export const projectionConfig = modelSettings.projection

const finite = (value) => Number.isFinite(Number(value))
const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value))

function monthKey(date) {
  const parsed = new Date(`${String(date).slice(0, 10)}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString().slice(0, 7)
}

/**
 * Reduces daily observations to month-end values before computing simple returns
 * r_t = V_t / V_(t-1) - 1. Month-end sampling prevents dense daily data from
 * making a short history appear long enough for a retirement model.
 */
export function monthlyReturnsFromSeries(series) {
  const dates = series?.dates || []
  const values = series?.values || series?.closes || []
  const monthEnds = new Map()
  dates.forEach((date, index) => {
    const key = monthKey(date)
    const value = Number(values[index])
    if (key && finite(value) && value > 0) monthEnds.set(key, { date: String(date).slice(0, 10), value })
  })
  const observations = [...monthEnds.values()].sort((left, right) => left.date.localeCompare(right.date))
  const returns = []
  for (let index = 1; index < observations.length; index += 1) {
    const value = observations[index].value / observations[index - 1].value - 1
    if (finite(value) && value > -1) returns.push(value)
  }
  return {
    returns,
    months: returns.length,
    startDate: observations[0]?.date || null,
    endDate: observations.at(-1)?.date || null,
  }
}

/**
 * Uses portfolio returns only after 36 observed monthly changes. Below that gate,
 * the selected benchmark supplies the resampling history because a partial market
 * cycle can give a misleadingly narrow distribution.
 */
export function selectProjectionReturnSource(portfolioSeries, benchmarkHistory, benchmarkSymbol = 'SPY') {
  const portfolio = monthlyReturnsFromSeries(portfolioSeries)
  const benchmark = monthlyReturnsFromSeries(benchmarkHistory)
  const minimumPortfolioMonths = projectionConfig.portfolio_minimum_history_months
  const blockMonths = projectionConfig.block_months
  if (portfolio.months >= minimumPortfolioMonths) {
    return {
      available: true,
      type: 'portfolio',
      label: 'portfolio monthly returns',
      ...portfolio,
    }
  }
  if (benchmark.months >= blockMonths) {
    return {
      available: true,
      type: 'benchmark-fallback',
      label: `${benchmarkSymbol} monthly returns`,
      fallbackReason: `Portfolio history has ${portfolio.months} monthly return${portfolio.months === 1 ? '' : 's'}, below the ${minimumPortfolioMonths}-month gate.`,
      ...benchmark,
    }
  }
  return {
    available: false,
    type: 'unavailable',
    label: `${benchmarkSymbol} monthly returns`,
    months: benchmark.months,
    returns: [],
    reason: `At least ${blockMonths} monthly benchmark returns are required for a ${blockMonths}-month block bootstrap.`,
  }
}

function seededRandom(seed) {
  let state = Number(seed) >>> 0
  return () => {
    state += 0x6D2B79F5
    let value = state
    value = Math.imul(value ^ value >>> 15, value | 1)
    value ^= value + Math.imul(value ^ value >>> 7, value | 61)
    return ((value ^ value >>> 14) >>> 0) / 4294967296
  }
}

function percentile(sorted, probability) {
  if (!sorted.length) return null
  const index = (sorted.length - 1) * probability
  const lower = Math.floor(index)
  const upper = Math.ceil(index)
  if (lower === upper) return sorted[lower]
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower)
}

function percentileMap(values) {
  values.sort()
  return Object.fromEntries(projectionConfig.percentiles.map((probability) => [
    `p${Math.round(probability * 100)}`,
    percentile(values, probability),
  ]))
}

function realValues(values, month, annualInflationRate) {
  const divisor = (1 + annualInflationRate) ** (month / projectionConfig.months_per_year)
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value / divisor]))
}

/**
 * Block bootstrap formula: B_(t+1) = max(0, B_t(1+r*_t) + C_t - W_t).
 * Each r*_t comes from a randomly selected consecutive 12-month historical block,
 * which preserves observed short-run return order instead of assuming a smooth rate.
 * Withdrawals rise monthly with inflation and occur after the sampled market return,
 * so path survival captures sequence risk during the spending phase.
 */
export function simulateProjection(input) {
  const monthlyReturns = (input?.monthlyReturns || []).map(Number).filter((value) => finite(value) && value > -1)
  const blockMonths = projectionConfig.block_months
  if (monthlyReturns.length < blockMonths) {
    return { available: false, reason: `At least ${blockMonths} monthly returns are required for the bootstrap model.` }
  }

  const monthsPerYear = projectionConfig.months_per_year
  const pathCount = Math.max(projectionConfig.minimum_paths, Math.floor(Number(input.paths) || projectionConfig.paths))
  const maximumMonths = projectionConfig.maximum_horizon_years * monthsPerYear
  const accumulationMonths = clamp(Math.round(Number(input.accumulationMonths) || monthsPerYear), projectionConfig.minimum_horizon_years * monthsPerYear, maximumMonths)
  const withdrawalMonths = clamp(Math.round(Number(input.withdrawalMonths) || 0), 0, maximumMonths - accumulationMonths)
  const totalMonths = accumulationMonths + withdrawalMonths
  const currentBalance = Math.max(0, Number(input.currentBalance) || 0)
  const monthlyContribution = Math.max(0, Number(input.monthlyContribution) || 0)
  const monthlyWithdrawal = Math.max(0, Number(input.monthlyWithdrawal) || 0)
  const annualInflationRate = Math.max(-0.99, (Number(input.inflationPct) || 0) / 100)
  const random = seededRandom(input.seed ?? Date.now())
  const sampleMonths = [0]
  for (let month = monthsPerYear; month <= totalMonths; month += monthsPerYear) sampleMonths.push(month)
  if (sampleMonths.at(-1) !== totalMonths) sampleMonths.push(totalMonths)
  const samples = sampleMonths.map(() => new Float64Array(pathCount))
  const retirementSamples = new Float64Array(pathCount)
  const latestBlockStart = monthlyReturns.length - blockMonths
  let survived = 0

  for (let path = 0; path < pathCount; path += 1) {
    let balance = currentBalance
    let blockStart = 0
    let sampleIndex = 1
    samples[0][path] = balance
    for (let month = 1; month <= totalMonths; month += 1) {
      const offset = (month - 1) % blockMonths
      if (offset === 0) blockStart = Math.floor(random() * (latestBlockStart + 1))
      balance *= 1 + monthlyReturns[blockStart + offset]
      if (month <= accumulationMonths) {
        balance += monthlyContribution
      } else {
        const withdrawalMonth = month - accumulationMonths - 1
        const inflationFactor = (1 + annualInflationRate) ** (withdrawalMonth / monthsPerYear)
        balance -= monthlyWithdrawal * inflationFactor
      }
      balance = Math.max(0, balance)
      if (month === accumulationMonths) retirementSamples[path] = balance
      if (month === sampleMonths[sampleIndex]) {
        samples[sampleIndex][path] = balance
        sampleIndex += 1
      }
    }
    if (!withdrawalMonths || balance > 0) survived += 1
  }

  const fan = samples.map((values, index) => {
    const month = sampleMonths[index]
    const nominal = percentileMap(values)
    return { month, year: month / monthsPerYear, phase: month <= accumulationMonths ? 'saving' : 'withdrawal', ...nominal, real: realValues(nominal, month, annualInflationRate) }
  })
  const retirementPercentiles = percentileMap(retirementSamples)
  const terminalPercentiles = Object.fromEntries(['p10', 'p25', 'p50', 'p75', 'p90'].map((key) => [key, fan.at(-1)[key]]))

  return {
    available: true,
    model: `${blockMonths}-month historical block bootstrap`,
    pathCount,
    blockMonths,
    accumulationMonths,
    withdrawalMonths,
    fan,
    retirementPercentiles,
    retirementPercentilesReal: realValues(retirementPercentiles, accumulationMonths, annualInflationRate),
    terminalPercentiles,
    terminalPercentilesReal: realValues(terminalPercentiles, totalMonths, annualInflationRate),
    successProbability: withdrawalMonths ? survived / pathCount : null,
  }
}
