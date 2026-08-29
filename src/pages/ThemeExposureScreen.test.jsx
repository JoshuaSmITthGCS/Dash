import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ThemeExposureScreen, { crossThemeNames } from './ThemeExposureScreen.jsx'
import { useData } from '../lib/useData'
import { useAdvisorRefresh } from '../lib/useAdvisorRefresh.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
// The screen re-ranks its own names and hides the reader's holdings, so it reaches for the
// refresh dispatcher and the portfolio. Both are stubbed: what is under test here is what the
// screen does with them, not Firebase.
vi.mock('../lib/useAdvisorRefresh.js', () => ({ useAdvisorRefresh: vi.fn() }))
vi.mock('../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))

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

const refreshStub = () => ({
  status: 'idle', message: '', refreshing: false, available: true,
  requestFocusedRefresh: vi.fn(), requestRefresh: vi.fn(), requestReanalyze: vi.fn(),
  elapsedLabel: null, progress: 0, stage: '',
})

describe('Theme Exposure screen', () => {
  beforeEach(() => {
    useAdvisorRefresh.mockReturnValue(refreshStub())
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
  })

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

  describe('why the top rows rank where they do', () => {
    const ranked = {
      ...multiThemeData,
      theme_screen: {
        ...multiThemeData.theme_screen,
        themes: [{
          ...multiThemeData.theme_screen.themes[0],
          rows: [{
            ticker: 'EME', name: 'EMCOR', theme_exposure_score: 100, opportunity_score: 88.6,
            eligible: true, candidate_source: 'sector_peer', role: 'infrastructure',
            why: ['In this theme because it is a peer-group neighbour of this theme\'s anchors'],
            rank_reason: [
              'Ranks #1 of 20 on an opportunity score of 88.6: exposure 100 (45% of that score), business quality 77 (35% of that score), in the cheapest third of its sector (20% of that score)',
              'It ranks above MCHP (87.5) mainly on business quality: 77 against 74',
              'Its research rating reads "Insufficient data" because no financial statements were pulled for it this run - 44% of that model\'s evidence resolved. Statements go to a shortlist of the universe, and this screen exists to surface names that are not already published leaders, so the business-quality leg above rests on price-based multiples rather than on returns on capital, leverage or accounting quality',
            ],
          }],
        }],
      },
    }

    it('shows the top row s ranking explanation without needing a click', () => {
      useData.mockImplementation(() => ({ data: ranked, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      // Visible outright, not inside the collapsed <details> the other clauses use.
      const reason = document.querySelector('.row-rank-reason')
      expect(reason).toBeTruthy()
      expect(reason.textContent).toMatch(/Ranks #1 of 20/)
      expect(reason.textContent).toMatch(/exposure 100 \(45% of that score\)/)
      expect(reason.textContent).toMatch(/mainly on business quality: 77 against 74/)
    })

    it('says on the row what an "Insufficient data" rating means for the ranking', () => {
      useData.mockImplementation(() => ({ data: ranked, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByText(/no financial statements were pulled for it this run/))
        .toBeInTheDocument()
      expect(screen.getByText(/rests on price-based multiples/)).toBeInTheDocument()
    })
  })

  describe('screen controls', () => {
    it('re-ranks exactly the names this screen scored, not the whole universe', () => {
      const requestFocusedRefresh = vi.fn()
      useAdvisorRefresh.mockReturnValue({ ...refreshStub(), requestFocusedRefresh })
      useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      // by_ticker is every company scored against any theme - the set the button re-runs.
      const [, , , focusSymbols] = useAdvisorRefresh.mock.calls.at(-1)
      expect(focusSymbols.sort()).toEqual(['ETN', 'NVDA'])

      fireEvent.click(screen.getByRole('button', { name: /Re-rank these 2 names/ }))
      expect(requestFocusedRefresh).toHaveBeenCalled()
    })

    it('sends holdings as holdings and the screen s names as a re-ranking request', () => {
      // Two different workflow inputs downstream: passing theme members as holdings would
      // relabel every one of them as something the reader owns.
      useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'AAPL' }], loading: false })
      useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const [, , holdings, focusSymbols] = useAdvisorRefresh.mock.calls.at(-1)
      expect(holdings).toEqual(['AAPL'])
      expect(focusSymbols).not.toContain('AAPL')
    })

    it('hides holdings from every ranked list when asked', () => {
      useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'nvda' }], loading: false })
      useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)
      expect(screen.getAllByText('NVDA').length).toBeGreaterThan(0)

      fireEvent.click(screen.getByRole('checkbox', { name: /Hide my holdings/ }))

      expect(screen.queryByText('NVDA')).toBeNull()
      expect(screen.getAllByText('ETN').length).toBeGreaterThan(0)
    })

    it('leaves the trend measurement alone when holdings are hidden', () => {
      // Breadth, leadership and crowding describe the whole group. Recomputing them over
      // what one reader chose to hide would report a different theme under the same name.
      const trend = {
        contributes_to_exposure: false, members_measured: 20,
        direction: { relative_strength_median: 6.4, acceleration_median: 1.2, label: 'strengthening' },
        breadth: { outperforming_share: 0.72, above_50d_share: 0.68, above_20d_share: 0.61, label: 'broad' },
        crowding: { expensiveness_percentile_median: 41, already_priced: false },
        leadership: { largest: 'NVDA', median_excluding_largest: 5.5, led_by_one_name: false },
        fundamental_confirmation: { positive_revision_share: 0.6, volume_ratio_median: 1.2 },
        chain_confirmation: { confirms: true, root_relative_strength: 8, supply_chain_relative_strength: 5 },
        roles: [], verdict: { label: 'broadening', summary: 'The group is outperforming.' },
      }
      useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'NVDA' }], loading: false })
      useData.mockImplementation(() => ({
        data: {
          ...multiThemeData,
          theme_screen: {
            ...multiThemeData.theme_screen,
            themes: [{ ...multiThemeData.theme_screen.themes[0], trend }],
          },
        },
        loading: false,
        error: null,
      }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)
      fireEvent.click(screen.getByRole('checkbox', { name: /Hide my holdings/ }))

      const panel = screen.getByLabelText('Trend evaluation')
      expect(within(panel).getByText('72%')).toBeInTheDocument()      // breadth unchanged
      expect(within(panel).getByText('broadening')).toBeInTheDocument()
      expect(screen.getByText(/trend reading is unchanged/)).toBeInTheDocument()
    })

    it('offers no holdings toggle to a reader with no holdings', () => {
      useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByRole('checkbox', { name: /Hide my holdings/ })).toBeDisabled()
    })

    it('offers no re-rank button to a signed-out reader', () => {
      useAdvisorRefresh.mockReturnValue({ ...refreshStub(), available: false })
      useData.mockImplementation(() => ({ data: multiThemeData, loading: false, error: null }))

      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.queryByRole('button', { name: /Re-rank/ })).toBeNull()
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

  describe('connectivity graph', () => {
    // Same shape pipeline/theme_graph.build_connectivity actually publishes, attached to
    // multiThemeData's two themes (ai_infrastructure, grid_electrification).
    const connectivityData = {
      ...multiThemeData,
      theme_screen: {
        ...multiThemeData.theme_screen,
        themes: multiThemeData.theme_screen.themes.map((theme) => ({
          ...theme, root_driver_tag: theme.id === 'ai_infrastructure' ? 'ELECTRIFICATION_DEMAND' : 'ELECTRIFICATION_DEMAND',
        })),
        connectivity: {
          root_driver_taxonomy: { ELECTRIFICATION_DEMAND: 'Electricity demand & electrification' },
          methodology: 'Edge weights are a declared heuristic.',
          by_ticker: {
            ETN: { connectivity_score: 3.0, effective_theme_count: 1, cleared_theme_count: 2 },
          },
          per_theme: {
            ai_infrastructure: {
              structural_rank: { contributes_to_exposure: false, composite_score: 0.82, tier: 'broadening' },
              connectivity_leaders: [{ ticker: 'ETN', role: 'infrastructure', theme_exposure_score: 74,
                connectivity_score: 3.0, effective_theme_count: 1, cleared_theme_count: 2 }],
              tail_pick: { tier: 1, ticker: 'NVDA', caveat: null },
            },
            grid_electrification: {
              structural_rank: { contributes_to_exposure: false, composite_score: 0.41, tier: 'mixed' },
              connectivity_leaders: [],
              tail_pick: { tier: 2, ticker: 'ETN', caveat: 'Secondary exposure to AI Infrastructure Buildout (shared root driver)' },
            },
          },
          ranked_themes: ['ai_infrastructure', 'grid_electrification'],
        },
        watchlist: [{
          id: 'humanoid_robotics', display_name: 'Humanoid & General-Purpose Robotics',
          why_not_promoted: 'No deployed, revenue-generating per-unit product yet.',
          promotion_threshold: 'Real per-unit deployment revenue.', recheck_cadence: 'quarterly',
        }],
      },
    }

    it('groups themes under their root driver, with a link to each theme panel', () => {
      useData.mockImplementation(() => ({ data: connectivityData, loading: false, error: null }))
      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByText('Electricity demand & electrification')).toBeInTheDocument()
      const heading = screen.getByRole('heading', { name: /Root drivers/ })
      const group = heading.closest('section')
      expect(within(group).getAllByRole('link', { name: 'AI Infrastructure Buildout' }).length).toBeGreaterThan(0)
    })

    it('ranks a theme panel s cross-theme leaderboard by connectivity score', () => {
      useData.mockImplementation(() => ({ data: connectivityData, loading: false, error: null }))
      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByRole('heading', { name: /Cross-theme leaderboard/ })).toBeInTheDocument()
      expect(screen.getByText(/connectivity 3/)).toBeInTheDocument()
      expect(screen.getByText(/1 effective of 2 cleared themes/)).toBeInTheDocument()
    })

    it('publishes a tail pick per theme, never rendering a relaxed pick as clean', () => {
      useData.mockImplementation(() => ({ data: connectivityData, loading: false, error: null }))
      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByRole('heading', { name: /Cleanest single-theme picks/ })).toBeInTheDocument()
      expect(screen.getAllByText('Clean pick').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Relaxed pick').length).toBeGreaterThan(0)
      expect(screen.getByText(/Secondary exposure to AI Infrastructure Buildout/)).toBeInTheDocument()
    })

    it('reports a Tier 4 theme as no unique pick, with its reason', () => {
      useData.mockImplementation(() => ({
        data: {
          ...connectivityData,
          theme_screen: {
            ...connectivityData.theme_screen,
            connectivity: {
              ...connectivityData.theme_screen.connectivity,
              per_theme: {
                ...connectivityData.theme_screen.connectivity.per_theme,
                grid_electrification: {
                  ...connectivityData.theme_screen.connectivity.per_theme.grid_electrification,
                  tail_pick: { tier: 4, ticker: null, caveat: null, reason: 'no candidate cleared this theme\'s guardrails to pick from' },
                },
              },
            },
          },
        },
        loading: false, error: null,
      }))
      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getAllByText('No unique pick').length).toBeGreaterThan(0)
      expect(screen.getByText(/no candidate cleared this theme's guardrails/)).toBeInTheDocument()
    })

    it('sorts the theme index by evidence by default, and lets a reader switch to trend', () => {
      useData.mockImplementation(() => ({ data: connectivityData, loading: false, error: null }))
      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      const nav = screen.getByRole('navigation', { name: 'Themes in this report' })
      const links = () => within(nav).getAllByRole('link').map((link) => link.textContent)
      // AI Infrastructure's composite (0.82) outranks Grid's (0.41) - the evidence-sorted default.
      expect(links()).toEqual(['AI Infrastructure Buildout', 'Grid & Electrification Buildout'])

      fireEvent.click(screen.getByRole('button', { name: 'By trend' }))
      // Neither theme fixture declares a trend verdict, so the trend sort falls back to its
      // own tiebreak - this only asserts the toggle re-renders without crashing and the evidence
      // scores stop being what is shown, not a specific trend order.
      expect(screen.queryByText('0.82 · broadening')).not.toBeInTheDocument()
    })

    it('notes a watchlist candidate as watched, not scored', () => {
      useData.mockImplementation(() => ({ data: connectivityData, loading: false, error: null }))
      render(<MemoryRouter><ThemeExposureScreen /></MemoryRouter>)

      expect(screen.getByRole('heading', { name: /Watching, not promoted/ })).toBeInTheDocument()
      expect(screen.getByText(/Humanoid & General-Purpose Robotics/)).toBeInTheDocument()
    })
  })
})
