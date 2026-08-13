import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import ResultCards from '../components/ResultCards.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import InfoTag from '../components/InfoTag.jsx'

// Every leg any book can carry, including the announcement return the horizon tiers added and
// which no single-book weight vector declares.
//
// Named for what they measure rather than for the literature they come from. "PEAD" and
// "52w prox." are precise and unreadable, and a column header nobody can parse is information
// that is technically present and practically absent. The paper name and the citation stay one
// tap away in the evidence panel, so nothing is lost by leading with the plain word.
const LEG_LABELS = {
  announcement_return: 'Reaction',
  pead_drift: 'Earnings',
  analyst_revision: 'Revisions',
  high_volume_premium: 'Volume',
  high_52w_proximity: '52w high',
  short_term_reversal: 'Pullback',
}

// The same legs written out, for the one-name-per-row "what is driving this" column where
// there is room for the full phrase.
const LEG_PHRASES = {
  announcement_return: 'Earnings reaction',
  pead_drift: 'Earnings surprise',
  analyst_revision: 'Analyst revisions',
  high_volume_premium: 'Volume spike',
  high_52w_proximity: 'Near 52-week high',
  short_term_reversal: 'Recent pullback',
}

// Order legs by declared weight, heaviest first, so each tier's table reads in the order its
// own composite is built rather than in the order the original five happened to be declared.
const legsFor = (weights) => Object.entries(weights || {})
  .sort(([leftKey, left], [rightKey, right]) => right - left || leftKey.localeCompare(rightKey))
  .map(([key]) => [key, LEG_LABELS[key] || key])

// The single-book fallback for a snapshot published before the horizon split, in the declared
// weight order of that book. Derived from LEG_LABELS rather than spelling the labels a second
// time, so renaming a column cannot rename it on one path and not the other.
const LEGS = legsFor({
  pead_drift: .30, analyst_revision: .25, high_volume_premium: .20,
  high_52w_proximity: .15, short_term_reversal: .10,
})

