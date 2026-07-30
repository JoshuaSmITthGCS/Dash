function pathFor(values, width, height, pad) {
  const usable = values.filter(Number.isFinite)
  if (usable.length < 2) return ''
  const min = Math.min(...usable)
  const max = Math.max(...usable)
  const span = max - min || 1
  return values.map((value, index) => {
    const x = pad + (index / (values.length - 1)) * (width - pad * 2)
    const y = pad + (1 - ((value - min) / span)) * (height - pad * 2)
    return `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`
  }).join(' ')
}

export default function Sparkline({ values = [], label = 'Price trend', height = 86, className = '' }) {
  const clean = values.filter(Number.isFinite)
  if (clean.length < 2) {
    return <div className={`sparkline-empty ${className}`} style={{ height }}>Trend unavailable</div>
  }
  const width = 320
  const positive = clean.at(-1) >= clean[0]
  const line = pathFor(clean, width, height, 4)
  const area = `${line} L${width - 4} ${height - 2} L4 ${height - 2} Z`
  return (
    <svg className={`sparkline ${className}`} viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none" height={height} role="img"
      aria-label={`${label}; ${positive ? 'up' : 'down'} over the displayed period`}>
      <defs>
        <linearGradient id={`spark-${positive ? 'up' : 'down'}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={positive ? 'var(--up)' : 'var(--down)'} stopOpacity=".28" />
          <stop offset="1" stopColor={positive ? 'var(--up)' : 'var(--down)'} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${positive ? 'up' : 'down'})`} />
      <path d={line} fill="none" stroke={positive ? 'var(--up)' : 'var(--down)'}
        strokeWidth="3" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
