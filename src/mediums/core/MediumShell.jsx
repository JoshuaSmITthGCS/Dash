import { lazy, Suspense, useEffect, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { loadMedium, getMediumMeta } from '../registry.js'
import { MediumProvider } from './MediumContext.jsx'
import { useEntryDecision } from './entry.js'
import HomeScreen from './screens/HomeScreen.jsx'

// Lazy, unlike Home — Home stays a static import since it's the actual cold-loaded route and
// lazy-loading it would just add a needless round trip. The other five screens grew
// substantially during Phase 4b's ledger-coverage wiring (Research/Screens/Evidence are each
// 800-1200+ lines now, and Screens/Evidence each mount their own <FirebaseAuthProvider> for
// watchlist/shadow-portfolio features) — statically importing any of them back into this file
// reintroduces the exact eager-Firebase/oversized-bundle problem Phase 4a fixed, just via a
// different route. Keeping every non-Home screen lazy is what keeps Home's own cold /v2 load
// (the one budget.spec.mjs measures) from paying for code five other routes need.
const ResearchScreen = lazy(() => import('./screens/ResearchScreen.jsx'))
const ScreensScreen = lazy(() => import('./screens/ScreensScreen.jsx'))
const PortfolioScreen = lazy(() => import('./screens/PortfolioScreen.jsx'))
const MarketsScreen = lazy(() => import('./screens/MarketsScreen.jsx'))
const EvidenceScreen = lazy(() => import('./screens/EvidenceScreen.jsx'))

export const MEDIUM_ROOT_PATH = '/v2'

/**
 * True once the active medium's fonts have settled — the Phase 3 Playwright harness waits on
 * `[data-app-ready="true"]` instead of `networkidle`/`waitForTimeout` (both banned in
 * `tests/e2e/**`, since neither actually promises the fonts a numeral-legibility assertion reads
 * are done swapping in). Guarded for test environments where `document.fonts` doesn't exist.
 */
function useAppReady() {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let cancelled = false
    const settle = () => { if (!cancelled) setReady(true) }
    if (globalThis.document?.fonts?.ready) {
      document.fonts.ready.then(settle).catch(settle)
    } else {
      settle()
    }
    return () => { cancelled = true }
  }, [])
  return ready
}

function MediumLoadError({ mediumId, error }) {
  return (
    <div role="alert" data-medium-load-error="true">
      <p>The "{mediumId}" medium could not be loaded.</p>
      <p>{error?.message}</p>
    </div>
  )
}

function MediumLoading() {
  return <div role="status" aria-live="polite">Loading medium…</div>
}

/**
 * A neutral, non-medium-themed exit affordance — "switch back to what you have now" (user's own
 * words). Deliberately styled plainly rather than through any medium's own material system, same
 * convention `MediumLoading`/`MediumLoadError` above already establish for shared shell chrome:
 * it must read consistently regardless of which of the twelve themes is active, and must not
 * depend on that medium's own tokens.css having loaded correctly.
 *
 * A hard reload to `/` (never a client-side navigate) — symmetric with `MediumApp.jsx`'s own
 * `EscapeToClassic` mechanism, and required for the same reason: `/` is a structurally different
 * root (`main.jsx`'s bootstrap picks `App.jsx` vs `MediumApp.jsx` by pathname), so nothing short
 * of a real navigation loads it. Deliberately does NOT touch the `medium` preference — this is a
 * pure escape hatch, not a reset; only Settings' picker (`src/pages/Settings.jsx`) changes which
 * medium is selected, so returning to `/v2` later lands back on whatever was last chosen.
 */
function ExitToClassic() {
  return (
    <button
      type="button"
      data-testid="exit-to-classic"
      aria-label="Back to Classic"
      onClick={() => window.location.assign('/')}
      style={{
        position: 'fixed', top: 8, right: 8, zIndex: 9999,
        padding: '6px 10px', minHeight: '32px', fontSize: '13px', fontFamily: 'system-ui, sans-serif',
        background: '#111', color: '#fff', border: '1px solid #444', borderRadius: '4px', cursor: 'pointer',
      }}
    >
      ← Back to Classic
    </button>
  )
}

/**
 * Mounts at `/v2/*`. Loads the active medium's manifest, sets `data-medium` on the document
 * root, provides it via MediumContext to every screen and WallLabel beneath it, decides whether
 * to show the medium's entry page (skippable, deep-link-bypass structural — see core/entry.js),
 * and renders the six destination screens the master's consolidation defines.
 *
 * `mediumId` and `entrySkip` are passed in rather than read from PreferencesContext directly,
 * so this component (and its tests) don't need the whole preferences provider tree to render.
 */
export default function MediumShell({ mediumId, entrySkip = false }) {
  const [state, setState] = useState({ status: 'loading', manifest: null, error: null })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading', manifest: null, error: null })
    loadMedium(mediumId)
      // `loadTokens()` is awaited before the medium ever renders — its whole `[data-medium="x"]`
      // token/structural CSS is otherwise dead code nothing ever injects into the page (every
      // `var(--ink-primary)`-style reference would resolve to nothing). Phase 3's harness caught
      // this the first time anything opened `/v2` in a real browser rather than jsdom, where a
      // bare `var(--x)` reference in a `style` attribute "passes" without ever resolving.
      .then((manifest) => manifest.loadTokens().then(() => manifest))
      .then((manifest) => { if (!cancelled) setState({ status: 'ready', manifest, error: null }) })
      .catch((error) => { if (!cancelled) setState({ status: 'error', manifest: null, error }) })
    return () => { cancelled = true }
  }, [mediumId])

  useEffect(() => {
    const meta = getMediumMeta(mediumId)
    document.documentElement.dataset.medium = mediumId
    if (meta) {
      document.documentElement.style.colorScheme = meta.colorScheme
      document.getElementById('theme-color-meta')?.setAttribute('content', meta.themeColor)
    }
  }, [mediumId])

  if (state.status === 'loading') return <MediumLoading />
  if (state.status === 'error') return <MediumLoadError mediumId={mediumId} error={state.error} />

  return (
    <MediumProvider value={state.manifest}>
      <MediumShellReady manifest={state.manifest} mediumId={mediumId} entrySkip={entrySkip} />
    </MediumProvider>
  )
}

function MediumShellReady({ manifest, mediumId, entrySkip }) {
  const { showEntry, dismiss } = useEntryDecision({
    mediumId, hasEntry: Boolean(manifest.entry), rootPath: MEDIUM_ROOT_PATH, entrySkip,
  })
  const appReady = useAppReady()
  const NavComponent = manifest.nav?.Component
  const EntryComponent = manifest.entry?.Component

  if (showEntry && EntryComponent) {
    return (
      <div data-app-ready={appReady ? 'true' : undefined}>
        <EntryComponent onContinue={dismiss} />
      </div>
    )
  }

  return (
    <div data-medium-shell="true" data-app-ready={appReady ? 'true' : undefined}>
      {NavComponent && <NavComponent />}
      <ExitToClassic />
      <main id="main-content" tabIndex="-1">
        <Suspense fallback={<MediumLoading />}>
          <Routes>
            <Route path="/" element={<HomeScreen />} />
            <Route path="research" element={<ResearchScreen />} />
            <Route path="screens" element={<ScreensScreen />} />
            <Route path="portfolio" element={<PortfolioScreen />} />
            <Route path="markets" element={<MarketsScreen />} />
            <Route path="evidence" element={<EvidenceScreen />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}
