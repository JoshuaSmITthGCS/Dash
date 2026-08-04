const PERIOD_DAYS = { '1D': 2, '1W': 7, '1M': 31, '3M': 93, '6M': 186, '1Y': 366, All: null }

const finite = (value) => value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))
const clamp = (value, min = 0, max = 100) => Math.max(min, Math.min(max, value))

export const BENCHMARKS = [
  { symbol: 'SPY', label: 'S&P 500', proxy: true, index: 'S&P 500 Index' },
  { symbol: 'QQQ', label: 'Nasdaq-100', proxy: true, index: 'Nasdaq-100 Index' },
  { symbol: 'DIA', label: 'Dow Jones', proxy: true, index: 'Dow Jones Industrial Average' },
  { symbol: 'IWM', label: 'Russell 2000', proxy: true, index: 'Russell 2000 Index' },
  { symbol: 'VTI', label: 'U.S. total market', proxy: true, index: 'CRSP U.S. Total Market Index' },
  { symbol: 'VEA', label: 'Developed ex-U.S.', proxy: true, index: 'FTSE Developed ex U.S. Index' },
  { symbol: 'VWO', label: 'Emerging markets', proxy: true, index: 'FTSE Emerging Markets Index' },
  { symbol: 'VXUS', label: 'Global ex-U.S.', proxy: true, index: 'FTSE Global All Cap ex U.S. Index' },
]

export function benchmarkHistoryFromSnapshot(snapshot) {
  const rows = snapshot?.price_series?.fund
  if (!Array.isArray(rows)) return null
  const usable = rows.filter((row) => row?.date && finite(row.adjusted_close))
  if (usable.length < 2) return null
  return { dates: usable.map((row) => row.date), closes: usable.map((row) => Number(row.adjusted_close)), source: snapshot.benchmark, symbol: snapshot.ticker }
}

export function enrichPortfolio(positions = [], priceData = {}) {
  const enriched = positions.map((position) => {
    const ticker = String(position.ticker || '').trim().toUpperCase()
    const source = priceData[ticker]
    const shares = Number(position.shares)
    const costBasis = Number(position.costBasis)
    const currentPrice = finite(source?.price) ? Number(source.price) : finite(position.snapshotPrice) ? Number(position.snapshotPrice) : null
    const totalCost = finite(shares) && finite(costBasis) ? shares * costBasis : null
    const currentValue = currentPrice == null || !finite(shares) ? null : shares * currentPrice
    const gain = currentValue == null || totalCost == null ? null : currentValue - totalCost
    return { ...position, ticker, shares, costBasis, currentPrice, totalCost, currentValue, gain, gainPct: totalCost > 0 && gain != null ? gain / totalCost * 100 : null, allocationPct: null, priceInfo: source }
  })
  const totalValue = enriched.reduce((sum, row) => sum + (row.currentValue || 0), 0)
  const totalCost = enriched.reduce((sum, row) => sum + (row.totalCost || 0), 0)
  const priced = enriched.filter((row) => row.currentValue != null).length
  return {
    positions: enriched.map((row) => ({ ...row, allocationPct: totalValue > 0 && row.currentValue != null ? row.currentValue / totalValue * 100 : null })),
    totalValue: priced ? totalValue : null,
    totalCost: enriched.some((row) => row.totalCost != null) ? totalCost : null,
    gain: priced && totalCost > 0 ? totalValue - totalCost : null,
    gainPct: priced && totalCost > 0 ? (totalValue - totalCost) / totalCost * 100 : null,
    coveragePct: positions.length ? priced / positions.length * 100 : 0,
  }
}

function closeMap(history) {
  return new Map((history?.dates || []).map((date, index) => [date, history.closes?.[index]]).filter(([, value]) => finite(value)))
}

