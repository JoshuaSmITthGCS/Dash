import { lazy, Suspense, useEffect } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { usePreferences } from './lib/PreferencesContext.jsx'
import RouteLoading from './components/RouteLoading.jsx'

// The twelve-medium rebuild's shell — see src/mediums/. Lazy so this chunk never pays for it
// until someone actually visits /v2 (each medium is its own lazy chunk loaded only when active).
const MediumShell = lazy(() => import('./mediums/core/MediumShell.jsx'))
// Phase 3 Playwright-only diagnostic route — see E2EHarness.jsx's own header for why it's
// gated on build mode rather than DEV. Lazy for the same reason MediumShell is.
const E2EHarness = lazy(() => import('./mediums/core/E2EHarness.jsx'))

// Every non-Classic medium's Nav.jsx links to the Classic-only /settings route as its required
// "settings affordance" (one tap, per DESIGN.md) — a path this root's <Routes> can't serve, since
// main.jsx chose this root specifically because the ENTRY pathname was a medium route. A soft
// client-side <Navigate> can't fix that (App.jsx, which owns /settings, was never loaded), so this
// forces the one hard reload needed to hand off back to main.jsx's bootstrap, which then picks
// App.jsx correctly for the new pathname. Rare in practice — every other in-medium destination
// stays on /v2/* and never hits this.
function EscapeToClassic() {
  useEffect(() => { window.location.assign(window.location.pathname + window.location.search) }, [])
  return <RouteLoading pathname={window.location.pathname} />
}

/**
 * The root for /v2/* and /e2e-harness/* traffic — main.jsx's bootstrap() dynamically imports
 * this instead of App.jsx for those paths, so nothing in App.jsx's module graph (Classic's full
 * nav chrome, and critically FirebaseAuthContext.jsx / firebase.js's eager SDK init) is
 * bundler-reachable from a medium's cold load. Phase 4 (NOTES.md) split this out of what used to
 * be two branches inside App.jsx's AppContent(), which pulled in Firebase for every medium
 * regardless of whether that medium's screens ever call useAuth() — repositioning
 * <FirebaseAuthProvider> deeper in the same component tree wasn't enough, since the eager cost
 * is paid at module-import time, not at provider-mount time.
 */
export default function MediumApp() {
  const { preferences } = usePreferences()
  const { pathname } = useLocation()

  // Phase 3 harness diagnostic route: bypasses all app chrome for a clean mount of one medium's
  // real LabelFrame/renderer against fixed fixtures — see E2EHarness.jsx. Never present in the
  // real production bundle (MODE is always 'production' there, never 'e2e'), so this branch
  // dead-code-eliminates away.
  if (import.meta.env.MODE === 'e2e' && pathname.startsWith('/e2e-harness/')) {
    return <Suspense fallback={null}><E2EHarness /></Suspense>
  }

  // MediumShell's own inner <Routes> uses paths relative to "/v2" (see MediumShell.jsx), which
  // React Router only resolves correctly when it's nested under a matching <Route path="/v2/*">
  // — hence the standalone <Routes> here rather than rendering <MediumShell> directly.
  return <Suspense fallback={<RouteLoading pathname={pathname} />}>
    <Routes>
      <Route path="/v2/*" element={
        <MediumShell mediumId={preferences.medium} entrySkip={Boolean(preferences.entrySkip?.[preferences.medium])} />
      } />
      <Route path="*" element={<EscapeToClassic />} />
    </Routes>
  </Suspense>
}

