import modelSettings from '../../pipeline/config/settings.json'

export const FINANCE_SCHEMA_VERSION = modelSettings.model.finance_schema_version

const DEFAULT_SETTINGS = {
  schemaVersion: FINANCE_SCHEMA_VERSION,
  currentAge: 30,
  retireAge: 65,
  inflationPct: 2.5,
  monthlyContribution: 0,
  currentSavings: 0,
  retirementEndAge: modelSettings.projection.default_retirement_end_age,
  monthlyWithdrawal: modelSettings.projection.default_monthly_withdrawal,
  allocationAggressiveness: modelSettings.projection.allocation_default,
  planningAnnualReturnTargetPct: modelSettings.projection.annual_return_target.default_pct,
  coastFireEnabled: modelSettings.projection.coast_fire.default_enabled,
}

/** Additive read migration for the singleton Finances settings document. */
export function migrateFinanceSettings(saved = {}) {
  const current = saved || {}
  if (Number(current.schemaVersion) >= FINANCE_SCHEMA_VERSION) return { ...DEFAULT_SETTINGS, ...current }
  return {
    ...DEFAULT_SETTINGS,
    ...current,
    schemaVersion: FINANCE_SCHEMA_VERSION,
    allocationAggressiveness: current.allocationAggressiveness || modelSettings.projection.allocation_default,
  }
}

/** Additive read migration for a goal document introduced in schema v2. */
export function migrateFinanceGoal(saved = {}) {
  return {
    ...saved,
    schemaVersion: FINANCE_SCHEMA_VERSION,
    targetAmount: Number(saved.targetAmount) || 0,
    targetDate: saved.targetDate || null,
    poolId: saved.poolId || null,
  }
}

export { DEFAULT_SETTINGS }
