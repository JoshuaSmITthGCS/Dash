import { STATES } from '../../core/states.js'
import { seededRange } from '../../core/seed.js'

const PLATE_W = 120
const PLATE_H = 70

function magnitudeFrom(read) {
  const parsed = read != null ? parseFloat(String(read).replace(/[^0-9.-]/g, '')) : NaN
  return Number.isFinite(parsed) ? Math.abs(parsed) : 1
}

/**
 * One star on its own small plate excerpt — the whole medium plots every metric at a real,
 * deterministic coordinate on a faint graticule rather than stacking cards (DESIGN.md §7).
 * Mark AREA (not radius) scales with the metric's own magnitude — the correct astronomical
 * convention, since radius-scaling exaggerates large values. Where a metric publishes a real
 * bootstrap CI (`parts.confidenceInterval`), the mark renders as an error ellipse sized to the
 * interval instead of a circle — never invented for a metric that doesn't publish one.
 */
export default function LabelFrame({ parts, capabilityId, children }) {
  const { title, read, reference, state, confidence, reason, confidenceInterval, action } = parts
  const isBreached = state.state === STATES.BREACHED
  const isAccumulating = state.state === STATES.ACCUMULATING
  const isUnavailable = state.state === STATES.UNAVAILABLE

  const cx = seededRange(capabilityId || title, 20, PLATE_W - 20, 'x')
  const cy = seededRange(capabilityId || title, 16, PLATE_H - 16, 'y')
  const magnitude = magnitudeFrom(read)
  const radius = 3 + Math.sqrt(magnitude) * 2.4 // area-proportional: r ~ sqrt(value)
  const ellipseWidth = confidenceInterval ? Math.max(4, Math.abs(confidenceInterval[1] - confidenceInterval[0]) * 200) : null

  return (
    <div data-sc-plate="true" data-capability-id={capabilityId}>
      <svg width={PLATE_W} height={PLATE_H} viewBox={`0 0 ${PLATE_W} ${PLATE_H}`} role="img" aria-label={`${title} plotted`}>
        <line x1={PLATE_W / 2} x2={PLATE_W / 2} y1={0} y2={PLATE_H} stroke="var(--graticule)" strokeWidth="0.5" />
        <line x1={0} x2={PLATE_W} y1={PLATE_H / 2} y2={PLATE_H / 2} stroke="var(--graticule)" strokeWidth="0.5" />
        {!isUnavailable && ellipseWidth ? (
          <ellipse cx={cx} cy={cy} rx={ellipseWidth} ry={radius} fill="none" stroke={isBreached ? 'var(--state-breach)' : 'var(--ink-primary)'} strokeWidth="1" />
        ) : !isUnavailable ? (
          <circle
            cx={cx} cy={cy} r={radius}
            fill={isAccumulating ? 'none' : isBreached ? 'var(--state-breach)' : 'var(--ink-primary)'}
            stroke={isBreached ? 'var(--state-breach)' : 'var(--ink-primary)'}
            strokeWidth={isAccumulating ? '1' : '0'}
          />
        ) : null}
        {isBreached && (
          <g aria-hidden="true">
            <line x1={cx - radius - 3} x2={cx + radius + 3} y1={cy} y2={cy} stroke="var(--state-breach)" strokeWidth="0.75" />
            <line x1={cx} x2={cx} y1={cy - radius - 3} y2={cy + radius + 3} stroke="var(--state-breach)" strokeWidth="0.75" />
          </g>
        )}
        <text x={cx + radius + 4} y={cy + 3} fontSize="8" fill="var(--ink-primary)" data-sc-designation="true" fontStyle="italic">
          {title}
        </text>
        {isAccumulating && state.observations != null && (
          <text x={cx + radius + 4} y={cy + 12} fontSize="7" fill="var(--ink-faint)">{state.observations} of {state.required ?? '—'}</text>
        )}
      </svg>
      <div data-sc-legend="true">
        <p data-sc-smallcaps="true" style={{ margin: 0 }}>{title}</p>
        {isUnavailable && <p style={{ color: 'var(--ink-faint)', margin: 0 }}>catalogued, unplotted — {reason}</p>}
        {reference && <p style={{ color: 'var(--ink-faint)', margin: 0 }}>{reference}</p>}
        <p style={{ color: 'var(--ink-faint)', fontStyle: 'italic', margin: 0 }}>
          Seeing: {confidence.level >= 0.7 ? 'excellent' : confidence.level >= 0.4 ? 'fair' : 'poor'} — {confidence.basis[0]}.
        </p>
      </div>
      {action}
      {children}
    </div>
  )
}
