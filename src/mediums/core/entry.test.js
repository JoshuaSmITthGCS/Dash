import { describe, expect, it } from 'vitest'
import { isEntryEligiblePath, computeShowEntry } from './entry.js'

describe('isEntryEligiblePath', () => {
  it('is eligible only on the exact root with no params', () => {
    expect(isEntryEligiblePath('/v2', '', '/v2')).toBe(true)
    expect(isEntryEligiblePath('/v2', '?', '/v2')).toBe(true)
  })

  it('is never eligible on a deep-linked path — the structural bypass', () => {
    expect(isEntryEligiblePath('/v2/research', '', '/v2')).toBe(false)
    expect(isEntryEligiblePath('/v2/screens', '?recipe=swing', '/v2')).toBe(false)
  })

  it('is never eligible when the root carries any query param', () => {
    expect(isEntryEligiblePath('/v2', '?customize=1', '/v2')).toBe(false)
  })
})

describe('computeShowEntry', () => {
  const base = { hasEntry: true, pathname: '/v2', search: '', rootPath: '/v2', seen: false, entrySkip: false }

  it('shows entry when every condition holds', () => {
    expect(computeShowEntry(base)).toBe(true)
  })

  it('never shows when the medium has no entry', () => {
    expect(computeShowEntry({ ...base, hasEntry: false })).toBe(false)
  })

  it('never shows off the destination root — deep link bypass', () => {
    expect(computeShowEntry({ ...base, pathname: '/v2/research' })).toBe(false)
  })

  it('never shows twice in one session', () => {
    expect(computeShowEntry({ ...base, seen: true })).toBe(false)
  })

  it('never shows once the user has opted out', () => {
    expect(computeShowEntry({ ...base, entrySkip: true })).toBe(false)
  })
})
