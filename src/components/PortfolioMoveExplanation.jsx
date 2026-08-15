import { useState } from 'react'
import { signedPct } from '../lib/formatters.js'
import { ATTRIBUTION_PERIODS } from '../lib/portfolioAttribution.js'

const moveColor = (value) => value == null ? 'var(--text-faint)' : value >= 0 ? 'var(--up)' : 'var(--down)'

// Published dates are plain YYYY-MM-DD market dates; parsing them as UTC keeps a west-coast
// browser from rendering the window start a day early.
const windowDate = (value) => {
  if (!value) return null
  const date = new Date(`${String(value).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(date)
}

function ContributorRow({ holding }) {
  return (
    <div className="move-contributor-row">
      <span className="move-contributor-ticker">{holding.ticker}</span>
      <span className="move-contributor-return" style={{ color: moveColor(holding.returnPct ?? holding.dailyReturnPct) }}>{signedPct(holding.returnPct ?? holding.dailyReturnPct, 2)}</span>
      <span className="move-contributor-points" style={{ color: moveColor(holding.contributionPct) }}>{signedPct(holding.contributionPct, 2)} pts</span>
    </div>
  )
}

function PeriodPicker({ period, onChange }) {
  return (
    <div className="chart-zoom move-period-picker" aria-label="Attribution time range">
      {ATTRIBUTION_PERIODS.map((entry) => (
        <button
          key={entry.key}
          className={period === entry.key ? 'active' : ''}
          aria-pressed={period === entry.key}
          onClick={() => onChange(entry.key)}
        >
          {entry.label}
        </button>
      ))}
    </div>
  )
}

export default function PortfolioMoveExplanation({
  attribution,
  benchmarkLabel = 'S&P 500',
  period = '1D',
  onPeriodChange = null,
}) {
  const [expanded, setExpanded] = useState(false)
  if (!attribution) return null

  const picker = onPeriodChange ? <PeriodPicker period={period} onChange={onPeriodChange} /> : null

  if (!attribution.available) {
    return (
      <section className="card portfolio-move-explanation" aria-label="Why your portfolio moved">
        <header className="move-explanation-head">
          <span className="eyebrow">Your move, {attribution.periodPhrase || 'today'}</span>
          {picker}
        </header>
        <p className="move-unavailable">{attribution.reason}</p>
      </section>
    )
  }

  const {
    totalReturnPct, marketPct, idiosyncraticPct, benchmarkReturnPct, topContributors, topDetractors,
    sectorBreakdown, unpriced, periodPhrase, weightBasis, startDate, endDate, spanDays,
    windowTruncated, partialHoldings = [], coveragePct, pricedCount, holdingCount,
  } = attribution
  const marketShare = totalReturnPct !== 0 ? (marketPct / totalReturnPct) * 100 : null
  const isWindow = Boolean(startDate)
  const windowLabel = isWindow
    ? `${windowDate(startDate)} to ${windowDate(endDate)} - ${spanDays} calendar days of published closes`
    : null

  return (
    <section className="card portfolio-move-explanation" aria-labelledby="move-explanation-title">
      <header className="move-explanation-head">
        <div>
          <span className="eyebrow">Why your portfolio moved {periodPhrase}</span>
          <h2 id="move-explanation-title">
            <span style={{ color: moveColor(totalReturnPct) }}>{signedPct(totalReturnPct, 2)}</span> {periodPhrase}
          </h2>
        </div>
        {picker}
      </header>
      {windowLabel && <p className="move-window-label">{windowLabel}</p>}

      <div className="move-split">
        <div className="move-split-bar" aria-hidden="true">
          <span className="move-split-market" style={{ width: `${Math.min(100, Math.abs(marketShare ?? 0))}%` }} />
        </div>
        <dl className="move-split-legend">
          <div><dt>Market ({benchmarkLabel} {signedPct(benchmarkReturnPct, 2)})</dt><dd style={{ color: moveColor(marketPct) }}>{signedPct(marketPct, 2)} pts</dd></div>
          <div><dt>Stock-specific</dt><dd style={{ color: moveColor(idiosyncraticPct) }}>{signedPct(idiosyncraticPct, 2)} pts</dd></div>
        </dl>
      </div>
      <p className="move-explanation-note">
        Market is each holding's beta times {benchmarkLabel}'s move {isWindow ? 'over this window' : 'today'}; stock-specific is what's left after that.
        The two always add up to your total move exactly - this is arithmetic, not a model fit.
        {isWindow && ' One published beta is applied across the whole window, so the split is coarser the longer the window.'}
      </p>
      {isWindow && weightBasis === 'start_of_period' && (
        <p className="move-explanation-note">
          Each holding is weighted by what it was worth at the start of the window, using today's share
          count - weighting by today's prices would credit the winners twice.
        </p>
      )}
      {isWindow && weightBasis === 'current_allocation' && (
        <p className="move-explanation-note">
          Share counts or opening prices were unavailable, so holdings are weighted by today's allocation
          instead of their start-of-window value. That overstates whatever has risen since the start date.
        </p>
      )}
      {windowTruncated && (
        <p className="move-explanation-note">
          Published price history does not reach back a full {periodPhrase.replace(/^(this|these) past /, '')} - this
          covers the {spanDays} days that are available.
        </p>
      )}
      {partialHoldings.length > 0 && (
        <p className="move-explanation-note">
          Bought after the window opened and measured as if held throughout: {partialHoldings.join(', ')}.
        </p>
      )}

      {(topContributors.length > 0 || topDetractors.length > 0) && (
        <div className="move-contributors">
          {topContributors.length > 0 && (
            <div>
              <h3>Biggest contributors</h3>
              {topContributors.map((holding) => <ContributorRow key={holding.ticker} holding={holding} />)}
            </div>
          )}
          {topDetractors.length > 0 && (
            <div>
              <h3>Biggest detractors</h3>
              {topDetractors.map((holding) => <ContributorRow key={holding.ticker} holding={holding} />)}
            </div>
          )}
        </div>
      )}

      <button className="expand-button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
        {expanded ? 'Hide sector breakdown' : 'Show sector breakdown'}
      </button>
      {expanded && (
        <div className="move-sector-breakdown">
          <p className="move-explanation-note">
            Stock-specific movement grouped by sector within your own holdings - not a comparison against a market
            sector index, which this system does not fetch daily.
          </p>
          {sectorBreakdown.map((entry) => (
            <div className="move-sector-row" key={entry.sector}>
              <span>{entry.sector}</span>
              <span style={{ color: moveColor(entry.idiosyncraticContributionPct) }}>{signedPct(entry.idiosyncraticContributionPct, 2)} pts</span>
            </div>
          ))}
          {unpriced.length > 0 && (
            <p className="move-explanation-note">
              No published price {isWindow ? 'at the start of this window' : 'for today'}: {unpriced.join(', ')} - excluded
              from this breakdown, which covers {pricedCount} of {holdingCount} holdings
              ({Math.round(coveragePct)}% of portfolio value).
            </p>
          )}
          <p className="move-explanation-note">
            Catalyst attribution (linking a move to a specific headline) is not available yet.
          </p>
        </div>
      )}
    </section>
  )
}
