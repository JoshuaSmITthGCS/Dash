import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { PreferencesProvider } from './lib/PreferencesContext.jsx'
import './lib/hudEffects.js'

// Advanced HUD background effects (data-stream/grid overlay) are initialized from
// AppContent() in App.jsx, gated to Classic's own routes — see the comment there.

// Classic's own stylesheet (src/styles/index.css, ~340 kB — 14 cascade-order-dependent
// modules) is legacy chrome none of the twelve medium manifests use; each medium loads its
// own tokens.css instead. Loading it unconditionally here blew the /v2 500 kB entry budget
// for every medium regardless of size (found by budget.spec.mjs). Fetching it before the
// initial render only when the entry URL isn't a medium route keeps Classic's current,
// zero-FOUC behavior unchanged while /v2 and the e2e harness never pay for it; App.jsx's
// route-gated effect covers the case of navigating into Classic later without a full reload.
async function bootstrap() {
  const isMediumRoute = window.location.pathname.startsWith('/v2') || window.location.pathname.startsWith('/e2e-harness')
  // Classic-as-a-medium (medium: 'classic' under /v2) still needs this — its own tokens.css
  // deliberately reuses src/styles/variables.css rather than redefining it (see that file's
  // header comment). The pre-paint IIFE in index.html sets dataset.medium synchronously before
  // this module runs, so it's available here with no round trip.
  const activeMedium = document.documentElement.dataset.medium
  if (!isMediumRoute || activeMedium === 'classic') await import('./styles/index.css')

  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <PreferencesProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </PreferencesProvider>
    </React.StrictMode>
  )
}

bootstrap()

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'))
}
