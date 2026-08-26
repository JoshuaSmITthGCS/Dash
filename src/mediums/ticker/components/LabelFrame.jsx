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
      {/* Confidence channel: transparency (DESIGN.md §4) — low confidence fades, high confidence
          is solid, matching every other medium's stated confidence direction. Floored at 0.85
          (not the full 0.6-1.0 range) because a11y.spec.mjs's WCAG contrast check found the
          breach-red state at lower opacity dropping well under the 4.5:1 text floor against this
          medium's near-black background; the value must stay legible at any confidence level. */}
      <span style={{ flex: '1 1 auto', minWidth: 0, fontSize: '16px', opacity: 0.85 + confidence.level * 0.15, textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: isBreached ? 'var(--state-breach)' : 'var(--ink-primary)' }}>
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
