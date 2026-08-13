/**
 * Deterministic metric classification. This module deliberately has no React dependency.
 * Assessment, confidence, and trend are independent fields: a favourable but immature
 * result is positive/low-confidence, never upgraded by its sign or hidden by its age.
 */

export const ASSESSMENTS = ['positive', 'neutral', 'negative', 'insufficient']
export const CONFIDENCE_LEVELS = ['high', 'moderate', 'low', 'none']
export const TRENDS = ['improving', 'stable', 'deteriorating', 'unknown']

export const UI_FAMILY_WEIGHTS = {
  standard: {
    return_efficiency: 0.30,
    statistical_confidence: 0.25,
    drawdown_severity: 0.25,
    drawdown_persistence: 0.10,
    tail_risk: 0.10,
  },
  comparison: {
    factor_alpha: 0.30,
    relative_return: 0.25,
    capture: 0.20,
    consistency: 0.15,
    recent_change: 0.10,
  },
  fast: {
    recent_excess: 0.30,
    signal_noise: 0.25,
    execution: 0.20,
    relative_risk: 0.15,
    portfolio_structure: 0.05,
    streak: 0.05,
  },
}

const finite = (value) => value !== null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value))
const clamp = (value, minimum = 0, maximum = 1) => Math.max(minimum, Math.min(maximum, value))

const RULES = {
  sharpe: { direction: 'high', positive: 0.5, negative: 0, reason: 'risk-adjusted return' },
  lo_adjusted_sharpe: { direction: 'high', positive: 0.5, negative: 0, reason: 'serial-correlation-adjusted return efficiency' },
  sortino: { direction: 'high', positive: 0.75, negative: 0, reason: 'downside-risk-adjusted return' },
  calmar: { direction: 'high', positive: 0.5, negative: 0, reason: 'return per unit of drawdown' },
  information_ratio: { direction: 'high', positive: 0.5, negative: 0, reason: 'active return per unit of tracking risk' },
  psr: { direction: 'high', positive: 0.95, negative: 0.5, reason: 'probability the true Sharpe exceeds the threshold' },
  dsr: { direction: 'high', positive: 0.95, negative: 0.5, reason: 'Sharpe confidence after registered trials' },
  sharpe_t_stat: { direction: 'absolute_positive', positive: 3, negative: 0, reason: 'Sharpe distance from zero' },
  factor_alpha_t: { direction: 'high', positive: 3, negative: 3, special: 'factor_alpha', reason: 'momentum-and-size-adjusted alpha evidence' },
  maximum_drawdown: { direction: 'low_abs', positive: 10, negative: 20, reason: 'peak-to-trough loss' },
  current_drawdown: { direction: 'low_abs', positive: 5, negative: 15, reason: 'current decline from the high-water mark' },
  expected_shortfall_95: { direction: 'low_abs', positive: 2, negative: 4, reason: 'average loss in the worst five percent of days' },
  var_95: { direction: 'low', positive: 1.5, negative: 3, reason: 'one-day tail-loss threshold' },
  ulcer_index: { direction: 'low', positive: 5, negative: 15, reason: 'depth and persistence of drawdowns' },
  pain_index: { direction: 'low', positive: 3, negative: 10, reason: 'average drawdown depth' },
  longest_underwater: { direction: 'low', positive: 60, negative: 365, reason: 'time spent below a prior high-water mark' },
  omega: { direction: 'high', positive: 1.2, negative: 1, reason: 'gains relative to losses' },
  tail_ratio: { direction: 'high', positive: 1.1, negative: 0.9, reason: 'right-tail return relative to left-tail loss' },
  batting_average: { direction: 'high', positive: 55, negative: 45, reason: 'share of months beating the benchmark' },
  relative_expectancy: { direction: 'high', positive: 0.05, negative: 0, reason: 'average benchmark-relative outcome per month' },
  capture_spread: { direction: 'high', positive: 10, negative: 0, reason: 'upside participation less downside participation' },
  acceleration: { direction: 'high', positive: 1, negative: -1, reason: 'change in beta-adjusted relative return' },
  effective_positions: { direction: 'high', positive: 8, negative: 5, reason: 'effective breadth after concentration' },
  pbo: { direction: 'low', positive: 0.5, negative: 0.5, reason: 'probability of backtest overfitting' },
  walk_forward_efficiency: { direction: 'high', positive: 0.5, negative: 0, reason: 'out-of-sample efficiency relative to in-sample performance' },
}

