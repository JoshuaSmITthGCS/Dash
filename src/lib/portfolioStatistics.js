/**
 * Pure portfolio statistics. This module has no presentation or status-colour logic.
 * Every public calculation either returns a measured value from supplied inputs or an
 * explicit unavailable result naming the missing dependency.
 */

export const TRADING_DAYS = 252
const DAY_MS = 86_400_000
const EPSILON = 1e-12

const finite = (value) => value !== null && value !== '' && Number.isFinite(Number(value))
const average = (values) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null

export function sampleDeviation(values = []) {
  if (values.length < 2) return null
  const center = average(values)
  return Math.sqrt(values.reduce((sum, value) => sum + (value - center) ** 2, 0) / (values.length - 1))
}

export function simpleReturns(values = []) {
  return values.slice(1).map((value, index) => (
    finite(value) && finite(values[index]) && Number(values[index]) > 0
      ? Number(value) / Number(values[index]) - 1
      : null
  )).filter(finite)
}

function weekdaysBetween(first, last) {
  const start = Date.parse(first)
  const end = Date.parse(last)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return 0
  let count = 0
  for (let value = start; value <= end; value += DAY_MS) {
    const day = new Date(value).getUTCDay()
    if (day !== 0 && day !== 6) count += 1
  }
  return count
}

export function dailyCadence(series) {
  const dates = series?.dates || []
  if (dates.length < 2) {
    return { valid: false, observations: dates.length, reason: 'At least two dated observations are required.' }
  }
  if (series.frequency && series.frequency !== 'daily') {
    const reason = series.frequency === 'cash-flow-unverified'
      ? 'Confirm the complete external cash-flow ledger before treating recorded account-value changes as strategy returns.'
      : 'Native daily analytics history is required; the available series is a compact chart grid.'
    return { valid: false, observations: dates.length, reason }
  }
  const expectedWeekdays = weekdaysBetween(dates[0], dates.at(-1))
  const coveragePct = expectedWeekdays ? dates.length / expectedWeekdays * 100 : 0
  const gaps = dates.slice(1).map((date, index) => Math.round((Date.parse(date) - Date.parse(dates[index])) / DAY_MS))
  const largeGaps = gaps.filter((gap) => gap > 4).length
  // Weekday count intentionally includes market holidays, so a good exchange tape lands
  // around 96%. The 90% floor catches a display grid without penalising normal holidays.
  const valid = coveragePct >= 90 && gaps.every((gap) => gap > 0)
  return {
    valid,
    observations: dates.length,
    returns: dates.length - 1,
    startDate: dates[0],
    endDate: dates.at(-1),
    expectedWeekdays,
    coveragePct,
    largeGaps,
    meanGapDays: average(gaps),
    maxGapDays: Math.max(...gaps),
    reason: valid ? null : `Daily series coverage is ${coveragePct.toFixed(1)}% (${dates.length} observations across ${expectedWeekdays} expected weekdays).`,
  }
}

// Abramowitz and Stegun 7.1.26; maximum error is sufficient for displayed probabilities.
export function normalCdf(value) {
  const sign = value < 0 ? -1 : 1
  const x = Math.abs(value) / Math.sqrt(2)
  const t = 1 / (1 + 0.3275911 * x)
  const coefficients = [0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429]
  const polynomial = coefficients.reduceRight((result, coefficient) => (result + coefficient) * t, 0)
  const erf = sign * (1 - polynomial * Math.exp(-x * x))
  return (1 + erf) / 2
}

// Peter J. Acklam's inverse-normal approximation.
export function inverseNormal(probability) {
  if (!(probability > 0 && probability < 1)) return probability === 0 ? -Infinity : probability === 1 ? Infinity : null
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239]
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572]
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783]
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416]
  const low = 0.02425
  const high = 1 - low
  if (probability < low) {
    const q = Math.sqrt(-2 * Math.log(probability))
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
      / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  if (probability > high) {
    const q = Math.sqrt(-2 * Math.log(1 - probability))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
      / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
  }
  const q = probability - 0.5
  const r = q * q
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
    / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
}

export function distributionMoments(values = []) {
  const clean = values.filter(finite).map(Number)
  if (clean.length < 3) return { available: false, reason: 'At least three returns are required for distribution moments.' }
  const center = average(clean)
  const second = average(clean.map((value) => (value - center) ** 2))
  if (!(second > 0)) return { available: false, reason: 'Return variance is required for distribution moments.' }
  const third = average(clean.map((value) => (value - center) ** 3))
  const fourth = average(clean.map((value) => (value - center) ** 4))
  return { available: true, skewness: third / second ** 1.5, kurtosis: fourth / second ** 2, excessKurtosis: fourth / second ** 2 - 3 }
}

