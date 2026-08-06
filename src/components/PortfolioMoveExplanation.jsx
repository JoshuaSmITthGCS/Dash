import { useState } from 'react'
import { signedPct } from '../lib/formatters.js'

const moveColor = (value) => value == null ? 'var(--text-faint)' : value >= 0 ? 'var(--up)' : 'var(--down)'

function ContributorRow({ holding }) {
  return (
    <div className="move-contributor-row">
      <span className="move-contributor-ticker">{holding.ticker}</span>
      <span className="move-contributor-return" style={{ color: moveColor(holding.dailyReturnPct) }}>{signedPct(holding.dailyReturnPct, 2)}</span>
      <span className="move-contributor-points" style={{ color: moveColor(holding.contributionPct) }}>{signedPct(holding.contributionPct, 2)} pts</span>
    </div>
  )
}

export default function PortfolioMoveExplanation({ attribution, benchmarkLabel = 'S&P 500' }) {
  const [expanded, setExpanded] = useState(false)
  if (!attribution) return null
  if (!attribution.available) {
    return (
      <section className="card portfolio-move-explanation" aria-label="Why your portfolio moved">
        <span className="eyebrow">Today's move</span>
        <p className="move-unavailable">{attribution.reason}</p>
      </section>
    )
  }

  const { totalReturnPct, marketPct, idiosyncraticPct, benchmarkReturnPct, topContributors, topDetractors, sectorBreakdown, unpriced } = attribution
  const marketShare = totalReturnPct !== 0 ? (marketPct / totalReturnPct) * 100 : null

  return (
    <section className="card portfolio-move-explanation" aria-labelledby="move-explanation-title">
      <header>
        <span className="eyebrow">Why your portfolio moved today</span>
        <h2 id="move-explanation-title">
          <span style={{ color: moveColor(totalReturnPct) }}>{signedPct(totalReturnPct, 2)}</span> today
        </h2>
      </header>

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
        Market is each holding's beta times {benchmarkLabel}'s move today; stock-specific is what's left after that.
        The two always add up to your total move exactly - this is arithmetic, not a model fit.
      </p>

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
            <p className="move-explanation-note">No fresh price for today: {unpriced.join(', ')} - excluded from this breakdown.</p>
          )}
          <p className="move-explanation-note">
            Catalyst attribution (linking a move to a specific headline) is not available yet.
          </p>
        </div>
      )}
    </section>
  )
}
