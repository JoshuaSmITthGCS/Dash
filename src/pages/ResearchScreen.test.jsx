import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ResearchScreen from './ResearchScreen'
import { useData } from '../lib/useData'
import { usePreferences } from '../lib/PreferencesContext.jsx'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../lib/PreferencesContext.jsx', () => ({ usePreferences: vi.fn() }))

beforeEach(() => usePreferences.mockReturnValue({ preferences: { mobileResearchView: 'compact' } }))

const row = (overrides = {}) => ({
  rank: 1, ticker: 'AAA', classification: 'actionable value', percentile: 98.3,
  structural_score: 72.4, tactical_score: null, data_coverage: 0.81, peer_group: 'Technology',
  reason_codes: [], ...overrides,
})

const screenProps = {
  file: 'screens/quality-value.json', eyebrow: 'Quarterly screen',
  title: 'Quality at valuation lows', description: 'Cheapness versus own-history multiples.',
}

const renderScreen = () => render(<MemoryRouter><ResearchScreen {...screenProps} /></MemoryRouter>)

describe('ResearchScreen', () => {
  it('renders scored rows with their classification', () => {
    useData.mockReturnValue({
      data: { status: 'success', schema_version: '1.0.0', results: [row(), row({ ticker: 'BBB', rank: 2 })] },
      loading: false, error: null,
    })

    renderScreen()

    expect(screen.getByRole('heading', { name: 'Quality at valuation lows' })).toBeVisible()
    expect(screen.getAllByText('AAA').length).toBeGreaterThan(0)
    expect(screen.getAllByText('actionable value').length).toBeGreaterThan(0)
  })

  it('shows the coverage caveat the screen published alongside its results', () => {
    useData.mockReturnValue({
      data: {
        status: 'success',
        coverage_note: 'Own-history cheapness is measured over at most 120 sessions.',
        results: [row()],
      },
      loading: false, error: null,
    })

    renderScreen()

    expect(screen.getByRole('note')).toHaveTextContent('at most 120 sessions')
  })

  it('reports the reason code when a screen has nothing to publish', () => {
    useData.mockReturnValue({
      data: { status: 'unavailable', reason_code: 'NO_SCORED_UNIVERSE', results: [] },
      loading: false, error: null,
    })

    renderScreen()

    expect(screen.getByText(/NO_SCORED_UNIVERSE/)).toBeVisible()
  })

  it('separates "no results" from "filtered everything out"', () => {
    useData.mockReturnValue({
      data: { status: 'success', results: [row({ sector: 'Technology' })] },
      loading: false, error: null,
    })

    renderScreen()

    expect(screen.queryByText(/No results match these filters/)).toBeNull()
  })
})
