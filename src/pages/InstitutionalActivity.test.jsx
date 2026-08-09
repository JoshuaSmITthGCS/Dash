import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import InstitutionalActivity from './InstitutionalActivity'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

const result = (overrides = {}) => ({
  ticker: 'ACME', cusip: '000000001', managers_added: 2, managers_dropped: 0,
  share_change_pct: 0.35, flag: 'ACCUMULATION', notes: ['2 curated managers added'],
  as_of: '2026-05-14',
  ...overrides,
})

describe('InstitutionalActivity page', () => {
  it('renders flagged tickers', () => {
    useData.mockReturnValue({
      data: {
        status: 'success', schema_version: '1.1.0', model_version: 'institutional-13f-v1.1.0',
        managers_reviewed: 3, managers_configured: 9, cusips_seen: 10, cusips_mapped: 4,
        amendments_seen: 1,
        results: [result(), result({ ticker: 'WIDGET', flag: 'CLUSTER_DISTRIBUTION', managers_added: 0, managers_dropped: 3 })],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><InstitutionalActivity /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: /Institutional/ })).toBeVisible()
    expect(screen.getAllByText('ACME').length).toBeGreaterThan(0)
    expect(screen.getAllByText('WIDGET').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Accumulation').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Cluster distribution').length).toBeGreaterThan(0)
  })

  it('filters by flag', () => {
    useData.mockReturnValue({
      data: { status: 'success', results: [
        result({ ticker: 'ACME', flag: 'ACCUMULATION' }),
        result({ ticker: 'WIDGET', flag: 'DISTRIBUTION' }),
      ] },
      loading: false, error: null,
    })

    render(<MemoryRouter><InstitutionalActivity /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Flag'), { target: { value: 'DISTRIBUTION' } })

    expect(screen.queryByText('ACME')).not.toBeInTheDocument()
    expect(screen.getAllByText('WIDGET').length).toBeGreaterThan(0)
  })

  it('shows an honest empty state when nothing has been collected yet', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [] }, loading: false, error: null })
    render(<MemoryRouter><InstitutionalActivity /></MemoryRouter>)
    expect(screen.getByText(/No flagged activity yet/)).toBeVisible()
  })

  it('shows the manager-coverage KPI tiles', () => {
    useData.mockReturnValue({
      data: {
        status: 'success', managers_reviewed: 3, managers_configured: 9,
        cusips_seen: 10, cusips_mapped: 4, amendments_seen: 1, results: [result()],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><InstitutionalActivity /></MemoryRouter>)

    expect(screen.getByText('3')).toBeVisible()
    expect(screen.getByText(/of 9 configured/)).toBeVisible()
  })
})