const capBucket = (value) => value >= 10e9 ? 'large' : value >= 2e9 ? 'mid' : 'small'
const z = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`
const pct = (value) => value == null ? '–' : `${Number(value).toFixed(0)}%`
const millions = (value) => value == null ? '–' : `$${(Number(value) / 1e6).toFixed(0)}M`
const bps = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(1)}`
const upside = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`

// Trend is descriptive, so it is toned by where the price sits rather than by whether that is
// good news. "At 52-week low" is not a sell and "At 52-week high" is not a buy: the score
// column is where the opinion lives, and colouring these as verdicts would quietly turn a
// context column into a second, unweighted signal.
const TREND_TONE = {
  at_high: 'high', rising: 'high', turning_up: 'neutral',
  range_bound: 'neutral', falling: 'cool', at_low: 'cool',
}

/**
 * Where a row stands, in one word, from what the screen already published.
 *
 * Nothing here is a new judgement. It restates eligibility, book membership and the cost
 * arithmetic that were already on the row as separate numeric columns a reader had to combine
 * in their head. The combination is the part people get wrong: a name at the top of the
 * composite whose round trip exceeds its expected alpha reads as the best idea on the page and
 * is the worst, and no amount of staring at two adjacent numbers makes that jump out.
 */
// Three states, ordered best-first when sorted descending.
const VERDICT_ORDER = { 'Worth buying': 2, 'Maybe': 1, 'Don’t buy': 0 }

/**
 * Three words, from what the screen already published.
 *
 * This is the one column that reads as advice, so it is worth being exact about what stands
 * behind it. It combines three things already on the row - whether the name cleared this
 * tier's gates, whether it ranks inside the book, and whether the model's edge survives its
 * own round-trip cost - and says nothing the other columns do not. It is not a
 * recommendation, it inherits every assumption in UPSIDE_NOTE, and the model behind it has no
 * out-of-sample record. The disclaimer under the table says so and must stay there.
 */
function verdictFor(row) {
  if (!row.eligibility) {
    const why = (row.reason_codes || []).join(', ')
    return {
      label: 'Don’t buy', tone: 'cool',
      title: row.short_interest?.suppressed
        ? `Screened out for short interest. ${why}`
        : `Did not clear this tier’s gates. ${why}`,
    }
  }
  // The model's own edge, before this name's historical travel is added. A name can travel a
  // long way in this much time and still be one the model has no edge on, and that is exactly
  // the case this branch exists to catch.
  const edge = row.economics_net_edge_bps
  if (edge != null && edge <= 0) {
    return {
      label: 'Don’t buy', tone: 'cool',
      title: `One round trip costs ${row.economics_round_trip_bps} bps against `
        + `${row.economics_expected_alpha_bps} bps of modelled edge over the whole hold, so the `
        + `cost eats the edge. Any upside shown is this name’s usual travel, not the model.`,
    }
  }
  if (row.current_membership) {
    return {
      label: 'Worth buying', tone: 'high',
      title: 'Ranks inside this tier’s book and the modelled edge covers its round-trip cost. '
        + 'A research filter under the assumptions on this page, not a recommendation.',
    }
  }
  return {
    label: 'Maybe', tone: 'watch',
    title: 'Clears the gates and its edge covers its cost, but it ranks below this tier’s '
      + 'entry percentile, so it is not in the book.',
  }
}

// Percentile in words. The composite is a rank of a rank, so a reader who treats its z as
// cardinal is over-reading it; a five-step word scale is closer to what the number can carry.
// The z and the percentile both stay on the row for anyone who wants them.
function strengthFor(percentile) {
  if (percentile == null) return { label: '–', tone: 'none', width: 0 }
  if (percentile >= 95) return { label: 'Very strong', tone: 'high', width: 100 }
  if (percentile >= 85) return { label: 'Strong', tone: 'high', width: 78 }
  if (percentile >= 65) return { label: 'Moderate', tone: 'neutral', width: 55 }
  if (percentile >= 40) return { label: 'Weak', tone: 'neutral', width: 32 }
  return { label: 'Very weak', tone: 'cool', width: 14 }
}

// Which leg is actually carrying the row. `contribution` is already published per leg, so this
// reads the answer rather than recomputing it.
function topDriver(row) {
  const entries = Object.entries(row.legs || {})
    .filter(([, leg]) => leg?.applied && leg.contribution > 0)
    .sort(([, left], [, right]) => right.contribution - left.contribution)
  if (!entries.length) return { label: '–', title: 'No leg is contributing positively to this row.' }
  const [key, leg] = entries[0]
  const share = entries.reduce((total, [, item]) => total + item.contribution, 0)
  return {
    label: LEG_PHRASES[key] || key,
    title: `${LEG_PHRASES[key] || key} contributes ${leg.contribution.toFixed(2)} of the composite`
      + `${share ? `, ${Math.round(100 * leg.contribution / share)}% of everything pushing this row up` : ''}.`,
  }
}

/**
 * The tier, in one sentence, before any number.
 *
 * The panel below it carries six statistics and the table carries a dozen columns. Neither
 * answers "should I be looking at this list at all", which is the first question and the one
 * the numbers only answer once you have combined three of them.
 */
function TierHeadline({ tier }) {
  if (!tier) return null
  const clears = tier.book_clearing_cost
  const total = tier.book_count
  const none = total > 0 && clears === 0
  return (
    <p className={`swing-headline${none ? ' is-warning' : ''}`} role="note">
      Hold about <b>{tier.target_hold_sessions} trading {tier.target_hold_sessions === 1 ? 'session' : 'sessions'}</b>.
      {' '}<b>{total}</b> {total === 1 ? 'name qualifies' : 'names qualify'} today.
      {total === 0 ? ' Nothing clears this tier’s gates right now.' : none
        ? ` None of them is expected to earn more than it costs to trade at this speed, so read this as a ranking rather than a shortlist.`
        : ` ${clears} of ${total} are expected to earn more than they cost to trade.`}
    </p>
  )
}

/**
 * The three horizon books, and what each one costs to run.
 *
 * The tiers are not one composite sorted three ways. Each carries only the legs whose
 * documented payoff lands inside its own holding window, so the switcher changes which columns
 * exist, not just which rows are on top. The economics line is the part worth reading twice: a
 * 3-day book pays its round trip 84 times a year and a 13-week book pays it under 4 times, which is
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
  const [view, setView] = useState('simple')

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
  //
  // `full` marks the columns that only appear in the detailed view. Nothing is removed by the
  // simple view, it is deferred: the plain columns are derived from the numeric ones, so the
  // simple table answers "which of these is worth my attention" and the full table answers
  // "why", which are different questions asked at different moments.
  const columns = useMemo(() => [
    {
      key: 'rank', label: 'Rank', get: (row) => row.rank, defaultDir: 'asc',
      cell: (row) => <td key="rank">#{row.rank}</td>,
    },
    {
      key: 'ticker', label: 'Ticker', get: (row) => row.ticker, defaultDir: 'asc',
      cell: (row) => (
        <td key="ticker"><b>{row.ticker}</b><span className="swing-row-name">{row.name}</span></td>
      ),
    },
    {
      key: 'verdict', label: 'Verdict', defaultDir: 'desc',
      hint: 'Where this row stands once ranking, eligibility and cost are combined.',
      get: (row) => VERDICT_ORDER[verdictFor(row).label] ?? -1,
      cell: (row) => {
        const verdict = verdictFor(row)
        return (
          <td key="verdict">
            <span className={`tier ${verdict.tone}`} title={verdict.title}>{verdict.label}</span>
          </td>
        )
      },
    },
    {
      key: 'percentile', label: 'Signal', defaultDir: 'desc', num: true, full: true,
      hint: 'Rank within this tier, in words. The exact percentile and composite z stay on the row.',
      get: (row) => row.percentile,
      cell: (row) => {
        const strength = strengthFor(row.percentile)
        return (
          <td key="percentile" className="swing-strength-cell"
            title={`${row.percentile == null ? 'unranked' : `${row.percentile.toFixed(0)}th percentile`} in this tier · composite ${z(row.composite_z)}`}>
            <span className={`swing-strength-label ${strength.tone}`}>{strength.label}</span>
            <span className="swing-strength-track" aria-hidden="true">
              <span className={`swing-strength-fill ${strength.tone}`} style={{ width: `${strength.width}%` }} />
            </span>
          </td>
        )
      },
    },
    {
      key: 'driver', label: 'Driven by', defaultDir: 'asc',
      hint: 'The leg contributing most to this row’s score.',
      get: (row) => topDriver(row).label,
      cell: (row) => {
        const driver = topDriver(row)
        return <td key="driver" className="swing-driver" title={driver.title}>{driver.label}</td>
      },
    },
    ...(tier ? [
      {
        key: 'upside', label: 'Upside', num: true, defaultDir: 'desc',
        hint: 'How far this name usually travels over a window this long, plus the model’s '
          + 'edge, less its round-trip cost. The size comes almost entirely from the name’s '
          + 'own past travel, which is measured but is not a forecast.',
        get: (row) => row.economics_predicted_upside_pct,
        cell: (row) => {
          const usual = row.economics_typical_move_pct
          const low = row.economics_usual_low_pct
          const high = row.economics_usual_high_pct
          return (
            <td key="upside" className="mono num swing-upside"
              title={usual == null
                ? `No usable price history over ${tier.target_hold_sessions} sessions, so this is the modelled edge alone.`
                : `Over ${tier.target_hold_sessions} sessions this name has usually moved ${upside(usual)}`
                  + ` (middle half ${upside(low)} to ${upside(high)}, up in `
                  + `${Math.round((row.economics_share_positive || 0) * 100)}% of ${row.economics_history_windows} overlapping windows).`
                  + ` Model edge adds ${bps(row.economics_net_edge_bps)} bps after a ${row.economics_round_trip_bps} bps round trip.`
                  + ` Past travel, not a forecast.`}>
              <span className={row.economics_predicted_upside_pct > 0 ? 'up' : 'down'}>
                {upside(row.economics_predicted_upside_pct)}
              </span>
              {low == null ? null : (
                <span className="swing-upside-range">{upside(low)} to {upside(high)}</span>
              )}
            </td>
          )
        },
      },
      {
        key: 'round_trip', label: 'Cost to trade', num: true, defaultDir: 'asc', full: true,
        hint: 'Estimated cost in bps of buying and selling this name at this book size. '
          + 'The spread term is a liquidity-tiered proxy, not a measured spread.',
        get: (row) => row.economics_round_trip_bps,
        cell: (row) => (
          <td key="round_trip" className="mono num"
            title={`${row.economics_liquidity_tier || 'unknown'} liquidity tier at ${millions(row.economics_position_dollars)} per position`}>
            {row.economics_round_trip_bps == null ? '–' : row.economics_round_trip_bps.toFixed(1)}
          </td>
        ),
      },
    ] : []),
    {
      key: 'trend', label: 'Trend', defaultDir: 'desc',
      hint: 'Where the price sits in its own 52-week range. Descriptive context, never a '
        + 'scoring leg.',
      get: (row) => row.trend?.range_position_52w ?? null,
      cell: (row) => {
        const trend = row.trend
        if (!trend) return <td key="trend" className="swing-trend">–</td>
        return (
          <td key="trend" className={`swing-trend ${TREND_TONE[trend.state] || 'neutral'}`}
            title={`${Math.round(trend.range_position_52w * 100)}% of the way up its 52-week range`
              + ` · ${trend.above_ma20 ? 'above' : 'below'} the 20-session average`
              + ` · ${trend.above_ma60 ? 'above' : 'below'} the 60-session average`}>
            {trend.label}
          </td>
        )
      },
    },
    {
      key: 'sector', label: 'Sector', get: (row) => row.sector, defaultDir: 'asc', full: true,
      cell: (row) => <td key="sector">{row.sector || '–'}</td>,
    },
    {
      key: 'composite_z', label: 'Composite', get: (row) => row.composite_z, defaultDir: 'desc',
      num: true, full: true,
      cell: (row) => <td key="composite_z" className="mono num score-cell">{z(row.composite_z)}</td>,
    },
    ...legs.map(([key, label]) => ({
      key: `leg:${key}`, label, num: true, defaultDir: 'desc', full: true,
      hint: `${LEG_PHRASES[key] || label}: standardized score for this leg across the tier.`,
      get: (row) => row.legs?.[key]?.applied ? row.legs[key].z : null,
      cell: (row) => <LegCell key={key} leg={row.legs?.[key]}
        detail={key === 'pead_drift' ? row.pead_detail : null} />,
    })),
    {
      key: 'coverage', label: 'Data', get: (row) => row.coverage, defaultDir: 'desc',
      num: true, full: true,
      hint: 'Share of this tier’s declared weight that actually resolved on this row.',
      cell: (row) => <td key="coverage" className="mono num">{pct((row.coverage || 0) * 100)}</td>,
    },
    {
      key: 'return_20d', label: '20-day', get: (row) => row.raw_factors?.return_20d,
      defaultDir: 'desc', num: true, full: true,
      cell: (row) => <td key="return_20d" className="num"><Move pct={row.raw_factors?.return_20d} /></td>,
    },
    {
      key: 'liquidity', label: 'Liquidity', get: (row) => row.median_dollar_volume_60d,
      defaultDir: 'desc', num: true, full: true,
      cell: (row) => <td key="liquidity" className="mono num">{millions(row.median_dollar_volume_60d)}</td>,
    },
    {
      key: 'short_interest', label: 'Short interest', full: true,
      get: (row) => row.short_interest?.short_percent_of_float ?? null, defaultDir: 'desc',
      cell: (row) => (
        <td key="short_interest" className={row.short_interest?.suppressed ? 'swing-suppressed-cell' : ''}>
          {shortInterestLabel(row)}
        </td>
      ),
    },
    {
      key: 'flags', label: 'Flags', full: true,
      get: (row) => (row.reason_codes || []).join(', '), defaultDir: 'asc',
      cell: (row) => <td key="flags">{(row.reason_codes || []).join(', ') || '–'}</td>,
    },
  ], [legs, tier])

  const shown = view === 'full' ? columns : columns.filter((column) => !column.full)

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
            Three separate books, one per holding period. Each carries only the signals that pay off
            inside its own window, so switching horizon changes which columns exist, not just which
            names are on top.
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
      <div className="result-count"><strong>{rows.length}</strong><span>rows shown</span></div>
    </div>

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {tiers ? <>
        <TierSwitcher tiers={tiers} order={tierOrder} active={activeKey} onSelect={setTierKey} />
        <TierHeadline tier={tier} />
      </> : null}

      {/* Everything that explains the model rather than the names. It was three cards deep
          before the first row, which put the method between the reader and the answer. It is
          all still here, one click away, because a screen that hides its evidence is worse
          than one that leads with it. */}
      <details className="card swing-method">
        <summary>
          <b>How this works</b>
          <span>
            {tier
              ? `The ${tier.label} book, what each leg rests on, and what it costs to trade.`
              : 'What each leg rests on, and what the book costs to trade.'}
          </span>
        </summary>
        <div className="swing-method-body">
          {tiers ? (
            <p className="swing-method-intro">
              Each horizon carries only the legs whose documented payoff lands inside its own
              holding window, at its own weights, behind its own liquidity floor, against its own
              cost budget. The 3-day book is event-triggered: a name enters it only in the sessions
              after it reports. Short interest is a negative screen, not a leg. RSI 70/30, MACD
              crossovers, Bollinger signals, VWAP, OBV and candlestick patterns are deliberately
              absent — none of them survive data-snooping correction and costs in US single-stock
              data.
            </p>
          ) : null}
          <TierEconomics tier={tier} alpha={data?.alpha_assumption} />
          <EvidencePanel data={data} legs={legs} tier={tier} />
          <CostPanel model={data?.cost_model} />
          {/* The methodology note. It was sitting between the filters and the table, which is
              the one place on the page a reader has to scroll past to reach an answer. */}
          {data?.coverage_note ? <p className="disclaimer" role="note">{data.coverage_note}</p> : null}
        </div>
      </details>

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

        <div className="swing-view-toggle">
          <span id="swing-view-label">Columns</span>
          <div role="group" aria-labelledby="swing-view-label">
            <button type="button" aria-pressed={view === 'simple'}
              className={view === 'simple' ? 'is-active' : ''} onClick={() => setView('simple')}>
              Simple
            </button>
            <button type="button" aria-pressed={view === 'full'}
              className={view === 'full' ? 'is-active' : ''} onClick={() => setView('full')}>
              Every number
            </button>
          </div>
          <span className="swing-view-note">
            {view === 'simple'
              ? 'Showing the columns that decide whether a name is worth a look. Nothing is discarded.'
              : 'Every published field, including each leg’s standardized score.'}
          </span>
        </div>

        <div className="research-table card"><table>
          <thead><tr>
            {shown.map((column) => (
              <SortHeader key={column.key} column={column} sort={sort} onSort={onSort}
                className={column.num ? 'num' : undefined} />
            ))}
          </tr></thead>
          <tbody>{rows.map((row) => (
            <tr key={row.ticker} className={row.short_interest?.suppressed ? 'swing-row-suppressed' : ''}>
              {shown.map((column) => column.cell(row))}
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
