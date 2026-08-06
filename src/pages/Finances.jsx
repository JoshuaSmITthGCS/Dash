import { useEffect, useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useFirebaseFinances } from '../lib/useFirebaseFinances'
import { Loading } from '../components/Bits'
import { summarizeBudget, splitAmount } from '../lib/financeSplit'
import { ACCOUNT_TYPES, getAnnualLimit, accountTypeLabel } from '../lib/retirementLimits'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { currentHoldingsSeries } from '../lib/portfolioAnalytics.js'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import { annualReturnTargetRange, applyAllocationAssumption, formatAnnualReturnTarget, normalizeAnnualReturnTarget, projectionConfig, selectProjectionReturnSource } from '../lib/projectionEngine.js'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'
import ProjectionPanel from '../components/ProjectionPanel.jsx'
import Icon from '../components/Icons.jsx'
import { fidelityProjectionBaseline } from '../lib/referenceCashFlows.js'

const money = (value, digits = 0) =>
  value == null ? '–' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })}`

const TABS = [
  { key: 'budget', label: 'Budget' },
  { key: 'pools', label: 'Auto-Split Pools' },
  { key: 'retirement', label: 'Retirement' },
]

/** Sums held-position value against live research prices, falling back to cost basis when a price isn't available. */
function currentPortfolioValue(positions, data) {
  const priceData = Object.fromEntries(
    [...(data?.research || []), ...(data?.portfolio_coverage || [])]
      .filter((row) => row.ticker && row.price != null)
      .map((row) => [String(row.ticker).trim().toUpperCase(), row])
  )
  return positions.reduce((sum, pos) => {
    const ticker = String(pos.ticker || '').trim().toUpperCase()
    const currentPrice = priceData[ticker]?.price ?? pos.snapshotPrice ?? pos.costBasis ?? 0
    return sum + (pos.shares || 0) * currentPrice
  }, 0)
}

export default function Finances() {
  const { data } = useData('advisor.json')
  const { data: benchmarkReport } = useData('benchmark-report.json')
  const { positions } = useFirebasePortfolio()
  const { preferences } = usePreferences()
  const finances = useFirebaseFinances()
  const [tab, setTab] = useState('budget')
  const [budgetForm, setBudgetForm] = useState({ name: '', amount: '', type: 'expense' })
  const [poolForm, setPoolForm] = useState({ name: '', percent: '' })
  const [depositAmount, setDepositAmount] = useState('')
  const [accountForm, setAccountForm] = useState({ name: '', type: ACCOUNT_TYPES[0].key })
  const [selectedAccountId, setSelectedAccountId] = useState(null)
  const [returnTargetDraft, setReturnTargetDraft] = useState(null)
  const [returnTargetCommitted, setReturnTargetCommitted] = useState(null)
  const minimumRetirementAge = Math.max(
    projectionConfig.lever_ranges.retirement_age.minimum,
    finances.settings.currentAge + projectionConfig.minimum_years_until_retirement,
  )
  const maximumRetirementAge = Math.max(projectionConfig.lever_ranges.retirement_age.maximum, minimumRetirementAge)
  const retirementAge = Math.min(maximumRetirementAge, Math.max(minimumRetirementAge, finances.settings.retireAge))

  const portfolioValue = useMemo(() => currentPortfolioValue(positions, data), [positions, data])
  const budgetSummary = useMemo(() => summarizeBudget(finances.budgetItems), [finances.budgetItems])
  const totalPoolBalance = finances.pools.reduce((sum, pool) => sum + (pool.balance || 0), 0)
  const accounts = finances.accounts || []
  const totalAnnualFromAccounts = accounts.reduce((sum, account) => sum + (account.annualContribution || 0), 0)
  const monthlyFromAccounts = totalAnnualFromAccounts / 12
  const projectionSource = useMemo(() => {
    const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
    const portfolioSeries = currentHoldingsSeries(positions, prices, data?.benchmark_history?.dates || [])
    const benchmarkSymbol = preferences.defaultBenchmark
    const benchmark = benchmarkReport?.histories?.[benchmarkSymbol]
    return selectProjectionReturnSource(
      portfolioSeries,
      benchmark,
      benchmarkSymbol,
      fidelityProjectionBaseline(positions),
    )
  }, [benchmarkReport, data, positions, preferences.defaultBenchmark])
  const returnTargetRange = useMemo(() => annualReturnTargetRange(projectionSource), [projectionSource])
  const savedAnnualReturnTargetPct = normalizeAnnualReturnTarget(finances.settings.planningAnnualReturnTargetPct, projectionSource)
  const annualReturnTargetPct = returnTargetCommitted ?? savedAnnualReturnTargetPct
  const displayedAnnualReturnTargetPct = returnTargetDraft ?? annualReturnTargetPct

  useEffect(() => {
    setReturnTargetDraft(savedAnnualReturnTargetPct)
    setReturnTargetCommitted(savedAnnualReturnTargetPct)
  }, [savedAnnualReturnTargetPct])

  const projectionInput = useMemo(() => projectionSource.available ? {
    monthlyReturns: applyAllocationAssumption(
      projectionSource.returns,
      finances.settings.allocationAggressiveness || projectionConfig.allocation_default,
      annualReturnTargetPct / 100,
    ),
    currentBalance: finances.settings.currentSavings,
    monthlyContribution: finances.settings.monthlyContribution,
    monthlyWithdrawal: finances.settings.monthlyWithdrawal,
    inflationPct: finances.settings.inflationPct,
    accumulationMonths: Math.max(projectionConfig.months_per_year, (retirementAge - finances.settings.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: Math.max(0, (finances.settings.retirementEndAge - retirementAge) * projectionConfig.months_per_year),
  } : null, [annualReturnTargetPct, finances.settings, projectionSource, retirementAge])
  const projection = useProjectionSimulation(projectionInput)
  const depositPreview = splitAmount(parseFloat(depositAmount) || 0, finances.pools)
  const projectedMedian = projection.result?.retirementPercentiles?.p50
  const successProbability = projection.result?.successProbability

  if (finances.loading) return <Loading />

  const handleAddBudgetItem = (event) => {
    event.preventDefault()
    if (!budgetForm.name || !budgetForm.amount) return
    finances.addBudgetItem(budgetForm)
    setBudgetForm({ name: '', amount: '', type: budgetForm.type })
  }

  const handleAddPool = (event) => {
    event.preventDefault()
    if (!poolForm.name || !poolForm.percent) return
    finances.addPool(poolForm)
    setPoolForm({ name: '', percent: '' })
  }

  const handleDeposit = (event) => {
    event.preventDefault()
    const amount = parseFloat(depositAmount)
    if (!amount || !finances.pools.length) return
    finances.depositToPools(splitAmount(amount, finances.pools).map(({ id, share }) => ({ id, share })))
    setDepositAmount('')
  }

  const handleAddAccount = (event) => {
    event.preventDefault()
    if (!accountForm.name || !accountForm.type) return
    finances.addAccount(accountForm)
    setAccountForm({ name: '', type: accountForm.type })
  }

  const commitReturnTarget = () => {
    const next = normalizeAnnualReturnTarget(displayedAnnualReturnTargetPct, projectionSource)
    if (next === annualReturnTargetPct) return
    setReturnTargetCommitted(next)
    finances.updateSettings({ planningAnnualReturnTargetPct: next })
  }

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Investing readiness</span>
          <h1 className="page-title">My <span className="accent">finances</span></h1>
          <p className="page-sub">
            Budget your income, auto-split savings into pools, and project how today's contributions grow toward retirement.
          </p>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 20 }}>
        <div className="card kpi">
          <div className="kpi-label">Monthly Leftover</div>
          <div className="kpi-value" style={{ color: budgetSummary.leftover >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
            {money(budgetSummary.leftover)}
          </div>
          <div className="kpi-note">{money(budgetSummary.income)} income − {money(budgetSummary.expenses)} expenses</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Saved in Pools</div>
          <div className="kpi-value">{money(totalPoolBalance, 2)}</div>
          <div className="kpi-note">{finances.pools.length} pool{finances.pools.length === 1 ? '' : 's'}</div>
        </div>
        <div className="card kpi">
          <div className="kpi-label">Median at Retirement</div>
          <div className="kpi-value">{projection.loading ? 'Simulating…' : money(projectedMedian)}</div>
          <div className="kpi-note">From 5,000 historical return paths</div>
        </div>
      </div>

      <div className="filters">
        {TABS.map((item) => (
          <button key={item.key} className={`tab ${tab === item.key ? 'active' : ''}`} onClick={() => setTab(item.key)}>
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'budget' && (
        <div className="card card-pad">
          <div className="sec-label">Add income or expense</div>
          <form onSubmit={handleAddBudgetItem} className="finance-form finance-form-budget">
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Name</label>
              <input type="text" placeholder="Paycheck" value={budgetForm.name} required
                onChange={(e) => setBudgetForm({ ...budgetForm, name: e.target.value })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Monthly amount</label>
              <input type="number" step="0.01" placeholder="500" value={budgetForm.amount} required
                onChange={(e) => setBudgetForm({ ...budgetForm, amount: e.target.value })} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Type</label>
              <select value={budgetForm.type} onChange={(e) => setBudgetForm({ ...budgetForm, type: e.target.value })}>
                <option value="income">Income</option>
                <option value="expense">Expense</option>
              </select>
            </div>
            <div><button type="submit" className="tab active">Add</button></div>
          </form>

          <div className="sec-label">Income</div>
          {finances.budgetItems.filter((item) => item.type === 'income').length === 0 && (
            <p className="body-copy" style={{ marginBottom: 12 }}>No income items yet.</p>
          )}
          {finances.budgetItems.filter((item) => item.type === 'income').map((item) => (
            <div key={item.id} className="finance-item-row">
              <span>{item.name}</span>
              <span className="mono" style={{ color: 'var(--pos)' }}>{money(item.amount)}</span>
              <button className="text-button danger" onClick={() => finances.removeBudgetItem(item.id)}>Remove</button>
            </div>
          ))}

          <div className="sec-label">Expenses</div>
          {finances.budgetItems.filter((item) => item.type === 'expense').length === 0 && (
            <p className="body-copy" style={{ marginBottom: 12 }}>No expense items yet.</p>
          )}
          {finances.budgetItems.filter((item) => item.type === 'expense').map((item) => (
            <div key={item.id} className="finance-item-row">
              <span>{item.name}</span>
              <span className="mono" style={{ color: 'var(--neg)' }}>{money(item.amount)}</span>
              <button className="text-button danger" onClick={() => finances.removeBudgetItem(item.id)}>Remove</button>
            </div>
          ))}

          <div className="callout" style={{ marginTop: 20 }}>
            <strong>{money(budgetSummary.leftover)}</strong> left over each month.{' '}
            <button className="text-button" style={{ padding: 0, minHeight: 'auto' }}
              onClick={() => finances.updateSettings({ monthlyContribution: Math.max(0, Math.round(budgetSummary.leftover)) })}>
              Use as retirement contribution
            </button>
          </div>
        </div>
      )}

      {tab === 'pools' && (
        <>
          <div className="card card-pad" style={{ marginBottom: 20 }}>
            <div className="sec-label">Add a pool</div>
            <form onSubmit={handleAddPool} className="finance-form finance-form-pool">
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Name</label>
                <input type="text" placeholder="Emergency fund" value={poolForm.name} required
                  onChange={(e) => setPoolForm({ ...poolForm, name: e.target.value })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Percent</label>
                <input type="number" step="1" min="0" max="100" placeholder="30" value={poolForm.percent} required
                  onChange={(e) => setPoolForm({ ...poolForm, percent: e.target.value })} />
              </div>
              <div><button type="submit" className="tab active">Add pool</button></div>
            </form>
          </div>

          <div className="card card-pad" style={{ marginBottom: 20 }}>
            {finances.pools.length === 0 ? (
              <p className="body-copy">Add at least one pool to start splitting deposits.</p>
            ) : (
              finances.pools.map((pool) => (
                <div key={pool.id} className="finance-pool-row">
                  <div className="finance-pool-head">
                    <span>{pool.name}</span>
                    <span className="mono" style={{ color: 'var(--text-faint)' }}>{pool.percent}%</span>
                  </div>
                  <div className="pool-bar"><div className="pool-bar-fill" style={{ width: `${Math.min(100, pool.percent)}%` }} /></div>
                  <div className="finance-pool-foot">
                    <span className="mono" style={{ fontWeight: 600 }}>{money(pool.balance, 2)} saved</span>
                    <button className="text-button danger" onClick={() => finances.removePool(pool.id)}>Remove</button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="card card-pad">
            <div className="sec-label">Log a deposit</div>
            <form onSubmit={handleDeposit} className="finance-form finance-form-deposit">
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Amount to split</label>
                <input type="number" step="0.01" placeholder={budgetSummary.leftover > 0 ? budgetSummary.leftover.toFixed(0) : '0'}
                  value={depositAmount} onChange={(e) => setDepositAmount(e.target.value)} />
              </div>
              <div><button type="submit" className="tab active" disabled={!finances.pools.length}>Add to pools</button></div>
            </form>
            {depositPreview.some((pool) => pool.share > 0) && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {depositPreview.map((pool) => (
                  <span key={pool.id} className="chip">{pool.name}: {money(pool.share, 2)}</span>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {tab === 'retirement' && (
        <>
          <div className="card card-pad" style={{ marginBottom: 20 }}>
            <div className="sec-label">Assumptions</div>
            <div className="grid grid-3" style={{ gap: 12 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Current age</label>
                <input type="number" value={finances.settings.currentAge}
                  onChange={(e) => finances.updateSettings({ currentAge: parseInt(e.target.value, 10) || 0 })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Retirement age</label>
                <input type="number" min={minimumRetirementAge} max={maximumRetirementAge} value={retirementAge}
                  onChange={(e) => finances.updateSettings({ retireAge: parseInt(e.target.value, 10) || 0 })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Inflation %</label>
                <input type="number" step="0.1" value={finances.settings.inflationPct}
                  onChange={(e) => finances.updateSettings({ inflationPct: parseFloat(e.target.value) || 0 })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Current savings</label>
                <input type="number" step="1" value={finances.settings.currentSavings}
                  onChange={(e) => finances.updateSettings({ currentSavings: parseFloat(e.target.value) || 0 })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Monthly contribution</label>
                <input type="number" step="1" value={finances.settings.monthlyContribution}
                  onChange={(e) => finances.updateSettings({ monthlyContribution: parseFloat(e.target.value) || 0 })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Plan through age</label>
                <input type="number" min={finances.settings.retireAge} max="120" value={finances.settings.retirementEndAge}
                  onChange={(e) => finances.updateSettings({ retirementEndAge: parseInt(e.target.value, 10) || projectionConfig.default_retirement_end_age })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Monthly retirement spending</label>
                <input type="number" min="0" step="100" value={finances.settings.monthlyWithdrawal}
                  onChange={(e) => finances.updateSettings({ monthlyWithdrawal: parseFloat(e.target.value) || 0 })} />
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <label htmlFor="retirement-return-target" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 4, fontSize: 13 }}><span>Annual return target</span><strong>{formatAnnualReturnTarget(displayedAnnualReturnTargetPct)}</strong></label>
                <input id="retirement-return-target" type="range" min={returnTargetRange.minimumPct} max={returnTargetRange.maximumPct} step={returnTargetRange.stepPct} value={displayedAnnualReturnTargetPct}
                  onChange={(event) => setReturnTargetDraft(Number(event.target.value))} onPointerUp={commitReturnTarget} onKeyUp={commitReturnTarget} />
                <small className="body-copy">Sets the dotted median for retirement. {returnTargetRange.evidence ? `${returnTargetRange.evidence.lowerPct.toFixed(2)}% year to date to ${returnTargetRange.evidence.upperPct.toFixed(2)}% trailing one year.` : 'Historical returns set the uncertainty around your target.'}</small>
              </div>
            </div>
            <button className="text-button" style={{ padding: 0, minHeight: 'auto', marginTop: 12 }}
              onClick={() => finances.updateSettings({ currentSavings: Math.round(portfolioValue) })}>
              Sync current savings from portfolio ({money(portfolioValue)})
            </button>
          </div>

          <div className="card card-pad" style={{ marginBottom: 20 }}>
            <div className="sec-label">Retirement & investing accounts</div>
            <p className="body-copy" style={{ marginBottom: 12 }}>
              Track contribution room against the 2026 IRS limits for each account.
              Roth IRA room can phase out at higher incomes. This assumes you're eligible.
            </p>
            {accounts.length > 0 && <nav className="finance-account-tabs" aria-label="Retirement accounts">{accounts.map((account, index) => <button type="button" className={(selectedAccountId || accounts[0]?.id) === account.id ? 'active' : ''} key={account.id} onClick={() => { setSelectedAccountId(account.id); document.getElementById(`finance-account-${account.id}`)?.scrollIntoView({ block: 'nearest' }) }}><span>{account.name}<small>{accountTypeLabel(account.type)}</small></span>{index === 0 && <Icon name="chevron" size={16} />}</button>)}</nav>}
            <form onSubmit={handleAddAccount} className="finance-form finance-form-account">
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Name</label>
                <input type="text" placeholder="Fidelity 401(k)" value={accountForm.name} required
                  onChange={(e) => setAccountForm({ ...accountForm, name: e.target.value })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Type</label>
                <select value={accountForm.type} onChange={(e) => setAccountForm({ ...accountForm, type: e.target.value })}>
                  {ACCOUNT_TYPES.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </div>
              <div><button type="submit" className="tab active">Add account</button></div>
            </form>

            {accounts.length === 0 ? (
              <p className="body-copy">Add a 401(k), IRA, HSA, or taxable account to track contributions toward the annual max.</p>
            ) : (
              accounts.map((account) => {
                const limit = getAnnualLimit(account.type, finances.settings.currentAge)
                const contributed = account.annualContribution || 0
                const pct = limit ? Math.min(100, (contributed / limit) * 100) : 0
                return (
                  <div key={account.id} id={`finance-account-${account.id}`} className={`finance-pool-row${(selectedAccountId || accounts[0]?.id) === account.id ? ' selected-account' : ''}`}>
                    <div className="finance-pool-head">
                      <span>{account.name} <span className="mono" style={{ color: 'var(--text-faint)', fontWeight: 400 }}>· {accountTypeLabel(account.type)}</span></span>
                      <button className="text-button danger" onClick={() => finances.removeAccount(account.id)}>Remove</button>
                    </div>
                    {limit ? (
                      <>
                        <div className="pool-bar"><div className="pool-bar-fill" style={{ width: `${pct}%` }} /></div>
                        <div className="finance-pool-foot">
                          <span className="mono">{money(contributed)} of {money(limit)} maxed ({pct.toFixed(0)}%)</span>
                          <span className="mono" style={{ color: 'var(--text-faint)' }}>{money(Math.max(0, limit - contributed))} room left</span>
                        </div>
                      </>
                    ) : (
                      <div className="finance-pool-foot">
                        <span className="mono">{money(contributed)} contributed this year</span>
                        <span className="mono" style={{ color: 'var(--text-faint)' }}>No IRS cap</span>
                      </div>
                    )}
                    <div style={{ marginTop: 8 }}>
                      <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Annual contribution</label>
                      <input type="number" step="1" min="0" value={contributed}
                        onChange={(e) => finances.updateAccountContribution(account.id, parseFloat(e.target.value) || 0)} />
                    </div>
                  </div>
                )
              })
            )}

            {accounts.length > 0 && (
              <div className="callout" style={{ marginTop: 20 }}>
                <strong>{money(monthlyFromAccounts, 2)}/mo</strong> equivalent across all accounts ({money(totalAnnualFromAccounts)}/yr).{' '}
                <button className="text-button" style={{ padding: 0, minHeight: 'auto' }}
                  onClick={() => finances.updateSettings({ monthlyContribution: Math.round(monthlyFromAccounts) })}>
                  Use as retirement contribution
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-3" style={{ marginBottom: 20 }}>
            <div className="card kpi">
              <div className="kpi-label">Median at Retirement</div>
              <div className="kpi-value">{projection.loading ? 'Simulating…' : money(projectedMedian)}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">Median in Today's Dollars</div>
              <div className="kpi-value">{money(projection.result?.retirementPercentilesReal?.p50)}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">Savings Last Through Age {finances.settings.retirementEndAge}</div>
              <div className="kpi-value" style={{ color: 'var(--pos)' }}>{successProbability == null ? '–' : `${(successProbability * 100).toFixed(0)}%`}</div>
              <div className="kpi-note">Given {money(finances.settings.monthlyWithdrawal)} monthly spending</div>
            </div>
          </div>

          <ProjectionPanel
            state={projection}
            source={projectionSource}
            money={money}
            annualReturnTargetPct={annualReturnTargetPct}
            startAge={finances.settings.currentAge}
            retirementAge={retirementAge}
            endAge={finances.settings.retirementEndAge}
            title="Retirement outcome range"
            assumptionNote={`The dotted median targets ${formatAnnualReturnTarget(annualReturnTargetPct)} annually. Historical monthly returns determine the range around it.`}
          />
        </>
      )}
    </>
  )
}
