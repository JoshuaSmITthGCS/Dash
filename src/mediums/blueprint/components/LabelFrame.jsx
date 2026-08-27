import { STATES } from '../../core/states.js'

/**
 * A dimensioned figure: the numeral sits above a drawn dimension line whose pattern IS the
 * four-state encoding (solid = established, dashed = accumulating, hatched-red = breached) and
 * whose weight (thickness) is the confidence channel — a lower-confidence figure draws with the
 * lighter construction pen weight even while established, a separate axis from the dash pattern
 * (DESIGN.md §6).
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE
  const weight = 1 + Math.round(confidence.level * 2) // 1-3px pen-width scale

  if (isUnavailable) {
    return (
      <div data-bp-sheet="true" data-capability-id={capabilityId}>
        <p style={{ fontSize: '11px', color: 'var(--ink-faint)', textTransform: 'uppercase' }}>{title}</p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span aria-hidden="true" style={{ flex: 1, borderBottom: `1px dashed var(--ink-faint)` }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '18px', color: 'var(--ink-faint)' }}>?</span>
        </div>
        <p style={{ fontSize: '10px', color: 'var(--ink-faint)' }}>{reason}</p>
      </div>
    )
  }

  return (
    <div data-bp-sheet="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId}>
      <p style={{ fontSize: '11px', color: 'var(--ink-faint)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {title}{mediumLine ? ` · ${mediumLine}` : ''}
      </p>
      <div
        data-dimension-line="true"
        data-state-pattern={isAccumulating ? 'dashed' : isBreached ? 'hatched' : 'solid'}
        style={{
          fontFamily: 'var(--font-mono)', fontSize: '20px', fontVariantNumeric: 'tabular-nums',
          color: isBreached ? 'var(--state-breach)' : 'var(--ink-primary)',
          borderBottom: `${weight}px ${isAccumulating ? 'dashed' : 'solid'} ${isBreached ? 'var(--state-breach)' : 'var(--rule-cyan)'}`,
          backgroundImage: isBreached ? 'repeating-linear-gradient(45deg, var(--state-breach) 0, var(--state-breach) 1px, transparent 1px, transparent 5px)' : undefined,
          backgroundSize: isBreached ? '100% 2px' : undefined,
          backgroundRepeat: isBreached ? 'repeat-x' : undefined,
          backgroundPosition: isBreached ? 'bottom' : undefined,
          display: 'inline-block', paddingBottom: '2px',
        }}
      >
        {isAccumulating && state.observations != null ? `${state.observations} / ${state.required ?? '—'}` : value ?? read ?? title}
      </div>
      {value != null && read && <p style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{read}</p>}
      {reference && <p style={{ fontSize: '10px', color: 'var(--rule-cyan)' }}>TOL: {reference}</p>}
      {isBreached && reason && <p style={{ fontSize: '10px', color: 'var(--state-breach)' }}>OUT OF TOLERANCE — {reason}</p>}
      {action}
      {children}
    </div>
  )
}
