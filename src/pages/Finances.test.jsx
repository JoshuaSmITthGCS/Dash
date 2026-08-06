import { fireEvent, render, screen } from '@testing-library/react'
import Finances from './Finances'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useFirebaseFinances } from '../lib/useFirebaseFinances'
import { usePreferences } from '../lib/PreferencesContext.jsx'

vi.mock('../lib/useData', () => ({ useData: vi.fn() }))
vi.mock('../lib/useFirebasePortfolio', () => ({ useFirebasePortfolio: vi.fn() }))
vi.mock('../lib/useFirebaseFinances', () => ({ useFirebaseFinances: vi.fn() }))
vi.mock('../lib/PreferencesContext.jsx', () => ({ usePreferences: vi.fn() }))

describe('Finances page', () => {
  const addBudgetItem = vi.fn()
  const addPool = vi.fn()
  const depositToPools = vi.fn()
  const updateSettings = vi.fn()
  const addAccount = vi.fn()
  const updateAccountContribution = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    const benchmarkDates = Array.from({ length: 40 }, (_, index) => new Date(Date.UTC(2022, index + 1, 0)).toISOString().slice(0, 10))
    useData.mockImplementation((file) => file === 'benchmark-report.json'
      ? { data: { histories: { SPY: { dates: benchmarkDates, closes: benchmarkDates.map((_, index) => 100 + index) } } } }
      : { data: { research: [], portfolio_coverage: [] } })
    usePreferences.mockReturnValue({ preferences: { defaultBenchmark: 'SPY' } })
    useFirebasePortfolio.mockReturnValue({ positions: [{ ticker: 'AAPL', shares: 10, costBasis: 100 }] })
    useFirebaseFinances.mockReturnValue({
      settings: {
        currentAge: 30, retireAge: 65, retirementEndAge: 95, inflationPct: 2.5,
        monthlyContribution: 200, monthlyWithdrawal: 3000, currentSavings: 1000,
        planningAnnualReturnTargetPct: 15,
      },
      budgetItems: [
        { id: 'income-1', name: 'Paycheck', amount: 4000, type: 'income' },
        { id: 'expense-1', name: 'Rent', amount: 1500, type: 'expense' },
      ],
      pools: [{ id: 'pool-1', name: 'Emergency fund', percent: 50, balance: 300 }],
      accounts: [{ id: 'account-1', name: 'Fidelity 401(k)', type: '401k', annualContribution: 12000 }],
      loading: false,
      updateSettings,
      addBudgetItem,
      removeBudgetItem: vi.fn(),
      addPool,
      removePool: vi.fn(),
      depositToPools,
      addAccount,
      removeAccount: vi.fn(),
      updateAccountContribution,
    })
  })

  it('shows the budget leftover and lets you add a line item', () => {
    render(<Finances />)
    expect(screen.getAllByText('$2,500').length).toBeGreaterThan(0)

    fireEvent.change(screen.getByPlaceholderText('Paycheck'), { target: { value: 'Freelance' } })
    fireEvent.change(screen.getByPlaceholderText('500'), { target: { value: '300' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(addBudgetItem).toHaveBeenCalledWith({ name: 'Freelance', amount: '300', type: 'expense' })
  })

  it('previews and logs a pool deposit split proportionally', () => {
    render(<Finances />)
    fireEvent.click(screen.getByRole('button', { name: 'Auto-Split Pools' }))

    const amountInput = screen.getByPlaceholderText('2500')
    fireEvent.change(amountInput, { target: { value: '100' } })
    expect(screen.getByText((_, el) => el.className === 'chip' && el.textContent === 'Emergency fund: $100')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add to pools' }))
    expect(depositToPools).toHaveBeenCalledWith([{ id: 'pool-1', share: 100 }])
  })

  it('projects a retirement balance from the current assumptions', () => {
    render(<Finances />)
    fireEvent.click(screen.getByRole('button', { name: 'Retirement' }))
    expect(screen.getAllByText('Median at Retirement').length).toBeGreaterThan(0)
    expect(screen.getByText(/Sync current savings from portfolio/)).toBeInTheDocument()
    const target = screen.getByRole('slider', { name: /Annual return target/ })
    expect(target).toHaveValue('15')
    fireEvent.change(target, { target: { value: '18' } })
    fireEvent.pointerUp(target)
    expect(updateSettings).toHaveBeenCalledWith({ planningAnnualReturnTargetPct: 18 })
  })

  it('tracks a retirement account against its 2026 IRS limit and lets you add another', () => {
    render(<Finances />)
    fireEvent.click(screen.getByRole('button', { name: 'Retirement' }))

    expect(screen.getAllByText(/Fidelity 401\(k\)/).length).toBeGreaterThan(0)
    expect(screen.getByText('$12,000 of $24,500 maxed (49%)')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Fidelity 401(k)'), { target: { value: 'Vanguard Roth IRA' } })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'roth_ira' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add account' }))
    expect(addAccount).toHaveBeenCalledWith({ name: 'Vanguard Roth IRA', type: 'roth_ira' })

    fireEvent.click(screen.getByRole('button', { name: 'Use as retirement contribution' }))
    expect(updateSettings).toHaveBeenCalledWith({ monthlyContribution: 1000 })
  })
})
