import { describe, expect, it } from 'vitest'
import { seedFor, seededInt, seededRange } from './seed.js'

describe('seedFor', () => {
  it('is deterministic for the same id', () => {
    const a = seedFor('rank_ic_1d')
    const b = seedFor('rank_ic_1d')
    expect(a()).toBe(b())
  })

  it('produces different sequences for different ids', () => {
    const a = seedFor('rank_ic_1d')()
    const b = seedFor('deflated_sharpe')()
    expect(a).not.toBe(b)
  })

  it('returns values in [0, 1)', () => {
    const rng = seedFor('pbo')
    for (let i = 0; i < 50; i += 1) {
      const value = rng()
      expect(value).toBeGreaterThanOrEqual(0)
      expect(value).toBeLessThan(1)
    }
  })

  it('handles a missing id without throwing', () => {
    expect(() => seedFor(undefined)()).not.toThrow()
    expect(() => seedFor(null)()).not.toThrow()
  })
})

describe('seededRange', () => {
  it('is deterministic and within bounds', () => {
    const a = seededRange('gain_to_pain', 2, 8)
    const b = seededRange('gain_to_pain', 2, 8)
    expect(a).toBe(b)
    expect(a).toBeGreaterThanOrEqual(2)
    expect(a).toBeLessThan(8)
  })

  it('salts to a distinct sub-sequence', () => {
    const base = seededRange('omega', 0, 1)
    const salted = seededRange('omega', 0, 1, 'smudge')
    expect(salted).not.toBe(base)
  })
})

describe('seededInt', () => {
  it('is an integer within the inclusive range', () => {
    for (let i = 0; i < 20; i += 1) {
      const value = seededInt(`ticker-${i}`, 1, 5)
      expect(Number.isInteger(value)).toBe(true)
      expect(value).toBeGreaterThanOrEqual(1)
      expect(value).toBeLessThanOrEqual(5)
    }
  })
})
