import { describe, expect, it } from 'vitest'
import { hourLabel, mostRecentWeeklyRefreshMs, refreshBoundaryLabel, weekdayLabel } from './marketCalendar.js'

describe('mostRecentWeeklyRefreshMs', () => {
  it('returns the prior Friday close when the current week has not reached it yet (EST)', () => {
    // 2023-01-06 was a Friday. 20:00 UTC = 15:00 EST, an hour before the 16:00 close.
    const nowMs = Date.parse('2023-01-06T20:00:00Z')
    const boundary = mostRecentWeeklyRefreshMs(nowMs)
    expect(new Date(boundary).toISOString()).toBe(new Date('2022-12-30T21:00:00.000Z').toISOString())
  })

  it('returns this week\'s Friday close once it has passed (EST)', () => {
    // 21:30 UTC = 16:30 EST, half an hour after the 16:00 close.
    const nowMs = Date.parse('2023-01-06T21:30:00Z')
    const boundary = mostRecentWeeklyRefreshMs(nowMs)
    expect(new Date(boundary).toISOString()).toBe(new Date('2023-01-06T21:00:00.000Z').toISOString())
  })

  it('accounts for daylight saving time (EDT, UTC-4)', () => {
    // 2023-08-04 was a Friday. 20:30 UTC = 16:30 EDT, after the 16:00 close.
    const nowMs = Date.parse('2023-08-04T20:30:00Z')
    const boundary = mostRecentWeeklyRefreshMs(nowMs)
    expect(new Date(boundary).toISOString()).toBe(new Date('2023-08-04T20:00:00.000Z').toISOString())
  })

  it('holds steady across the rest of the week until the next Friday close', () => {
    const fridayClose = mostRecentWeeklyRefreshMs(Date.parse('2023-01-06T21:30:00Z'))
    const wednesdayAfter = mostRecentWeeklyRefreshMs(Date.parse('2023-01-11T18:00:00Z'))
    expect(wednesdayAfter).toBe(fridayClose)
  })
})

describe('display labels', () => {
  it('names the weekday from its numeric index', () => {
    expect(weekdayLabel(5)).toBe('Friday')
    expect(weekdayLabel(0)).toBe('Sunday')
  })

  it('formats the hour in 12-hour clock form', () => {
    expect(hourLabel(16)).toBe('4pm')
    expect(hourLabel(0)).toBe('12am')
    expect(hourLabel(12)).toBe('12pm')
  })

  it('combines the configured weekday and hour into one label', () => {
    expect(refreshBoundaryLabel()).toBe('Friday 4pm market close')
  })
})
