import { describe, expect, it } from 'vitest'
import { MOBILE_NAV } from './App.jsx'

describe('mobile navigation contract', () => {
  it('uses the report as the centered cold-start destination', () => {
    expect(MOBILE_NAV.map((item) => item.label)).toEqual(['Research', 'Search', 'Report', 'Portfolio', 'Watchlist', 'Planning', 'Screens'])
    expect(MOBILE_NAV[2]).toMatchObject({ to: '/', primary: true, end: true })
    expect(MOBILE_NAV.some((item) => item.to === '/market')).toBe(false)
  })
})
