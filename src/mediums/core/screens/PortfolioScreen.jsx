import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { AuthProvider as FirebaseAuthProvider } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'
import { enrichPortfolio } from '../../../lib/portfolioAnalytics.js'
import { buildPortfolioPriceData, mergePositionSnapshots } from '../../../lib/portfolioPosition.js'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { PORTFOLIO_IDS } from './capabilityIds.js'

export const PORTFOLIO_VIEWS = Object.freeze(['summary', 'performance', 'data', 'diversification', 'insights', 'finances', 'planning'])

/**
 * Absorbs the five existing /portfolio/* routes plus Finances and Planning behind
 * `?view=` (see ROUTE-INVENTORY.md §2 and CAPABILITY-LEDGER.md §4-8). This shell renders the
 * `summary` view's KPI row for real; the other six views' full capability sets (performance's
 * TWR/reconciliation bridge, data-overview's export surface and 64-metric embed,
 * diversification's factor regression, insights' share flow, finances' budget/pools/retirement
 * tabs, planning's levers) port in per medium in Phase 2b against their own ledger sections.
 *
 * Lazy-loaded from MediumShell.jsx (Phase 4, NOTES.md) since it's entirely gated behind
 * useFirebasePortfolio() — /v2's root (MediumApp.jsx) never mounts <FirebaseAuthProvider>, so
 * this chunk provides its own, same pattern as HomePortfolioPanel.jsx.
 */
export default function PortfolioScreen() {
  return <FirebaseAuthProvider><PortfolioScreenContent /></FirebaseAuthProvider>
}

function PortfolioScreenContent() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams] = useSearchParams()
  const view = PORTFOLIO_VIEWS.includes(searchParams.get('view')) ? searchParams.get('view') : 'summary'

  const { data: report, loading: reportLoading } = useData('report.json')
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()

  const priceData = useMemo(() => {
    if (!report) return {}
    const published = buildPortfolioPriceData(report.screen_universe || [], report.portfolio_coverage || [], report.research || [])
    return mergePositionSnapshots(published, positions, report.generated_at)
  }, [report, positions])

  const portfolio = useMemo(() => enrichPortfolio(positions, priceData), [positions, priceData])

  if (reportLoading || portfolioLoading) {
    return <div {...cap(PORTFOLIO_IDS.loading)} role="status" aria-live="polite">Loading…</div>
  }

  return (
    <div data-screen="portfolio" data-view={view}>
      <Container {...cap(PORTFOLIO_IDS.kpiRow)}>
        {positions.length ? (
          <>
            <strong data-testid="invested-value">{portfolio.totalValue != null ? `$${portfolio.totalValue.toFixed(2)}` : '–'}</strong>
            <span data-testid="gain">{portfolio.gain != null ? `${portfolio.gain >= 0 ? '+' : ''}$${portfolio.gain.toFixed(2)}` : '–'}</span>
          </>
        ) : (
          <span>No positions yet. Add a position to start tracking.</span>
        )}
      </Container>
    </div>
  )
}
