import { describe, expect, it } from 'vitest'
import {
  addEstimatedMarketDays,
  standardMeasuresCountdown,
} from './liveTrackingAvailability.js'

function marketDates(start, end) {
  const dates = []
  let cursor = Date.parse(`${start}T00:00:00Z`)
  const finish = Date.parse(`${end}T00:00:00Z`)
  while (cursor <= finish) {
    const weekday = new Date(cursor).getUTCDay()
    if (weekday !== 0 && weekday !== 6) dates.push(new Date(cursor).toISOString().slice(0, 10))
    cursor += 86400000
  }
  return dates
}

describe('live tracking availability countdown', () => {
  it('counts returns and estimates the first standard-measures date across a weekend', () => {
    const status = standardMeasuresCountdown({
      dates: marketDates('2026-07-20', '2026-08-12'),
      now: '2026-08-12T16:00:00Z',
    })
    expect(status).toMatchObject({
      observations: 17,
      remainingReturns: 3,
      targetDate: '2026-08-17',
      calendarDaysToTarget: 5,
      progressPct: 85,
      available: false,
    })
  })

  it('does not count Saturday or Sunday as expected return dates', () => {
    expect(addEstimatedMarketDays('2026-08-14', 1)).toBe('2026-08-17')
  })

  it('switches to live when the twentieth daily return arrives', () => {
    const status = standardMeasuresCountdown({
      dates: marketDates('2026-07-20', '2026-08-17'),
      now: '2026-08-17T21:00:00Z',
    })
    expect(status.available).toBe(true)
    expect(status.remainingReturns).toBe(0)
    expect(status.progressPct).toBe(100)
  })
})