export function probabilisticSharpe({ sharpePerPeriod, observations, skewness, kurtosis, thresholdPerPeriod = 0 }) {
  if (![sharpePerPeriod, observations, skewness, kurtosis].every(finite) || observations < 2) {
    return { available: false, value: null, reason: 'Sharpe, sample size, skewness, and kurtosis are required for PSR.' }
  }
  const denominatorSquared = 1 - skewness * sharpePerPeriod + ((kurtosis - 1) / 4) * sharpePerPeriod ** 2
  if (!(denominatorSquared > 0)) return { available: false, value: null, reason: 'The PSR denominator is not positive for this return distribution.' }
  const z = (sharpePerPeriod - thresholdPerPeriod) * Math.sqrt(observations - 1) / Math.sqrt(denominatorSquared)
  return { available: true, value: normalCdf(z), z, thresholdPerPeriod }
}

export function minimumTrackRecordLength({ sharpePerPeriod, skewness, kurtosis, thresholdPerPeriod = 0, confidence = 0.95 }) {
  if (![sharpePerPeriod, skewness, kurtosis].every(finite)) {
    return { available: false, observations: null, reason: 'Sharpe, skewness, and kurtosis are required for MinTRL.' }
  }
  if (sharpePerPeriod <= thresholdPerPeriod + EPSILON) {
    return { available: false, observations: null, reason: 'Not estimable at the current Sharpe because it does not exceed the selected threshold.' }
  }
  const adjustment = 1 - skewness * sharpePerPeriod + ((kurtosis - 1) / 4) * sharpePerPeriod ** 2
  const z = inverseNormal(confidence)
  const observations = adjustment * (z / (sharpePerPeriod - thresholdPerPeriod)) ** 2
  return Number.isFinite(observations) && observations > 0
    ? { available: true, observations: Math.ceil(observations), confidence, thresholdPerPeriod }
    : { available: false, observations: null, reason: 'MinTRL is not estimable for this return distribution.' }
}

export function deflatedSharpe({ sharpePerPeriod, observations, skewness, kurtosis, trialCount, trialSharpeVariance }) {
  if (!finite(trialCount)) return { available: false, value: null, reason: 'Trial count not recorded.' }
  if (Number(trialCount) < 2) return { available: false, value: null, reason: 'At least two registered trials are required for DSR.' }
  if (!finite(trialSharpeVariance)) return { available: false, value: null, reason: 'Variance of Sharpes across registered trials is not recorded.' }
  const euler = 0.5772156649015329
  const trials = Number(trialCount)
  const expectedMaximum = Math.sqrt(Number(trialSharpeVariance)) * (
    (1 - euler) * inverseNormal(1 - 1 / trials)
    + euler * inverseNormal(1 - 1 / (trials * Math.E))
  )
  const psr = probabilisticSharpe({ sharpePerPeriod, observations, skewness, kurtosis, thresholdPerPeriod: expectedMaximum })
  return psr.available ? { ...psr, expectedMaximumSharpe: expectedMaximum, trialCount: trials } : psr
}

export function autocorrelation(values = [], lag = 1) {
  if (values.length <= lag || lag < 1) return null
  const center = average(values)
  const denominator = values.reduce((sum, value) => sum + (value - center) ** 2, 0)
  if (!(denominator > 0)) return null
  let numerator = 0
  for (let index = lag; index < values.length; index += 1) {
    numerator += (values[index] - center) * (values[index - lag] - center)
  }
  return numerator / denominator
}

export function loAnnualizationFactor(values = [], periods = TRADING_DAYS) {
  if (values.length < periods + 1) {
    return { available: false, value: null, reason: `Lo-adjusted annualization at q=${periods} requires at least ${periods + 1} returns; ${values.length} available.` }
  }
  let weightedCorrelation = 0
  for (let lag = 1; lag < periods; lag += 1) {
    const rho = autocorrelation(values, lag)
    if (!finite(rho)) return { available: false, value: null, reason: `Autocorrelation at lag ${lag} is not estimable.` }
    weightedCorrelation += (periods - lag) * rho
  }
  const denominator = periods + 2 * weightedCorrelation
  if (!(denominator > 0)) return { available: false, value: null, reason: 'Lo annualization denominator is not positive for this sample.' }
  return { available: true, value: periods / Math.sqrt(denominator), q: periods }
}

export function ljungBox(values = [], requestedLags = 10) {
  const observations = values.length
  const lags = Math.min(requestedLags, observations - 2)
  if (lags < 1) return { available: false, value: null, reason: 'At least three returns are required for Ljung–Box Q.' }
  let statistic = 0
  const correlations = []
  for (let lag = 1; lag <= lags; lag += 1) {
    const rho = autocorrelation(values, lag)
    if (!finite(rho)) return { available: false, value: null, reason: `Autocorrelation at lag ${lag} is not estimable.` }
    correlations.push(rho)
    statistic += rho ** 2 / (observations - lag)
  }
  return { available: true, value: observations * (observations + 2) * statistic, lags, correlations }
}

