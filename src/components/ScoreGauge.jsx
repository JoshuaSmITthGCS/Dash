const SIZE = 200
const STROKE = 16
const RADIUS = (SIZE - STROKE) / 2
const CENTER = SIZE / 2

// Semi-circle arc from 180deg to 0deg (bottom-left to bottom-right through top)
const ARC_SWEEP = 260 // total arc sweep in degrees
const ARC_LENGTH = (ARC_SWEEP / 360) * 2 * Math.PI * RADIUS

function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

function describeArc(cx, cy, r, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, r, endAngle)
  const end = polarToCartesian(cx, cy, r, startAngle)
  const large = endAngle - startAngle > 180 ? 1 : 0
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 0 ${end.x} ${end.y}`
}

function scoreLabel(score) {
  if (score >= 80) return 'Strong'
  if (score >= 60) return 'Moderate'
  if (score >= 40) return 'Fair'
  if (score >= 20) return 'Developing'
  return 'Weak'
}

export default function ScoreGauge({ score = 0, available = true, label = '', provisional = false, reason = '' }) {
  const clampedScore = Math.max(0, Math.min(100, score))
  const fillLength = available ? (clampedScore / 100) * ARC_LENGTH : 0
  const trackPath = describeArc(CENTER, CENTER, RADIUS, -ARC_SWEEP / 2 + 180, ARC_SWEEP / 2 + 180)
  const needleAngle = -ARC_SWEEP / 2 + 180 + (clampedScore / 100) * ARC_SWEEP
  const needleTip = polarToCartesian(CENTER, CENTER, RADIUS - STROKE / 2 - 4, needleAngle)

  return (
    <div className="score-gauge" role="img" aria-label={`${label}: ${available ? `${score} out of 100, ${scoreLabel(score)}` : 'unavailable'}`}>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width={SIZE} height={SIZE} className="score-gauge-svg">
        <defs>
          <linearGradient id="gauge-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--negative)" />
            <stop offset="45%" stopColor="var(--warning)" />
            <stop offset="100%" stopColor="var(--positive)" />
          </linearGradient>
        </defs>
        <path d={trackPath} fill="none" stroke="var(--surface-tertiary)" strokeWidth={STROKE} strokeLinecap="round" />
        {available && (
          <path
            className="gauge-fill-arc"
            d={trackPath}
            fill="none"
            stroke="url(#gauge-gradient)"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={`${fillLength} ${ARC_LENGTH}`}
          />
        )}
        {available && (
          <circle cx={needleTip.x} cy={needleTip.y} r="6" fill="var(--surface-primary)" stroke="var(--text-primary)" strokeWidth="2.5" className="gauge-needle" />
        )}
      </svg>
      <div className="gauge-readout">
        <strong>{available ? score : '–'}</strong>
        <span>{available ? scoreLabel(score) : reason || 'Unavailable'}</span>
        {provisional && <span className="provisional-badge">Provisional</span>}
      </div>
    </div>
  )
}
