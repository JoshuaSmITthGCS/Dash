import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Planning from './Planning.jsx'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { useFirebaseFinances } from '../lib/useFirebaseFinances.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { usePortfolioMonteCarloCalibration } from '../lib/usePortfolioMonteCarloCalibration.js'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'

vi.mock('../lib/useData.js', () => ({ useData: vi.fn() }))
vi.mock('../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../lib/useFirebaseFinances.js', () => ({ useFirebaseFinances: vi.fn() }))
vi.mock('../lib/usePortfolioTracking.js', () => ({ usePortfolioTracking: vi.fn() }))
vi.mock('../lib/usePortfolioMonteCarloCalibration.js', () => ({ usePortfolioMonteCarloCalibration: vi.fn() }))
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
    useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'MSFT', shares: 1, snapshotSource: 'User-provided brokerage snapshot' }], loading: false })
    usePortfolioTracking.mockReturnValue({ activities: [] })
    usePortfolioMonteCarloCalibration.mockReturnValue({
      riskProfile: { available: false },
      calibratedAt: null,
      stale: true,
      staleReason: null,
      refreshLabel: 'Friday 4pm market close',
      loading: false,
      recalibrate: vi.fn(),
    })
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
        planningAnnualReturnTargetPct: 15,
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
    expect(screen.getAllByText('+15%').length).toBeGreaterThan(0)
    expect(screen.getByText('Now')).toBeInTheDocument()
    expect(screen.getByRole('slider', { name: /Target retirement age/ })).toHaveAttribute('min', '36')
    expect(screen.getByRole('slider', { name: /Annual return target/ })).toHaveAttribute('min', '14.6')
    expect(screen.getByRole('slider', { name: /Annual return target/ })).toHaveAttribute('max', '32.4')
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

  it('saves the return target and uses it for the shared projection center', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    const target = await screen.findByRole('slider', { name: /Annual return target/ })
    expect(target).toHaveValue('15')
    fireEvent.change(target, { target: { value: '18' } })
    fireEvent.pointerUp(target)
    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ planningAnnualReturnTargetPct: 18 }))
    expect(screen.getAllByText('+18%').length).toBeGreaterThan(0)
  })

  it('tracks the current-holdings return as the projection center when available, and can be turned off', async () => {
    useData.mockImplementation((file) => file === 'benchmark-report.json'
      ? { data: { histories: { SPY: { dates, closes: dates.map((_, index) => 100 + index + Math.sin(index) * 4) } } }, loading: false }
      : { data: {
          screen_universe: [{
            ticker: 'MSFT', price: 200,
            analytics_history: { dates, closes: dates.map((_, index) => 100 + index * 2), frequency: 'daily' },
          }],
          portfolio_coverage: [], research: [], benchmark_history: { dates },
        }, loading: false })
    render(<MemoryRouter><Planning /></MemoryRouter>)
    const toggle = await screen.findByRole('checkbox', { name: /Track my current-holdings return/ })
    expect(toggle).toBeChecked()
    const target = screen.getByRole('slider', { name: /Annual return target/ })
    expect(target).toBeDisabled()
    expect(target.value).not.toBe('15')

    fireEvent.click(toggle)
    expect(toggle).not.toBeChecked()
    expect(screen.getByRole('slider', { name: /Annual return target/ })).not.toBeDisabled()
  })

  it('creates a goal tied to the selected Finances pool', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    fireEvent.change(await screen.findByPlaceholderText('Home down payment'), { target: { value: 'Education' } })
    fireEvent.change(screen.getByLabelText('Funding pool'), { target: { value: 'pool-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add goal' }))
    expect(addGoal).toHaveBeenCalledWith(expect.objectContaining({ name: 'Education', poolId: 'pool-1' }))
  })
})