export function confidenceFor(observations, minimum = 1, frequency = 'daily') {
  if (!finite(observations) || Number(observations) < minimum) return 'none'
  const count = Number(observations)
  const high = frequency === 'monthly' ? 60 : frequency === 'point' ? Infinity : 500
  const moderate = frequency === 'monthly' ? 36 : frequency === 'point' ? Infinity : 250
  if (count >= high) return 'high'
  if (count >= moderate) return 'moderate'
  return 'low'
}

function genericAssessment(value, rule) {
  if (rule.direction === 'high') {
    if (value >= rule.positive) return { assessment: 'positive', strength: clamp((value - rule.positive) / (Math.abs(rule.positive) || 1) + 0.5) }
    if (value < rule.negative) return { assessment: 'negative', strength: clamp((rule.negative - value) / (Math.abs(rule.negative) || 1) + 0.5) }
    return { assessment: 'neutral', strength: 0.5 }
  }
  if (rule.direction === 'low') {
    if (value <= rule.positive) return { assessment: 'positive', strength: clamp((rule.positive - value) / (Math.abs(rule.positive) || 1) + 0.5) }
    if (value > rule.negative) return { assessment: 'negative', strength: clamp((value - rule.negative) / (Math.abs(rule.negative) || 1) + 0.5) }
    return { assessment: 'neutral', strength: 0.5 }
  }
  if (rule.direction === 'low_abs') return genericAssessment(Math.abs(value), { ...rule, direction: 'low' })
  if (rule.direction === 'absolute_positive') {
    if (Math.abs(value) >= rule.positive) return { assessment: value > 0 ? 'positive' : 'negative', strength: clamp(Math.abs(value) / (rule.positive * 2)) }
    return { assessment: value < 0 ? 'negative' : 'neutral', strength: clamp(Math.abs(value) / rule.positive) }
  }
  return { assessment: 'neutral', strength: 0 }
}

function assessmentReason(name, assessment, rule) {
  const label = assessment === 'positive' ? 'favourable' : assessment === 'negative' ? 'unfavourable' : 'descriptive or within its neutral band'
  return `${name} is ${label} for ${rule?.reason || 'this metric'} under the dashboard’s documented interpretation bands.`
}

export function classifyMetric(input) {
  const observations = input.observations ?? null
  const minimum = Number(input.minObservations ?? 1)
  const frequency = input.frequency || 'daily'
  if (input.insufficientReason) {
    return { assessment: 'insufficient', strength: 0, confidence: 'none', reason: `Insufficient — ${input.insufficientReason}`, insufficientReason: input.insufficientReason }
  }
  if (frequency !== 'point' && (!finite(observations) || Number(observations) < minimum)) {
    const have = finite(observations) ? Number(observations) : 0
    const reason = `requires ≥ ${minimum} ${frequency} observations, have ${have}`
    return { assessment: 'insufficient', strength: 0, confidence: 'none', reason: `Insufficient — ${reason}`, insufficientReason: reason }
  }
  if (!finite(input.value)) {
    const reason = input.missingInput || 'a measured value is unavailable'
    return { assessment: 'insufficient', strength: 0, confidence: 'none', reason: `Insufficient — ${reason}`, insufficientReason: reason }
  }
  if (input.descriptive) {
    return { assessment: input.constraintViolation ? 'negative' : 'neutral', strength: input.constraintViolation ? 1 : 0, confidence: frequency === 'point' ? 'high' : confidenceFor(observations, minimum, frequency), reason: input.constraintViolation ? `${input.name} violates the configured portfolio constraint.` : `${input.name} is descriptive; higher or lower is not inherently better.` }
  }
  if (input.id === 'tracking_risk') return classifyTrackingRisk(input)
  if (input.id.startsWith('signal_to_noise')) return classifySignalToNoise(input)
  if (input.id === 'capture_profile') return classifyCaptureProfile(input)
  const rule = input.id.endsWith('_alpha_t')
    ? { direction: 'high', positive: 3, negative: 3, special: 'factor_alpha', reason: 'momentum-and-size-adjusted alpha evidence' }
    : RULES[input.id] || input.rule
  if (!rule) return { assessment: 'neutral', strength: 0, confidence: confidenceFor(observations, minimum, frequency), reason: `${input.name} is descriptive; no directional rule is applied.` }
  let result
  if (rule.special === 'factor_alpha') {
    result = Number(input.value) > 3 && Number(input.alphaAnnualPct) > 0
      ? { assessment: 'positive', strength: clamp(Number(input.value) / 6) }
      : { assessment: 'negative', strength: clamp((3 - Number(input.value)) / 3 + 0.5) }
  } else result = genericAssessment(Number(input.value), rule)
  return { ...result, confidence: confidenceFor(observations, minimum, frequency), reason: assessmentReason(input.name, result.assessment, rule) }
}

