import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import MediumShell from './MediumShell.jsx'
import { loadMedium } from '../registry.js'
import { useData } from '../../lib/useData.js'
import { useFirebasePortfolio } from '../../lib/useFirebasePortfolio.js'
import { useAuth } from '../../lib/FirebaseAuthContext.jsx'

vi.mock('../registry.js', async (importOriginal) => ({ ...(await importOriginal()), loadMedium: vi.fn() }))
vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn() }))

function FakeNav() { return <nav aria-label="fake nav">nav</nav> }
function FakeEntry({ onContinue }) {
  return <div><p>Entry card</p><button onClick={onContinue}>Continue</button></div>
}

const fakeManifestNoEntry = { components: {}, nav: { Component: FakeNav }, entry: null }
const fakeManifestWithEntry = { components: {}, nav: { Component: FakeNav }, entry: { Component: FakeEntry } }

function renderShell(path, mediumId = 'gallery', entrySkip = false) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/v2/*" element={<MediumShell mediumId={mediumId} entrySkip={entrySkip} />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('MediumShell', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: null })
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    useData.mockReturnValue({ data: null, loading: false })
    globalThis.sessionStorage?.clear()
  })

  it('shows a loading state while the manifest resolves', async () => {
    let resolveManifest
    loadMedium.mockReturnValue(new Promise((resolve) => { resolveManifest = resolve }))
    renderShell('/v2')
    expect(screen.getByRole('status')).toHaveTextContent('Loading medium')
    resolveManifest(fakeManifestNoEntry)
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'fake nav' })).toBeInTheDocument())
  })

  it('shows a catchable error when the medium fails to load', async () => {
    loadMedium.mockRejectedValue(new Error('manifest.js has not been built yet.'))
    renderShell('/v2')
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not be loaded'))
  })

  it('mounts the nav and Home screen once the manifest resolves, no entry declared', async () => {
    loadMedium.mockResolvedValue(fakeManifestNoEntry)
    useData.mockReturnValue({ data: { research: [] }, loading: false })
    renderShell('/v2')
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'fake nav' })).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent('No advisor dataset')
  })

  it('sets data-medium on the document root', async () => {
    loadMedium.mockResolvedValue(fakeManifestNoEntry)
    renderShell('/v2', 'neon')
    await waitFor(() => expect(document.documentElement.dataset.medium).toBe('neon'))
  })

  it('shows the entry card on first load when the medium has one, then dismisses to the shell', async () => {
    loadMedium.mockResolvedValue(fakeManifestWithEntry)
    useData.mockReturnValue({ data: { research: [] }, loading: false })
    renderShell('/v2')
    await waitFor(() => expect(screen.getByText('Entry card')).toBeInTheDocument())
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    screen.getByText('Continue').click()
    await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
  })

  it('never shows the entry on a deep-linked path — structural bypass', async () => {
    loadMedium.mockResolvedValue(fakeManifestWithEntry)
    useData.mockReturnValue({ data: { research: [] }, loading: false })
    renderShell('/v2/research')
    await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
    expect(screen.queryByText('Entry card')).not.toBeInTheDocument()
  })

  it('respects a persisted entrySkip preference', async () => {
    loadMedium.mockResolvedValue(fakeManifestWithEntry)
    useData.mockReturnValue({ data: { research: [] }, loading: false })
    renderShell('/v2', 'gallery', true)
    await waitFor(() => expect(screen.getByRole('navigation')).toBeInTheDocument())
    expect(screen.queryByText('Entry card')).not.toBeInTheDocument()
  })
})
