import { actionHeadline, actionStyle, positionImpact } from '../lib/recommendation'

const money = (value) => (value == null ? '–' : `$${value.toFixed(2)}`)

/** Compact action chip for tables and card headers. */
export function ActionPill({ recommendation }) {
  if (!recommendation) return <span className="mono text-faint">–</span>
  const style = actionStyle(recommendation.action)
  return (
    <span
      className="action-pill"
      style={{ color: style.color, borderColor: style.color, background: `color-mix(in srgb, ${style.color} 10%, transparent)` }}
      title={recommendation.summary || style.blurb}
    >
      {style.icon} {actionHeadline(recommendation)}
    </span>
  )
}

/**
 * The full explanation: what to do, how much of the position it applies to, and every
 * factor that had to agree before the guidance moved off Hold.
 */
export default function ActionGuidance({ recommendation, position, stopLoss }) {
  if (!recommendation) return null
  const style = actionStyle(recommendation.action)
  const impact = position ? positionImpact(recommendation, position) : null
  const fromStopLoss = recommendation.source === 'stop_loss'

  return (
    <div
      className="action-panel"
      style={{ borderColor: style.color, background: `color-mix(in srgb, ${style.color} 7%, transparent)` }}
    >
      <div className="action-panel-head">
        <h4 style={{ color: style.color }}>{style.icon} {actionHeadline(recommendation)}</h4>
        <span className="chip">
          {fromStopLoss
            ? 'Position stop-loss, not a thesis signal'
            : `${recommendation.agreementCount} of 3 factors flagged · ${recommendation.agreementStrength || 'moderate'} agreement`}
        </span>
      </div>

      <p className="action-summary-text">
        {recommendation.summary || style.blurb}
      </p>

      {impact && (
        <div className="action-impact">
          <span>On this position: <b>{impact.shares.toFixed(2)} shares</b></span>
          <span>≈ <b>${impact.proceeds.toLocaleString('en-US', { maximumFractionDigits: 0 })}</b></span>
          <span>leaving <b>{impact.remainingShares.toFixed(2)} shares</b></span>
        </div>
      )}

      {recommendation.reasons?.length > 0 && (
        <ul>
          {recommendation.reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}

      {stopLoss?.bindingPrice != null && (
        <div className="action-impact" aria-label="Stop-loss levels">
          <span>
            {stopLoss.rule === 'atr' ? 'ATR position rule' : stopLoss.rule === 'sigma' ? 'Volatility position rule' : 'Fixed fallback rule'}:
            {' '}<b>{money(stopLoss.bindingPrice)}</b>
          </span>
          {stopLoss.distancePct != null && (
            <span>{stopLoss.distancePct >= 0 ? '' : 'past it, '}<b>{Math.abs(stopLoss.distancePct).toFixed(1)}%</b> {stopLoss.distancePct >= 0 ? 'away' : ''}</span>
          )}
          <span>trim <b>{money(stopLoss.trimPrice)}</b>, exit <b>{money(stopLoss.exitPrice)}</b></span>
        </div>
      )}
      {stopLoss?.explanation && <p className="position-risk-explanation">{stopLoss.explanation}</p>}

      <small className="action-disclaimer-text">
        {fromStopLoss
          ? 'This guidance comes from a high-water-mark position rule, not the business thesis. The company\'s own fundamentals, market behaviour, and sentiment may still read Hold.'
          : 'Guidance never moves off Hold on price action alone, or on a single headline. Two of three independent factors – business fundamentals, market behaviour, and positioning/sentiment – have to agree first.'}
      </small>
      {fromStopLoss && recommendation.companyRecommendation && (
        <div className="company-thesis-row">
          <span>Company thesis</span>
          <b>{recommendation.companyRecommendation.action}</b>
          <small>{recommendation.companyRecommendation.summary || 'Independent of your entry price and stop rule.'}</small>
        </div>
      )}
    </div>
  )
}
