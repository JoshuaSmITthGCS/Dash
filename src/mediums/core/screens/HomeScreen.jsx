import { lazy, Suspense } from 'react'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { canonicalArtifactState, provenanceOf, promotionDisclosure } from '../states.js'
import { cap } from '../capability.js'
import { HOME_IDS } from './capabilityIds.js'
import { signedPct } from '../../../lib/formatters.js'
import { rankBreakoutInProgress, rankValueTurnarounds, rankMomentum, rankReversal, rankGrowingEtfs } from '../../../lib/researchScreens.js'

// Lazy — the only Firebase-dependent part of Home (useAuth/useFirebasePortfolio, both of which
// statically import FirebaseAuthContext.jsx and its eager ~610 kB SDK init) is split out here so
// Home's cold /v2 load — the exact route budget.spec.mjs measures — never pays for it up front.
// See HomePortfolioPanel.jsx's own header comment (Phase 4, NOTES.md).
const HomePortfolioPanel = lazy(() => import('./HomePortfolioPanel.jsx'))

function PortfolioHeroFallback({ Skeleton }) {
  return Skeleton ? <Skeleton /> : <div role="status" aria-live="polite">Loading…</div>
}

// figure.home.top-signal — the highest-scoring published company, report.json only (no
// portfolio/Firebase dependency), so this renders directly on HomeScreen rather than inside the
// lazy portfolio panel. `report.research` is already sorted descending by score in the published
// artifact, but the leader is re-derived by an explicit max rather than trusting that ordering.
function TopSignal({ report, Container }) {
  const leader = report.research.reduce(
    (best, row) => (best == null || (row.score ?? -Infinity) > (best.score ?? -Infinity) ? row : best),
    null,
  )
  if (!leader) return null
  return (
    <Container {...cap('figure.home.top-signal')} aria-label="Top research signal">
      <span className="eyebrow">Top signal</span>
      <h3 data-testid="top-signal-ticker">{leader.ticker}</h3>
      <p data-testid="top-signal-name">{leader.name}</p>
      <strong data-testid="top-signal-score">{leader.score}/100{leader.stance ? ` · ${leader.stance}` : ''}</strong>
      <p data-testid="top-signal-strength">{leader.strengths?.[0] || 'Highest-scoring published company in the latest evidence run.'}</p>
    </Container>
  )
}

// One card within the figure.home.focused-screen-cards figure — mirrors FocusedScreenCard /
// InsideInformationCard from src/pages/Dashboard.jsx (read-only reference), reimplemented without
// importing from src/pages or src/components (ESLint forbids that outside Classic).
function ScreenCardBody({ rows, loading, metric, emptyText }) {
  if (loading) {
    return <div role="status" {...cap('state.home.screen-card-loading')}>Loading this screen on the Report…</div>
  }
  if (!rows.length) {
    return <div {...cap('state.home.screen-card-empty')}>{emptyText}</div>
  }
  return (
    <ol data-testid="screen-card-rows">
      {rows.map((row, index) => {
        const detail = metric(row)
        return (
          <li key={row.ticker}>
            <span>#{index + 1}</span>
            <b>{row.ticker}</b>
            {row.name && <small>{row.name}</small>}
            {detail && <span>{detail.label} {signedPct(detail.value)}</span>}
          </li>
        )
      })}
    </ol>
  )
}

