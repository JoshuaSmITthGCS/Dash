import { useMemo } from 'react'
import { useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { useData } from '../../../lib/useData.js'
import { enrichPortfolio, currentHoldingsSeries, selectPeriod, latestMarketDayReturn } from '../../../lib/portfolioAnalytics.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { liveTodayPortfolioReturn } from '../../../lib/afterHoursQuotes.js'
import { useMedium } from '../MediumContext.jsx'
import { canonicalArtifactState, provenanceOf, promotionDisclosure } from '../states.js'
import { cap } from '../capability.js'
import { HOME_IDS } from './capabilityIds.js'

/**
 * The primary destination. Renders the Phase 0 first-viewport recommendation
 * (ROUTE-INVENTORY.md §3): portfolio value + today's delta + as-of line, then a growth chart of
 * current holdings vs. the default benchmark, then the live evidence/provenance strip. Every
 * medium renders this same data through its own `components.Container`/`LabelFrame` — nothing
 * here is medium-specific.
 *
 * Scope note (NOTES.md): this is the current-holdings-applied-to-published-closes computation
 * Dashboard.jsx already uses for its own hero, not yet the full time-weighted-return chart named
 * as the ideal in DESIGN.md's first-viewport recommendation — porting the live-quote overlay and
 * TWR computation is follow-on work, tracked in NOTES.md rather than half-implemented here.
 */
export default function HomeScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const Skeleton = manifest.components?.Skeleton
  const EmptyState = manifest.components?.EmptyState

  const { currentUser } = useAuth()
  const { data: report, loading: reportLoading } = useData('report.json')
  const { data: signalMetrics } = useData('validation/signal_metrics.json')
  const { data: researchEvidence } = useData('validation/research_evidence.json')
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

  const promotion = promotionDisclosure(researchEvidence)
  const artifactState = canonicalArtifactState(report ? { status: 'success' } : null)
  const provenance = provenanceOf(report)
  const summary = signalMetrics?.summary
  const liveSample = signalMetrics?.live_sample

  if (reportLoading || (currentUser && portfolioLoading)) {
    return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
  }
  if (!report?.research?.length) {
    return EmptyState
      ? <EmptyState reason="No advisor dataset is available yet." />
      : <div role="alert">No advisor dataset is available yet.</div>
  }

  return (
    <div data-screen="home">
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
          Latest close · {report.generated_at ? new Date(report.generated_at).toLocaleDateString() : '–'} · {report.research.length} names covered
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

      {/* First-viewport item 3: the live evidence/provenance strip */}
      <Container {...cap(HOME_IDS.provenanceStrip)}>
        <span data-testid="evidence-strip">
          {summary ? `${summary.ready} ready · ${summary.breached} breached` : '– ready · – breached'}
          {liveSample ? ` · ${liveSample.days}d live` : ''}
          {provenance.semanticVersion ? ` · model ${provenance.semanticVersion}` : ''}
        </span>
        <p data-testid="promotion-disclosure">{promotion.text}</p>
        {artifactState.reason && <p data-testid="artifact-reason">{artifactState.reason}</p>}
      </Container>
    </div>
  )
}
