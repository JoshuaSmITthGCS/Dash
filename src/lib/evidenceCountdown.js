// One dated list of when each "not yet" on the evidence views turns into a reading. Every date
// is an estimate from counts the reports already publish; the counts stay the source of truth,
// so a refresh that falls behind moves the date rather than silently breaking a promise.

import { addEstimatedMarketDays } from './liveTrackingAvailability.js'

const finite = (value) => value != null && Number.isFinite(Number(value))

function addMonths(iso, months) {
  const date = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return null
  date.setUTCMonth(date.getUTCMonth() + Math.max(0, Math.round(months)))
  return date.toISOString().slice(0, 10)
}

function milestone({ id, label, unlocks, observations, required, unit, estimatedDate, today }) {
  const met = finite(observations) && finite(required) && Number(observations) >= Number(required)
  return {
    id,
    label,
    unlocks,
    observations: finite(observations) ? Number(observations) : null,
    required: finite(required) ? Number(required) : null,
    unit,
    met,
    estimatedDate: met ? null : estimatedDate,
    overdue: !met && estimatedDate != null && estimatedDate < today,
  }
}

function sessionsMilestone(base, today) {
  const remaining = Math.max(0, Number(base.required) - Number(base.observations))
  return milestone({ ...base, unit: 'sessions', estimatedDate: addEstimatedMarketDays(today, remaining), today })
}

/**
 * @param {object} inputs
 * @param {object} inputs.timeToValidMetric  portfolioStatistics.timeToValidMetric output
 * @param {object} inputs.signalMetrics      signal_metrics.json
 * @param {object} inputs.factor             factorAnalytics output for the account
 * @param {object} inputs.prospective        pipeline/validation/harness_freeze.json
 * @param {string} inputs.today              YYYY-MM-DD
 */
export function evidenceMilestones({ timeToValidMetric, signalMetrics, factor, prospective, today = new Date().toISOString().slice(0, 10) } = {}) {
  const rows = []
  const metrics = signalMetrics?.metrics || []

  if (timeToValidMetric?.available) {
    rows.push(milestone({
      id: 'headline_ratios',
      label: 'Your Sharpe, Sortino and annualized return',
      unlocks: 'Headline ratios on this page clear the reliability floor',
      observations: timeToValidMetric.observations,
      required: timeToValidMetric.floor,
      unit: 'sessions',
      estimatedDate: timeToValidMetric.estimatedDate || null,
      today,
    }))
  }

  const distribution = metrics.filter((row) => row.group === 'distribution'
    && finite(row.observations) && finite(row.required_observations))
  if (distribution.length) {
    rows.push(sessionsMilestone({
      id: 'distribution_shape',
      label: 'Tail and drawdown shape',
      unlocks: distribution.map((row) => row.label).join(', '),
      observations: distribution[0].observations,
      required: distribution[0].required_observations,
    }, today))
  }

  const psi = metrics.find((row) => row.id === 'feature_psi')
  if (psi && finite(psi.observations) && finite(psi.required_observations)) {
    rows.push(sessionsMilestone({
      id: 'feature_psi',
      label: 'Feature drift alarm (PSI)',
      unlocks: 'Detects when the live feature population drifts from its earlier window',
      observations: psi.observations,
      required: psi.required_observations,
    }, today))
  }

  const start = prospective?.harness_start_date
  if (start) {
    const liveIc = metrics.find((row) => row.id === 'live_vs_backtest_ic')
    const periods = finite(liveIc?.observations) ? Number(liveIc.observations) : 0
    const required = finite(liveIc?.required_observations) ? Number(liveIc.required_observations) : 24
    rows.push(milestone({
      id: 'prospective_first_ic',
      label: 'First out-of-sample IC reading',
      unlocks: 'The first month the model is graded on returns it had not seen when it scored',
      observations: Math.min(periods, 1),
      required: 1,
      unit: 'months',
      estimatedDate: addMonths(start, 1),
      today,
    }))
    rows.push(milestone({
      id: 'prospective_icir',
      label: 'Prospective ICIR and champion-vs-challenger verdict',
      unlocks: 'Enough monthly periods to judge the edge and promote or abandon a challenger',
      observations: periods,
      required,
      unit: 'months',
      estimatedDate: prospective.expected_completion_at_monthly_frequency || addMonths(start, required),
      today,
    }))
  }

  if (factor && finite(factor.requiredObservations)) {
    const observations = finite(factor.observations) ? Number(factor.observations) : 0
    rows.push(milestone({
      id: 'account_factor_loadings',
      label: 'Your account’s factor loadings',
      unlocks: 'Six-factor regression on your own returns, not the backtest',
      observations,
      required: factor.requiredObservations,
      unit: 'months',
      estimatedDate: addMonths(today, Number(factor.requiredObservations) - observations),
      today,
    }))
  }

  const pending = rows.filter((row) => !row.met)
    .sort((a, b) => String(a.estimatedDate || '9999').localeCompare(String(b.estimatedDate || '9999')))
  return { today, pending, met: rows.filter((row) => row.met) }
}
