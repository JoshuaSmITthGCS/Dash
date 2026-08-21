// Holdings-level data-quality panel (Master Remediation Prompt v3, item 5). DataStatus.jsx
// already shows freshness/provider health, but only for the pipeline as a whole -- never
// scoped to what the user actually holds. The per-ticker fields this reads (data_coverage,
// data_coverage_detail, data_quality_violations, last_polled_at) are already published by the
// pipeline for every holding via portfolio_coverage/research/screen_universe -- this is a
// presentation gap, not a missing data source.

import { freshness } from '../../components/DataStatus.jsx'

function coverageTone(pct) {
  if (pct == null) return 'unknown'
  if (pct >= 0.75) return 'good'
  if (pct >= 0.45) return 'warn'
  return 'poor'
}

export default function HoldingsDataQuality({ portfolioPositions = [] }) {
  const rows = portfolioPositions.map((position) => {
    const info = position.priceInfo
    if (!info) {
      return {
        ticker: position.ticker, resolved: false,
        coveragePct: null, coverageTone: 'unknown', age: { stale: true, label: 'no source resolved' },
        violations: [],
      }
    }
    const age = freshness(info.last_polled_at || info.data_fetched_at || info.data_as_of)
    const coveragePct = Number.isFinite(info.data_coverage) ? info.data_coverage : null
    return {
      ticker: position.ticker,
      resolved: true,
      coveragePct,
      coverageTone: coverageTone(coveragePct),
      age,
      violations: Array.isArray(info.data_quality_violations) ? info.data_quality_violations : [],
    }
  })

  if (!rows.length) return null
  const flagged = rows.filter((row) => !row.resolved || row.age.stale || row.violations.length > 0 || row.coverageTone === 'poor')

  return (
    <div className="card holdings-data-quality">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Evidence</span><h3>Holdings data quality</h3></div>
        <span className="holdings-data-quality-summary">{flagged.length === 0 ? 'All holdings current' : `${flagged.length} of ${rows.length} need attention`}</span>
      </div>
      <ul className="holdings-data-quality-list">
        {rows.map((row) => (
          <li key={row.ticker} className={row.resolved ? '' : 'unresolved'}>
            <span className="holdings-data-quality-ticker">{row.ticker}</span>
            <span className={`holdings-data-quality-coverage tone-${row.coverageTone}`}>
              {row.coveragePct == null ? 'Coverage unavailable' : `${Math.round(row.coveragePct * 100)}% coverage`}
            </span>
            <span className={row.age.stale ? 'negative' : ''}>{row.age.label}</span>
            <span className="holdings-data-quality-violations">
              {row.violations.length > 0
                ? <span className="negative" title={row.violations.join('; ')}>{row.violations.length} data quality {row.violations.length === 1 ? 'flag' : 'flags'}</span>
                : row.resolved ? 'No flags' : 'Not in the scored universe'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
