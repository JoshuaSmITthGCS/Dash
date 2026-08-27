import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { PreferencesProvider } from './lib/PreferencesContext.jsx'
import './lib/hudEffects.js'

// Advanced HUD background effects (data-stream/grid overlay) are initialized from
// AppContent() in App.jsx, gated to Classic's own routes — see the comment there.

// Classic's own stylesheet (src/styles/index.css, ~340 kB — 14 cascade-order-dependent
// modules) is legacy chrome none of the twelve medium manifests use; each medium loads its
// own tokens.css instead. Loading it unconditionally here blew the /v2 500 kB entry budget
// for every medium regardless of size (found by budget.spec.mjs). Fetching it before the
// initial render only when the entry URL isn't a medium route keeps Classic's current,
// zero-FOUC behavior unchanged while /v2 and the e2e harness never pay for it. Since App.jsx and
// MediumApp.jsx are now two separate roots chosen once here (see below) rather than branches of
// one component, there's no soft in-app navigation between them any more — MediumApp.jsx's
// EscapeToClassic and App.jsx's NotFoundOrMedium both hard-reload through this same check
// instead, so this is the only place Classic's stylesheet needs to be fetched.
async function bootstrap() {
  const isMediumRoute = window.location.pathname.startsWith('/v2') || window.location.pathname.startsWith('/e2e-harness')
  // Classic-as-a-medium (medium: 'classic' under /v2) still needs this — its own tokens.css
  // deliberately reuses src/styles/variables.css rather than redefining it (see that file's
  // header comment). The pre-paint IIFE in index.html sets dataset.medium synchronously before
  // this module runs, so it's available here with no round trip.
  const activeMedium = document.documentElement.dataset.medium
  if (!isMediumRoute || activeMedium === 'classic') await import('./styles/index.css')

  // Two separate root components, chosen by this one runtime check, rather than one component
  // that branches internally (as it used to) — a static top-of-file `import App from
  // './App.jsx'` would still pull App.jsx's whole module graph, FirebaseAuthContext.jsx and its
  // eager Firebase SDK init included, into whatever chunk this file lands in, regardless of
  // which branch actually executes: import()-resolution happens at bundle time, not render time.
  // This dynamic import is what actually keeps Firebase's ~610 kB out of a medium's cold load
  // (Phase 4, NOTES.md) — MediumApp.jsx's own header comment has the full reasoning.
  const { default: RootApp } = isMediumRoute
    ? await import('./MediumApp.jsx')
    : await import('./App.jsx')

  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <PreferencesProvider>
        <BrowserRouter>
          <RootApp />
        </BrowserRouter>
      </PreferencesProvider>
    </React.StrictMode>
  )
}

bootstrap()

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'))
}
