import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import DataTable from '../components/DataTable.jsx'
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

// Same reasoning as TREND_TONE: descriptive, not a verdict. "Stage 1" (basing) is not a sell
// and "Stage 2" (advancing) is not a buy — see swing_signals.CONTEXT_NOTE.
const STAGE_LABELS = { stage_1: 'Basing', stage_2: 'Advancing', stage_3: 'Topping', stage_4: 'Declining' }
const STAGE_TONE = { stage_1: 'neutral', stage_2: 'high', stage_3: 'watch', stage_4: 'cool' }

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
  // The model can like a name that has historically gone nowhere over a window this long.
  // Calling that "worth buying" beside a negative upside is a contradiction on the face of
  // the row, whatever the internal logic, so it is downgraded rather than explained away.
  const upsidePct = row.economics_predicted_upside_pct
  if (upsidePct != null && upsidePct <= 0) {
    return {
      label: 'Maybe', tone: 'watch',
      title: 'The model’s edge survives its cost, but over a window this long this name has '
        + 'more often than not gone nowhere or fallen, so the two disagree.',
    }
  }
  if (row.current_membership) {
    return {
      label: 'Worth buying', tone: 'high',
      title: 'Ranks inside this tier’s book, the modelled edge covers its round-trip cost, and '
        + 'this name has historically travelled upward over a window this long. A research '
        + 'filter under the assumptions on this page, not a recommendation.',
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
 * One reading-guidance sentence from the market-wide regime gate, keyed to which tier is
 * showing. Never changes a score or an eligibility gate - see market_regime.py's
 * REGIME_GATE_NOTE, which this restates for the tier actually on screen rather than making a
 * reader translate the general note themselves. Returns null rather than guessing when the
 * regime gate itself did not resolve, or when neither condition below is clearly met.
 */
function regimeHint(regimeGate, tierKey) {
  if (!regimeGate) return null
  const { breadth, hurst, vix } = regimeGate
  if (tierKey === 'S' && breadth?.above_200dma_pct >= 60 && vix?.label !== 'restrictive') {
    return 'Broad breadth and a non-restrictive VIX read currently favor this book’s '
      + 'continuation legs.'
  }
  if (tierKey === 'F' && hurst?.label === 'mean_reverting') {
    return 'The market’s current mean-reverting regime is the setting this book’s reversal '
      + 'leg and context signals were built for.'
  }
  return null
}

/**
 * The tier, in one sentence, before any number.
 *
 * The panel below it carries six statistics and the table carries a dozen columns. Neither
 * answers "should I be looking at this list at all", which is the first question and the one
 * the numbers only answer once you have combined three of them.
 */
function TierHeadline({ tier, tierKey, regimeGate }) {
  if (!tier) return null
  const clears = tier.book_clearing_cost
  const total = tier.book_count
  const none = total > 0 && clears === 0
  const hint = regimeHint(regimeGate, tierKey)
  return (
    <p className={`swing-headline${none ? ' is-warning' : ''}`} role="note">
      Hold about <b>{tier.target_hold_sessions} trading {tier.target_hold_sessions === 1 ? 'session' : 'sessions'}</b>.
      {' '}<b>{total}</b> {total === 1 ? 'name qualifies' : 'names qualify'} today.
      {total === 0 ? ' Nothing clears this tier’s gates right now.' : none
        ? ` None of them is expected to earn more than it costs to trade at this speed, so read this as a ranking rather than a shortlist.`
        : ` ${clears} of ${total} are expected to earn more than they cost to trade.`}
      {hint ? ` ${hint}` : ''}
    </p>
  )
}

/**
 * Market-wide breadth, a Hurst-exponent trend/mean-reversion read, and the VIX regime,
 * published once per run - "regime is a gate, not a trigger". Reading guidance only: nothing
 * here changes a score, an eligibility gate, or which tier's book a name belongs to, and the
 * panel says so in its own note rather than only in this comment.
 */
function RegimeGatePanel({ regimeGate }) {
  if (!regimeGate) return null
  const { breadth, hurst, vix, evidence } = regimeGate
  return (
    <section className="card swing-evidence" aria-labelledby="swing-regime-title">
      <h2 id="swing-regime-title">Market regime</h2>
      <ul className="swing-evidence-list swing-tier-econ">
        <li><b>{breadth ? `${breadth.above_200dma_pct}%` : '–'}</b>
          <span>of the universe above its 200-day average</span></li>
        <li><b>{breadth ? `${breadth.above_50dma_pct}%` : '–'}</b>
          <span>above its 50-day average</span></li>
        <li><b>{hurst ? hurst.label.replace('_', ' ') : '–'}</b>
          <span>{hurst ? `Hurst exponent ${hurst.hurst.toFixed(2)}` : 'Hurst exponent'}</span></li>
        <li><b>{vix ? vix.label : '–'}</b>
          <span>VIX regime{vix?.score != null ? ` (${vix.score})` : ''}</span></li>
      </ul>
      <p className="swing-evidence-caveat">{regimeGate.note}</p>
      {['breadth_50_200dma', 'hurst_regime', 'vix_regime'].map((key) => {
        const item = evidence?.[key]
        if (!item) return null
        return (
          <p key={key} className="swing-evidence-cite">
            <b>{item.label}:</b> {item.citation}
          </p>
        )
      })}
    </section>
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
    return <span className="mono swing-leg-missing" title="Not resolvable on this row – it contributes nothing at its declared weight, which pulls the composite toward neutral rather than rescaling the legs that did resolve.">–</span>
  }
  const announced = detail?.pead_announced_on
    ? ` · announced ${detail.pead_announced_on}, ${detail.pead_age_trading_days} sessions ago`
    : ''
  return (
    <span className={`mono${leg.z > 0 ? ' up' : leg.z < 0 ? ' down' : ''}`}
      title={`${Math.round(leg.weight * 100)}% declared weight · ${(leg.contribution >= 0 ? '+' : '')}${leg.contribution.toFixed(2)} of the composite${announced}`}>
      {z(leg.z)}
    </span>
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

export default function SwingScreen() {
  const { data, loading, error } = useData('screens/swing.json')
  const { preferences } = usePreferences()
  const [filters, setFilters] = useState({
    sector: 'all', cap: 'all', liquidity: 0, coverage: 0, membership: 'all', shortInterest: 'all',
  })
  const [tierKey, setTierKey] = useState(null)
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
  // drift apart. `defaultSortDir` is the direction that answers the question the column is
  // usually asked: best first for a score, cheapest first for a cost.
  //
  // `full` marks the columns that only appear in the detailed view. Nothing is removed by the
  // simple view, it is deferred: the plain columns are derived from the numeric ones, so the
  // simple table answers "which of these is worth my attention" and the full table answers
  // "why", which are different questions asked at different moments.
  const columns = useMemo(() => [
    {
      key: 'rank', label: 'Rank', sortValue: (row) => row.rank, defaultSortDir: 'asc',
      cell: (row) => `#${row.rank}`,
    },
    {
      key: 'ticker', label: 'Ticker', sortValue: (row) => row.ticker, defaultSortDir: 'asc',
      cell: (row) => <><b>{row.ticker}</b><span className="swing-row-name">{row.name}</span></>,
    },
    {
      key: 'verdict', label: 'Verdict', defaultSortDir: 'desc',
      hint: 'Where this row stands once ranking, eligibility and cost are combined.',
      sortValue: (row) => VERDICT_ORDER[verdictFor(row).label] ?? -1,
      cell: (row) => {
        const verdict = verdictFor(row)
        return <span className={`tier ${verdict.tone}`} title={verdict.title}>{verdict.label}</span>
      },
    },
    {
      key: 'percentile', label: 'Signal', defaultSortDir: 'desc', numeric: true, full: true,
      hint: 'Rank within this tier, in words. The exact percentile and composite z stay on the row.',
      sortValue: (row) => row.percentile,
      cell: (row) => {
        const strength = strengthFor(row.percentile)
        return (
          <span className="swing-strength-cell"
            title={`${row.percentile == null ? 'unranked' : `${row.percentile.toFixed(0)}th percentile`} in this tier · composite ${z(row.composite_z)}`}>
            <span className={`swing-strength-label ${strength.tone}`}>{strength.label}</span>
            <span className="swing-strength-track" aria-hidden="true">
              <span className={`swing-strength-fill ${strength.tone}`} style={{ width: `${strength.width}%` }} />
            </span>
          </span>
        )
      },
    },
    {
      key: 'driver', label: 'Driven by', defaultSortDir: 'asc',
      hint: 'The leg contributing most to this row’s score.',
      sortValue: (row) => topDriver(row).label,
      cell: (row) => {
        const driver = topDriver(row)
        return <span className="swing-driver" title={driver.title}>{driver.label}</span>
      },
    },
    ...(tier ? [
      {
        key: 'upside', label: 'Upside', numeric: true, defaultSortDir: 'desc',
        hint: 'How far this name usually travels over a window this long, plus the model’s '
          + 'edge, less its round-trip cost. The size comes almost entirely from the name’s '
          + 'own past travel, which is measured but is not a forecast.',
        sortValue: (row) => row.economics_predicted_upside_pct,
        cell: (row) => {
          const usual = row.economics_typical_move_pct
          const low = row.economics_usual_low_pct
          const high = row.economics_usual_high_pct
          return (
            <span className="mono swing-upside"
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
            </span>
          )
        },
      },
      {
        key: 'round_trip', label: 'Cost to trade', numeric: true, defaultSortDir: 'asc', full: true,
        hint: 'Estimated cost in bps of buying and selling this name at this book size. '
          + 'The spread term is a liquidity-tiered proxy, not a measured spread.',
        sortValue: (row) => row.economics_round_trip_bps,
        cell: (row) => (
          <span className="mono"
            title={`${row.economics_liquidity_tier || 'unknown'} liquidity tier at ${millions(row.economics_position_dollars)} per position`}>
            {row.economics_round_trip_bps == null ? '–' : row.economics_round_trip_bps.toFixed(1)}
          </span>
        ),
      },
    ] : []),
    {
      key: 'trend', label: 'Trend', defaultSortDir: 'desc',
      hint: 'Where the price sits in its own 52-week range. Descriptive context, never a '
        + 'scoring leg.',
      sortValue: (row) => row.trend?.range_position_52w ?? null,
      cell: (row) => {
        const trend = row.trend
        if (!trend) return <span className="swing-trend">–</span>
        return (
          <span className={`swing-trend ${TREND_TONE[trend.state] || 'neutral'}`}
            title={`${Math.round(trend.range_position_52w * 100)}% of the way up its 52-week range`
              + ` · ${trend.above_ma20 ? 'above' : 'below'} the 20-session average`
              + ` · ${trend.above_ma60 ? 'above' : 'below'} the 60-session average`}>
            {trend.label}
          </span>
        )
      },
    },
    {
      key: 'setup', label: 'Setup', full: true,
      hint: 'Volatility-contraction and volume context (Bollinger BandWidth squeeze, NR7, '
        + 'ATR-percentile compression, volume dry-up, 2-period RSI, a multi-week volatility '
        + 'contraction pattern). Descriptive, never a scoring leg — a coiled or thinned-out '
        + 'name is not a directional call by itself. NR7, ATR compression and VCP read a '
        + 'separate data store than the rest, so they show "–" on a name too new to the '
        + 'universe to have accrued it.',
      sortValue: (row) => (row.contraction?.bandwidth_squeeze?.squeezed ? 1 : 0)
        + (row.contraction?.volume_dry_up?.dried_up ? 1 : 0)
        + (row.contraction?.narrow_range?.is_nr7 ? 1 : 0)
        + (row.contraction?.atr_compression?.squeezed ? 1 : 0)
        + (row.contraction?.vcp?.sequentially_tightening ? 1 : 0),
      cell: (row) => {
        const setup = row.contraction
        if (!setup) return <span className="swing-trend">–</span>
        const badges = []
        if (setup.bandwidth_squeeze?.squeezed) badges.push('Squeeze')
        if (setup.narrow_range?.is_nr7) badges.push('NR7')
        if (setup.atr_compression?.squeezed) badges.push('ATR compression')
        if (setup.volume_dry_up?.dried_up) badges.push('Volume dry-up')
        if (setup.vcp?.sequentially_tightening) badges.push('VCP')
        const rsi = setup.rsi_2
        return (
          <span className="swing-trend neutral"
            title={`RSI(2): ${rsi == null ? '–' : rsi.toFixed(0)}`
              + (setup.bandwidth_squeeze
                ? ` · BandWidth ${Math.round(setup.bandwidth_squeeze.percentile_of_own_history * 100)}th pct of its own 6-month range`
                : '')
              + (setup.atr_compression
                ? ` · ATR ${Math.round(setup.atr_compression.percentile_of_own_history * 100)}th pct of its own trailing range`
                : '')
              + (setup.volume_dry_up
                ? ` · volume ${(setup.volume_dry_up.ratio_to_50d_average * 100).toFixed(0)}% of its 50-day average`
                : '')
              + (setup.vcp
                ? ` · ${setup.vcp.contraction_count} trailing monthly BandWidth checkpoints, `
                  + `${setup.vcp.sequentially_tightening ? 'each narrower than the last' : 'not sequentially narrowing'}`
                : '')}>
            {badges.length ? badges.join(', ') : '–'}
          </span>
        )
      },
    },
    {
      key: 'accumulation', label: 'Accumulation', full: true,
      hint: 'Chaikin Money Flow (accumulation vs. distribution pressure) and 20-session '
        + 'relative strength against this name’s own peer group, leave-one-out. Descriptive, '
        + 'never a scoring leg.',
      sortValue: (row) => row.context?.chaikin_money_flow?.cmf ?? null,
      cell: (row) => {
        const context = row.context
        const cmf = context?.chaikin_money_flow
        const rs = context?.sector_relative_strength
        if (!cmf && !rs) return <span className="swing-trend">–</span>
        const badges = []
        if (cmf) badges.push(cmf.accumulating ? 'Accumulating' : 'Distributing')
        if (rs?.status === 'success' && rs.relative_strength != null) {
          badges.push(rs.relative_strength > 0 ? 'RS leader' : 'RS laggard')
        }
        return (
          <span className="swing-trend neutral"
            title={(cmf ? `Chaikin Money Flow: ${cmf.cmf.toFixed(2)}` : 'Chaikin Money Flow: –')
              + (rs?.status === 'success' && rs.relative_strength != null
                ? ` · 20-day return vs. ${rs.peer_count} peers: `
                  + `${rs.relative_strength > 0 ? '+' : ''}${rs.relative_strength.toFixed(1)}pp`
                : ' · not enough peers for a relative-strength read')}>
            {badges.length ? badges.join(', ') : '–'}
          </span>
        )
      },
    },
    {
      key: 'stage', label: 'Stage', full: true,
      hint: 'An approximation of Weinstein’s four-stage cycle: price against a 150-session '
        + 'moving average and its own trailing slope. Descriptive, never a scoring leg.',
      sortValue: (row) => row.context?.weinstein_stage2?.stage ?? null,
      cell: (row) => {
        const stage = row.context?.weinstein_stage2
        if (!stage) return <span className="swing-trend">–</span>
        return (
          <span className={`swing-trend ${STAGE_TONE[stage.stage] || 'neutral'}`}
            title={`${stage.above_ma150 ? 'Above' : 'Below'} its 150-session average, which is `
              + `${stage.ma150_rising ? 'rising' : 'falling'}`
              + (stage.volume_confirmed == null ? ''
                : stage.volume_confirmed ? ' · volume confirms' : ' · volume does not confirm')}>
            {STAGE_LABELS[stage.stage] || stage.stage}
          </span>
        )
      },
    },
    {
      key: 'sector', label: 'Sector', sortValue: (row) => row.sector, defaultSortDir: 'asc', full: true,
      cell: (row) => row.sector || '–',
    },
    {
      key: 'composite_z', label: 'Composite', sortValue: (row) => row.composite_z, defaultSortDir: 'desc',
      numeric: true, full: true,
      cell: (row) => <span className="mono score-cell">{z(row.composite_z)}</span>,
    },
    ...legs.map(([key, label]) => ({
      key: `leg:${key}`, label, numeric: true, defaultSortDir: 'desc', full: true,
      hint: `${LEG_PHRASES[key] || label}: standardized score for this leg across the tier.`,
      sortValue: (row) => row.legs?.[key]?.applied ? row.legs[key].z : null,
      cell: (row) => <LegCell leg={row.legs?.[key]}
        detail={key === 'pead_drift' ? row.pead_detail : null} />,
    })),
    {
      key: 'coverage', label: 'Data', sortValue: (row) => row.coverage, defaultSortDir: 'desc',
      numeric: true, full: true,
      hint: 'Share of this tier’s declared weight that actually resolved on this row.',
      cell: (row) => <span className="mono">{pct((row.coverage || 0) * 100)}</span>,
    },
    {
      key: 'return_20d', label: '20-day', sortValue: (row) => row.raw_factors?.return_20d,
      defaultSortDir: 'desc', numeric: true, full: true,
      cell: (row) => <Move pct={row.raw_factors?.return_20d} />,
    },
    {
      key: 'liquidity', label: 'Liquidity', sortValue: (row) => row.median_dollar_volume_60d,
      defaultSortDir: 'desc', numeric: true, full: true,
      cell: (row) => <span className="mono">{millions(row.median_dollar_volume_60d)}</span>,
    },
    {
      key: 'short_interest', label: 'Short interest', full: true,
      sortValue: (row) => row.short_interest?.short_percent_of_float ?? null, defaultSortDir: 'desc',
      cell: (row) => (
        <span className={row.short_interest?.suppressed ? 'swing-suppressed-cell' : undefined}>
          {shortInterestLabel(row)}
        </span>
      ),
    },
    {
      key: 'flags', label: 'Flags', full: true,
      sortValue: (row) => (row.reason_codes || []).join(', '), defaultSortDir: 'asc',
      cell: (row) => (row.reason_codes || []).join(', ') || '–',
    },
  ], [legs, tier])

  const shown = view === 'full' ? columns : columns.filter((column) => !column.full)
  const rows = filtered

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
            names are on top. Chaikin Money Flow, an approximate Weinstein trend stage and
            20-session sector-relative strength are also published as context in the Accumulation
            and Stage columns, alongside a market-wide breadth/VIX/Hurst regime read — never a leg,
            see “How this works” below.
          </> : <>
            The five signals with real peer-reviewed support at the swing horizon, ranked cross-sectionally
            and combined into one composite: post-earnings drift, the change in analyst consensus, the
            high-volume return premium, 52-week-high proximity, and a small cost-gated prior-week reversal
            tilt. Short interest is a negative screen, not a leg. MACD crossovers, VWAP and candlestick
            patterns are deliberately absent — none of them survive data-snooping correction and costs
            in US single-stock data. A Bollinger BandWidth squeeze, NR7, ATR-percentile compression,
            volume dry-up, a multi-week volatility contraction pattern and 2-period RSI read are
            published in the Setup column as context only, not as legs: they say a name is coiled or
            thinned out, not which way it resolves, and have not been run through this composite's own
            validation. Chaikin Money Flow, an approximate Weinstein trend stage and sector-relative
            strength are published the same way in the Accumulation and Stage columns, and a
            market-wide breadth/VIX/Hurst regime read is published once for the whole screen.
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
        <TierHeadline tier={tier} tierKey={activeKey} regimeGate={data?.regime_gate} />
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
          <RegimeGatePanel regimeGate={data?.regime_gate} />
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

        <DataTable
          rows={rows}
          getKey={(row) => row.ticker}
          columns={shown}
          rowClassName={(row) => (row.short_interest?.suppressed ? 'swing-row-suppressed' : undefined)}
          className="research-table card"
          mobile={{
            variant: preferences.mobileResearchView,
            title: (row) => `#${row.rank} · ${row.ticker}`,
            subtitle: (row) => row.sector || 'Unclassified',
            fields: preferences.mobileResearchView === 'detailed' ? [
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
            ],
          }}
        />
      </>}

      {/* A <div>, not a <p> - InfoTag renders a <details> block below, and <details> inside a
          <p> is invalid HTML: the browser implicitly closes the <p> right there, silently
          splitting this into two untagged fragments and losing .disclaimer's styling on the
          second half ("Rankings are hypotheses..."). Confirmed via a real
          validateDOMNesting console warning, not a lint rule. */}
      <div className="disclaimer">
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
      </div>
    </>}
  </>
}
