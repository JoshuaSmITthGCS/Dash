import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { useFirebaseFinances } from '../lib/useFirebaseFinances.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { currentHoldingsSeries } from '../lib/portfolioAnalytics.js'
import { formatPreferenceMoney, usePreferences } from '../lib/PreferencesContext.jsx'
import { applyAllocationAssumption, projectionConfig, selectProjectionReturnSource, sequenceRiskPaths } from '../lib/projectionEngine.js'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'
import ProjectionPanel from '../components/ProjectionPanel.jsx'
import { Loading } from '../components/Bits.jsx'

function defaultGoalDate() {
  const date = new Date()
  date.setUTCFullYear(date.getUTCFullYear() + projectionConfig.goal_default_years)
  return date.toISOString().slice(0, 10)
}

function successBand(probability) {
  return projectionConfig.success_bands.find((band) => probability >= band.minimum)
    || projectionConfig.success_bands.at(-1)
}

function SequenceRiskPanel({ money }) {
  const paths = sequenceRiskPaths()
  const width = projectionConfig.sequence_chart_width
  const height = projectionConfig.sequence_chart_height
  const maximum = Math.max(...paths.favorable, ...paths.unfavorable)
  const points = (values) => values.map((value, index) => (
    `${index / (values.length - 1) * width},${height - value / maximum * height}`
  )).join(' ')
  return <section className="sequence-risk-panel">
    <header><div><span className="eyebrow">Sequence risk</span><h2>Same average, different ending</h2></div></header>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Two return sequences with identical average returns and different ending balances">
      <polyline className="favorable" points={points(paths.favorable)} />
      <polyline className="unfavorable" points={points(paths.unfavorable)} />
    </svg>
    <div><span>Gains first <strong>{money(paths.favorable.at(-1))}</strong></span><span>Losses first <strong>{money(paths.unfavorable.at(-1))}</strong></span></div>
    <p>Both paths use the same returns and the same average. Withdrawals after early losses leave less capital available for the later recovery.</p>
  </section>
}

