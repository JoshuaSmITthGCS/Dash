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
        industries: ['semiconductor', 'electrical equipment'],
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

  describe('trend evaluation', () => {
    const withTrend = (trend, extra = {}) => ({
      ...multiThemeData,
      theme_screen: {
        ...multiThemeData.theme_screen,
        themes: [{ ...multiThemeData.theme_screen.themes[0], trend, ...extra }],
      },
    })

    const broadening = {
      contributes_to_exposure: false, members_measured: 20,
      direction: { relative_strength_median: 6.4, acceleration_median: 1.2, label: 'strengthening' },
      breadth: { outperforming_share: 0.72, above_50d_share: 0.68, above_20d_share: 0.61, label: 'broad' },
      crowding: { expensiveness_percentile_median: 41, already_priced: false },
      leadership: { largest: 'NVDA', largest_relative_strength: 9, median_excluding_largest: 5.5, led_by_one_name: false },
      fundamental_confirmation: { positive_revision_share: 0.6, volume_ratio_median: 1.2 },
      chain_confirmation: { root_relative_strength: 8, supply_chain_relative_strength: 5, confirms: true },
      roles: [{ role: 'supplier', members: 8, relative_strength_median: 7.1, above_50d_share: 0.75 },
        { role: 'root', members: 4, relative_strength_median: 3.2, above_50d_share: 0.5 }],
      verdict: { label: 'broadening', summary: 'The group is outperforming.' },
    }

    it('answers whether the trend is rising, shared, and already paid for', () => {
      useData.mockImplementation(() => ({ data: withTrend(broadening), loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const panel = screen.getByLabelText('Trend evaluation')
      expect(within(panel).getByText('broadening')).toBeInTheDocument()
      expect(within(panel).getByText('+6.4')).toBeInTheDocument()      // leading the market by
      expect(within(panel).getByText('72%')).toBeInTheDocument()       // members participating
      expect(within(panel).getByText('No')).toBeInTheDocument()        // already priced
    })

    it('shows where in the chain the money is arriving, strongest stage first', () => {
      useData.mockImplementation(() => ({ data: withTrend(broadening), loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const rotation = screen.getByText('Where the money is arriving in the chain').closest('div')
      const stages = within(rotation).getAllByRole('listitem').map((item) => item.textContent)
      expect(stages[0]).toMatch(/Supplier/)
      expect(stages[1]).toMatch(/Root/)
    })

    it('says plainly when a move is one company rather than a trend', () => {
      const narrow = {
        ...broadening,
        breadth: { ...broadening.breadth, outperforming_share: 0.3, label: 'narrow' },
        leadership: { largest: 'NVDA', largest_relative_strength: 40, median_excluding_largest: -2, led_by_one_name: true },
        chain_confirmation: { root_relative_strength: 30, supply_chain_relative_strength: -3, confirms: false },
        verdict: { label: 'narrow leadership', summary: 'Concentrated in NVDA.' },
      }
      useData.mockImplementation(() => ({ data: withTrend(narrow), loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const panel = screen.getByLabelText('Trend evaluation')
      expect(within(panel).getByText(/company story rather than a trend/)).toBeInTheDocument()
      expect(within(panel).getByText(/NVDA at \+40 against -2 for the rest/)).toBeInTheDocument()
    })

    it('renders a crowded theme as a warning, never as a clean signal', () => {
      const crowded = {
        ...broadening,
        crowding: { expensiveness_percentile_median: 88, already_priced: true },
        verdict: { label: 'strong but already priced', summary: 'Outperforming and expensive.' },
      }
      useData.mockImplementation(() => ({ data: withTrend(crowded), loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(document.querySelector('.theme-verdict.watch')).toBeTruthy()
      expect(document.querySelector('.theme-verdict.pos')).toBeNull()
    })

    it('lists the biggest players by size, with their exposure and role', () => {
      useData.mockImplementation(() => ({
        data: withTrend(broadening, {
          biggest_players: [
            { ticker: 'NVDA', name: 'NVIDIA', role: 'root', market_cap: 3e12, theme_exposure_score: 72, eligible: true },
            { ticker: 'ETN', name: 'Eaton', role: 'infrastructure', market_cap: 1e11, theme_exposure_score: 88, eligible: true },
          ],
        }),
        loading: false,
        error: null,
      }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const players = screen.getByText('Biggest players').closest('div')
      const listed = within(players).getAllByRole('listitem').map((item) => item.textContent)
      // Size order, not exposure order: NVDA is bigger, ETN scores higher.
      expect(listed[0]).toMatch(/NVDA/)
      expect(listed[0]).toMatch(/Root/)
      expect(listed[1]).toMatch(/ETN/)
    })

    it('says a theme is unmeasured rather than inventing a verdict', () => {
      useData.mockImplementation(() => ({
        data: withTrend({ contributes_to_exposure: false, members_measured: 2,
          verdict: { label: 'unmeasured', summary: 'Only 2 members resolved price behavior.' } }),
        loading: false,
        error: null,
      }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByText('Only 2 members resolved price behavior.')).toBeInTheDocument()
      expect(screen.queryByLabelText('Trend evaluation')).toBeNull()
    })

    it('orders the index by how each trend reads, not alphabetically', () => {
      const cooling = { ...broadening, verdict: { label: 'cooling', summary: 'Lagging.' },
        direction: { relative_strength_median: -5, acceleration_median: -2, label: 'weakening' } }
      useData.mockImplementation(() => ({
        data: {
          ...multiThemeData,
          theme_screen: {
            ...multiThemeData.theme_screen,
            themes: [
              { ...multiThemeData.theme_screen.themes[0], trend: cooling },
              { ...multiThemeData.theme_screen.themes[1], trend: broadening },
            ],
          },
        },
        loading: false,
        error: null,
      }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const index = screen.getByRole('navigation', { name: 'Themes in this report' })
      const links = within(index).getAllByRole('link').map((link) => link.textContent)
      expect(links[0]).toBe('Grid & Electrification Buildout')   // broadening outranks cooling
    })
  })

  describe('why each stock is in its section', () => {
    const withWhy = {
      ...multiThemeData,
      theme_screen: {
        ...multiThemeData.theme_screen,
        themes: [{
          ...multiThemeData.theme_screen.themes[0],
          rows: [
            {
              ticker: 'NVDA', name: 'NVIDIA', theme_exposure_score: 85, opportunity_score: 60,
              eligible: true, role: 'root', candidate_source: 'published_leader',
              why: ['In this theme because it is already a published top research score',
                'Placed as the root of this chain, selling the product the theme is named for',
                'Its latest 10-K devotes 96% more of its language to this theme than the prior year\'s'],
            },
            {
              ticker: 'MU', name: 'Micron', theme_exposure_score: 70, opportunity_score: 75,
              eligible: false, role: 'supplier', candidate_source: 'sector_peer',
              why: ['In this theme because it is a peer-group neighbour of this theme\'s anchors, not yet a published research score',
                'Flagged, not promoted: valuation already in the top 10% of its sector'],
            },
          ],
        }],
      },
    }

    it('gives every row in every section its own stated reason', () => {
      useData.mockImplementation(() => ({ data: withWhy, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      // Both sections: a leader and a sector-connected name, each saying how it got there.
      // Scoped to the row summaries, since the section's own prose uses the same words.
      const summaries = [...document.querySelectorAll('.row-why summary')].map((node) => node.textContent)
      expect(summaries.some((text) => /already a published top research score/.test(text))).toBe(true)
      expect(summaries.some((text) => /peer-group neighbour/.test(text))).toBe(true)
    })

    it('keeps the reason visible on the row rather than behind a hover', () => {
      useData.mockImplementation(() => ({ data: withWhy, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const summaries = [...document.querySelectorAll('.row-why summary')].map((node) => node.textContent)
      expect(summaries.length).toBe(2)
      expect(summaries.every((text) => text.length > 0)).toBe(true)
    })

    it('shows the evidence and the flag when the row is expanded', () => {
      useData.mockImplementation(() => ({ data: withWhy, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByText(/96% more of its language/)).toBeInTheDocument()
      expect(screen.getByText(/Flagged, not promoted/)).toBeInTheDocument()
    })

    it('shows each row s role in the chain', () => {
      useData.mockImplementation(() => ({ data: withWhy, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getAllByText('Root').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Supplier').length).toBeGreaterThan(0)
    })

    it('says why a crossing name crosses, per theme, not just how many', () => {
      useData.mockImplementation(() => ({
        data: {
          ...multiThemeData,
          theme_screen: {
            ...multiThemeData.theme_screen,
            by_ticker: {
              ETN: [
                { theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout', theme_exposure_score: 74, opportunity_score: 71, eligible: true, role: 'infrastructure', confidence: 0.35 },
                { theme_id: 'grid_electrification', display_name: 'Grid & Electrification Buildout', theme_exposure_score: 88, opportunity_score: 79, eligible: true, role: 'supplier', confidence: 0.55 },
              ],
            },
          },
        },
        loading: false,
        error: null,
      }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const crossing = screen.getByRole('heading', { name: /Where the themes cross/ }).closest('section')
      expect(within(crossing).getByText(/exposure 74 as infrastructure/)).toBeInTheDocument()
      expect(within(crossing).getByText(/exposure 88 as supplier/)).toBeInTheDocument()
      expect(within(crossing).getByText(/35% of that theme's signal weight/)).toBeInTheDocument()
    })
  })

  it('names the industries a theme is built by, not just its sectors', () => {
    useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(screen.getByText(/Semiconductor · Electrical Equipment/)).toBeInTheDocument()
  })

  it('shows each row s industry, since a sector cannot say whether a name builds any of it', () => {
    useData.mockImplementation(() => ({
      data: {
        ...multiThemeData,
        research: [{ ticker: 'NVDA', name: 'NVIDIA', sector: 'Technology', industry: 'Semiconductors', score: 90 },
          { ticker: 'ETN', name: 'Eaton', sector: 'Industrials', industry: 'Electrical Equipment & Parts', score: 80 }],
      },
      loading: false,
      error: null,
    }))

    render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

    expect(screen.getAllByText('Semiconductors').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Electrical Equipment & Parts').length).toBeGreaterThan(0)
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
