import { useEffect, useState } from 'react'
import { useMedium } from './MediumContext.jsx'

/**
 * Resolves the active medium's chart renderer (see `chartContract.js`) and hands it to a
 * `core/screens/*` component. This is the one call other screens should make to reach the
 * chart-renderer contract — it never bypasses `useMedium()`, and it never re-implements the
 * async-load-then-guard-against-a-stale-medium dance `E2EHarness.jsx` (lines 73-86) already
 * does; it just does the same thing behind a one-line hook.
 *
 * HOW TO LOAD IT
 *   const renderer = useRenderer()
 * `manifest.loadRenderer()` is an async dynamic import per medium, so this hook calls it once
 * per mounted medium (in a `useEffect`, keyed on the manifest) rather than on every render, and
 * returns `null` until it resolves. Every call site MUST guard on that: never call
 * `renderer.line(...)` unconditionally — always `renderer && renderer.line({...})` (or an
 * early-return/loading branch), the same way `WallLabel` call sites already guard on their own
 * loading states.
 *
 * PICKING A CHART TYPE
 * Choose only from `CHART_TYPES` in `./chartContract.js` — never invent a type, and never reach
 * for `donut` or `radar`: both are banned in every medium in this rebuild. An allocation/
 * breakdown use case is `composition` (a stacked-bar or treemap form, never a pie/donut). A
 * factor-loading-profile use case is `profile` (replaces the banned radar chart).
 *
 * BUILDING CHART PROPS
 * Build the props object from the ledger row's `dataSource` column, exactly the way every
 * `WallLabel`-driven row already does: read the real published JSON the screen has already
 * fetched via `useData(...)`, then shape it into the chart's props — `{ metricId, series |
 * values, domain, unit, thresholds, annotations, ariaLabel, width, height }` (see
 * `CHART_COMMON_PROP_KEYS` in `./chartContract.js`). Never fabricate a value that is not in the
 * published data.
 *
 * STATE AND CONFIDENCE
 * Derive `state` via `canonicalMetricState(metric)` (or `canonicalArtifactState(artifact)` for
 * artifact-level, non-per-metric data) and `confidence` via `confidenceOf({ metric })`, both
 * imported from `../states.js` (relative to a file under `core/`, `./states.js` from within
 * `core/` itself). Never hand-derive either inline — these two functions are the single source
 * of truth for what "established/accumulating/breached/unavailable" and confidence mean.
 *
 * ANNOTATIONS ARE REQUIRED WHEN A THRESHOLD OR EVENT EXISTS
 * Per the standing rule already documented on `CHART_COMMON_PROP_KEYS` in `chartContract.js`:
 * whenever the series carries a `kill_threshold` or some other explaining event, `annotations`
 * is REQUIRED (not optional) on that call — do not skip it just because the row also has
 * `thresholds` set. A series with no threshold and no explaining event (e.g. a plain market
 * index) legitimately passes empty arrays for both; don't force one in where none exists.
 *
 * CAPABILITY INSTRUMENTATION IS STILL REQUIRED
 * The chart contract does not replace `cap(id)` — it is additive. Wrap the chart's container
 * element in `cap(id)` with the ledger's capabilityId copied verbatim, exactly like every other
 * row on the screen.
 */
export function useRenderer() {
  const manifest = useMedium()
  const [renderer, setRenderer] = useState(null)

  useEffect(() => {
    let cancelled = false
    setRenderer(null)
    manifest.loadRenderer()
      .then((loaded) => { if (!cancelled) setRenderer(loaded) })
      .catch(() => { if (!cancelled) setRenderer(null) })
    return () => { cancelled = true }
  }, [manifest])

  return renderer
}

export default useRenderer
