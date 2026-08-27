import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { canonicalArtifactState, confidenceOf } from '../states.js'
import { cap } from '../capability.js'
import { SCREENS_IDS } from './capabilityIds.js'
import { useRenderer } from '../useRenderer.js'
import { AuthProvider as FirebaseAuthProvider } from '../../../lib/FirebaseAuthContext.jsx'
import { useStockDetail } from '../useStockDetail.js'
import StockDetailSheet from './StockDetailSheet.jsx'
import { useWatchlist } from '../../../lib/useWatchlist.js'
import { useScreenRefresh } from '../../../lib/useScreenRefresh.js'
import { useAdvisorRefresh } from '../../../lib/useAdvisorRefresh.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { STRATEGY_SCREENS } from '../../../lib/strategyScreenConfigs.js'
import { activeThemes, rankBreakoutInProgress, rankEmergingGrowth, rankThemeExposure } from '../../../lib/researchScreens.js'

// Maps `?recipe=` to its published screen file — the twelve ranked-list families
// CAPABILITY-LEDGER.md §9 consolidates. `options` and its 7 strategies share one file family;
// the strategy sub-selector is layered in per-medium once the Options screen's own controls
// (direction/strategy selects, trade-ticket reference) are ported in Phase 2b.
const RECIPE_FILES = Object.freeze({
  swing: 'screens/swing.json',
  'fast-growth': null, // client-ranked from report.json — fetched by FastGrowthRecipe itself, see SELF_FETCHING_RECIPES
  options: 'screens/options.json',
  momentum: 'screens/momentum.json',
  'quality-value': 'screens/quality-value.json',
  earnings: 'screens/earnings-timeliness.json',
  matrix: 'screens/structural-tactical.json',
  themes: null, // sourced from advisor.json + theme-peers.json — fetched by ThemesRecipe itself, see SELF_FETCHING_RECIPES
  'early-session': 'screens/early-session.json',
  politics: 'screens/congress-trades.json',
  institutional: 'screens/institutional-13f.json',
  'inside-information': 'screens/inside-information.json',
})

export const DEFAULT_RECIPE = 'swing'

const GENERIC_FAMILY = new Set(['momentum', 'quality-value', 'earnings', 'matrix'])

// Recipes whose dataSource isn't one `screens/*.json` file the shell can resolve up front —
// each fetches its own file(s) via its own `useData(...)` call(s) and owns its own loading/
// unavailable states (using the same LOADING_IDS/UNAVAILABLE_IDS below), so the shell's generic
// file-gate (loading/unavailable) is skipped for them and they render unconditionally.
const SELF_FETCHING_RECIPES = new Set(['fast-growth', 'themes'])

// Per-recipe capabilityIds for the two states the shell renders itself (loading, and "no data at
// all"), copied verbatim from CAPABILITY-LEDGER.md §9. Recipes not listed here (institutional,
// inside-information, fast-growth, themes) have no distinct loading row in the ledger, so they
// fall back to the already-wired generic ids.
const LOADING_IDS = Object.freeze({
  swing: 'state.screens.swing-loading',
  options: 'state.screens.options-loading',
  momentum: 'state.screens.generic-loading',
  'quality-value': 'state.screens.generic-loading',
  earnings: 'state.screens.generic-loading',
  matrix: 'state.screens.generic-loading',
  politics: 'state.screens.politics-loading',
  'fast-growth': 'state.screens.fastgrowth-loading',
  themes: 'state.screens.themes-loading',
})

const UNAVAILABLE_IDS = Object.freeze({
  swing: 'state.screens.swing-snapshot-unavailable',
  options: 'state.screens.options-unavailable',
  momentum: 'state.screens.generic-unavailable',
  'quality-value': 'state.screens.generic-unavailable',
  earnings: 'state.screens.generic-unavailable',
  matrix: 'state.screens.generic-unavailable',
  politics: 'state.screens.politics-unavailable',
  institutional: 'state.screens.institutional-unavailable',
  'inside-information': 'state.screens.insideinfo-unavailable',
  'early-session': 'state.screens.earlysession-unavailable',
  'fast-growth': 'state.screens.fastgrowth-unavailable',
  themes: 'state.screens.themes-unavailable',
})

// ---------------------------------------------------------------------------------------------
// Formatting helpers — every one reads a live field off a published row, never a hardcoded number.
// ---------------------------------------------------------------------------------------------
const capBucket = (value) => value >= 10e9 ? 'large' : value >= 2e9 ? 'mid' : 'small'
const z = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}`
const pctZ = (value) => value == null ? '–' : `${Number(value).toFixed(0)}%`
const bps = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(1)}`
const upside = (value) => value == null ? '–' : `${value > 0 ? '+' : ''}${Number(value).toFixed(2)}%`
const number = (value, digits = 1) => value == null ? '–' : Number(value).toFixed(digits)
const money = (value) => value == null ? '–' : `$${Number(value).toFixed(2)}`
const dollars = (value) => value == null ? '–' : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
const pctFrac = (value, digits = 1) => value == null ? '–' : `${(value * 100).toFixed(digits)}%`
const compactMoney = (value) => {
  if (value == null) return '–'
  if (value >= 1e9) return `$${(value / 1e9).toFixed(3)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  return `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}
