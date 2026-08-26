import { STATES } from '../../core/states.js'

/**
 * The readout — Cockpit's rendering of the wall-label contract. Every metric is one bezel:
 * title as the micro-label, the read as the plain-language line, state as full/dimmed/unlit
 * luminance, and confidence as a small blur glyph beside the readout (never blurring the value
 * itself — the glyph is a separate mark).
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, provenance, state, confidence, reason, action } = parts
  const isLive = state.state === STATES.ESTABLISHED
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE

  return (
    <div
      data-cockpit-bezel="true"
      data-live={isLive ? 'true' : undefined}
      data-breached={isBreached ? 'true' : undefined}
      data-capability-id={capabilityId}
      style={{ opacity: isUnavailable ? 0.45 : 1 }}
    >
      <header style={{ display: 'flex', justifyContent: 'space-between', letterSpacing: '0.06em', fontSize: '11px', textTransform: 'uppercase', color: 'var(--ink-secondary)' }}>
        <span>{title}</span>
        {mediumLine && <span>{mediumLine}</span>}
      </header>

      <div style={{ fontSize: '20px', color: isBreached ? 'var(--state-breach)' : 'var(--ink-primary)', fontVariantNumeric: 'tabular-nums' }}>
        {isAccumulating && state.observations != null
          ? `${state.observations} / ${state.required ?? '—'}`
          : value ?? read ?? title}
      </div>
      {value != null && read && <p style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>{read}</p>}

      {reference && <div style={{ fontSize: '12px', color: 'var(--ink-faint)' }}>LIMIT · {reference}</div>}
      {reason && <div style={{ fontSize: '12px', color: isBreached ? 'var(--state-breach)' : 'var(--ink-faint)' }}>{reason}</div>}

      <footer style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
        <span
          aria-hidden="true"
          data-testid="confidence-glyph"
          style={{
            width: '8px', height: '8px', borderRadius: '50%',
            background: 'var(--ink-secondary)',
            filter: `blur(${(1 - confidence.level) * 2}px)`,
          }}
        />
        <span style={{ fontSize: '10px', color: 'var(--ink-faint)' }}>{provenance || 'source unknown'}</span>
      </footer>

      {action}
      {children}
    </div>
  )
}
