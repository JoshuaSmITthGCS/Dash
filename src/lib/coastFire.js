import modelSettings from '../../pipeline/config/settings.json'

const config = modelSettings.projection.coast_fire

const finite = (value) => Number.isFinite(Number(value))

/** Retirement balance implied by an annual withdrawal at the configured safe withdrawal rate. */
export function coastFireTargetAmount(annualWithdrawal) {
  const withdrawalRate = config.withdrawal_rate_pct / 100
  const withdrawal = Math.max(0, Number(annualWithdrawal) || 0)
  return withdrawalRate > 0 ? withdrawal / withdrawalRate : 0
}

/**
 * Coast FIRE: today's balance, left untouched by further contributions, compounds at the
 * plan's annual return target until it alone reaches the retirement target. `requiredTodayAmount`
 * runs that same growth assumption backward from the target, giving the balance needed right
 * now to coast -- independent of the Monte Carlo simulation, so it stays a cheap, synchronous
 * read rather than another simulated distribution.
 */
export function coastFireStatus({ currentSavings, currentAge, retirementAge, annualReturnPct, annualWithdrawal }) {
  const yearsToRetirement = Math.max(0, Number(retirementAge) - Number(currentAge))
  const annualReturn = Number(annualReturnPct) / 100
  const targetAmount = coastFireTargetAmount(annualWithdrawal)
  if (!finite(annualReturn) || annualReturn <= -1 || !finite(targetAmount) || targetAmount <= 0) {
    return { available: false, targetAmount, yearsToRetirement }
  }
  const growth = (1 + annualReturn) ** yearsToRetirement
  const requiredTodayAmount = growth > 0 ? targetAmount / growth : targetAmount
  const projectedBalance = Math.max(0, Number(currentSavings) || 0) * growth
  return {
    available: true,
    targetAmount,
    requiredTodayAmount,
    projectedBalance,
    yearsToRetirement,
    isCoasting: projectedBalance >= targetAmount,
    surplus: projectedBalance - targetAmount,
  }
}
