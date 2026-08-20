import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import InsideInformation from './InsideInformation'
import { useData } from '../lib/useData'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../lib/FirebaseAuthContext.jsx', () => ({ useAuth: vi.fn() }))

const result = (overrides = {}) => ({
  ticker: 'ACME', score: 3.5, political_points: 1.5, institutional_points: 2.0,
  members_buying: 2, extraordinary_members: 0, managers_added: 3, managers_dropped: 0,
  institutional_flag: 'CLUSTER_ACCUMULATION', congress_flags: [],
  ...overrides,
})

describe('InsideInformation page', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: null })
  })

  it('renders notable tickers with their flags', () => {
    useData.mockReturnValue({
      data: {
        status: 'success', schema_version: '1.0.0', model_version: 'inside-information-v1.0.0',
        ranked_count: 5, notable_count: 2,
        results: [
          result(),
          result({ ticker: 'WIDGET', institutional_flag: null, congress_flags: ['CLUSTER_TRADE'] }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><InsideInformation /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: /Disclosed/ })).toBeVisible()
    expect(screen.getAllByText('ACME').length).toBeGreaterThan(0)
    expect(screen.getAllByText('WIDGET').length).toBeGreaterThan(0)
    expect(screen.getByText('Cluster accumulation')).toBeVisible()
    expect(screen.getByText('3+ representatives, 14-day span')).toBeVisible()
  })

  it('sorts by institutional or congressional points', () => {
    useData.mockReturnValue({
      data: {
        status: 'success', results: [
          result({ ticker: 'LOWINST', institutional_points: 0.5, political_points: 5.0 }),
          result({ ticker: 'HIGHINST', institutional_points: 5.0, political_points: 0.5 }),
        ],
      },
      loading: false, error: null,
    })

    render(<MemoryRouter><InsideInformation /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'institutional' } })

    const rows = screen.getAllByRole('row').map((row) => row.textContent)
    const highIndex = rows.findIndex((text) => text.includes('HIGHINST'))
    const lowIndex = rows.findIndex((text) => text.includes('LOWINST'))
    expect(highIndex).toBeGreaterThan(-1)
    expect(highIndex).toBeLessThan(lowIndex)
  })

  it('shows an honest empty state when nothing is notable', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [] }, loading: false, error: null })
    render(<MemoryRouter><InsideInformation /></MemoryRouter>)
    expect(screen.getByText(/No notable activity right now/)).toBeVisible()
  })

  it('says the merge did not complete rather than claiming a quiet market', () => {
    useData.mockReturnValue({
      data: { status: 'skipped', results: [] },
      loading: false, error: null,
    })

    render(<MemoryRouter><InsideInformation /></MemoryRouter>)

    expect(screen.getByRole('alert')).toHaveTextContent(/Merge did not run/)
  })

  it('shows the KPI tiles on a successful run', () => {
    useData.mockReturnValue({
      data: { status: 'success', ranked_count: 7, notable_count: 2, results: [result()] },
      loading: false, error: null,
    })

    render(<MemoryRouter><InsideInformation /></MemoryRouter>)

    expect(screen.getByText('7')).toBeVisible()
    expect(screen.getByText('Tickers with disclosed activity').closest('.card')).toHaveTextContent('7')
    expect(screen.getByText('Notable (shown below)').closest('.card')).toHaveTextContent('2')
  })

  it('offers a re-run control to a signed-in user', () => {
    useAuth.mockReturnValue({ currentUser: { uid: 'u1' } })
    useData.mockReturnValue({ data: { status: 'success', results: [result()] }, loading: false, error: null })

    render(<MemoryRouter><InsideInformation /></MemoryRouter>)

    expect(screen.getByRole('button', { name: /Re-run merge/ })).toBeEnabled()
  })

  it('hides the re-run control when nobody is signed in', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [result()] }, loading: false, error: null })

    render(<MemoryRouter><InsideInformation /></MemoryRouter>)

    expect(screen.queryByRole('button', { name: /Re-run merge/ })).toBeNull()
  })
})
