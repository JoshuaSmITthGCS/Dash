import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ThemeExposureScreen from './ThemeExposureScreen.jsx'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const advisorData = {
  research: [{ ticker: 'NVDA', name: 'NVIDIA', sector: 'Technology', score: 90, stance: 'ATTRACTIVE' }],
  screen_universe: [{ ticker: 'MU', name: 'Micron', sector: 'Technology', score: 55, stance: 'MIXED' }],
  theme_screen: {
    themes: [{
      id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', thesis: 'A capex cycle.',
      rows: [
        {
          ticker: 'NVDA', name: 'NVIDIA', theme_exposure_score: 85, opportunity_score: 60,
          eligible: true, leading_signals_fired: ['filing_keyword_density_trend'],
          candidate_source: 'published_leader',
        },
        {
          ticker: 'MU', name: 'Micron', theme_exposure_score: 70, opportunity_score: 75,
          eligible: true, leading_signals_fired: ['filing_keyword_density_trend'],
          candidate_source: 'sector_peer',
        },
      ],
    }],
  },
}

describe('Theme Exposure screen', () => {
  it('renders both the mobile card list and the desktop table for the same rows', () => {
    // .research-table is hidden outright below 900px in global.css, and MobileVirtualList
    // itself only mounts its cards when matchMedia reports a mobile viewport - without a
    // card fallback in the DOM, a phone would show an empty page below the intro copy.
    const originalMatchMedia = window.matchMedia
    window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} })
    useData.mockImplementation(() => ({ data: advisorData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(document.querySelector('.research-mobile-list')).toBeTruthy()
    expect(document.querySelectorAll('.research-mobile-card').length).toBeGreaterThan(0)
    expect(document.querySelector('.research-table table')).toBeTruthy()

    window.matchMedia = originalMatchMedia
  })

  it('splits rows into Leaders and Connected, not yet re-rated by candidate_source', () => {
    useData.mockImplementation(() => ({ data: advisorData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(screen.getAllByText('Leaders').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Connected, not yet re-rated').length).toBeGreaterThan(0)
    expect(screen.getAllByText('NVDA').length).toBeGreaterThan(0)
    expect(screen.getAllByText('MU').length).toBeGreaterThan(0)
  })

  it('shows an empty state instead of crashing when no theme produced scored rows', () => {
    useData.mockImplementation(() => ({
      data: { research: [], screen_universe: [], theme_screen: { themes: [], unavailable_reason: 'no signals' } },
      loading: false, error: null,
    }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(screen.getByText('no signals')).toBeInTheDocument()
  })
})
