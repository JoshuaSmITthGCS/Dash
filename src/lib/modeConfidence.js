/**
 * Confidence, per mode, from the inputs each mode actually reads.
 *
 * One global "Data confidence" number cannot describe a row honestly. A company can have two
 * flawless years of daily price and volume history and no resolved accounting statements at
 * all - which makes it a perfectly measurable momentum candidate and an unmeasurable
 * long-term one. Collapsing that into a single 42% understates the momentum reading and
 * overstates the fundamentals one at the same time.
 *
 * So every mode declares the inputs it depends on and how much each matters. Confidence is
 * the share of that mode's declared weight that actually resolved on this row, adjusted for
 * how fresh the evidence is where freshness is part of the claim (the catalyst mode's whole
 * proposition is that something happened *recently*; a fully decayed event is weak evidence
 * even though the field is populated).
 *
 * Confidence here is data completeness and reliability - never a probability that the stock
 * rises. It is used two ways: to gate action labels (src/lib/confidenceGate.js) and to shrink
 * each mode score toward neutral before ranking, so a 92 resting on one stray headline cannot
 * outrank an 80 backed by resolved inputs.
 */

const finite = (value) => typeof value === 'number' && Number.isFinite(value)

const has = (value) => (finite(value) ? 1 : 0)

/** Freshness credit for evidence whose value is inseparable from its age. */
function freshness(ageTradingDays, halfLife) {
  if (!finite(ageTradingDays) || !finite(halfLife) || halfLife <= 0) return 0
  return 2 ** (-Math.max(0, ageTradingDays) / halfLife)
}

const technical = (row) => row.technical_detail || {}
const evidence = (row) => row.evidence_summary || row.evidence || {}
const estimates = (row) => row.estimate_detail || {}

/**
 * Each entry is a list of [label, weight, resolve] where `resolve` returns 0..1 for how well
 * that input landed on this row. Weights are relative and get renormalized, so adding an
 * input later cannot silently deflate every existing score.
 */
