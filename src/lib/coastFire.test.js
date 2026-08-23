import { describe, expect, it } from 'vitest'
import { coastFireStatus, coastFireTargetAmount } from './coastFire.js'

describe('coastFireTargetAmount', () => {
  it('inverts the annual withdrawal at the configured safe withdrawal rate', () => {
    expect(coastFireTargetAmount(40000)).toBeCloseTo(1000000, 6)
  })

  it('floors negative or missing withdrawal at zero', () => {
    expect(coastFireTargetAmount(-100)).toBe(0)
    expect(coastFireTargetAmount(undefined)).toBe(0)
  })
})

describe('coastFireStatus', () => {
  it('reports coasting once current savings alone compound past the target by retirement age', () => {
    const status = coastFireStatus({
      currentSavings: 1000000,
      currentAge: 45,
      retirementAge: 65,
      annualReturnPct: 7,
      annualWithdrawal: 40000,
    })
    expect(status.available).toBe(true)
    expect(status.targetAmount).toBeCloseTo(1000000, 6)
    expect(status.yearsToRetirement).toBe(20)
    expect(status.projectedBalance).toBeCloseTo(1000000 * 1.07 ** 20, 4)
    expect(status.isCoasting).toBe(true)
    expect(status.requiredTodayAmount).toBeCloseTo(1000000 / 1.07 ** 20, 4)
  })

  it('reports not coasting when projected growth falls short of the target', () => {
    const status = coastFireStatus({
      currentSavings: 50000,
      currentAge: 30,
      retirementAge: 65,
      annualReturnPct: 6,
      annualWithdrawal: 40000,
    })
    expect(status.isCoasting).toBe(false)
    expect(status.surplus).toBeLessThan(0)
    expect(status.requiredTodayAmount).toBeGreaterThan(50000)
  })

  it('is unavailable without a usable return or withdrawal target', () => {
    expect(coastFireStatus({ currentSavings: 1000, currentAge: 30, retirementAge: 65, annualReturnPct: -150, annualWithdrawal: 40000 }).available).toBe(false)
    expect(coastFireStatus({ currentSavings: 1000, currentAge: 30, retirementAge: 65, annualReturnPct: NaN, annualWithdrawal: 40000 }).available).toBe(false)
    expect(coastFireStatus({ currentSavings: 1000, currentAge: 30, retirementAge: 65, annualReturnPct: 7, annualWithdrawal: 0 }).available).toBe(false)
  })

  it('treats retirement at or before the current age as already arrived, with no further growth', () => {
    const status = coastFireStatus({
      currentSavings: 1000000,
      currentAge: 65,
      retirementAge: 60,
      annualReturnPct: 7,
      annualWithdrawal: 40000,
    })
    expect(status.yearsToRetirement).toBe(0)
    expect(status.projectedBalance).toBeCloseTo(1000000, 6)
    expect(status.requiredTodayAmount).toBeCloseTo(1000000, 6)
  })
})
