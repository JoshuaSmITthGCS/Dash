import { describe, expect, it } from 'vitest'
import { calculateAge, isValidBirthDate, parseDateOnly, RETIREMENT_AGES } from './age.js'

describe('age helpers', () => {
  const today = new Date(2026, 7, 4)

  it('calculates age using whether the birthday has occurred this year', () => {
    expect(calculateAge('1990-08-04', today)).toBe(36)
    expect(calculateAge('1990-08-05', today)).toBe(35)
  })

  it('rejects impossible, future, and implausibly old birthdates', () => {
    expect(parseDateOnly('2024-02-30')).toBeNull()
    expect(isValidBirthDate('2027-01-01', today)).toBe(false)
    expect(isValidBirthDate('1900-01-01', today)).toBe(false)
  })

  it('provides the supported retirement age choices', () => {
    expect(RETIREMENT_AGES).toEqual([30, 40, 45, 50, 60, 65])
  })
})
