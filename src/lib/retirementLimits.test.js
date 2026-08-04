import { describe, expect, it } from 'vitest'
import { getAnnualLimit, accountTypeLabel } from './retirementLimits'

describe('getAnnualLimit', () => {
  it('applies the base 401(k) limit under 50', () => {
    expect(getAnnualLimit('401k', 35)).toBe(24500)
  })

  it('applies the 50-59 401(k) catch-up', () => {
    expect(getAnnualLimit('401k', 55)).toBe(24500 + 8000)
  })

  it('applies the higher 60-63 401(k) catch-up', () => {
    expect(getAnnualLimit('401k', 62)).toBe(24500 + 11250)
  })

  it('drops back to the 50-59 catch-up at 64', () => {
    expect(getAnnualLimit('401k', 64)).toBe(24500 + 8000)
  })

  it('applies the IRA catch-up at 50 for both Roth and traditional', () => {
    expect(getAnnualLimit('roth_ira', 50)).toBe(7500 + 1100)
    expect(getAnnualLimit('traditional_ira', 50)).toBe(7500 + 1100)
    expect(getAnnualLimit('roth_ira', 40)).toBe(7500)
  })

  it('applies the HSA catch-up at 55, self-only vs family', () => {
    expect(getAnnualLimit('hsa_self', 55)).toBe(4400 + 1000)
    expect(getAnnualLimit('hsa_family', 55)).toBe(8750 + 1000)
    expect(getAnnualLimit('hsa_self', 30)).toBe(4400)
  })

  it('returns null for personal investing accounts (no IRS cap)', () => {
    expect(getAnnualLimit('personal')).toBeNull()
  })
})

describe('accountTypeLabel', () => {
  it('labels known account types', () => {
    expect(accountTypeLabel('401k')).toBe('401(k) / 403(b)')
    expect(accountTypeLabel('hsa_family')).toBe('HSA (family)')
  })

  it('falls back to the raw key for unknown types', () => {
    expect(accountTypeLabel('mystery')).toBe('mystery')
  })
})
