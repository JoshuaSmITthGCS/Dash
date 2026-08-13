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

// Every leg any book can carry, including the announcement return the horizon tiers added and
// which no single-book weight vector declares.
const LEG_LABELS = {
  announcement_return: 'Announce.',
  pead_drift: 'PEAD',
  analyst_revision: 'Revision',
  high_volume_premium: 'Volume',
  high_52w_proximity: '52w prox.',
  short_term_reversal: 'Reversal',
}

// Order legs by declared weight, heaviest first, so each tier's table reads in the order its
// own composite is built rather than in the order the original five happened to be declared.
const legsFor = (weights) => Object.entries(weights || {})
  .sort(([leftKey, left], [rightKey, right]) => right - left || leftKey.localeCompare(rightKey))
  .map(([key]) => [key, LEG_LABELS[key] || key])

const capBucket = (value) => value >= 10e9 ? 'large' : value >= 2e9 ? 'mid' : 'small'
const z = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`
const pct = (value) => value == null ? '–' : `${Number(value).toFixed(0)}%`
const millions = (value) => value == null ? '–' : `$${(Number(value) / 1e6).toFixed(0)}M`
const bps = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(1)}`

/**
 * The three horizon books, and what each one costs to run.
 *
 * The tiers are not one composite sorted three ways. Each carries only the legs whose
 * documented payoff lands inside its own holding window, so the switcher changes which columns
 * exist, not just which rows are on top. The economics line is the part worth reading twice: a
 * 3-day book pays its round trip 84 times a year and an 8-week book pays it 6 times, which is
 * the whole reason they cannot share a cost budget or a liquidity floor.
 */
function TierSwitcher({ tiers, order, active, onSelect }) {
  return (
    <div className="swing-tier-switcher" role="tablist" aria-label="Holding horizon">
      {order.map((key) => {
        const tier = tiers[key]
        if (!tier) return null
        const selected = key === active
        return (
          <button key={key} type="button" role="tab" aria-selected={selected}
            className={`swing-tier-tab${selected ? ' is-active' : ''}`}
            onClick={() => onSelect(key)}>
            <b>{tier.label}</b>
            <span className="swing-tier-horizon">{tier.horizon_label}</span>
            <span className="swing-tier-meta">
              {tier.book_count} in book · {tier.round_trips_per_year}x/yr
            </span>
          </button>
        )
      })}
    </div>
  )
}

/**
 * What this tier costs against what it assumes it can earn.
 *
 * Published together rather than separately because neither number means anything alone. The
 * alpha figure is an assumption and is labelled one here, not only in the payload: it is the
 * weakest link in every net-edge number on the page and a reader who does not know that will
 * read a cost ranking as a return forecast.
 */
function TierEconomics({ tier, alpha }) {
  if (!tier) return null
  const shortfall = tier.median_net_edge_bps != null && tier.median_net_edge_bps < 0
  return (
    <section className="card swing-evidence" aria-labelledby="swing-tier-econ-title">
      <h2 id="swing-tier-econ-title">What the {tier.label} book costs</h2>
      <p>{tier.note}</p>
      <ul className="swing-evidence-list swing-tier-econ">
        <li><b>{tier.round_trips_per_year}</b><span>round trips per year</span></li>
        <li><b>{tier.median_round_trip_bps == null ? '–' : `${tier.median_round_trip_bps} bps`}</b>
          <span>median round trip</span></li>
        <li><b>{tier.expected_alpha_bps_per_period} bps</b><span>assumed alpha per hold</span></li>
        <li className={shortfall ? 'thin' : ''}>
          <b>{bps(tier.median_net_edge_bps)} bps</b><span>median net edge</span></li>
        <li className={shortfall ? 'thin' : ''}>
          <b>{tier.book_clearing_cost}/{tier.book_count}</b><span>names clearing cost</span></li>
        <li><b>{tier.break_even_alpha_bps_per_month == null ? '–' : `${tier.break_even_alpha_bps_per_month} bps`}</b>
          <span>break-even alpha per month</span></li>
      </ul>
      {shortfall ? (
        <p className="swing-evidence-caveat" role="note">
          At this horizon the median name in the book costs more to round trip than the tier
          assumes it earns over its entire holding period. Sort on <b>Net edge</b> to find the
          names that clear, and treat the rest as a ranking of things not worth trading at this
          speed.
        </p>
      ) : null}
      {tier.required_legs?.length ? (
        <p className="swing-evidence-caveat">
          Event-triggered: a name enters only when its {tier.required_legs.join(' and ')} leg
          resolves, so turnover follows the earnings calendar rather than the trading calendar.
          {' '}{tier.trigger_unresolved_count} names are ranked but held out today for having no
          open event window.
        </p>
      ) : null}
      <p className="swing-evidence-cite">{alpha?.note}</p>
    </section>
  )
}