export function currentHoldingsSeries(positions = [], priceData = {}, anchorDates = []) {
  const dated = anchorDates.length ? anchorDates : [...new Set(positions.flatMap((position) => priceData[position.ticker]?.history?.dates || []))].sort()
  const tracked = positions.map((position) => ({ position, prices: closeMap(priceData[position.ticker]?.history) })).filter((row) => row.prices.size && finite(row.position.shares))
  if (!tracked.length || dated.length < 2) return null
  const rows = dated.map((date) => {
    let value = 0
    let covered = 0
    tracked.forEach(({ position, prices }) => { const price = prices.get(date); if (finite(price)) { value += Number(position.shares) * Number(price); covered += 1 } })
    return covered === tracked.length ? { date, value, coveragePct: positions.length ? covered / positions.length * 100 : 0 } : null
  }).filter(Boolean)
  if (rows.length < 2) return null
  return { dates: rows.map((row) => row.date), values: rows.map((row) => row.value), coverage: rows.map((row) => row.coveragePct), methodology: 'Current quantities applied to historical daily closes; not actual historical account value.' }
}

export function selectPeriod(series, period = '1M') {
  if (!series?.dates?.length || !series?.values?.length) return null
  const days = PERIOD_DAYS[period] ?? null
  const endMs = Date.parse(series.dates.at(-1))
  const foundIndex = days == null ? 0 : series.dates.findIndex((date) => Date.parse(date) >= endMs - days * 86400000)
  const startIndex = days == null ? 0 : foundIndex < 0 ? Math.max(0, series.dates.length - 2) : foundIndex
  const dates = series.dates.slice(startIndex)
  const values = series.values.slice(startIndex)
  if (values.length < 2) return null
  const start = values[0]
  const end = values.at(-1)
  const dollarReturn = end - start
  return { period, dates, values, startDate: dates[0], endDate: dates.at(-1), startValue: start, endValue: end, dollarReturn, returnPct: start ? dollarReturn / start * 100 : null, high: Math.max(...values), low: Math.min(...values), coveragePct: series.coverage?.slice(startIndex).reduce((sum, value) => sum + value, 0) / values.length || null, methodology: series.methodology }
}

export function latestMarketDayReturn(series) {
  if (!series?.values || series.values.length < 2) return null
  const previous = series.values.at(-2)
  const current = series.values.at(-1)
  return { date: series.dates.at(-1), previousDate: series.dates.at(-2), dollarReturn: current - previous, returnPct: previous ? (current - previous) / previous * 100 : null, currentValue: current }
}

export function alignSeries(left, right, period = left?.period || right?.period || 'All') {
  if (!left?.dates?.length || !right?.dates?.length) return null
  const rightValues = new Map(right.dates.map((date, index) => [date, right.values[index]]))
  const rows = left.dates.map((date, index) => ({ date, left: left.values[index], right: rightValues.get(date) })).filter((row) => finite(row.left) && finite(row.right))
  if (rows.length < 2) return null
  const make = (key) => selectPeriod({ dates: rows.map((row) => row.date), values: rows.map((row) => row[key]) }, 'All')
  return { dates: rows.map((row) => row.date), left: { ...make('left'), period }, right: { ...make('right'), period } }
}

export function intradayPortfolioHigh(points = []) {
  const usable = points.filter((point) => point?.timestamp && finite(point.value))
  if (!usable.length) return null
  const high = usable.reduce((best, point) => Number(point.value) > Number(best.value) ? point : best)
  const current = Number(usable.at(-1).value)
  return { value: Number(high.value), timestamp: high.timestamp, belowHigh: Number(high.value) - current }
}

export function netInvestedCapital(transactions) {
  if (!Array.isArray(transactions) || !transactions.length) return { available: false, value: null, reason: 'Complete contribution and withdrawal history is unavailable.' }
  const external = transactions.filter((row) => ['deposit', 'withdrawal'].includes(row.type) && finite(row.amount))
  if (!external.length || external.some((row) => !row.date)) return { available: false, value: null, reason: 'Complete dated external cash flows are unavailable.' }
  return { available: true, value: external.reduce((sum, row) => sum + (row.type === 'deposit' ? Number(row.amount) : -Number(row.amount)), 0), reason: 'External deposits minus external withdrawals.' }
}

export function scenarioProjection(currentValue, annualRate, years, recurringAnnual = 0) {
  if (!finite(currentValue) || !finite(annualRate) || !finite(years)) return null
  const rate = Number(annualRate) / 100
  let value = Number(currentValue)
  for (let year = 0; year < Number(years); year += 1) value = value * (1 + rate) + Number(recurringAnnual || 0)
  return value
}

