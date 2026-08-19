import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { useFirebaseFinances } from '../lib/useFirebaseFinances.js'
import { usePortfolioTracking } from '../lib/usePortfolioTracking.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { annualizeReturnPct, currentHoldingsSeries, selectPeriod, sliceSeriesFrom } from '../lib/portfolioAnalytics.js'
import { LIVE_TRACKING_START } from '../lib/liveTrackingAvailability.js'
import { derivePortfolioRiskProfile } from '../lib/monteCarloRiskProfile.js'
import { usePortfolioMonteCarloCalibration } from '../lib/usePortfolioMonteCarloCalibration.js'
import { formatPreferenceMoney, usePreferences } from '../lib/PreferencesContext.jsx'
import { annualReturnTargetRange, applyAllocationAssumption, formatAnnualReturnTarget, normalizeAnnualReturnTarget, projectionConfig, selectProjectionReturnSource, sequenceRiskPaths } from '../lib/projectionEngine.js'
import { useProjectionSimulation } from '../lib/useProjectionSimulation.js'
import { fidelityProjectionBaseline } from '../lib/referenceCashFlows.js'
import ProjectionPanel from '../components/ProjectionPanel.jsx'
import { Loading } from '../components/Bits.jsx'
import modelSettings from '../../pipeline/config/settings.json'

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
  const { positions: storedPositions, loading: portfolioLoading } = useFirebasePortfolio()
  const { activities } = usePortfolioTracking()
  const previewPortfolio = import.meta.env.DEV
    && new window.URLSearchParams(window.location.search).get('portfolioPreview') === '1'
  const positions = previewPortfolio ? modelSettings.interface.mobile_preview_positions : storedPositions
  const finances = useFirebaseFinances()
  const { preferences } = usePreferences()
  const [draft, setDraft] = useState(null)
  const [committed, setCommitted] = useState(null)
  const [useLiveStrategyReturn, setUseLiveStrategyReturn] = useState(true)
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
  const minimumRetirementAge = Math.max(
    projectionConfig.lever_ranges.retirement_age.minimum,
    finances.settings.currentAge + projectionConfig.minimum_years_until_retirement,
  )
  const maximumRetirementAge = Math.max(
    projectionConfig.lever_ranges.retirement_age.maximum,
    minimumRetirementAge,
  )

  const benchmarkSymbol = preferences.defaultBenchmark
  const portfolioSeries = useMemo(() => {
    const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
    return currentHoldingsSeries(positions, prices, data?.benchmark_history?.dates || [])
  }, [data, positions])
  // The Overview panel's Sharpe/Sortino/Calmar/Annualized-return tiles default to the
  // since-live-tracking window (analyticsScope 'since_algorithm'), not the full holdings
  // history. Calibrating off the unsliced portfolioSeries silently diluted the annualized
  // return toward a much longer, lower-return window and disagreed with what the Overview
  // panel shows for the same ratios - slicing to the same LIVE_TRACKING_START window is what
  // makes "calibrated to your Sharpe/Sortino/Calmar" literally true.
  const sinceAlgorithmSeries = useMemo(() => sliceSeriesFrom(portfolioSeries, LIVE_TRACKING_START), [portfolioSeries])
  const riskProfile = useMemo(() => derivePortfolioRiskProfile(sinceAlgorithmSeries, data), [sinceAlgorithmSeries, data])
  const lastActivityAt = useMemo(() => activities
    .map((row) => row.recordedAt)
    .filter(Boolean)
    .sort()
    .at(-1) || null, [activities])
  const calibration = usePortfolioMonteCarloCalibration(riskProfile, lastActivityAt)
  const source = useMemo(() => selectProjectionReturnSource(
    portfolioSeries,
    benchmarkReport?.histories?.[benchmarkSymbol],
    benchmarkSymbol,
    fidelityProjectionBaseline(positions),
    calibration.riskProfile,
  ), [benchmarkReport, portfolioSeries, positions, benchmarkSymbol, calibration.riskProfile])
  const returnTargetRange = useMemo(() => annualReturnTargetRange(source), [source])

  // Reprice the current basket across its published history. Holding quantities stay fixed,
  // so transfers never enter the annualized planning assumption. Once the risk-profile
  // calibration is available, its annualized return is the exact figure driving Sharpe,
  // Sortino, and Calmar on the Overview panel - using it here instead of a separate
  // whole-history calculation keeps the dotted median target and that panel from disagreeing.
  const currentHoldingsPeriod = selectPeriod(portfolioSeries, 'All')
  const wholeHistoryAnnualReturnPct = currentHoldingsPeriod
    ? annualizeReturnPct(currentHoldingsPeriod.returnPct, currentHoldingsPeriod.startDate, currentHoldingsPeriod.endDate)
    : null
  const liveStrategyAnnualReturnPct = calibration.riskProfile?.available
    ? calibration.riskProfile.annualReturn * 100
    : wholeHistoryAnnualReturnPct
  const liveStrategyReturnWindow = calibration.riskProfile?.available
    ? { startDate: calibration.riskProfile.startDate, endDate: calibration.riskProfile.endDate }
    : currentHoldingsPeriod
  const liveTargetActive = useLiveStrategyReturn && liveStrategyAnnualReturnPct != null
  const effectiveAnnualReturnTargetPct = liveTargetActive
    ? normalizeAnnualReturnTarget(liveStrategyAnnualReturnPct, source)
    : committed?.annualReturnTargetPct

  useEffect(() => {
    if (finances.loading) return
    const next = {
      annualReturnTargetPct: normalizeAnnualReturnTarget(finances.settings.planningAnnualReturnTargetPct, source),
      monthlyContribution: finances.settings.monthlyContribution,
      retirementAge: Math.min(maximumRetirementAge, Math.max(minimumRetirementAge, finances.settings.retireAge)),
      annualWithdrawal: finances.settings.monthlyWithdrawal * projectionConfig.months_per_year,
      allocation: finances.settings.allocationAggressiveness || projectionConfig.allocation_default,
    }
    setDraft(next)
    setCommitted(next)
  }, [finances.loading, maximumRetirementAge, minimumRetirementAge, returnTargetRange.minimumPct, returnTargetRange.maximumPct])

  const adjustedReturns = useMemo(() => source.available && committed
    ? applyAllocationAssumption(source.returns, committed.allocation, effectiveAnnualReturnTargetPct / 100)
    : [], [committed, effectiveAnnualReturnTargetPct, source])
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
          : key === 'annualReturnTargetPct' ? { planningAnnualReturnTargetPct: draft[key] }
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

  if (loading || benchmarkLoading || (!previewPortfolio && portfolioLoading) || finances.loading || !draft || !committed) return <Loading />
  const success = probability == null ? null : probability * 100
  const verdict = successBand(probability || 0)
  const alternativeSuccess = contributionAlternative.result?.successProbability
  const addGoal = (event) => {
    event.preventDefault()
    finances.addGoal(goalForm)
    setGoalForm({ ...goalForm, name: '' })
  }

  return <div className="planning-page">
    <header className="page-head"><div><span className="eyebrow">Planning</span><h1 className="page-title">Can your plan last?</h1><p className="page-sub">Set the annual return you want the dotted median to target. Historical paths estimate the range around it from now through the end of your plan.</p></div><Link className="secondary-button compact" to="/finances">Accounts and pools</Link></header>

    <section className="planning-verdict">
      <div className="success-gauge" style={{ '--success': `${success || 0}%` }} aria-label={success == null ? 'Success probability unavailable' : `Success probability ${success.toFixed(0)} percent`}><div><strong>{projection.loading && success == null ? '…' : success == null ? 'N/A' : `${success.toFixed(0)}%`}</strong><span>probability of success</span></div></div>
      <div><span className={`planning-band band-${verdict.label.toLowerCase().replaceAll(' ', '-')}`}>{verdict.label}</span><h2>{verdict.label === 'On track' ? 'Your current plan clears the survival threshold.' : verdict.label === 'Needs attention' ? 'Your plan works in some paths, but the margin is thin.' : 'Your current assumptions exhaust savings in too many paths.'}</h2>{alternativeSuccess == null || success == null ? <p>Testing the most effective contribution lever.</p> : <p>Raising monthly contributions by {money(projectionConfig.contribution_lever_step)} moves this from {success.toFixed(0)}% to {(alternativeSuccess * 100).toFixed(0)}%.</p>}<small>{projection.result?.pathCount?.toLocaleString() || projectionConfig.paths.toLocaleString()} historical paths through age {finances.settings.retirementEndAge}</small></div>
    </section>

    <section className="planning-baseline" aria-labelledby="planning-baseline-title">
      <div><span className="eyebrow">Dotted median target</span><h2 id="planning-baseline-title">{formatAnnualReturnTarget(effectiveAnnualReturnTargetPct)} annual</h2></div>
      <p>{liveTargetActive
        ? `Your current-holdings return, annualized from ${liveStrategyReturnWindow.startDate} to ${liveStrategyReturnWindow.endDate}${calibration.riskProfile?.available ? ' -- the same window and calculation behind your Sharpe, Sortino, and Calmar ratios' : ''}. Cash transfers are not part of this series. This is a planning assumption, not a forecast.`
        : returnTargetRange.evidence ? `Your ${returnTargetRange.evidence.lowerPct.toFixed(2)}% year-to-date return and ${returnTargetRange.evidence.upperPct.toFixed(2)}% trailing one-year return set the evidence range. Move the slider to choose the annual target. This is a planning assumption, not a forecast.` : `Move the slider to choose the annual target. Historical monthly volatility and return ordering determine the shaded estimates around it. This is a planning assumption, not a forecast.`}</p>
      <label className="planning-inline-note">
        <input type="checkbox" checked={useLiveStrategyReturn} disabled={liveStrategyAnnualReturnPct == null} onChange={(e) => setUseLiveStrategyReturn(e.target.checked)} />
        Track my current-holdings return{liveStrategyAnnualReturnPct == null ? ' -- unavailable until there are at least two dated market values' : ''}
      </label>
    </section>

    <section className="planning-calibration" aria-labelledby="planning-calibration-title">
      <div><span className="eyebrow">Monte Carlo calibration</span><h2 id="planning-calibration-title">{calibration.riskProfile?.available ? 'Calibrated to your risk-adjusted return ratios' : 'Waiting on enough daily history'}</h2></div>
      {calibration.riskProfile?.available ? <>
        <div className="planning-calibration-ratios">
          <span>Sharpe <strong>{calibration.riskProfile.sharpe?.toFixed(2)}</strong></span>
          <span>Sortino <strong>{calibration.riskProfile.sortino?.toFixed(2)}</strong></span>
          <span>Lo-adjusted Sortino <strong>{calibration.riskProfile.loAdjusted ? calibration.riskProfile.loAdjustedSortino?.toFixed(2) : 'Insufficient'}</strong></span>
          <span>Calmar <strong>{calibration.riskProfile.calmar?.toFixed(2)}</strong></span>
        </div>
        <p>The simulated distribution's mean and volatility are solved algebraically from these ratios, not resampled from your literal daily path. {calibration.calibratedAt ? `Last calibrated ${calibration.calibratedAt.slice(0, 10)} from ${calibration.riskProfile.observations} daily returns through ${calibration.riskProfile.endDate}.` : 'Calibrating now.'} {calibration.stale ? 'A new calibration is due' + (calibration.staleReason ? ` (${calibration.staleReason})` : '') + ' and will run automatically the next time you open this page.' : `Holds steady until your next ${calibration.refreshLabel} or a new deposit, so day-to-day price moves don't reshuffle the plan.`}</p>
        <button type="button" className="secondary-button compact" onClick={calibration.recalibrate} disabled={calibration.loading}>Recalibrate now</button>
      </> : <p>{riskProfile.reason || 'At least 20 daily portfolio observations are required before the simulation can calibrate to your own Sharpe, Sortino, and Calmar ratios. Until then, the model falls back to benchmark-derived history.'}</p>}
    </section>

    <section className="planning-levers"><header><span className="eyebrow">Live levers</span><h2>Change the plan, then release to resimulate</h2></header>
      <label><span>Annual return target <strong>{formatAnnualReturnTarget(liveTargetActive ? effectiveAnnualReturnTargetPct : draft.annualReturnTargetPct)}</strong></span><input type="range" disabled={liveTargetActive} min={returnTargetRange.minimumPct} max={returnTargetRange.maximumPct} step={returnTargetRange.stepPct} value={liveTargetActive ? effectiveAnnualReturnTargetPct : draft.annualReturnTargetPct} onChange={(event) => setDraft({ ...draft, annualReturnTargetPct: Number(event.target.value) })} onPointerUp={() => commitLever('annualReturnTargetPct')} onKeyUp={() => commitLever('annualReturnTargetPct')} /><small>{liveTargetActive ? 'Following your current-holdings return -- turn off tracking above to set a custom target. ' : `Dotted median target. ${returnTargetRange.evidence ? `${returnTargetRange.evidence.lowerPct.toFixed(2)}% year to date to ${returnTargetRange.evidence.upperPct.toFixed(2)}% trailing one year. ` : ''}${delta('annualReturnTargetPct')}`}</small></label>
      <label><span>Monthly contribution <strong>{money(draft.monthlyContribution)}</strong></span><input type="range" min={projectionConfig.lever_ranges.monthly_contribution.minimum} max={projectionConfig.lever_ranges.monthly_contribution.maximum} step={projectionConfig.lever_ranges.monthly_contribution.step} value={draft.monthlyContribution} onChange={(event) => setDraft({ ...draft, monthlyContribution: Number(event.target.value) })} onPointerUp={() => commitLever('monthlyContribution')} onKeyUp={() => commitLever('monthlyContribution')} /><small>{delta('monthlyContribution')}</small></label>
      <label><span>Target retirement age <strong>{draft.retirementAge}</strong></span><input type="range" min={minimumRetirementAge} max={maximumRetirementAge} step={projectionConfig.lever_ranges.retirement_age.step} value={draft.retirementAge} onChange={(event) => setDraft({ ...draft, retirementAge: Number(event.target.value) })} onPointerUp={() => commitLever('retirementAge')} onKeyUp={() => commitLever('retirementAge')} /><small>Available from age {minimumRetirementAge}. {delta('retirementAge')}</small></label>
      <label><span>Annual retirement withdrawal <strong>{money(draft.annualWithdrawal)}</strong></span><input type="range" min={projectionConfig.lever_ranges.annual_withdrawal.minimum} max={projectionConfig.lever_ranges.annual_withdrawal.maximum} step={projectionConfig.lever_ranges.annual_withdrawal.step} value={draft.annualWithdrawal} onChange={(event) => setDraft({ ...draft, annualWithdrawal: Number(event.target.value) })} onPointerUp={() => commitLever('annualWithdrawal')} onKeyUp={() => commitLever('annualWithdrawal')} /><small>In today's dollars. {delta('annualWithdrawal')}</small></label>
      <label><span>Allocation aggressiveness <strong>{projectionConfig.allocation_assumptions[draft.allocation].label}</strong></span><select value={draft.allocation} onChange={(event) => { const allocation = event.target.value; setDraft({ ...draft, allocation }); setCommitted({ ...committed, allocation }); priorProbability.current = probability; setChangedLever('allocation'); finances.updateSettings({ allocationAggressiveness: allocation }) }}>{Object.entries(projectionConfig.allocation_assumptions).map(([key, assumption]) => <option value={key} key={key}>{assumption.label}: {assumption.annual_volatility_pct}% volatility around your target</option>)}</select><small>{delta('allocation')}</small></label>
      {projection.result?.runtimeMs != null && <p className="planning-runtime">Updated in {projection.result.runtimeMs.toFixed(0)} ms</p>}
    </section>

    <ProjectionPanel state={projection} source={source} money={money} annualReturnTargetPct={effectiveAnnualReturnTargetPct} startAge={finances.settings.currentAge} retirementAge={committed.retirementAge} endAge={finances.settings.retirementEndAge} title="Long-range outcome distribution" showSuccess={false} assumptionNote={`The chart runs from now through age ${finances.settings.retirementEndAge}. The dotted median targets ${formatAnnualReturnTarget(effectiveAnnualReturnTargetPct)} annually${liveTargetActive ? ', your current-holdings return with transfers excluded' : ''} and the shaded bands are estimates around it.`} />
    <SequenceRiskPanel money={money} />

    <section className="planning-goals"><header><div><span className="eyebrow">Goals</span><h2>Retirement is one goal among several</h2></div></header><form onSubmit={addGoal}><label><span>Goal name</span><input required placeholder="Home down payment" value={goalForm.name} onChange={(event) => setGoalForm({ ...goalForm, name: event.target.value })} /></label><label><span>Target amount</span><input required type="number" min="1" value={goalForm.targetAmount} onChange={(event) => setGoalForm({ ...goalForm, targetAmount: event.target.value })} /></label><label><span>Target date</span><input required type="date" value={goalForm.targetDate} onChange={(event) => setGoalForm({ ...goalForm, targetDate: event.target.value })} /></label><label><span>Funding pool</span><select value={goalForm.poolId} onChange={(event) => setGoalForm({ ...goalForm, poolId: event.target.value })}><option value="">No linked pool</option>{finances.pools.map((pool) => <option value={pool.id} key={pool.id}>{pool.name}</option>)}</select></label><button className="primary-button">Add goal</button></form>
      {finances.goals.length ? <div className="goal-list">{finances.goals.map((goal) => <button className={selectedGoal?.id === goal.id ? 'selected' : ''} key={goal.id} onClick={() => setSelectedGoalId(goal.id)}><span>{goal.name}<small>{goal.targetDate}</small></span><strong>{money(goal.targetAmount)}</strong></button>)}</div> : <p>Add a named goal and connect it to one of your Finances pools.</p>}
      {selectedGoal && <div className="goal-probability"><span>Probability of reaching {selectedGoal.name}</span><strong>{goalProjection.loading || goalProjection.result?.goalProbability == null ? 'Calculating' : `${(goalProjection.result.goalProbability * 100).toFixed(0)}%`}</strong><small>Uses {finances.pools.find((pool) => pool.id === selectedGoal.poolId)?.name || 'an unlinked starting balance'} through {selectedGoal.targetDate}</small></div>}
    </section>
  </div>
}
