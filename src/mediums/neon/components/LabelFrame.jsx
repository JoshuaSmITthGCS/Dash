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
  const { title, mediumLine, read, reference, state, confidence, reason, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE
  const total = state.required || 8
  const lit = isAccumulating ? Math.round((state.progress ?? 0) * total) : isUnavailable ? 0 : total

  return (
    <div data-neon-panel="true" data-breached={isBreached ? 'true' : undefined} data-capability-id={capabilityId} style={{ opacity: isUnavailable ? 0.4 : 1 }}>
      <header style={{ fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--ink-secondary)' }}>
        {title}{mediumLine ? ` · ${mediumLine}` : ''}
      </header>
      <div style={{ fontSize: '18px', fontVariantNumeric: 'tabular-nums', color: 'var(--ink-primary)' }}>
        {read || (isAccumulating ? `${state.observations ?? 0} / ${state.required ?? '—'}` : title)}
      </div>
      <TubeRow total={total} lit={lit} chroma={confidence.level} breached={isBreached} />
      {reference && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{reference}</div>}
      {isUnavailable && reason && <div style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>dead tube — {reason}</div>}
      {action}
      {children}
    </div>
  )
}
