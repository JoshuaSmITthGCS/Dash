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
  // DataTable mounts exactly one representation of the rows. Both directions are
  // asserted because the failure that matters is a viewport rendering neither:
  // before DataTable this page mounted both trees and hid one with CSS.
  const withViewport = (matches, assertion) => {
    const originalMatchMedia = window.matchMedia
    window.matchMedia = () => ({ matches, addEventListener() {}, removeEventListener() {} })
    useData.mockImplementation(() => ({ data: advisorData, loading: false, error: null }))
    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)
    assertion()
    window.matchMedia = originalMatchMedia
  }

  it('renders the card list and no table below the mobile breakpoint', () => {
    withViewport(true, () => {
      expect(document.querySelector('.research-mobile-list')).toBeTruthy()
      expect(document.querySelectorAll('.research-mobile-card').length).toBeGreaterThan(0)
      expect(document.querySelector('table')).toBeNull()
    })
  })

  it('renders the table and no card list above the mobile breakpoint', () => {
    withViewport(false, () => {
      expect(document.querySelector('table')).toBeTruthy()
      expect(document.querySelector('.research-mobile-list')).toBeNull()
    })
  })

  it('splits rows into Leaders and Connected, not yet re-rated by candidate_source', () => {
    useData.mockImplementation(() => ({ data: advisorData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(screen.getAllByText('Leaders').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Connected, not yet re-rated').length).toBeGreaterThan(0)
    expect(screen.getAllByText('NVDA').length).toBeGreaterThan(0)
    expect(screen.getAllByText('MU').length).toBeGreaterThan(0)
  })

  it('plots the mean resolved score per signal across the theme leaders', () => {
    const withSignals = {
      research: advisorData.research,
      screen_universe: advisorData.screen_universe,
      theme_screen: {
        themes: [{
          id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', thesis: 'A capex cycle.',
          rows: [
            {
              ticker: 'NVDA', name: 'NVIDIA', theme_exposure_score: 85, opportunity_score: 60,
              eligible: true, candidate_source: 'published_leader',
              signals: [
                { name: 'filing_keyword_density_trend', score: 100, weight: 0.2, leading: true },
                { name: 'hyperscaler_capex_growth', score: 90, weight: 0.15, leading: true },
              ],
            },
            {
              ticker: 'AMD', name: 'AMD', theme_exposure_score: 70, opportunity_score: 55,
              eligible: true, candidate_source: 'published_leader',
              signals: [
                { name: 'filing_keyword_density_trend', score: 60, weight: 0.2, leading: true },
              ],
            },
          ],
        }],
      },
    }
    useData.mockImplementation(() => ({ data: withSignals, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(screen.getByText('Mean signal score among leaders (0-100)')).toBeInTheDocument()
    expect(screen.getByText('Filing Keyword Density Trend · leading')).toBeInTheDocument()
    expect(screen.getByText('Hyperscaler Capex Growth · leading')).toBeInTheDocument()
    expect(screen.getByText('80', { selector: '.dot-plot-value' })).toBeInTheDocument() // mean of 100 and 60
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
