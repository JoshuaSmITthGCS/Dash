import { STATES } from '../../core/states.js'

function confidenceWord(level) {
  if (level >= 0.7) return 'high'
  if (level >= 0.4) return 'moderate'
  return 'low'
}

/**
 * Headline above every chart, generated from `parts.headline` (core/headline.js) — never
 * freehand. Breached metrics get a standfirst flag line above the headline. Confidence renders
 * as a bylined note, a separate line/channel from the headline's own declarative/interrogative
 * grammar.
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, read, reference, state, confidence, reason, headline, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isUnavailable = state.state === STATES.UNAVAILABLE

  if (isUnavailable) {
    return (
      <div data-column-rule="true" data-capability-id={capabilityId}>
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--ink-faint)', fontStyle: 'italic' }}>
          {headline?.headline || `Not yet reported — ${reason || 'no data published.'}`}
        </p>
      </div>
    )
  }

  return (
    <div data-column-rule="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId}>
      {isBreached && <p data-standfirst="true">{headline?.standfirst}</p>}
      <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '18px', margin: '0 0 4px' }}>{headline?.headline || title}</h3>
      {read && <p style={{ fontSize: '13px', color: 'var(--ink-secondary)', margin: '0 0 4px' }}>{read}</p>}
      <div style={{ fontSize: '20px', fontVariantNumeric: 'tabular-nums', fontFamily: 'var(--font-mono)', color: isBreached ? 'var(--accent-standfirst)' : 'var(--ink-primary)' }}>
        {title}
      </div>
      {reference && <p style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>{reference}</p>}
      <p style={{ fontSize: '11px', color: 'var(--ink-faint)', fontStyle: 'italic' }}>
        Confidence: {confidenceWord(confidence.level)}, per {confidence.basis[0]}.
      </p>
      {action}
      {children}
    </div>
  )
}
