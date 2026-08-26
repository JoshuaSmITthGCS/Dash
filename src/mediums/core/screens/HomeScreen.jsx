import { lazy, Suspense } from 'react'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { canonicalArtifactState, provenanceOf, promotionDisclosure } from '../states.js'
import { cap } from '../capability.js'
import { HOME_IDS } from './capabilityIds.js'

// Lazy — the only Firebase-dependent part of Home (useAuth/useFirebasePortfolio, both of which
// statically import FirebaseAuthContext.jsx and its eager ~610 kB SDK init) is split out here so
// Home's cold /v2 load — the exact route budget.spec.mjs measures — never pays for it up front.
// See HomePortfolioPanel.jsx's own header comment (Phase 4, NOTES.md).
const HomePortfolioPanel = lazy(() => import('./HomePortfolioPanel.jsx'))

function PortfolioHeroFallback({ Skeleton }) {
  return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
}

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

  const { data: report, loading: reportLoading } = useData('report.json')
  const { data: signalMetrics } = useData('validation/signal_metrics.json')
  const { data: researchEvidence } = useData('validation/research_evidence.json')

  const promotion = promotionDisclosure(researchEvidence)
  const artifactState = canonicalArtifactState(report ? { status: 'success' } : null)
  const provenance = provenanceOf(report)
  const summary = signalMetrics?.summary
  const liveSample = signalMetrics?.live_sample

  if (reportLoading) {
    return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
  }
  if (!report?.research?.length) {
    return EmptyState
      ? <EmptyState reason="No advisor dataset is available yet." />
      : <div role="alert">No advisor dataset is available yet.</div>
  }

  return (
    <div data-screen="home">
      <Suspense fallback={<PortfolioHeroFallback Skeleton={Skeleton} />}>
        <HomePortfolioPanel report={report} />
      </Suspense>

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
