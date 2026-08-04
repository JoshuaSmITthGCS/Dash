import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import EarlySessionResearch from './EarlySessionResearch'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))

describe('EarlySessionResearch', () => {
  it('presents killed screens as data-gate outcomes with zero candidates', () => {
    useData.mockReturnValue({ data: {
      schema_version: '1.0.0', model_version: 'gate-v1', disclaimer: 'Research only.',
      screens: {
        premarket_reversal: { status: 'killed', reason_code: 'NO_EXTENDED_HOURS_OHLCV', fallback: 'next_open_daily_research_only', candidate_count: 0 },
        first_hour_reversal: { status: 'killed', reason_code: 'NO_SUB_15_MINUTE_BARS', fallback: 'end_of_day_studies_only', candidate_count: 0 },
      },
      capabilities: [{ capability: 'Premarket OHLCV', available: false, provider: 'None', granularity: 'Daily', freshness: 'Not collected', verdict: 'KILL_PREMARKET_SCREEN' }],
    }, loading: false, error: null })

    render(<MemoryRouter><EarlySessionResearch /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Early-session reversals' })).toBeVisible()
    expect(screen.getAllByText('Killed by data gate')).toHaveLength(2)
    expect(screen.getByText('Premarket OHLCV')).toBeVisible()
    expect(screen.getByText('Unavailable')).toBeVisible()
    expect(screen.getByText(/successful research outcome/)).toBeVisible()
  })
})