export const MODE_INPUTS = {
  research: [
    ['fundamental coverage', 0.45, (row) => row.fundamental_detail?.coverage ?? has(row.components?.fundamentals)],
    ['valuation percentile', 0.15, (row) => has(row.sector_valuation_percentile)],
    ['price history', 0.2, (row) => has(technical(row).return_252d) * 0.5 + has(technical(row).return_20d) * 0.5],
    ['analyst coverage', 0.1, (row) => Math.min(1, (row.analyst_count || 0) / 5)],
    ['statement depth', 0.1, (row) => has(row.free_cash_flow) * 0.5 + has(row.return_on_equity) * 0.5],
  ],
  fundamentals: [
    ['fundamental coverage', 0.7, (row) => row.fundamental_detail?.coverage ?? has(row.components?.fundamentals)],
    ['statement depth', 0.3, (row) => (
      has(row.operating_margin) * 0.4 + has(row.free_cash_flow) * 0.3 + has(row.return_on_equity) * 0.3
    )],
  ],
  valuation: [
    ['sector percentile', 0.6, (row) => has(row.sector_valuation_percentile)],
    ['peer sample', 0.4, (row) => Math.min(1, (row.valuation_percentile?.peer_count_with_valid_data || 0) / 20)],
  ],
  // Momentum and reversal are price-and-volume questions. A row with no accounting data at
  // all can still be a fully measurable momentum candidate, which is exactly the case a
  // single global confidence number gets wrong.
  momentum: [
    ['long-horizon return', 0.35, (row) => has(technical(row).momentum_12_1) || has(technical(row).return_252d)],
    ['medium-horizon return', 0.3, (row) => has(technical(row).return_60d) * 0.5 + has(technical(row).return_20d) * 0.5],
    ['relative strength', 0.2, (row) => has(technical(row).relative_strength_20d)],
    ['volume confirmation', 0.15, (row) => has(technical(row).volume_confirmation) || has(technical(row).volume_ratio_60d)],
  ],
  reversal: [
    ['drawdown depth', 0.3, (row) => has(technical(row).drawdown_60d)],
    ['recent returns', 0.25, (row) => has(technical(row).return_5d) * 0.5 + has(technical(row).return_20d) * 0.5],
    ['fundamental shield', 0.25, (row) => has(row.components?.fundamentals)],
    ['thesis-break evidence', 0.2, (row) => (evidence(row).event_count ? 1 : 0)],
  ],
  // Freshness is load-bearing here rather than decorative: "a catalyst arrived" is a claim
  // about recency, so a populated-but-fully-decayed event is weak evidence, not strong.
  catalyst: [
    ['news events', 0.4, (row) => {
      const detail = evidence(row)
      if (!detail.event_count) return 0
      return Math.max(0.25, freshness(detail.dominant_age_trading_days, 5))
    }],
    ['insider activity', 0.35, (row) => {
      const detail = evidence(row)
      if (!finite(detail.insider_score)) return row.insider_activity?.available ? 0.5 : 0
      return Math.max(0.3, freshness(detail.insider_freshest_age_trading_days, 30))
    }],
    ['expectation change', 0.25, (row) => Math.min(1, (evidence(row).expectation_inputs_resolved || 0) / 3)],
  ],
  analystConviction: [
    ['revision history', 0.45, (row) => (
      has(estimates(row).revision_breadth_30d) * 0.5 + has(estimates(row).eps_revision_30d_pct) * 0.5
    )],
    ['rating changes', 0.25, (row) => has(estimates(row).net_upgrades_90d)],
    ['analyst breadth', 0.2, (row) => Math.min(1, (row.analyst_count || 0) / 10)],
    ['consensus target', 0.1, (row) => has(row.analyst_target_upside)],
  ],
  valueTurnaround: [
    ['valuation percentile', 0.3, (row) => has(row.sector_valuation_percentile)],
    ['margin trend', 0.25, (row) => has(row.operating_margin_trend)],
    ['cash flow', 0.2, (row) => has(row.free_cash_flow_yield) || has(row.free_cash_flow)],
    ['fundamental coverage', 0.15, (row) => row.fundamental_detail?.coverage ?? has(row.components?.fundamentals)],
    ['recent price', 0.1, (row) => has(technical(row).return_20d)],
  ],
  tailwind: [
    ['theme exposure', 0.5, (row) => ((row.theme_exposure || []).length ? 1 : 0)],
    ['valuation percentile', 0.25, (row) => has(row.sector_valuation_percentile)],
    ['expectation change', 0.15, (row) => Math.min(1, (evidence(row).expectation_inputs_resolved || 0) / 2)],
    ['fundamental coverage', 0.1, (row) => row.fundamental_detail?.coverage ?? has(row.components?.fundamentals)],
  ],
}

/**
 * Confidence for one mode on one row, 0..1, with the per-input breakdown that produced it.
 * The breakdown is the point: a low number that cannot be explained is just as opaque as no
 * number at all.
 */
export function modeConfidence(row, mode) {
  const inputs = MODE_INPUTS[mode]
  if (!inputs || !row) return null
  let resolvedWeight = 0
  let totalWeight = 0
  const detail = []
  for (const [label, weight, resolve] of inputs) {
    let resolved
    try {
      resolved = Math.max(0, Math.min(1, Number(resolve(row)) || 0))
    } catch {
      // A reader that trips over an unexpected row shape means the input did not resolve,
      // which is exactly what a zero says here.
      resolved = 0
    }
    totalWeight += weight
    resolvedWeight += weight * resolved
    detail.push({ label, weight, resolved: Number(resolved.toFixed(3)) })
  }
  const confidence = totalWeight ? resolvedWeight / totalWeight : 0
  return {
    mode,
    confidence: Number(confidence.toFixed(3)),
    percent: Math.round(confidence * 100),
    inputs: detail,
    // Ordered worst-first: what to fix, or what to say when someone asks why it is low.
    weakest: detail.slice().sort((a, b) => a.resolved - b.resolved).filter((item) => item.resolved < 1),
  }
}

/** Every mode's confidence for one row, for the per-company breakdown panel. */
export function allModeConfidence(row) {
  return Object.fromEntries(Object.keys(MODE_INPUTS).map((mode) => [mode, modeConfidence(row, mode)]))
}
