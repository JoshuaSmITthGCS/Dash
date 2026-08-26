import { STATES } from '../../core/states.js'

function statusGlyph(state) {
  if (state.state === STATES.BREACHED) return '✖'
  if (state.state === STATES.ESTABLISHED) return '●'
  if (state.state === STATES.ACCUMULATING) return '◐'
  return '○'
}

/** One dense row: label (mono, like every other cell), value, fixed-width status column. */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, value, read, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const statusText = state.observations != null && state.required != null
    ? `${state.observations}/${state.required}`
    : state.state === STATES.UNAVAILABLE ? '—' : 'ok'

  return (
    <div data-ticker-row="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId}>
      <span style={{ flex: '0 0 40%', fontSize: '16px', fontVariantNumeric: 'normal', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
      <span style={{ flex: '1 1 auto', fontSize: '16px', opacity: 1 - confidence.level * 0.4, textAlign: 'right', color: isBreached ? 'var(--state-breach)' : 'var(--ink-primary)' }}>
        {state.observations != null ? `${state.observations}/${state.required ?? '—'}` : value ?? read ?? '–'}
      </span>
      <span style={{ flex: '0 0 72px', fontSize: '16px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }} data-testid="status-column">
        {statusGlyph(state)} {statusText}
      </span>
      {reason && <span style={{ display: 'block', width: '100%', fontSize: '11px', fontVariantNumeric: 'normal', color: 'var(--ink-faint)' }}>{reason}</span>}
      {action}
      {children}
    </div>
  )
}
