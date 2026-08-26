import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { AuthProvider as FirebaseAuthProvider, useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { currentHoldingsSeries, returnOverWindow } from '../../../lib/portfolioAnalytics.js'
import { useMedium } from '../MediumContext.jsx'
import { promotionDisclosure } from '../states.js'
import { cap } from '../capability.js'
import { EVIDENCE_IDS } from './capabilityIds.js'
import WallLabel from '../WallLabel.jsx'
import { splitBySampleRequirement, defaultOpenGroups, sharedStatusMessage } from '../../../lib/signalMetrics.js'
import appBreakdownMd from '../../../../APP-COMPLETE-BREAKDOWN.md?raw'
import masterMethodologyMd from '../../../../docs/MASTER-METHODOLOGY.md?raw'

export const EVIDENCE_SECTIONS = Object.freeze(['validation', 'backtests', 'shadow', 'methodology', 'glossary'])

// ---------------------------------------------------------------------------------------------
// Formatting helpers. Deliberately local (not imported from src/pages or src/components, which
// are off-limits to every medium but Classic) — small, pure, and easy to verify against the
// originals they mirror (BacktestComparison.jsx, BacktestSummary.jsx, ShadowPortfolios.jsx,
// Methodology.jsx, Glossary.jsx).
// ---------------------------------------------------------------------------------------------
const pctFmt = (value, digits = 2) => value == null ? null : `${Number(value).toFixed(digits)}%`
const rateFmt = (value, digits = 1) => value == null ? null : `${(Number(value) * 100).toFixed(digits)}%`
const numFmt = (value, digits = 2) => value == null ? null : Number(value).toFixed(digits)
const moneyFmt = (value) => value == null ? null : `$${Number(value).toFixed(2)}`
const countFmt = (value) => value == null ? null : Number(value).toLocaleString()
const signedPct = (value) => value == null ? null : `${Number(value) >= 0 ? '+' : '−'}${Math.abs(Number(value)).toFixed(2)}%`

function metricRow(row) {
  return {
    breached: false,
    observations: null,
    required_observations: null,
    status_message: null,
    source: null,
    display: null,
    reads: null,
    ...row,
  }
}

// =================================================================================================
// Backtests (`?section=backtests`) — CAPABILITY-LEDGER.md §10a
// =================================================================================================

const BACKTEST_GROUP_ORDER = ['held_portfolio', 'contribution_flows', 'option_trades', 'rank_quality']
const BACKTEST_GROUP_TITLES = {
  held_portfolio: 'Held portfolios',
  contribution_flows: 'Portfolios with ongoing contributions',
  option_trades: 'Option strategies',
  rank_quality: 'Ranking quality (not a portfolio return)',
}
const BACKTEST_BASIS_LABELS = {
  rebalance_periods_positive: 'periods positive',
  trades_profitable: 'trades profitable',
  periods_with_positive_ic: 'periods ranked correctly',
  not_measurable_with_contribution_flows: 'not measurable',
}
const portfolioLikeGroup = (group) => group === 'held_portfolio' || group === 'contribution_flows'
const backtestWindowLabel = (row) => row?.window_start && row?.window_end ? `${row.window_start} → ${row.window_end}` : 'no recorded window'
const backtestStatusLabel = (row) => {
  if (row.status === 'measured') return null
  if (row.status === 'unavailable') return 'Not yet run'
  return 'Insufficient history'
}

function groupBacktestMethods(methods) {
  const bucketed = new Map()
  methods.forEach((row) => {
    const key = row.comparable_group || 'other'
    if (!bucketed.has(key)) bucketed.set(key, [])
    bucketed.get(key).push(row)
  })
  bucketed.forEach((rows) => rows.sort((a, b) => {
    const ranked = (row) => row.status === 'measured' && row.success_rate != null
    if (ranked(a) !== ranked(b)) return ranked(a) ? -1 : 1
    if (!ranked(a)) return (a.label || '').localeCompare(b.label || '')
    return b.success_rate - a.success_rate
  }))
  return BACKTEST_GROUP_ORDER.filter((key) => bucketed.has(key)).map((key) => [key, bucketed.get(key)])
}

/**
 * Maps §15's 10 `metric.report.backtest-*` / `metric.report.average-pnl-trade` /
 * `metric.report.trade-count` rows onto a single WallLabel-shaped object each.
 *
 * `screens/backtest-comparison.json` (BacktestComparison.jsx's source) carries total return,
 * CAGR, vs-SPY, success rate and beat-SPY for every method, read here off the champion
 * ("research_score_monthly", the model this app actually ranks on) since the ledger asks for
 * one representative value per metric id, not a full table. It does not carry `win_rate` or
 * `num_trades` at all, and only option-trades rows carry `deflated_sharpe` — those four ids
 * (dsr, win-rate, avg-pnl-per-trade, trade-count) are BacktestSummary.jsx's fields instead, read
 * from `screens/options-backtest.json`'s embedded `backtest` object (the same file/shape
 * `<BacktestSummary file="screens/options-backtest.json" />` renders on OptionsScreen). This is
 * a genuine field-mapping judgment call — see the wiring report for the full rationale.
 */
function backtestMetricRows(comparison, optionsBacktest) {
  const champion = (comparison?.methods || []).find((row) => row.id === 'research_score_monthly') || null
  const champMeasured = champion?.status === 'measured'
  const champState = (value, nullMessage) => {
    if (!champion) return { status: 'unavailable', status_message: 'Backtest comparison has not published this method yet.' }
    if (!champMeasured) return { status: 'unavailable', status_message: champion.status_detail || 'Not yet run.' }
    if (value == null) return { status: 'awaiting_input', status_message: nullMessage || 'Not measurable for this method.' }
    return { status: 'ready', status_message: null }
  }

  const optBt = optionsBacktest?.backtest || null
  const optReady = optionsBacktest?.status === 'success'
  const optState = (value) => {
    if (!optReady) return { status: 'unavailable', status_message: 'Options backtest has not published a result yet.' }
    if (value == null) return { status: 'awaiting_input', status_message: 'Not measurable yet.' }
    return { status: 'ready', status_message: null }
  }

  const totalReturn = champion?.total_return_pct
  const cagr = champion?.cagr_pct
  const excessSpy = champion?.excess_return_pct
  const successRate = champion?.success_rate
  const beatSpy = champion?.beat_benchmark_rate
  const sharpe = champion?.sharpe
  const dsr = optBt?.deflated_sharpe_ratio
  const winRate = optBt?.win_rate
  const avgPnl = optBt?.average_pnl_per_trade
  const tradeCount = optBt?.num_trades

  return [
    metricRow({
      id: 'backtest_total_return', label: 'Total return', unit: '%',
      value: totalReturn, display: pctFmt(totalReturn),
      reads: totalReturn != null ? `${champion.label} returned ${pctFmt(totalReturn)} total return across its backtest window (${backtestWindowLabel(champion)}).` : null,
      source: champion?.source, ...champState(totalReturn),
    }),
    metricRow({
      id: 'backtest_cagr', label: 'CAGR', unit: '%',
      value: cagr, display: pctFmt(cagr),
      reads: cagr != null ? `${champion.label}'s CAGR over its backtest window is ${pctFmt(cagr)}.` : null,
      source: champion?.source, ...champState(cagr),
    }),
    metricRow({
      id: 'backtest_excess_spy', label: 'vs SPY', unit: '%',
      value: excessSpy, display: pctFmt(excessSpy),
      reads: excessSpy != null ? `${champion.label} beat SPY by ${pctFmt(excessSpy)} over the same window.` : null,
      source: champion?.source, ...champState(excessSpy, champion?.excess_return_withheld_reason),
    }),
    metricRow({
      id: 'backtest_success_rate', label: 'Success rate', unit: '%',
      value: successRate, display: rateFmt(successRate),
      reads: successRate != null ? `${champion.label}'s success rate is ${rateFmt(successRate)} (${BACKTEST_BASIS_LABELS[champion.success_rate_basis] || champion.success_rate_basis}).` : null,
      source: champion?.source, ...champState(successRate),
    }),
    metricRow({
      id: 'backtest_beat_spy', label: 'Beat SPY', unit: '%',
      value: beatSpy, display: rateFmt(beatSpy),
      reads: beatSpy != null ? `${champion.label} beat SPY in ${rateFmt(beatSpy)} of measured periods.` : null,
      source: champion?.source, ...champState(beatSpy),
    }),
    metricRow({
      id: 'backtest_sharpe', label: 'Sharpe', unit: 'ratio',
      value: sharpe, display: numFmt(sharpe, 3),
      reads: sharpe != null ? `${champion.label}'s Sharpe ratio over its backtest window is ${numFmt(sharpe, 3)}.` : null,
      source: champion?.source, ...champState(sharpe),
    }),
    metricRow({
      id: 'backtest_dsr', label: 'Deflated Sharpe', unit: 'probability',
      value: dsr, display: rateFmt(dsr, 2),
      reads: dsr != null ? `Deflated Sharpe for the multi-day options backtest is ${rateFmt(dsr, 2)} — the probability the true Sharpe ratio beats what random chance across this many strategy-design choices would produce on its own.` : null,
      source: 'screens/options-backtest.json', ...optState(dsr),
    }),
    metricRow({
      id: 'backtest_win_rate', label: 'Win rate', unit: '%',
      value: winRate, display: rateFmt(winRate),
      reads: winRate != null ? `${rateFmt(winRate)} of multi-day options trades were profitable.` : null,
      source: 'screens/options-backtest.json', ...optState(winRate),
    }),
    metricRow({
      id: 'average_pnl_trade', label: 'Avg P/L per trade', unit: '$',
      value: avgPnl, display: moneyFmt(avgPnl),
      reads: avgPnl != null ? `Average P/L per trade across the multi-day options backtest is ${moneyFmt(avgPnl)}.` : null,
      source: 'screens/options-backtest.json', ...optState(avgPnl),
    }),
    metricRow({
      id: 'trade_count', label: 'Trades', unit: 'count',
      value: tradeCount, display: countFmt(tradeCount),
      reads: tradeCount != null ? `${countFmt(tradeCount)} multi-day options trades have been simulated.` : null,
      source: 'screens/options-backtest.json', ...optState(tradeCount),
    }),
  ]
}

function BacktestSuccessCell({ row }) {
  if (row.success_rate == null) {
    if (row.periods_in_cash) {
      return <span {...cap('state.evidence.backtests-held-cash-n-periods')}>
        {`Held cash in ${row.periods_in_cash} of ${row.periods_in_cash + (row.periods_measured || 0)} periods`}
      </span>
    }
    return <>—</>
  }
  return <>{rateFmt(row.success_rate)} <small>{BACKTEST_BASIS_LABELS[row.success_rate_basis] || row.success_rate_basis}</small></>
}

function BacktestsSection({ comparison, optionsBacktest, loading, Container }) {
  const [showCaveats, setShowCaveats] = useState(false)

  if (loading) return <div role="status" aria-live="polite">Loading…</div>
  if (!comparison) {
    return <div {...cap('state.evidence.backtests-unavailable')} role="alert">Backtest comparison unavailable</div>
  }

  const methods = comparison.methods || []
  const measured = methods.filter((row) => row.status === 'measured')
  const rollup = comparison.feature_rollup || []
  const caveats = methods.filter((row) => (row.caveats || []).length)
  const groups = groupBacktestMethods(methods)
  const metricRows = backtestMetricRows(comparison, optionsBacktest)

  return (
    <div data-testid="backtests-section">
      <Container {...cap('figure.evidence.backtests-coverage-cards')}>
        <article><span>Methods measured</span><strong data-testid="backtests-measured-count">{measured.length}</strong>
          <small>of {comparison.methods_total ?? 0} backtests wired up</small></article>
        <article><span>Comparable groups</span><strong>{groups.length}</strong>
          <small {...cap('disclosure.evidence.backtests-within-group-only')}>success rates rank only within a group</small></article>
        <article><span>Features tracked</span><strong>{new Set(rollup.map((row) => row.feature)).size}</strong>
          <small>declared inputs across all methods</small></article>
        <article><span>Generated</span><strong>{(comparison.generated_at || '').slice(0, 10) || '—'}</strong>
          <small>from result files on disk</small></article>
      </Container>

      <p>{comparison.interpretation}</p>

      <div data-testid="backtest-metrics">
        {metricRows.map((metric) => <WallLabel key={metric.id} metric={metric} />)}
      </div>

      {/*
        chart.evidence.backtests-dotplots (DotPlot x4 groups) is deliberately skipped: it needs
        the same per-medium chart-renderer contract the task notes as legitimately hard to do
        well in one pass, and `DotPlot` itself lives under the ESLint-restricted src/components/*
        (only Classic may import it). Every value it would plot is still on screen via the
        method tables below.
      */}

      {groups.map(([group, groupRows]) => (
        <Container key={group} {...cap('column.evidence.backtests-method-tables')}>
          <h3>{BACKTEST_GROUP_TITLES[group] || group}</h3>
          <p>{comparison.comparable_groups?.[group]}</p>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Success rate</th>
                  {portfolioLikeGroup(group) && <th>Beat SPY</th>}
                  <th>Total return</th>
                  {portfolioLikeGroup(group) && <th>vs SPY</th>}
                  <th>{group === 'rank_quality' ? 'Mean IC' : 'CAGR'}</th>
                  <th>Sharpe</th>
                  <th>Max drawdown</th>
                  <th>Observations</th>
                  <th>Window</th>
                </tr>
              </thead>
              <tbody>
                {groupRows.map((row) => (
                  <tr key={row.id}>
                    <td><b>{row.label}</b>
                      {backtestStatusLabel(row) && <small {...cap('disclosure.evidence.backtests-status-chips')}> {backtestStatusLabel(row)}</small>}
                    </td>
                    <td><BacktestSuccessCell row={row} /></td>
                    {portfolioLikeGroup(group) && <td>{row.beat_benchmark_rate != null ? rateFmt(row.beat_benchmark_rate) : '—'}</td>}
                    <td>{pctFmt(row.total_return_pct) ?? '—'}</td>
                    {portfolioLikeGroup(group) && <td>{pctFmt(row.excess_return_pct) ?? '—'}</td>}
                    <td>{group === 'rank_quality' ? (numFmt(row.mean_ic, 4) ?? '—') : (pctFmt(row.cagr_pct) ?? '—')}</td>
                    <td>{numFmt(row.sharpe ?? row.deflated_sharpe, 3) ?? '—'}</td>
                    <td>{pctFmt(row.max_drawdown_pct) ?? '—'}</td>
                    <td>{countFmt(row.periods_measured) ?? '—'}</td>
                    <td>{backtestWindowLabel(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Container>
      ))}

      <Container {...cap('figure.evidence.backtests-success-rollup')}>
        <h3>Success rate by feature</h3>
        <p {...cap('disclosure.evidence.backtests-cooccurrence-note')}>
          This is co-occurrence across methods, not attribution: methods share inputs and cover
          different windows, so use it to decide what to investigate, never as evidence that a
          feature caused a result.
        </p>
        {rollup.length ? (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Feature</th><th>Mean success rate</th><th>Range</th><th>Methods</th>
                  <th {...cap('disclosure.evidence.backtests-basis-column')}>Measured as</th>
                </tr>
              </thead>
              <tbody>
                {rollup.map((row) => (
                  <tr key={`${row.feature}-${row.success_rate_basis}`}>
                    <td><b>{row.feature}</b></td>
                    <td>{rateFmt(row.mean_success_rate) ?? '—'}</td>
                    <td>{rateFmt(row.minimum_success_rate) ?? '—'} – {rateFmt(row.maximum_success_rate) ?? '—'}</td>
                    <td>{row.methods}</td>
                    <td>{BACKTEST_BASIS_LABELS[row.success_rate_basis] || row.success_rate_basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p {...cap('state.evidence.backtests-nothing-to-rollup')}>
            No method has published a success rate yet, so there is nothing to roll up.
          </p>
        )}
      </Container>

      {caveats.length > 0 && (
        <Container {...cap('control.evidence.backtests-coverage-expander')}>
          <button type="button" aria-expanded={showCaveats} onClick={() => setShowCaveats((value) => !value)}>
            {showCaveats ? 'Hide' : 'Show'} what each backtest cannot measure ({caveats.length} methods)
          </button>
          {showCaveats && caveats.map((row) => (
            <div key={row.id}>
              <strong>{row.label}</strong>
              {row.status_detail && <p>{row.status_detail}</p>}
              <ul>{(row.caveats || []).map((note) => <li key={note}>{note}</li>)}</ul>
              <small>Source: {row.source}</small>
            </div>
          ))}
        </Container>
      )}

      <p {...cap('disclosure.evidence.backtests-footer')}>
        Every figure here is retrospective and simulated. A backtest is evidence about the past
        under its own stated assumptions, not a forecast, and the strategies with the shortest
        windows are the ones most easily misread — check the observation count and the window
        before comparing anything. Prospective, forward-only results are on the shadow
        portfolios screen, and those are the ones that govern whether a strategy is ever promoted.
      </p>
    </div>
  )
}

// =================================================================================================
// Shadow (`?section=shadow`) — CAPABILITY-LEDGER.md §10b
// =================================================================================================

function shadowCellText(value, suffix, row, minimum = 1) {
  if (value != null) return `${Number(value).toFixed(2)}${suffix}`
  if (!row?.snapshots) return 'Not started'
  if (!row?.observations) return 'First return pending'
  return `${row.observations}/${minimum} returns`
}

function shadowAlignedCell(row) {
  if (!row?.observations) return '—'
  const value = row.aligned?.net_return
  if (value == null) return 'Outside shared window'
  return `${Number(value).toFixed(2)}%`
}

function shadowRankingOverview(strategies, alignedWindow, annualizedMinimum) {
  const sessions = Number(alignedWindow?.observations) || 0
  const ranked = strategies
    .filter((row) => row.observations > 0 && row.aligned?.net_return != null && Number.isFinite(Number(row.aligned.net_return)))
    .sort((a, b) => Number(b.aligned.net_return) - Number(a.aligned.net_return))
  if (!sessions || ranked.length < 2) {
    const waiting = strategies.filter((row) => !row.observations).length
    const waitingNote = waiting
      ? ` ${waiting} of ${strategies.length} ${strategies.length === 1 ? 'strategy has' : 'strategies have'} not started.`
      : ''
    return {
      noComparable: true,
      text: `No comparable ranking yet. At least two strategies need a return from the same aligned window before they can be ordered fairly.${waitingNote}`,
    }
  }
  const leader = ranked[0]
  const sessionLabel = `${sessions} shared session${sessions === 1 ? '' : 's'}`
  const caveat = sessions < annualizedMinimum
    ? `Treat the order as an early read; annualized statistics need ${annualizedMinimum} matched returns.`
    : 'No strategy is promotion-eligible until 36 monthly observations are complete.'
  return {
    noComparable: false,
    text: `${leader.strategy} ranks #1 of ${ranked.length} on aligned net return at ${signedPct(leader.aligned.net_return)} over ${sessionLabel}. ${caveat}`,
  }
}

/**
 * Maps §15's 6 `metric.report.shadow-*` rows onto a WallLabel-shaped object each, read off the
 * "Existing production model" strategy (the champion / production analogue among the shadow
 * strategies — falls back to the first published strategy if that one is ever renamed or
 * absent). `sortino`/`cagr`/`sharpe` are frequently still null this early in collection (they
 * need `annualized_metrics_minimum_observations` matched returns) — that null is itself the
 * accumulating state WallLabel renders, not a mapping gap.
 */
function shadowMetricRows(shadowData) {
  const strategies = shadowData?.strategies || []
  const row = strategies.find((entry) => entry.strategy === 'Existing production model') || strategies[0] || null
  const annualizedMinimum = strategies.length
    ? Math.max(...strategies.map((entry) => entry.annualized_metrics_minimum_observations || 0), 20)
    : 20

  const cellState = (value, { annualized = false } = {}) => {
    if (!row) return { status: 'unavailable', status_message: 'No shadow strategy published yet.' }
    if (value != null) {
      return { status: 'ready', status_message: null, observations: row.observations ?? null, required_observations: annualized ? annualizedMinimum : null }
    }
    if (!row.snapshots) return { status: 'awaiting_input', status_message: 'Not started', observations: 0, required_observations: annualized ? annualizedMinimum : null }
    if (!row.observations) return { status: 'accumulating', status_message: 'First return pending', observations: 0, required_observations: annualized ? annualizedMinimum : null }
    return {
      status: 'accumulating',
      status_message: annualized ? `${row.observations}/${annualizedMinimum} returns` : (row.evidence_status || null),
      observations: row.observations,
      required_observations: annualized ? annualizedMinimum : null,
    }
  }

  const alignedValue = row?.aligned?.net_return
  const alignedState = !row
    ? { status: 'unavailable', status_message: 'No shadow strategy published yet.' }
    : alignedValue != null
      ? { status: 'ready', status_message: null }
      : row.observations
        ? { status: 'unavailable', status_message: 'Outside shared window' }
        : { status: 'awaiting_input', status_message: 'Not started' }

  return [
    metricRow({
      id: 'shadow_aligned_net_return', label: 'Aligned net return', unit: '%',
      value: alignedValue, display: signedPct(alignedValue),
      reads: alignedValue != null ? `${row.strategy} moved ${signedPct(alignedValue)} over the shared aligned window.` : null,
      source: 'pipeline/shadow_portfolios.py', ...alignedState,
    }),
    metricRow({
      id: 'shadow_net_return', label: 'Net return (own window)', unit: '%',
      value: row?.net_return, display: row?.net_return != null ? `${row.net_return.toFixed(2)}%` : null,
      reads: row?.net_return != null ? `${row.strategy}'s net return over its own collection window is ${row.net_return.toFixed(2)}%.` : null,
      source: 'pipeline/shadow_portfolios.py', ...cellState(row?.net_return),
    }),
    metricRow({
      id: 'shadow_sortino', label: 'Sortino', unit: 'ratio',
      value: row?.sortino, display: numFmt(row?.sortino, 2),
      reads: row?.sortino != null ? `${row.strategy}'s Sortino ratio is ${numFmt(row.sortino, 2)}.` : null,
      source: 'pipeline/shadow_portfolios.py', ...cellState(row?.sortino, { annualized: true }),
    }),
    metricRow({
      id: 'shadow_turnover', label: 'Turnover', unit: '%',
      value: row?.turnover, display: row?.turnover != null ? `${row.turnover.toFixed(2)}%` : null,
      reads: row?.turnover != null ? `${row.strategy}'s turnover is ${row.turnover.toFixed(2)}%.` : null,
      source: 'pipeline/shadow_portfolios.py', ...cellState(row?.turnover),
    }),
    metricRow({
      id: 'shadow_coverage_change', label: 'Coverage change', unit: '%',
      value: row?.composition_change, display: row?.composition_change != null ? `${row.composition_change.toFixed(2)}% not traded` : null,
      reads: row?.composition_change != null ? `${row.composition_change.toFixed(2)}% of ${row.strategy}'s weight entered because more of the universe became priced, not turnover.` : null,
      source: 'pipeline/shadow_portfolios.py', ...cellState(row?.composition_change),
    }),
    metricRow({
      id: 'shadow_observations', label: 'Observations / snapshots', unit: 'count',
      value: row?.observations, display: row ? `${row.observations || 0} observations · ${row.snapshots || 0} snapshots` : null,
      reads: row ? `${row.strategy} has ${row.observations || 0} matched returns from ${row.snapshots || 0} immutable snapshots.` : null,
      source: 'pipeline/shadow_portfolios.py',
      ...(!row
        ? { status: 'unavailable', status_message: 'No shadow strategy published yet.' }
        : row.observations > 0
          ? { status: 'ready', status_message: null, observations: row.observations }
          : row.snapshots
            ? { status: 'accumulating', status_message: 'First return pending', observations: 0 }
            : { status: 'awaiting_input', status_message: 'Not started', observations: 0 }),
    }),
  ]
}

/**
 * The "your portfolio vs. these strategies" overlay (figure.evidence.shadow-my-portfolio-overlay
 * / state.evidence.shadow-mine-4-branches). Informational only — mirrors
 * `src/pages/portfolio/MyPortfolioVsShadow.jsx`'s four branches (not signed in / no positions /
 * not enough history / result) but is reimplemented here from `src/lib/*` primitives only
 * (`useFirebasePortfolio`, `buildPortfolioPriceData` + `mergePositionSnapshots`,
 * `currentHoldingsSeries` + `returnOverWindow`) since the page's own
 * `buildPriceModel` helper lives under the ESLint-restricted `src/pages/portfolio/*`. This
 * mounts its own `<FirebaseAuthProvider>` the same way PortfolioScreen.jsx does, since `/v2`'s
 * root never provides one.
 */
function ShadowMineOverlay({ reportData, alignedWindow }) {
  const { currentUser } = useAuth()
  const { positions } = useFirebasePortfolio()

  const priceData = useMemo(() => {
    if (!reportData) return {}
    return mergePositionSnapshots(
      buildPortfolioPriceData(reportData.screen_universe || [], reportData.portfolio_coverage || [], reportData.research || []),
      positions,
      reportData.generated_at,
    )
  }, [reportData, positions])

  const myHoldingsSeries = currentHoldingsSeries(positions, priceData, [])
  const myWindow = alignedWindow?.window_start && alignedWindow?.window_end
    ? returnOverWindow(myHoldingsSeries, alignedWindow.window_start, alignedWindow.window_end)
    : { available: false, reason: 'No comparable window has been established yet.' }

  let branch
  let body
  if (!currentUser) {
    branch = 'not-signed-in'
    body = <p>Sign in and add your holdings to compare your own investing against these strategies over this same window.</p>
  } else if (!positions.length) {
    branch = 'no-positions'
    body = <p>Add holdings to your portfolio to compare your own investing against these strategies over this same window.</p>
  } else if (!myWindow.available) {
    branch = 'not-enough-history'
    body = <p>{myWindow.reason || 'Your portfolio does not yet have enough price history to compare over this window.'}</p>
  } else {
    branch = 'result'
    body = (
      <>
        <p data-testid="shadow-mine-result">
          Your portfolio: <strong>{signedPct(myWindow.netReturnPct)}</strong> from {myWindow.startDate} to {myWindow.endDate}
        </p>
        <p {...cap('disclosure.evidence.shadow-informational-only')}>
          Informational only: this never writes into the shadow strategy registry above and plays no part in any promotion decision.
        </p>
      </>
    )
  }

  return (
    <div {...cap('figure.evidence.shadow-my-portfolio-overlay')} data-mine-branch={branch}>
      <span {...cap('state.evidence.shadow-mine-4-branches')} data-testid="shadow-mine-branch">{branch}</span>
      {body}
    </div>
  )
}

function ShadowMineWrapper(props) {
  return <FirebaseAuthProvider><ShadowMineOverlay {...props} /></FirebaseAuthProvider>
}

function ShadowSection({ shadowData, reportData, loading, Container }) {
  if (loading) return <div role="status" aria-live="polite">Loading…</div>
  if (!shadowData) {
    return <div {...cap('state.evidence.shadow-unavailable')} role="alert">Shadow results unavailable</div>
  }

  const strategies = shadowData.strategies || []
  const live = strategies.filter((row) => row.observations > 0)
  const snapshots = strategies.reduce((total, row) => total + (row.snapshots || 0), 0)
  const alignedWindow = shadowData.aligned_window || {}
  const annualizedMinimum = strategies.length
    ? Math.max(...strategies.map((row) => row.annualized_metrics_minimum_observations || 0), 20)
    : 20
  const overview = shadowRankingOverview(strategies, alignedWindow, annualizedMinimum)
  const metricRows = shadowMetricRows(shadowData)

  return (
    <div data-testid="shadow-section">
      <Container {...cap('figure.evidence.shadow-overview')}>
        <p data-testid="shadow-overview-text" {...(overview.noComparable ? cap('state.evidence.shadow-no-comparable-ranking') : {})}>
          {overview.text}
        </p>
      </Container>

      <ShadowMineWrapper reportData={reportData} alignedWindow={alignedWindow} />

      <Container {...cap('figure.evidence.shadow-summary-cards')}>
        <article><span>Reporting now</span><strong>{live.length}</strong><small>strategies with matched returns</small></article>
        <article><span>Immutable snapshots</span><strong>{snapshots}</strong><small>one per market session, never rewritten</small></article>
        <article><span>Comparable window</span>
          <strong>{alignedWindow.window_start ? `${alignedWindow.window_start.slice(5)} → ${alignedWindow.window_end.slice(5)}` : 'Starting'}</strong>
          <small>{alignedWindow.observations || 0} sessions every strategy observed</small></article>
        <article><span>Implementation cost</span><strong>{live[0]?.cost_bps ?? 20} bps</strong><small>spread plus slippage</small></article>
      </Container>

      <div data-testid="shadow-metrics">
        {metricRows.map((metric) => <WallLabel key={metric.id} metric={metric} />)}
      </div>

      {/*
        chart.evidence.shadow-scatter (max drawdown vs aligned net return) is deliberately
        skipped for the same reason as the backtests dot plots: `ScatterChart` lives under the
        ESLint-restricted src/components/*, and a bespoke chart-contract renderer per medium is
        out of scope for this pass. Every point it would plot is on the strategies table below.
      */}

      <Container {...cap('column.evidence.shadow-strategies-table')}>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Strategy</th><th>Aligned net return</th><th>Net return (own window)</th><th>CAGR</th>
                <th>Sharpe</th><th>Sortino</th><th>Max drawdown</th><th>Turnover</th>
                <th>Coverage change</th><th>Observations</th><th>Evidence status</th>
              </tr>
            </thead>
            <tbody>
              {strategies.map((row) => (
                <tr key={row.strategy}>
                  <td><b>{row.strategy}</b></td>
                  <td {...cap('state.evidence.shadow-per-cell-status')}>{shadowAlignedCell(row)}</td>
                  <td>{shadowCellText(row.net_return, '%', row)}</td>
                  <td>{shadowCellText(row.cagr, '%', row, annualizedMinimum)}</td>
                  <td>{shadowCellText(row.sharpe, '', row, annualizedMinimum)}</td>
                  <td>{shadowCellText(row.sortino, '', row, annualizedMinimum)}</td>
                  <td>{shadowCellText(row.max_drawdown, '%', row)}</td>
                  <td>{shadowCellText(row.turnover, '%', row)}</td>
                  <td>{row.composition_change != null ? `${Number(row.composition_change).toFixed(2)}% not traded` : '—'}</td>
                  <td>{row.observations || 0} · {row.snapshots || 0} snapshots</td>
                  <td>{row.evidence_status || 'Insufficient observations'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Container>

      <p {...cap('disclosure.evidence.shadow-promotion-gate')}>{shadowData.promotion_gate}</p>
      {alignedWindow.observations > 0 && (
        <p {...cap('disclosure.evidence.shadow-aligned-window-explanation')}>
          Each strategy above reports over its own collection window, which differs by strategy.
          Use the aligned net return to compare them: it covers only the {alignedWindow.observations}{' '}
          session{alignedWindow.observations === 1 ? '' : 's'} every reporting strategy was in the market for.
        </p>
      )}
      <p {...cap('disclosure.evidence.shadow-annualization-gate')}>
        Annualized statistics remain gated until {annualizedMinimum} matched returns exist;
        promotion remains gated until 36 monthly observations.
      </p>
    </div>
  )
}

// =================================================================================================
// Methodology (`?section=methodology`) — CAPABILITY-LEDGER.md §10d. Copy in the two static
// constants below is reproduced verbatim from src/pages/Methodology.jsx (not fabricated —
// relocated per the medium-agnostic architecture); every weight/version/capability value is
// still read live off `advisor.json`, never hardcoded.
// =================================================================================================

const METHODOLOGY_COMPONENT_LABEL = { fundamentals: 'fundamentals', market_behavior: 'behaviour', news_sentiment: 'news' }

const METHODOLOGY_CATEGORIES = {
  valuation: ['Valuation', 'EV/EBITDA and EV/EBIT carry this bucket. The enterprise multiple is the best-validated single value measure in the published research, and enterprise multiples are capital-structure neutral, so a levered company cannot look cheap purely because debt flatters its equity ratios. PEG is now a minor sanity check rather than the largest input. Both book-value multiples are trimmed because book value systematically mismeasures intangible-heavy businesses.'],
  profitability: ['Profitability + cash', 'ROIC leads rather than ROE because leverage inflates return on equity but cannot inflate return on invested capital. Gross profits over assets adds information a value screen cannot. Cash conversion tests whether reported earnings arrive as money.'],
  financial_health: ['Financial health', 'Interest coverage and net debt to EBITDA answer the question debt-to-equity cannot: can this business comfortably service its debt at current rates? The Altman Z-score uses the variant fitted for the filer’s sector and is suppressed for financials, where it has no meaning.'],
  accounting_quality: ['Accounting quality', 'The Piotroski F-score leads this bucket. The accruals ratio remains at a smaller weight because its predictive power has decayed in recent US data. Receivable and inventory day trends round out the check.'],
  growth: ['Growth', 'Revenue and earnings year over year, three-year free-cash-flow growth, the direction of operating margin, and earnings surprise against expectations. Trailing growth on its own predicts forward returns weakly. The surprise component is the part that carries drift.'],
  capital_allocation: ['Capital allocation', 'Net buyback yield after dilution, stock compensation as a share of revenue, capex against depreciation, and total asset growth. Aggressive expansion and under-investment can both weaken future returns, so both tails are penalized.'],
}

const METHODOLOGY_MODIFIERS = [
  ['sector_valuation_percentile', 'Sector-relative valuation', 'Being cheap for a utility and being cheap outright are different claims. A percentile against sector peers separates them.'],
  ['short_interest', 'Short interest', 'Crowded shorts are not automatically bearish, but unusually high and low short interest can carry useful cross-sectional information.'],
  ['insider_activity', 'Insider activity', 'SEC Form 4 open-market trades are split into routine and opportunistic. Scheduled trades score zero. Fresh clusters of irregular open-market buying score positively and decay over time.'],
  ['liquidity', 'Liquidity', 'A name you cannot exit without moving the price carries a real cost that fundamentals never show.'],
  ['expectations', 'Analyst expectations', 'Consensus is used only when the published minimum analyst coverage is present.'],
  ['macro_regime', 'Macro regime', 'FRED rates, inflation, labor, and yield-curve conditions are weighted by sector sensitivity and never replace company evidence.'],
  ['institutional_13f', 'Institutional 13F', 'A curated set of publicly traded, actively managed 13F filers – index funds and private-equity managers are excluded, since their position changes track index membership or take-private deals rather than conviction. Decayed by filing lag: a position disclosed 45+ days ago carries less weight than a fresh one.'],
  ['congressional_buying', 'Congressional buying', 'Reward-only. Disclosed Congressional stock purchases score a mild positive; a member’s first-ever trade in a company under a $2B market cap scores an additional bonus. Sales and non-buying never penalize.'],
  ['customer_concentration_risk', 'Customer concentration (shadow only)', 'ASC 280 customer-concentration disclosures, penalty-only. Not yet part of the published score – shown here, and in the challenger comparison, while tagging coverage across the scored universe is being measured.'],
  ['geographic_concentration', 'Geographic concentration (shadow only)', 'Revenue concentrated in a single non-domestic country, penalty-only. Not yet part of the published score, for the same reason as customer concentration – coverage and tag accuracy are still being checked against real filings.'],
]

const METHODOLOGY_DEFAULT_CAPABILITIES = {
  form4_insider_transactions: { status: 'available_next_refresh', source: 'SEC EDGAR', note: 'Free Form 4 parser is included in the pipeline.' },
  implied_vs_realized_volatility: { status: 'opt_in', source: 'Option chains + calculated returns', note: 'Enable options requests in the pipeline.' },
  analyst_revision_trends: { status: 'provider_required', note: 'Point-in-time estimate history is not supplied by the current providers.' },
  guidance_beat_miss_history: { status: 'provider_required', note: 'Requires contemporaneous consensus snapshots.' },
  backlog_growth: { status: 'available', source: 'SEC EDGAR XBRL', note: 'Remaining performance obligation, read from dimensional XBRL contexts.' },
  institutional_13f_changes: { status: 'available', source: 'SEC EDGAR Form 13F-HR + OpenFIGI', note: 'Curated, publicly traded, actively managed filers only; decayed by filing lag.' },
  congressional_buying: { status: 'available', source: 'STOCK Act disclosures', note: 'Reward-only; disclosed purchases, with a bonus for a first-ever trade in a small company.' },
  customer_concentration_risk: { status: 'shadow_only', source: 'SEC EDGAR XBRL', note: 'ASC 280 customer concentration. Challenger-only pending tagging-coverage measurement.' },
  fx_exposure: { status: 'shadow_only', source: 'SEC EDGAR XBRL', note: 'Single-country revenue concentration. Challenger-only pending measurement.' },
}

function methodologyModifierRangeText(config = {}) {
  const positive = config.max_points
  const negative = config.max_penalty
  if (typeof positive === 'number' && typeof negative === 'number') return `+${positive} / -${negative} points. `
  if (typeof positive === 'number') return `Up to +${positive} points. `
  if (typeof negative === 'number') return `Up to -${negative} points. `
  return ''
}

function downloadTextFile(filename, content, mime) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function MethodologySection({ data, loading, Container }) {
  const [downloadStatus, setDownloadStatus] = useState(null)
  if (loading) return <div role="status" aria-live="polite">Loading…</div>

  const blend = data?.methodology?.weights
  const blendEntries = Object.entries(blend || {}).filter(([, value]) => typeof value === 'number')
  const categoryWeights = data?.methodology?.fundamental_weights || {}
  const modifierConfig = data?.methodology?.modifiers || {}
  const version = data?.model_metadata
  const capabilities = data?.capability_status || METHODOLOGY_DEFAULT_CAPABILITIES

  const handleDownload = () => {
    try {
      downloadTextFile('APP-COMPLETE-BREAKDOWN.md', appBreakdownMd, 'text/markdown')
      downloadTextFile('MASTER-METHODOLOGY.md', masterMethodologyMd, 'text/markdown')
      setDownloadStatus('Download started')
    } catch {
      setDownloadStatus('Download failed')
    }
    setTimeout(() => setDownloadStatus(null), 2500)
  }

  return (
    <div data-testid="methodology-section">
      <Container {...cap('export.evidence.methodology-download-docs')}>
        <button type="button" onClick={handleDownload}>Download full docs (.md)</button>
        {downloadStatus && <p role="status">{downloadStatus}</p>}
      </Container>

      <Container {...cap('figure.evidence.methodology-weight-stack')}>
        {blendEntries.length ? (
          <div data-testid="weight-stack">
            {blendEntries.map(([key, value]) => {
              const pct = Math.round(value * 100)
              return <div key={key}>{pct}% {METHODOLOGY_COMPONENT_LABEL[key] || key.replace(/_/g, ' ')}</div>
            })}
          </div>
        ) : (
          <p {...cap('state.evidence.methodology-pending-refresh')}>The scoring blend will appear after the first published research refresh.</p>
        )}
      </Container>

      <Container {...cap('figure.evidence.methodology-category-cards')}>
        {Object.entries(METHODOLOGY_CATEGORIES).map(([key, [title, body]]) => (
          <article key={key}>
            <h3>{title}{categoryWeights[key] != null ? ` · ${Math.round(categoryWeights[key] * 100)}%` : ''}</h3>
            <p>{body}</p>
          </article>
        ))}
      </Container>

      <Container {...cap('figure.evidence.methodology-modifiers-list')}>
        <p>Applied after the published blend and reported on every company. They refine a ranking; they are capped so they can never outweigh the fundamental evidence behind it.</p>
        <ul>
          {METHODOLOGY_MODIFIERS.map(([key, title, body]) => (
            <li key={key}><b>{title}</b>: {methodologyModifierRangeText(modifierConfig[key])}{body}</li>
          ))}
        </ul>
      </Container>

      <Container {...cap('figure.evidence.methodology-version-card')}>
        <dl>
          <div><dt>Semantic version</dt><dd>{version?.semantic_version || data?.model_version || 'Pending refresh'}</dd></div>
          <div><dt>Git commit</dt><dd>{version?.git_commit_sha?.slice(0, 12) || 'Pending refresh'}</dd></div>
          <div><dt>Config hash</dt><dd>{version?.config_hash?.slice(0, 12) || 'Pending refresh'}</dd></div>
          <div><dt>Generated</dt><dd>{version?.generated_at ? new Date(version.generated_at).toLocaleString() : 'Pending refresh'}</dd></div>
        </dl>
      </Container>

      <Container {...cap('figure.evidence.methodology-active-vs-shadow')}>
        <p>
          The active legacy policy requires agreement across business fundamentals, market
          behaviour, and positioning or sentiment before it trims or sells. Its fixed
          factor-count sizing remains visible while the replacement policy is evaluated.
        </p>
        <p {...cap('disclosure.evidence.methodology-shadow-not-controlling')}>
          The shadow policy keeps the company thesis, one-to-three-month timeliness, portfolio
          fit, and user position rules separate. A stop can trigger a position exit without
          turning the company into a thesis sell. Company scores are shrunk toward neutral when
          confidence is low, and trim size reflects severity, confidence, concentration,
          liquidity, tax friction, and minimum economic trade size. Shadow results do not
          control production actions.
        </p>
      </Container>

      <Container {...cap('figure.evidence.methodology-benchmark-rationale')}>
        <p>
          Every hypothetical return is measured against the same dollars invested in the S&amp;P
          500 over the same window, because the honest question is not “did this go up” but
          “did this beat the index I could have bought instead”.
        </p>
        <p {...cap('disclosure.evidence.methodology-pre-window-unavailable')}>
          Positions bought before the published benchmark window are shown as unavailable rather
          than compared against the wrong entry price.
        </p>
      </Container>

      <Container {...cap('figure.evidence.methodology-capability-grid')}>
        {Object.entries(capabilities).map(([key, capability]) => (
          <article key={key}>
            <span>{(capability.status || '').replace(/_/g, ' ')}</span>
            <h4>{key.replace(/_/g, ' ')}</h4>
            {capability.source && <b>{capability.source}</b>}
            <p>{capability.note}</p>
          </article>
        ))}
      </Container>

      <p {...cap('disclosure.evidence.methodology-blend-from-snapshot')}>
        Read the blend from the snapshot so this page cannot drift from the config that produced
        the scores it is describing.
      </p>
      <div {...cap('disclosure.evidence.methodology-general-research-fallback')} className="disclaimer">
        {data?.disclaimer || 'General research only. Not individualized investment advice.'}
      </div>
    </div>
  )
}

// =================================================================================================
// Glossary (`?section=glossary`) — CAPABILITY-LEDGER.md §10e. GLOSSARY_GROUPS is reproduced
// verbatim from src/pages/Glossary.jsx's GROUPS const (not fabricated — relocated, per the
// medium-agnostic architecture, alongside the same live scoring-weight substitution below).
// =================================================================================================

const GLOSSARY_GROUPS = [
  {
    title: 'Valuation',
    note: 'What you are paying, relative to what the business actually produces.',
    terms: [
      ['PEG ratio', 'A P/E ratio divided by expected earnings growth. It answers "is this multiple justified by how fast earnings are growing," which the P/E ratio alone cannot.'],
      ['Forward P/E', 'Share price divided by next year’s expected earnings per share, rather than the year just reported. Lower generally means cheaper, holding growth and risk constant.'],
      ['EV/EBITDA', 'Enterprise value (market cap plus debt, minus cash) divided by operating profit before interest, tax, depreciation, and amortization. Unlike P/E, it is neutral to how a company is financed, so a heavily indebted company cannot look artificially cheap.'],
      ['EV/FCF', 'Enterprise value divided by free cash flow. The same capital-structure-neutral idea as EV/EBITDA, but measured against actual cash generated instead of an accounting profit figure.'],
      ['P/S (Price-to-sales)', 'Share price divided by revenue per share. Useful for early-stage or low-margin companies where earnings are small, negative, or noisy.'],
      ['P/B (Price-to-book)', 'Share price divided by reported book (accounting) value per share.'],
      ['Price-to-tangible-book', 'Price-to-book with goodwill and other intangible assets stripped out of book value. The more honest version for banks and insurers, whose goodwill can otherwise flatter the ratio.'],
      ['Dividend yield', 'Annual dividend per share divided by share price – the income return you get just for holding, before any price change.'],
      ['Enterprise value (EV)', 'The theoretical full takeover cost of a company: market capitalization plus total debt, minus cash on hand. It reflects what a buyer would actually have to pay, including the debt they’d assume.'],
    ],
  },
  {
    title: 'Profitability & cash',
    note: 'Whether the business earns well and whether the reported earnings show up as real cash.',
    terms: [
      ['ROIC (Return on invested capital)', 'Operating profit after tax divided by all the capital funding the business – debt and equity combined. Leverage cannot inflate it the way it inflates ROE, which makes it a cleaner read on how good the underlying business actually is.'],
      ['ROE (Return on equity)', 'Net income divided by shareholder equity. Taking on more debt can push this number up without the business getting any better, so it is best read alongside ROIC, not alone.'],
      ['Cash conversion', 'Free cash flow divided by net income. A ratio well under 100% is a flag that reported profit isn’t fully showing up as cash – often a sign of aggressive accounting.'],
      ['FCF yield (Free-cash-flow yield)', 'Free cash flow divided by market value. Similar in spirit to earnings yield, but built on cash the business actually generated rather than an accounting profit figure.'],
      ['Operating margin', 'Operating profit divided by revenue – what is left after running the core business, before interest and tax.'],
      ['Margin trend', 'The year-over-year change in operating margin. A mediocre margin that is improving is a meaningfully different story than the same margin that is sliding.'],
      ['Incremental margin', 'The profit earned on each new dollar of revenue growth, rather than on revenue overall. It shows whether growth is actually profitable.'],
      ['Net margin (Profit margin)', 'Bottom-line net income divided by revenue – what is left for shareholders after every expense, including interest and tax.'],
    ],
  },
  {
    title: 'Financial health',
    note: 'Whether the company can comfortably service its obligations, not just how big its debt looks on paper.',
    terms: [
      ['Interest coverage', 'Operating profit divided by interest expense – how many times over the company could pay the interest it owes from operating profit alone. Answers the "can they actually afford this debt" question that debt-to-equity cannot.'],
      ['Net debt / EBITDA', 'Total debt minus cash, divided by EBITDA. Roughly: how many years of current operating profit it would take to pay off all net debt.'],
      ['Debt-to-equity', 'Total debt divided by shareholder equity – a basic leverage ratio. Read it alongside interest coverage, since a high ratio at a very low interest rate is a different risk than the same ratio at a high one.'],
      ['Current ratio', 'Current assets divided by current liabilities – whether short-term resources cover short-term bills. Below 1 means bills due within a year exceed the cash and near-cash on hand.'],
      ['Altman Z-score', 'A composite bankruptcy-risk score built from five accounting ratios. Above roughly 3 is considered the safe zone. Below roughly 1.8 signals meaningful distress risk.'],
    ],
  },
  {
    title: 'Accounting quality',
    note: 'The most commonly overlooked risk in a stock screen: whether reported profit is trustworthy.',
    terms: [
      ['Accruals ratio', '(Net income minus operating cash flow) divided by total assets. A persistently large gap between profit and cash is one of the most-studied predictors of future earnings disappointments and underperformance.'],
      ['Piotroski F-score', 'A nine-point checklist of profitability, leverage, and efficiency signals, each scored pass/fail and summed. Higher (toward 9) indicates broader fundamental strength. Below about 4 is weak.'],
      ['Days sales outstanding (DSO)', 'The average number of days it takes to collect payment after a sale. A rising trend can mean revenue is being booked before the cash actually arrives.'],
      ['Inventory days', 'The average number of days stock sits before it sells. A rising trend is the manufacturing and retail equivalent of the same warning DSO gives – demand may be softening faster than the income statement shows.'],
    ],
  },
  {
    title: 'Capital allocation',
    note: 'What management does with the cash the business generates – whether your ownership stake is growing or being quietly diluted.',
    terms: [
      ['Net buyback yield', 'The year-over-year change in share count, net of new shares issued, expressed as a percentage. Positive means your ownership stake grew even though you did nothing. Negative means dilution outpaced buybacks.'],
      ['Gross buyback yield', 'Cash spent on share repurchases divided by market value, before netting out new shares issued from options or compensation.'],
      ['Stock comp / revenue', 'Stock-based compensation as a share of revenue. This is a real dilution cost that does not appear as a cash expense on the income statement the way a cash salary would.'],
      ['Capex / depreciation', 'Capital expenditure divided by depreciation. A ratio under 1x means the company is spending less on new equipment and facilities than its existing assets are wearing out – a way of flattering near-term cash flow that can starve future competitiveness.'],
    ],
  },
  {
    title: 'Growth',
    terms: [
      ['Revenue growth', 'The year-over-year percentage change in total revenue.'],
      ['Earnings growth', 'The year-over-year percentage change in net income or earnings per share.'],
      ['FCF growth (3y)', 'The compound annual growth rate of free cash flow over the trailing three years – smoother than a single year-over-year figure.'],
    ],
  },
  {
    title: 'Ownership & positioning',
    note: 'Signals from who owns the stock and how it is being traded, separate from the financial statements.',
    terms: [
      ['Short interest', 'The percentage of a company’s tradable shares (its float) that are currently sold short. High short interest is not automatically bearish, but it raises the cost of being wrong if the short thesis fails.'],
      ['Days to cover', 'Total shares sold short divided by average daily trading volume – roughly how many trading days it would take for all short sellers to buy back their shares at normal volume. A high figure means any rally could be amplified by short sellers rushing to exit.'],
      ['Institutional ownership', 'The percentage of shares held by professional money managers (funds, pensions, endowments) rather than individual retail investors.'],
      ['Insider ownership', 'The percentage of shares held by a company’s own officers and directors.'],
      ['Analyst consensus', 'The average recommendation across covering analysts, typically on a 1 (strong buy) to 5 (strong sell) scale, so a lower number is more bullish.'],
      ['Target upside', 'The percentage gap between the average analyst price target and the current share price.'],
      ['Beta', 'A measure of how much a stock tends to move relative to the broader market. A beta above 1 means the stock has historically swung more than the market. Below 1 means less.'],
    ],
  },
  {
    title: 'Behaviour & tradability',
    note: 'Price trend, risk, and how easily a position can actually be bought or sold without moving the price.',
    terms: [
      ['Max drawdown', 'The deepest peak-to-trough decline in price over a given window (commonly one year here). It measures the worst pain an investor would have felt holding through the period, regardless of where the price ended up.'],
      ['Noise floor', 'How large a move against the index would have to be, over a given window, before it means anything for your particular portfolio. It is one standard error of your own tracking noise – the ordinary week-to-week wobble between you and the index – scaled to the length of the window. A +0.4% month against a ±2.4% floor is not a good month, it is a normal one, and the short-term tiles say so rather than reporting the number on its own and inviting a conclusion it cannot support. The floor grows with the square root of the window, which is why the same 2% means different things over a week and over a quarter.'],
      ['Current streak', 'How many consecutive recent observations your portfolio has finished ahead of (or behind) the index, and the calendar days those observations span. The day count matters because the underlying price history is not evenly spaced – five observations in a row can mean a week or a month depending on where in the history you are.'],
      ['Recent tracking risk', 'How much your portfolio has been moving independently of the index lately, annualized, shown against the same figure over a longer baseline. Rising above the baseline means your holdings have started behaving less like the market than usual – which is neither good nor bad in itself, but it is the quantity that sets the noise floor, so it tells you how much of any recent gap is likely to be luck.'],
      ['Active share', 'The share of your portfolio that differs from the index’s own holdings, position by position. 0% means you have effectively bought the index; 100% means you own nothing it owns. Unlike almost everything else on the page it needs no history at all – it is a fact about today’s weights – so it is readable from the first day you hold anything. It is only shown when enough of your holdings can be matched against published index constituents.'],
      ['Up capture / down capture', 'What share of the index’s gains your portfolio kept, and what share of its losses it took, measured separately over the periods the index rose and the periods it fell. Up 90 / down 60 means you keep most of the rallies while taking well under two thirds of the selloffs. Neither number means much on its own – a low up capture is the price you pay for a low down capture, and that trade can be a good one. Sharpe and information ratio blend both directions into a single figure, which is why they cannot tell a portfolio that wins by keeping up in rallies from one that wins by losing less in downturns.'],
      ['Capture spread', 'Up capture minus down capture. This is the number that settles whether the trade-off is working: positive means you keep more of the upside than you take of the downside, which is the entire justification for not just buying the index. Negative means the reverse – giving up the rallies and taking the falls anyway – and is the specific failure mode a cautious, low-beta portfolio is at risk of.'],
      ['Batting average', 'The share of calendar months in which your portfolio beat the index. It measures how *often* you win, where capture ratios measure how *much*, and the two can disagree sharply: a portfolio that wins four months in twelve with three enormous wins is a real strategy and a fragile one. The tile also shows how big a typical winning month is against a typical losing one, which is how a record below 50% can still be ahead overall. Counted monthly on purpose – a hit rate measured daily is a different and much less meaningful number.'],
      ['Longest underwater', 'The longest stretch your portfolio spent below its previous high-water mark, in calendar time rather than trading days. Maximum drawdown says how deep the hole was; this says how long you were in it, and those are very different experiences of the same percentage. A 20% fall recovered in three weeks and a 20% fall you sat in for fourteen months are not the same portfolio to live with, and duration is the part most people underestimate in advance.'],
      ['Acceleration vs S&P 500 (portfolio)', 'The same question asked of your whole portfolio rather than one holding: is the gap between your account and the index still widening? It compares the excess return your portfolio earned over the last quarter against the quarter before it, after subtracting the move your portfolio’s own beta says the market handed it – so a portfolio that only rose because the index rose does not read as accelerating. Deposits and withdrawals are netted out first, since money arriving in an account is not performance. Every other measure on that panel reports a level: how far ahead you are, how much risk you took. This one reports the change in it. A portfolio that beat the index by 8% last quarter and 1% this one is still ahead, and is losing the argument.'],
      ['Acceleration vs market', 'Whether a stock’s lead over the market is widening or narrowing, rather than how big that lead currently is. It compares the excess return earned over the most recent quarter against the quarter before it, after subtracting the move the stock’s own beta says the market handed it – so a high-beta name that only rose because the index rose does not read as accelerating. The result is quoted in standard errors (σ) of the stock’s own tracking noise, which is what lets a quiet utility and a volatile biotech be compared on the same scale: +1σ is a pickup one standard error larger than this stock’s ordinary week-to-week wobble. The most recent week is deliberately excluded, because very short-term moves tend to reverse. It is measured and displayed but carries no weight in the research score, pending evidence that it predicts anything.'],
      ['Volume confirmation', 'The ratio of trading volume on up days to volume on down days. A ratio below 1 means recent gains happened on lighter volume than recent declines – a rally that isn’t fully convincing yet.'],
      ['52-week high / low', 'The highest and lowest closing prices over the trailing year. Distance from these levels is a common (if rough) gauge of where a stock sits within its recent range.'],
      ['Volatility (annualized)', 'The annualized standard deviation of daily price changes – a statistical measure of how much a price bounces around, independent of direction.'],
      ['Implied volatility', 'The volatility level embedded in current option prices for the nearest listed expiry – the market’s forward-looking expectation of how much a stock will move.'],
      ['Realized volatility', 'The volatility a stock actually experienced over a recent window (commonly 20 trading days), calculated directly from historical price changes rather than inferred from option prices.'],
      ['Implied / realized vol ratio', 'Implied volatility divided by realized volatility. A ratio above 1x means options are pricing in more future movement than the stock has actually shown recently.'],
      ['Average dollar volume', 'Average daily trading volume multiplied by share price – how much money trades hands in a typical day. Low dollar volume means a position can be harder to exit without moving the price against you.'],
    ],
  },
  {
    title: 'Scoring & guidance',
    note: 'How the research score is built and how buy/hold/sell-style guidance is decided.',
    terms: [
      ['Research score', null],
      ['Confidence', 'A measure of how complete the underlying data was for a given score, not a measure of how good the company is. Missing key inputs lowers confidence even if the metrics that are available look strong.'],
      ['Buy', 'A shadow-policy entry classification: structural quality, timing, confidence, data quality, valuation, liquidity, and portfolio capacity all pass. It is distinct from Hold.'],
      ['Accumulate', 'The shadow policy permits gradual additions because business quality is strong and timing is improving, while concentration remains acceptable.'],
      ['Hold existing position', 'Evidence supports maintaining a position already owned. It does not mean the security meets today’s entry requirements.'],
      ['Watch', 'No action. Evidence is incomplete, mixed, weakly timed, or below the confidence needed for a prescriptive company decision.'],
      ['Trim', 'Reduce an existing position. The shadow policy names whether the cause is company deterioration, concentration, valuation, tactics, or risk budget and sizes the trade from context.'],
      ['Exit position', 'Close a held position under a namespaced stop, thesis, portfolio, or explicit user rule. A position exit does not automatically mean the company thesis failed.'],
      ['Avoid', 'Do not initiate a new position under current company evidence. This is not the same as selling a position already owned.'],
      ['Sell thesis', 'Verified structural or combined company evidence has invalidated the thesis, independently of the user’s cost basis.'],
      ['Agreement count', 'How many of the three independent factors (fundamentals, market behaviour, positioning/sentiment) currently agree in the same negative direction. Guidance only moves off Hold once two or more agree.'],
      ['Sector-relative valuation', 'A modifier (±3 points) based on how cheap or expensive a company is versus its own sector peers, rather than against the whole market. Being cheap for a utility and being cheap outright are different claims.'],
      ['Macro regime', 'A modifier (±3 points) built from interest rates, inflation, labor data, and the yield curve, weighted by how sensitive a given sector is to those conditions. It never replaces company-level evidence.'],
    ],
  },
  {
    title: 'Finances',
    note: 'Terms used on the Finances tab: budgeting, savings pools, and the retirement projection.',
    terms: [
      ['Leftover', 'Monthly income minus monthly expenses in the budget subsection – the amount available to save, invest, or split into pools.'],
      ['Auto-split pool', 'A named savings bucket with a target percentage. Logging a deposit divides that dollar amount across every pool in proportion to its percentage.'],
      ['Retirement simulation', 'A range built from 5,000 paths that resample consecutive 12-month blocks of historical returns. It uses portfolio history after three years, otherwise the selected benchmark, and reports percentiles plus the probability savings last through the planned withdrawal period. Simulated outcomes are not predictions.'],
      ['Nominal balance', 'A projected future balance in future dollars, not adjusted for inflation.'],
      ['Inflation-adjusted balance', 'A projected future balance restated in today’s purchasing power by discounting for assumed inflation – a more honest read of what the balance will actually buy.'],
      ['401(k) / 403(b)', 'An employer-sponsored retirement account with pre-tax (traditional) or after-tax (Roth) contributions, deducted straight from payroll. The 2026 IRS employee deferral limit is $24,500, plus a $8,000 catch-up at 50+ or $11,250 at ages 60–63.'],
      ['Roth IRA', 'An individual retirement account funded with after-tax dollars. Qualified withdrawals in retirement are tax-free. The 2026 IRS limit is $7,500, plus a $1,100 catch-up at 50+. Eligibility to contribute phases out at higher incomes.'],
      ['Traditional IRA', 'An individual retirement account funded with pre-tax dollars (subject to income and workplace-plan rules). Withdrawals in retirement are taxed as income. Shares the same 2026 IRS limit as a Roth IRA: $7,500, plus a $1,100 catch-up at 50+.'],
      ['HSA (Health Savings Account)', 'A triple-tax-advantaged account for medical expenses, available with a qualifying high-deductible health plan. 2026 IRS limits are $4,400 self-only or $8,750 family coverage, plus a $1,000 catch-up at 55+.'],
      ['Contribution limit', 'The maximum an account holder may contribute to a tax-advantaged account in a calendar year under IRS rules. Exceeding it can trigger excise taxes, so it is tracked separately from an account’s balance.'],
      ['Catch-up contribution', 'An additional amount the IRS allows account holders past a certain age to contribute on top of the standard limit, meant to help late savers close the gap before retirement.'],
    ],
  },
]

function GlossarySection({ data, loading, Container }) {
  const [query, setQuery] = useState('')
  if (loading) return <div role="status" aria-live="polite">Loading…</div>

  const normalized = query.trim().toLowerCase()
  const weights = data?.methodology?.weights || {}
  const blend = Object.entries(weights)
    .filter(([, value]) => typeof value === 'number')
    .map(([key, value]) => `${Math.round(value * 100)}% ${key.replace(/_/g, ' ')}`)
    .join(', ')
  const scoringDefinition = blend
    ? `The overall 0 to 100 company ranking uses ${blend}, then applies the capped modifiers published with the snapshot.`
    : 'The overall 0 to 100 company ranking uses the component weights in the latest published snapshot, then applies its capped modifiers.'

  const groups = GLOSSARY_GROUPS.map((group) => ({
    ...group,
    terms: group.terms.map(([term, definition]) => [term, term === 'Research score' ? scoringDefinition : definition]),
  }))

  const filtered = !normalized ? groups : groups
    .map((group) => ({
      ...group,
      terms: group.terms.filter(([term, definition]) => term.toLowerCase().includes(normalized) || definition.toLowerCase().includes(normalized)),
    }))
    .filter((group) => group.terms.length)

  const totalTerms = groups.reduce((sum, group) => sum + group.terms.length, 0)
  const shownTerms = filtered.reduce((sum, group) => sum + group.terms.length, 0)

  return (
    <div data-testid="glossary-section">
      <Container {...cap('control.evidence.glossary-search')}>
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search terms"
          placeholder='Search a term, e.g. "drawdown" or "PEG"'
        />
      </Container>
      <Container {...cap('figure.evidence.glossary-count')}>
        <span data-testid="glossary-count">{shownTerms} of {totalTerms} terms</span>
      </Container>
      <Container {...cap('figure.evidence.glossary-groups')}>
        {filtered.map((group) => (
          <section key={group.title}>
            <h3>{group.title}</h3>
            {group.note && <p>{group.note}</p>}
            <dl>
              {group.terms.map(([term, definition]) => (
                <div key={term} {...(term === 'Research score' ? cap('figure.evidence.glossary-research-score-def') : {})}>
                  <dt>{term}</dt><dd>{definition}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </Container>
      {!filtered.length && (
        <div {...cap('state.evidence.glossary-no-match')} data-testid="glossary-no-match">
          No terms matched “{query}”.
        </div>
      )}
      <div {...cap('disclosure.evidence.glossary-footer')} className="disclaimer">General research only. Not individualized investment advice.</div>
    </div>
  )
}

// =================================================================================================
// Screen shell
// =================================================================================================

/**
 * Absorbs LiveValidation, BacktestComparison, ShadowPortfolios, Methodology, and Glossary behind
 * `?section=` (see ROUTE-INVENTORY.md §2) — the destination that answers "should I trust this
 * model at all?" This shell renders the promotion/classification-B disclosure for real (closing
 * the docs-only gap noted in NOTES.md), the full SignalMetricsPanel embed for `validation`, and
 * the backtests/shadow/methodology/glossary sections against CAPABILITY-LEDGER.md §10 (Phase 2b).
 */
export default function EvidenceScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams] = useSearchParams()
  const section = EVIDENCE_SECTIONS.includes(searchParams.get('section')) ? searchParams.get('section') : 'validation'

  const { data: signalMetrics, loading: metricsLoading } = useData(section === 'validation' ? 'validation/signal_metrics.json' : null)
  const { data: researchEvidence } = useData(section === 'validation' ? 'validation/research_evidence.json' : null)

  const { data: comparisonData, loading: comparisonLoading } = useData(section === 'backtests' ? 'screens/backtest-comparison.json' : null)
  const { data: optionsBacktestData } = useData(section === 'backtests' ? 'screens/options-backtest.json' : null)

  const { data: shadowData, loading: shadowLoading } = useData(section === 'shadow' ? 'screens/shadow-portfolios.json' : null)
  const { data: reportData } = useData(section === 'shadow' ? 'report.json' : null)

  const { data: advisorData, loading: advisorLoading } = useData((section === 'methodology' || section === 'glossary') ? 'advisor.json' : null)

  const promotion = promotionDisclosure(researchEvidence)
  const buckets = section === 'validation' && signalMetrics ? splitBySampleRequirement(signalMetrics) : []

  if (section === 'validation' && metricsLoading) {
    return <div role="status" aria-live="polite">Loading…</div>
  }
  if (section === 'validation' && !signalMetrics) {
    return <div {...cap(EVIDENCE_IDS.icUnavailable)} role="alert">Signal metrics unavailable — run pipeline/signal_metrics.py.</div>
  }

  return (
    <div data-screen="evidence" data-section={section}>
      <Container {...cap(EVIDENCE_IDS.noSignalPromoted)}>
        <p data-testid="promotion-disclosure">{promotion.text}</p>
      </Container>
      {section === 'validation' && signalMetrics && (
        <Container {...cap(EVIDENCE_IDS.signalMetricsPanel)}>
          <span data-testid="metrics-summary">
            {signalMetrics.summary?.ready} ready · {signalMetrics.summary?.breached} breached of {signalMetrics.summary?.total}
          </span>
          {buckets.map((bucket) => {
            const openGroups = defaultOpenGroups(bucket)
            return (
              <section key={bucket.id} data-metrics-bucket={bucket.id}>
                <h3>{bucket.title}</h3>
                <p>{bucket.subtitle}</p>
                {bucket.groups.map((group) => {
                  const groupMessage = sharedStatusMessage(group.metrics)
                  return (
                    <details key={group.id} open={openGroups.has(group.id)}>
                      <summary>{group.letter ? `${group.letter} — ` : ''}{group.title || group.id} ({group.metrics.length})</summary>
                      {groupMessage && <p data-testid={`group-status-${group.id}`}>{groupMessage}</p>}
                      {group.metrics.map((metric) => (
                        <WallLabel key={metric.id} metric={metric} />
                      ))}
                    </details>
                  )
                })}
              </section>
            )
          })}
        </Container>
      )}

      {section === 'backtests' && (
        <BacktestsSection comparison={comparisonData} optionsBacktest={optionsBacktestData} loading={comparisonLoading} Container={Container} />
      )}

      {section === 'shadow' && (
        <ShadowSection shadowData={shadowData} reportData={reportData} loading={shadowLoading} Container={Container} />
      )}

      {section === 'methodology' && (
        <MethodologySection data={advisorData} loading={advisorLoading} Container={Container} />
      )}

      {section === 'glossary' && (
        <GlossarySection data={advisorData} loading={advisorLoading} Container={Container} />
      )}
    </div>
  )
}
