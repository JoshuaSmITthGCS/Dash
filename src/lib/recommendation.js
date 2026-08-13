import { getSellWatchRecommendation } from './sellWatchLogic'
import { confidenceBand, confidencePercent, gateReason } from './confidenceGate'

/**
 * One source of truth for hold / watch / trim / sell guidance across the app.
 *
 * The pipeline already applies the two-factor rule when it builds advisor.json, so its
 * verdict wins. Rows published before that field existed fall back to the browser-side
 * engine, which applies the identical rule to whatever the row does carry.
 */

export const ACTION_STYLES = {
  INSUFFICIENT_DATA: {
    label: 'Insufficient data', color: 'var(--text-faint)', icon: '○',
    blurb: 'Not enough resolved evidence to make any action call',
  },
  HOLD: { label: 'Hold', color: 'var(--pos)', icon: '●', blurb: 'Keep the position as it stands' },
  WATCH: { label: 'Watch', color: 'var(--warn)', icon: '◐', blurb: 'One factor slipped – monitor, do not act yet' },
  TRIM: { label: 'Trim', color: 'var(--warn)', icon: '◑', blurb: 'Reduce exposure while the thesis is tested' },
  SELL: { label: 'Sell', color: 'var(--neg)', icon: '●', blurb: 'Exit and redeploy the capital' },
}

const DEFAULT_TRIM = { HOLD: 0, WATCH: 0, TRIM: 33, SELL: 100 }

// SELL means "exit, this is not coming back" -- reserve it for when the consensus price
// target itself sits at or below today's price (the only signal on hand that speaks to where
// the stock is expected to go, not just how it got here). Deteriorating fundamentals, broken
// technicals, or bad sentiment alone only justify trimming exposure while that's tested;
// without evidence the price has a lower expected ceiling than where it already trades,
// a published or client-derived SELL is downgraded to TRIM instead.
function downgradeUnjustifiedSell(recommendation, stock) {
  if (recommendation?.action !== 'SELL') return recommendation
  const upside = Number(stock?.analyst_target_upside)
  if (Number.isFinite(upside) && upside <= 0) return recommendation
  return {
    ...recommendation,
    action: 'TRIM',
    suggestedTrimPct: DEFAULT_TRIM.TRIM,
    summary: `${recommendation.summary} Downgraded from Sell: ${Number.isFinite(upside)
      ? `the consensus price target still implies ${upside >= 0 ? '+' : ''}${upside.toFixed(0)}% upside`
      : 'no analyst price target is on file'}, so there is no evidence the price won’t recover.`,
  }
}

export function getRecommendation(stock) {
  if (!stock) return null
  const published = stock.recommendation
  const structural = stock.analysis_v2?.structural

  // The row-level confidence gate runs before anything else and applies to every row, not
  // only rows that happen to carry an analysis_v2 block. Without it a lightweight universe
  // row - which publishes no confidence at all - inherited whatever action the pipeline
  // last wrote and displayed it beside "Data coverage 0%".
  const band = confidenceBand(stock.data_coverage)
  if (!stock.is_etf && (band === 'insufficient' || band === 'watch')) {
    const pct = confidencePercent(stock.data_coverage)
    return {
      action: band === 'insufficient' ? 'INSUFFICIENT_DATA' : 'WATCH',
      confidence: band === 'insufficient' ? 'none' : 'low',
      summary: gateReason(stock.data_coverage),
      reasons: pct === null
        ? ['This row was scored on the lighter universe data set, which publishes no confidence measure.']
        : [`Data coverage ${Math.round(pct)}%.`],
      agreementCount: 0,
      suggestedTrimPct: 0,
      source: 'confidence_gate',
    }
  }

  if (structural && structural.evidence_weight_resolved < 0.4) {
    return {
      action: 'WATCH',
      confidence: 'low',
      summary: `Insufficient evidence: ${Math.round(structural.coverage * 100)}% data coverage, ${Math.round(structural.evidence_weight_resolved * 100)}% of evidence weight resolved.`,
      reasons: [...(structural.missing_metrics || []).slice(0, 3).map((metric) => `Missing ${metric.replace(/_/g, ' ')}`)],
      agreementCount: 0,
      suggestedTrimPct: 0,
      source: 'canonical_confidence_gate',
    }
  }
  if (structural && structural.evidence_weight_resolved < 0.6 && ['TRIM', 'SELL'].includes(published?.action)) {
    return {
      action: 'WATCH', confidence: 'limited',
      summary: 'Review only: evidence confidence is below the threshold for prescriptive company action.',
      reasons: published.reasons || [], agreementCount: published.agreement_count ?? 0,
      suggestedTrimPct: 0, source: 'canonical_confidence_gate',
    }
  }
  if (published?.action) {
    return downgradeUnjustifiedSell({
      ...published,
      suggestedTrimPct: published.suggested_trim_pct ?? DEFAULT_TRIM[published.action] ?? 0,
      agreementCount: published.agreement_count ?? 0,
      reasons: published.reasons || [],
      source: 'pipeline',
    }, stock)
  }

  const derived = getSellWatchRecommendation(stock)
  return downgradeUnjustifiedSell({
    action: derived.action,
    confidence: derived.confidence,
    summary: derived.reason,
    reasons: derived.topReasons || [],
    agreementCount: derived.agreementCount || 0,
    suggestedTrimPct: DEFAULT_TRIM[derived.action] ?? 0,
    factors: derived.factors,
    source: 'client',
  }, stock)
}

/** Action plus the share of the position it applies to, e.g. "TRIM 33%". */
export function actionHeadline(recommendation) {
  if (!recommendation) return '–'
  const { action, suggestedTrimPct } = recommendation
  // Underscores are an internal token shape, not something to put in front of a reader.
  const label = String(action || '').replace(/_/g, ' ')
  return suggestedTrimPct > 0 ? `${label} ${suggestedTrimPct}%` : label
}

/** What acting on the guidance would mean for a specific holding, in shares and dollars. */
export function positionImpact(recommendation, { shares, price }) {
  const pct = recommendation?.suggestedTrimPct || 0
  if (!pct || !shares || !price) return null
  const sharesAffected = (shares * pct) / 100
  return {
    pct,
    shares: sharesAffected,
    proceeds: sharesAffected * price,
    remainingShares: shares - sharesAffected,
  }
}

export function actionStyle(action) {
  return ACTION_STYLES[action] || ACTION_STYLES.HOLD
}
