import { describe, expect, it } from 'vitest'
import { isRefreshDue, msUntilNextBoundary } from './nightlyRefresh'

describe('isRefreshDue', () => {
  it('is due when there is no prior fetch at all', () => {
    expect(isRefreshDue(null, new Date('2026-08-05T13:00:00'))).toBe(true)
    expect(isRefreshDue(undefined, new Date('2026-08-05T13:00:00'))).toBe(true)
    expect(isRefreshDue('not-a-date', new Date('2026-08-05T13:00:00'))).toBe(true)
  })

  it('is due before today\'s 9pm boundary if the last fetch predates yesterday\'s 9pm', () => {
    const now = new Date('2026-08-05T10:00:00')
    expect(isRefreshDue('2026-08-04T20:00:00', now)).toBe(true)
  })

  it('is not due once a fetch has landed at or after the most recent 9pm boundary', () => {
    const now = new Date('2026-08-05T22:00:00')
    expect(isRefreshDue('2026-08-05T21:30:00', now)).toBe(false)
  })

  it('is due again once a new 9pm boundary has passed, even with a same-evening prior fetch', () => {
    const now = new Date('2026-08-06T21:15:00')
    expect(isRefreshDue('2026-08-05T21:30:00', now)).toBe(true)
  })

  it('is due right at 9:15pm if the day\'s only fetch was this morning', () => {
    const now = new Date('2026-08-05T21:15:00')
    expect(isRefreshDue('2026-08-05T09:00:00', now)).toBe(true)
  })
})

describe('msUntilNextBoundary', () => {
  it('counts forward to today\'s 9pm when called earlier in the day', () => {
    const now = new Date('2026-08-05T20:00:00')
    expect(msUntilNextBoundary(now)).toBe(60 * 60 * 1000)
  })

  it('rolls over to tomorrow\'s 9pm once today\'s has passed', () => {
    const now = new Date('2026-08-05T21:00:01')
    const expected = new Date('2026-08-06T21:00:00').getTime() - now.getTime()
    expect(msUntilNextBoundary(now)).toBe(expected)
  })
})
