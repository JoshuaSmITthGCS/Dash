import { STATES } from '../../core/states.js'

/** The wall label — museum-convention provenance line, present with zero exceptions. */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, provenance, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE

  return (
    <div
      data-gallery-frame="true"
      data-breached={isBreached ? 'true' : undefined}
      data-capability-id={capabilityId}
      style={{ opacity: isUnavailable ? 0.5 : 1 - (1 - confidence.level) * 0.35 }}
    >
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '17px', fontStyle: isAccumulating ? 'italic' : 'normal' }}>
        {title}
      </div>
      <div style={{ fontSize: '17px', fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', color: isBreached ? 'var(--state-breach)' : 'var(--ink-primary)' }}>
        {isAccumulating && state.observations != null ? `${state.observations} of ${state.required ?? '—'} observed` : value ?? read ?? title}
      </div>
      {value != null && read && <div style={{ fontSize: '14px', fontStyle: 'italic', color: 'var(--ink-secondary)' }}>{read}</div>}
      {reference && <div data-gallery-plaque="true">{reference}</div>}
      <div data-gallery-plaque="true">
        {mediumLine ? `${mediumLine} · ` : ''}{provenance || 'source unrecorded'}
      </div>
      {reason && <div data-gallery-plaque="true">{reason}</div>}
      {action}
      {children}
    </div>
  )
}
