import { useMemo } from 'react'
import { AuthProvider as FirebaseAuthProvider, useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { enrichPortfolio, currentHoldingsSeries, selectPeriod, latestMarketDayReturn } from '../../../lib/portfolioAnalytics.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { liveTodayPortfolioReturn } from '../../../lib/afterHoursQuotes.js'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { HOME_IDS } from './capabilityIds.js'

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
 */
export default function HomePortfolioPanel({ report }) {
  return <FirebaseAuthProvider><HomePortfolioContent report={report} /></FirebaseAuthProvider>
}

function HomePortfolioContent({ report }) {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const Skeleton = manifest.components?.Skeleton

  const { currentUser } = useAuth()
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()

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
  const chart = useMemo(() => selectPeriod(holdingsSeries, '1M'), [holdingsSeries])
  const liveToday = useMemo(() => liveTodayPortfolioReturn(positions, priceData), [positions, priceData])
  const marketDayToday = useMemo(() => latestMarketDayReturn(holdingsSeries), [holdingsSeries])
  const today = liveToday.available ? liveToday : marketDayToday

  if (currentUser && portfolioLoading) {
    return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
  }

  return (
    <>
      {/* First-viewport item 1: portfolio value + today's delta + as-of line */}
      <Container primary {...cap(HOME_IDS.portfolioHero)}>
        {currentUser && positions.length ? (
          <>
            <strong data-testid="portfolio-value">
              {portfolio.totalValue != null ? `$${portfolio.totalValue.toFixed(2)}` : '–'}
            </strong>
            <span data-testid="portfolio-today">
              {today?.dollarReturn != null
                ? `${today.dollarReturn >= 0 ? '+' : ''}$${today.dollarReturn.toFixed(2)} (${today.returnPct?.toFixed(2)}%) today`
                : 'Today’s move is still building.'}
            </span>
          </>
        ) : (
          <span>Sign in and add holdings to see your portfolio value here.</span>
        )}
        <span {...cap(HOME_IDS.asOfEyebrow)} data-testid="as-of">
          Latest close · {report?.generated_at ? new Date(report.generated_at).toLocaleDateString() : '–'} · {report?.research?.length ?? 0} names covered
        </span>
      </Container>

      {/* First-viewport item 2: growth chart of current holdings */}
      <Container {...cap(HOME_IDS.growthChart)}>
        {chart ? (
          <div data-testid="growth-chart" data-points={chart.values.length}>
            Current holdings, {chart.period}: {chart.returnPct != null ? `${chart.returnPct.toFixed(2)}%` : '–'}
          </div>
        ) : (
          <span data-testid="growth-chart-empty">
            1M history is still building — two saved portfolio observations are needed.
          </span>
        )}
      </Container>
    </>
  )
}