export function classifySignalToNoise(input) {
  if (!finite(input.value)) return { assessment: 'insufficient', strength: 0, confidence: 'none', reason: 'Insufficient — excess return and noise floor are required.', insufficientReason: 'excess return and noise floor are required' }
  const ratio = Math.abs(Number(input.value))
  const direction = Number(input.excessReturn ?? 1) >= 0 ? 1 : -1
  if (ratio < 0.5) return { assessment: 'neutral', strength: ratio, confidence: confidenceFor(input.observations, input.minObservations || 2), reason: 'Mostly noise — below 0.5× the descriptive noise floor.' }
  if (ratio < 1) return { assessment: 'neutral', strength: ratio / 2, confidence: confidenceFor(input.observations, input.minObservations || 2), reason: 'Within normal variation — below 1.0× the descriptive noise floor.' }
  if (ratio < 1.5) return { assessment: 'neutral', strength: 0.7, confidence: confidenceFor(input.observations, input.minObservations || 2), reason: 'Possible signal, not decisive — 1.0–1.5× the descriptive noise floor.' }
  if (direction < 0) return { assessment: 'negative', strength: clamp(ratio / 2), confidence: confidenceFor(input.observations, input.minObservations || 2), reason: ratio >= 2 ? 'Strong recent negative deviation; this is a descriptive band, not formal significance.' : 'Meaningful recent negative deviation; this is a descriptive band, not formal significance.' }
  return { assessment: 'positive', strength: clamp(ratio / 2), confidence: confidenceFor(input.observations, input.minObservations || 2), reason: ratio >= 2 ? 'Strong recent positive deviation; this is a descriptive band, not formal significance.' : 'Meaningful recent positive deviation; this is a descriptive band, not formal significance.' }
}

export function classifyCaptureProfile(input) {
  if (![input.upCapture, input.downCapture].every(finite)) return { assessment: 'insufficient', strength: 0, confidence: 'none', reason: 'Insufficient — both up-capture and down-capture are required.', insufficientReason: 'both up-capture and down-capture are required' }
  const spread = Number(input.upCapture) - Number(input.downCapture)
  if (spread >= 10 && Number(input.downCapture) < 100) return { assessment: 'positive', strength: clamp(spread / 50), confidence: confidenceFor(input.observations, input.minObservations || 16), reason: `Favourable asymmetry — participates in ${Number(input.upCapture).toFixed(0)}% of benchmark upside and ${Number(input.downCapture).toFixed(0)}% of downside.` }
  if (spread < 0 || Number(input.downCapture) > 100) return { assessment: 'negative', strength: clamp(Math.abs(spread) / 50 + (Number(input.downCapture) > 100 ? 0.25 : 0)), confidence: confidenceFor(input.observations, input.minObservations || 16), reason: `Unfavourable asymmetry — participates in ${Number(input.upCapture).toFixed(0)}% of benchmark upside but ${Number(input.downCapture).toFixed(0)}% of downside.` }
  return { assessment: 'neutral', strength: 0.5, confidence: confidenceFor(input.observations, input.minObservations || 16), reason: 'Capture asymmetry is close to balanced.' }
}