function quantile(values, probability) {
  if (!values.length) return null
  const sorted = values.slice().sort((left, right) => left - right)
  const position = (sorted.length - 1) * probability
  const lower = Math.floor(position)
  const weight = position - lower
  return sorted[lower + 1] == null ? sorted[lower] : sorted[lower] * (1 - weight) + sorted[lower + 1] * weight
}

function compounded(rows) {
  return rows.reduce((product, value) => product * (1 + value), 1) - 1
}

function calendarReturns(series, prefixLength) {
  const values = new Map()
  ;(series?.dates || []).forEach((date, index) => {
    const value = Number(series.values?.[index])
    if (date && finite(value)) values.set(String(date).slice(0, prefixLength), value)
  })
  const keys = [...values.keys()].sort()
  return keys.slice(1).map((key, index) => {
    const previous = values.get(keys[index])
    return previous > 0 ? values.get(key) / previous - 1 : null
  }).filter(finite)
}

export function drawdownDistribution(series) {
  const dates = series?.dates || []
  const values = series?.values || []
  if (values.length < 2 || dates.length !== values.length) return { available: false, reason: 'Dated portfolio values are required for drawdown duration.' }
  let peak = Number(values[0])
  let peakDate = dates[0]
  let episode = null
  const episodes = []
  const drawdowns = []
  values.forEach((raw, index) => {
    const value = Number(raw)
    if (value >= peak) {
      if (episode) {
        episodes.push({
          ...episode,
          recoveredAt: dates[index],
          durationDays: Math.round((Date.parse(dates[index]) - Date.parse(episode.startedAt)) / DAY_MS),
          recoveryDays: Math.round((Date.parse(dates[index]) - Date.parse(episode.troughAt)) / DAY_MS),
          ongoing: false,
        })
        episode = null
      }
      peak = value
      peakDate = dates[index]
    }
    const drawdown = peak > 0 ? value / peak - 1 : 0
    drawdowns.push(drawdown)
    if (drawdown < 0) {
      if (!episode) episode = { startedAt: peakDate, troughAt: dates[index], depthPct: drawdown * 100 }
      if (drawdown * 100 < episode.depthPct) episode = { ...episode, troughAt: dates[index], depthPct: drawdown * 100 }
    }
  })
  if (episode) {
    episodes.push({
      ...episode,
      recoveredAt: null,
      durationDays: Math.round((Date.parse(dates.at(-1)) - Date.parse(episode.startedAt)) / DAY_MS),
      recoveryDays: null,
      ongoing: true,
    })
  }
  return { available: true, drawdowns, episodes }
}

export function tailStatistics(series, returns = simpleReturns(series?.values || [])) {
  if (returns.length < 20) return { available: false, reason: `At least 20 daily returns are required for tail statistics; ${returns.length} available.` }
  const lossAt = (confidence) => Math.max(0, -(quantile(returns, 1 - confidence) || 0) * 100)
  const expectedShortfall = (confidence) => {
    const cutoff = quantile(returns, 1 - confidence)
    const tail = returns.filter((value) => value <= cutoff)
    return Math.max(0, -(average(tail) || 0) * 100)
  }
  const threshold = 0
  const gains = returns.filter((value) => value > threshold).reduce((sum, value) => sum + value - threshold, 0)
  const losses = returns.filter((value) => value < threshold).reduce((sum, value) => sum + threshold - value, 0)
  const drawdown = drawdownDistribution(series)
  const drawdownMagnitudes = drawdown.available ? drawdown.drawdowns.map((value) => Math.abs(value * 100)) : []
  const ulcerIndexPct = drawdownMagnitudes.length ? Math.sqrt(average(drawdownMagnitudes.map((value) => value ** 2))) : null
  const painIndexPct = drawdownMagnitudes.length ? average(drawdownMagnitudes) : null
  const annualizedReturnPct = series?.values?.length > 1 && Number(series.values[0]) > 0
    ? ((Number(series.values.at(-1)) / Number(series.values[0])) ** (TRADING_DAYS / returns.length) - 1) * 100
    : null
  const weekly = returns.slice(4).map((_, index) => compounded(returns.slice(index, index + 5)))
  const monthly = calendarReturns(series, 7)
  const upper = quantile(returns, 0.95)
  const lower = quantile(returns, 0.05)
  return {
    available: true,
    var95Pct: lossAt(0.95),
    var99Pct: lossAt(0.99),
    expectedShortfall95Pct: expectedShortfall(0.95),
    expectedShortfall975Pct: expectedShortfall(0.975),
    expectedShortfall99Pct: expectedShortfall(0.99),
    omega: losses > 0 ? gains / losses : null,
    ulcerIndexPct,
    painIndexPct,
    painRatio: painIndexPct > 0 && finite(annualizedReturnPct) ? annualizedReturnPct / painIndexPct : null,
    tailRatio: lower < 0 ? upper / Math.abs(lower) : null,
    worstDayPct: Math.min(...returns) * 100,
    worstWeekPct: weekly.length ? Math.min(...weekly) * 100 : null,
    worstMonthPct: monthly.length ? Math.min(...monthly) * 100 : null,
    drawdownEpisodes: drawdown.available ? drawdown.episodes : [],
    recoveredEpisodes: drawdown.available ? drawdown.episodes.filter((row) => !row.ongoing) : [],
    annualizedReturnPct,
  }
}