export function diversificationScore(positions = []) {
  const priced = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0)
  const total = priced.reduce((sum, row) => sum + Number(row.currentValue), 0)
  if (!total) return { available: false, score: null, coveragePct: 0, components: {}, warnings: [] }
  const weights = priced.map((row) => ({ ...row, pct: Number(row.currentValue) / total * 100 })).sort((a, b) => b.pct - a.pct)
  const group = (field) => Object.values(weights.reduce((acc, row) => { const key = row.priceInfo?.[field] || 'Unclassified'; acc[key] = (acc[key] || 0) + row.pct; return acc }, {})).sort((a, b) => b - a)
  const sectors = group('sector'); const industries = group('industry')
  const largest = weights[0]?.pct || 100; const topFive = weights.slice(0, 5).reduce((sum, row) => sum + row.pct, 0)
  const meaningful = weights.filter((row) => row.pct >= 2).length
  const components = { positionBalance: clamp(100 - Math.max(0, largest - 10) * 2.7), topFiveBalance: clamp(100 - Math.max(0, topFive - 50) * 1.5), sectorBalance: clamp(100 - Math.max(0, (sectors[0] || 100) - 25) * 1.8), industryBalance: clamp(100 - Math.max(0, (industries[0] || 100) - 20) * 1.5), meaningfulPositions: clamp(meaningful / 12 * 100) }
  const score = Math.round(components.positionBalance * .3 + components.topFiveBalance * .2 + components.sectorBalance * .25 + components.industryBalance * .15 + components.meaningfulPositions * .1)
  const warnings = []; if (largest > 25) warnings.push(`Largest holding is ${largest.toFixed(1)}% of portfolio`); if ((sectors[0] || 0) > 35) warnings.push(`Largest sector is ${(sectors[0]).toFixed(1)}%`); if (topFive > 70) warnings.push(`Top five positions represent ${topFive.toFixed(1)}%`)
  return { available: true, score, coveragePct: priced.length / positions.length * 100, components, warnings, weights, sectors, industries, provisional: priced.length < 5 }
}

export function maximumDrawdown(values = []) { let peak = null; let worst = 0; values.filter(finite).forEach((raw) => { const value = Number(raw); peak = peak == null ? value : Math.max(peak, value); if (peak) worst = Math.min(worst, (value / peak - 1) * 100) }); return values.length > 1 ? worst : null }
export function annualizedVolatility(values = []) { const returns = values.slice(1).map((value, index) => finite(value) && finite(values[index]) && values[index] ? Number(value) / Number(values[index]) - 1 : null).filter(finite); if (returns.length < 2) return null; const mean = returns.reduce((a, b) => a + b, 0) / returns.length; const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1); return Math.sqrt(variance) * Math.sqrt(252) * 100 }

export function resilienceIndex(values = [], diversification = null) {
  if (values.length < 20) return { available: false, score: null, provisional: true, coverage: values.length, reason: 'At least 20 daily observations are required.' }
  const drawdown = maximumDrawdown(values); const volatility = annualizedVolatility(values)
  const drawdownScore = clamp(100 + (drawdown || 0) * 2.5); const volatilityScore = clamp(100 - Math.max(0, (volatility || 0) - 10) * 2.2); const concentrationScore = diversification?.score ?? 50
  return { available: true, score: Math.round(drawdownScore * .45 + volatilityScore * .35 + concentrationScore * .2), provisional: values.length < 60, coverage: values.length, components: { drawdown: drawdownScore, downsideVolatility: volatilityScore, concentration: concentrationScore }, maxDrawdown: drawdown, volatility }
}

export function performanceRating(portfolioPeriod, benchmarkPeriod) {
  if (!portfolioPeriod || !benchmarkPeriod) return { available: false, score: null, rating: 'Unavailable', reason: 'Comparable portfolio and benchmark history is required.' }
  const excess = portfolioPeriod.returnPct - benchmarkPeriod.returnPct; const drawdown = maximumDrawdown(portfolioPeriod.values); const score = Math.round(clamp(65 + excess * 2 + (drawdown || 0) * .8)); const rating = score >= 90 ? 'A' : score >= 80 ? 'B' : score >= 70 ? 'C' : score >= 60 ? 'D' : 'F'
  return { available: true, score, rating, excessReturnPct: excess, period: portfolioPeriod.period, reason: `${excess >= 0 ? 'Outperformed' : 'Trailed'} the benchmark by ${Math.abs(excess).toFixed(1)} percentage points; maximum drawdown ${Math.abs(drawdown || 0).toFixed(1)}%.` }
}

