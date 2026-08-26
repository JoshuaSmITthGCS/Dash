import { STATES } from '../../core/states.js'

// Same tone vocabulary src/lib/signalMetrics.js's metricTone() produces (breached/ready/
// accumulating/pending) — Classic's CSS already styles `.tone-*`/`.signal-status-*` for exactly
// these four classes, so this mapping is definitional, not an adapter guessing at equivalence.
function toneFor(state) {
  if (state === STATES.BREACHED) return 'breached'
  if (state === STATES.ESTABLISHED) return 'ready'
  if (state === STATES.ACCUMULATING) return 'accumulating'
  return 'pending'
}

const STATUS_LABEL = { breached: 'Breached', ready: 'Ready', accumulating: 'Accumulating', pending: 'Unavailable' }

/**
 * Reuses the existing `.signal-metric`/`.tone-*`/`.chip.signal-status-*`/`.signal-kill` CSS from
 * `src/components/SignalMetricsPanel.jsx` (DESIGN.md §12's existing card/shelf system) — the
 * classes are ported as-is; the markup here is new because `WallLabel`'s `parts` contract (used
 * by all twelve mediums) is a different, narrower shape than that panel's raw metric row, so a
 * literal component reuse isn't a clean fit without reaching back into raw data WallLabel
 * deliberately doesn't pass through.
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, mediumLine, value, read, reference, state, confidence, reason, action } = parts
  const tone = toneFor(state.state)
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isBreached = state.state === STATES.BREACHED
  const text = isAccumulating && state.observations != null
    ? `${state.observations} of ${state.required ?? '—'}`
    : value ?? read ?? title

  return (
    <article className={`signal-metric tone-${tone}`} data-capability-id={capabilityId}>
      <header>
        <div>
          <strong>{title}</strong>
          {mediumLine && <small>{mediumLine}</small>}
        </div>
        <div className="signal-metric-value">
          <b style={{ fontVariantNumeric: 'tabular-nums' }}>{text}</b>
          <span className={`chip signal-status-${tone}`}>{STATUS_LABEL[tone]}</span>
        </div>
      </header>
      {value != null && read && <small>{read}</small>}
      {reason && <p className="signal-metric-state">{reason}</p>}
      {reference && (
        <footer>
          <span className={isBreached ? 'signal-kill breached' : 'signal-kill'}>
            {isBreached ? 'Breached: ' : 'Kill: '}{reference}
          </span>
        </footer>
      )}
      <p className="metric-confidence">
        {Math.round(confidence.level * 100)}% confidence — {confidence.basis[0]}
      </p>
      {action}
      {children}
    </article>
  )
}