export function rollingSharpe(series, window, riskFreeAnnualPct = 0) {
  const returns = simpleReturns(series?.values || [])
  if (returns.length < window) return []
  const riskFreeDaily = (1 + Number(riskFreeAnnualPct) / 100) ** (1 / TRADING_DAYS) - 1
  return returns.slice(window - 1).map((_, endingIndex) => {
    const index = endingIndex + window - 1
    const sample = returns.slice(index - window + 1, index + 1).map((value) => value - riskFreeDaily)
    const deviation = sampleDeviation(sample)
    return { date: series.dates[index + 1], value: deviation ? average(sample) / deviation * Math.sqrt(TRADING_DAYS) : null }
  })
}

export function regimeConditionalPerformance(portfolioSeries, benchmarkSeries) {
  if (!portfolioSeries?.dates?.length || !benchmarkSeries?.dates?.length) return { available: false, reason: 'Daily portfolio and benchmark histories are required for regime splits.' }
  const benchmarkByDate = new Map(benchmarkSeries.dates.map((date, index) => [date, benchmarkSeries.values?.[index] ?? benchmarkSeries.closes?.[index]]))
  const rows = portfolioSeries.dates.map((date, index) => ({ date, portfolio: Number(portfolioSeries.values[index]), benchmark: Number(benchmarkByDate.get(date)) }))
    .filter((row) => finite(row.portfolio) && finite(row.benchmark))
  const intervals = rows.slice(1).map((row, index) => ({
    date: row.date,
    portfolio: row.portfolio / rows[index].portfolio - 1,
    benchmark: row.benchmark / rows[index].benchmark - 1,
  }))
  if (intervals.length < 40) return { available: false, reason: `At least 40 overlapping daily returns are required for regime splits; ${intervals.length} available.` }
  const volatilityCutoff = quantile(intervals.map((row) => Math.abs(row.benchmark)), 0.5)
  const summarize = (sample) => ({
    observations: sample.length,
    portfolioReturnPct: compounded(sample.map((row) => row.portfolio)) * 100,
    benchmarkReturnPct: compounded(sample.map((row) => row.benchmark)) * 100,
    meanDailyExcessPct: average(sample.map((row) => row.portfolio - row.benchmark)) * 100,
  })
  return {
    available: true,
    bull: summarize(intervals.filter((row) => row.benchmark >= 0)),
    bear: summarize(intervals.filter((row) => row.benchmark < 0)),
    highVolatility: summarize(intervals.filter((row) => Math.abs(row.benchmark) > volatilityCutoff)),
    lowVolatility: summarize(intervals.filter((row) => Math.abs(row.benchmark) <= volatilityCutoff)),
    methodology: 'Bull/bear uses the sign of each benchmark day. High/low volatility splits absolute benchmark returns at their sample median; these are descriptive regimes, not a fitted market-state model.',
  }
}