export function classifyTrackingRisk(input) {
  if (![input.value, input.baseline].every(finite) || Number(input.baseline) <= 0) return { assessment: 'insufficient', strength: 0, confidence: 'none', reason: 'Insufficient — current and baseline tracking risk are required.', insufficientReason: 'current and baseline tracking risk are required' }
  const multiple = Number(input.value) / Number(input.baseline)
  if (multiple > 2) return { assessment: 'negative', strength: clamp((multiple - 2) / 2 + 0.5), confidence: confidenceFor(input.observations, input.minObservations || 20), reason: `Tracking risk is ${multiple.toFixed(1)}× its baseline, an extreme elevation.` }
  if (multiple > 1.25) return { assessment: 'neutral', strength: 0.75, confidence: confidenceFor(input.observations, input.minObservations || 20), reason: `Tracking risk is ${multiple.toFixed(1)}× its baseline; elevated enough to watch, not automatically bad.` }
  return { assessment: 'neutral', strength: 0.25, confidence: confidenceFor(input.observations, input.minObservations || 20), reason: 'Tracking risk is within its normal baseline band.' }
}

export function metric(input) {
  const classified = classifyMetric(input)
  return {
    id: input.id,
    name: input.name,
    category: input.category || 'Risk',
    family: input.family,
    value: finite(input.value) ? Number(input.value) : null,
    formattedValue: input.formattedValue || (finite(input.value) ? String(input.value) : 'Insufficient'),
    supportingValue: input.supportingValue,
    assessment: classified.assessment,
    strength: classified.strength,
    reason: classified.reason,
    confidence: classified.confidence,
    observations: finite(input.observations) ? Number(input.observations) : null,
    minObservations: Number(input.minObservations ?? 1),
    startDate: input.startDate || null,
    endDate: input.endDate || null,
    frequency: input.frequency || 'daily',
    benchmark: finite(input.benchmark) ? Number(input.benchmark) : undefined,
    trend: input.trend || 'unknown',
    trendDetail: input.trendDetail,
    tooltip: input.tooltip || { measures: input.name },
    priority: Number(input.priority ?? 50),
    insufficientReason: classified.insufficientReason,
    group: input.group,
    watch: input.watch,
  }
}

export function evidenceCounts(metrics = []) {
  const counts = { positive: 0, neutral: 0, negative: 0, insufficient: 0, total: metrics.length }
  metrics.forEach((row) => { if (ASSESSMENTS.includes(row.assessment)) counts[row.assessment] += 1 })
  return counts
}

function familyAssessment(rows) {
  const assessed = rows.filter((row) => row.assessment !== 'insufficient')
  if (!assessed.length) return { assessment: 'insufficient', strength: 1 }
  const signed = assessed.reduce((sum, row) => sum + (row.assessment === 'positive' ? 1 : row.assessment === 'negative' ? -1 : 0) * (row.strength || 0.5), 0) / assessed.length
  if (signed > 0.15) return { assessment: 'positive', strength: Math.abs(signed) }
  if (signed < -0.15) return { assessment: 'negative', strength: Math.abs(signed) }
  return { assessment: 'neutral', strength: 1 - Math.abs(signed) }
}

const READ_RANK = { Poor: 0, Weak: 1, Inconclusive: 2, Mixed: 3, Healthy: 4, Strong: 5 }

export function sectionAssessment(section, metrics = []) {
  const weights = UI_FAMILY_WEIGHTS[section] || {}
  const counts = evidenceCounts(metrics)
  const families = Object.keys(weights).map((family) => ({ family, weight: weights[family], ...familyAssessment(metrics.filter((row) => row.family === family)) }))
  const assessedFamilies = families.filter((row) => row.assessment !== 'insufficient')
  const denominator = assessedFamilies.reduce((sum, row) => sum + row.weight, 0)
  const share = (assessment) => denominator ? assessedFamilies.filter((row) => row.assessment === assessment).reduce((sum, row) => sum + row.weight, 0) / denominator : 0
  const positive = share('positive')
  const negative = share('negative')
  const insufficientWeight = families.filter((row) => row.assessment === 'insufficient').reduce((sum, row) => sum + row.weight, 0)
  let read
  if (!denominator || insufficientWeight >= 0.5) read = 'Inconclusive'
  else if (negative > 0.65) read = 'Poor'
  else if (negative > 0.5) read = 'Weak'
  else if (positive > 0.65 && negative < 0.2) read = 'Strong'
  else if (positive > 0.5) read = 'Healthy'
  else read = 'Mixed'
  const statistical = families.find((row) => row.family === 'statistical_confidence')
  if (statistical && ['negative', 'insufficient'].includes(statistical.assessment) && READ_RANK[read] > READ_RANK.Inconclusive) read = 'Inconclusive'
  const drivers = metrics.map((row) => ({ ...row, impact: (weights[row.family] || 0) * (row.strength || 0) }))
  const helping = drivers.filter((row) => row.assessment === 'positive').sort((left, right) => right.impact - left.impact)[0] || null
  const hurting = drivers.filter((row) => row.assessment === 'negative').sort((left, right) => right.impact - left.impact)[0] || null
  const watch = drivers.filter((row) => row.assessment === 'insufficient' || row.watch).sort((left, right) => right.priority - left.priority)[0] || null
  return {
    read,
    counts,
    families,
    weighted: { positive, negative, neutral: Math.max(0, 1 - positive - negative), insufficientWeight },
    helping,
    hurting,
    watch,
    narrative: sectionNarrative({ read, helping, hurting, watch }),
  }
}

