import { useEffect, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { loadMedium, getMediumMeta } from '../registry.js'
import { MediumProvider } from './MediumContext.jsx'
import { useEntryDecision } from './entry.js'
import HomeScreen from './screens/HomeScreen.jsx'
import ResearchScreen from './screens/ResearchScreen.jsx'
import ScreensScreen from './screens/ScreensScreen.jsx'
import PortfolioScreen from './screens/PortfolioScreen.jsx'
import MarketsScreen from './screens/MarketsScreen.jsx'
import EvidenceScreen from './screens/EvidenceScreen.jsx'

export const MEDIUM_ROOT_PATH = '/v2'

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
  const NavComponent = manifest.nav?.Component
  const EntryComponent = manifest.entry?.Component

  if (showEntry && EntryComponent) {
    return <EntryComponent onContinue={dismiss} />
  }

  return (
    <div data-medium-shell="true">
      {NavComponent && <NavComponent />}
      <main id="main-content" tabIndex="-1">
        <Routes>
          <Route path="/" element={<HomeScreen />} />
          <Route path="research" element={<ResearchScreen />} />
          <Route path="screens" element={<ScreensScreen />} />
          <Route path="portfolio" element={<PortfolioScreen />} />
          <Route path="markets" element={<MarketsScreen />} />
          <Route path="evidence" element={<EvidenceScreen />} />
        </Routes>
      </main>
    </div>
  )
}
