import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import PortfolioScreen from './PortfolioScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))

const fakeManifest = { components: {} }

function renderPortfolio(path = '/v2/portfolio') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><PortfolioScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('PortfolioScreen', () => {
  beforeEach(() => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25', research: [], screen_universe: [], portfolio_coverage: [] }, loading: false })
  })

  it('shows the no-positions empty state', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    renderPortfolio()
    expect(screen.getByText('No positions yet. Add a position to start tracking.')).toBeInTheDocument()
  })

  it('reads the ?view= param', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio('/v2/portfolio?view=diversification')
    expect(container.querySelector('[data-view="diversification"]')).toBeInTheDocument()
  })

  it('falls back to summary for an unknown view param', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio('/v2/portfolio?view=not-a-real-view')
    expect(container.querySelector('[data-view="summary"]')).toBeInTheDocument()
  })

  it('applies the KPI-row capability id', () => {
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    const { container } = renderPortfolio()
    expect(container.querySelector('[data-capability-id="figure.portfolio.kpi-row"]')).toBeInTheDocument()
  })
})