export default function Planning() {
  const { data, loading } = useData('report.json')
  const { data: benchmarkReport, loading: benchmarkLoading } = useData('benchmark-report.json')
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const finances = useFirebaseFinances()
  const { preferences } = usePreferences()
  const [draft, setDraft] = useState(null)
  const [committed, setCommitted] = useState(null)
  const [changedLever, setChangedLever] = useState(null)
  const [leverDeltas, setLeverDeltas] = useState({})
  const priorProbability = useRef(null)
  const [goalForm, setGoalForm] = useState({
    name: '',
    targetAmount: projectionConfig.goal_default_amount,
    targetDate: defaultGoalDate(),
    poolId: '',
  })
  const [selectedGoalId, setSelectedGoalId] = useState(null)

  useEffect(() => {
    if (finances.loading) return
    const next = {
      monthlyContribution: finances.settings.monthlyContribution,
      retirementAge: finances.settings.retireAge,
      annualWithdrawal: finances.settings.monthlyWithdrawal * projectionConfig.months_per_year,
      allocation: finances.settings.allocationAggressiveness || projectionConfig.allocation_default,
    }
    setDraft(next)
    setCommitted(next)
  }, [finances.loading])

  const source = useMemo(() => {
    const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
    const series = currentHoldingsSeries(positions, prices, data?.benchmark_history?.dates || [])
    const symbol = preferences.defaultBenchmark
    return selectProjectionReturnSource(series, benchmarkReport?.histories?.[symbol], symbol)
  }, [benchmarkReport, data, positions, preferences.defaultBenchmark])

  const adjustedReturns = useMemo(() => source.available && committed
    ? applyAllocationAssumption(source.returns, committed.allocation)
    : [], [committed, source])
  const input = useMemo(() => source.available && committed ? {
    monthlyReturns: adjustedReturns,
    currentBalance: finances.settings.currentSavings,
    monthlyContribution: committed.monthlyContribution,
    monthlyWithdrawal: committed.annualWithdrawal / projectionConfig.months_per_year,
    inflationPct: finances.settings.inflationPct,
    accumulationMonths: Math.max(1, (committed.retirementAge - finances.settings.currentAge) * projectionConfig.months_per_year),
    withdrawalMonths: Math.max(0, (finances.settings.retirementEndAge - committed.retirementAge) * projectionConfig.months_per_year),
  } : null, [adjustedReturns, committed, finances.settings, source.available])
  const projection = useProjectionSimulation(input)
  const contributionAlternative = useProjectionSimulation(input ? {
    ...input,
    monthlyContribution: input.monthlyContribution + projectionConfig.contribution_lever_step,
  } : null)
  const probability = projection.result?.successProbability

  useEffect(() => {
    if (probability == null) return
    if (changedLever && priorProbability.current != null) {
      setLeverDeltas((current) => ({ ...current, [changedLever]: probability - priorProbability.current }))
      setChangedLever(null)
    }
    priorProbability.current = probability
  }, [changedLever, probability])

  const commitLever = (key) => {
    if (!draft || !committed || draft[key] === committed[key]) return
    priorProbability.current = probability
    setChangedLever(key)
    setCommitted({ ...committed, [key]: draft[key] })
    const settingsUpdate = key === 'monthlyContribution' ? { monthlyContribution: draft[key] }
      : key === 'retirementAge' ? { retireAge: draft[key] }
        : key === 'annualWithdrawal' ? { monthlyWithdrawal: draft[key] / projectionConfig.months_per_year }
          : { allocationAggressiveness: draft[key] }
    finances.updateSettings(settingsUpdate)
  }
  const delta = (key) => leverDeltas[key] == null ? 'Move this lever to compare outcomes' : `${leverDeltas[key] >= 0 ? '+' : '−'}${Math.abs(leverDeltas[key] * 100).toFixed(0)} percentage points from its prior setting`
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)

  const selectedGoal = finances.goals.find((goal) => goal.id === selectedGoalId) || finances.goals[0]
  const selectedPool = finances.pools.find((pool) => pool.id === selectedGoal?.poolId)
  const goalMonths = selectedGoal?.targetDate
    ? Math.max(1, Math.round((Date.parse(selectedGoal.targetDate) - Date.now()) / (projectionConfig.milliseconds_per_day * projectionConfig.days_per_year / projectionConfig.months_per_year)))
    : null
  const goalInput = selectedGoal && goalMonths && source.available ? {
    monthlyReturns: adjustedReturns,
    currentBalance: selectedPool?.balance || 0,
    monthlyContribution: committed?.monthlyContribution * ((selectedPool?.percent || 0) / 100),
    accumulationMonths: goalMonths,
    withdrawalMonths: 0,
    inflationPct: finances.settings.inflationPct,
    targetAmount: selectedGoal.targetAmount,
  } : null
  const goalProjection = useProjectionSimulation(goalInput)

  if (loading || benchmarkLoading || portfolioLoading || finances.loading || !draft || !committed) return <Loading />
  const success = probability == null ? null : probability * 100
  const verdict = successBand(probability || 0)
  const alternativeSuccess = contributionAlternative.result?.successProbability

  const addGoal = (event) => {
    event.preventDefault()
    finances.addGoal(goalForm)
    setGoalForm({ ...goalForm, name: '' })
  }

  return <div className="planning-page">
    <header className="page-head"><div><span className="eyebrow">Planning</span><h1 className="page-title">Can your plan last?</h1><p className="page-sub">Historical paths turn your savings, timing, and spending assumptions into one direct answer.</p></div><Link className="secondary-button compact" to="/finances">Accounts and pools</Link></header>

    <section className="planning-verdict">
      <div className="success-gauge" style={{ '--success': `${success || 0}%` }} aria-label={success == null ? 'Success probability unavailable' : `Success probability ${success.toFixed(0)} percent`}><div><strong>{projection.loading && success == null ? '…' : success == null ? 'N/A' : `${success.toFixed(0)}%`}</strong><span>probability of success</span></div></div>
      <div><span className={`planning-band band-${verdict.label.toLowerCase().replaceAll(' ', '-')}`}>{verdict.label}</span><h2>{verdict.label === 'On track' ? 'Your current plan clears the survival threshold.' : verdict.label === 'Needs attention' ? 'Your plan works in some paths, but the margin is thin.' : 'Your current assumptions exhaust savings in too many paths.'}</h2>{alternativeSuccess == null || success == null ? <p>Testing the most effective contribution lever.</p> : <p>Raising monthly contributions by {money(projectionConfig.contribution_lever_step)} moves this from {success.toFixed(0)}% to {(alternativeSuccess * 100).toFixed(0)}%.</p>}<small>{projection.result?.pathCount?.toLocaleString() || projectionConfig.paths.toLocaleString()} historical paths through age {finances.settings.retirementEndAge}</small></div>
    </section>

    <section className="planning-levers"><header><span className="eyebrow">Live levers</span><h2>Change the plan, then release to resimulate</h2></header>
      <label><span>Monthly contribution <strong>{money(draft.monthlyContribution)}</strong></span><input type="range" min={projectionConfig.lever_ranges.monthly_contribution.minimum} max={projectionConfig.lever_ranges.monthly_contribution.maximum} step={projectionConfig.lever_ranges.monthly_contribution.step} value={draft.monthlyContribution} onChange={(event) => setDraft({ ...draft, monthlyContribution: Number(event.target.value) })} onPointerUp={() => commitLever('monthlyContribution')} onKeyUp={() => commitLever('monthlyContribution')} /><small>{delta('monthlyContribution')}</small></label>
      <label><span>Target retirement age <strong>{draft.retirementAge}</strong></span><input type="range" min={projectionConfig.lever_ranges.retirement_age.minimum} max={projectionConfig.lever_ranges.retirement_age.maximum} step={projectionConfig.lever_ranges.retirement_age.step} value={draft.retirementAge} onChange={(event) => setDraft({ ...draft, retirementAge: Number(event.target.value) })} onPointerUp={() => commitLever('retirementAge')} onKeyUp={() => commitLever('retirementAge')} /><small>{delta('retirementAge')}</small></label>
      <label><span>Annual retirement withdrawal <strong>{money(draft.annualWithdrawal)}</strong></span><input type="range" min={projectionConfig.lever_ranges.annual_withdrawal.minimum} max={projectionConfig.lever_ranges.annual_withdrawal.maximum} step={projectionConfig.lever_ranges.annual_withdrawal.step} value={draft.annualWithdrawal} onChange={(event) => setDraft({ ...draft, annualWithdrawal: Number(event.target.value) })} onPointerUp={() => commitLever('annualWithdrawal')} onKeyUp={() => commitLever('annualWithdrawal')} /><small>In today's dollars. {delta('annualWithdrawal')}</small></label>
      <label><span>Allocation aggressiveness <strong>{projectionConfig.allocation_assumptions[draft.allocation].label}</strong></span><select value={draft.allocation} onChange={(event) => { const allocation = event.target.value; setDraft({ ...draft, allocation }); setCommitted({ ...committed, allocation }); priorProbability.current = probability; setChangedLever('allocation'); finances.updateSettings({ allocationAggressiveness: allocation }) }}>{Object.entries(projectionConfig.allocation_assumptions).map(([key, assumption]) => <option value={key} key={key}>{assumption.label}: {assumption.annual_return_pct}% return, {assumption.annual_volatility_pct}% volatility</option>)}</select><small>{delta('allocation')}</small></label>
      {projection.result?.runtimeMs != null && <p className="planning-runtime">Updated in {projection.result.runtimeMs.toFixed(0)} ms</p>}
    </section>

    <ProjectionPanel state={projection} source={source} money={money} startAge={finances.settings.currentAge} retirementAge={committed.retirementAge} endAge={finances.settings.retirementEndAge} title="Long-range outcome distribution" showSuccess={false} assumptionNote="The dotted median and shaded bands are simulated, not observed." />
    <SequenceRiskPanel money={money} />

    <section className="planning-goals"><header><div><span className="eyebrow">Goals</span><h2>Retirement is one goal among several</h2></div></header><form onSubmit={addGoal}><label><span>Goal name</span><input required placeholder="Home down payment" value={goalForm.name} onChange={(event) => setGoalForm({ ...goalForm, name: event.target.value })} /></label><label><span>Target amount</span><input required type="number" min="1" value={goalForm.targetAmount} onChange={(event) => setGoalForm({ ...goalForm, targetAmount: event.target.value })} /></label><label><span>Target date</span><input required type="date" value={goalForm.targetDate} onChange={(event) => setGoalForm({ ...goalForm, targetDate: event.target.value })} /></label><label><span>Funding pool</span><select value={goalForm.poolId} onChange={(event) => setGoalForm({ ...goalForm, poolId: event.target.value })}><option value="">No linked pool</option>{finances.pools.map((pool) => <option value={pool.id} key={pool.id}>{pool.name}</option>)}</select></label><button className="primary-button">Add goal</button></form>
      {finances.goals.length ? <div className="goal-list">{finances.goals.map((goal) => <button className={selectedGoal?.id === goal.id ? 'selected' : ''} key={goal.id} onClick={() => setSelectedGoalId(goal.id)}><span>{goal.name}<small>{goal.targetDate}</small></span><strong>{money(goal.targetAmount)}</strong></button>)}</div> : <p>Add a named goal and connect it to one of your Finances pools.</p>}
      {selectedGoal && <div className="goal-probability"><span>Probability of reaching {selectedGoal.name}</span><strong>{goalProjection.loading || goalProjection.result?.goalProbability == null ? 'Calculating' : `${(goalProjection.result.goalProbability * 100).toFixed(0)}%`}</strong><small>Uses {finances.pools.find((pool) => pool.id === selectedGoal.poolId)?.name || 'an unlinked starting balance'} through {selectedGoal.targetDate}</small></div>}
    </section>
  </div>
}
