import { useMemo, useState } from 'react'
import { AuthProvider as FirebaseAuthProvider, useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { enrichPortfolio, currentHoldingsSeries, selectPeriod, latestMarketDayReturn } from '../../../lib/portfolioAnalytics.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { liveTodayPortfolioReturn } from '../../../lib/afterHoursQuotes.js'
import { dailyMoveForPosition } from '../../../lib/marketPresentation.js'
import { signedPct } from '../../../lib/formatters.js'
import { usePreferences } from '../../../lib/PreferencesContext.jsx'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { HOME_IDS } from './capabilityIds.js'

const PERIODS = ['1H', '1D', '1W', '1M', '3M', '1Y']
const PERIOD_LABELS = { '1H': 'Last hour', '1D': 'Today', '1W': 'Week', '1M': 'Month', '3M': '3 months', '1Y': 'Year' }

/**
 * The portfolio-value hero and growth-chart items from Home's first viewport (Container items
 * 1-2) — split out of HomeScreen.jsx and lazy-loaded from there (Phase 4, NOTES.md) because this
 * is the only Firebase-dependent part of Home: useAuth() and useFirebasePortfolio() both
 * statically import FirebaseAuthContext.jsx, which eagerly initializes the whole Firebase SDK
 * (~610 kB) at module-load time. Keeping that import out of HomeScreen.jsx's own static graph is
 * what lets Home's cold /v2 load stay under budget.spec.mjs's 500 kB ceiling. Item 3 (the
 * provenance strip) needs no Firebase data and stays in HomeScreen.jsx directly.
 *
 * /v2's own root (MediumApp.jsx) never mounts <FirebaseAuthProvider> — that's the whole point of
 * the deferral — so this chunk provides its own, wrapping the part of the tree that actually
 * calls useAuth()/useFirebasePortfolio(). Costs nothing extra: AuthProvider is the other named
 * export of the same FirebaseAuthContext.jsx module useFirebasePortfolio.js already pulls in.
 * usePreferences() is cheap to add alongside it — PreferencesContext.jsx has no Firebase import
 * of its own, and both mediums roots already mount <PreferencesProvider> above App.jsx/
 * MediumApp.jsx in main.jsx, so it costs nothing extra here either.
 */
export default function HomePortfolioPanel({ report }) {
  return <FirebaseAuthProvider><HomePortfolioContent report={report} /></FirebaseAuthProvider>
}

function HomePortfolioContent({ report }) {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const ControlComponent = manifest.components?.Control
  const Skeleton = manifest.components?.Skeleton

  const { currentUser, authError, retryAuth } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { preferences, updatePreferences } = usePreferences()

  const [period, setPeriod] = useState(preferences.defaultChartPeriod && PERIODS.includes(preferences.defaultChartPeriod) ? preferences.defaultChartPeriod : '1M')
  const [holdingsSort, setHoldingsSort] = useState('day')

  const priceData = useMemo(() => {
    if (!report) return {}
    const published = buildPortfolioPriceData(report.screen_universe || [], report.portfolio_coverage || [], report.research || [])
    return mergePositionSnapshots(published, positions, report.generated_at)
  }, [report, positions])

  const portfolio = useMemo(() => enrichPortfolio(positions, priceData), [positions, priceData])
  const holdingsSeries = useMemo(
    () => currentHoldingsSeries(positions, priceData, report?.benchmark_history?.dates || []),
    [positions, priceData, report],
  )
  const chart = useMemo(() => selectPeriod(holdingsSeries, period), [holdingsSeries, period])
  const liveToday = useMemo(() => liveTodayPortfolioReturn(positions, priceData), [positions, priceData])
  const marketDayToday = useMemo(() => latestMarketDayReturn(holdingsSeries), [holdingsSeries])
  const today = liveToday.available ? liveToday : marketDayToday

  const rankedHoldings = useMemo(() => portfolio.positions
    .map((position) => ({ ...position, move: dailyMoveForPosition(position) }))
    .sort((left, right) => holdingsSort === 'allocation'
      ? (right.allocationPct ?? -Infinity) - (left.allocationPct ?? -Infinity)
      : (right.move.pct ?? -Infinity) - (left.move.pct ?? -Infinity))
    .slice(0, 5), [portfolio.positions, holdingsSort])

  const privacyMode = Boolean(preferences.privacyMode)
  const money = (value) => value == null ? '–' : privacyMode ? '••••' : `$${value.toFixed(2)}`

  const changePeriod = (next) => { setPeriod(next); updatePreferences({ defaultChartPeriod: next }) }

  if (currentUser && portfolioLoading) {
    return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
  }

  return (
    <>
      {/* First-viewport item 1: portfolio value + today's delta + as-of line */}
      <Container primary {...cap(HOME_IDS.portfolioHero)}>
        {ControlComponent ? (
          <ControlComponent
            as="button" type="button" capId="control.home.privacy-eye"
            pressed={privacyMode}
            aria-label={privacyMode ? 'Show balances' : 'Hide balances'}
            onClick={() => updatePreferences({ privacyMode: !privacyMode })}
          >
            {privacyMode ? 'Show balances' : 'Hide balances'}
          </ControlComponent>
        ) : (
          <button
            type="button" {...cap('control.home.privacy-eye')}
            aria-pressed={privacyMode}
            aria-label={privacyMode ? 'Show balances' : 'Hide balances'}
            onClick={() => updatePreferences({ privacyMode: !privacyMode })}
          >
            {privacyMode ? 'Show balances' : 'Hide balances'}
          </button>
        )}

        {!currentUser ? (
          <div {...cap('state.home.cloud-offline')}>
            <strong>Cloud portfolio is offline</strong>
            <p>{authError || 'Firebase is connecting to your solo workspace.'}</p>
            <button type="button" onClick={retryAuth}>Reconnect Firebase</button>
          </div>
        ) : !positions.length ? (
          <div {...cap('state.home.no-holdings')}>
            <strong>Add holdings to unlock your report</strong>
            <p>Portfolio analytics appear after holdings and per-share cost basis are available.</p>
          </div>
        ) : (
          <>
            <strong data-testid="portfolio-value">{money(portfolio.totalValue)}</strong>
            <span data-testid="portfolio-today">
              {today?.dollarReturn != null
                ? `${today.dollarReturn >= 0 ? '+' : ''}${money(Math.abs(today.dollarReturn))} (${signedPct(today.returnPct, 2)}) today`
                : 'Today’s move is still building.'}
            </span>

            <div data-testid="top-5-holdings">
              <label>
                <span>Rank holdings by</span>
                <select
                  {...cap('control.home.top5-rank-mode')}
                  value={holdingsSort}
                  onChange={(event) => setHoldingsSort(event.target.value)}
                >
                  <option value="day">Today’s performance</option>
                  <option value="allocation">Biggest allocation</option>
                </select>
              </label>
              <ol>
                {rankedHoldings.map((position, index) => (
                  <li key={position.id || position.ticker}>
                    <span>{index + 1}</span>
                    <b>{position.ticker}</b>
                    <small>{position.allocationPct == null ? 'Allocation pending' : `${position.allocationPct.toFixed(1)}% allocation`}</small>
                    <span>{signedPct(position.move.pct, 2)}</span>
                  </li>
                ))}
              </ol>
            </div>
          </>
        )}

        <span {...cap(HOME_IDS.asOfEyebrow)} data-testid="as-of">
          Latest close · {report?.generated_at ? new Date(report.generated_at).toLocaleDateString() : '–'} · {report?.research?.length ?? 0} names covered
        </span>
      </Container>

      {/* First-viewport item 2: growth chart of current holdings */}
      <Container {...cap(HOME_IDS.growthChart)}>
        <label>
          <span>Portfolio performance</span>
          <select {...cap('control.home.chart-period')} value={period} onChange={(event) => changePeriod(event.target.value)}>
            {PERIODS.map((item) => <option key={item} value={item}>{PERIOD_LABELS[item]}</option>)}
          </select>
        </label>
        {chart ? (
          <div data-testid="growth-chart" data-points={chart.values.length}>
            Current holdings, {chart.period}: {chart.returnPct != null ? signedPct(chart.returnPct) : '–'}
          </div>
        ) : (
          <span data-testid="growth-chart-empty" {...cap('state.home.chart-unavailable')}>
            {PERIOD_LABELS[period] || period} history is still building — two saved portfolio observations are needed.
          </span>
        )}
      </Container>

      <p {...cap('disclosure.home.methodology-footer')}>
        Balances use the latest stored closes. Historical portfolio lines apply current
        quantities to past closes and do not reconstruct trades, deposits, withdrawals, taxes,
        fees, or dividends. General research only.
      </p>
    </>
  )
}
