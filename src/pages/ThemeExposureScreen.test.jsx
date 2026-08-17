import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ThemeExposureScreen, { crossThemeNames } from './ThemeExposureScreen.jsx'
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

// Two themes with one company (ETN) exposed to both, mirroring what the pipeline publishes:
// per-theme `group_counts` carry the pre-truncation sizes and `by_ticker` indexes every
// scored name across every theme, not just the rows that made a published table.
const multiThemeData = {
  research: [
    { ticker: 'NVDA', name: 'NVIDIA', sector: 'Technology', score: 90, stance: 'ATTRACTIVE' },
    { ticker: 'ETN', name: 'Eaton', sector: 'Industrials', score: 80, stance: 'ATTRACTIVE' },
  ],
  screen_universe: [],
  theme_screen: {
    by_ticker: {
      NVDA: [{ theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', theme_exposure_score: 85, opportunity_score: 60, eligible: true }],
      ETN: [
        { theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', theme_exposure_score: 74, opportunity_score: 71, eligible: true },
        { theme_id: 'grid_electrification', display_name: 'Grid & Electrification Buildout', theme_exposure_score: 88, opportunity_score: 79, eligible: true },
      ],
    },
    themes: [
      {
        id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', thesis: 'A capex cycle.',
        count: 12, eligible_count: 9, sectors: ['technology', 'industrials'],
        group_counts: { leaders: 9, connected: 3 },
        rows: [{
          ticker: 'NVDA', name: 'NVIDIA', theme_exposure_score: 85, opportunity_score: 60,
          eligible: true, leading_signals_fired: ['filing_keyword_density_trend'],
          candidate_source: 'published_leader',
        }],
      },
      {
        id: 'grid_electrification', display_name: 'Grid & Electrification Buildout', thesis: 'Load growth.',
        count: 6, eligible_count: 4, sectors: ['industrials', 'utilities'],
        group_counts: { leaders: 1, connected: 5 },
        rows: [{
          ticker: 'ETN', name: 'Eaton', theme_exposure_score: 88, opportunity_score: 79,
          eligible: true, leading_signals_fired: ['filing_keyword_density_trend'],
          candidate_source: 'published_leader',
        }],
      },
    ],
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

  it('indexes every theme in the report with a link to its panel', () => {
    useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    const index = screen.getByRole('navigation', { name: 'Themes in this report' })
    expect(within(index).getByRole('link', { name: 'AI Infrastructure Buildout' }))
      .toHaveAttribute('href', '#theme-ai_infrastructure')
    expect(within(index).getByRole('link', { name: 'Grid & Electrification Buildout' }))
      .toHaveAttribute('href', '#theme-grid_electrification')
  })

  it('groups companies that clear more than one theme into a crossing section', () => {
    useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    const crossing = screen.getByRole('heading', { name: /Where the themes cross/ }).closest('section')
    // ETN clears both themes; NVDA clears one, so it is not a crossing point.
    expect(within(crossing).getAllByText('ETN').length).toBeGreaterThan(0)
    expect(within(crossing).queryByText('NVDA')).toBeNull()
  })

  it('says how much of a group it is showing when the pipeline truncated it', () => {
    useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    // group_counts records the pre-truncation size: 1 leader published out of 9 scored.
    expect(screen.getAllByText('Showing 1 of 9').length).toBeGreaterThan(0)
  })

  describe('crossThemeNames', () => {
    const byTicker = {
      ONE: [{ theme_id: 'a', eligible: true, opportunity_score: 90 }],
      TWO: [{ theme_id: 'a', eligible: true, opportunity_score: 50 },
        { theme_id: 'b', eligible: true, opportunity_score: 60 }],
      THREE: [{ theme_id: 'a', eligible: true, opportunity_score: 10 },
        { theme_id: 'b', eligible: true, opportunity_score: 20 },
        { theme_id: 'c', eligible: true, opportunity_score: 30 }],
      FLAGGED: [{ theme_id: 'a', eligible: false, opportunity_score: 99 },
        { theme_id: 'b', eligible: false, opportunity_score: 99 }],
    }

    it('ranks by how many themes a name clears, then by its best opportunity', () => {
      expect(crossThemeNames(byTicker).map((row) => row.ticker)).toEqual(['THREE', 'TWO'])
    })

    it('reports the best opportunity across the themes a name clears', () => {
      expect(crossThemeNames(byTicker).find((row) => row.ticker === 'TWO').bestOpportunity).toBe(60)
    })

    it('reports the thinnest evidence among the themes, not the average', () => {
      const thin = crossThemeNames({
        TWO: [{ theme_id: 'a', eligible: true, opportunity_score: 50, confidence: 0.8 },
          { theme_id: 'b', eligible: true, opportunity_score: 60, confidence: 0.35 }],
      })
      expect(thin[0].weakestConfidence).toBe(0.35)
    })

    it('leaves the evidence unreported rather than guessing when no theme published it', () => {
      const missing = crossThemeNames({
        TWO: [{ theme_id: 'a', eligible: true }, { theme_id: 'b', eligible: true }],
      })
      expect(missing[0].weakestConfidence).toBeNull()
    })

    it('counts only themes whose guardrails the name actually cleared', () => {
      // FLAGGED sits in two themes but cleared neither, so it is not a crossing point -
      // it is the same already-priced-in exposure flagged twice.
      expect(crossThemeNames(byTicker).map((row) => row.ticker)).not.toContain('FLAGGED')
    })

    it('needs more than one theme before a name counts as a crossing', () => {
      expect(crossThemeNames(byTicker).map((row) => row.ticker)).not.toContain('ONE')
    })
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
