import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import MarketsScreen from './MarketsScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const fakeManifest = { components: {} }

function renderMarkets(path = '/v2/markets') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><MarketsScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('MarketsScreen', () => {
  it('renders the session badge from live market data', () => {
    useData.mockReturnValue({ data: { market: { macro: { regime: { label: 'supportive' } } } }, loading: false })
    renderMarkets()
    expect(screen.getByTestId('market-type')).toHaveTextContent('supportive')
  })

  it('shows unavailable when market data is absent', () => {
    useData.mockReturnValue({ data: {}, loading: false })
    renderMarkets()
    expect(screen.getByRole('alert')).toHaveTextContent('Market data is unavailable')
  })

  it('reads the ?view=news param — resolves the /market vs /markets confusion', () => {
    useData.mockReturnValue({ data: { market: {} }, loading: false })
    const { container } = renderMarkets('/v2/markets?view=news')
    expect(container.querySelector('[data-view="news"]')).toBeInTheDocument()
  })
})
