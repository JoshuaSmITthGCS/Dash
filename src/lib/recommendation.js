import { getSellWatchRecommendation } from './sellWatchLogic'

/**
 * One source of truth for hold / watch / trim / sell guidance across the app.
 *
 * The pipeline already applies the two-factor rule when it builds advisor.json, so its
 * verdict wins. Rows published before that field existed fall back to the browser-side
 * engine, which applies the identical rule to whatever the row does carry.
 */

export const ACTION_STYLES = {
  HOLD: { label: 'Hold', color: 'var(--pos)', icon: '●', blurb: 'Keep the position as it stands' },
  WATCH: { label: 'Watch', color: 'var(--warn)', icon: '◐', blurb: 'One factor slipped — monitor, do not act yet' },
  TRIM: { label: 'Trim', color: 'var(--warn)', icon: '◑', blurb: 'Reduce exposure while the thesis is tested' },
  SELL: { label: 'Sell', color: 'var(--neg)', icon: '●', blurb: 'Exit and redeploy the capital' },
}

const DEFAULT_TRIM = { HOLD: 0, WATCH: 0, TRIM: 33, SELL: 100 }

export function getRecommendation(stock) {
  if (!stock) return null
  const published = stock.recommendation
  const structural = stock.analysis_v2?.structural
  if (structural && structural.confidence < 0.4) {
    return {
      action: 'WATCH',
      confidence: 'low',
      summary: `Insufficient evidence: ${Math.round(structural.coverage * 100)}% coverage and ${Math.round(structural.confidence * 100)}% confidence.`,
      reasons: [...(structural.missing_metrics || []).slice(0, 3).map((metric) => `Missing ${metric.replace(/_/g, ' ')}`)],
      agreementCount: 0,
      suggestedTrimPct: 0,
      source: 'canonical_confidence_gate',
    }
  }
  if (structural && structural.confidence < 0.6 && ['TRIM', 'SELL'].includes(published?.action)) {
    return {
      action: 'WATCH', confidence: 'limited',
      summary: 'Review only: evidence confidence is below the threshold for prescriptive company action.',
      reasons: published.reasons || [], agreementCount: published.agreement_count ?? 0,
      suggestedTrimPct: 0, source: 'canonical_confidence_gate',
    }
  }
  if (published?.action) {
    return {
      ...published,
      suggestedTrimPct: published.suggested_trim_pct ?? DEFAULT_TRIM[published.action] ?? 0,
      agreementCount: published.agreement_count ?? 0,
      reasons: published.reasons || [],
      source: 'pipeline',
    }
  }

  const derived = getSellWatchRecommendation(stock)
  return {
    action: derived.action,
    confidence: derived.confidence,
    summary: derived.reason,
    reasons: derived.topReasons || [],
    agreementCount: derived.agreementCount || 0,
    suggestedTrimPct: DEFAULT_TRIM[derived.action] ?? 0,
    factors: derived.factors,
    source: 'client',
  }
}

/** Action plus the share of the position it applies to, e.g. "TRIM 33%". */
export function actionHeadline(recommendation) {
  if (!recommendation) return '—'
  const { action, suggestedTrimPct } = recommendation
  return suggestedTrimPct > 0 ? `${action} ${suggestedTrimPct}%` : action
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
