import { useState } from 'react'
import Icon from './Icons.jsx'
import { dailyMoveForPosition } from '../lib/marketPresentation.js'

const price = (value) => value == null ? '–' : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const percent = (value) => value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`

export default function StockTickerTape({ positions = [], label = 'Portfolio ticker tape' }) {
  const [paused, setPaused] = useState(false)
  const rows = positions.filter((position) => position?.ticker).map((position) => ({
    ...position,
    move: dailyMoveForPosition(position),
  }))
  if (!rows.length) return null
  const repeated = [...rows, ...rows]

  return (
    <section className={`stock-ticker-tape${paused ? ' paused' : ''}`} aria-label={label}>
      <div className="ticker-tape-viewport">
        <div className="ticker-tape-track" aria-live="off">
          {repeated.map((row, index) => (
            <span className="ticker-tape-item" key={`${row.ticker}-${index}`} aria-hidden={index >= rows.length ? 'true' : undefined}>
              <b>{row.ticker}</b>
              <span>{price(row.move.price ?? row.currentPrice)}</span>
              <em className={row.move.pct == null ? 'neutral' : row.move.pct >= 0 ? 'positive' : 'negative'}>
                {row.move.pct != null && <span aria-hidden="true">{row.move.pct >= 0 ? '▲' : '▼'}</span>}
                {percent(row.move.pct)}
              </em>
            </span>
          ))}
        </div>
      </div>
      <button type="button" className="ticker-pause" onClick={() => setPaused((value) => !value)} aria-pressed={paused}>
        <Icon name={paused ? 'arrow' : 'more'} size={15} />
        <span>{paused ? 'Resume' : 'Pause'} ticker</span>
      </button>
    </section>
  )
}