/**
 * The evidence behind each leg, published by the screen itself rather than restated here.
 *
 * A composite of five signals is only as honest as its willingness to say where each one
 * comes from, how large the published effect was, and how much of the cross-section it
 * actually resolved on today. `leg_coverage` is the part that changes day to day: a
 * 30%-weighted leg resolving on 4% of the universe produces a very different screen from
 * the same leg resolving on 90%, and the two must not look identical on the page.
 */
function EvidencePanel({ data, legs = LEGS, tier = null }) {
  const coverage = (tier ? tier.leg_coverage : data?.leg_coverage) || {}
  const weights = (tier ? tier.weights : data?.weights) || {}
  const capture = tier?.decay_capture || {}
  return (
    <section className="card swing-evidence" aria-labelledby="swing-evidence-title">
      <h2 id="swing-evidence-title">What the composite is made of</h2>
      <ul className="swing-evidence-list">
        {legs.map(([key]) => {
          const evidence = data?.evidence?.[key]
          if (!evidence) return null
          const resolved = coverage[key]
          const captured = capture[key]
          return (
            <li key={key}>
              <div className="swing-evidence-head">
                <b>{evidence.label}</b>
                <span className="swing-evidence-weight">{Math.round((weights[key] || 0) * 100)}% weight</span>
                <span className="swing-evidence-horizon">{evidence.horizon} · {evidence.direction}</span>
                {captured == null ? null : (
                  // The number that decides whether a leg belongs in this book at all. A leg
                  // paying 5% of its documented total inside the window is being paid for
                  // before it has delivered.
                  <span className={`swing-evidence-capture${captured < .3 ? ' thin' : ''}`}
                    title="Share of this leg's documented payoff that lands inside this tier's holding window.">
                    {Math.round(captured * 100)}% of its payoff lands in this window
                  </span>
                )}
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

function LegCell({ leg, detail }) {
  if (!leg || !leg.applied) {
    return <td className="mono num swing-leg-missing" title="Not resolvable on this row – it contributes nothing at its declared weight, which pulls the composite toward neutral rather than rescaling the legs that did resolve.">–</td>
  }
  const announced = detail?.pead_announced_on
    ? ` · announced ${detail.pead_announced_on}, ${detail.pead_age_trading_days} sessions ago`
    : ''
  return (
    <td className={`mono num${leg.z > 0 ? ' up' : leg.z < 0 ? ' down' : ''}`}
      title={`${Math.round(leg.weight * 100)}% declared weight · ${(leg.contribution >= 0 ? '+' : '')}${leg.contribution.toFixed(2)} of the composite${announced}`}>
      {z(leg.z)}
    </td>
  )
}

/**
 * What the traded book costs to turn over, from the same cost model the research score uses.
 *
 * The evidence panel above quotes gross, pre-cost effect sizes with a decay haircut beside
 * them. At a 2-to-40-session horizon the other half of that disclosure is the round trip:
 * this is the only screen here whose holding period is short enough for cost to be the thing
 * that decides whether any of it survives.
 */
function CostPanel({ model }) {
  if (!model || model.status) return null
  const sizes = Object.values(model.by_portfolio_size || {})
  const dollars = (value) => value >= 1e9 ? `$${value / 1e9}B`
    : value >= 1e6 ? `$${value / 1e6}M` : `$${(value / 1e3).toFixed(0)}k`
  return (
    <section className="card swing-evidence" aria-labelledby="swing-cost-title">
      <h2 id="swing-cost-title">What it costs to trade</h2>
      <p>
        Median <b>round-trip</b> cost for one position in the {model.book_size}-name book above the
        {' '}{model.entry_percentile}th percentile, at the canonical square-root impact law.
      </p>
      <ul className="swing-evidence-list">
        {sizes.map((size) => (
          <li key={size.portfolio_value}>
            <div className="swing-evidence-head">
              <b>{dollars(size.portfolio_value)} book</b>
              <span className="swing-evidence-horizon">{dollars(size.position_dollar_value)} per position</span>
              <span className={`swing-evidence-coverage${size.median_round_trip_bps > model.cost_ceiling_bps ? ' thin' : ''}`}>
                {size.median_round_trip_bps.toFixed(1)} bps round trip
              </span>
            </div>
          </li>
        ))}
      </ul>
      <p className="swing-evidence-caveat">
        {model.first_size_over_ceiling
          ? `Past ${dollars(model.first_size_over_ceiling)} the median round trip exceeds ${model.cost_ceiling_bps} bps, which is where this book stops fitting.`
          : `The median round trip stays under ${model.cost_ceiling_bps} bps across every size tested.`}
        {' '}{model.note}
      </p>
      <p className="swing-evidence-cite">
        Spread is a liquidity-tiered proxy, not a measured spread — no provider used here serves
        quoted or effective spreads.
      </p>
    </section>
  )
}

function shortInterestLabel(row) {
  const detail = row.short_interest || {}
  if (detail.suppressed) return detail.reasons.join(' · ')
  if (detail.short_percent_of_float != null) return `${(detail.short_percent_of_float * 100).toFixed(1)}% of float`
  if (detail.days_to_cover != null) return `${detail.days_to_cover.toFixed(1)} days to cover`
  return '–'
}

/**
 * A sortable column header.
 *
 * The sort indicator is aria-hidden and the direction is carried on `aria-sort` instead, so a
 * screen reader announces the column by its name and its sort state rather than reading a
 * triangle, and so the accessible name stays stable while the direction changes.
 */
function SortHeader({ column, sort, onSort, className }) {
  const active = sort.key === column.key
  return (
    <th scope="col" className={className}
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" className={`swing-sort${active ? ' is-active' : ''}`}
        onClick={() => onSort(column.key)}
        title={column.hint || `Sort by ${column.label}`}>
        {column.label}
        <span aria-hidden="true" className="swing-sort-caret">
          {active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  )
}

// Nulls always sort last regardless of direction. A name with no cost estimate is not the
// cheapest name in the book, and letting it sort to the top of an ascending cost column is
// exactly the reading error the cost columns exist to prevent.
const compareBy = (accessor, dir) => (left, right) => {
  const a = accessor(left)
  const b = accessor(right)
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'string' || typeof b === 'string') {
    return dir === 'asc' ? String(a).localeCompare(String(b)) : String(b).localeCompare(String(a))
  }
  return dir === 'asc' ? a - b : b - a
}

export default function SwingScreen() {
  const { data, loading, error } = useData('screens/swing.json')
  const { preferences } = usePreferences()
  const [filters, setFilters] = useState({
    sector: 'all', cap: 'all', liquidity: 0, coverage: 0, membership: 'all', shortInterest: 'all',
  })
  const [tierKey, setTierKey] = useState(null)
  const [sort, setSort] = useState({ key: 'rank', dir: 'asc' })

  // A published snapshot from before the horizon split has no `tiers`, so the single-book path
  // stays live rather than the page breaking on an older file.
  const tiers = data?.tiers && Object.keys(data.tiers).length ? data.tiers : null
  const tierOrder = (data?.tier_order || []).filter((key) => tiers?.[key])
  const activeKey = tierKey && tiers?.[tierKey] ? tierKey : (data?.default_tier || tierOrder[0])
  const tier = tiers?.[activeKey] || null
  const legs = useMemo(
    () => tier ? legsFor(tier.weights) : LEGS,
    [tier],
  )

  const sourceRows = (tier ? tier.results : data?.results) || []
  const sectors = useMemo(
    () => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(),
    [sourceRows],
  )
  const filtered = sourceRows
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

  // Every column the table can sort on, with the accessor beside the label so the two cannot
  // drift apart. `defaultDir` is the direction that answers the question the column is usually
  // asked: best first for a score, cheapest first for a cost.
  const columns = useMemo(() => [
    { key: 'rank', label: 'Rank', get: (row) => row.rank, defaultDir: 'asc' },
    { key: 'ticker', label: 'Ticker', get: (row) => row.ticker, defaultDir: 'asc' },
    { key: 'sector', label: 'Sector', get: (row) => row.sector, defaultDir: 'asc' },
    { key: 'composite_z', label: 'Composite', get: (row) => row.composite_z, defaultDir: 'desc', num: true },
    { key: 'percentile', label: 'Percentile', get: (row) => row.percentile, defaultDir: 'desc', num: true },
    ...legs.map(([key, label]) => ({
      key: `leg:${key}`, label, num: true, defaultDir: 'desc',
      get: (row) => row.legs?.[key]?.applied ? row.legs[key].z : null,
    })),
    ...(tier ? [
      {
        key: 'net_edge', label: 'Net edge', num: true, defaultDir: 'desc',
        hint: 'Assumed gross alpha over one holding period, less one round trip. '
          + 'Negative means the trade costs more than the tier assumes it earns.',
        get: (row) => row.economics_net_edge_bps,
      },
      {
        key: 'round_trip', label: 'Round trip', num: true, defaultDir: 'asc',
        hint: 'Estimated cost in bps of buying and selling this name at this book size. '
          + 'The spread term is a liquidity-tiered proxy, not a measured spread.',
        get: (row) => row.economics_round_trip_bps,
      },
    ] : []),
    { key: 'coverage', label: 'Coverage', get: (row) => row.coverage, defaultDir: 'desc', num: true },
    { key: 'return_20d', label: '20-day', get: (row) => row.raw_factors?.return_20d, defaultDir: 'desc', num: true },
    { key: 'liquidity', label: 'Liquidity', get: (row) => row.median_dollar_volume_60d, defaultDir: 'desc', num: true },
  ], [legs, tier])

  const onSort = (key) => setSort((current) => current.key === key
    ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' }
    : { key, dir: columns.find((column) => column.key === key)?.defaultDir || 'desc' })

  const active = columns.find((column) => column.key === sort.key)
  const rows = active ? [...filtered].sort(compareBy(active.get, sort.dir)) : filtered

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">{tier ? `${tier.label} · ${tier.horizon_label}` : '2 trading days – 8 weeks'}</span>
        <h1 className="page-title">Swing <span className="accent">signals</span></h1>
        <p className="page-sub">
          {tiers ? <>
            Three separately-specified books, not one composite sorted three ways. Each horizon carries
            only the legs whose documented payoff lands inside its own holding window, at its own weights,
            behind its own liquidity floor, against its own cost budget — so switching horizon changes
            which columns exist, not just which names are on top. The 3-day book is event-triggered: a
            name enters it only in the sessions after it reports. Short interest is a negative screen,
            not a leg. RSI 70/30, MACD crossovers, Bollinger signals, VWAP, OBV and candlestick patterns
            are deliberately absent — none of them survive data-snooping correction and costs in US
            single-stock data.
          </> : <>
            The five signals with real peer-reviewed support at the swing horizon, ranked cross-sectionally
            and combined into one composite: post-earnings drift, the change in analyst consensus, the
            high-volume return premium, 52-week-high proximity, and a small cost-gated prior-week reversal
            tilt. Short interest is a negative screen, not a leg. RSI 70/30, MACD crossovers, Bollinger
            signals, VWAP, OBV and candlestick patterns are deliberately absent — none of them survive
            data-snooping correction and costs in US single-stock data.
          </>}
        </p>
      </div>
      <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
    </div>

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {tiers ? <>
        <TierSwitcher tiers={tiers} order={tierOrder} active={activeKey} onSelect={setTierKey} />
        <TierEconomics tier={tier} alpha={data?.alpha_assumption} />
      </> : null}
      <EvidencePanel data={data} legs={legs} tier={tier} />
      <CostPanel model={data?.cost_model} />

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
            ...legs.map(([key, label]) => ({
              label, value: (row) => row.legs?.[key]?.applied ? z(row.legs[key].z) : '–',
            })),
            ...(tier ? [{ label: 'Net edge (bps)', value: (row) => bps(row.economics_net_edge_bps) }] : []),
            { label: 'Signal coverage', value: (row) => pct((row.coverage || 0) * 100) },
            { label: 'Short interest', value: (row) => shortInterestLabel(row) },
            { label: 'Flags', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
          ] : [
            { label: 'Composite', value: (row) => z(row.composite_z) },
            { label: 'Percentile', value: (row) => row.percentile == null ? '–' : row.percentile.toFixed(0) },
            ...(tier ? [{ label: 'Net edge (bps)', value: (row) => bps(row.economics_net_edge_bps) }] : []),
            { label: 'Signal coverage', value: (row) => pct((row.coverage || 0) * 100) },
            { label: 'Flags', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
          ]} />

        <div className="research-table card"><table>
          <thead><tr>
            {columns.map((column) => (
              <SortHeader key={column.key} column={column} sort={sort} onSort={onSort}
                className={column.num ? 'num' : undefined} />
            ))}
            <th scope="col">Short interest</th><th scope="col">Flags</th>
          </tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.ticker} className={row.short_interest?.suppressed ? 'swing-row-suppressed' : ''}>
              <td>#{row.rank}</td>
              <td><b>{row.ticker}</b><span className="swing-row-name">{row.name}</span></td>
              <td>{row.sector || '–'}</td>
              <td className="mono num score-cell">{z(row.composite_z)}</td>
              <td className="mono num">{row.percentile == null ? '–' : row.percentile.toFixed(0)}</td>
              {legs.map(([key]) => <LegCell key={key} leg={row.legs?.[key]}
                detail={key === 'pead_drift' ? row.pead_detail : null} />)}
              {tier ? <>
                <td className={`mono num${row.economics_clears_cost ? ' up' : ' down'}`}
                  title={`${row.economics_expected_alpha_bps} bps assumed alpha over ${tier.target_hold_sessions} sessions, less ${row.economics_round_trip_bps} bps round trip`}>
                  {bps(row.economics_net_edge_bps)}
                </td>
                <td className="mono num" title={`${row.economics_liquidity_tier || 'unknown'} liquidity tier at ${millions(row.economics_position_dollars)} per position`}>
                  {row.economics_round_trip_bps == null ? '–' : row.economics_round_trip_bps.toFixed(1)}
                </td>
              </> : null}
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
        screen is visible rather than silent). Each leg is standardized across the cross-section — winsorized
        and z-scored, except the earnings surprise, whose tail is heavy enough that clipping would tie a
        block of the universe at one value, so it is ranked instead. A leg a row cannot fill contributes
        nothing at its declared weight rather than rescaling the legs that did resolve, so a thin row scores
        nearer neutral and never on a wider scale; that is what the coverage column reports. The reversal leg
        is not scored at all below
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
          <p>
            This model is registered in the prospective freeze on a clock that starts 2026-09-01 and needs
            24 monthly periods. Until it reports, read this as a research filter rather than a screen with
            a record: by effective weight it is 45% technical, and this system's own as-filed measurements
            found no technical sub-signal clearing its noise standard.
          </p>
        </InfoTag>
        {' '}Rankings are hypotheses for prospective validation, not claims of outperformance, and this is a
        research screen rather than a trade instruction.
      </p>
    </>}
  </>
}
