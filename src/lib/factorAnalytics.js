import modelSettings from '../../pipeline/config/settings.json' with { type: 'json' }

const config = modelSettings.portfolio_analytics
const FACTOR_KEYS = ['market_excess', 'size', 'value', 'profitability', 'investment', 'momentum']

const finite = (value) => Number.isFinite(Number(value))

function invertMatrix(input) {
  const size = input.length
  const rows = input.map((row, rowIndex) => [
    ...row.map(Number),
    ...Array.from({ length: size }, (_, columnIndex) => rowIndex === columnIndex ? 1 : 0),
  ])
  for (let column = 0; column < size; column += 1) {
    let pivot = column
    for (let row = column + 1; row < size; row += 1) {
      if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) pivot = row
    }
    if (Math.abs(rows[pivot][column]) <= config.factor_standard_error_tolerance) return null
    ;[rows[column], rows[pivot]] = [rows[pivot], rows[column]]
    const divisor = rows[column][column]
    rows[column] = rows[column].map((value) => value / divisor)
    for (let row = 0; row < size; row += 1) {
      if (row === column) continue
      const multiplier = rows[row][column]
      rows[row] = rows[row].map((value, index) => value - multiplier * rows[column][index])
    }
  }
  return rows.map((row) => row.slice(size))
}

function multiplyMatrixVector(matrix, vector) {
  return matrix.map((row) => row.reduce((sum, value, index) => sum + value * vector[index], 0))
}

function monthlyReturns(series) {
  if (!series?.dates?.length || !series?.values?.length) return new Map()
  const closes = new Map()
  series.dates.forEach((date, index) => {
    if (date && finite(series.values[index])) closes.set(String(date).slice(0, 7), Number(series.values[index]))
  })
  const months = [...closes.keys()].sort()
  return new Map(months.slice(1).map((month, index) => {
    const previous = closes.get(months[index])
    const current = closes.get(month)
    return [month, previous > 0 ? current / previous - 1 : null]
  }).filter(([, value]) => finite(value)))
}

function factorSummary(loadings) {
  const threshold = config.factor_loading_summary_threshold
  const traits = []
  if (loadings.profitability >= threshold) traits.push('quality-tilted')
  if (loadings.size <= -threshold) traits.push('large-cap')
  else if (loadings.size >= threshold) traits.push('small-cap')
  if (loadings.value <= -threshold) traits.push('growth')
  else if (loadings.value >= threshold) traits.push('value')
  const momentum = Math.abs(loadings.momentum) >= threshold
    ? `${Math.abs(loadings.momentum) < threshold * 2 ? 'slight ' : ''}${loadings.momentum > 0 ? 'momentum' : 'anti-momentum'} exposure`
    : null
  const allocation = traits.length ? `${traits.join(' ')} allocation` : 'broad market allocation'
  return `Your portfolio behaves like a ${allocation}${momentum ? ` with ${momentum}` : ''}.`
}

/** Ordinary least squares on monthly excess returns against FF5 plus momentum. */
export function factorRegression(portfolioSeries, payload) {
  const returns = monthlyReturns(portfolioSeries)
  const factorRows = new Map((payload?.observations || []).map((row) => [row.month, row]))
  const observations = [...returns.entries()].map(([month, value]) => {
    const factors = factorRows.get(month)
    if (!factors || !FACTOR_KEYS.every((key) => finite(factors[key])) || !finite(factors.risk_free)) return null
    return { month, y: value - Number(factors.risk_free), x: [1, ...FACTOR_KEYS.map((key) => Number(factors[key]))] }
  }).filter(Boolean)
  if (observations.length < config.factor_minimum_monthly_observations) {
    return {
      available: false,
      observations: observations.length,
      requiredObservations: config.factor_minimum_monthly_observations,
      reason: `${observations.length} of ${config.factor_minimum_monthly_observations} monthly observations accumulated.`,
    }
  }
  const columns = FACTOR_KEYS.length + 1
  const xtx = Array.from({ length: columns }, (_, row) => Array.from({ length: columns }, (_, column) => (
    observations.reduce((sum, item) => sum + item.x[row] * item.x[column], 0)
  )))
  const inverse = invertMatrix(xtx)
  if (!inverse) return { available: false, observations: observations.length, reason: 'The factor inputs are collinear for this window.' }
  const xty = Array.from({ length: columns }, (_, column) => observations.reduce(
    (sum, item) => sum + item.x[column] * item.y, 0,
  ))
  const coefficients = multiplyMatrixVector(inverse, xty)
  const fitted = observations.map((item) => item.x.reduce((sum, value, index) => sum + value * coefficients[index], 0))
  const residuals = observations.map((item, index) => item.y - fitted[index])
  const residualSumSquares = residuals.reduce((sum, value) => sum + value ** 2, 0)
  const yMean = observations.reduce((sum, item) => sum + item.y, 0) / observations.length
  const totalSumSquares = observations.reduce((sum, item) => sum + (item.y - yMean) ** 2, 0)
  const residualVariance = residualSumSquares / (observations.length - columns)
  const standardErrors = inverse.map((row, index) => Math.sqrt(Math.max(0, residualVariance * row[index])))
  const loadings = Object.fromEntries(FACTOR_KEYS.map((key, index) => [key, coefficients[index + 1]]))
  const loadingStandardErrors = Object.fromEntries(FACTOR_KEYS.map((key, index) => [key, standardErrors[index + 1]]))
  const alphaMonthly = coefficients[0]
  const alphaStandardError = standardErrors[0]
  return {
    available: true,
    observations: observations.length,
    startMonth: observations[0].month,
    endMonth: observations.at(-1).month,
    loadings,
    standardErrors: loadingStandardErrors,
    alphaAnnualPct: alphaMonthly * config.factor_annualization_months * 100,
    alphaTStatistic: alphaStandardError > 0 ? alphaMonthly / alphaStandardError : null,
    rSquared: totalSumSquares > 0 ? 1 - residualSumSquares / totalSumSquares : null,
    summary: factorSummary(loadings),
  }
}

/** Theme exposure stays a separate weighted portfolio lens and never enters research score. */
export function aggregateThemeExposure(positions = [], themesByTicker = {}) {
  const total = positions.filter((row) => finite(row.currentValue) && Number(row.currentValue) > 0)
    .reduce((sum, row) => sum + Number(row.currentValue), 0)
  if (!total) return []
  const themes = new Map()
  positions.forEach((position) => {
    if (!finite(position.currentValue) || Number(position.currentValue) <= 0) return
    const weight = Number(position.currentValue) / total
    ;(themesByTicker[String(position.ticker || '').toUpperCase()] || []).forEach((theme) => {
      const key = theme.theme || theme.name
      const score = Number(theme.score ?? theme.exposure_score)
      if (!key || !finite(score)) return
      const current = themes.get(key) || { weightedScore: 0, coveredWeight: 0 }
      current.weightedScore += weight * score
      current.coveredWeight += weight
      themes.set(key, current)
    })
  })
  return [...themes.entries()].map(([theme, value]) => ({
    theme,
    exposureScore: value.coveredWeight ? value.weightedScore / value.coveredWeight : 0,
    portfolioCoveragePct: value.coveredWeight * 100,
  })).sort((left, right) => right.exposureScore - left.exposureScore)
}
