/**
 * Ultra HUD Components - Command Center
 * Ultra-dense, multi-layered sci-fi interface components
 */

import { useEffect, useState } from 'react'

/**
 * Central Circular Radar Display
 * Shows stocks arranged in a circle with radar sweep
 */
export function CircularRadar({ stocks = [], onStockClick }) {
  const angleStep = (2 * Math.PI) / stocks.length

  return (
    <div className="central-radar">
      <div className="radar-rings">
        {/* Concentric rings */}
        <div className="radar-ring" />
        <div className="radar-ring" />
        <div className="radar-ring" />
        <div className="radar-ring" />

        {/* Rotating sweep */}
        <div className="radar-sweep" />

        {/* Crosshair */}
        <div className="radar-crosshair" />

        {/* Stock positions */}
        {stocks.map((stock, index) => {
          const angle = index * angleStep
          const radius = 240 // Distance from center
          const x = 50 + (radius / 300) * 50 * Math.cos(angle)
          const y = 50 + (radius / 300) * 50 * Math.sin(angle)

          return (
            <div
              key={stock.ticker}
              className="radar-stock"
              style={{
                left: `${x}%`,
                top: `${y}%`,
              }}
              onClick={() => onStockClick?.(stock)}
            >
              <div className="radar-stock-ring" />
              <div className="radar-stock-content">
                <span>{stock.ticker}</span>
                <span className="radar-stock-score">{Math.round(stock.score)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Waveform Display
 * Shows data as a waveform chart
 */
export function Waveform({ data = [], color = 'var(--brand-primary)' }) {
  const width = 280
  const height = 80
  const padding = 10

  if (data.length === 0) return null

  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1

  const points = data.map((value, index) => {
    const x = padding + (index / (data.length - 1)) * (width - 2 * padding)
    const y = padding + (1 - (value - min) / range) * (height - 2 * padding)
    return `${x},${y}`
  }).join(' ')

  const fillPoints = `${padding},${height - padding} ${points} ${width - padding},${height - padding}`

  return (
    <div className="waveform">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="waveform-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.6" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline className="waveform-path" points={points} />
        <polygon className="waveform-fill" points={fillPoints} />
      </svg>
    </div>
  )
}

/**
 * Technical Panel
 * Container with header and indicator
 */
export function TechPanel({ title, children, active = true }) {
  return (
    <div className="tech-panel">
      <div className="tech-panel-header">
        <span className="tech-panel-title">{title}</span>
        {active && <div className="tech-panel-indicator" />}
      </div>
      {children}
    </div>
  )
}

/**
 * Data Strip
 * Grid of labeled data cells
 */
export function DataStrip({ items = [] }) {
  return (
    <div className="data-strip">
      {items.map((item, index) => (
        <div key={index} className="data-cell">
          <span className="data-cell-label">{item.label}</span>
          <span className="data-cell-value">{item.value}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * Mini Gauge
 * Horizontal progress bar with value
 */
export function MiniGauge({ value = 0, max = 100 }) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100)

  return (
    <div className="mini-gauge">
      <div className="mini-gauge-value">{Math.round(value)}</div>
      <div className="mini-gauge-track">
        <div className="mini-gauge-fill" style={{ width: `${percentage}%` }} />
      </div>
    </div>
  )
}

/**
 * Bar Chart Strip
 * Compact bar chart
 */
export function BarChartStrip({ data = [] }) {
  if (data.length === 0) return null

  const max = Math.max(...data.map(d => d.value))

  return (
    <div className="bar-chart-strip">
      {data.map((item, index) => (
        <div
          key={index}
          className="bar-chart-bar"
          style={{ height: `${(item.value / max) * 100}%` }}
          title={`${item.label}: ${item.value}`}
        />
      ))}
    </div>
  )
}

/**
 * Circular Progress Mini
 * Small circular progress indicator
 */
export function CircularMini({ value = 0, max = 100 }) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100)
  const radius = 20
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (percentage / 100) * circumference

  return (
    <div className="circular-mini">
      <svg viewBox="0 0 50 50">
        <circle className="circular-mini-bg" cx="25" cy="25" r={radius} />
        <circle
          className="circular-mini-fill"
          cx="25"
          cy="25"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="circular-mini-text">{Math.round(percentage)}</div>
    </div>
  )
}

/**
 * Metric Grid
 * 2-column grid of metrics
 */
export function MetricGrid({ items = [] }) {
  return (
    <div className="metric-grid">
      {items.map((item, index) => (
        <div key={index} className="metric-item">
          <div className="metric-label">{item.label}</div>
          <div className="metric-value">{item.value}</div>
        </div>
      ))}
    </div>
  )
}

/**
 * Status Matrix
 * 3-column grid of status cells
 */
export function StatusMatrix({ items = [] }) {
  return (
    <div className="status-matrix">
      {items.map((item, index) => (
        <div key={index} className="status-cell">
          <span className="status-cell-value">{item.value}</span>
          <span className="status-cell-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

/**
 * Sector Distribution Donut
 * Shows sector allocation as mini donut
 */
export function SectorDonut({ sectors = [] }) {
  const total = sectors.reduce((sum, s) => sum + s.count, 0)
  let currentAngle = -90 // Start at top

  const arcs = sectors.slice(0, 5).map((sector) => {
    const percentage = sector.count / total
    const angle = percentage * 360
    const endAngle = currentAngle + angle

    const startX = 25 + 18 * Math.cos((currentAngle * Math.PI) / 180)
    const startY = 25 + 18 * Math.sin((currentAngle * Math.PI) / 180)
    const endX = 25 + 18 * Math.cos((endAngle * Math.PI) / 180)
    const endY = 25 + 18 * Math.sin((endAngle * Math.PI) / 180)

    const largeArcFlag = angle > 180 ? 1 : 0

    const path = `M 25 25 L ${startX} ${startY} A 18 18 0 ${largeArcFlag} 1 ${endX} ${endY} Z`

    currentAngle = endAngle

    return {
      path,
      sector: sector.name,
      count: sector.count,
    }
  })

  return (
    <svg viewBox="0 0 50 50" style={{ width: '100%', height: 'auto' }}>
      {arcs.map((arc, index) => (
        <path
          key={index}
          d={arc.path}
          fill={`rgba(0, 212, 255, ${0.3 + index * 0.15})`}
          stroke="rgba(0, 212, 255, 0.4)"
          strokeWidth="0.5"
        >
          <title>{`${arc.sector}: ${arc.count}`}</title>
        </path>
      ))}
      <circle cx="25" cy="25" r="10" fill="rgba(0, 0, 0, 0.8)" />
    </svg>
  )
}

/**
 * Live Clock
 * Updates every second
 */
export function LiveClock() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])

  return (
    <span>
      {time.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      })} UTC
    </span>
  )
}

/**
 * Scrolling Ticker
 * Horizontal scrolling text
 */
export function ScrollingTicker({ items = [], speed = 30 }) {
  const text = items.join('  •  ')

  return (
    <div style={{
      overflow: 'hidden',
      whiteSpace: 'nowrap',
      fontSize: 'var(--fs-2xs)',
      fontFamily: 'var(--font-mono)',
      color: 'rgba(255, 255, 255, 0.5)',
    }}>
      <div style={{
        display: 'inline-block',
        animation: `scroll-left ${speed}s linear infinite`,
      }}>
        {text}&nbsp;&nbsp;&nbsp;&nbsp;{text}
      </div>
      <style>{`
        @keyframes scroll-left {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  )
}

/**
 * Performance Indicator
 * Shows +/- with color
 */
export function PerformanceIndicator({ value, label }) {
  const isPositive = value >= 0
  const color = isPositive ? '#00ff88' : '#ff4466'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
      <span className="data-cell-label">{label}</span>
      <span style={{
        font: 'var(--fw-bold) var(--fs-sm) var(--font-mono)',
        color,
        textShadow: `0 0 8px ${color}`,
      }}>
        {isPositive ? '+' : ''}{value.toFixed(2)}%
      </span>
    </div>
  )
}
