import { useMemo } from 'react'

export default function BacktestChart({ results, selectedStrategy }) {
  // Prepare chart data
  const chartData = useMemo(() => {
    if (!results) return null

    const { equalWeight, rankWeighted, spy } = results

    // Combine all portfolio value points and normalize to starting value
    const allPoints = []

    if (selectedStrategy === 'all' || selectedStrategy === 'equalWeight') {
      equalWeight.portfolioValue.forEach(point => {
        allPoints.push({
          date: new Date(point.date),
          strategy: 'Equal-Weight',
          value: point.value,
          color: '#3b82f6' // blue
        })
      })
    }

    if (selectedStrategy === 'all' || selectedStrategy === 'rankWeighted') {
      rankWeighted.portfolioValue.forEach(point => {
        allPoints.push({
          date: new Date(point.date),
          strategy: 'Rank-Weighted',
          value: point.value,
          color: '#8b5cf6' // purple
        })
      })
    }

    if (selectedStrategy === 'all' || selectedStrategy === 'spy') {
      spy.portfolioValue.forEach(point => {
        allPoints.push({
          date: new Date(point.date),
          strategy: 'SPY Benchmark',
          value: point.value,
          color: '#6b7280' // gray
        })
      })
    }

    if (allPoints.length === 0) return null

    // Sort by date
    allPoints.sort((a, b) => a.date - b.date)

    // Find min/max values for scaling
    const minValue = Math.min(...allPoints.map(p => p.value))
    const maxValue = Math.max(...allPoints.map(p => p.value))

    // Group by strategy for line rendering
    const strategies = {}
    allPoints.forEach(point => {
      if (!strategies[point.strategy]) {
        strategies[point.strategy] = []
      }
      strategies[point.strategy].push(point)
    })

    return {
      strategies,
      minValue,
      maxValue,
      minDate: allPoints[0].date,
      maxDate: allPoints[allPoints.length - 1].date
    }
  }, [results, selectedStrategy])

  if (!chartData) {
    return (
      <div style={{ padding: 40, textAlign: 'center', opacity: 0.6 }}>
        No chart data available
      </div>
    )
  }

  const { strategies, minValue, maxValue, minDate, maxDate } = chartData

  // Chart dimensions
  const width = 800
  const height = 400
  const padding = { top: 20, right: 120, bottom: 60, left: 80 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom

  // Scale functions
  const valueRange = maxValue - minValue
  const timeRange = maxDate - minDate

  const scaleY = (value) => {
    return chartHeight - ((value - minValue) / valueRange) * chartHeight
  }

  const scaleX = (date) => {
    return ((date - minDate) / timeRange) * chartWidth
  }

  // Y-axis ticks (5 ticks)
  const yTicks = []
  for (let i = 0; i <= 4; i++) {
    const value = minValue + (valueRange * i / 4)
    yTicks.push({
      value,
      y: scaleY(value),
      label: `$${Math.round(value).toLocaleString()}`
    })
  }

  // X-axis ticks (show first, middle, last dates)
  const xTicks = []
  if (timeRange > 0) {
    const dates = [minDate, new Date((minDate.getTime() + maxDate.getTime()) / 2), maxDate]
    dates.forEach(date => {
      xTicks.push({
        date,
        x: scaleX(date),
        label: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
      })
    })
  }

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        width={width}
        height={height}
        style={{ display: 'block', margin: '0 auto' }}
      >
        {/* Y-axis */}
        <line
          x1={padding.left}
          y1={padding.top}
          x2={padding.left}
          y2={height - padding.bottom}
          stroke="var(--border)"
          strokeWidth={2}
        />

        {/* X-axis */}
        <line
          x1={padding.left}
          y1={height - padding.bottom}
          x2={width - padding.right}
          y2={height - padding.bottom}
          stroke="var(--border)"
          strokeWidth={2}
        />

        {/* Y-axis ticks and labels */}
        {yTicks.map((tick, i) => (
          <g key={i}>
            <line
              x1={padding.left - 5}
              y1={padding.top + tick.y}
              x2={padding.left}
              y2={padding.top + tick.y}
              stroke="var(--border)"
              strokeWidth={1}
            />
            <line
              x1={padding.left}
              y1={padding.top + tick.y}
              x2={width - padding.right}
              y2={padding.top + tick.y}
              stroke="var(--border)"
              strokeWidth={0.5}
              strokeDasharray="4 4"
              opacity={0.3}
            />
            <text
              x={padding.left - 10}
              y={padding.top + tick.y + 4}
              textAnchor="end"
              fontSize={12}
              fill="currentColor"
              opacity={0.7}
            >
              {tick.label}
            </text>
          </g>
        ))}

        {/* X-axis ticks and labels */}
        {xTicks.map((tick, i) => (
          <g key={i}>
            <line
              x1={padding.left + tick.x}
              y1={height - padding.bottom}
              x2={padding.left + tick.x}
              y2={height - padding.bottom + 5}
              stroke="var(--border)"
              strokeWidth={1}
            />
            <text
              x={padding.left + tick.x}
              y={height - padding.bottom + 20}
              textAnchor="middle"
              fontSize={11}
              fill="currentColor"
              opacity={0.7}
            >
              {tick.label}
            </text>
          </g>
        ))}

        {/* Plot lines for each strategy */}
        {Object.entries(strategies).map(([strategyName, points]) => {
          if (points.length === 0) return null

          const color = points[0].color

          // Build path
          const pathData = points.map((point, i) => {
            const x = padding.left + scaleX(point.date)
            const y = padding.top + scaleY(point.value)
            return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
          }).join(' ')

          return (
            <g key={strategyName}>
              <path
                d={pathData}
                fill="none"
                stroke={color}
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {/* Legend */}
              <g transform={`translate(${width - padding.right + 10}, ${padding.top + Object.keys(strategies).indexOf(strategyName) * 25})`}>
                <line
                  x1={0}
                  y1={0}
                  x2={20}
                  y2={0}
                  stroke={color}
                  strokeWidth={2.5}
                />
                <text
                  x={25}
                  y={4}
                  fontSize={12}
                  fill="currentColor"
                >
                  {strategyName}
                </text>
                <text
                  x={25}
                  y={17}
                  fontSize={10}
                  fill="currentColor"
                  opacity={0.6}
                >
                  {points.length > 0 ? `$${Math.round(points[points.length - 1].value).toLocaleString()}` : '—'}
                </text>
              </g>
            </g>
          )
        })}

        {/* Axis labels */}
        <text
          x={padding.left - 50}
          y={height / 2}
          transform={`rotate(-90, ${padding.left - 50}, ${height / 2})`}
          textAnchor="middle"
          fontSize={13}
          fontWeight={600}
          fill="currentColor"
          opacity={0.8}
        >
          Portfolio Value ($)
        </text>

        <text
          x={width / 2}
          y={height - 10}
          textAnchor="middle"
          fontSize={13}
          fontWeight={600}
          fill="currentColor"
          opacity={0.8}
        >
          Date
        </text>
      </svg>

      {/* Mobile fallback message */}
      <div style={{
        fontSize: 12,
        opacity: 0.6,
        textAlign: 'center',
        marginTop: 12,
        display: 'none'
      }}
        className="mobile-only"
      >
        Chart best viewed on larger screens. Scroll horizontally to see full timeline.
      </div>
    </div>
  )
}
