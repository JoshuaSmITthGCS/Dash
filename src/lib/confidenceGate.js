/**
 * One rule for whether the evidence behind a row is strong enough to carry an action label.
 *
 * The failure this exists to stop is a row reading "Data coverage 0%" and "BUY NOW" at the
 * same time. Those two statements cannot both be true: an action label is a claim about what
 * to do, and it has to be backed by evidence the platform actually resolved.
 *
 * The quantity gated on is `data_coverage` -- the share of the evidence this model intended
 * to use that actually resolved. It is not a reliability score and not a probability that the
 * stock rises, which is exactly why it was renamed out of "confidence": a completeness ratio
 * was being read as trustworthiness, here and in position sizing. A low band withholds the
 * recommendation rather than reversing it - "we cannot say" is a different verdict from
 * "sell". See research/audit/CURRENT_MODEL_AUDIT.md section 4.
 *
 * Bands, on the 0-100 scale the UI displays:
 *
 *   below 40   insufficient   no actionable label at all
 *   40 - 59    watch          monitoring language only, never buy/trim/sell
 *   60 - 74    moderate       actionable, but not presented as conviction
 *   75+        high           full conviction labels allowed
 *
 * A row with no coverage measurement at all (the lightweight universe projection publishes
 * none) is `insufficient`, not zero: absent evidence and measured-and-terrible are different
 * claims, and neither one earns a Buy Now.
 */

export const CONFIDENCE_BANDS = {
  insufficient: { min: 0, label: 'Insufficient data', actionable: false, conviction: false },
  watch: { min: 40, label: 'Limited evidence', actionable: false, conviction: false },
  moderate: { min: 60, label: 'Moderate data coverage', actionable: true, conviction: false },
  high: { min: 75, label: 'High data coverage', actionable: true, conviction: true },
}

const ORDER = ['high', 'moderate', 'watch', 'insufficient']

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/** Data coverage as a 0-100 number, accepting either the 0-1 stored form or an already-scaled one. */
export function confidencePercent(confidence) {
  if (!finite(confidence)) return null
  return confidence <= 1 ? confidence * 100 : confidence
}

/** Band name for a confidence value, or 'insufficient' when there is no measurement. */
export function confidenceBand(confidence) {
  const pct = confidencePercent(confidence)
  if (pct === null) return 'insufficient'
  return ORDER.find((name) => pct >= CONFIDENCE_BANDS[name].min) || 'insufficient'
}

export function isActionable(confidence) {
  return CONFIDENCE_BANDS[confidenceBand(confidence)].actionable
}

export function allowsConviction(confidence) {
  return CONFIDENCE_BANDS[confidenceBand(confidence)].conviction
}

/**
 * Why an action was withheld, in the row's own numbers, so the UI never has to say
 * "unavailable" without a reason.
 */
export function gateReason(confidence) {
  const pct = confidencePercent(confidence)
  if (pct === null) {
    return 'No data-coverage measurement was published for this row, so no action call is made.'
  }
  const band = confidenceBand(confidence)
  if (band === 'insufficient') {
    return `Data coverage is ${Math.round(pct)}%, below the 40% floor for any action call.`
  }
  if (band === 'watch') {
    return `Data coverage is ${Math.round(pct)}% – enough to monitor, not enough to act on.`
  }
  return null
}

/**
 * Shrink a raw 0-100 model score toward neutral by how much the evidence behind it is worth.
 *
 * `50 + confidence x (raw - 50)`: a 92 backed by one stray headline lands near 63, while a 92
 * backed by resolved inputs stays near 88. Without this a single thin observation outranks a
 * fully evidenced one, which is exactly how a screen ends up leading with its worst-supported
 * row.
 */
export function shrinkToConfidence(rawScore, confidence) {
  if (!finite(rawScore)) return null
  const pct = confidencePercent(confidence)
  if (pct === null) return 50
  const weight = Math.max(0, Math.min(1, pct / 100))
  return 50 + weight * (rawScore - 50)
}
