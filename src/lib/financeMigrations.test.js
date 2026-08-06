import { describe, expect, it } from 'vitest'
import { FINANCE_SCHEMA_VERSION, migrateFinanceGoal, migrateFinanceSettings } from './financeMigrations.js'

describe('Finances schema migrations', () => {
  it('adds Planning fields without changing saved assumptions', () => {
    const migrated = migrateFinanceSettings({ currentAge: 44, monthlyContribution: 725 })
    expect(migrated).toMatchObject({
      schemaVersion: FINANCE_SCHEMA_VERSION,
      currentAge: 44,
      monthlyContribution: 725,
      allocationAggressiveness: 'growth',
      planningAnnualReturnTargetPct: 15,
    })
  })

  it('preserves a saved return target while adding schema v3 fields', () => {
    expect(migrateFinanceSettings({ schemaVersion: 2, planningAnnualReturnTargetPct: 18.5 })).toMatchObject({
      schemaVersion: FINANCE_SCHEMA_VERSION,
      planningAnnualReturnTargetPct: 18.5,
    })
  })

  it('normalizes an additive goal document', () => {
    expect(migrateFinanceGoal({ id: 'goal-1', name: 'Home', targetAmount: '80000' })).toEqual({
      schemaVersion: FINANCE_SCHEMA_VERSION,
      id: 'goal-1',
      name: 'Home',
      targetAmount: 80000,
      targetDate: null,
      poolId: null,
    })
  })
})
