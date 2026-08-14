const SECTOR_COLORS = [
  'var(--sector-tech)',
  'var(--sector-health)',
  'var(--sector-finance)',
  'var(--sector-consumer-disc)',
  'var(--sector-consumer-staples)',
  'var(--sector-energy)',
  'var(--sector-industrials)',
  'var(--sector-materials)',
  'var(--sector-real-estate)',
  'var(--sector-utilities)',
  'var(--sector-comm)',
]

const SIZE = 200
const STROKE = 28
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS
const CENTER = SIZE / 2

export default function AllocationDonut({ sectors = [], totalLabel = '' }) {
  if (!sectors.length) return null
  let offset = 0
  const arcs = sectors.map((sector, index) => {
    const dash = (sector.pct / 100) * CIRCUMFERENCE
    const gap = CIRCUMFERENCE - dash
    const rotation = (offset / 100) * 360 - 90
    offset += sector.pct
    return { ...sector, dash, gap, rotation, color: SECTOR_COLORS[index % SECTOR_COLORS.length] }
  })

  return (
    <div className="allocation-donut-widget">
      <svg
        className="allocation-donut-svg"
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE}
        height={SIZE}
        role="img"
        aria-label={`Sector allocation: ${sectors.map((s) => `${s.sector} ${s.pct.toFixed(1)}%`).join(', ')}`}
      >
        <circle cx={CENTER} cy={CENTER} r={RADIUS} fill="none"
          stroke="var(--surface-tertiary)" strokeWidth={STROKE} />
        {arcs.map((arc) => (
          <circle
            key={arc.sector}
            className="donut-segment"
            cx={CENTER} cy={CENTER} r={RADIUS}
            fill="none"
            stroke={arc.color}
            strokeWidth={STROKE}
            strokeDasharray={`${arc.dash} ${arc.gap}`}
            strokeLinecap="butt"
            transform={`rotate(${arc.rotation} ${CENTER} ${CENTER})`}
          >
            <title>{arc.sector}: {arc.pct.toFixed(1)}%</title>
          </circle>
        ))}
      </svg>
      {totalLabel && <span className="donut-center-label">{totalLabel}</span>}
      <div className="donut-legend">
        {arcs.map((arc) => (
          <div key={arc.sector}>
            <i style={{ background: arc.color }} />
            <span>{arc.sector}</span>
            <b>{arc.pct.toFixed(1)}%</b>
          </div>
        ))}
      </div>
    </div>
  )
}
