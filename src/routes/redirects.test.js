import { describe, expect, it } from 'vitest'
import { REDIRECTS, findRedirect, resolveRedirect } from './redirects.js'

describe('REDIRECTS', () => {
  it('has no duplicate "from" paths', () => {
    const froms = REDIRECTS.map((entry) => entry.from)
    expect(new Set(froms).size).toBe(froms.length)
  })

  it('covers every legacy options strategy route, flat and nested', () => {
    for (const id of ['short-term-trades', 'covered-call', 'cash-secured-put', 'protective-put', 'collar', 'vertical-spread', 'advanced-strategies']) {
      expect(findRedirect(`/screens/options/${id}`)?.to()).toBe(`/screens?recipe=options&strategy=${id}`)
      expect(findRedirect(`/screens/${id}`)?.to()).toBe(`/screens?recipe=options&strategy=${id}`)
    }
  })

  it('collapses /market directly to /markets?view=news, not through /news first', () => {
    expect(findRedirect('/market')?.to()).toBe('/markets?view=news')
  })

  it('maps every /portfolio/* sub-route to its view param', () => {
    expect(findRedirect('/portfolio/performance')?.to()).toBe('/portfolio?view=performance')
    expect(findRedirect('/portfolio/data-overview')?.to()).toBe('/portfolio?view=data')
    expect(findRedirect('/finances')?.to()).toBe('/portfolio?view=finances')
    expect(findRedirect('/planning')?.to()).toBe('/portfolio?view=planning')
  })

  it('maps every screens family route to its recipe param', () => {
    expect(findRedirect('/screens/swing')?.to()).toBe('/screens?recipe=swing')
    expect(findRedirect('/screens/themes')?.to()).toBe('/screens?recipe=themes')
  })
})

describe('findRedirect', () => {
  it('returns null for a route that is not retired', () => {
    expect(findRedirect('/research')).toBeNull()
    expect(findRedirect('/not-a-real-route')).toBeNull()
  })
})

describe('resolveRedirect — the /search param-mapping fix', () => {
  it('maps the ?q= param instead of dropping it', () => {
    const entry = findRedirect('/search')
    const params = new URLSearchParams('q=AAPL')
    expect(resolveRedirect(entry, params)).toBe('/research?q=AAPL')
  })

  it('handles a missing q param without throwing', () => {
    const entry = findRedirect('/search')
    expect(resolveRedirect(entry, new URLSearchParams())).toBe('/research?q=')
  })
})