export function sectionNarrative({ read, helping, hurting, watch }) {
  const lead = {
    Strong: 'Evidence is broadly favourable.',
    Healthy: 'Favourable evidence outweighs the concerns.',
    Mixed: 'Favourable and unfavourable evidence remain mixed.',
    Weak: 'Unfavourable evidence outweighs the support.',
    Poor: 'The assessed evidence is predominantly unfavourable.',
    Inconclusive: 'The available sample cannot support a firm read.',
  }[read] || 'The available evidence is inconclusive.'
  if (hurting) return `${lead} The main drag is ${hurting.name.toLowerCase()}${helping ? `; ${helping.name.toLowerCase()} is the strongest support` : ''}.`
  if (helping) return `${lead} The strongest support is ${helping.name.toLowerCase()}.`
  if (watch) return `${lead} Watch ${watch.name.toLowerCase()} as its required evidence accumulates.`
  return lead
}

export function combinedEvidence(sections = []) {
  const metrics = sections.flatMap((section) => section.metrics || [])
  const counts = evidenceCounts(metrics)
  const assessed = counts.positive + counts.neutral + counts.negative
  const positive = assessed ? counts.positive / assessed : 0
  const negative = assessed ? counts.negative / assessed : 0
  const read = counts.insufficient > metrics.length / 2 ? 'Inconclusive'
    : negative > 0.65 ? 'Poor'
      : negative > 0.5 ? 'Weak'
        : positive > 0.65 && negative < 0.2 ? 'Strong'
          : positive > 0.5 ? 'Healthy' : 'Mixed'
  const recent = sections.find((section) => section.id === 'fast')?.summary
  const longRun = sections.filter((section) => section.id !== 'fast').flatMap((section) => section.metrics || [])
  const longCounts = evidenceCounts(longRun)
  let narrative = `Overall evidence is ${read.toLowerCase()}.`
  if (longCounts.negative > longCounts.positive && recent?.counts?.positive > recent?.counts?.negative) {
    narrative += ' Long-run performance remains weak, although recent relative performance is improving.'
  } else if (counts.negative > counts.positive) narrative += ' Unfavourable long-run evidence is the dominant feature.'
  else if (counts.positive > counts.negative) narrative += ' Favourable readings lead, subject to the displayed confidence and sample gates.'
  else narrative += ' Positive and negative readings are balanced.'
  return { read, counts, narrative }
}

export function compareEvidencePeriods(before = [], since = []) {
  const beforeById = new Map(before.filter((row) => row.assessment !== 'insufficient').map((row) => [row.id, row]))
  const pairs = since.filter((row) => row.assessment !== 'insufficient' && beforeById.has(row.id) && beforeById.get(row.id).frequency === row.frequency)
  const beforeCompatible = pairs.map((row) => beforeById.get(row.id))
  const beforeCounts = evidenceCounts(beforeCompatible)
  const sinceCounts = evidenceCounts(pairs)
  return {
    before: beforeCounts,
    since: sinceCounts,
    positiveShift: sinceCounts.positive - beforeCounts.positive,
    negativeShift: sinceCounts.negative - beforeCounts.negative,
    compared: pairs.length,
    omitted: Math.max(before.length, since.length) - pairs.length,
    label: 'Observed improvement since algorithm launch.',
  }
}
