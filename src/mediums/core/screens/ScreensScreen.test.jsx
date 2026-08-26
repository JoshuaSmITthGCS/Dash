import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ScreensScreen from './ScreensScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const fakeManifest = { components: {} }

function renderScreens(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><ScreensScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('ScreensScreen', () => {
  it('resolves ?recipe=swing to the swing file and renders its rows', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [{ ticker: 'AAPL' }, { ticker: 'MSFT' }] }, loading: false })
    renderScreens('/v2/screens?recipe=swing')
    expect(screen.getByTestId('row-count')).toHaveTextContent('2 names')
  })

  it('defaults to swing with no recipe param', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [] }, loading: false })
    renderScreens('/v2/screens')
    expect(screen.getByText('swing')).toBeInTheDocument()
  })

  it('shows the gated state as a feature, not a failure, for early-session', () => {
    useData.mockReturnValue({ data: { status: 'gated', disclaimer: 'Killed screens are a successful outcome.' }, loading: false })
    renderScreens('/v2/screens?recipe=early-session')
    expect(screen.getByTestId('gated-note')).toHaveTextContent('successful outcome')
  })

  it('shows the partial-collection alert for politics', () => {
    useData.mockReturnValue({ data: { status: 'partial', reason_code: 'SOME_SOURCES_UNAVAILABLE', results: [] }, loading: false })
    renderScreens('/v2/screens?recipe=politics')
    expect(screen.getByTestId('partial-note')).toBeInTheDocument()
  })

  it('shows unavailable when the recipe has no data yet', () => {
    useData.mockReturnValue({ data: null, loading: false })
    renderScreens('/v2/screens?recipe=matrix')
    expect(screen.getByRole('alert')).toHaveTextContent('Screen snapshot unavailable')
  })
})
