import { Link } from 'react-router-dom'
import CompanyLogo from './CompanyLogo.jsx'
import { weekRange } from '../lib/dipWatch.js'

const STATUS_COPY = {
  near_floor: 'Near the floor',
  in_range: 'Still working lower',
}

// One row's 52-week range as a horizontal track, with dipWatch's estimated floor-to-
// recovery buy zone shaded inside it and today's price marked on top - so "how far down is
// this" and "how close is it to the zone this platform would flag as a buy-worthy dip" read
// off the same bar instead of two separate numbers.
function DipRangeRow({ row }) {
  const { screen, price } = row
  const range = weekRange(row)
  if (!range) return null
  const axisMin = Math.min(range.weekLow, screen.floor)
  const axisMax = Math.max(range.weekHigh, screen.max)
  const span = axisMax - axisMin || 1
  const pct = (value) => Math.min(100, Math.max(0, ((value - axisMin) / span) * 100))
  const zoneLeft = pct(screen.floor)
  const zoneWidth = Math.max(1, pct(screen.max) - zoneLeft)

  return (
    <div className="dip-chart-row">
      <div className="dip-chart-identity">
        <CompanyLogo company={row} size={28} />
        <div><strong>{row.ticker}</strong><span>{row.name}</span></div>
      </div>
      <div className="dip-chart-track-wrap">
        <div
          className="dip-chart-track"
          role="img"
          aria-label={`${row.ticker} at $${price.toFixed(2)}, ${Math.abs(screen.distanceToFloorPct).toFixed(1)}% ${screen.distanceToFloorPct >= 0 ? 'above' : 'below'} its estimated floor of $${screen.floor.toFixed(2)}, within a 52-week range of $${range.weekLow.toFixed(2)} to $${range.weekHigh.toFixed(2)}.`}
        >
          <span className="dip-chart-buyzone" style={{ left: `${zoneLeft}%`, width: `${zoneWidth}%` }} />
          <span className={`dip-chart-marker ${screen.status}`} style={{ left: `${pct(price)}%` }} />
        </div>
        <div className="dip-chart-track-labels">
          <span>${range.weekLow.toFixed(0)} 52w low</span>
          <span>${range.weekHigh.toFixed(0)} 52w high</span>
        </div>
      </div>
      <div className="dip-chart-figures">
        <b>${price.toFixed(2)}</b>
        <span className={`dip-chart-status ${screen.status}`}>{STATUS_COPY[screen.status]}</span>
      </div>
      <div className="dip-chart-score"><b>{row.score}</b><small>score</small></div>
    </div>
  )
}

/**
 * Names this platform already rates ATTRACTIVE or PROMISING that are also genuinely down
 * from their highs right now - src/lib/researchScreens.js's rankBuyingTheDip widened across
 * the universe, rather than the single-stock dip-watch badge (src/components/DipWatchBadge.jsx).
 * Quality first, proximity to the estimated floor second: a merely cheap name never crowds
 * out a merely-dipping great one.
 */
export default function BuyingTheDipChart({ rows }) {
  if (!rows.length) {
    return (
      <section className="card buying-the-dip-chart" aria-labelledby="buying-the-dip-title">
        <header className="section-heading">
          <div><span className="eyebrow">Quality down from its highs</span><h2 id="buying-the-dip-title">Buying the dip</h2></div>
        </header>
        <p className="dip-chart-note">No ATTRACTIVE or PROMISING name is currently down far enough from its highs to clear this screen. Check back after the next data refresh.</p>
      </section>
    )
  }
  return (
    <section className="card buying-the-dip-chart" aria-labelledby="buying-the-dip-title">
      <header className="section-heading">
        <div><span className="eyebrow">Quality down from its highs</span><h2 id="buying-the-dip-title">Buying the dip</h2></div>
        <Link to="/research">Full research →</Link>
      </header>
      <p className="dip-chart-note">
        Stances the platform already rates ATTRACTIVE or PROMISING that are currently trading down from their
        highs. The shaded band is the estimated floor-to-recovery zone from the same model behind each stock's
        dip-watch badge; the dot is today's price. Research context, not a buy signal or a guarantee of a bounce.
      </p>
      <div className="dip-chart-rows">
        {rows.map((row) => <DipRangeRow key={row.ticker} row={row} />)}
      </div>
    </section>
  )
}
