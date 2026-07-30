import { actionHeadline, actionStyle, positionImpact } from '../lib/recommendation'

/** Compact action chip for tables and card headers. */
export function ActionPill({ recommendation }) {
  if (!recommendation) return <span className="mono" style={{ color: 'var(--text-faint)' }}>—</span>
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
export default function ActionGuidance({ recommendation, position }) {
  if (!recommendation) return null
  const style = actionStyle(recommendation.action)
  const impact = position ? positionImpact(recommendation, position) : null

  return (
    <div
      className="action-panel"
      style={{ borderColor: style.color, background: `color-mix(in srgb, ${style.color} 7%, transparent)` }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h4 style={{ color: style.color }}>{style.icon} {actionHeadline(recommendation)}</h4>
        <span className="chip">
          {recommendation.agreementCount} of 3 factors flagged · {recommendation.confidence || 'moderate'} confidence
        </span>
      </div>

      <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>
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

      <small style={{ color: 'var(--text-faint)', fontSize: 11 }}>
        Guidance never moves off Hold on price action alone, or on a single headline. Two of
        three independent factors — business fundamentals, market behaviour, and
        positioning/sentiment — have to agree first.
      </small>
    </div>
  )
}
