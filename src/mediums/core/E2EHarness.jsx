/**
 * A diagnostic-only route, `/e2e-harness/:mediumId`, that mounts one medium's real
 * `LabelFrame`/renderer against fixed fixture metrics — never real page composition. It exists
 * because the six core screens (Phase 2a/2b, an intentionally partial slice — see NOTES.md)
 * don't yet wire every medium's WallLabel/renderer into live traffic the way `manifest.test.jsx`
 * already exercises them in vitest; this route lets Playwright inspect the SAME contract at real
 * browser/DOM/computed-style fidelity (renderer distinctness, numeral legibility, the
 * Chalkboard-smudge/Neon-glow/Beige-contrast rules) without waiting on that page-composition
 * work. Built (not compiled away) only when `vite build --mode e2e` — never in the real
 * production bundle users get; mirrors the existing `/hud-demo` DEV-only-route precedent, but
 * gated on build mode rather than `import.meta.env.DEV` since a Playwright run tests a real
 * `vite build` + `vite preview`, where `DEV` is always false.
 */
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { loadMedium } from '../registry.js'
import { MediumProvider } from './MediumContext.jsx'
import WallLabel from './WallLabel.jsx'

// One fixture per canonical state, plus the optional devices (previous value, bootstrap CI)
// that only some mediums render (Chalkboard's smudge, Star Chart's error ellipse) — present on
// every medium's fixture set so every medium gets the same opportunity to render them.
export const FIXTURE_METRICS = Object.freeze([
  {
    id: 'established_metric', label: 'Deflated Sharpe', status: 'ready', breached: false,
    reads: 'Deflated Sharpe adjusts the raw ratio for the number of configurations tried.',
    unit: 'ratio', cadence: 'Weekly', value: 0.62, display: '0.62',
    previous_value: '0.58',
  },
  {
    id: 'accumulating_metric', label: 'Rank IC (1d)', status: 'provisional',
    observations: 17, required_observations: 24, cadence: 'Weekly',
    status_message: '17 of 24 weekly periods observed.',
  },
  {
    id: 'breached_metric', label: 'Hit Rate', status: 'ready', breached: true,
    kill_threshold: 'Hit rate < 0.50', kill_threshold_value: 0.5, comparison: 'gt',
    status_message: 'Hit rate has fallen below the registered floor.', value: 0.42, display: '0.42',
  },
  {
    id: 'unavailable_metric', label: 'Prospective IC', status: 'unavailable',
    status_message: 'No eligible periods have accumulated yet.',
  },
  {
    id: 'ic_bootstrap_ci', label: 'Bootstrap IC confidence interval', status: 'ready', breached: true,
    kill_threshold: '95% CI includes zero', value: 0.0356, display: '0.036',
    detail: { ic_ci_95: [-0.01, 0.0777] },
  },
])

export const FIXTURE_SERIES = Object.freeze([1, 2, 1.5, 3, 2.5, 4, 3.5, 5])

function useAppReady() {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let cancelled = false
    const settle = () => { if (!cancelled) setReady(true) }
    if (globalThis.document?.fonts?.ready) document.fonts.ready.then(settle).catch(settle)
    else settle()
    return () => { cancelled = true }
  }, [])
  return ready
}

export default function E2EHarness() {
  const { pathname } = useLocation()
  const mediumId = pathname.replace(/^\/e2e-harness\//, '').replace(/\/$/, '')
  const [manifest, setManifest] = useState(null)
  const [renderer, setRenderer] = useState(null)
  const [error, setError] = useState(null)
  const appReady = useAppReady()

  useEffect(() => {
    let cancelled = false
    setManifest(null)
    setRenderer(null)
    loadMedium(mediumId)
      .then((m) => m.loadTokens().then(() => m))
      .then((m) => {
        if (cancelled) return
        setManifest(m)
        return m.loadRenderer().then((r) => { if (!cancelled) setRenderer(r) })
      })
      .catch((e) => { if (!cancelled) setError(e) })
    return () => { cancelled = true }
  }, [mediumId])

  useEffect(() => {
    document.documentElement.dataset.medium = mediumId
  }, [mediumId])

  if (error) return <div role="alert" data-e2e-harness-error="true">{error.message}</div>
  if (!manifest || !renderer) return <div role="status" aria-live="polite">Loading…</div>

  const Container = manifest.components?.Container

  return (
    <MediumProvider value={manifest}>
      <div data-e2e-harness="true" data-app-ready={appReady ? 'true' : undefined} style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {FIXTURE_METRICS.map((metric) => {
          const body = <WallLabel key={metric.id} metric={metric} capabilityId={`e2e-harness.${metric.id}`} />
          return Container ? <Container key={metric.id} state={{ state: metric.breached ? 'breached' : 'established' }}>{body}</Container> : body
        })}
        {renderer && (
          <div data-e2e-harness-chart="line" data-capability-id="e2e-harness.chart-line">
            {renderer.line({ values: FIXTURE_SERIES, metricId: 'e2e-harness-line', ariaLabel: 'harness line chart', width: 240, height: 100, confidence: { level: 0.8 }, state: { state: 'established' } })}
          </div>
        )}
      </div>
    </MediumProvider>
  )
}
