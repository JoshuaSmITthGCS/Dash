import { STATES } from '../../core/states.js'
import { seededRange } from '../../core/seed.js'

const MAX_OFFSET_PX = 1.5

export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, read, reference, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE

  // Registration offset — Poster's confidence channel. Deterministic from the capabilityId so
  // screenshots never churn; capped at MAX_OFFSET_PX; NEVER applied to the numeral/text layer
  // itself, only to a duplicate decorative ink layer behind it.
  const offset = (1 - confidence.level) * MAX_OFFSET_PX
  const angle = seededRange(capabilityId || title, 0, 360)
  const dx = offset * Math.cos((angle * Math.PI) / 180)
  const dy = offset * Math.sin((angle * Math.PI) / 180)

  return (
    <div data-poster-panel="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId} style={{ opacity: isUnavailable ? 0.5 : 1, position: 'relative' }}>
      <span
        aria-hidden="true"
        data-testid="registration-ghost"
        style={{ position: 'absolute', inset: 0, color: 'var(--ink-spot-2)', opacity: 0.35, transform: `translate(${dx}px, ${dy}px)`, pointerEvents: 'none' }}
      />
      <header style={{ fontSize: '11px', letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--ink-secondary)' }}>
        {title}{mediumLine ? ` · ${mediumLine}` : ''}
      </header>
      <div style={{ fontSize: '20px', fontVariantNumeric: 'tabular-nums', color: isBreached ? 'var(--ink-spot-1)' : 'var(--ink-black)' }}>
        {isAccumulating && state.observations != null ? `${state.observations} / ${state.required ?? '—'}` : read || title}
      </div>
      {reference && <div style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>{reference}</div>}
      {reason && <div style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>{reason}</div>}
      {action}
      {children}
    </div>
  )
}