function FocusedScreens({ report, etfData, etfLoading, Container, SectionHeading }) {
  const screenRows = [...new Map(
    [...(report.research || []), ...(report.screen_universe || [])].map((row) => [row.ticker, row]),
  ).values()]
  const cards = [
    { id: 'fast-growth', title: 'Fast growth breakouts', kicker: 'Fast growth', note: 'Sharp acceleration this week', rows: rankBreakoutInProgress(screenRows, 3), metric: (row) => ({ label: '5 days', value: row.screen.weekReturn }) },
    { id: 'quality-value', title: 'Value near 52-week lows', kicker: 'Value turnarounds', note: 'Quality plus a positive latest week', rows: rankValueTurnarounds(screenRows, 3), metric: (row) => ({ label: 'Above low', value: row.screen.aboveLow }) },
    { id: 'momentum', title: 'Recent momentum', kicker: 'Momentum', note: 'Positive week and month', rows: rankMomentum(screenRows, 3), metric: (row) => ({ label: '20 days', value: row.screen.monthReturn }) },
    { id: 'matrix', title: 'Short-term reversals', kicker: 'Reversal', note: '20-day pullback turning up', rows: rankReversal(screenRows, 3), metric: (row) => ({ label: 'This week', value: row.screen.weekReturn }) },
    { id: 'etfs', title: 'Top ETFs', kicker: 'Fund screens', note: 'Performance, risk, cost and liquidity', rows: rankGrowingEtfs(etfData?.etfs || [], 3), metric: (row) => ({ label: '1 year', value: row.returns?.['1y'] }), loading: etfLoading },
  ]
  return (
    <Container {...cap('figure.home.focused-screen-cards')} aria-labelledby="focused-screens-title">
      <SectionHeading id="focused-screens-title">Fast growth, value, momentum, reversals, and ETFs</SectionHeading>
      <div data-testid="focused-screen-grid">
        {cards.map((screen) => (
          <article key={screen.id} data-screen-card={screen.id}>
            <header><span>{screen.kicker}</span><h4>{screen.title}</h4><small>{screen.note}</small></header>
            <ScreenCardBody rows={screen.rows} loading={Boolean(screen.loading)} metric={screen.metric} emptyText="No name clears this screen in the latest report." />
          </article>
        ))}
      </div>
    </Container>
  )
}

// figure.home.inside-information-card — Congress + institutional 13F disclosed-positioning
// preview, from the precomputed screens/inside-information.json artifact.
function InsideInformation({ insideInformation, insideInformationLoading, Container }) {
  const rows = insideInformation?.results?.slice(0, 3) || []
  const flagSummary = (row) => [
    row.institutional_flag === 'CLUSTER_ACCUMULATION' && 'Managers accumulating',
    row.institutional_flag === 'CLUSTER_DISTRIBUTION' && 'Managers distributing',
    row.congress_flags?.length ? 'Congressional cluster' : null,
  ].filter(Boolean).join(' · ') || 'Notable disclosed activity'
  return (
    <Container {...cap('figure.home.inside-information-card')} aria-label="Disclosed positioning">
      <header><span>Disclosed positioning</span><h4>Congress + institutional 13F</h4><small>Rare or flagged activity only</small></header>
      {insideInformationLoading ? (
        <div role="status" {...cap('state.home.screen-card-loading')}>Loading this screen on the Report…</div>
      ) : rows.length ? (
        <ol data-testid="inside-information-rows">
          {rows.map((row, index) => <li key={row.ticker}><span>#{index + 1}</span><b>{row.ticker}</b><small>{flagSummary(row)}</small></li>)}
        </ol>
      ) : (
        <div {...cap('state.home.no-notable-activity')}>No notable disclosed activity right now.</div>
      )}
    </Container>
  )
}

/**
 * The primary destination. Renders the Phase 0 first-viewport recommendation
 * (ROUTE-INVENTORY.md §3): portfolio value + today's delta + as-of line, then a growth chart of
 * current holdings vs. the default benchmark, then the live evidence/provenance strip, then the
 * report-json/screens-derived figures that don't depend on Firebase (top signal, focused
 * screens, disclosed positioning). Every medium renders this same data through its own
 * `components.Container`/`LabelFrame` — nothing here is medium-specific.
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
  const SectionHeading = manifest.components?.SectionHeading || 'h2'

  const { data: report, loading: reportLoading } = useData('report.json')
  const { data: signalMetrics } = useData('validation/signal_metrics.json')
  const { data: researchEvidence } = useData('validation/research_evidence.json')
  const { data: etfData, loading: etfLoading } = useData('etfs.json')
  const { data: insideInformation, loading: insideInformationLoading } = useData('screens/inside-information.json')

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

      <TopSignal report={report} Container={Container} />

      <FocusedScreens report={report} etfData={etfData} etfLoading={etfLoading} Container={Container} SectionHeading={SectionHeading} />
      <InsideInformation insideInformation={insideInformation} insideInformationLoading={insideInformationLoading} Container={Container} />
      <p {...cap('disclosure.home.screen-disclaimer')}>
        Research screens, not trade instructions. Confirm current prices, liquidity, news, and your own risk limits before acting.
      </p>
    </div>
  )
}