export function performanceStatistics(series, riskFreeAnnualPct = 0, options = {}) {
  const cadence = dailyCadence(series)
  if (!cadence.valid) return { available: false, cadence, reason: cadence.reason }
  const returns = simpleReturns(series.values)
  const minimum = Number(options.minimumObservations ?? 20)
  if (returns.length < minimum) return { available: false, observations: returns.length, cadence, reason: `At least ${minimum} daily returns are required; ${returns.length} available.` }
  const riskFreeDaily = (1 + Number(riskFreeAnnualPct) / 100) ** (1 / TRADING_DAYS) - 1
  const excess = returns.map((value) => value - riskFreeDaily)
  const deviation = sampleDeviation(excess)
  if (!(deviation > 0)) return { available: false, observations: returns.length, cadence, reason: 'Non-zero return variance is required.' }
  const sharpePerPeriod = average(excess) / deviation
  const naiveSharpe = sharpePerPeriod * Math.sqrt(TRADING_DAYS)
  const downsideDeviation = Math.sqrt(average(excess.map((value) => Math.min(0, value) ** 2)))
  const sortinoPerPeriod = downsideDeviation > 0 ? average(excess) / downsideDeviation : null
  const moments = distributionMoments(excess)
  const sharpeStandardErrorPerPeriod = Math.sqrt((1 + sharpePerPeriod ** 2 / 2) / returns.length)
  const sharpeStandardErrorAnnual = sharpeStandardErrorPerPeriod * Math.sqrt(TRADING_DAYS)
  const psr = moments.available ? probabilisticSharpe({ sharpePerPeriod, observations: returns.length, ...moments }) : { available: false, value: null, reason: moments.reason }
  const minTrackRecord = moments.available ? minimumTrackRecordLength({ sharpePerPeriod, ...moments }) : { available: false, observations: null, reason: moments.reason }
  const loFactor = loAnnualizationFactor(excess, TRADING_DAYS)
  const ljung = ljungBox(excess)
  const trialCount = options.trialCount
  const dsr = moments.available ? deflatedSharpe({
    sharpePerPeriod,
    observations: returns.length,
    skewness: moments.skewness,
    kurtosis: moments.kurtosis,
    trialCount,
    trialSharpeVariance: options.trialSharpeVariance,
  }) : { available: false, value: null, reason: moments.reason }
  return {
    available: true,
    observations: returns.length,
    startDate: series.dates[0],
    endDate: series.dates.at(-1),
    frequency: 'daily',
    cadence,
    returns,
    excessReturns: excess,
    sharpePerPeriod,
    naiveSharpe,
    loAdjustedSharpe: loFactor.available ? sharpePerPeriod * loFactor.value : null,
    naiveSortino: finite(sortinoPerPeriod) ? sortinoPerPeriod * Math.sqrt(TRADING_DAYS) : null,
    loAdjustedSortino: loFactor.available && finite(sortinoPerPeriod) ? sortinoPerPeriod * loFactor.value : null,
    naiveVolatilityPct: deviation * Math.sqrt(TRADING_DAYS) * 100,
    loAdjustedVolatilityPct: loFactor.available ? deviation * loFactor.value * 100 : null,
    loFactor,
    sharpeStandardErrorPerPeriod,
    sharpeStandardErrorAnnual,
    sharpeConfidence95: [naiveSharpe - 1.96 * sharpeStandardErrorAnnual, naiveSharpe + 1.96 * sharpeStandardErrorAnnual],
    sharpeTStatistic: sharpePerPeriod * Math.sqrt(returns.length),
    psr,
    minTrackRecord,
    dsr,
    trialCount: finite(trialCount) ? Number(trialCount) : null,
    moments,
    autocorrelation1: autocorrelation(excess, 1),
    ljungBox: ljung,
    rolling60: rollingSharpe(series, 60, riskFreeAnnualPct),
    rolling120: rollingSharpe(series, 120, riskFreeAnnualPct),
    tail: tailStatistics(series, returns),
  }
}

function covariance(left, right) {
  if (left.length !== right.length || left.length < 2) return null
  const leftMean = average(left)
  const rightMean = average(right)
  return left.reduce((sum, value, index) => sum + (value - leftMean) * (right[index] - rightMean), 0) / (left.length - 1)
}

