import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Planning from './Planning.jsx'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { useFirebaseFinances } from '../lib/useFirebaseFinances.js'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'

vi.mock('../lib/useData.js', () => ({ useData: vi.fn() }))
vi.mock('../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../lib/useFirebaseFinances.js', () => ({ useFirebaseFinances: vi.fn() }))
vi.mock('../lib/PreferencesContext.jsx', () => ({ usePreferences: vi.fn(), formatPreferenceMoney: (value) => `$${Number(value).toLocaleString()}` }))
vi.mock('../lib/useProjectionSimulation.js', () => ({ useProjectionSimulation: vi.fn() }))

const dates = Array.from({ length: 48 }, (_, index) => new Date(Date.UTC(2022, index + 1, 0)).toISOString().slice(0, 10))
const fan = [
  { month: 0, year: 0, p10: 100000, p25: 100000, p50: 100000, p75: 100000, p90: 100000 },
  { month: 12, year: 1, p10: 95000, p25: 105000, p50: 120000, p75: 135000, p90: 150000 },
]

describe('Planning hub', () => {
  const updateSettings = vi.fn()
  const addGoal = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    useData.mockImplementation((file) => file === 'benchmark-report.json'
      ? { data: { histories: { SPY: { dates, closes: dates.map((_, index) => 100 + index + Math.sin(index) * 4) } } }, loading: false }
      : { data: { screen_universe: [], portfolio_coverage: [], research: [], benchmark_history: { dates } }, loading: false })
    useFirebasePortfolio.mockReturnValue({ positions: [], loading: false })
    usePreferences.mockReturnValue({ preferences: { defaultBenchmark: 'SPY', privacyMode: false, numberFormat: 'en-US' } })
    useFirebaseFinances.mockReturnValue({
      settings: {
        currentAge: 35,
        retireAge: 65,
        retirementEndAge: 95,
        inflationPct: 2.5,
        monthlyContribution: 200,
        monthlyWithdrawal: 3000,
        currentSavings: 100000,
        allocationAggressiveness: 'growth',
      },
      pools: [{ id: 'pool-1', name: 'Home fund', percent: 25, balance: 20000 }],
      goals: [{ id: 'goal-1', name: 'Home', targetAmount: 50000, targetDate: '2031-08-05', poolId: 'pool-1' }],
      loading: false,
      updateSettings,
      addGoal,
    })
    useProjectionSimulation.mockImplementation((input) => {
      if (!input) return { result: null, loading: false, error: null }
      if (input.targetAmount) return { result: { available: true, goalProbability: 0.74 }, loading: false, error: null }
      const successProbability = input.monthlyContribution >= 350 ? 0.81 : 0.68
      return {
        loading: false,
        error: null,
        result: {
          available: true,
          model: '12-month historical block bootstrap',
          pathCount: 5000,
          blockMonths: 12,
          accumulationMonths: input.accumulationMonths,
          withdrawalMonths: input.withdrawalMonths,
          fan,
          retirementPercentiles: { p10: 95000, p25: 105000, p50: 120000, p75: 135000, p90: 150000 },
          terminalPercentiles: { p10: 50000, p25: 80000, p50: 110000, p75: 150000, p90: 200000 },
          successProbability,
          runtimeMs: 24,
        },
      }
    })
  })

  it('leads with the verdict and names the contribution lever', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    expect(await screen.findByLabelText('Success probability 68 percent')).toBeInTheDocument()
    expect(screen.getByText('Needs attention')).toBeInTheDocument()
    expect(screen.getByText(/Raising monthly contributions by \$150 moves this from 68% to 81%/)).toBeInTheDocument()
  })

  it('resimulates a lever on release and exposes goal probability', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    const contribution = await screen.findByRole('slider', { name: /Monthly contribution/ })
    fireEvent.change(contribution, { target: { value: '350' } })
    fireEvent.pointerUp(contribution)
    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ monthlyContribution: 350 }))
    expect(screen.getByText('74%')).toBeInTheDocument()
    expect(screen.getByText(/Probability of reaching Home/)).toBeInTheDocument()
  })

  it('creates a goal tied to the selected Finances pool', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    fireEvent.change(await screen.findByPlaceholderText('Home down payment'), { target: { value: 'Education' } })
    fireEvent.change(screen.getByLabelText('Funding pool'), { target: { value: 'pool-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add goal' }))
    expect(addGoal).toHaveBeenCalledWith(expect.objectContaining({ name: 'Education', poolId: 'pool-1' }))
  })
})
