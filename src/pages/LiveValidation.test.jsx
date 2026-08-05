import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LiveValidation from './LiveValidation.jsx'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))

const accumulating = {
  periods_accumulated: 0,
  minimum_periods: 24,
  status: 'accumulating',
  status_message: 'accumulating, 0 of 24 periods',
  mean_rank_ic: null,
  confidence_interval_95: [null, null],
  icir: null,
  bucket_returns: { 5: { buckets: [], monotonic: false } },
}

describe('LiveValidation', () => {
  beforeEach(() => {
    useData.mockImplementation((name) => name.includes('ic_validation')
      ? { data: {
          snapshot_refreshes: 1,
          variants: {
            champion: { '1M': accumulating },
            challenger: { '1M': accumulating },
          },
        }, loading: false, error: null }
      : { data: { summary: { passed: 0, failed: 0 }, results: [] }, loading: false, error: null })
  })

  it('renders honest accumulating states with zero realized periods', () => {
    render(<MemoryRouter><LiveValidation /></MemoryRouter>)
    expect(screen.getByText('Champion versus challenger')).toBeInTheDocument()
    expect(screen.getAllByText('accumulating, 0 of 24 periods')).toHaveLength(2)
    expect(screen.queryByText(/^0\.000$/)).not.toBeInTheDocument()
  })
})
