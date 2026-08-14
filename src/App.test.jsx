import { describe, expect, it } from 'vitest'
import { MOBILE_NAV } from './App.jsx'

describe('mobile navigation contract', () => {
  it('presents exactly five tabs: Home, Portfolio, Research, Markets, More', () => {
    expect(MOBILE_NAV.map((item) => item.label)).toEqual(['Home', 'Portfolio', 'Research', 'Markets', 'More'])
    expect(MOBILE_NAV[0]).toMatchObject({ to: '/', end: true })
    expect(MOBILE_NAV.some((item) => item.to === '/market')).toBe(false)
  })
})
