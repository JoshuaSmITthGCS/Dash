import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { cap } from '../capability.js'
import { MARKETS_IDS } from './capabilityIds.js'

export const MARKETS_VIEWS = Object.freeze(['indexes', 'news'])

/**
 * Absorbs Markets and News behind `?view=indexes|news` (see ROUTE-INVENTORY.md §2), which also
 * resolves the old `/market` (singular) vs `/markets` (plural) confusion by naming both as
 * views of one destination. This shell renders the indexes view's session badge for real; the
 * full stat-card grid, direct-lookup search, intraday accumulation, and the news view port in
 * per medium in Phase 2b against CAPABILITY-LEDGER.md §3.
 */
export default function MarketsScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams] = useSearchParams()
  const view = MARKETS_VIEWS.includes(searchParams.get('view')) ? searchParams.get('view') : 'indexes'

  const { data: report, loading } = useData('report.json')

  if (loading) return <div role="status" aria-live="polite">Loading…</div>
  if (!report?.market) {
    return <div {...cap(MARKETS_IDS.unavailable)} role="alert">Market data is unavailable in the latest refresh.</div>
  }

  return (
    <div data-screen="markets" data-view={view}>
      <Container {...cap(MARKETS_IDS.sessionBadge)}>
        <span data-testid="market-type">{report.market?.macro?.regime?.label || 'regime unavailable'}</span>
      </Container>
    </div>
  )
}
