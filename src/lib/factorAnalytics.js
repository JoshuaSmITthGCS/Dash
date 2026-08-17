import modelSettings from '../../pipeline/config/settings.json' with { type: 'json' }

const config = modelSettings.portfolio_analytics
const FACTOR_KEYS = ['market_excess', 'size', 'value', 'profitability', 'investment', 'momentum']
const FACTOR_MODELS = [
  { id: 'capm', label: 'CAPM', keys: ['market_excess'] },
  { id: 'ff3', label: 'Fama–French 3-factor', keys: ['market_excess', 'size', 'value'] },
  { id: 'carhart4', label: 'Carhart 4-factor', keys: ['market_excess', 'size', 'value', 'momentum'] },
  { id: 'ff5', label: 'Fama–French 5-factor', keys: ['market_excess', 'size', 'value', 'profitability', 'investment'] },
  // Retained as the existing canonical read so no pre-refactor measurement disappears.
  { id: 'ff5_momentum', label: 'Fama–French 5-factor + momentum', keys: FACTOR_KEYS },
]

const finite = (value) => value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))

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

function multiplyMatrices(left, right) {
  return left.map((row) => right[0].map((_, column) => (
    row.reduce((sum, value, index) => sum + value * right[index][column], 0)
  )))
}

function transpose(matrix) {
  return matrix[0].map((_, column) => matrix.map((row) => row[column]))
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

function neweyWestCovariance(inverseXtx, observations, residuals, lag) {
  const columns = observations[0].x.length
  const meat = Array.from({ length: columns }, () => Array(columns).fill(0))
  const addOuter = (left, right, scale) => {
    for (let row = 0; row < columns; row += 1) {
      for (let column = 0; column < columns; column += 1) meat[row][column] += scale * left[row] * right[column]
    }
  }
  observations.forEach((item, index) => addOuter(item.x, item.x, residuals[index] ** 2))
  for (let distance = 1; distance <= lag; distance += 1) {
    const weight = 1 - distance / (lag + 1)
    for (let index = distance; index < observations.length; index += 1) {
      const scale = weight * residuals[index] * residuals[index - distance]
      addOuter(observations[index].x, observations[index - distance].x, scale)
      addOuter(observations[index - distance].x, observations[index].x, scale)
    }
  }
  const sandwich = multiplyMatrices(multiplyMatrices(inverseXtx, meat), transpose(inverseXtx))
  const correction = observations.length / Math.max(1, observations.length - columns)
  return sandwich.map((row) => row.map((value) => value * correction))
}

function regress(baseObservations, model) {
  const observations = baseObservations.map((item) => ({
    ...item,
    x: [1, ...model.keys.map((key) => item.factors[key])],
  }))
  const columns = model.keys.length + 1
  if (observations.length <= columns) return { id: model.id, label: model.label, available: false, reason: 'The sample has fewer observations than regression parameters.' }
  const xtx = Array.from({ length: columns }, (_, row) => Array.from({ length: columns }, (_, column) => (
    observations.reduce((sum, item) => sum + item.x[row] * item.x[column], 0)
  )))
  const inverse = invertMatrix(xtx)
  if (!inverse) return { id: model.id, label: model.label, available: false, observations: observations.length, reason: 'The factor inputs are collinear for this window.' }
  const xty = Array.from({ length: columns }, (_, column) => observations.reduce(
    (sum, item) => sum + item.x[column] * item.y, 0,
  ))
  const coefficients = multiplyMatrixVector(inverse, xty)
  const fitted = observations.map((item) => item.x.reduce((sum, value, index) => sum + value * coefficients[index], 0))
  const residuals = observations.map((item, index) => item.y - fitted[index])
  const residualSumSquares = residuals.reduce((sum, value) => sum + value ** 2, 0)
  const yMean = observations.reduce((sum, item) => sum + item.y, 0) / observations.length
  const totalSumSquares = observations.reduce((sum, item) => sum + (item.y - yMean) ** 2, 0)
  const hacLag = Math.max(1, Math.floor(4 * (observations.length / 100) ** (2 / 9)))
  const hacCovariance = neweyWestCovariance(inverse, observations, residuals, hacLag)
  const standardErrors = hacCovariance.map((row, index) => Math.sqrt(Math.max(0, row[index])))
  const loadings = Object.fromEntries(model.keys.map((key, index) => [key, coefficients[index + 1]]))
  const loadingStandardErrors = Object.fromEntries(model.keys.map((key, index) => [key, standardErrors[index + 1]]))
  const alphaMonthly = coefficients[0]
  const alphaStandardError = standardErrors[0]
  return {
    id: model.id,
    label: model.label,
    available: true,
    observations: observations.length,
    startMonth: observations[0].month,
    endMonth: observations.at(-1).month,
    loadings,
    standardErrors: loadingStandardErrors,
    alphaAnnualPct: alphaMonthly * config.factor_annualization_months * 100,
    alphaTStatistic: alphaStandardError > 0 ? alphaMonthly / alphaStandardError : null,
    rSquared: totalSumSquares > 0 ? 1 - residualSumSquares / totalSumSquares : null,
    residualVolatilityAnnualPct: Math.sqrt(residualSumSquares / Math.max(1, observations.length - columns)) * Math.sqrt(config.factor_annualization_months) * 100,
    unexplainedVariancePct: totalSumSquares > 0 ? residualSumSquares / totalSumSquares * 100 : null,
    hacLag,
    covariance: 'Newey–West HAC with Bartlett weights and finite-sample correction',
  }
}

/**
 * Escalating monthly CAPM/FF3/Carhart4/FF5 regressions with Newey–West HAC inference.
 * The committed Ken French artifact is monthly, so this does not pretend to be a daily
 * regression. The frequency and sample are returned explicitly.
 */
export function factorRegression(portfolioSeries, payload) {
  const returns = monthlyReturns(portfolioSeries)
  const factorRows = new Map((payload?.observations || []).map((row) => [row.month, row]))
  const observations = [...returns.entries()].map(([month, value]) => {
    const factors = factorRows.get(month)
    if (!factors || !FACTOR_KEYS.every((key) => finite(factors[key])) || !finite(factors.risk_free)) return null
    return {
      month,
      y: value - Number(factors.risk_free),
      factors: Object.fromEntries(FACTOR_KEYS.map((key) => [key, Number(factors[key])])),
    }
  }).filter(Boolean)
  if (observations.length < config.factor_minimum_monthly_observations) {
    return {
      available: false,
      observations: observations.length,
      requiredObservations: config.factor_minimum_monthly_observations,
      frequency: 'monthly',
      reason: `${observations.length} of ${config.factor_minimum_monthly_observations} monthly observations accumulated.`,
    }
  }
  const models = FACTOR_MODELS.map((model) => regress(observations, model))
  const full = models.at(-1)
  if (!full?.available) return { ...full, models, frequency: 'monthly' }
  return {
    ...full,
    frequency: 'monthly',
    models,
    summary: factorSummary(full.loadings),
    alphaInterpretation: (() => {
      const carhart = models.find((model) => model.id === 'carhart4')
      if (!carhart?.available || !finite(carhart.alphaTStatistic)) return 'Momentum-and-size-adjusted alpha is not estimable.'
      return carhart.alphaTStatistic > 3
        ? 'Alpha remains positive above the registered t > 3 hurdle after momentum and size.'
        : 'Alpha is not significant after momentum and size; this sample does not distinguish alpha from packaged factor exposure.'
    })(),
  }
}

// The pipeline publishes each per-ticker theme entry as
// `{theme_id, display_name, theme_exposure_score, opportunity_score, eligible}`
// (themes.build_theme_screen). Reading `theme`/`score` alone silently matched nothing, so
// every position resolved to no key and no score and the portfolio lens rendered its
// "unavailable" branch against a fully populated payload. The older spellings stay as
// fallbacks because snapshots predating the current shape are still loadable.
const themeEntryName = (entry) => entry.display_name || entry.theme_id || entry.theme || entry.name
const themeEntryScore = (entry) => Number(entry.theme_exposure_score ?? entry.exposure_score ?? entry.score)

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
      const key = themeEntryName(theme)
      const score = themeEntryScore(theme)
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
