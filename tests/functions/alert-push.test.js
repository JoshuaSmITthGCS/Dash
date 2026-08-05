import { describe, expect, it } from 'vitest'
import { buildPushPayload, isQuietTime } from '../../netlify/functions/alert-push.mjs'

describe('grouped alert push delivery', () => {
  it('groups several events into one payload', () => {
    const result = buildPushPayload([{ title: 'AAPL alert' }, { title: 'MSFT alert' }])
    expect(result).toMatchObject({ title: '2 ValueSignal alerts', url: '/alerts', renotify: true })
    expect(result.body).toContain('AAPL alert')
  })

  it('honors overnight quiet hours in the saved timezone', () => {
    const settings = { quietHoursStart: '22:00', quietHoursEnd: '07:00', timeZone: 'UTC' }
    expect(isQuietTime(settings, new Date('2026-08-05T23:00:00Z'))).toBe(true)
    expect(isQuietTime(settings, new Date('2026-08-05T12:00:00Z'))).toBe(false)
  })
})