export function benchmarkFit(portfolioSeries, candidates = []) {
  const portfolioByDate = new Map((portfolioSeries?.dates || []).map((date, index) => [date, portfolioSeries.values?.[index]]))
  const diagnostics = candidates.map((candidate) => {
    const candidateValues = candidate.values || candidate.closes || []
    const rows = (candidate.dates || []).map((date, index) => ({ date, benchmark: Number(candidateValues[index]), portfolio: Number(portfolioByDate.get(date)) }))
      .filter((row) => finite(row.portfolio) && finite(row.benchmark))
    if (rows.length < 21) return { symbol: candidate.symbol, label: candidate.label || candidate.symbol, available: false, reason: `At least 20 overlapping returns are required; ${Math.max(0, rows.length - 1)} available.` }
    const portfolioReturns = rows.slice(1).map((row, index) => row.portfolio / rows[index].portfolio - 1)
    const benchmarkReturns = rows.slice(1).map((row, index) => row.benchmark / rows[index].benchmark - 1)
    const benchmarkVariance = covariance(benchmarkReturns, benchmarkReturns)
    const portfolioVariance = covariance(portfolioReturns, portfolioReturns)
    const cross = covariance(portfolioReturns, benchmarkReturns)
    const beta = benchmarkVariance > 0 ? cross / benchmarkVariance : null
    const correlation = portfolioVariance > 0 && benchmarkVariance > 0 ? cross / Math.sqrt(portfolioVariance * benchmarkVariance) : null
    const active = portfolioReturns.map((value, index) => value - benchmarkReturns[index])
    const trackingDeviation = sampleDeviation(active)
    const loTrackingFactor = loAnnualizationFactor(active, TRADING_DAYS)
    const informationRatio = trackingDeviation ? average(active) / trackingDeviation * Math.sqrt(TRADING_DAYS) : null
    return {
      symbol: candidate.symbol,
      label: candidate.label || candidate.symbol,
      available: true,
      observations: portfolioReturns.length,
      startDate: rows[0].date,
      endDate: rows.at(-1).date,
      beta,
      correlation,
      trackingErrorPct: trackingDeviation * Math.sqrt(TRADING_DAYS) * 100,
      loAdjustedTrackingErrorPct: loTrackingFactor.available ? trackingDeviation * loTrackingFactor.value * 100 : null,
      loTrackingFactor,
      rSquared: correlation ** 2,
      informationRatio,
      fitDistance: Math.abs(beta - 1) + (1 - correlation),
    }
  })
  const available = diagnostics.filter((row) => row.available && finite(row.fitDistance)).sort((left, right) => left.fitDistance - right.fitDistance)
  return {
    available: available.length > 0,
    candidates: diagnostics,
    bestFit: available[0] || null,
    sectorNeutral: { available: false, reason: 'Sector-neutral benchmark constituent returns and rebalance weights are not available.' },
    methodology: 'Best fit minimises |beta − 1| plus (1 − correlation) on the same daily return sample. It is a diagnostic, not a silent benchmark replacement.',
  }
}

/** Euclidean projection of a vector onto the probability simplex {w : w_i >= 0, sum(w) = 1}. */
function projectOntoSimplex(values) {
  const n = values.length
  const sorted = [...values].sort((left, right) => right - left)
  let cumulative = 0
  let rho = 0
  const cumulativeSums = sorted.map((value) => (cumulative += value))
  for (let index = 0; index < n; index += 1) {
    const threshold = (cumulativeSums[index] - 1) / (index + 1)
    if (sorted[index] - threshold > 0) rho = index
  }
  const theta = (cumulativeSums[rho] - 1) / (rho + 1)
  return values.map((value) => Math.max(value - theta, 0))
}

/**
 * Non-negative weights summing to 1 that minimise sum((portfolioReturns - blend)^2), by
 * projected gradient descent on the simplex. Convex objective + a step size bounded by the
 * gradient's Lipschitz constant guarantees monotonic convergence to the global optimum
 * regardless of the (uniform) starting point -- no random seed, no local-minimum risk,
 * deterministic across runs. The Lipschitz bound is estimated from the trace of the
 * candidates' Gram matrix (trace >= largest eigenvalue for a PSD matrix), which is loose
 * but safe, and matters here because daily returns are ~1e-2 in scale: a step size chosen
 * without accounting for that (e.g. a bare constant) is either too large to converge or,
 * as small as it would need to be to stay stable, too small to move off the starting point
 * within any reasonable iteration budget.
 */
function fitSimplexWeights(portfolioReturns, candidateReturnsMatrix, iterations = 3000) {
  const assetCount = candidateReturnsMatrix.length
  const observationCount = portfolioReturns.length
  let weights = new Array(assetCount).fill(1 / assetCount)
  let energy = 0
  for (const series of candidateReturnsMatrix) {
    for (const value of series) energy += value * value
  }
  const lipschitzBound = (2 / observationCount) * energy
  const learningRate = lipschitzBound > 0 ? 1 / lipschitzBound : 0
  if (!(learningRate > 0)) return weights
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const predicted = new Array(observationCount).fill(0)
    for (let asset = 0; asset < assetCount; asset += 1) {
      const weight = weights[asset]
      const series = candidateReturnsMatrix[asset]
      for (let t = 0; t < observationCount; t += 1) predicted[t] += weight * series[t]
    }
    const residual = predicted.map((value, t) => value - portfolioReturns[t])
    const gradient = candidateReturnsMatrix.map((series) => {
      let sum = 0
      for (let t = 0; t < observationCount; t += 1) sum += series[t] * residual[t]
      return (2 / observationCount) * sum
    })
    weights = projectOntoSimplex(weights.map((weight, asset) => weight - learningRate * gradient[asset]))
  }
  return weights
}

/**
 * A blended benchmark constructed from the same candidate indices `benchmarkFit` picks a
 * single winner from (Master Remediation Prompt v3 roadmap item 17), instead of forcing
 * the portfolio's comparison onto whichever one index fits best. Non-negative weights
 * summing to 1 are fit by minimising tracking error against the portfolio's own daily
 * returns -- classic returns-based style analysis (Sharpe 1992), not a claim about actual
 * sector or factor exposure, and refit fresh every time this is computed rather than stored.
 */
