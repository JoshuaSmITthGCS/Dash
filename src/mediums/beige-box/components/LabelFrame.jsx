import { STATES } from '../../core/states.js'
import { ditherBackground } from './dither.js'

/**
 * A bevelled metric row. Confidence renders as 1-bit dither density on a decorative backing
 * layer behind the value — never on the numeral itself (the standing numerals-stay-clean rule).
 * Accumulating uses a real native `<progress>` bound to `state.observations`/`state.required`.
 * Breached renders as an alert-box marker: a colored border plus a title-bar-style icon, never
 * hue alone.
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, read, reference, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE

  if (isUnavailable) {
    return (
      <div data-beige-bevel="true" data-beige-disabled="true" data-capability-id={capabilityId} style={{ padding: '8px 10px' }}>
        <span style={{ fontSize: '13px' }}>{title}</span>
        <div style={{ fontSize: '11px' }}>{reason}</div>
      </div>
    )
  }

  return (
    <div
      data-beige-bevel="true"
      data-breached={isBreached ? 'true' : undefined}
      data-capability-id={capabilityId}
      style={{ borderColor: isBreached ? 'var(--state-breach)' : undefined, padding: '8px 10px', position: 'relative' }}
    >
      <span aria-hidden="true" data-testid="dither-layer" style={{ position: 'absolute', inset: 0, opacity: 0.12, color: 'var(--ink-faint)', pointerEvents: 'none', ...ditherBackground(confidence.level) }} />
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '8px', position: 'relative' }}>
        <span style={{ fontSize: '12px', color: 'var(--ink-secondary)' }}>{title}{mediumLine ? ` · ${mediumLine}` : ''}</span>
        {isBreached && <span aria-hidden="true">⚠</span>}
      </div>
      {isAccumulating && state.observations != null ? (
        <div style={{ position: 'relative' }}>
          <progress value={state.observations} max={state.required ?? 1} style={{ width: '100%', height: '10px' }} />
          <div style={{ fontSize: '11px', fontVariantNumeric: 'tabular-nums' }}>{state.observations} of {state.required ?? '—'}</div>
        </div>
      ) : (
        <div style={{ fontSize: '20px', fontVariantNumeric: 'tabular-nums', color: isBreached ? 'var(--state-breach)' : 'var(--ink-primary)', position: 'relative' }}>
          {read || title}
        </div>
      )}
      {reference && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{reference}</div>}
      {isBreached && reason && <div style={{ fontSize: '11px', color: 'var(--state-breach)' }}>{reason}</div>}
      {action}
      {children}
    </div>
  )
}
