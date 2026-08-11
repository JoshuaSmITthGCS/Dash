import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import ResultCards from '../components/ResultCards.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import InfoTag from '../components/InfoTag.jsx'

// Column order matches the declared weights in pipeline/swing_signals.py, heaviest leg
// first, so the table reads in the same order the composite is built.
const LEGS = [
  ['pead_drift', 'PEAD'],
  ['analyst_revision', 'Revision'],
  ['high_volume_premium', 'Volume'],
  ['high_52w_proximity', '52w prox.'],
  ['short_term_reversal', 'Reversal'],
]

const capBucket = (value) => value >= 10e9 ? 'large' : value >= 2e9 ? 'mid' : 'small'
const z = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`
const pct = (value) => value == null ? '–' : `${Number(value).toFixed(0)}%`
const millions = (value) => value == null ? '–' : `$${(Number(value) / 1e6).toFixed(0)}M`

/**
 * The evidence behind each leg, published by the screen itself rather than restated here.
 *
 * A composite of five signals is only as honest as its willingness to say where each one
 * comes from, how large the published effect was, and how much of the cross-section it
 * actually resolved on today. `leg_coverage` is the part that changes day to day: a
 * 30%-weighted leg resolving on 4% of the universe produces a very different screen from
 * the same leg resolving on 90%, and the two must not look identical on the page.
 */
function EvidencePanel({ data }) {
  const coverage = data?.leg_coverage || {}
  const weights = data?.weights || {}
  return (
    <section className="card swing-evidence" aria-labelledby="swing-evidence-title">
      <h2 id="swing-evidence-title">What the composite is made of</h2>
      <ul className="swing-evidence-list">
        {LEGS.map(([key]) => {
          const evidence = data?.evidence?.[key]
          if (!evidence) return null
          const resolved = coverage[key]
          return (
            <li key={key}>
              <div className="swing-evidence-head">
                <b>{evidence.label}</b>
                <span className="swing-evidence-weight">{Math.round((weights[key] || 0) * 100)}% weight</span>
                <span className="swing-evidence-horizon">{evidence.horizon} · {evidence.direction}</span>
                <span className={`swing-evidence-coverage${resolved != null && resolved < 0.25 ? ' thin' : ''}`}>
                  resolved on {resolved == null ? '–' : `${Math.round(resolved * 100)}%`} of the universe
                </span>
              </div>
              <p>{evidence.effect}</p>
              <p className="swing-evidence-cite">{evidence.citation}</p>
              <p className="swing-evidence-caveat">{evidence.caveat}</p>
            </li>
          )
        })}
      </ul>
      {data?.negative_screen && (
        <div className="swing-negative-screen">
          <b>{data.negative_screen.label}</b>
          <p>{data.negative_screen.effect} — {data.negative_screen.caveat}</p>
          <p className="swing-evidence-cite">{data.negative_screen.citation}</p>
        </div>
      )}
      {data?.decay_haircut && (
        <p className="swing-decay" role="note">
          Every effect size above is the published <b>gross</b> figure, before costs and before decay.
          {' '}{data.decay_haircut.source} measured predictor returns {Math.round(data.decay_haircut.out_of_sample * 100)}%
          {' '}lower out of sample and {Math.round(data.decay_haircut.post_publication * 100)}% lower after publication.
          {' '}{data.decay_haircut.note}
        </p>
      )}
    </section>
  )
}

function LegCell({ leg }) {
  if (!leg || !leg.applied) {
    return <td className="mono num swing-leg-missing" title="Not resolvable on this row – its weight was redistributed across the legs that were, rather than scored as zero.">–</td>
  }
  return (
    <td className={`mono num${leg.z > 0 ? ' up' : leg.z < 0 ? ' down' : ''}`}
      title={`${Math.round(leg.weight * 100)}% declared weight · ${(leg.contribution >= 0 ? '+' : '')}${leg.contribution.toFixed(2)} of the composite after renormalization`}>
      {z(leg.z)}
    </td>
  )
}

function shortInterestLabel(row) {
  const detail = row.short_interest || {}
  if (detail.suppressed) return detail.reasons.join(' · ')
  if (detail.short_percent_of_float != null) return `${(detail.short_percent_of_float * 100).toFixed(1)}% of float`
  if (detail.days_to_cover != null) return `${detail.days_to_cover.toFixed(1)} days to cover`
  return '–'
}

export default function SwingScreen() {
  const { data, loading, error } = useData('screens/swing.json')
  const { preferences } = usePreferences()
  const [filters, setFilters] = useState({
    sector: 'all', cap: 'all', liquidity: 0, coverage: 0, membership: 'all', shortInterest: 'all',
  })
  const sourceRows = data?.results || []
  const sectors = useMemo(
    () => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(),
    [sourceRows],
  )
  const rows = sourceRows
    .filter((row) => filters.sector === 'all' || row.sector === filters.sector)
    .filter((row) => filters.cap === 'all' || capBucket(row.market_cap || 0) === filters.cap)
    .filter((row) => (row.median_dollar_volume_60d || 0) >= filters.liquidity * 1e6)
    .filter((row) => (row.coverage || 0) * 100 >= filters.coverage)
    .filter((row) => filters.membership === 'all' || Boolean(row.current_membership) === (filters.membership === 'yes'))
    .filter((row) => {
      const suppressed = Boolean(row.short_interest?.suppressed)
      if (filters.shortInterest === 'exclude') return !suppressed
      if (filters.shortInterest === 'only') return suppressed
      return true
    })
  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">2 trading days – 8 weeks</span>
        <h1 className="page-title">Swing <span className="accent">signals</span></h1>
        <p className="page-sub">
          The five signals with real peer-reviewed support at the swing horizon, ranked cross-sectionally
          and combined into one composite: post-earnings drift, the change in analyst consensus, the
          high-volume return premium, 52-week-high proximity, and a small cost-gated prior-week reversal
          tilt. Short interest is a negative screen, not a leg. RSI 70/30, MACD crossovers, Bollinger
          signals, VWAP, OBV and candlestick patterns are deliberately absent — none of them survive
          data-snooping correction and costs in US single-stock data.
        </p>
      </div>
      <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
    </div>

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div>
    ) : <>
      <EvidencePanel data={data} />

      <ResponsiveControlPanel label="Filter results" title="Filter results">
        <div className="screen-filters" aria-label="Swing screen filters">
          <label>Sector<select value={filters.sector} onChange={update('sector')}>
            <option value="all">All</option>{sectors.map((sector) => <option key={sector}>{sector}</option>)}
          </select></label>
          <label>Market cap<select value={filters.cap} onChange={update('cap')}>
            <option value="all">All</option><option value="large">Large</option>
            <option value="mid">Mid</option><option value="small">Small</option>
          </select></label>
          <label>Min liquidity ($M)<input type="number" min="0" value={filters.liquidity} onChange={update('liquidity')} /></label>
          <label>Min signal coverage (%)<input type="number" min="0" max="100" value={filters.coverage} onChange={update('coverage')} /></label>
          <label>Membership<select value={filters.membership} onChange={update('membership')}>
            <option value="all">All</option><option value="yes">Members</option><option value="no">Non-members</option>
          </select></label>
          <label>Short interest<select value={filters.shortInterest} onChange={update('shortInterest')}>
            <option value="all">Show suppressed</option>
            <option value="exclude">Hide suppressed</option>
            <option value="only">Suppressed only</option>
          </select></label>
        </div>
      </ResponsiveControlPanel>

      {data?.coverage_note ? <p className="disclaimer" role="note">{data.coverage_note}</p> : null}

      {data?.status === 'unavailable' ? (
        <Empty note={`Unavailable: ${data.reason_code}`} />
      ) : !rows.length ? <Empty note="No name matches these filters." /> : <>
        <ResultCards rows={rows} getKey={(row) => row.ticker} variant={preferences.mobileResearchView}
          title={(row) => `#${row.rank} · ${row.ticker}`}
          subtitle={(row) => row.sector || 'Unclassified'}
          fields={preferences.mobileResearchView === 'detailed' ? [
            { label: 'Composite', value: (row) => z(row.composite_z) },
            { label: 'Percentile', value: (row) => row.percentile == null ? '–' : row.percentile.toFixed(0) },
            ...LEGS.map(([key, label]) => ({
              label, value: (row) => row.legs?.[key]?.applied ? z(row.legs[key].z) : '–',
            })),
            { label: 'Signal coverage', value: (row) => pct((row.coverage || 0) * 100) },
            { label: 'Short interest', value: (row) => shortInterestLabel(row) },
            { label: 'Flags', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
          ] : [
            { label: 'Composite', value: (row) => z(row.composite_z) },
            { label: 'Percentile', value: (row) => row.percentile == null ? '–' : row.percentile.toFixed(0) },
            { label: 'Signal coverage', value: (row) => pct((row.coverage || 0) * 100) },
            { label: 'Flags', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
          ]} />

        <div className="research-table card"><table>
          <thead><tr>
            <th scope="col">Rank</th><th scope="col">Ticker</th><th scope="col">Sector</th>
            <th scope="col" className="num">Composite</th><th scope="col" className="num">Percentile</th>
            {LEGS.map(([key, label]) => <th key={key} scope="col" className="num">{label}</th>)}
            <th scope="col" className="num">Coverage</th>
            <th scope="col" className="num">20-day</th>
            <th scope="col" className="num">Liquidity</th>
            <th scope="col">Short interest</th><th scope="col">Flags</th>
          </tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.ticker} className={row.short_interest?.suppressed ? 'swing-row-suppressed' : ''}>
              <td>#{row.rank}</td>
              <td><b>{row.ticker}</b><span className="swing-row-name">{row.name}</span></td>
              <td>{row.sector || '–'}</td>
              <td className="mono num score-cell">{z(row.composite_z)}</td>
              <td className="mono num">{row.percentile == null ? '–' : row.percentile.toFixed(0)}</td>
              {LEGS.map(([key]) => <LegCell key={key} leg={row.legs?.[key]} />)}
              <td className="mono num">{pct((row.coverage || 0) * 100)}</td>
              <td className="num"><Move pct={row.raw_factors?.return_20d} /></td>
              <td className="mono num">{millions(row.median_dollar_volume_60d)}</td>
              <td className={row.short_interest?.suppressed ? 'swing-suppressed-cell' : ''}>{shortInterestLabel(row)}</td>
              <td>{(row.reason_codes || []).join(', ') || '–'}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </>}

      <p className="disclaimer">
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        {' '}Scored {data?.scored_count ?? '–'} names, {data?.eligible_count ?? '–'} eligible,
        {' '}{data?.suppressed_count ?? '–'} suppressed on short interest
        {' '}({data?.published_suppressed_count ?? 0} of them shown here, ranked but ineligible, so the negative
        screen is visible rather than silent). Each leg is winsorized and z-scored across the cross-section;
        legs a row cannot fill are dropped and the remaining weights renormalized, which is what the coverage
        column reports. The reversal leg is not scored at all below
        {' '}{millions(data?.thresholds?.reversal_minimum_dollar_volume)} of median daily dollar volume — at
        swing turnover, spread is the binding cost and reversal is the most cost-constrained of these signals.
        {' '}<InfoTag label="Weights">
          <strong>Frozen starting priors</strong>
          <p>
            The weights are ordered by evidence quality at this horizon and deliberately frozen so the
            point-in-time store accumulates observations under one fixed policy. They are not measured
            optima, and no rank-IC, quantile-spread or deflated-Sharpe result backs this composite in this
            system yet — the validation harness is what will test it.
          </p>
        </InfoTag>
        {' '}Rankings are hypotheses for prospective validation, not claims of outperformance, and this is a
        research screen rather than a trade instruction.
      </p>
    </>}
  </>
}
