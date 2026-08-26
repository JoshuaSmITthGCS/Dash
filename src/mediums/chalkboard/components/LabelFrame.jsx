import { STATES } from '../../core/states.js'

/**
 * Dotted leader line from label to value (the single most useful device for a long metric list,
 * per the master doc — Uniform Connectedness applied literally). The erasure smudge for a prior
 * value renders BEHIND the current value in stacking order (DOM order here) at a fixed lower
 * opacity/luminance step, and carries `data-state-mark="prior"` so Phase 3 assertion 11 can
 * check both facts mechanically — never just hoped for visually.
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, state, confidence, reason, previous, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE
  const pressure = 0.4 + confidence.level * 0.6 // chalk pressure — confidence channel, distinct from completeness

  if (isUnavailable) {
    return (
      <div data-chalk-box="true" data-capability-id={capabilityId} style={{ opacity: 0.5 }}>
        <div style={{ fontSize: '20px' }}>?</div>
        <div style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>{reason}</div>
      </div>
    )
  }

  return (
    <div data-chalk-box="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId} style={{ opacity: pressure }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
        <span style={{ fontSize: '13px', color: 'var(--ink-faint)' }}>{title}</span>
        <span aria-hidden="true" style={{ flex: 1, borderBottom: '2px dotted var(--ink-faint)', minWidth: '16px' }} />
        <span style={{ position: 'relative', display: 'inline-block' }}>
          {previous != null && (
            <span
              data-state-mark="prior"
              aria-hidden="true"
              style={{
                // Deliberately NOT fontVariantNumeric/tabular-nums: this is a decorative echo of
                // a prior reading (aria-hidden, never the primary content), not itself a numeral
                // subject to the numerals-stay-clean legibility floor — the blur is the point.
                position: 'absolute', right: 0, top: 0,
                opacity: 0.28, filter: 'blur(0.4px)',
                color: 'var(--ink-faint)',
                fontSize: '20px',
                zIndex: 0,
              }}
            >
              {previous}
            </span>
          )}
          <span
            data-state-mark="current"
            style={{
              position: 'relative', zIndex: 1,
              fontSize: '20px', fontVariantNumeric: 'tabular-nums',
              color: isBreached ? 'var(--chalk-alert)' : 'var(--chalk-white)',
              textDecoration: isBreached ? 'underline' : 'none',
              textDecorationStyle: isBreached ? 'double' : undefined,
            }}
          >
            {isAccumulating && state.observations != null ? `${state.observations}/${state.required ?? '—'}` : value ?? read ?? title}
          </span>
        </span>
      </div>
      {value != null && read && <div style={{ fontSize: '13px', color: 'var(--ink-faint)' }}>{read}</div>}
      {mediumLine && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{mediumLine}</div>}
      {reference && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{reference}</div>}
      {isBreached && reason && <div style={{ fontSize: '11px', color: 'var(--chalk-alert)' }}>{reason}</div>}
      {action}
      {children}
    </div>
  )
}
