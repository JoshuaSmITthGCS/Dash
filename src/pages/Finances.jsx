import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio'
import { useFirebaseFinances } from '../lib/useFirebaseFinances'
import { Loading } from '../components/Bits'
import GrowthChart from '../components/GrowthChart'
import { summarizeBudget, splitAmount } from '../lib/financeSplit'
import { projectRetirement } from '../lib/retirementCalculator'

const money = (value, digits = 0) =>
  value == null ? '—' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })}`

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
  const { positions } = useFirebasePortfolio()
  const finances = useFirebaseFinances()
  const [tab, setTab] = useState('budget')
  const [budgetForm, setBudgetForm] = useState({ name: '', amount: '', type: 'expense' })
  const [poolForm, setPoolForm] = useState({ name: '', percent: '' })
  const [depositAmount, setDepositAmount] = useState('')

  const portfolioValue = useMemo(() => currentPortfolioValue(positions, data), [positions, data])
  const budgetSummary = useMemo(() => summarizeBudget(finances.budgetItems), [finances.budgetItems])
  const totalPoolBalance = finances.pools.reduce((sum, pool) => sum + (pool.balance || 0), 0)
  const projection = useMemo(() => projectRetirement({
    currentSavings: finances.settings.currentSavings,
    monthlyContribution: finances.settings.monthlyContribution,
    annualReturnPct: finances.settings.annualReturnPct,
    inflationPct: finances.settings.inflationPct,
    years: Math.max(1, (finances.settings.retireAge || 0) - (finances.settings.currentAge || 0)),
  }), [finances.settings])
  const depositPreview = splitAmount(parseFloat(depositAmount) || 0, finances.pools)

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
          <div className="kpi-label">Projected at Retirement</div>
          <div className="kpi-value">{money(projection.nominalFinal)}</div>
          <div className="kpi-note">{money(projection.realFinal)} in today's dollars</div>
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
          <form onSubmit={handleAddBudgetItem}
            style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 12, alignItems: 'end', marginBottom: 20 }}>
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
            <form onSubmit={handleAddPool} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr auto', gap: 12, alignItems: 'end' }}>
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
            <form onSubmit={handleDeposit}
              style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'end', marginBottom: 16 }}>
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
                <input type="number" value={finances.settings.retireAge}
                  onChange={(e) => finances.updateSettings({ retireAge: parseInt(e.target.value, 10) || 0 })} />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>Expected annual return %</label>
                <input type="number" step="0.1" value={finances.settings.annualReturnPct}
                  onChange={(e) => finances.updateSettings({ annualReturnPct: parseFloat(e.target.value) || 0 })} />
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
            </div>
            <button className="text-button" style={{ padding: 0, minHeight: 'auto', marginTop: 12 }}
              onClick={() => finances.updateSettings({ currentSavings: Math.round(portfolioValue) })}>
              Sync current savings from portfolio ({money(portfolioValue)})
            </button>
          </div>

          <div className="grid grid-3" style={{ marginBottom: 20 }}>
            <div className="card kpi">
              <div className="kpi-label">At Retirement (Nominal)</div>
              <div className="kpi-value">{money(projection.nominalFinal)}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">At Retirement (Today's $)</div>
              <div className="kpi-value">{money(projection.realFinal)}</div>
            </div>
            <div className="card kpi">
              <div className="kpi-label">Total Growth</div>
              <div className="kpi-value" style={{ color: 'var(--pos)' }}>{money(projection.totalGrowth)}</div>
              <div className="kpi-note">On {money(projection.totalContributed)} contributed</div>
            </div>
          </div>

          <div className="card card-pad">
            <GrowthChart
              title="Projected balance to retirement"
              dates={projection.series.map((point) => `Year ${point.year}`)}
              series={[
                { label: 'Nominal', values: projection.series.map((point) => point.nominal), color: 'var(--accent)', emphasis: true },
                { label: 'Inflation-adjusted', values: projection.series.map((point) => point.real), color: 'var(--text-dim)', dashed: true },
              ]}
              caption="General projection only, not a guarantee — actual markets don't compound smoothly."
            />
          </div>
        </>
      )}
    </>
  )
}
