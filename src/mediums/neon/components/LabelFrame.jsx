import { STATES } from '../../core/states.js'

/** Renders `n` tube segments, `lit` of them colored — the literal "unlit segments = missing observations" device. */
function TubeRow({ total = 8, lit = 0, chroma = 1, breached = false }) {
  const segments = Array.from({ length: Math.max(1, total) }, (_, i) => i < lit)
  const color = breached ? 'var(--brand-magenta)' : `color-mix(in srgb, var(--brand-cyan) ${Math.round(chroma * 100)}%, #4a4470)`
  return (
    <div aria-hidden="true" style={{ display: 'flex', gap: '2px' }}>
      {segments.map((isLit, i) => (
        <span key={i} style={{ width: '10px', height: '4px', background: isLit ? color : 'var(--rule-hairline)', borderRadius: '2px' }} />
      ))}
    </div>
  )
}

export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE
  const total = state.required || 8
  const lit = isAccumulating ? Math.round((state.progress ?? 0) * total) : isUnavailable ? 0 : total

  return (
    // "Unavailable = dead tube + reason" (DESIGN.md §2) — floored well above the original 0.4,
    // which a11y.spec.mjs's WCAG contrast check found crushing even --ink-primary text under the
    // 4.5:1 floor; the printed reason must stay legible per the protected-disclosure rule.
    <div data-neon-panel="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId} style={{ opacity: isUnavailable ? 0.85 : 1 }}>
      <header style={{ fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-secondary)' }}>
        {title}{mediumLine ? ` · ${mediumLine}` : ''}
      </header>
      <div style={{ fontSize: '18px', fontVariantNumeric: 'tabular-nums', color: 'var(--ink-primary)' }}>
        {isAccumulating ? `${state.observations ?? 0} / ${state.required ?? '—'}` : value ?? read ?? title}
      </div>
      {value != null && read && <div style={{ fontSize: '11px', color: 'var(--ink-secondary)' }}>{read}</div>}
      <TubeRow total={total} lit={lit} chroma={confidence.level} breached={isBreached} />
      {reference && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{reference}</div>}
      {isUnavailable && reason && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>dead tube — {reason}</div>}
      {action}
      {children}
    </div>
  )
}
