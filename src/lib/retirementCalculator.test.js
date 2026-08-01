import { describe, expect, it } from 'vitest'
import { projectRetirement } from './retirementCalculator'

describe('projectRetirement', () => {
  it('grows a starting balance with no contributions at the given return', () => {
    const { series, nominalFinal } = projectRetirement({
      currentSavings: 1000,
      monthlyContribution: 0,
      annualReturnPct: 12,
      inflationPct: 0,
      years: 1,
    })
    expect(series[0]).toEqual({ year: 0, nominal: 1000, real: 1000 })
    expect(nominalFinal).toBeCloseTo(1126.83, 1)
  })

  it('adds monthly contributions on top of growth', () => {
    const withContribution = projectRetirement({
      currentSavings: 0,
      monthlyContribution: 100,
      annualReturnPct: 0,
      inflationPct: 0,
      years: 1,
    })
    expect(withContribution.nominalFinal).toBeCloseTo(1200, 5)
    expect(withContribution.totalContributed).toBeCloseTo(1200, 5)
    expect(withContribution.totalGrowth).toBeCloseTo(0, 5)
  })

  it('discounts the final balance for inflation to produce a lower real value', () => {
    const { nominalFinal, realFinal } = projectRetirement({
      currentSavings: 10000,
      monthlyContribution: 0,
      annualReturnPct: 5,
      inflationPct: 3,
      years: 10,
    })
    expect(realFinal).toBeLessThan(nominalFinal)
  })
})