export function concentrationLiquidityScore(positions = []) {
  const weighted = positions.filter((row) => finite(row.currentValue) && row.currentValue > 0 && finite(row.allocationPct))
  if (!weighted.length) return { available: false, score: null, reason: 'Priced position weights are required.' }
  const liquid = weighted.filter((row) => finite(row.priceInfo?.average_dollar_volume) && row.priceInfo.average_dollar_volume > 0)
  const coveragePct = liquid.reduce((sum, row) => sum + row.allocationPct, 0)
  if (coveragePct < 80) return { available: false, score: null, coveragePct, reason: 'Average dollar-volume coverage is below 80% of portfolio value.' }
  const largest = Math.max(...weighted.map((row) => row.allocationPct))
  const concentration = clamp(100 - Math.max(0, largest - 10) * 2.5)
  const liquidity = liquid.reduce((sum, row) => {
    const daysAtTenPctAdv = row.currentValue / (Number(row.priceInfo.average_dollar_volume) * .1)
    return sum + clamp(100 - Math.max(0, daysAtTenPctAdv - 1) * 12) * row.allocationPct / coveragePct
  }, 0)
  return { available: true, score: Math.round(concentration * .55 + liquidity * .45), coveragePct, components: { concentration, liquidity }, reason: 'Combines largest-position concentration with estimated days to liquidate at 10% of published average dollar volume.' }
}

export function opportunityCost(portfolioPeriod, benchmarkPeriod) {
  if (!portfolioPeriod || !benchmarkPeriod || !portfolioPeriod.startValue || !benchmarkPeriod.startValue) return null
  const benchmarkEndingValue = portfolioPeriod.startValue * (benchmarkPeriod.endValue / benchmarkPeriod.startValue)
  const difference = portfolioPeriod.endValue - benchmarkEndingValue
  return { portfolioEndingValue: portfolioPeriod.endValue, benchmarkEndingValue, difference, differencePct: benchmarkEndingValue ? difference / benchmarkEndingValue * 100 : null, startDate: portfolioPeriod.startDate > benchmarkPeriod.startDate ? portfolioPeriod.startDate : benchmarkPeriod.startDate, endDate: portfolioPeriod.endDate < benchmarkPeriod.endDate ? portfolioPeriod.endDate : benchmarkPeriod.endDate, methodology: 'Approximation from the earliest common date using current holdings and no external cash-flow adjustments.' }
}

export function portfolioScore({ diversification, resilience, performance, benchmarkEfficiency, concentrationLiquidity, dataCompleteness = 0 }) {
  const required = [diversification?.score, resilience?.score, performance?.score, benchmarkEfficiency, concentrationLiquidity?.score, dataCompleteness]
  if (required.some((value) => !finite(value))) return { available: false, score: null, provisional: false, reason: 'Diversification, sufficient daily history, an aligned benchmark, liquidity coverage, and price coverage are all required.' }
  const values = { diversification: diversification.score, resilience: resilience.score, riskAdjustedPerformance: performance.score, benchmarkEfficiency, concentrationLiquidity: concentrationLiquidity.score, dataCompleteness }
  const score = Math.round(values.diversification * .25 + values.resilience * .25 + values.riskAdjustedPerformance * .2 + values.benchmarkEfficiency * .15 + values.concentrationLiquidity * .1 + values.dataCompleteness * .05)
  return { available: true, score, provisional: Boolean(diversification.provisional || resilience.provisional || concentrationLiquidity.coveragePct < 100 || dataCompleteness < 100), components: values, strongest: Object.entries(values).sort((a, b) => b[1] - a[1])[0][0], weakest: Object.entries(values).sort((a, b) => a[1] - b[1])[0][0] }
}