export function constructedBenchmarkFit(portfolioSeries, candidates = []) {
  const usable = candidates.filter((candidate) =>
    Array.isArray(candidate?.dates) && Array.isArray(candidate?.values) && candidate.dates.length === candidate.values.length)
  if (usable.length < 2) {
    return { available: false, reason: 'At least two benchmark candidates with return histories are required to construct a blend.' }
  }
  const portfolioByDate = new Map((portfolioSeries?.dates || []).map((date, index) => [date, Number(portfolioSeries.values?.[index])]))
  const candidateMaps = usable.map((candidate) => new Map(candidate.dates.map((date, index) => [date, Number(candidate.values[index])])))
  const commonDates = (portfolioSeries?.dates || [])
    .filter((date) => finite(portfolioByDate.get(date)) && candidateMaps.every((map) => finite(map.get(date))))
  if (commonDates.length < 22) {
    return {
      available: false,
      reason: `At least 21 overlapping returns are required across every candidate; ${Math.max(0, commonDates.length - 1)} available.`,
    }
  }
  const portfolioValues = commonDates.map((date) => portfolioByDate.get(date))
  const candidateValueSeries = candidateMaps.map((map) => commonDates.map((date) => map.get(date)))
  const portfolioReturns = portfolioValues.slice(1).map((value, index) => value / portfolioValues[index] - 1)
  const candidateReturns = candidateValueSeries.map((series) => series.slice(1).map((value, index) => value / series[index] - 1))

  const weights = fitSimplexWeights(portfolioReturns, candidateReturns)
  const blendedReturns = portfolioReturns.map((_, t) =>
    candidateReturns.reduce((sum, series, asset) => sum + weights[asset] * series[t], 0))
  const active = portfolioReturns.map((value, index) => value - blendedReturns[index])
  const benchmarkVariance = covariance(blendedReturns, blendedReturns)
  const portfolioVariance = covariance(portfolioReturns, portfolioReturns)
  const cross = covariance(portfolioReturns, blendedReturns)
  const beta = benchmarkVariance > 0 ? cross / benchmarkVariance : null
  const correlation = portfolioVariance > 0 && benchmarkVariance > 0 ? cross / Math.sqrt(portfolioVariance * benchmarkVariance) : null
  const trackingDeviation = sampleDeviation(active)
  const informationRatio = trackingDeviation ? average(active) / trackingDeviation * Math.sqrt(TRADING_DAYS) : null

  return {
    available: true,
    observations: portfolioReturns.length,
    startDate: commonDates[1],
    endDate: commonDates.at(-1),
    weights: usable.map((candidate, index) => ({
      symbol: candidate.symbol, label: candidate.label || candidate.symbol, weight: weights[index],
    })).sort((left, right) => right.weight - left.weight),
    beta,
    correlation,
    rSquared: correlation != null ? correlation ** 2 : null,
    trackingErrorPct: trackingDeviation != null ? trackingDeviation * Math.sqrt(TRADING_DAYS) * 100 : null,
    informationRatio,
    methodology: 'Non-negative weights summing to 1, fit by minimising tracking error against the '
      + "portfolio's own daily returns (returns-based style analysis). A diagnostic constructed fresh "
      + 'each time, not a claim about actual sector/factor exposure and not a stored or silently reused benchmark.',
  }
}

export function exposureStatistics(positions = []) {
  const measured = positions.filter((row) => finite(row.currentValue) && Number(row.currentValue) !== 0)
  const totalAbsolute = measured.reduce((sum, row) => sum + Math.abs(Number(row.currentValue)), 0)
  if (!(totalAbsolute > 0)) return { available: false, reason: 'Priced position values are required for exposure statistics.' }
  const totalValue = measured.reduce((sum, row) => sum + Number(row.currentValue), 0)
  const weights = measured.map((row) => Number(row.currentValue) / totalAbsolute)
  const hhi = weights.reduce((sum, weight) => sum + weight ** 2, 0)
  const longValue = measured.filter((row) => Number(row.currentValue) > 0).reduce((sum, row) => sum + Number(row.currentValue), 0)
  const shortValue = measured.filter((row) => Number(row.currentValue) < 0).reduce((sum, row) => sum + Math.abs(Number(row.currentValue)), 0)
  return {
    available: true,
    grossExposurePct: totalValue ? totalAbsolute / Math.abs(totalValue) * 100 : null,
    netExposurePct: totalValue ? (longValue - shortValue) / Math.abs(totalValue) * 100 : null,
    leverage: totalValue ? totalAbsolute / Math.abs(totalValue) : null,
    longExposurePct: totalValue ? longValue / Math.abs(totalValue) * 100 : null,
    shortExposurePct: totalValue ? shortValue / Math.abs(totalValue) * 100 : null,
    positionCount: measured.length,
    maxPositionWeightPct: Math.max(...weights.map((weight) => Math.abs(weight))) * 100,
    hhi,
    effectivePositions: hhi > 0 ? 1 / hhi : null,
    sectorTilts: { available: false, reason: 'Benchmark sector weights are required for sector tilts.' },
    advParticipation: { available: false, reason: 'Position-level order sizes are required for ADV participation.' },
  }
}