const dateLabel = (value) => {
  if (!value) return '–'
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
const titleCase = (value = '') => value.toLowerCase().replaceAll('_', ' ')

// Order a tier's legs by declared weight, heaviest first, so a table reads in the order its own
// composite is built rather than in the order the legs happened to be declared.
const LEG_LABELS = {
  announcement_return: 'Reaction', pead_drift: 'Earnings', analyst_revision: 'Revisions',
  high_volume_premium: 'Volume', high_52w_proximity: '52w high', short_term_reversal: 'Pullback',
}
const legsFor = (weights) => Object.entries(weights || {})
  .sort(([leftKey, left], [rightKey, right]) => right - left || leftKey.localeCompare(rightKey))
  .map(([key]) => [key, LEG_LABELS[key] || key])

// ---------------------------------------------------------------------------------------------
// Small shared primitives
// ---------------------------------------------------------------------------------------------

/** One `data-capability-id`-bearing scrollable table. Column instrumentation is one id for the
 * whole column set, per how CAPABILITY-LEDGER.md §9 declares these rows (e.g.
 * `column.screens.swing-table` covers every column together, not one id per column). */
function SimpleTable({ capId, columns, rows, getKey }) {
  return (
    <div {...cap(capId)} style={{ overflowX: 'auto' }} tabIndex={0}>
      <table>
        <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={getKey ? getKey(row, index) : index}>
              {columns.map((column) => <td key={column.key}>{column.cell(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** A cell whose leg/field could not be resolved on this row — contributes nothing at its
 * declared weight rather than rescaling the legs that did resolve. Shared across every recipe's
 * table so the same capability id marks every occurrence, matching the repeated-instance pattern
 * `WallLabel` already establishes for metric rows. */
function NotResolvable({ title }) {
  return <span {...cap('state.screens.swing-cell-not-resolvable')} title={title || 'Not resolvable on this row.'}>–</span>
}

function EmptyNote({ manifest, reason, testId }) {
  const EmptyState = manifest.components?.EmptyState
  if (EmptyState) return <EmptyState reason={reason} />
  return <p role="status" data-testid={testId}>{reason}</p>
}

function RecipeTabs({ manifest, items, active, onSelect, capId, ariaLabel }) {
  const Tabs = manifest.components?.Tabs
  if (Tabs) return <Tabs items={items} active={active} onSelect={onSelect} capId={capId} />
  return (
    <div {...cap(capId)} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => (
        <button key={item.id} type="button" role="tab" aria-selected={item.id === active}
          onClick={() => onSelect(item.id)}>
          {item.label}
        </button>
      ))}
    </div>
  )
}

/** A rerun/refresh button for the three screens (politics, institutional, inside-information)
 * whose own collector runs on a slower cron than the main research refresh. Only rendered once
 * `useScreenRefresh` reports a signed-in session — matches the source pages' own gating. */
function RerunButton({ manifest, refresh, capId, idleLabel, busyLabel, title }) {
  if (!refresh.available) return null
  const Control = manifest.components?.Control
  const label = refresh.refreshing ? busyLabel : idleLabel
  if (Control) {
    return (
      <Control as="button" capId={capId} type="button" onClick={refresh.requestRefresh} disabled={refresh.refreshing} title={title}>
        {label}
      </Control>
    )
  }
  return (
    <button type="button" {...cap(capId)} onClick={refresh.requestRefresh} disabled={refresh.refreshing} title={title}>
      {label}
    </button>
  )
}

function RefreshStatus({ refresh }) {
  if (!refresh.message) return null
  return <p role={refresh.status === 'error' ? 'alert' : 'status'}>{refresh.message}</p>
}

// =================================================================================================
// 9a — Swing
// =================================================================================================

function verdictFor(row) {
  if (!row.eligibility) return { label: 'Don’t buy', title: 'Did not clear this tier’s gates.' }
  const edge = row.economics_net_edge_bps
  if (edge != null && edge <= 0) {
    return { label: 'Don’t buy', title: `One round trip (${row.economics_round_trip_bps} bps) exceeds the modelled edge (${row.economics_expected_alpha_bps} bps).` }
  }
  const upsidePct = row.economics_predicted_upside_pct
  if (upsidePct != null && upsidePct <= 0) {
    return { label: 'Maybe', title: 'The model’s edge survives its cost, but this name has more often gone nowhere or fallen over a window this long.' }
  }
  if (row.current_membership) return { label: 'Worth buying', title: 'Ranks inside this tier’s book and the modelled edge covers its round-trip cost.' }
  return { label: 'Maybe', title: 'Clears the gates and its edge covers its cost, but ranks below this tier’s entry percentile.' }
}

function SwingRecipe({ manifest, data, searchParams, setParam }) {
  const Container = manifest.components?.Container || 'section'

  const tiers = data?.tiers && Object.keys(data.tiers).length ? data.tiers : null
  const tierOrder = (data?.tier_order || []).filter((key) => tiers?.[key])
  const tierParam = searchParams.get('tier')
  const activeKey = tierParam && tiers?.[tierParam] ? tierParam : (data?.default_tier || tierOrder[0])
  const tier = tiers?.[activeKey] || null
  const legs = useMemo(() => tier ? legsFor(tier.weights) : legsFor(data?.weights), [tier, data])

  const sector = searchParams.get('sector') || 'all'
  const cap_ = searchParams.get('cap') || 'all'
  const liquidity = Number(searchParams.get('liquidity') || 0)
  const coverage = Number(searchParams.get('coverage') || 0)
  const membership = searchParams.get('membership') || 'all'
  const shortInterest = searchParams.get('shortInterest') || 'all'
  const cols = searchParams.get('cols') === 'full' ? 'full' : 'simple'

  const sourceRows = (tier ? tier.results : data?.results) || []
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => sector === 'all' || row.sector === sector)
    .filter((row) => cap_ === 'all' || capBucket(row.market_cap || 0) === cap_)
    .filter((row) => (row.median_dollar_volume_60d || 0) >= liquidity * 1e6)
    .filter((row) => (row.coverage || 0) * 100 >= coverage)
    .filter((row) => membership === 'all' || Boolean(row.current_membership) === (membership === 'yes'))
    .filter((row) => {
      const suppressed = Boolean(row.short_interest?.suppressed)
      if (shortInterest === 'exclude') return !suppressed
      if (shortInterest === 'only') return suppressed
      return true
    })

  const columns = [
    { key: 'rank', label: 'Rank', cell: (row) => `#${row.rank}` },
    { key: 'ticker', label: 'Ticker', cell: (row) => <><b>{row.ticker}</b> {row.name}</> },
    { key: 'verdict', label: 'Verdict', cell: (row) => { const v = verdictFor(row); return <span title={v.title}>{v.label}</span> } },
    { key: 'percentile', label: 'Percentile', cell: (row) => row.percentile == null ? <NotResolvable /> : `${row.percentile.toFixed(0)}th` },
    { key: 'composite', label: 'Composite', cell: (row) => z(row.composite_z) },
    ...(tier ? [
      { key: 'upside', label: 'Upside', cell: (row) => upside(row.economics_predicted_upside_pct) },
      { key: 'net_edge', label: 'Net edge (bps)', cell: (row) => bps(row.economics_net_edge_bps) },
    ] : []),
    { key: 'sector', label: 'Sector', cell: (row) => row.sector || '–' },
    ...(cols === 'full' ? legs.map(([key, label]) => ({
      key: `leg:${key}`, label,
      cell: (row) => row.legs?.[key]?.applied ? z(row.legs[key].z) : <NotResolvable title={`${label} did not resolve on this row.`} />,
    })) : []),
    ...(cols === 'full' ? [
      { key: 'coverage', label: 'Signal coverage', cell: (row) => pctZ((row.coverage || 0) * 100) },
      { key: 'short_interest', label: 'Short interest', cell: (row) => row.short_interest?.suppressed ? (row.short_interest.reasons || []).join(', ') : (row.short_interest?.short_percent_of_float != null ? `${(row.short_interest.short_percent_of_float * 100).toFixed(1)}% of float` : '–') },
      { key: 'flags', label: 'Flags', cell: (row) => (row.reason_codes || []).join(', ') || '–' },
    ] : []),
  ]

  return (
    <>
      {tiers && (
        <RecipeTabs manifest={manifest} ariaLabel="Holding horizon" capId="nav.screens.swing-tier-tablist"
          items={tierOrder.map((key) => ({ id: key, label: tiers[key].label }))}
          active={activeKey} onSelect={(key) => setParam('tier', key)} />
      )}

      {tier && (
        <p {...cap('figure.screens.swing-tier-headline')} role="note">
          Hold about <b>{tier.target_hold_sessions}</b> trading {tier.target_hold_sessions === 1 ? 'session' : 'sessions'}.
          {' '}<b>{tier.book_count}</b> {tier.book_count === 1 ? 'name qualifies' : 'names qualify'} today,
          {' '}{tier.book_clearing_cost} of {tier.book_count} expected to earn more than they cost to trade.
        </p>
      )}

      <details {...cap('control.screens.swing-how-this-works')}>
        <summary>How this works</summary>

        {tier && (
          <section {...cap('figure.screens.swing-tier-economics')}>
            <h3>What the {tier.label} book costs</h3>
            <ul>
              <li>{tier.round_trips_per_year} round trips/yr</li>
              <li>{tier.median_round_trip_bps == null ? '–' : `${tier.median_round_trip_bps} bps`} median round trip</li>
              <li>{tier.expected_alpha_bps_per_period} bps assumed alpha per hold (an assumption, not a measured result)</li>
              <li>{bps(tier.median_net_edge_bps)} bps median net edge</li>
              <li>{tier.book_clearing_cost}/{tier.book_count} names clearing cost</li>
              <li>{tier.break_even_alpha_bps_per_month == null ? '–' : `${tier.break_even_alpha_bps_per_month} bps`} break-even alpha/month</li>
            </ul>
          </section>
        )}

        <section {...cap('figure.screens.swing-evidence-panel')}>
          <h3>What the composite is made of</h3>
          <ul>
            {legs.map(([key]) => {
              const evidence = data?.evidence?.[key]
              if (!evidence) return null
              const coverageMap = (tier ? tier.leg_coverage : data?.leg_coverage) || {}
              const weights = (tier ? tier.weights : data?.weights) || {}
              return (
                <li key={key}>
                  <b>{evidence.label}</b> — {Math.round((weights[key] || 0) * 100)}% weight, {evidence.horizon}, {evidence.direction}
                  {' '}(resolved on {coverageMap[key] == null ? '–' : `${Math.round(coverageMap[key] * 100)}%`} of the universe)
                  <p>{evidence.effect}</p>
                  <p>{evidence.citation}</p>
                  <p>{evidence.caveat}</p>
                </li>
              )
            })}
          </ul>
          {data?.negative_screen && (
            <p><b>{data.negative_screen.label}</b> — {data.negative_screen.effect} — {data.negative_screen.caveat}</p>
          )}
          {data?.decay_haircut && (
            <p {...cap('disclosure.screens.swing-decay-haircut')} role="note">
              Every effect size above is the published gross figure, before costs and decay. {data.decay_haircut.source} measured
              predictor returns {Math.round(data.decay_haircut.out_of_sample * 100)}% lower out of sample and{' '}
              {Math.round(data.decay_haircut.post_publication * 100)}% lower after publication. {data.decay_haircut.note}
            </p>
          )}
        </section>

        {data?.cost_model && !data.cost_model.status && (
          <section {...cap('figure.screens.swing-cost-panel')}>
            <h3>What it costs to trade</h3>
            <ul>
              {Object.values(data.cost_model.by_portfolio_size || {}).map((size) => (
                <li key={size.portfolio_value}>{dollars(size.portfolio_value)} book — {size.median_round_trip_bps.toFixed(1)} bps round trip</li>
              ))}
            </ul>
            <p {...cap('disclosure.screens.swing-spread-proxy')}>
              Spread is a liquidity-tiered proxy, not a measured spread — no provider used here serves quoted or effective spreads.
              Cost ceiling {data.cost_model.cost_ceiling_bps} bps. {data.cost_model.note}
            </p>
          </section>
        )}

        <p {...cap('disclosure.screens.swing-unfillable-leg')}>
          A leg a row can’t fill contributes nothing at its declared weight rather than rescaling the legs that did resolve, so a
          thin row scores nearer neutral and never on a wider scale.
        </p>

        <p {...cap('disclosure.screens.swing-absent-indicators')}>
          Deliberately absent: RSI 70/30, MACD crossovers, Bollinger signals, VWAP, OBV, and candlestick patterns — none of them
          survive data-snooping correction and costs in US single-stock data.
        </p>

        <details {...cap('disclosure.screens.swing-frozen-priors')}>
          <summary>Frozen starting priors</summary>
          <p>
            The weights are ordered by evidence quality at this horizon and deliberately frozen on a clock that starts 2026-09-01
            and needs 24 monthly periods. By effective weight this composite is 45% technical, and no technical sub-signal in this
            system has cleared its own noise standard yet.
          </p>
        </details>

        {data?.coverage_note && <p role="note">{data.coverage_note}</p>}
      </details>

      <Container {...cap('control.screens.swing-filters')}>
        <label>Sector<select value={sector} onChange={(event) => setParam('sector', event.target.value)}>
          <option value="all">All</option>{sectors.map((option) => <option key={option}>{option}</option>)}
        </select></label>
        <label>Market cap<select value={cap_} onChange={(event) => setParam('cap', event.target.value)}>
          <option value="all">All</option><option value="large">Large</option><option value="mid">Mid</option><option value="small">Small</option>
        </select></label>
        <label>Min liquidity ($M)<input type="number" min="0" value={liquidity} onChange={(event) => setParam('liquidity', event.target.value)} /></label>
        <label>Min signal coverage (%)<input type="number" min="0" max="100" value={coverage} onChange={(event) => setParam('coverage', event.target.value)} /></label>
        <label>Membership<select value={membership} onChange={(event) => setParam('membership', event.target.value)}>
          <option value="all">All</option><option value="yes">Members</option><option value="no">Non-members</option>
        </select></label>
        <label>Short interest<select value={shortInterest} onChange={(event) => setParam('shortInterest', event.target.value)}>
          <option value="all">Show suppressed</option><option value="exclude">Hide suppressed</option><option value="only">Suppressed only</option>
        </select></label>
      </Container>

      {data?.status === 'unavailable' ? (
        <p {...cap('state.screens.swing-unavailable-reason')} role="alert">Unavailable: {data.reason_code}</p>
      ) : !rows.length ? (
        <div {...cap('state.screens.swing-no-filter-match')}><EmptyNote manifest={manifest} reason="No name matches these filters." testId="swing-no-match" /></div>
      ) : (
        <>
          <div role="group" aria-label="Columns" {...cap('control.screens.swing-column-view-toggle')}>
            <button type="button" aria-pressed={cols === 'simple'} onClick={() => setParam('cols', null)}>Simple</button>
            <button type="button" aria-pressed={cols === 'full'} onClick={() => setParam('cols', 'full')}>Every number</button>
          </div>
          <SimpleTable capId="column.screens.swing-table" columns={columns} rows={rows} getKey={(row) => row.ticker} />
        </>
      )}

      <p {...cap('disclosure.screens.swing-shortfall-caveat')}>
        The median name in a tier's book can cost more to round trip than the tier assumes it earns — sort on net edge to find
        the names that clear, and treat the rest as a ranking rather than a shortlist.
      </p>

      <p {...cap('disclosure.screens.swing-footer-versions')}>
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        Scored {data?.scored_count ?? '–'} names, {data?.eligible_count ?? '–'} eligible, {data?.suppressed_count ?? '–'} suppressed
        on short interest. Rankings are hypotheses for prospective validation, not claims of outperformance, and this is a
        research screen rather than a trade instruction.
      </p>
    </>
  )
}

// =================================================================================================
// 9b — Fast Growth
// =================================================================================================

/** Tiny inline sparkline — the mobile card's own trend glance. Not a `chart.*`-class row (the
 * ledger declares this element under `figure.screens.fastgrowth-mobile-cards`), so it does not
 * go through the chart-renderer contract — same reasoning as `BarTimeline` below for politics. */
function MiniSparkline({ values, label }) {
  const usable = (values || []).filter((value) => typeof value === 'number' && Number.isFinite(value))
  if (usable.length < 2) return null
  const min = Math.min(...usable)
  const max = Math.max(...usable)
  const span = max - min || 1
  const points = usable.map((value, index) => `${(index / (usable.length - 1)) * 100},${100 - ((value - min) / span) * 100}`).join(' ')
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={label} width="100%" height="32">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function FastGrowthRecipe({ manifest, searchParams, setParam }) {
  const { data, loading } = useData('report.json')
  const { openStockDetail } = useStockDetail()
  const sub = searchParams.get('sub') === 'emerging' ? 'emerging' : 'breakout'
  const sector = searchParams.get('sector') || 'all'

  const universe = useMemo(() => [...new Map(
    [...(data?.research || []), ...(data?.screen_universe || [])].map((row) => [row.ticker, row]),
  ).values()], [data])

  const breakoutRows = useMemo(() => rankBreakoutInProgress(universe, universe.length), [universe])
  const emergingRows = useMemo(() => rankEmergingGrowth(universe, universe.length), [universe])
  const rows = sub === 'breakout' ? breakoutRows : emergingRows
  const sectors = useMemo(() => [...new Set(rows.map((row) => row.sector).filter(Boolean))].sort(), [rows])
  const filtered = sector === 'all' ? rows : rows.filter((row) => row.sector === sector)

  if (loading) return <div {...cap('state.screens.fastgrowth-loading')} role="status" aria-live="polite">Loading…</div>
  if (!data) return <div {...cap('state.screens.fastgrowth-unavailable')} role="alert">Screen snapshot unavailable.</div>

  const columns = sub === 'breakout' ? [
    { key: 'ticker', label: 'Ticker', cell: (row) => <><button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button> {row.name}</> },
    { key: 'sector', label: 'Sector', cell: (row) => row.sector || '–' },
    { key: 'week', label: '5-day return', cell: (row) => upside(row.screen.weekReturn) },
    { key: 'month', label: '20-day return', cell: (row) => upside(row.screen.monthReturn) },
    { key: 'acceleration', label: 'Acceleration', cell: (row) => upside(row.screen.acceleration) },
    { key: 'score', label: 'Score', cell: (row) => number(row.score, 1) },
  ] : [
    { key: 'ticker', label: 'Ticker', cell: (row) => <><button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button> {row.name}</> },
    { key: 'sector', label: 'Sector', cell: (row) => row.sector || '–' },
    { key: 'revenue', label: 'Revenue growth', cell: (row) => pctFrac(row.screen.revenueGrowth) },
    { key: 'relative', label: 'Relative strength', cell: (row) => upside(row.screen.relativeStrength) },
    { key: 'contracting', label: 'Vol. contracting', cell: (row) => row.screen.volatilityContracting == null ? '–' : row.screen.volatilityContracting ? 'Yes' : 'No' },
    { key: 'score', label: 'Score', cell: (row) => number(row.score, 1) },
  ]

  return (
    <>
      <div {...cap('control.screens.fastgrowth-screen-select')}>
        <label>Screen
          <select value={sub} onChange={(event) => setParam('sub', event.target.value === 'breakout' ? null : event.target.value)}>
            <option value="breakout">Breakout in progress</option>
            <option value="emerging">Emerging growth (unvalidated)</option>
          </select>
        </label>
      </div>

      {sub === 'emerging' && (
        <p {...cap('disclosure.screens.fastgrowth-unvalidated')} role="note">
          Prospective and unvalidated. No backtest, no rank-IC, no track record backs this screen — the validation
          harness has not accumulated enough prospective history to test it. It exists so that history can start
          accumulating, not because it is known to work.
        </p>
      )}

      {sectors.length > 0 && (
        <label {...cap('control.screens.fastgrowth-sector-filter')}>Sector
          <select value={sector} onChange={(event) => setParam('sector', event.target.value)}>
            <option value="all">All sectors</option>{sectors.map((option) => <option key={option}>{option}</option>)}
          </select>
        </label>
      )}

      {!filtered.length ? (
        <div {...cap(sub === 'breakout' ? 'state.screens.fastgrowth-empty-breakout' : 'state.screens.fastgrowth-empty-emerging')}>
          <EmptyNote manifest={manifest} testId="fastgrowth-empty" reason={sub === 'breakout'
            ? 'No name is accelerating sharply enough to clear this screen in the latest report.'
            : 'No name clears the emerging-growth measurables in the latest report.'} />
        </div>
      ) : (
        <>
          <SimpleTable capId={sub === 'breakout' ? 'column.screens.fastgrowth-breakout-columns' : 'column.screens.fastgrowth-emerging-columns'}
            columns={columns} rows={filtered} getKey={(row) => row.ticker} />
          <section {...cap('figure.screens.fastgrowth-mobile-cards')} aria-label="Idea cards">
            {filtered.slice(0, 10).map((row) => (
              <article key={row.ticker}>
                <button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button> · score {number(row.score, 1)}
                <MiniSparkline values={(row.history?.closes || []).slice(-22)} label={`${row.ticker} one-month daily close trend`} />
              </article>
            ))}
          </section>
        </>
      )}

      <p {...cap('disclosure.screens.fastgrowth-footer')}>
        {sub === 'breakout'
          ? 'A breakout screen flags a change in pace, not a guaranteed continuation — a sharp run can just as easily fade or reverse the following week.'
          : 'An emerging-growth screen flags currently-measurable conditions with no proven predictive track record in this system.'}
        {' '}This is a research screen, not a trade instruction; confirm current price, liquidity, news, and your own risk limits before acting.
      </p>
    </>
  )
}

// =================================================================================================
// 9c — Options + 7 strategies
// =================================================================================================

const OPTIONS_SUB_NAV = [
  { id: null, label: 'Multi-day' },
  { id: 'short-term-trades', label: 'Short-term' },
  { id: 'covered-call', label: 'Covered call' },
  { id: 'cash-secured-put', label: 'Cash-secured put' },
  { id: 'protective-put', label: 'Protective put' },
  { id: 'collar', label: 'Collar' },
  { id: 'vertical-spread', label: 'Vertical spread' },
  { id: 'advanced-strategies', label: 'Advanced' },
]

function TradeTicket({ row }) {
  const legs = row.legs || []
  if (!legs.length) return null
  return (
    <details {...cap('control.screens.options-trade-ticket')}>
      <summary>How to enter this in your broker</summary>
      {legs.map((leg, index) => (
        <p key={index}>
          {leg.action === 'buy' ? 'Buy' : 'Sell'} to open · Qty 1 · Exp {dateLabel(row.expiration)} · Strike {money(leg.strike)} ·{' '}
          {leg.option_type} — Bid {money(leg.bid)} · Mid {money(leg.mid)} · Ask {money(leg.ask)}
        </p>
      ))}
      <p>Order type: Limit · Price: {legs.length === 1 ? money(legs[0].mid) : 'Net of leg mids'} · Time in force: Day</p>
    </details>
  )
}

function OptionsRecipe({ manifest, data, searchParams, setParam }) {
  const { openStockDetail } = useStockDetail()
  const strategyId = searchParams.get('strategy')
  const strategyConfig = strategyId && STRATEGY_SCREENS[strategyId] ? STRATEGY_SCREENS[strategyId] : null
  const { data: strategyData } = useData(strategyConfig?.file || null)
  const activeData = strategyConfig ? strategyData : data

  const direction = searchParams.get('direction') || 'all'
  const sector = searchParams.get('sector') || 'all'
  const strategyFilter = searchParams.get('sub') || 'all'

  const sourceRows = (activeData?.results || []).filter((row) => row.eligibility)
  const strategies = useMemo(() => [...new Set(sourceRows.map((row) => row.strategy).filter(Boolean))], [sourceRows])
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => strategyConfig ? true : (direction === 'all' || row.option_type === direction))
    .filter((row) => sector === 'all' || row.sector === sector)
    .filter((row) => strategyFilter === 'all' || row.strategy === strategyFilter)

  const { isWatched } = useWatchlist()

  const { data: backtestData } = useData(strategyConfig?.backtestFile || null)
  const backtestStats = strategyConfig?.backtestStrategyKeys
    ? null
    : (backtestData?.status === 'success' ? backtestData.backtest : null)

  // Cross-strategy comparison — index only (`?recipe=options`, no `&strategy=`), per
  // CAPABILITY-LEDGER.md §9c's selector column.
  const isIndex = !strategyConfig
  const { data: optionsBacktest } = useData(isIndex ? 'screens/options-backtest.json' : null)
  const { data: shortTermBacktest } = useData(isIndex ? 'screens/short-term-trades-backtest.json' : null)
  const { data: coveredCallBacktest } = useData(isIndex ? 'screens/covered-calls-backtest.json' : null)
  const { data: cspBacktest } = useData(isIndex ? 'screens/cash-secured-puts-backtest.json' : null)
  const { data: protectivePutBacktest } = useData(isIndex ? 'screens/protective-puts-backtest.json' : null)
  const { data: collarBacktest } = useData(isIndex ? 'screens/collars-backtest.json' : null)
  const { data: verticalBacktest } = useData(isIndex ? 'screens/vertical-spreads-backtest.json' : null)
  const { data: advancedBacktest } = useData(isIndex ? 'screens/advanced-strategies-backtest.json' : null)
  const crossStrategyRows = isIndex ? [
    ['Multi-day options', optionsBacktest],
    ['Short-term trades', shortTermBacktest],
    ['Covered call', coveredCallBacktest],
    ['Cash-secured put', cspBacktest],
    ['Protective put', protectivePutBacktest],
    ['Collar', collarBacktest],
    ['Vertical spread', verticalBacktest],
    ['Iron condor', advancedBacktest ? { ...advancedBacktest, backtest: advancedBacktest.backtest?.iron_condor } : null],
    ['Straddle', advancedBacktest ? { ...advancedBacktest, backtest: advancedBacktest.backtest?.straddle } : null],
  ].map(([label, source]) => ({
    label, annualizedReturn: source?.status === 'success' ? source.backtest?.annualized_return : null,
  })).filter((row) => row.annualizedReturn != null) : []

  const columns = [
    { key: 'rank', label: 'Rank', cell: (row) => `#${row.rank}` },
    { key: 'ticker', label: 'Ticker', cell: (row) => <button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button> },
    { key: 'sector', label: 'Sector', cell: (row) => row.sector || '–' },
    { key: 'side', label: strategyConfig ? 'Strategy' : 'Side', cell: (row) => strategyConfig ? (strategyConfig.strategyLabel(row)) : (row.option_type === 'put' ? 'Put' : 'Call') },
    { key: 'legs', label: 'Strike/legs', cell: (row) => row.legs?.length ? row.legs.map((leg) => `${leg.action === 'buy' ? 'Buy' : 'Sell'} ${leg.option_type} ${money(leg.strike)}`).join(' · ') : money(row.strike) },
    { key: 'expiration', label: 'Expiration', cell: (row) => dateLabel(row.expiration) },
    { key: 'dte', label: 'DTE', cell: (row) => row.days_to_expiration ?? '–' },
    { key: 'iv', label: 'IV', cell: (row) => pctFrac(row.implied_volatility) },
    { key: 'iv_rv', label: 'IV / RV', cell: (row) => row.implied_realized_vol_ratio != null ? `${number(row.implied_realized_vol_ratio, 2)}×` : '–' },
    { key: 'spread', label: 'Spread', cell: (row) => pctFrac(row.spread_pct) },
    { key: 'oi', label: 'Open interest', cell: (row) => row.open_interest ?? '–' },
    { key: 'capital', label: 'Capital required', cell: (row) => dollars(row.capital_required) },
    { key: 'score', label: 'Score', cell: (row) => number(row.score, 2) },
    {
      key: 'watchlist', label: 'Watchlist', cell: (row) => (
        <button type="button" {...cap('control.screens.options-watchlist-toggle')}
          aria-pressed={isWatched(row.ticker)}>
          {isWatched(row.ticker) ? 'Watching' : 'Watch'}
        </button>
      ),
    },
  ]

  const status = activeData?.status
  const reasonBlock = status === 'unavailable' ? (
    status && activeData.reason_code === 'YFINANCE_UNAVAILABLE' ? (
      <p {...cap('state.screens.options-chain-unavailable')} role="alert">Options-chain data is unavailable in this snapshot.</p>
    ) : (
      <p {...cap('state.screens.options-no-clearing-ticker')} role="alert">No ticker currently clears this screen. Check back after the next data refresh.</p>
    )
  ) : null

  return (
    <>
      <RecipeTabs manifest={manifest} ariaLabel="Options strategies" capId="nav.screens.options-sub-nav"
        items={OPTIONS_SUB_NAV.map((item) => ({ id: item.id || 'index', label: item.label }))}
        active={strategyId || 'index'}
        onSelect={(id) => setParam('strategy', id === 'index' ? null : id)} />

      <p {...cap('disclosure.screens.options-not-instruction')} role="note">
        Research screen, not a trade instruction. Options carry leverage, time decay, and can expire worthless. Confirm live
        bid/ask, open interest, and your own risk limits in your broker before acting on anything here.
      </p>

      {strategyConfig && backtestStats && (
        <section {...cap('figure.screens.options-backtest-summary')}>
          <h3>Example performance (simulated) — {strategyConfig.title}</h3>
          <p>Annualized return {pctFrac(backtestStats.annualized_return)} · Sharpe {number(backtestStats.sharpe_ratio, 2)} ·
            {' '}win rate {pctFrac(backtestStats.win_rate)} · {backtestStats.num_trades} trades</p>
        </section>
      )}

      {isIndex && crossStrategyRows.length >= 2 && (
        <section {...cap('figure.screens.options-cross-strategy-comparison')}>
          <h3>Simulated annualized return across every options strategy backtest</h3>
          <ul>
            {crossStrategyRows.map((row) => <li key={row.label}>{row.label}: {pctFrac(row.annualizedReturn)}</li>)}
          </ul>
        </section>
      )}

      <div>
        {!strategyConfig && (
          <label {...cap('control.screens.options-direction-select')}>Direction
            <select value={direction} onChange={(event) => setParam('direction', event.target.value === 'all' ? null : event.target.value)}>
              <option value="all">Calls &amp; puts</option><option value="call">Calls only</option><option value="put">Puts only</option>
            </select>
          </label>
        )}
        {strategies.length > 1 && (
          <label {...cap('control.screens.options-strategy-select')}>Strategy
            <select value={strategyFilter} onChange={(event) => setParam('sub', event.target.value === 'all' ? null : event.target.value)}>
              <option value="all">All strategies</option>
              {strategies.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        )}
        <label {...cap('control.screens.options-sector-filter')}>Sector
          <select value={sector} onChange={(event) => setParam('sector', event.target.value === 'all' ? null : event.target.value)}>
            <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      </div>

      {reasonBlock}
      {!reasonBlock && !rows.length && (
        <div {...cap('state.screens.options-no-filter-match')}><EmptyNote manifest={manifest} reason="No candidate matches the current filters." testId="options-no-match" /></div>
      )}
      {!reasonBlock && rows.length > 0 && (
        <>
          <SimpleTable capId="column.screens.options-table" columns={columns} rows={rows}
            getKey={(row) => `${row.ticker}-${row.strategy || row.option_type || ''}-${row.strike || ''}-${row.expiration}`} />

          <section {...cap('figure.screens.options-mobile-cards')} aria-label="Idea cards">
            {rows.slice(0, 10).map((row) => (
              <article key={`${row.ticker}-${row.rank}`}>
                <button type="button" onClick={() => openStockDetail(row.ticker)}><b>{row.ticker}</b></button> #{row.rank} · score {number(row.score, 2)}
                <div role="progressbar" aria-valuenow={row.confidence != null ? Math.round(row.confidence * 100) : 0} aria-valuemin={0} aria-valuemax={100}>
                  Confidence {row.confidence != null ? `${Math.round(row.confidence * 100)}%` : '–'}
                </div>
                <TradeTicket row={row} />
              </article>
            ))}
          </section>
        </>
      )}

      <p {...cap('disclosure.screens.options-footer')}>
        Schema {activeData?.schema_version || '–'} · model {activeData?.model_version || '–'} · config {activeData?.config_version || '–'}.
        IV, spreads, and open interest are snapshots from the last pipeline run. Delta and probability figures use a
        Black-Scholes model with the risk-free rate held at 0%, a stated simplification, not a quote-derived one.
      </p>
    </>
  )
}

// =================================================================================================
// 9d — Generic ResearchScreen family: momentum, quality-value, earnings timeliness, matrix
// =================================================================================================

// Structural-vs-tactical is the axis pair every generic recipe's rows carry (momentum,
// quality-value, earnings-timeliness, structural-tactical all publish structural_score/
// tactical_score). Tone follows the model's own classification, not a re-derived threshold —
// copied verbatim from the legacy src/pages/ResearchScreen.jsx, which this medium may not import.
const CLASSIFICATION_TONE = {
  'high-conviction candidate': 'high', 'quality company, wait': 'watch',
  'tactical-only candidate': 'neutral', avoid: 'cool',
}
const CLASSIFICATION_LEGEND = [
  { tone: 'high', label: 'High-conviction candidate' }, { tone: 'watch', label: 'Quality company, wait' },
  { tone: 'neutral', label: 'Tactical-only candidate' }, { tone: 'cool', label: 'Avoid' },
]
function median(values) {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

function GenericRecipe({ manifest, recipe, data, searchParams, setParam }) {
  const renderer = useRenderer()
  const sector = searchParams.get('sector') || 'all'
  const cap_ = searchParams.get('cap') || 'all'
  const confidence = Number(searchParams.get('confidence') || 0)
  const liquidity = Number(searchParams.get('liquidity') || 0)
  const structural = Number(searchParams.get('structural') || 0)
  const tactical = Number(searchParams.get('tactical') || 0)
  const membership = searchParams.get('membership') || 'all'

  const seenTickers = new Set()
  const sourceRows = (data?.results || []).filter((row) => {
    if (seenTickers.has(row.ticker)) return false
    seenTickers.add(row.ticker)
    return true
  })
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => sector === 'all' || row.sector === sector)
    .filter((row) => cap_ === 'all' || capBucket(row.market_cap || 0) === cap_)
    .filter((row) => (row.confidence || 0) * 100 >= confidence)
    .filter((row) => (row.median_dollar_volume_60d || 0) >= liquidity * 1e6)
    .filter((row) => (row.structural_score || 0) >= structural && (row.tactical_score || 0) >= tactical)
    .filter((row) => membership === 'all' || Boolean(row.current_membership) === (membership === 'yes'))

  const columns = [
    { key: 'rank', label: 'Rank', cell: (row) => `#${row.rank ?? '–'}` },
    { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker}</b> },
    { key: 'classification', label: 'Classification', cell: (row) => row.classification || (row.eligibility ? 'Eligible' : 'Ineligible') },
    { key: 'peer_group', label: 'Peer group', cell: (row) => row.peer_group || '–' },
    { key: 'percentile', label: 'Percentile', cell: (row) => number(row.percentile) },
    { key: 'structural', label: 'Structural', cell: (row) => number(row.structural_score) },
    { key: 'tactical', label: 'Tactical', cell: (row) => number(row.tactical_score) },
    { key: 'confidence', label: 'Confidence', cell: (row) => `${number((row.confidence || 0) * 100)}%` },
    { key: 'warnings', label: 'Warnings', cell: (row) => (row.reason_codes || []).join(', ') || 'None' },
  ]

  return (
    <>
      {(() => {
        const scatterRows = rows.filter((row) => row.structural_score != null && row.tactical_score != null)
        if (!scatterRows.length || !renderer) return null
        const structuralMedian = median(scatterRows.map((row) => row.structural_score))
        const tacticalMedian = median(scatterRows.map((row) => row.tactical_score))
        return (
          <div {...cap('chart.screens.generic-quadrant-scatter')} aria-label="Structural versus tactical score">
            {renderer.scatter({
              metricId: `screens-${recipe}-quadrant-scatter`,
              series: scatterRows.map((row) => ({
                x: row.structural_score, y: row.tactical_score,
                tone: CLASSIFICATION_TONE[row.classification], label: row.ticker, id: row.ticker,
              })),
              domain: null, unit: '',
              thresholds: [
                { value: structuralMedian, label: 'Median structural', kind: 'band', axis: 'x' },
                { value: tacticalMedian, label: 'Median tactical', kind: 'band', axis: 'y' },
              ],
              annotations: [],
              state: canonicalArtifactState(data),
              confidence: confidenceOf({}),
              ariaLabel: 'Structural score versus tactical score, one point per name, split at the median of each',
              width: 480, height: 360,
              // Extra fields beyond CHART_COMMON_PROP_KEYS — Classic's scatter() renderer forwards
              // these to ScatterChartImpl (a real, already-tested component that natively supports
              // them); the other 11 mediums' scatter() functions ignore unknown keys harmlessly for
              // now (a documented trade-off, not a bug — cross-medium tone-color parity is a future
              // item).
              quadrant: { x: structuralMedian, y: tacticalMedian },
              legend: CLASSIFICATION_LEGEND,
              xLabel: 'Structural', yLabel: 'Tactical',
            })}
          </div>
        )
      })()}

      <div {...cap('control.screens.generic-filters')}>
        <label>Sector<select value={sector} onChange={(event) => setParam('sector', event.target.value)}>
          <option value="all">All</option>{sectors.map((option) => <option key={option}>{option}</option>)}
        </select></label>
        <label>Market cap<select value={cap_} onChange={(event) => setParam('cap', event.target.value)}>
          <option value="all">All</option><option value="large">Large</option><option value="mid">Mid</option><option value="small">Small</option>
        </select></label>
        <label>Min confidence<input type="number" min="0" max="100" value={confidence} onChange={(event) => setParam('confidence', event.target.value)} /></label>
        <label>Min liquidity ($M)<input type="number" min="0" value={liquidity} onChange={(event) => setParam('liquidity', event.target.value)} /></label>
        <label>Min structural<input type="number" min="0" max="100" value={structural} onChange={(event) => setParam('structural', event.target.value)} /></label>
        <label>Min tactical<input type="number" min="0" max="100" value={tactical} onChange={(event) => setParam('tactical', event.target.value)} /></label>
        <label>Membership<select value={membership} onChange={(event) => setParam('membership', event.target.value)}>
          <option value="all">All</option><option value="yes">Members</option><option value="no">Non-members</option>
        </select></label>
      </div>

      {data?.coverage_note && <p {...cap('disclosure.screens.generic-coverage-note')} role="note">{data.coverage_note}</p>}
      {recipe === 'quality-value' && (
        <p {...cap('disclosure.screens.quality-value-window-note')}>
          Each row's own-history window is only as deep as the collected point-in-time record — every row publishes its window.
        </p>
      )}

      {data?.status === 'unavailable' ? (
        <p {...cap('state.screens.generic-reason-code')} role="alert">Unavailable: {data.reason_code}</p>
      ) : !rows.length ? (
        <div {...cap('state.screens.generic-no-filter-match')}><EmptyNote manifest={manifest} reason="No results match these filters." testId="generic-no-match" /></div>
      ) : (
        <>
          <SimpleTable capId="column.screens.generic-table" columns={columns} rows={rows} getKey={(row) => row.ticker} />
          <section {...cap('figure.screens.generic-mobile-card')} aria-label="Result cards">
            {rows.slice(0, 10).map((row) => (
              <article key={row.ticker}>
                <b>#{row.rank ?? '–'} · {row.ticker}</b>
                <div>{row.classification || (row.eligibility ? 'Eligible' : 'Ineligible')} · confidence {number((row.confidence || 0) * 100)}%</div>
              </article>
            ))}
          </section>
        </>
      )}

      <p {...cap('disclosure.screens.generic-footer')}>
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        Rankings are hypotheses for prospective validation, not claims of outperformance.
      </p>
    </>
  )
}

// =================================================================================================
// 9e — Theme Exposure
// =================================================================================================

const THEME_CROSS_MINIMUM = 2
const THEME_CROSS_LIMIT = 15

// Which structural trends each company clears the guardrails on, across every theme it was
// scored against — reimplemented locally from `theme_screen.by_ticker` because the legacy
// version of this (`crossThemeNames`) lives in `src/pages/ThemeExposureScreen.jsx`, which this
// medium may not import from. Same rule as that original: a crossing is only as strong as its
// thinnest leg, so `weakestConfidence` takes the minimum, not the average.
function crossThemeCompanies(byTicker = {}) {
  return Object.entries(byTicker)
    .map(([ticker, entries]) => {
      const eligible = (entries || []).filter((entry) => entry.eligible)
      const scores = eligible.map((entry) => entry.opportunity_score).filter((value) => Number.isFinite(value))
      const confidences = eligible.map((entry) => entry.confidence).filter((value) => Number.isFinite(value))
      return {
        ticker, themes: eligible, themeCount: eligible.length,
        bestOpportunity: scores.length ? Math.max(...scores) : null,
        weakestConfidence: confidences.length ? Math.min(...confidences) : null,
      }
    })
    .filter((row) => row.themeCount >= THEME_CROSS_MINIMUM)
    .sort((left, right) => (right.themeCount - left.themeCount) || ((right.bestOpportunity ?? -1) - (left.bestOpportunity ?? -1)))
    .slice(0, THEME_CROSS_LIMIT)
}

const THEME_ROLE_LABELS = {
  root: 'Root', enabler: 'Enabler', supplier: 'Supplier', infrastructure: 'Infrastructure', service: 'Service',
}
const THEME_SOURCE_LABELS = { published_leader: 'Published leader', portfolio: 'Your holding', sector_peer: 'Sector-connected' }
const THEME_VERDICT_RANK = ['broadening', 'narrow leadership', 'strong but already priced', 'mixed', 'cooling', 'unmeasured']

function themesByTrend(left, right) {
  const rank = (theme) => { const index = THEME_VERDICT_RANK.indexOf(theme.trend?.verdict?.label); return index === -1 ? THEME_VERDICT_RANK.length : index }
  const strength = (theme) => theme.trend?.direction?.relative_strength_median ?? -Infinity
  return (rank(left) - rank(right)) || (strength(right) - strength(left))
}

function GroupCount({ shown, total }) {
  if (!total || total <= shown) return null
  return <span>Showing {shown} of {total}</span>
}

function ThemeRowsTable({ rows, openStockDetail }) {
  return (
    <SimpleTable columns={[
      { key: 'ticker', label: 'Ticker', cell: (row) => <><button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button> {row.name}{row.candidate_source ? ` (${THEME_SOURCE_LABELS[row.candidate_source] || row.candidate_source})` : ''}</> },
      { key: 'industry', label: 'Industry', cell: (row) => row.industry || row.sector || '–' },
      { key: 'why', label: 'Why it is here', cell: (row) => (row.why || [])[0] || '–' },
      { key: 'exposure', label: 'Exposure', cell: (row) => number(row.theme_exposure_score, 0) },
      { key: 'opportunity', label: 'Opportunity', cell: (row) => number(row.opportunity_score, 0) },
      { key: 'leading', label: 'Leading signals', cell: (row) => (row.leading_signals_fired || []).length || '–' },
      { key: 'role', label: 'Role in chain', cell: (row) => row.role ? (THEME_ROLE_LABELS[row.role] || row.role) : '–' },
      { key: 'eligible', label: 'Eligible', cell: (row) => row.eligible ? 'Yes' : 'No' },
    ]} rows={rows} getKey={(row) => row.ticker} />
  )
}

function ThemeTrendBlock({ trend }) {
  if (!trend) return null
  const verdict = trend.verdict || {}
  if (verdict.label === 'unmeasured') return <p>{verdict.summary}</p>
  const { direction = {}, breadth = {}, crowding = {}, roles = [] } = trend
  return (
    <div>
      <p><b>Trend: {verdict.label}</b> — {verdict.summary}</p>
      <ul>
        <li>Leading the market by {direction.relative_strength_median == null ? '–' : `${direction.relative_strength_median > 0 ? '+' : ''}${direction.relative_strength_median}`} (median member vs. benchmark)</li>
        <li>{breadth.outperforming_share == null ? '–' : `${Math.round(breadth.outperforming_share * 100)}%`} of members participating</li>
        <li>Already priced: {crowding.already_priced == null ? '–' : crowding.already_priced ? 'Yes' : 'No'} (median member at the {crowding.expensiveness_percentile_median ?? '–'}th expensiveness percentile of its sector)</li>
      </ul>
      {roles.length > 1 && (
        <div>
          <h4>Where the money is arriving in the chain</h4>
          <ul>
            {roles.map((role) => (
              <li key={role.role}>{THEME_ROLE_LABELS[role.role] || role.role}: {role.relative_strength_median == null ? '–' : `${role.relative_strength_median > 0 ? '+' : ''}${role.relative_strength_median}`}
                {' '}({role.members} {role.members === 1 ? 'name' : 'names'})</li>
            ))}
          </ul>
          <p {...cap('disclosure.screens.themes-supply-chain-note')}>
            Median relative strength per stage of the supply chain. A rotation shows up here — money moving from the
            root outward, or the reverse — before it registers as a sector move.
          </p>
        </div>
      )}
    </div>
  )
}

function ThemesRecipe({ manifest }) {
  const { data, loading, reload } = useData('advisor.json')
  const { data: peerScreen } = useData('theme-peers.json')
  const [hideHoldings, setHideHoldings] = useState(false)
  const { positions } = useFirebasePortfolio()
  const { openStockDetail } = useStockDetail()

  const holdings = useMemo(() => new Set((positions || []).map((position) => String(position.ticker || '').toUpperCase())), [positions])
  const themeScreen = data?.theme_screen
  const themes = useMemo(() => activeThemes(themeScreen), [themeScreen])
  const themeTickers = useMemo(() => Object.keys(themeScreen?.by_ticker || {}), [themeScreen])
  const refresh = useAdvisorRefresh(data?.generated_at, reload, [...holdings], themeTickers)

  const visible = (rows) => hideHoldings ? rows.filter((row) => !holdings.has(String(row.ticker || '').toUpperCase())) : rows
  const crossTheme = useMemo(() => visible(crossThemeCompanies(themeScreen?.by_ticker || {})), [themeScreen, hideHoldings, holdings])
  const indexThemes = peerScreen?.themes?.length ? peerScreen.themes : themes

  if (loading) return <div {...cap('state.screens.themes-loading')} role="status" aria-live="polite">Loading…</div>
  if (!data) return <div {...cap('state.screens.themes-unavailable')} role="alert">Theme screen unavailable.</div>
  if (!themes.length) {
    return (
      <div {...cap('state.screens.themes-unavailable-reason')}>
        <EmptyNote manifest={manifest} testId="themes-empty" reason={themeScreen?.unavailable_reason || 'No theme produced scored exposures in the latest report.'} />
      </div>
    )
  }

  return (
    <>
      <div>
        {refresh.available && (
          <button type="button" {...cap('action.screens.themes-rerank-button')}
            onClick={refresh.requestFocusedRefresh} disabled={refresh.refreshing || !themeTickers.length}
            title={themeTickers.length ? `Re-poll and re-rank the ${themeTickers.length} companies on this screen, and nothing else` : 'No theme members are published to re-rank yet'}>
            {refresh.refreshing ? 'Re-ranking…' : `Re-rank these ${themeTickers.length} names`}
          </button>
        )}
        <label {...cap('control.screens.themes-hide-holdings')}>
          <input type="checkbox" checked={hideHoldings} onChange={(event) => setHideHoldings(event.target.checked)} disabled={!holdings.size} />
          {' '}Hide my holdings{holdings.size ? ` (${holdings.size})` : ''}
        </label>
      </div>
      <RefreshStatus refresh={refresh} />

      {hideHoldings && (
        <p {...cap('disclosure.screens.themes-hide-holdings-note')} role="status">
          Your holdings are hidden from the ranked lists. Each theme's trend reading is unchanged: it measures the
          whole group — how many members participate, whether one name carries it, how expensive the group is — and
          recomputing it over a subset would report a different theme under the same name.
        </p>
      )}

      <nav {...cap('nav.screens.themes-index')} aria-label="Themes in this report">
        <ul>
          {[...indexThemes].sort(themesByTrend).map((theme) => (
            <li key={theme.id}>
              <a href={`#theme-${theme.id}`}>{theme.display_name}</a>
              {theme.trend?.verdict?.label && <span> {theme.trend.verdict.label}</span>}
              <small> — {theme.eligible_count ?? 0} of {theme.count ?? 0} cleared the guardrails</small>
            </li>
          ))}
        </ul>
        <details {...cap('detail.screens.themes-info-tags')}>
          <summary>Reading the index</summary>
          <p><b>Broadening</b> — the group is beating the market, most members are participating, and it is not yet
            priced as an expensive third of its sectors.</p>
          <p><b>Narrow leadership</b> — the group is up, but the advance belongs to a minority of it, or to one large
            member.</p>
          <p><b>Strong but already priced</b> — real strength, at valuations that already reflect it.</p>
          <p><b>Cooling</b> — the group is lagging and not recovering.</p>
        </details>
      </nav>

      <p {...cap('disclosure.screens.themes-momentum-excluded')} role="note">
        Price momentum contributes nothing to this ranking by design — a name earns a spot from filing evidence and
        supply-chain ties, not from having already run.
      </p>

      {crossTheme.length > 0 && (
        <section {...cap('figure.screens.themes-cross-theme-section')} aria-label="Where the themes cross">
          <h2>Where the themes cross</h2>
          <details {...cap('detail.screens.themes-info-tags')}>
            <summary>Where themes cross</summary>
            <p>Companies that clear the guardrails on more than one structural trend at once — a name sitting in
              three themes is the most direct expression of where those trends converge, and it is also a single
              position carrying three correlated bets.</p>
          </details>
          <SimpleTable columns={[
            { key: 'ticker', label: 'Ticker', cell: (row) => <button type="button" onClick={() => openStockDetail(row.ticker)}>{row.ticker}</button> },
            { key: 'themeCount', label: 'Themes', cell: (row) => row.themeCount },
            { key: 'themes', label: 'Why it crosses', cell: (row) => row.themes.map((theme) => theme.display_name || theme.theme_id).join(' · ') },
            { key: 'bestOpportunity', label: 'Best opportunity', cell: (row) => number(row.bestOpportunity, 0) },
            { key: 'weakestConfidence', label: 'Weakest evidence', cell: (row) => row.weakestConfidence == null ? '–' : `${Math.round(row.weakestConfidence * 100)}%` },
          ]} rows={crossTheme} getKey={(row) => row.ticker} />
        </section>
      )}

      {themes.map((theme) => {
        const leaderRows = (theme.rows || []).filter((row) => row.candidate_source !== 'sector_peer')
        const leaders = visible(rankThemeExposure({ rows: leaderRows }, leaderRows.length))
        const widePeers = (peerScreen?.themes || []).find((entry) => entry.id === theme.id)
        const connectedSource = widePeers?.rows?.length ? widePeers.rows : (theme.rows || []).filter((row) => row.candidate_source === 'sector_peer')
        const connected = visible(rankThemeExposure({ rows: connectedSource }, connectedSource.length))
        const connectedTotal = widePeers ? widePeers.group_counts?.connected : theme.group_counts?.connected

        return (
          <section {...cap('figure.screens.themes-per-theme-blocks')} id={`theme-${theme.id}`} key={theme.id}>
            <h2>{theme.display_name}</h2>
            <details {...cap('detail.screens.themes-info-tags')}>
              <summary>Columns</summary>
              <p><b>Exposure</b> — 0-100, how exposed this company is to the theme, from filing evidence, never from
                price action.</p>
              <p><b>Opportunity</b> — exposure × business quality × how cheap the stock still is.</p>
              <p><b>Leading signals</b> — how many of this company's own leading signals fired.</p>
              <p><b>Eligible</b> — "No" means the name already trades in the top valuation decile of its sector, or
                no company-specific leading signal confirmed the exposure.</p>
              <p><b>Research rating</b> — a name reading "Insufficient data" has no financial statements pulled for
                it this run; the business-quality leg then rests on price-based multiples alone.</p>
            </details>
            <p>{theme.thesis}</p>
            {(theme.industries || theme.sectors || []).length > 0 && (
              <p>
                <b>Built by:</b> {(theme.industries?.length ? theme.industries : theme.sectors).join(' · ')}
                <details {...cap('detail.screens.themes-info-tags')}>
                  <summary>Built by</summary>
                  <p>The industries this theme's supply chain can sit in. A company outside them is never scored
                    against the theme, however much its own filings talk about the trend.</p>
                </details>
              </p>
            )}
            <ThemeTrendBlock trend={theme.trend} />
            {(theme.biggest_players || []).length > 0 && (
              <div>
                <h4>Biggest players</h4>
                <ul>
                  {visible(theme.biggest_players).map((player) => (
                    <li key={player.ticker}><button type="button" onClick={() => openStockDetail(player.ticker)}>{player.ticker}</button> {player.name} — {player.role ? `${THEME_ROLE_LABELS[player.role] || player.role} in this chain` : 'no chain role assigned'}
                      {' '}· exposure {player.theme_exposure_score ?? '–'}{player.eligible === false ? ' · flagged, not promoted' : ''}</li>
                  ))}
                </ul>
              </div>
            )}

            <h3>Leaders <GroupCount shown={leaders.length} total={theme.group_counts?.leaders} />
              <details {...cap('detail.screens.themes-info-tags')}>
                <summary>Leaders</summary>
                <p>Names already a published top research score or one of your holdings, that also cleared this
                  theme's signal minimum.</p>
              </details>
            </h3>
            {!leaders.length ? (
              <p {...cap('state.screens.themes-no-leader')}>No published leader or holding cleared this theme's signal minimum yet.</p>
            ) : <ThemeRowsTable rows={leaders} openStockDetail={openStockDetail} />}

            <h3>Connected, not yet re-rated <GroupCount shown={connected.length} total={connectedTotal} />
              <details {...cap('detail.screens.themes-info-tags')}>
                <summary>Connected</summary>
                <p>Sector/peer-group neighbours of this theme's anchor companies that are not already a published
                  top research score — a sector/peer-group heuristic, not product-space matching.</p>
              </details>
            </h3>
            {!connected.length ? (
              <p {...cap('state.screens.themes-no-connected')}>No sector-connected candidate cleared this theme's signal minimum in the latest report.</p>
            ) : <ThemeRowsTable rows={connected} openStockDetail={openStockDetail} />}
          </section>
        )
      })}
    </>
  )
}

// =================================================================================================
// 9f — Early Session
// =================================================================================================

function EarlySessionRecipe({ data }) {
  const screens = Object.entries(data?.screens || {})
  const liveCandidates = screens.reduce((total, [, screen]) => total + (screen.candidate_count || 0), 0)
  const allGated = screens.every(([, screen]) => Boolean(screen.reason_code))

  return (
    <>
      <div {...cap('figure.screens.earlysession-gate-summary')} aria-label="Subsystem status">
        Current verdict: {allGated ? 'Gated' : 'Live'} · {liveCandidates} live candidate{liveCandidates === 1 ? '' : 's'}
      </div>

      <section {...cap('figure.screens.earlysession-gate-cards')} aria-label="Early-session screen verdicts">
        {screens.map(([name, screen]) => (
          <article key={name}>
            <h3>{titleCase(name)}</h3>
            {screen.reason_code && <span>Killed by data gate</span>}
            <dl>
              <div><dt>Reason</dt><dd>{screen.reason_code || '–'}</dd></div>
              <div><dt>Fallback</dt><dd>{titleCase(screen.fallback || '')}</dd></div>
              <div><dt>Candidates</dt><dd>{screen.candidate_count}</dd></div>
            </dl>
          </article>
        ))}
      </section>

      <section {...cap('figure.screens.earlysession-capability-matrix')} aria-label="Data capability matrix">
        {(data?.capabilities || []).map((row) => (
          <article key={row.capability}>
            <h4>{row.capability}</h4>
            <span>{row.provider}</span>
            <div>Granularity: {row.granularity}</div>
            <div>Freshness: {row.freshness}</div>
            <div>Verdict: {titleCase(row.verdict)}</div>
          </article>
        ))}
      </section>

      <aside {...cap('disclosure.screens.earlysession-guardrail')} aria-label="Research guardrail">
        Killed screens are a successful research outcome, not a pipeline error. No trade execution, profit promise, "bottom," or
        positive classifier is emitted from unavailable data.
      </aside>

      <p {...cap('disclosure.screens.earlysession-footer')}>
        {data?.disclaimer} Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>
  )
}

// =================================================================================================
// 9g — Politics
// =================================================================================================

const POLITICS_FLAG_LABELS = {
  LATE_FILING: 'Late filing', OPTIONS_TRADE: 'Options trade', RARE_TRADER: 'Rare trader',
  CONCENTRATED_SIZE: 'Concentrated size', CLUSTER_TRADE: 'Cluster trade',
  SAME_SECTOR_REPEAT: 'Same-sector repeat', BUY_SELL_FLIP: 'Buy/sell flip', NOVEL_TICKER: 'Novel ticker',
}

function filerLine(row) {
  const role = row.office ? [row.office, row.agency].filter(Boolean).join(' · ') : [row.chamber, row.district].filter(Boolean).join(' · ')
  return [row.representative, role].filter(Boolean).join(' · ')
}

function monthlyVolume(rows) {
  const byMonth = new Map()
  rows.forEach((row) => {
    const month = (row.transaction_date || '').slice(0, 7)
    if (!month) return
    const lower = row.amount_lower
    const upper = row.amount_upper
    if (lower == null && upper == null) return
    const midpoint = lower != null && upper != null ? (lower + upper) / 2 : (lower ?? upper)
    byMonth.set(month, (byMonth.get(month) || 0) + midpoint)
  })
  return [...byMonth.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([month, value]) => ({ month, value }))
}

function BarTimeline({ points, capId }) {
  const max = Math.max(1, ...points.map((point) => point.value))
  return (
    <div {...cap(capId)} role="img" aria-label="Disclosed volume by month">
      {points.map((point) => (
        <div key={point.month} title={`${point.month}: ${compactMoney(point.value)}`}>
          <span>{point.month}</span>
          <div style={{ height: '8px', width: `${Math.max(2, (point.value / max) * 100)}%`, background: 'currentColor' }} />
          <span>{compactMoney(point.value)}</span>
        </div>
      ))}
    </div>
  )
}

function politicsEmptyNote(data) {
  const failures = data?.collection?.failures || []
  if (data?.reason_code === 'CONGRESS_DISCLOSURE_FEED_UNAVAILABLE') {
    return `Disclosure feed unavailable, so nothing could be collected this run${failures.length ? ` (${failures[0]})` : ''}.`
  }
  if (data?.reason_code === 'NO_DISCLOSURES_IN_PUBLISH_WINDOW') {
    return `No disclosures filed in the trailing ${data.publish_window_days || 120} days.`
  }
  return 'No disclosures collected yet – this screen updates weekly.'
}

function PoliticsRecipe({ manifest, data, reload, searchParams, setParam }) {
  const refresh = useScreenRefresh('congress', reload)
  const chamber = searchParams.get('chamber') || 'all'
  const flag = searchParams.get('flag') || 'all'
  const sort = searchParams.get('sort') || 'disclosed'
  const rows = data?.results || []
  const summary = data?.summary

  const filtered = useMemo(() => {
    let next = rows.filter((row) => chamber === 'all' || row.chamber === chamber)
    if (flag !== 'all') next = next.filter((row) => (row.flags || []).includes(flag))
    const sorted = [...next]
    if (sort === 'amount') sorted.sort((left, right) => (right.amount_upper || 0) - (left.amount_upper || 0))
    else if (sort === 'performance') sorted.sort((left, right) => (right.return_since_purchase_pct ?? -Infinity) - (left.return_since_purchase_pct ?? -Infinity))
    else sorted.sort((left, right) => (right.disclosure_date || '').localeCompare(left.disclosure_date || ''))
    return sorted
  }, [rows, chamber, flag, sort])

  const volumeByMonth = useMemo(() => monthlyVolume(rows), [rows])

  const columns = [
    { key: 'symbol', label: 'Stock', cell: (row) => (
      <details {...cap('control.screens.politics-identity-reveal')}>
        <summary><b>{row.symbol || '–'}</b></summary>
        <span>{row.asset_description || 'Issuer unavailable'} · {row.representative || 'Representative unavailable'}</span>
      </details>
    ) },
    { key: 'type', label: 'Type', cell: (row) => row.transaction_type || '–' },
    { key: 'amount', label: 'Size', cell: (row) => row.amount || '–' },
    { key: 'traded', label: 'Traded', cell: (row) => row.transaction_date || '–' },
    { key: 'filed_after', label: 'Filed after', cell: (row) => row.filing_delay_days != null ? `${row.filing_delay_days}d` : '–' },
    {
      key: 'since_purchase', label: 'Since purchase',
      cell: (row) => row.return_since_purchase_pct != null
        ? <span {...cap('disclosure.screens.politics-since-purchase-caveat')} title="Only appears for a plain stock purchase with enough collected price history.">{upside(row.return_since_purchase_pct)}</span>
        : '–',
    },
    { key: 'flags', label: 'Flags', cell: (row) => (row.flags || []).map((code) => POLITICS_FLAG_LABELS[code] || code).join(', ') || '–' },
  ]

  return (
    <>
      <RerunButton manifest={manifest} refresh={refresh} capId="action.screens.politics-rerun"
        idleLabel="Re-run collection" busyLabel="Collecting…" title="Re-run the disclosure collection now" />
      <RefreshStatus refresh={refresh} />

      {data?.status === 'partial' && (
        <p {...cap('state.screens.politics-partial')} role="alert">
          Collected from some sources only — some disclosures below may be missing ({(data.collection?.failures || []).join('; ') || 'source unavailable'}).
        </p>
      )}

      {data?.signals?.length > 0 && (
        <section {...cap('figure.screens.politics-signals-panel')} aria-label="Most notable disclosures">
          <h3>Top disclosed signals</h3>
          <p {...cap('disclosure.screens.politics-not-a-score')}>Largest, most novel, or most clustered disclosed trades this window — not a score, not advice.</p>
          <ol>
            {data.signals.map((signal) => (
              <li key={signal.ticker}>{signal.direction} <b>{signal.ticker}</b> — {filerLine(signal)} — {(signal.flags || []).map((code) => POLITICS_FLAG_LABELS[code] || code).join(', ')}</li>
            ))}
          </ol>
        </section>
      )}

      {data?.top_tickers?.length > 0 && (
        <section {...cap('figure.screens.politics-top-tickers')} aria-label="Top 10 unusual stocks">
          <h3>Top 10 unusual stocks</h3>
          <p {...cap('disclosure.screens.politics-not-a-score')}>Rolled up per stock by disclosed volume, distinct filers, and clustering/novelty flags — not a score, not advice.</p>
          <SimpleTable columns={[
            { key: 'rank', label: '#', cell: (row) => row.rank },
            { key: 'ticker', label: 'Stock', cell: (row) => (
              <details {...cap('control.screens.politics-identity-reveal')}>
                <summary><b>{row.ticker}</b></summary><span>{row.asset_description || 'Issuer unavailable'}</span>
              </details>
            ) },
            { key: 'volume', label: 'Disclosed volume', cell: (row) => compactMoney(row.disclosed_volume_midpoint) },
            { key: 'trades', label: 'Trades', cell: (row) => `${row.trade_count} (${row.buy_count} buy / ${row.sell_count} sell)` },
            { key: 'filers', label: 'Distinct filers', cell: (row) => (
              <details {...cap('control.screens.politics-identity-reveal')}>
                <summary>{row.unique_politicians}</summary><span>{(row.politicians || []).join(', ') || 'Filer unavailable'}</span>
              </details>
            ) },
          ]} rows={data.top_tickers} getKey={(row) => row.ticker} />
        </section>
      )}

      {summary && (
        <div {...cap('figure.screens.politics-kpi-cards')}>
          <div>Trades: {summary.trades.toLocaleString('en-US')}</div>
          <div>Filings (estimated): {summary.filings_estimated.toLocaleString('en-US')}</div>
          <div>Volume (range ceiling): {compactMoney(summary.volume_upper)}</div>
          <div>Politicians: {summary.politicians.toLocaleString('en-US')}</div>
          <div>Issuers: {summary.issuers.toLocaleString('en-US')}</div>
        </div>
      )}

      <BarTimeline capId="chart.screens.politics-bar-timeline" points={volumeByMonth} />

      <div {...cap('control.screens.politics-filters')}>
        <label>Chamber<select value={chamber} onChange={(event) => setParam('chamber', event.target.value)}>
          <option value="all">All</option><option value="senate">Senate</option><option value="house">House</option><option value="executive">Executive branch</option>
        </select></label>
        <label>Flag<select value={flag} onChange={(event) => setParam('flag', event.target.value)}>
          <option value="all">All</option>{Object.entries(POLITICS_FLAG_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Sort by<select value={sort} onChange={(event) => setParam('sort', event.target.value)}>
          <option value="disclosed">Most recently disclosed</option><option value="amount">Largest reported amount</option><option value="performance">Best performance since purchase</option>
        </select></label>
      </div>

      {!filtered.length ? (
        <div {...cap('state.screens.politics-empty-note')}><EmptyNote manifest={manifest} reason={rows.length ? 'No disclosures match these filters.' : politicsEmptyNote(data)} testId="politics-empty" /></div>
      ) : (
        <SimpleTable capId="column.screens.politics-table" columns={columns} rows={filtered}
          getKey={(row, index) => `${row.representative}-${row.symbol}-${row.transaction_date}-${index}`} />
      )}

      <p {...cap('disclosure.screens.politics-flags-note')}>
        Flags are computed directly from the disclosure data — a late filing, an options trade, an unusually large or clustered
        position, a repeat pattern — not a claim that any trade was improper.
      </p>
      <p {...cap('disclosure.screens.politics-stock-act-ranges')}>Reported amounts are STOCK Act ranges, not exact figures.</p>
      {data?.history_days != null && (
        <p {...cap('disclosure.screens.politics-accumulated-days')}>{data.history_days} day(s) of accumulated history.</p>
      )}
    </>
  )
}

// =================================================================================================
// 9h — Institutional
// =================================================================================================

const INSTITUTIONAL_FLAG_LABELS = {
  CLUSTER_ACCUMULATION: 'Cluster accumulation', ACCUMULATION: 'Accumulation',
  DISTRIBUTION: 'Distribution', CLUSTER_DISTRIBUTION: 'Cluster distribution',
}

function InstitutionalRecipe({ manifest, data, reload, searchParams, setParam }) {
  const refresh = useScreenRefresh('institutional', reload)
  const flag = searchParams.get('flag') || 'all'
  const sort = searchParams.get('sort') || 'recent'
  const rows = data?.results || []

  const filtered = useMemo(() => {
    let next = rows
    if (flag !== 'all') next = next.filter((row) => row.flag === flag)
    const sorted = [...next]
    if (sort === 'breadth') {
      sorted.sort((left, right) => ((right.managers_added || 0) - (right.managers_dropped || 0)) - ((left.managers_added || 0) - (left.managers_dropped || 0)))
    } else {
      sorted.sort((left, right) => (right.as_of || '').localeCompare(left.as_of || ''))
    }
    return sorted
  }, [rows, flag, sort])

  const columns = [
    { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker || '–'}</b> },
    { key: 'cusip', label: 'CUSIP', cell: (row) => row.cusip || '–' },
    { key: 'added', label: 'Managers added', cell: (row) => row.managers_added ?? '–' },
    { key: 'dropped', label: 'Managers dropped', cell: (row) => row.managers_dropped ?? '–' },
    { key: 'change', label: 'Share change', cell: (row) => upside(row.share_change_pct != null ? row.share_change_pct * 100 : null) },
    { key: 'flag', label: 'Flag', cell: (row) => INSTITUTIONAL_FLAG_LABELS[row.flag] || row.flag || '–' },
    { key: 'filed', label: 'Filed', cell: (row) => row.as_of || '–' },
  ]

  return (
    <>
      <RerunButton manifest={manifest} refresh={refresh} capId="action.screens.institutional-rerun"
        idleLabel="Re-run collection" busyLabel="Collecting…" title="Re-run the 13F collection now" />
      <RefreshStatus refresh={refresh} />

      {data && data.status !== 'success' && (
        <p {...cap('state.screens.institutional-collection-incomplete')} role="alert">
          {data.status === 'skipped' ? 'Collection did not run' : 'Collection did not complete'} —{' '}
          {data.degraded_reason || 'The last run published no holdings. Nothing below reflects current 13F filings.'}
        </p>
      )}

      {data && data.status === 'success' && (
        <div {...cap('figure.screens.institutional-kpis')}>
          <div>Managers reviewed: {data.managers_reviewed ?? '–'} of {data.managers_configured ?? '–'} configured</div>
          <div>Tickers flagged: {rows.length.toLocaleString('en-US')}</div>
          <div>CUSIPs mapped: {data.cusips_mapped ?? '–'} of {data.cusips_seen ?? '–'} seen{data.cusips_pending ? `, ${data.cusips_pending} awaiting lookup` : ''}</div>
          <div>Amendments seen: {data.amendments_seen ?? '–'} (13F-HR/A revisions)</div>
        </div>
      )}

      <div {...cap('control.screens.institutional-filters')}>
        <label>Flag<select value={flag} onChange={(event) => setParam('flag', event.target.value)}>
          <option value="all">All</option>{Object.entries(INSTITUTIONAL_FLAG_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>Sort by<select value={sort} onChange={(event) => setParam('sort', event.target.value)}>
          <option value="recent">Most recently filed</option><option value="breadth">Largest manager breadth</option>
        </select></label>
      </div>

      {!filtered.length ? (
        <div {...cap(data && data.status !== 'success' ? 'state.screens.institutional-empty-success' : undefined)}>
          <EmptyNote manifest={manifest} testId="institutional-empty" reason={rows.length
            ? 'No results match these filters.'
            : (data && data.status !== 'success'
              ? 'Nothing to show – the last collection run did not complete, so this is not a statement that no manager moved a position.'
              : 'No flagged activity yet – this screen updates monthly.')} />
        </div>
      ) : (
        <SimpleTable capId="column.screens.institutional-table" columns={columns} rows={filtered} getKey={(row, index) => `${row.ticker}-${row.cusip}-${index}`} />
      )}

      <p {...cap('disclosure.screens.institutional-curated-list')}>
        A curated list of publicly traded, actively managed institutional filers — not the full 13F universe, and not index
        funds or private-equity managers.
      </p>
      <p {...cap('disclosure.screens.institutional-flag-not-prediction')}>
        A flag reports how many curated managers added or cut a position; it is not a prediction.
      </p>
      <p {...cap('disclosure.screens.institutional-cusip-note')}>
        Mapping a CUSIP to a ticker is rate-limited — unmapped holdings are absent from the table above.
      </p>
    </>
  )
}

// =================================================================================================
// 9i — Inside Information
// =================================================================================================

const INSIDEINFO_INSTITUTIONAL_LABELS = { CLUSTER_ACCUMULATION: 'Cluster accumulation', CLUSTER_DISTRIBUTION: 'Cluster distribution' }
const INSIDEINFO_CONGRESS_LABELS = {
  EXTRAORDINARY_BUY: 'First trade in a small, unfamiliar company',
  CLUSTER_TRADE: '3+ representatives, 14-day span',
  BUY_SELL_FLIP: 'Round trip within 60 days',
}

function InsideInfoRecipe({ manifest, data, reload, searchParams, setParam }) {
  const refresh = useScreenRefresh('inside-information', reload)
  const sort = searchParams.get('sort') || 'score'
  const rows = data?.results || []

  const sorted = useMemo(() => {
    const next = [...rows]
    if (sort === 'institutional') next.sort((left, right) => (right.institutional_points || 0) - (left.institutional_points || 0))
    else if (sort === 'congress') next.sort((left, right) => (right.political_points || 0) - (left.political_points || 0))
    else next.sort((left, right) => (right.score || 0) - (left.score || 0))
    return next
  }, [rows, sort])

  const columns = [
    { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker}</b> },
    { key: 'score', label: 'Combined score', cell: (row) => row.score?.toFixed(2) ?? '–' },
    { key: 'institutional', label: 'Institutional', cell: (row) => row.institutional_flag ? (INSIDEINFO_INSTITUTIONAL_LABELS[row.institutional_flag] || row.institutional_flag) : '–' },
    { key: 'congress', label: 'Congressional', cell: (row) => (row.congress_flags || []).map((code) => INSIDEINFO_CONGRESS_LABELS[code] || code).join(', ') || '–' },
    { key: 'members', label: 'Members buying', cell: (row) => row.members_buying ?? '–' },
    { key: 'managers', label: 'Managers added', cell: (row) => row.managers_added ?? '–' },
  ]

  return (
    <>
      <RerunButton manifest={manifest} refresh={refresh} capId="action.screens.insideinfo-rerun"
        idleLabel="Re-run merge" busyLabel="Merging…" title="Re-merge the last published congress and institutional 13F screens" />
      <RefreshStatus refresh={refresh} />

      {data && data.status === 'success' && (
        <div {...cap('figure.screens.insideinfo-kpis')}>
          <div>Tickers with disclosed activity: {data.ranked_count ?? '–'}</div>
          <div>Notable (shown below): {data.notable_count ?? '–'}</div>
        </div>
      )}

      <div>
        <label {...cap('control.screens.insideinfo-sort')}>Sort by
          <select value={sort} onChange={(event) => setParam('sort', event.target.value)}>
            <option value="score">Combined score</option><option value="institutional">Institutional points</option><option value="congress">Congressional points</option>
          </select>
        </label>
      </div>

      {!sorted.length ? (
        <div {...cap('state.screens.insideinfo-no-activity')}>
          <EmptyNote manifest={manifest} testId="insideinfo-empty" reason={data && data.status !== 'success'
            ? 'Nothing to show – the last merge did not complete.'
            : 'No notable activity right now – most disclosed trading is routine and stays on the individual Politics and Institutional screens.'} />
        </div>
      ) : (
        <SimpleTable capId="column.screens.insideinfo-table" columns={columns} rows={sorted} getKey={(row) => row.ticker} />
      )}

      <p {...cap('disclosure.screens.insideinfo-flagged-only')}>
        Shown only where the underlying screen already flagged the activity as rare or notable. Not a claim that any of this
        was informed or improper.
      </p>
    </>
  )
}

// =================================================================================================
// Shell
// =================================================================================================

/**
 * Absorbs the twelve ranked-list-with-a-recipe screen families behind `?recipe=<id>` (see
 * ROUTE-INVENTORY.md §2 and CAPABILITY-LEDGER.md §9). This shell resolves which file to load and
 * renders the artifact's own build-status state, then hands off to one recipe-specific renderer
 * below. `fast-growth` (`report.json`-ranked) and `themes` (`advisor.json` + `theme-peers.json`)
 * are `SELF_FETCHING_RECIPES` — each fetches its own file(s) and owns its own loading/unavailable
 * states, so the shell's single-file gate below is skipped for them.
 */
export default function ScreensScreen() {
  return <FirebaseAuthProvider><ScreensScreenContent /></FirebaseAuthProvider>
}

function ScreensScreenContent() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams, setSearchParams] = useSearchParams()
  const recipe = searchParams.get('recipe') || DEFAULT_RECIPE
  const file = RECIPE_FILES[recipe] ?? RECIPE_FILES[DEFAULT_RECIPE]

  const { data, loading, reload } = useData(file)
  const artifactState = canonicalArtifactState(data)

  const setParam = (key, value) => {
    const next = new URLSearchParams(searchParams)
    if (value == null || value === '') next.delete(key); else next.set(key, value)
    setSearchParams(next, { replace: true })
  }

  const selfFetching = SELF_FETCHING_RECIPES.has(recipe)

  if (!selfFetching) {
    if (loading) return <div {...cap(LOADING_IDS[recipe] || SCREENS_IDS.loading)} role="status" aria-live="polite">Loading…</div>

    if (!file || !data) {
      return (
        <div {...cap(UNAVAILABLE_IDS[recipe] || SCREENS_IDS.unavailable)} role="alert">
          Screen snapshot unavailable{artifactState.reason ? `: ${artifactState.reason}` : '.'}
        </div>
      )
    }
  }

  const rows = data?.results ?? data?.rows ?? []

  return (
    <div data-screen="screens" data-recipe={recipe}>
      <StockDetailSheet />
      <Container>
        <h1>{recipe}</h1>
        {!selfFetching && (
          <>
            <span data-testid="row-count">{rows.length} name{rows.length === 1 ? '' : 's'}</span>
            {artifactState.partial && <p role="alert" data-testid="partial-note">Collected from some sources only.</p>}
            {artifactState.state === 'unavailable' && <p data-testid="gated-note">{artifactState.reason}</p>}
          </>
        )}
      </Container>

      {recipe === 'swing' && <SwingRecipe manifest={manifest} data={data} searchParams={searchParams} setParam={setParam} />}
      {recipe === 'fast-growth' && <FastGrowthRecipe manifest={manifest} searchParams={searchParams} setParam={setParam} />}
      {recipe === 'options' && <OptionsRecipe manifest={manifest} data={data} searchParams={searchParams} setParam={setParam} />}
      {GENERIC_FAMILY.has(recipe) && <GenericRecipe manifest={manifest} recipe={recipe} data={data} searchParams={searchParams} setParam={setParam} />}
      {recipe === 'themes' && <ThemesRecipe manifest={manifest} />}
      {recipe === 'early-session' && <EarlySessionRecipe data={data} />}
      {recipe === 'politics' && <PoliticsRecipe manifest={manifest} data={data} reload={reload} searchParams={searchParams} setParam={setParam} />}
      {recipe === 'institutional' && <InstitutionalRecipe manifest={manifest} data={data} reload={reload} searchParams={searchParams} setParam={setParam} />}
      {recipe === 'inside-information' && <InsideInfoRecipe manifest={manifest} data={data} reload={reload} searchParams={searchParams} setParam={setParam} />}
    </div>
  )
}
