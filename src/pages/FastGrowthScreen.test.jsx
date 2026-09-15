import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import FastGrowthScreen from './FastGrowthScreen'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const breakoutQualifyingRow = (overrides = {}) => ({
  ticker: 'UP', name: 'Up Inc', sector: 'Technology', score: 70, stance: 'Buy',
  is_etf: false, price: 110.0,
  technical_detail: { return_5d: 4.0, return_20d: 6.0, volume_ratio_60d: 1.5 },
  fundamental_detail: {},
  history: { closes: [100, 102, 104, 106, 108, 110] },
  ...overrides,
})

const emergingQualifyingRow = (overrides = {}) => ({
  ticker: 'EARLY', name: 'Early Inc', sector: 'Health Care', score: 65, stance: 'Buy',
  is_etf: false, price: 55.0,
  technical_detail: { return_5d: 1.0, relative_strength_20d: 3.0 },
  fundamental_detail: { revenue_growth: 0.15, operating_margin_trend: 0.02 },
  history: { closes: [50, 51, 52, 53, 54, 55] },
  ...overrides,
})

const renderScreen = () => render(<MemoryRouter><FastGrowthScreen /></MemoryRouter>)

describe('FastGrowthScreen since-flagged track record', () => {
  it('shows the plain return since a name first entered the breakout top 10', () => {
    useData.mockReturnValue({
      data: {
        research: [breakoutQualifyingRow()],
        fast_growth_track_record: {
          breakout: { UP: { date_predicted: '2026-09-10', price_at_prediction: 100.0 } },
          emerging: {},
        },
      },
      loading: false, error: null,
    })
    renderScreen()
    expect(screen.getByRole('columnheader', { name: 'Since flagged' })).toBeVisible()
    expect(screen.getByText('since 2026-09-10')).toBeInTheDocument()
    // (110/100 - 1) * 100 = +10.0%
    expect(screen.getByText('+10.0%')).toBeInTheDocument()
  })

  it('shows a dash when a name is not currently in the top 10', () => {
    useData.mockReturnValue({
      data: { research: [breakoutQualifyingRow()], fast_growth_track_record: { breakout: {}, emerging: {} } },
      loading: false, error: null,
    })
    renderScreen()
    const row = screen.getByText('UP', { selector: 'b' }).closest('tr')
    expect(within(row).getByTitle("Not currently in this screen's top 10.")).toHaveTextContent('–')
  })

  it('shows the return since flagged on the emerging-growth tab too', () => {
    useData.mockReturnValue({
      data: {
        research: [emergingQualifyingRow()],
        fast_growth_track_record: {
          breakout: {},
          emerging: { EARLY: { date_predicted: '2026-09-01', price_at_prediction: 50.0 } },
        },
      },
      loading: false, error: null,
    })
    renderScreen()
    fireEvent.change(screen.getByRole('combobox', { name: /screen/i }), { target: { value: 'emerging' } })
    expect(screen.getByText('since 2026-09-01')).toBeInTheDocument()
    // (55/50 - 1) * 100 = +10.0%
    expect(screen.getByText('+10.0%')).toBeInTheDocument()
  })

  it('shows the same field on the mobile card', () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: true, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }))
    useData.mockReturnValue({
      data: {
        research: [breakoutQualifyingRow()],
        fast_growth_track_record: {
          breakout: { UP: { date_predicted: '2026-09-10', price_at_prediction: 100.0 } },
          emerging: {},
        },
      },
      loading: false, error: null,
    })
    renderScreen()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByText('since 2026-09-10')).toBeInTheDocument()
  })
})