/** Compute turnover and break-even cost only from an actual position-level rebalance ledger. */
export function executionStatistics({ returns = [], rebalances = [], riskFreePerPeriod = 0 } = {}) {
  if (!Array.isArray(rebalances) || !rebalances.length) {
    return { available: false, reason: 'Position-level trade or rebalance data is required; turnover is not estimated from returns.' }
  }
  const rows = rebalances.map((rebalance) => {
    const keys = new Set([...Object.keys(rebalance.beforeWeights || {}), ...Object.keys(rebalance.afterWeights || {})])
    const oneWay = 0.5 * [...keys].reduce((sum, key) => sum + Math.abs(Number(rebalance.afterWeights?.[key] || 0) - Number(rebalance.beforeWeights?.[key] || 0)), 0)
    return { ...rebalance, oneWayTurnover: oneWay, twoWayTurnover: 2 * oneWay }
  })
  const dated = rows.filter((row) => row.date).sort((left, right) => left.date.localeCompare(right.date))
  const spanYears = dated.length > 1 ? (Date.parse(dated.at(-1).date) - Date.parse(dated[0].date)) / (365.25 * DAY_MS) : null
  const annualOneWayTurnover = spanYears > 0 ? rows.reduce((sum, row) => sum + row.oneWayTurnover, 0) / spanYears : null
  const totalTwoWay = rows.reduce((sum, row) => sum + row.twoWayTurnover, 0)
  const excess = returns.filter(finite).map((value) => Number(value) - Number(riskFreePerPeriod || 0))
  const grossExcess = average(excess)
  const twoWayPerPeriod = excess.length ? totalTwoWay / excess.length : null
  const breakEvenCostBps = grossExcess > 0 && twoWayPerPeriod > 0 ? grossExcess / twoWayPerPeriod * 10_000 : null
  return {
    available: true,
    rebalances: rows,
    oneWayTurnover: rows.reduce((sum, row) => sum + row.oneWayTurnover, 0),
    twoWayTurnover: totalTwoWay,
    annualOneWayTurnover,
    averageHoldingPeriodYears: annualOneWayTurnover > 0 ? 1 / annualOneWayTurnover : null,
    breakEvenCostBps,
    netReturnsAtCost: (costBps) => excess.map((value) => value - Number(costBps) / 10_000 * twoWayPerPeriod),
    grossVsNet: { available: false, reason: 'Realized spreads, commissions, market impact, and trade timestamps are required for net returns and net Sharpe.' },
    costDrag: { available: false, reason: 'Realized all-in trading costs are required for cost drag.' },
    capacity: { available: false, reason: 'Position-level order sizes, volatility, ADV, and realized premium are required for capacity.' },
  }
}

export function robustnessStatistics(payload = {}) {
  const missing = []
  if (!finite(payload.inSampleAnnualPct)) missing.push('in-sample annualized performance')
  if (!finite(payload.outOfSampleAnnualPct)) missing.push('out-of-sample annualized performance')
  const wfe = missing.length || Number(payload.inSampleAnnualPct) === 0 ? null : Number(payload.outOfSampleAnnualPct) / Number(payload.inSampleAnnualPct)
  return {
    walkForwardEfficiency: missing.length
      ? { available: false, value: null, reason: `${missing.join(' and ')} required for WFE.` }
      : { available: true, value: wfe, convention: 'WFE above 0.5 is a robustness convention, not a statistical cutoff.' },
    pbo: finite(payload.pbo)
      ? { available: true, value: Number(payload.pbo) }
      : { available: false, value: null, reason: 'Combinatorially symmetric cross-validation results are required for PBO.' },
    cpcv: payload.cpcv
      ? { available: true, value: payload.cpcv }
      : { available: false, value: null, reason: 'Purged and embargoed combinatorial cross-validation results are required.' },
    parameterSensitivity: payload.parameterSensitivity
      ? { available: true, value: payload.parameterSensitivity }
      : { available: false, value: null, reason: 'Registered parameter-sweep results are required for plateau analysis.' },
  }
}
