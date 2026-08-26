import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { canonicalArtifactState } from '../states.js'
import { cap } from '../capability.js'
import { SCREENS_IDS } from './capabilityIds.js'

// Maps `?recipe=` to its published screen file — the twelve ranked-list families
// CAPABILITY-LEDGER.md §9 consolidates. `options` and its 7 strategies share one file family;
// the strategy sub-selector is layered in per-medium once the Options screen's own controls
// (direction/strategy selects, trade-ticket reference) are ported in Phase 2b.
const RECIPE_FILES = Object.freeze({
  swing: 'screens/swing.json',
  'fast-growth': null, // client-ranked from report.json, ported in Phase 2b
  options: 'screens/options.json',
  momentum: 'screens/momentum.json',
  'quality-value': 'screens/quality-value.json',
  earnings: 'screens/earnings-timeliness.json',
  matrix: 'screens/structural-tactical.json',
  themes: null, // sourced from advisor.json + theme-peers.json, ported in Phase 2b
  'early-session': 'screens/early-session.json',
  politics: 'screens/congress-trades.json',
  institutional: 'screens/institutional-13f.json',
  'inside-information': 'screens/inside-information.json',
})

export const DEFAULT_RECIPE = 'swing'

/**
 * Absorbs the twelve ranked-list-with-a-recipe screen families behind `?recipe=<id>` (see
 * ROUTE-INVENTORY.md §2 and CAPABILITY-LEDGER.md §9). Every recipe keeps its own file, filters,
 * columns, and disclosure set intact — this shell only resolves which file to load and renders
 * the artifact's own build-status state; the recipe-specific filter panels and tables port in
 * per medium in Phase 2b against each §9 sub-section's full row set.
 */
export default function ScreensScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams] = useSearchParams()
  const recipe = searchParams.get('recipe') || DEFAULT_RECIPE
  const file = RECIPE_FILES[recipe] ?? RECIPE_FILES[DEFAULT_RECIPE]

  const { data, loading } = useData(file)
  const artifactState = canonicalArtifactState(data)

  if (loading) return <div {...cap(SCREENS_IDS.loading)} role="status" aria-live="polite">Loading…</div>

  if (!file || !data) {
    return (
      <div {...cap(SCREENS_IDS.unavailable)} role="alert">
        Screen snapshot unavailable{artifactState.reason ? `: ${artifactState.reason}` : '.'}
      </div>
    )
  }

  const rows = data.results ?? data.rows ?? []

  return (
    <div data-screen="screens" data-recipe={recipe}>
      <Container>
        <h1>{recipe}</h1>
        <span data-testid="row-count">{rows.length} name{rows.length === 1 ? '' : 's'}</span>
        {artifactState.partial && <p role="alert" data-testid="partial-note">Collected from some sources only.</p>}
        {artifactState.state === 'unavailable' && <p data-testid="gated-note">{artifactState.reason}</p>}
      </Container>
    </div>
  )
}
