import { dipWatch } from '../lib/dipWatch'

const STATUS_COPY = {
  near_floor: {
    label: 'Near the floor',
    hint: 'Trading close to the estimated bottom of this pullback.',
  },
  in_range: {
    label: 'Still working lower',
    hint: 'Between the estimated floor and the level that would confirm a recovery.',
  },
  recovering: {
    label: 'Recovering',
    hint: 'Back above the recovery level - the downtrend looks over.',
  },
}

// Shown only for stances the platform already treats as buy-worthy while the stock is
// actually down from its highs - see src/lib/dipWatch.js for the floor/max calculation.
export default function DipWatchBadge({ stock }) {
  const watch = dipWatch(stock)
  if (!watch) return null
  const copy = STATUS_COPY[watch.status]

  return (
    <div className={`dip-watch ${watch.status}`} aria-label="Buy-the-dip watch">
      <div className="dip-watch-head">
        <strong>{copy.label}</strong>
        <span>{copy.hint}</span>
      </div>
      <div className="dip-watch-levels">
        <div>
          <span>Floor (est. bottom)</span>
          <b>${watch.floor.toFixed(2)}</b>
        </div>
        <div>
          <span>Recovery level</span>
          <b>${watch.max.toFixed(2)}</b>
        </div>
      </div>
      <p className="dip-watch-note">
        A reasonable pair of broker alerts: drops below ${watch.floor.toFixed(2)}, rises above ${watch.max.toFixed(2)}.
      </p>
    </div>
  )
}
